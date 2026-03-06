#!/usr/bin/env python3
"""Auto-execute PENDING trading decisions on paper account.

Runs after trade-decision sessions to close the decision-to-execution gap.
Only operates on paper account. Validates risk limits before each order.

Usage:
    PYTHONPATH=. python3 scripts/cron_auto_execute.py [--dry-run]
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [auto-execute] %(message)s")
logger = logging.getLogger(__name__)


async def auto_execute(dry_run: bool = False):
    """Find PENDING decisions and execute them on paper account."""
    from src.db.database import get_db, init_db
    from src.db.models import DecisionRecord

    init_db()

    # Find PENDING decisions from last 4 hours (don't execute stale ones)
    cutoff = datetime.now() - timedelta(hours=4)

    with get_db() as session:
        pending = (
            session.query(DecisionRecord)
            .filter(
                DecisionRecord.status == "pending",
                DecisionRecord.timestamp >= cutoff,
                DecisionRecord.action.in_(["BUY", "SELL", "ADD", "TRIM", "CLOSE"]),
            )
            .order_by(DecisionRecord.timestamp)
            .all()
        )

        if not pending:
            logger.info("No pending decisions to execute")
            return

        logger.info(f"Found {len(pending)} pending decision(s)")

        # Get broker and account info
        from scripts.quick_trade import get_broker

        broker = get_broker(paper=True)
        await broker.connect()

        try:
            account = await broker.get_account()
            equity = float(account.portfolio_value)
            logger.info(f"Paper account equity: ${equity:,.2f}")

            if equity < 1000:
                logger.warning(f"Equity too low (${equity:,.2f}), skipping execution")
                return

            executed = 0
            for decision in pending:
                try:
                    ok = await _execute_one(broker, session, decision, equity, dry_run)
                    if ok:
                        executed += 1
                except Exception as e:
                    logger.error(f"Failed to execute {decision.symbol} {decision.action}: {e}")
                    continue

            logger.info(f"Executed {executed}/{len(pending)} decisions" + (" (DRY RUN)" if dry_run else ""))

        finally:
            await broker.disconnect()

    # Log to ProcessEvent
    try:
        from src.autonomy.provenance import log_event

        log_event(
            "auto_execute_complete",
            source="cron:auto_execute",
            title=f"Auto-executed {executed}/{len(pending)} paper decisions",
        )
    except Exception:
        pass


async def _execute_one(
    broker, db_session, decision: "DecisionRecord", equity: float, dry_run: bool
) -> bool:
    """Execute a single decision. Returns True if successful."""
    symbol = decision.symbol
    action = decision.action
    size_pct = decision.size_pct or 5.0

    # Calculate quantity from size_pct
    target_value = equity * (size_pct / 100.0)

    # Get current price
    try:
        quote = await broker.get_quote(symbol)
        price = float(quote.last)
    except Exception as e:
        logger.warning(f"Cannot get quote for {symbol}: {e}")
        return False

    if price <= 0:
        logger.warning(f"Invalid price for {symbol}: {price}")
        return False

    qty = int(target_value / price)
    if qty < 1:
        qty = 1

    # Validate position size won't exceed 10%
    position_value = qty * price
    if position_value / equity > 0.10:
        qty = int(equity * 0.10 / price)
        if qty < 1:
            logger.warning(f"Position size for {symbol} would exceed 10% limit, skipping")
            return False

    logger.info(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"{action} {qty} {symbol} @ ${price:.2f} = ${qty * price:,.2f} "
        f"({size_pct:.1f}% of ${equity:,.0f})"
    )

    if dry_run:
        return True

    # Execute
    try:
        if action in ("BUY", "ADD"):
            order = await broker.market_buy(symbol, Decimal(qty))
        elif action in ("SELL", "TRIM", "CLOSE"):
            order = await broker.market_sell(symbol, Decimal(qty))
        else:
            logger.warning(f"Unknown action {action} for {symbol}")
            return False

        # Update decision status
        decision.status = "executed"
        decision.execution_price = price
        decision.execution_time = datetime.now()
        db_session.commit()

        logger.info(f"Order submitted: {order.order_id} status={order.status}")
        return True

    except Exception as e:
        logger.error(f"Order failed for {symbol}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Auto-execute pending paper decisions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would execute without submitting orders")
    args = parser.parse_args()

    asyncio.run(auto_execute(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
