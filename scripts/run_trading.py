#!/usr/bin/env python3
"""
Unified Trading Runner - Supports both Day Trading and Swing Trading

This script runs both intraday and swing strategies while tracking PDT compliance.
It separates day trades from swing trades so you can test both approaches.

Usage:
    # Generate signals only
    python scripts/run_trading.py --mode signals

    # Paper trading (default)
    python scripts/run_trading.py --mode paper

    # Day trading only (uses day trade capacity)
    python scripts/run_trading.py --mode paper --day-trades-only

    # Swing trading only (PDT safe)
    python scripts/run_trading.py --mode paper --swing-only

    # Monitor positions
    python scripts/run_trading.py --monitor

    # Check PDT status
    python scripts/run_trading.py --pdt-status
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import Direction, Signal
from src.execution.pdt_manager import PDTManager, PDTStatus, create_pdt_manager
from src.execution.broker.alpaca import AlpacaBroker
from src.strategies.intraday import (
    VWAPStrategy,
    IntradayMomentumStrategy,
    SessionPhase,
    get_session_phase,
)
from src.data.pipeline import (
    IntradayDataPipeline,
    IntradayDataConfig,
    is_market_open,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Output directories
RESULTS_DIR = Path("/home/nock/quant_results")
PDT_STATE_FILE = RESULTS_DIR / "pdt" / "pdt_state.json"
TRADES_DIR = RESULTS_DIR / "trades"


def load_credentials() -> dict:
    """Load trading credentials."""
    creds_path = Path(__file__).parent.parent / "config" / "credentials.yaml"
    if not creds_path.exists():
        raise FileNotFoundError(f"Credentials not found: {creds_path}")

    with open(creds_path) as f:
        return yaml.safe_load(f)


def load_pdt_manager() -> PDTManager:
    """Load PDT manager with persisted state."""
    PDT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PDT_STATE_FILE.exists():
        try:
            pdt = PDTManager.load(str(PDT_STATE_FILE))
            logger.info(f"Loaded PDT state: {pdt.day_trades_remaining} day trades remaining")
            return pdt
        except Exception as e:
            logger.warning(f"Could not load PDT state: {e}")

    # Create new PDT manager
    return create_pdt_manager(account_equity=100000)  # Will be updated with real value


def save_pdt_manager(pdt: PDTManager) -> None:
    """Save PDT manager state."""
    pdt.save(str(PDT_STATE_FILE))
    logger.info(f"Saved PDT state to {PDT_STATE_FILE}")


class TradingRunner:
    """
    Unified trading runner for day and swing trades.

    Tracks both trade types separately for PDT compliance.
    """

    def __init__(
        self,
        mode: str = "paper",
        day_trades_only: bool = False,
        swing_only: bool = False,
    ):
        self.mode = mode
        self.day_trades_only = day_trades_only
        self.swing_only = swing_only

        # Load credentials
        self.creds = load_credentials()

        # Initialize PDT manager
        self.pdt = load_pdt_manager()

        # Initialize broker (if not signals-only mode)
        self.broker = None
        if mode in ("paper", "live"):
            self.broker = self._init_broker()

        # Initialize strategies
        self.intraday_strategies = [
            VWAPStrategy(),
            IntradayMomentumStrategy(),
        ]

        # Track today's activity
        self.today_signals: list[dict] = []
        self.today_trades: list[dict] = []

    def _init_broker(self) -> AlpacaBroker:
        """Initialize Alpaca broker."""
        alpaca_creds = self.creds.get("alpaca", {})

        return AlpacaBroker(
            api_key=alpaca_creds.get("api_key"),
            secret_key=alpaca_creds.get("secret_key"),
            paper=alpaca_creds.get("paper", True),
        )

    async def update_account_info(self) -> dict[str, Any]:
        """Get current account info from broker."""
        if not self.broker:
            return {"equity": 100000, "cash": 100000, "positions": {}}

        try:
            # Connect if not connected
            from src.execution.broker.base import BrokerStatus
            if self.broker._status != BrokerStatus.CONNECTED:
                await self.broker.connect()

            account = await self.broker.get_account()
            positions = await self.broker.get_positions()

            # AccountInfo is an object, not a dict
            equity = float(account.portfolio_value)
            self.pdt.account_equity = equity

            return {
                "equity": equity,
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "positions": positions,
                "day_trade_count": account.day_trade_count,
                "pattern_day_trader": account.pattern_day_trader,
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {"equity": 100000, "cash": 100000, "positions": {}}

    async def get_pdt_status(self) -> dict[str, Any]:
        """Get comprehensive PDT status."""
        await self.update_account_info()

        return {
            "status": self.pdt.status.value,
            "day_trades_used": 3 - self.pdt.day_trades_remaining,
            "day_trades_remaining": self.pdt.day_trades_remaining,
            "can_day_trade": self.pdt.day_trades_remaining > 0,
            "positions_can_exit": [
                {"symbol": p.symbol, "entry_date": p.entry_date.isoformat()}
                for p in self.pdt.get_positions_can_exit()
            ],
            "positions_locked": [
                {
                    "symbol": p.symbol,
                    "entry_date": p.entry_date.isoformat(),
                    "min_exit_date": p.min_exit_date.isoformat() if p.min_exit_date else None,
                }
                for p in self.pdt.get_positions_locked()
            ],
            "recommendation": self._get_trading_recommendation(),
        }

    def _get_trading_recommendation(self) -> str:
        """Get recommendation based on PDT status."""
        status = self.pdt.status
        remaining = self.pdt.day_trades_remaining

        if status == PDTStatus.PDT_FLAGGED:
            return "FLAGGED: Swing trades only for 90 days"
        elif status == PDTStatus.RESTRICTED:
            return "RESTRICTED: Do NOT day trade - would trigger PDT flag"
        elif status == PDTStatus.AT_LIMIT:
            return "AT LIMIT: 3/3 day trades used. Swing trades only until reset."
        elif status == PDTStatus.WARNING:
            return f"WARNING: Only {remaining} day trade(s) left. Consider swing trades."
        else:
            return f"OK: {remaining} day trades available. Both strategies allowed."

    async def run_intraday_scan(self, symbols: list[str]) -> list[dict]:
        """
        Run intraday strategies and generate signals.

        Returns signals that pass PDT checks.
        """
        signals = []

        # Check if we can day trade
        if self.swing_only:
            logger.info("Swing-only mode: Skipping intraday scan")
            return signals

        can_day_trade, reason = self.pdt.can_day_trade()
        if not can_day_trade:
            logger.warning(f"Cannot day trade: {reason}")
            if self.day_trades_only:
                return signals

        # Get current session phase
        phase = get_session_phase(datetime.now())
        logger.info(f"Session phase: {phase.value}")

        # Initialize data pipeline
        config = IntradayDataConfig(
            symbols=symbols,
            timeframe="5Min",
            lookback_days=5,
        )
        pipeline = IntradayDataPipeline(config=config)

        # Fetch data (use yfinance as fallback)
        await pipeline.initialize()

        # Run strategies
        for strategy in self.intraday_strategies:
            for symbol in symbols:
                try:
                    data = pipeline.get_data(symbol)
                    if data.empty:
                        continue

                    strategy_signals = strategy.generate_signals(data)

                    for sig in strategy_signals:
                        signal_dict = {
                            "symbol": sig.symbol,
                            "direction": sig.direction.value,
                            "strategy": strategy.name,
                            "entry_price": sig.entry_price,
                            "stop_loss": sig.stop_loss,
                            "take_profit": sig.take_profit,
                            "confidence": sig.confidence,
                            "reason": sig.reason,
                            "timestamp": datetime.now().isoformat(),
                            "trade_type": "DAY_TRADE",
                            "session_phase": phase.value,
                        }
                        signals.append(signal_dict)
                        logger.info(f"Signal: {sig.direction.value} {symbol} - {sig.reason}")

                except Exception as e:
                    logger.error(f"Error scanning {symbol} with {strategy.name}: {e}")

        return signals

    async def check_swing_exits(self) -> list[dict]:
        """
        Check which swing positions can exit (held 2+ days).

        Returns exit signals for positions that can be closed.
        """
        exits = []

        can_exit = self.pdt.get_positions_can_exit()

        for position in can_exit:
            exits.append({
                "symbol": position.symbol,
                "action": "CAN_EXIT",
                "entry_date": position.entry_date.isoformat(),
                "entry_price": position.entry_price,
                "days_held": (datetime.now().date() - position.entry_date).days,
            })
            logger.info(f"Position {position.symbol} can exit (swing trade)")

        locked = self.pdt.get_positions_locked()
        for position in locked:
            logger.info(
                f"Position {position.symbol} LOCKED until {position.min_exit_date} "
                f"(avoid day trade)"
            )

        return exits

    async def record_trade(
        self,
        symbol: str,
        direction: str,
        price: float,
        quantity: int,
        is_entry: bool,
    ) -> dict:
        """
        Record a trade and update PDT tracking.

        Args:
            symbol: Stock symbol
            direction: "BUY" or "SELL"
            price: Execution price
            quantity: Number of shares
            is_entry: True for opening position, False for closing

        Returns:
            Trade record with PDT classification
        """
        trade_record = {
            "symbol": symbol,
            "direction": direction,
            "price": price,
            "quantity": quantity,
            "timestamp": datetime.now().isoformat(),
            "is_entry": is_entry,
        }

        if is_entry:
            # Record entry in PDT manager
            self.pdt.record_entry(symbol, price, quantity)
            trade_record["trade_type"] = "ENTRY"
            trade_record["min_exit_date"] = self.pdt.get_position(symbol).min_exit_date.isoformat()
            logger.info(f"Recorded entry: {symbol} @ ${price:.2f}")
        else:
            # Record exit and get trade type
            trade_type, trade_info = self.pdt.record_exit(symbol, price)
            trade_record["trade_type"] = trade_type.value
            trade_record["pnl"] = trade_info.pnl if trade_info else None
            trade_record["pnl_pct"] = trade_info.pnl_pct if trade_info else None
            logger.info(
                f"Recorded exit: {symbol} @ ${price:.2f} - "
                f"Type: {trade_type.value}"
            )

        # Save PDT state
        save_pdt_manager(self.pdt)

        # Add to today's trades
        self.today_trades.append(trade_record)

        return trade_record

    async def execute_signal(self, signal: dict, dry_run: bool = True) -> dict:
        """
        Execute a trading signal.

        Args:
            signal: Signal dictionary
            dry_run: If True, log but don't execute

        Returns:
            Execution result
        """
        symbol = signal["symbol"]
        direction = signal["direction"]

        result = {
            "signal": signal,
            "executed": False,
            "dry_run": dry_run,
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would execute: {direction} {symbol}")
            result["message"] = "Dry run - no execution"
            return result

        if not self.broker:
            result["error"] = "No broker connection"
            return result

        try:
            # Get current quote
            quote = await self.broker.get_quote(symbol)
            price = float(quote.get("ask", quote.get("last", 0)))

            # Calculate position size (5% of portfolio)
            account = await self.broker.get_account()
            equity = float(account.get("equity", 100000))
            position_value = equity * 0.05
            quantity = int(position_value / price)

            if quantity < 1:
                result["error"] = "Position size too small"
                return result

            # Submit order
            order = await self.broker.submit_order(
                symbol=symbol,
                qty=quantity,
                side=direction.lower(),
                order_type="market",
            )

            result["executed"] = True
            result["order"] = order
            result["price"] = price
            result["quantity"] = quantity

            # Record the trade
            await self.record_trade(
                symbol=symbol,
                direction=direction,
                price=price,
                quantity=quantity,
                is_entry=(direction == "BUY"),
            )

            logger.info(f"Executed: {direction} {quantity} {symbol} @ ${price:.2f}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Execution failed: {e}")

        return result

    async def run_daily_cycle(self, symbols: list[str]) -> dict:
        """
        Run a complete daily trading cycle.

        1. Update account info
        2. Check PDT status
        3. Scan for intraday signals (if allowed)
        4. Check swing exits
        5. Generate summary
        """
        logger.info("=" * 60)
        logger.info("DAILY TRADING CYCLE")
        logger.info("=" * 60)

        # 1. Update account info
        account = await self.update_account_info()
        logger.info(f"Account equity: ${account['equity']:,.2f}")
        logger.info(f"Positions: {len(account['positions'])}")

        # 2. Check PDT status
        pdt_status = await self.get_pdt_status()
        logger.info(f"PDT Status: {pdt_status['status']}")
        logger.info(f"Day trades remaining: {pdt_status['day_trades_remaining']}")
        logger.info(f"Recommendation: {pdt_status['recommendation']}")

        # 3. Scan for intraday signals
        intraday_signals = []
        if not self.swing_only and is_market_open():
            logger.info("\nScanning for intraday signals...")
            intraday_signals = await self.run_intraday_scan(symbols)
            logger.info(f"Found {len(intraday_signals)} intraday signals")

        # 4. Check swing exits
        logger.info("\nChecking swing positions...")
        swing_exits = await self.check_swing_exits()

        # 5. Generate summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "mode": self.mode,
            "account": account,
            "pdt_status": pdt_status,
            "intraday_signals": intraday_signals,
            "swing_exits": swing_exits,
            "market_open": is_market_open(),
        }

        # Save daily summary
        self._save_daily_summary(summary)

        return summary

    def _save_daily_summary(self, summary: dict) -> None:
        """Save daily summary to file."""
        TRADES_DIR.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = TRADES_DIR / f"daily_summary_{date_str}.json"

        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Saved daily summary to {filepath}")

    async def monitor_positions(self) -> dict:
        """Monitor current positions with real-time P&L."""
        if not self.broker:
            return {"error": "No broker connection"}

        # Connect if needed
        from src.execution.broker.base import BrokerStatus
        if self.broker._status != BrokerStatus.CONNECTED:
            await self.broker.connect()

        positions = await self.broker.get_positions()
        account = await self.broker.get_account()

        position_details = []
        for symbol, pos in positions.items():
            # Position is a Position object
            entry_price = float(pos.entry_price)
            current_price = float(pos.current_price)
            quantity = float(pos.quantity)

            unrealized_pnl = (current_price - entry_price) * quantity
            unrealized_pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0

            # Check PDT status for this position
            pdt_pos = self.pdt.get_position(symbol)
            can_exit = pdt_pos is None or pdt_pos.can_exit_without_day_trade()

            position_details.append({
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": entry_price,
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "can_exit_pdt_safe": can_exit,
                "market_value": current_price * quantity,
            })

        return {
            "timestamp": datetime.now().isoformat(),
            "equity": float(account.portfolio_value),
            "cash": float(account.cash),
            "positions": position_details,
            "pdt_status": await self.get_pdt_status(),
        }


async def main():
    parser = argparse.ArgumentParser(description="Unified Trading Runner")
    parser.add_argument(
        "--mode",
        choices=["signals", "paper", "live"],
        default="paper",
        help="Trading mode"
    )
    parser.add_argument(
        "--day-trades-only",
        action="store_true",
        help="Only run day trading strategies"
    )
    parser.add_argument(
        "--swing-only",
        action="store_true",
        help="Only run swing trading strategies (PDT safe)"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor current positions"
    )
    parser.add_argument(
        "--pdt-status",
        action="store_true",
        help="Show PDT status only"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SPY", "QQQ", "AAPL", "NVDA", "AMD", "TSLA"],
        help="Symbols to trade"
    )

    args = parser.parse_args()

    runner = TradingRunner(
        mode=args.mode,
        day_trades_only=args.day_trades_only,
        swing_only=args.swing_only,
    )

    if args.pdt_status:
        status = await runner.get_pdt_status()
        print("\n" + "=" * 50)
        print("PDT STATUS")
        print("=" * 50)
        print(json.dumps(status, indent=2))
        return

    if args.monitor:
        positions = await runner.monitor_positions()
        print("\n" + "=" * 50)
        print("POSITION MONITOR")
        print("=" * 50)
        print(json.dumps(positions, indent=2, default=str))
        return

    # Run daily cycle
    summary = await runner.run_daily_cycle(args.symbols)

    print("\n" + "=" * 50)
    print("DAILY SUMMARY")
    print("=" * 50)
    print(f"Mode: {summary['mode']}")
    print(f"Market Open: {summary['market_open']}")
    print(f"PDT Status: {summary['pdt_status']['status']}")
    print(f"Day Trades Remaining: {summary['pdt_status']['day_trades_remaining']}")
    print(f"Intraday Signals: {len(summary['intraday_signals'])}")
    print(f"Swing Exits Available: {len(summary['swing_exits'])}")

    if summary['intraday_signals']:
        print("\nIntraday Signals:")
        for sig in summary['intraday_signals']:
            print(f"  {sig['direction']} {sig['symbol']} - {sig['reason'][:50]}...")

    print(f"\nRecommendation: {summary['pdt_status']['recommendation']}")


if __name__ == "__main__":
    asyncio.run(main())
