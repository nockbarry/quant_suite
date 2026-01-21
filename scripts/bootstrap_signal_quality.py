#!/usr/bin/env python3
"""
Bootstrap Signal Quality Tracker with Historical Trades.

Reads closed positions from Alpaca and logs signal outcomes to initialize
the signal quality tracking system with historical data.

Usage:
    python3 scripts/bootstrap_signal_quality.py
    python3 scripts/bootstrap_signal_quality.py --dry-run
    python3 scripts/bootstrap_signal_quality.py --days 30
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.signal_quality_tracker import (
    SignalQualityTracker,
    log_signal_outcome,
    get_signal_quality_tracker,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_closed_positions(days: int = 30) -> list[dict]:
    """Get closed positions from Alpaca."""
    import yaml
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import OrderSide, QueryOrderStatus

    # Load credentials
    creds_file = Path(__file__).parent.parent / "config/credentials.yaml"
    with open(creds_file) as f:
        creds = yaml.safe_load(f)

    client = TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True
    )

    # Get closed orders
    after_date = datetime.now() - timedelta(days=days)
    request = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        after=after_date,
        limit=500,
    )

    orders = client.get_orders(filter=request)

    # Group by symbol to calculate P&L
    positions = {}
    for order in orders:
        if order.filled_qty is None or float(order.filled_qty) == 0:
            continue

        symbol = order.symbol
        if symbol not in positions:
            positions[symbol] = {
                "symbol": symbol,
                "buys": [],
                "sells": [],
            }

        entry = {
            "qty": float(order.filled_qty),
            "price": float(order.filled_avg_price) if order.filled_avg_price else 0,
            "date": order.filled_at.isoformat() if order.filled_at else order.created_at.isoformat(),
            "side": order.side.value,
        }

        if order.side == OrderSide.BUY:
            positions[symbol]["buys"].append(entry)
        else:
            positions[symbol]["sells"].append(entry)

    # Calculate realized P&L for positions with both buys and sells
    closed_positions = []
    for symbol, data in positions.items():
        if not data["buys"] or not data["sells"]:
            continue

        # Simple FIFO matching
        total_buy_qty = sum(b["qty"] for b in data["buys"])
        total_sell_qty = sum(s["qty"] for s in data["sells"])
        total_buy_cost = sum(b["qty"] * b["price"] for b in data["buys"])
        total_sell_proceeds = sum(s["qty"] * s["price"] for s in data["sells"])

        if total_buy_qty == 0:
            continue

        avg_buy_price = total_buy_cost / total_buy_qty
        avg_sell_price = total_sell_proceeds / total_sell_qty if total_sell_qty > 0 else 0

        closed_qty = min(total_buy_qty, total_sell_qty)
        if closed_qty == 0:
            continue

        realized_pnl = closed_qty * (avg_sell_price - avg_buy_price)
        realized_pnl_pct = ((avg_sell_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0

        # Get dates
        buy_dates = [b["date"] for b in data["buys"]]
        sell_dates = [s["date"] for s in data["sells"]]
        first_buy = min(buy_dates) if buy_dates else None
        last_sell = max(sell_dates) if sell_dates else None

        # Calculate hold days
        hold_days = None
        if first_buy and last_sell:
            try:
                buy_dt = datetime.fromisoformat(first_buy.replace("Z", "+00:00"))
                sell_dt = datetime.fromisoformat(last_sell.replace("Z", "+00:00"))
                hold_days = (sell_dt - buy_dt).days
            except:
                pass

        closed_positions.append({
            "symbol": symbol,
            "qty": closed_qty,
            "buy_price": avg_buy_price,
            "sell_price": avg_sell_price,
            "buy_date": first_buy,
            "sell_date": last_sell,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "hold_days": hold_days,
        })

    return closed_positions


def infer_signal_type(symbol: str, pnl_pct: float) -> tuple[str, str, float]:
    """
    Infer the likely signal type based on symbol characteristics.
    Returns (signal_type, direction, estimated_strength).
    """
    # Options positions
    if len(symbol) > 10 and any(c.isdigit() for c in symbol[-8:]):
        return "options", "bullish" if "C" in symbol else "bearish", 0.6

    # Energy sector - likely thesis-driven
    energy_symbols = ['SLB', 'HAL', 'XLE', 'FRO', 'STNG', 'CNQ', 'PBF', 'BKR',
                     'PBR', 'PSX', 'IMO', 'DHT', 'OIH', 'XOP', 'MPC', 'INSW',
                     'ERX', 'GUSH', 'IEO', 'WFRD', 'KBR', 'FLR', 'PSN', 'J', 'SU',
                     'VLO', 'ERY', 'UVXY', 'VXX']
    if symbol in energy_symbols:
        return "technical", "bullish", 0.65

    # Gold sector
    gold_symbols = ['GLD', 'GDX', 'NEM', 'GOLD', 'NUGT', 'UGL']
    if symbol in gold_symbols:
        return "technical", "bullish", 0.7

    # Financials
    financials = ['JPM', 'GS', 'SYF', 'V', 'MA']
    if symbol in financials:
        return "technical", "bullish", 0.55

    # Tech
    tech = ['NVDA', 'GOOGL', 'MU', 'AMD', 'AAPL', 'MSFT']
    if symbol in tech:
        return "technical", "bullish", 0.6

    # Default
    return "technical", "bullish", 0.5


def bootstrap_from_closed_positions(positions: list[dict], dry_run: bool = False) -> dict:
    """Bootstrap signal quality tracker with closed position data."""
    results = {
        "total_positions": len(positions),
        "logged": 0,
        "skipped": 0,
        "by_signal_type": {},
    }

    for pos in positions:
        symbol = pos["symbol"]
        pnl = pos["realized_pnl"]
        pnl_pct = pos["realized_pnl_pct"]
        hold_days = pos.get("hold_days")

        # Infer signal type
        signal_type, direction, strength = infer_signal_type(symbol, pnl_pct)

        # Track by signal type
        if signal_type not in results["by_signal_type"]:
            results["by_signal_type"][signal_type] = {
                "count": 0,
                "profitable": 0,
                "total_pnl": 0,
            }

        results["by_signal_type"][signal_type]["count"] += 1
        results["by_signal_type"][signal_type]["total_pnl"] += pnl
        if pnl > 0:
            results["by_signal_type"][signal_type]["profitable"] += 1

        if dry_run:
            logger.info(f"[DRY RUN] Would log: {symbol} {signal_type} {direction} "
                       f"strength={strength:.2f} pnl=${pnl:.2f} ({pnl_pct:+.1f}%)")
            results["logged"] += 1
            continue

        # Log the signal outcome
        try:
            log_signal_outcome(
                signal_type=signal_type,
                symbol=symbol,
                direction=direction,
                signal_strength=strength,
                acted_on=True,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_days=hold_days,
            )
            results["logged"] += 1
            logger.info(f"Logged: {symbol} {signal_type} pnl=${pnl:.2f} ({pnl_pct:+.1f}%)")
        except Exception as e:
            logger.error(f"Error logging {symbol}: {e}")
            results["skipped"] += 1

    return results


def bootstrap_from_json_file(file_path: Path, dry_run: bool = False) -> dict:
    """Bootstrap from a JSON file of closed positions."""
    with open(file_path) as f:
        positions = json.load(f)

    results = {
        "total_positions": len(positions),
        "logged": 0,
        "skipped": 0,
        "by_signal_type": {},
    }

    for pos in positions:
        symbol = pos["symbol"]
        pnl = pos.get("realized_pnl", 0)
        pnl_pct = pos.get("realized_pnl_pct", 0)

        # Calculate hold days if dates available
        hold_days = None
        if pos.get("buy_date") and pos.get("sell_date"):
            try:
                buy_dt = datetime.fromisoformat(pos["buy_date"])
                sell_dt = datetime.fromisoformat(pos["sell_date"])
                hold_days = (sell_dt - buy_dt).days
            except:
                pass

        # Infer signal type
        signal_type, direction, strength = infer_signal_type(symbol, pnl_pct)

        # Track by signal type
        if signal_type not in results["by_signal_type"]:
            results["by_signal_type"][signal_type] = {
                "count": 0,
                "profitable": 0,
                "total_pnl": 0,
            }

        results["by_signal_type"][signal_type]["count"] += 1
        results["by_signal_type"][signal_type]["total_pnl"] += pnl
        if pnl > 0:
            results["by_signal_type"][signal_type]["profitable"] += 1

        if dry_run:
            logger.info(f"[DRY RUN] Would log: {symbol} {signal_type} {direction} "
                       f"strength={strength:.2f} pnl=${pnl:.2f} ({pnl_pct:+.1f}%)")
            results["logged"] += 1
            continue

        # Log the signal outcome
        try:
            log_signal_outcome(
                signal_type=signal_type,
                symbol=symbol,
                direction=direction,
                signal_strength=strength,
                acted_on=True,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_days=hold_days,
            )
            results["logged"] += 1
            logger.info(f"Logged: {symbol} {signal_type} pnl=${pnl:.2f} ({pnl_pct:+.1f}%)")
        except Exception as e:
            logger.error(f"Error logging {symbol}: {e}")
            results["skipped"] += 1

    return results


def print_summary(results: dict) -> None:
    """Print bootstrap summary."""
    print("\n" + "=" * 60)
    print("BOOTSTRAP SIGNAL QUALITY SUMMARY")
    print("=" * 60)

    print(f"\nTotal positions: {results['total_positions']}")
    print(f"Logged: {results['logged']}")
    print(f"Skipped: {results['skipped']}")

    print("\nBy Signal Type:")
    for sig_type, stats in results.get("by_signal_type", {}).items():
        count = stats["count"]
        profitable = stats["profitable"]
        hit_rate = (profitable / count * 100) if count > 0 else 0
        total_pnl = stats["total_pnl"]
        print(f"  {sig_type}:")
        print(f"    Count: {count}")
        print(f"    Profitable: {profitable} ({hit_rate:.0f}%)")
        print(f"    Total P&L: ${total_pnl:.2f}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Signal Quality Tracker")
    parser.add_argument("--dry-run", action="store_true", help="Preview without logging")
    parser.add_argument("--days", type=int, default=30, help="Days of history to fetch")
    parser.add_argument("--from-file", type=str, help="Load from JSON file instead of Alpaca")
    args = parser.parse_args()

    print("=" * 60)
    print("BOOTSTRAP SIGNAL QUALITY TRACKER")
    print("=" * 60)

    if args.from_file:
        file_path = Path(args.from_file)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return

        logger.info(f"Loading positions from: {file_path}")
        results = bootstrap_from_json_file(file_path, dry_run=args.dry_run)
    else:
        logger.info(f"Fetching closed positions from Alpaca (last {args.days} days)...")
        try:
            positions = get_closed_positions(days=args.days)
            logger.info(f"Found {len(positions)} closed positions")

            if not positions:
                logger.warning("No closed positions found")
                return

            results = bootstrap_from_closed_positions(positions, dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return

    print_summary(results)

    # Calculate and show updated quality metrics
    if not args.dry_run:
        print("\nRecalculating signal quality metrics...")
        tracker = get_signal_quality_tracker()
        quality = tracker.calculate_quality(days=30)

        print("\nUpdated Signal Quality:")
        for sig_type, q in quality.items():
            print(f"  {sig_type}: hit_rate={q.hit_rate:.0%}, "
                  f"acted_on={q.acted_on}, trend={q.trend}")


if __name__ == "__main__":
    main()
