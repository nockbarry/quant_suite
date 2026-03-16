#!/usr/bin/env python3
"""Quick trade execution helpers.

Usage:
    # Buy 10 shares of MU (default: paper account)
    PYTHONPATH=. python3 scripts/quick_trade.py buy MU 10

    # Sell on live account
    PYTHONPATH=. python3 scripts/quick_trade.py sell SLB 5 --live

    # Check positions for a thesis
    PYTHONPATH=. python3 scripts/quick_trade.py positions --thesis "Venezuela"

    # Compare all accounts
    PYTHONPATH=. python3 scripts/quick_trade.py status

    # Get quote
    PYTHONPATH=. python3 scripts/quick_trade.py quote MU FCX LEN

Account flags:
    --live      Use live trading account (real money)
    --paper     Use paper trading account (default)
    --tracking  Use paper position tracker (no broker)
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.instance import instance_config
from src.core.paths import paths
from src.execution.accounts import AccountManager, TradingAccount, get_account_manager


def get_broker(paper: bool = True):
    """Get connected broker instance (legacy support)."""
    import yaml
    from src.execution.broker.alpaca import AlpacaBroker

    creds_path = instance_config.credentials_path()
    with open(creds_path, 'r') as f:
        creds = yaml.safe_load(f)

    alpaca = creds.get('alpaca', {})
    return AlpacaBroker(
        api_key=alpaca.get('api_key'),
        secret_key=alpaca.get('secret_key'),
        paper=paper
    )


def get_account_type(args) -> TradingAccount:
    """Determine account type from args."""
    if getattr(args, 'live', False):
        return TradingAccount.LIVE
    elif getattr(args, 'tracking', False):
        return TradingAccount.TRACKING
    return TradingAccount.PAPER


async def cmd_buy(args):
    """Execute buy order."""
    account_type = get_account_type(args)
    manager = get_account_manager()

    # Handle tracking account separately
    if account_type == TradingAccount.TRACKING:
        from src.knowledge.paper_positions import PaperPositionTracker
        tracker = PaperPositionTracker()
        # Need a broker just for quotes
        broker = get_broker(paper=True)
        await broker.connect()
        quote = await broker.get_quote(args.symbol)
        price = float(quote.last)
        await broker.disconnect()

        if args.value:
            qty = int(args.value / price)
        else:
            qty = args.quantity

        position = tracker.add_position(
            symbol=args.symbol,
            quantity=qty,
            entry_price=price,
            notes=f"Added via quick_trade"
        )
        print(f"✓ TRACKING BUY {qty} {args.symbol} @ ${price:.2f}")
        print(f"  Position ID: {position.id}")
        return

    broker = await manager.get_broker(account_type)

    try:
        # Get quote and account info
        quote = await broker.get_quote(args.symbol)
        price = float(quote.last)
        account = await broker.get_account()
        portfolio_value = float(account.portfolio_value)

        if args.value:
            qty = int(args.value / price)
            value = args.value
        else:
            qty = args.quantity
            value = qty * price

        # Validate trade against risk limits
        is_valid, reason = manager.validate_trade(
            account=account_type,
            symbol=args.symbol,
            value=value,
            portfolio_value=portfolio_value,
        )

        if not is_valid:
            print(f"✗ BLOCKED: {reason}")
            if account_type == TradingAccount.LIVE:
                print(f"  (Live account has stricter limits)")
            return

        # Extra confirmation for live trades
        if account_type == TradingAccount.LIVE:
            print(f"⚠️  LIVE TRADE: BUY {qty} {args.symbol} @ ${price:.2f} = ${value:.2f}")
            confirm = input("  Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("  Cancelled.")
                return

        order = await broker.market_buy(args.symbol, Decimal(qty))
        account_label = "LIVE" if account_type == TradingAccount.LIVE else "PAPER"
        print(f"✓ [{account_label}] BUY {qty} {args.symbol}")
        print(f"  Order ID: {order.order_id}")
        print(f"  Status: {order.status}")
    finally:
        await manager.close_all()


async def cmd_sell(args):
    """Execute sell order."""
    account_type = get_account_type(args)
    manager = get_account_manager()

    # Handle tracking account
    if account_type == TradingAccount.TRACKING:
        from src.knowledge.paper_positions import PaperPositionTracker
        tracker = PaperPositionTracker()
        positions = tracker.get_positions_for_symbol(args.symbol)
        if positions:
            for p in positions:
                tracker.remove_position(p.id)
            print(f"✓ TRACKING SELL {args.symbol} (removed {len(positions)} position(s))")
        else:
            print(f"No tracking positions for {args.symbol}")
        return

    broker = await manager.get_broker(account_type)

    try:
        # Extra confirmation for live trades
        if account_type == TradingAccount.LIVE:
            print(f"⚠️  LIVE TRADE: SELL {args.quantity} {args.symbol}")
            confirm = input("  Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("  Cancelled.")
                return

        order = await broker.market_sell(args.symbol, Decimal(args.quantity))
        account_label = "LIVE" if account_type == TradingAccount.LIVE else "PAPER"
        print(f"✓ [{account_label}] SELL {args.quantity} {args.symbol}")
        print(f"  Order ID: {order.order_id}")
        print(f"  Status: {order.status}")
    finally:
        await manager.close_all()


async def cmd_quote(args):
    """Get quotes for symbols."""
    broker = get_broker()
    await broker.connect()

    try:
        for symbol in args.symbols:
            quote = await broker.get_quote(symbol)
            if quote:
                print(f"{symbol}: ${float(quote.last):.2f} (bid ${float(quote.bid):.2f} / ask ${float(quote.ask):.2f})")
            else:
                print(f"{symbol}: No quote available")
    finally:
        await broker.disconnect()


async def cmd_positions(args):
    """Show positions, optionally filtered by thesis."""
    broker = get_broker()
    await broker.connect()

    try:
        positions = await broker.get_positions()
        account = await broker.get_account()

        print(f"Portfolio: ${float(account.portfolio_value):,.2f} | Cash: ${float(account.cash):,.2f}")
        print()

        # Filter by thesis if specified
        if args.thesis:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            thesis_symbols = set()
            for t in tracker.get_active_theses():
                if args.thesis.lower() in t.name.lower():
                    thesis_symbols.update(t.positions)
                    print(f"Thesis: {t.name} ({t.conviction}% conviction)")
            print()
            positions = {s: p for s, p in positions.items() if str(s) in thesis_symbols}

        total_value = 0
        total_pnl = 0
        for sym, pos in sorted(positions.items(), key=lambda x: float(x[1].market_value or 0), reverse=True):
            value = float(pos.market_value) if pos.market_value else 0
            pnl = float(pos.unrealized_pnl) if pos.unrealized_pnl else 0
            pnl_pct = float(pos.unrealized_pnl_pct) * 100 if pos.unrealized_pnl_pct else 0
            qty = float(pos.quantity) if pos.quantity else 0

            pnl_sign = "+" if pnl >= 0 else ""
            print(f"{sym}: {qty:.0f} @ ${value:,.0f} ({pnl_sign}{pnl_pct:.1f}%)")
            total_value += value
            total_pnl += pnl

        pnl_sign = "+" if total_pnl >= 0 else ""
        print(f"\nTotal: ${total_value:,.0f} | P&L: {pnl_sign}${total_pnl:,.0f}")
    finally:
        await broker.disconnect()


async def cmd_close(args):
    """Close a position entirely."""
    account_type = get_account_type(args)

    if account_type == TradingAccount.TRACKING:
        from src.knowledge.paper_positions import PaperPositionTracker
        tracker = PaperPositionTracker()
        positions = tracker.get_positions_for_symbol(args.symbol)
        if positions:
            for p in positions:
                tracker.remove_position(p.id)
            print(f"✓ TRACKING CLOSED {args.symbol}")
        else:
            print(f"No tracking positions for {args.symbol}")
        return

    manager = get_account_manager()
    broker = await manager.get_broker(account_type)

    try:
        if account_type == TradingAccount.LIVE:
            print(f"⚠️  LIVE TRADE: CLOSE {args.symbol}")
            confirm = input("  Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("  Cancelled.")
                return

        order = await broker.close_position(args.symbol)
        if order:
            account_label = "LIVE" if account_type == TradingAccount.LIVE else "PAPER"
            print(f"✓ [{account_label}] CLOSED {args.symbol}")
            print(f"  Order ID: {order.order_id}")
        else:
            print(f"No position in {args.symbol}")
    finally:
        await manager.close_all()


async def cmd_status(args):
    """Show status of all accounts."""
    manager = get_account_manager()

    print("=" * 70)
    print("MULTI-ACCOUNT STATUS")
    print("=" * 70)

    # Paper account
    try:
        broker = await manager.get_broker(TradingAccount.PAPER)
        account = await broker.get_account()
        positions = await broker.get_positions()

        total_value = sum(float(p.market_value or 0) for p in positions.values())
        total_pnl = sum(float(p.unrealized_pnl or 0) for p in positions.values())
        pnl_sign = "+" if total_pnl >= 0 else ""

        print(f"\n[PAPER] Alpaca Paper Trading")
        print(f"  Portfolio: ${float(account.portfolio_value):,.2f}")
        print(f"  Cash: ${float(account.cash):,.2f}")
        print(f"  Positions: {len(positions)} ({pnl_sign}${total_pnl:,.0f} P&L)")
    except Exception as e:
        print(f"\n[PAPER] Error: {e}")

    # Live account
    try:
        if manager.is_enabled(TradingAccount.LIVE):
            broker = await manager.get_broker(TradingAccount.LIVE)
            account = await broker.get_account()
            positions = await broker.get_positions()

            total_pnl = sum(float(p.unrealized_pnl or 0) for p in positions.values())
            pnl_sign = "+" if total_pnl >= 0 else ""

            print(f"\n[LIVE] Alpaca Live Trading")
            print(f"  Portfolio: ${float(account.portfolio_value):,.2f}")
            print(f"  Cash: ${float(account.cash):,.2f}")
            print(f"  Positions: {len(positions)} ({pnl_sign}${total_pnl:,.0f} P&L)")
        else:
            print(f"\n[LIVE] Not enabled (set live_trading_enabled: true in credentials.yaml)")
    except Exception as e:
        print(f"\n[LIVE] Error: {e}")

    # Tracking
    try:
        from src.knowledge.paper_positions import PaperPositionTracker
        tracker = PaperPositionTracker()
        positions = tracker.get_positions()

        if positions:
            # Update prices
            broker = get_broker(paper=True)
            await broker.connect()
            await tracker.update_prices(broker)
            await broker.disconnect()

            total_entry = sum(p.entry_value for p in positions)
            total_current = sum(p.current_value or 0 for p in positions)
            total_pnl = total_current - total_entry
            pnl_sign = "+" if total_pnl >= 0 else ""

            print(f"\n[TRACKING] Paper Position Tracker")
            print(f"  Entry Value: ${total_entry:,.2f}")
            print(f"  Current Value: ${total_current:,.2f}")
            print(f"  Positions: {len(positions)} ({pnl_sign}${total_pnl:,.0f} P&L)")
        else:
            print(f"\n[TRACKING] No paper positions")
    except Exception as e:
        print(f"\n[TRACKING] Error: {e}")

    await manager.close_all()
    print()


def add_account_args(parser):
    """Add account selection arguments to a parser."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="Use live account (real money)")
    group.add_argument("--paper", action="store_true", help="Use paper account (default)")
    group.add_argument("--tracking", action="store_true", help="Use paper position tracker")


