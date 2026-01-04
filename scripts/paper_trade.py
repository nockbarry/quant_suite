#!/usr/bin/env python3
"""
Paper Trading Runner

Run strategies in paper trading mode with human-in-the-loop approval.

Usage:
    python scripts/paper_trade.py --strategy ma_crossover --symbols AAPL,MSFT,GOOGL
    python scripts/paper_trade.py --strategy momentum --config config/strategies/momentum.yaml
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from src.core import Portfolio, Signal, Symbol
from src.data import DataPipeline, FeatureEngine, ParquetStorage, YahooFinanceSource
from src.execution.approval import run_approval_session
from src.execution.broker.paper import PaperBroker, PaperTradingConfig
from src.execution.order_manager import OrderManager, OrderManagerConfig
from src.risk.limits import RiskLimitsConfig, RiskManager
from src.risk.position_sizing import get_position_sizer
from src.strategies import (
    MovingAverageCrossover,
    MomentumStrategy,
    BollingerBandMeanReversion,
    RSIMeanReversion,
    Strategy,
)

console = Console()
logger = logging.getLogger(__name__)


# Available strategies
STRATEGIES = {
    "ma_crossover": MovingAverageCrossover,
    "momentum": MomentumStrategy,
    "bb_reversion": BollingerBandMeanReversion,
    "rsi_reversion": RSIMeanReversion,
}


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Paper Trading Runner")

    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=list(STRATEGIES.keys()),
        help="Strategy to run",
    )

    parser.add_argument(
        "--symbols",
        type=str,
        default="SPY,AAPL,MSFT,GOOGL,AMZN",
        help="Comma-separated list of symbols",
    )

    parser.add_argument(
        "--capital",
        type=float,
        default=100000,
        help="Initial capital (default: 100000)",
    )

    parser.add_argument(
        "--position-size",
        type=float,
        default=0.10,
        help="Position size as fraction of portfolio (default: 0.10)",
    )

    parser.add_argument(
        "--sizing-method",
        type=str,
        default="fixed_fractional",
        choices=["fixed_fractional", "volatility_target", "kelly", "equal_weight"],
        help="Position sizing method",
    )

    parser.add_argument(
        "--require-approval",
        action="store_true",
        default=True,
        help="Require human approval for trades",
    )

    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="Auto-approve all trades (no human approval)",
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data/processed",
        help="Directory for cached data",
    )

    parser.add_argument(
        "--lookback-days",
        type=int,
        default=365,
        help="Days of historical data to fetch",
    )

    parser.add_argument(
        "--update-interval",
        type=int,
        default=60,
        help="Seconds between strategy updates",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


async def fetch_data(
    pipeline: DataPipeline,
    symbols: list[str],
    lookback_days: int,
) -> dict[str, any]:
    """Fetch historical data for symbols."""
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    console.print(f"[cyan]Fetching data for {len(symbols)} symbols...[/cyan]")

    data = await pipeline.fetch_multiple(
        symbols=symbols,
        start=start,
        end=end,
        overwrite=False,
    )

    console.print(f"[green]Fetched data for {len(data)} symbols[/green]")
    return data


def create_strategy(
    strategy_name: str,
    symbols: list[str],
    **kwargs,
) -> Strategy:
    """Create strategy instance."""
    strategy_class = STRATEGIES[strategy_name]
    return strategy_class(universe=symbols, **kwargs)


async def run_paper_trading(args: argparse.Namespace) -> None:
    """Main paper trading loop."""
    # Parse symbols
    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    console.print(Panel(
        f"[bold]Paper Trading Session[/bold]\n\n"
        f"Strategy: {args.strategy}\n"
        f"Symbols: {', '.join(symbols)}\n"
        f"Capital: ${args.capital:,.0f}\n"
        f"Position Size: {args.position_size:.0%}\n"
        f"Sizing Method: {args.sizing_method}\n"
        f"Approval Required: {not args.auto_trade}",
        title="[bold cyan]Quant Suite[/bold cyan]",
    ))

    # Initialize data pipeline
    source = YahooFinanceSource()
    storage = ParquetStorage(args.data_dir)
    pipeline = DataPipeline(source, storage)

    # Fetch initial data
    data = await fetch_data(pipeline, symbols, args.lookback_days)

    if not data:
        console.print("[red]No data available. Exiting.[/red]")
        return

    # Add features to data
    console.print("[cyan]Computing features...[/cyan]")
    for symbol in data:
        data[symbol] = FeatureEngine.add_all_features(data[symbol])

    # Initialize broker
    broker_config = PaperTradingConfig(
        initial_capital=Decimal(str(args.capital)),
        commission_percentage=Decimal("0.001"),
        slippage_percentage=Decimal("0.0005"),
    )

    # Set initial prices in paper broker
    broker = PaperBroker(broker_config)
    await broker.connect()

    for symbol, df in data.items():
        if len(df) > 0:
            broker.set_price(symbol, Decimal(str(df["close"].iloc[-1])))

    # Initialize order manager
    order_config = OrderManagerConfig(
        require_approval=not args.auto_trade,
        proposal_timeout_seconds=300,
    )

    def on_proposal(proposal):
        console.print(f"[yellow]New proposal: {proposal.proposal.order.symbol} "
                     f"{proposal.proposal.order.side.value}[/yellow]")

    def on_execution(order):
        console.print(f"[green]Executed: {order.symbol} {order.side.value} "
                     f"{order.quantity} @ {order.filled_price}[/green]")

    order_manager = OrderManager(
        broker=broker,
        config=order_config,
        on_proposal=on_proposal,
        on_execution=on_execution,
    )

    # Initialize risk manager
    risk_config = RiskLimitsConfig(
        max_position_pct=args.position_size * 2,  # Allow 2x position size
        max_drawdown_pct=0.20,
        max_daily_loss_pct=0.05,
    )
    risk_manager = RiskManager(config=risk_config)

    # Initialize position sizer
    position_sizer = get_position_sizer(
        args.sizing_method,
        fraction=args.position_size,
    )

    # Create strategy
    strategy = create_strategy(args.strategy, symbols)
    console.print(f"[green]Strategy initialized: {strategy.name}[/green]")

    # Create portfolio for position sizing
    portfolio = Portfolio(initial_capital=Decimal(str(args.capital)))

    # Main trading loop
    console.print("\n[bold]Starting trading loop...[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    iteration = 0
    try:
        while True:
            iteration += 1
            console.print(f"\n[bold]--- Iteration {iteration} ---[/bold]")

            # Update prices
            for symbol, df in data.items():
                if len(df) > 0:
                    broker.set_price(symbol, Decimal(str(df["close"].iloc[-1])))

            # Get current portfolio state
            account = await broker.get_account()
            positions = await broker.get_positions()

            console.print(f"Portfolio Value: ${account.portfolio_value:,.2f}")
            console.print(f"Cash: ${account.cash:,.2f}")
            console.print(f"Positions: {len(positions)}")

            # Update portfolio object for position sizer
            portfolio._cash = account.cash
            portfolio.positions = positions

            # Generate signals
            signals = strategy.generate_signals(data, datetime.now())

            if signals:
                console.print(f"[cyan]Generated {len(signals)} signals[/cyan]")

                for signal in signals:
                    console.print(
                        f"  {signal.symbol}: {signal.direction.value} "
                        f"(strength={signal.strength:.2f}, confidence={signal.confidence:.2f})"
                    )

                    # Get current price
                    quote = await broker.get_quote(signal.symbol)
                    if quote is None:
                        continue

                    price = quote.mid

                    # Calculate position size
                    size_result = position_sizer.calculate(
                        signal=signal,
                        portfolio=portfolio,
                        price=price,
                    )

                    if abs(size_result.target_quantity) < Decimal("0.01"):
                        continue

                    # Create order
                    from src.core import Order, OrderSide, OrderType

                    order = Order(
                        symbol=signal.symbol,
                        side=OrderSide.BUY if signal.strength > 0 else OrderSide.SELL,
                        quantity=abs(size_result.target_quantity),
                        order_type=OrderType.MARKET,
                        strategy_name=strategy.name,
                    )

                    # Check risk limits
                    allowed, violations = risk_manager.is_order_allowed(
                        order, portfolio, price
                    )

                    if not allowed:
                        console.print(f"[red]Order blocked by risk limits:[/red]")
                        for v in violations:
                            console.print(f"  - {v.message}")
                        continue

                    # Submit proposal
                    risk_metrics = {
                        "signal_strength": signal.strength,
                        "signal_confidence": signal.confidence,
                        "position_weight": size_result.target_weight,
                    }

                    await order_manager.propose_trade(
                        order=order,
                        reasoning=f"Signal from {strategy.name}: {signal.direction.value} "
                                 f"with strength {signal.strength:.2f}",
                        signal=signal,
                        risk_metrics=risk_metrics,
                    )

            else:
                console.print("[dim]No signals generated[/dim]")

            # Process pending proposals (if auto-trade or show pending)
            pending = order_manager.get_pending_proposals()
            if pending and not args.auto_trade:
                console.print(f"\n[yellow]{len(pending)} proposals pending approval[/yellow]")
                console.print("[dim]Run with --auto-trade to auto-approve[/dim]")

            # Wait for next iteration
            console.print(f"\n[dim]Next update in {args.update_interval}s...[/dim]")
            await asyncio.sleep(args.update_interval)

            # Refresh data periodically (every 10 iterations)
            if iteration % 10 == 0:
                console.print("[cyan]Refreshing data...[/cyan]")
                new_data = await fetch_data(pipeline, symbols, 30)
                for symbol in new_data:
                    if symbol in data:
                        # Append new data
                        data[symbol] = FeatureEngine.add_all_features(new_data[symbol])

    except KeyboardInterrupt:
        console.print("\n[yellow]Trading stopped by user[/yellow]")

    # Final summary
    account = await broker.get_account()
    console.print(Panel(
        f"[bold]Final Summary[/bold]\n\n"
        f"Portfolio Value: ${account.portfolio_value:,.2f}\n"
        f"Cash: ${account.cash:,.2f}\n"
        f"Total Trades: {account.metadata.get('total_trades', 0)}\n"
        f"Total Commission: ${float(account.metadata.get('total_commission', 0)):,.2f}",
        title="[bold cyan]Session Complete[/bold cyan]",
    ))

    await broker.disconnect()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    try:
        asyncio.run(run_paper_trading(args))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if args.verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
