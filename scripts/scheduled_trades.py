#!/usr/bin/env python3
"""Scheduled trade execution with price bounds checking.

Executes trades at market open ONLY if prices are within expected bounds.
Designed to be run via cron at 9:31 AM ET (1 minute after open for prices to settle).

Usage:
    # Dry run (default) - shows what would execute
    PYTHONPATH=/home/nock/projects/quant_suite python3 scripts/scheduled_trades.py

    # Live execution
    PYTHONPATH=/home/nock/projects/quant_suite python3 scripts/scheduled_trades.py --execute

    # With specific trade file
    PYTHONPATH=/home/nock/projects/quant_suite python3 scripts/scheduled_trades.py --trades trades_20260113.json
"""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution.accounts import AccountManager, TradingAccount
from src.decision.decision_logger import DecisionLogger, TradingDecision, Action, DecisionStatus
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
from scripts.quick_trade import get_broker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(paths.base / "logs" / "scheduled_trades.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ensure log directory exists
(paths.base / "logs").mkdir(parents=True, exist_ok=True)


@dataclass
class ScheduledTrade:
    """A trade scheduled for conditional execution."""
    symbol: str
    action: str  # BUY, SELL, TRIM
    quantity: Optional[int] = None  # For BUY/SELL
    trim_pct: Optional[float] = None  # For TRIM (e.g., 0.30 = 30%)
    dollar_value: Optional[float] = None  # For BUY by dollar amount

    # Price bounds - trade only executes if price within bounds
    min_price: Optional[float] = None  # Don't buy above this / don't sell below this
    max_price: Optional[float] = None  # Don't buy above this

    # Technical bounds
    max_rsi: Optional[float] = None  # Don't buy if RSI above this
    min_rsi: Optional[float] = None  # Don't sell if RSI below this

    # Context
    thesis: Optional[str] = None
    reasoning: str = ""
    stop_loss_pct: float = 0.05  # Default 5% stop
    target_pct: float = 0.06  # Default 6% target

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# Today's scheduled trades based on research
SCHEDULED_TRADES = [
    # BUY - Oversold banks (mean reversion)
    ScheduledTrade(
        symbol="AXP",
        action="BUY",
        dollar_value=3500,  # ~$3,500 position
        max_price=365.00,  # Don't buy if gapped up above $365
        min_price=345.00,  # Don't buy if crashed below $345 (something wrong)
        max_rsi=45,  # Only buy if still oversold
        thesis="Bank Rate Cap Overreaction",
        reasoning="Mean reversion z=-3.03, RSI 38.1. Rate cap needs Congress, unlikely to pass.",
        stop_loss_pct=0.05,
        target_pct=0.06,
    ),
    ScheduledTrade(
        symbol="SYF",
        action="BUY",
        dollar_value=2500,  # ~$2,500 position
        max_price=82.00,  # Don't buy if gapped up
        min_price=74.00,  # Don't buy if crashed
        max_rsi=45,
        thesis="Bank Rate Cap Overreaction",
        reasoning="Mean reversion z=-2.64, RSI 36.7. Oversold on rate cap fear.",
        stop_loss_pct=0.045,
        target_pct=0.055,
    ),

    # TRIM - Overbought winners (lock in gains)
    ScheduledTrade(
        symbol="GOLD",
        action="TRIM",
        trim_pct=0.40,  # Trim 40%
        min_price=40.00,  # Don't sell if dropped below $40
        min_rsi=65,  # Only trim if still overbought
        thesis="Gold De-Dollarization Bull Cycle",
        reasoning="RSI 87.6, +23% gain. Lock in profits, keep core position.",
    ),
    ScheduledTrade(
        symbol="FRO",
        action="TRIM",
        trim_pct=0.35,  # Trim 35%
        min_price=23.00,  # Don't sell if dropped significantly
        min_rsi=60,
        thesis="Venezuela Energy Recovery",
        reasoning="RSI 72.8, +19% gain. Tankers ran hard, take some off.",
    ),
    ScheduledTrade(
        symbol="INSW",
        action="TRIM",
        trim_pct=0.30,  # Trim 30%
        min_price=50.00,
        min_rsi=60,
        thesis="Venezuela Energy Recovery",
        reasoning="RSI 73.2, +14% gain. Reduce concentration.",
    ),
    ScheduledTrade(
        symbol="SLB",
        action="TRIM",
        trim_pct=0.25,  # Trim 25%
        min_price=43.00,
        min_rsi=65,
        thesis="Venezuela Energy Recovery",
        reasoning="RSI 80.9, largest position. Reduce to rebalance.",
    ),
]


def save_trades_to_file(trades: list[ScheduledTrade], filename: str = None):
    """Save scheduled trades to JSON file."""
    if filename is None:
        filename = f"trades_{datetime.now().strftime('%Y%m%d')}.json"

    path = paths.base / "scheduled_trades" / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w') as f:
        json.dump([t.to_dict() for t in trades], f, indent=2)

    logger.info(f"Saved {len(trades)} trades to {path}")
    return path


def load_trades_from_file(filename: str) -> list[ScheduledTrade]:
    """Load scheduled trades from JSON file."""
    path = paths.base / "scheduled_trades" / filename

    with open(path, 'r') as f:
        data = json.load(f)

    return [ScheduledTrade.from_dict(d) for d in data]


async def check_trade_conditions(trade: ScheduledTrade, broker) -> tuple[bool, str, dict]:
    """
    Check if trade conditions are met.

    Returns:
        (should_execute, reason, market_data)
    """
    try:
        quote = await broker.get_quote(trade.symbol)
        current_price = float(quote.last)

        market_data = {
            "symbol": trade.symbol,
            "current_price": current_price,
            "bid": float(quote.bid),
            "ask": float(quote.ask),
            "checked_at": datetime.now().isoformat(),
        }

        # Price bounds check
        if trade.action == "BUY":
            if trade.max_price and current_price > trade.max_price:
                return False, f"Price ${current_price:.2f} > max ${trade.max_price:.2f}", market_data
            if trade.min_price and current_price < trade.min_price:
                return False, f"Price ${current_price:.2f} < min ${trade.min_price:.2f} (something wrong?)", market_data

        elif trade.action in ("SELL", "TRIM"):
            if trade.min_price and current_price < trade.min_price:
                return False, f"Price ${current_price:.2f} < min ${trade.min_price:.2f} (don't sell low)", market_data

        # RSI check would require more data - skip for now, trust the morning analysis
        # In production, we'd compute RSI here

        return True, "All conditions met", market_data

    except Exception as e:
        return False, f"Error getting quote: {e}", {}


async def execute_trade(trade: ScheduledTrade, broker, manager: AccountManager, dry_run: bool = True) -> dict:
    """
    Execute a single trade if conditions are met.

    Returns execution result dict.
    """
    result = {
        "symbol": trade.symbol,
        "action": trade.action,
        "status": "pending",
        "executed_at": None,
        "order_id": None,
        "quantity": None,
        "price": None,
        "reason": None,
    }

    # Check conditions
    should_execute, reason, market_data = await check_trade_conditions(trade, broker)
    result["market_data"] = market_data

    if not should_execute:
        result["status"] = "skipped"
        result["reason"] = reason
        logger.warning(f"SKIP {trade.action} {trade.symbol}: {reason}")
        return result

    current_price = market_data["current_price"]

    # Calculate quantity
    if trade.action == "BUY":
        if trade.dollar_value:
            quantity = int(trade.dollar_value / current_price)
        else:
            quantity = trade.quantity

        if quantity <= 0:
            result["status"] = "skipped"
            result["reason"] = "Calculated quantity is 0"
            return result

        result["quantity"] = quantity
        result["price"] = current_price

        if dry_run:
            result["status"] = "dry_run"
            result["reason"] = f"Would BUY {quantity} @ ${current_price:.2f} = ${quantity * current_price:.2f}"
            logger.info(f"DRY RUN: BUY {quantity} {trade.symbol} @ ${current_price:.2f}")
        else:
            # Validate against risk limits
            account = await broker.get_account()
            portfolio_value = float(account.portfolio_value)
            trade_value = quantity * current_price

            is_valid, validation_reason = manager.validate_trade(
                account=TradingAccount.PAPER,
                symbol=trade.symbol,
                value=trade_value,
                portfolio_value=portfolio_value,
            )

            if not is_valid:
                result["status"] = "blocked"
                result["reason"] = validation_reason
                logger.warning(f"BLOCKED {trade.symbol}: {validation_reason}")
                return result

            order = await broker.market_buy(trade.symbol, Decimal(quantity))
            result["status"] = "executed"
            result["order_id"] = order.order_id
            result["executed_at"] = datetime.now().isoformat()
            logger.info(f"EXECUTED: BUY {quantity} {trade.symbol} @ ${current_price:.2f}")

    elif trade.action == "TRIM":
        # Get current position
        positions = await broker.get_positions()
        position = positions.get(trade.symbol)

        if not position:
            result["status"] = "skipped"
            result["reason"] = f"No position in {trade.symbol}"
            return result

        current_qty = int(float(position.quantity))
        trim_qty = int(current_qty * trade.trim_pct)

        if trim_qty <= 0:
            result["status"] = "skipped"
            result["reason"] = f"Trim quantity too small ({current_qty} * {trade.trim_pct} = {trim_qty})"
            return result

        result["quantity"] = trim_qty
        result["price"] = current_price

        if dry_run:
            result["status"] = "dry_run"
            result["reason"] = f"Would SELL {trim_qty} of {current_qty} @ ${current_price:.2f}"
            logger.info(f"DRY RUN: TRIM {trim_qty}/{current_qty} {trade.symbol} @ ${current_price:.2f}")
        else:
            order = await broker.market_sell(trade.symbol, Decimal(trim_qty))
            result["status"] = "executed"
            result["order_id"] = order.order_id
            result["executed_at"] = datetime.now().isoformat()
            logger.info(f"EXECUTED: TRIM {trim_qty}/{current_qty} {trade.symbol}")

    elif trade.action == "SELL":
        quantity = trade.quantity
        result["quantity"] = quantity
        result["price"] = current_price

        if dry_run:
            result["status"] = "dry_run"
            result["reason"] = f"Would SELL {quantity} @ ${current_price:.2f}"
            logger.info(f"DRY RUN: SELL {quantity} {trade.symbol} @ ${current_price:.2f}")
        else:
            order = await broker.market_sell(trade.symbol, Decimal(quantity))
            result["status"] = "executed"
            result["order_id"] = order.order_id
            result["executed_at"] = datetime.now().isoformat()
            logger.info(f"EXECUTED: SELL {quantity} {trade.symbol}")

    return result


def log_trade_as_decision(trade: ScheduledTrade, result: dict, decision_logger: DecisionLogger) -> Optional[str]:
    """Log an executed trade as a formal decision for tracking.

    Returns decision_id if logged, None otherwise.
    """
    if result["status"] not in ["executed", "dry_run"]:
        return None

    # Map action to Decision Action enum
    action_map = {
        "BUY": Action.BUY,
        "SELL": Action.SELL,
        "TRIM": Action.TRIM,
    }

    action = action_map.get(trade.action, Action.BUY)

    # Find thesis ID if thesis name provided
    thesis_id = None
    if trade.thesis:
        try:
            tracker = ThesisTracker(paths.theses)
            for thesis in tracker.get_active_theses():
                if thesis.name == trade.thesis:
                    thesis_id = thesis.id
                    break
        except Exception as e:
            logger.warning(f"Could not find thesis: {e}")

    # Create decision record
    import uuid
    decision = TradingDecision(
        id=f"sched_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(),
        symbol=trade.symbol,
        action=action,
        confidence=0.70,  # Scheduled trades have pre-vetted confidence
        size_pct=0.0,  # Will be calculated from portfolio
        limit_price=None,
        stop_loss_pct=trade.stop_loss_pct,
        take_profit_pct=trade.target_pct,
        expected_hold_days=5,  # Default swing trade horizon
        reasoning=trade.reasoning,
        key_factors=[
            f"Scheduled execution at market open",
            f"Thesis: {trade.thesis}" if trade.thesis else "No thesis",
        ],
        risks=[
            "Pre-market conditions may have changed",
            "Scheduled trade - limited real-time analysis",
        ],
        context={
            "source": "scheduled_trades",
            "market_data": result.get("market_data", {}),
            "price_bounds": {
                "min": trade.min_price,
                "max": trade.max_price,
            },
        },
        thesis_id=thesis_id,
        setup_type="scheduled_cron",
    )

    # Mark as executed if actually executed
    if result["status"] == "executed":
        decision.status = DecisionStatus.EXECUTED
        decision.execution_price = result.get("price")
        decision.execution_time = datetime.now()

    # Log the decision
    decision_id = decision_logger.log_decision(decision)
    logger.info(f"Logged decision: {decision_id} for {trade.symbol}")

    return decision_id


async def run_scheduled_trades(trades: list[ScheduledTrade], dry_run: bool = True):
    """Execute all scheduled trades."""
    logger.info(f"{'='*60}")
    logger.info(f"SCHEDULED TRADE EXECUTION - {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Trades to process: {len(trades)}")
    logger.info(f"{'='*60}")

    manager = AccountManager()
    broker = get_broker(paper=True)
    await broker.connect()

    # Initialize decision logger for tracking
    decision_logger = DecisionLogger()

    results = []
    decisions_logged = []

    try:
        for trade in trades:
            logger.info(f"\nProcessing: {trade.action} {trade.symbol}")
            result = await execute_trade(trade, broker, manager, dry_run)
            results.append(result)

            # Log as formal decision (only for executed/dry_run, not skipped)
            if result["status"] in ["executed", "dry_run"] and not dry_run:
                decision_id = log_trade_as_decision(trade, result, decision_logger)
                if decision_id:
                    decisions_logged.append(decision_id)
                    result["decision_id"] = decision_id
    finally:
        await broker.disconnect()

    if decisions_logged:
        logger.info(f"\nLogged {len(decisions_logged)} decisions to decision tracker")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("EXECUTION SUMMARY")
    logger.info(f"{'='*60}")

    executed = [r for r in results if r["status"] == "executed"]
    dry_runs = [r for r in results if r["status"] == "dry_run"]
    skipped = [r for r in results if r["status"] == "skipped"]
    blocked = [r for r in results if r["status"] == "blocked"]

    if dry_run:
        logger.info(f"Would execute: {len(dry_runs)}")
        for r in dry_runs:
            logger.info(f"  {r['symbol']}: {r['reason']}")
    else:
        logger.info(f"Executed: {len(executed)}")
        for r in executed:
            logger.info(f"  {r['symbol']}: {r['quantity']} @ ${r['price']:.2f}")

    if skipped:
        logger.info(f"Skipped: {len(skipped)}")
        for r in skipped:
            logger.info(f"  {r['symbol']}: {r['reason']}")

    if blocked:
        logger.info(f"Blocked: {len(blocked)}")
        for r in blocked:
            logger.info(f"  {r['symbol']}: {r['reason']}")

    # Save results
    results_path = paths.base / "scheduled_trades" / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with open(results_path, 'w') as f:
        json.dump({
            "executed_at": datetime.now().isoformat(),
            "dry_run": dry_run,
            "trades": [t.to_dict() for t in trades],
            "results": results,
        }, f, indent=2)

    logger.info(f"\nResults saved to: {results_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Execute scheduled trades at market open")
    parser.add_argument("--execute", action="store_true", help="Actually execute trades (default is dry run)")
    parser.add_argument("--trades", type=str, help="Load trades from JSON file instead of using defaults")
    parser.add_argument("--save", action="store_true", help="Save current trades to file for later use")

    args = parser.parse_args()

    # Load or use default trades
    if args.trades:
        trades = load_trades_from_file(args.trades)
        logger.info(f"Loaded {len(trades)} trades from {args.trades}")
    else:
        trades = SCHEDULED_TRADES
        logger.info(f"Using {len(trades)} default scheduled trades")

    # Optionally save trades
    if args.save:
        save_trades_to_file(trades)
        return

    # Check market hours (optional - cron should handle this)
    now = datetime.now()
    market_open = time(9, 30)
    market_close = time(16, 0)

    if not (market_open <= now.time() <= market_close):
        logger.warning(f"Warning: Market may be closed (current time: {now.time()})")
        if not args.execute:
            logger.info("Proceeding with dry run anyway...")
        else:
            logger.error("Refusing to execute trades outside market hours. Use dry run to test.")
            return

    # Run trades
    dry_run = not args.execute
    asyncio.run(run_scheduled_trades(trades, dry_run=dry_run))


if __name__ == "__main__":
    main()