def main():
    parser = argparse.ArgumentParser(description="Quick trade execution")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Buy
    buy_parser = subparsers.add_parser("buy", help="Buy shares")
    buy_parser.add_argument("symbol", help="Symbol to buy")
    buy_parser.add_argument("quantity", type=int, nargs="?", help="Number of shares")
    buy_parser.add_argument("--value", "-v", type=float, help="Dollar value to buy")
    add_account_args(buy_parser)
    buy_parser.set_defaults(func=cmd_buy)

    # Sell
    sell_parser = subparsers.add_parser("sell", help="Sell shares")
    sell_parser.add_argument("symbol", help="Symbol to sell")
    sell_parser.add_argument("quantity", type=int, help="Number of shares")
    add_account_args(sell_parser)
    sell_parser.set_defaults(func=cmd_sell)

    # Quote
    quote_parser = subparsers.add_parser("quote", help="Get quotes")
    quote_parser.add_argument("symbols", nargs="+", help="Symbols to quote")
    quote_parser.set_defaults(func=cmd_quote)

    # Positions
    pos_parser = subparsers.add_parser("positions", help="Show positions")
    pos_parser.add_argument("--thesis", "-t", help="Filter by thesis name")
    add_account_args(pos_parser)
    pos_parser.set_defaults(func=cmd_positions)

    # Close
    close_parser = subparsers.add_parser("close", help="Close position")
    close_parser.add_argument("symbol", help="Symbol to close")
    add_account_args(close_parser)
    close_parser.set_defaults(func=cmd_close)

    # Status - show all accounts
    status_parser = subparsers.add_parser("status", help="Show all account status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
