#!/usr/bin/env python3
"""Cron job: rebuild realized P&L from broker fill history (nightly 5:40 PM).

Fix #1 from the 2026-06-09 fresh evaluation: only 1 of 492 executed decisions
had a realized_pnl — the learning stack was running without measured outcomes.
This job FIFO-matches the full Alpaca fill history into realized lots and
stamps P&L back onto the matching executed decisions. Fully idempotent
(derived table is wiped and rebuilt each run).

Usage:
    PYTHONPATH=. python3 scripts/cron_realized_pnl.py          # current instance
    ATHENA_INSTANCE=beta QUANT_RESULTS_DIR=~/quant_results_beta \
        PYTHONPATH=. python3 scripts/cron_realized_pnl.py
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("realized-pnl")


async def main_async() -> int:
    from scripts.quick_trade import get_broker
    from src.core.events import emit
    from src.core.instance import InstanceConfig
    from src.db.database import init_db
    from src.analytics.realized_pnl import (
        fetch_filled_orders, fifo_realize, rebuild_lots,
        summarize, writeback_decisions,
    )

    instance = InstanceConfig.instance_name()
    init_db()

    broker = get_broker(paper=True)
    await broker.connect()
    try:
        fills = fetch_filled_orders(broker._trading_client)
    finally:
        try:
            await broker.disconnect()
        except Exception:
            pass

    if not fills:
        logger.info("No fills found — nothing to do")
        return 0

    lots = fifo_realize(fills)
    n_lots = rebuild_lots(lots, instance_id=instance)
    n_dec = writeback_decisions(lots)
    stats = summarize(lots)

    logger.info(f"[{instance}] {len(fills)} fills -> {n_lots} realized lots; "
                f"{n_dec} decisions stamped with P&L")
    logger.info(f"  total realized: ${stats.get('total_realized_pnl', 0):,.0f}  "
                f"win rate: {stats.get('win_rate', 0):.0%}  "
                f"avg: {stats.get('avg_pnl_pct', 0):+.2f}%  "
                f"avg hold: {stats.get('avg_hold_days', 0):.1f}d")
    logger.info(f"  short-hold (<=10d) P&L: ${stats.get('short_hold_pnl', 0):,.0f}  "
                f"long-hold (>10d) P&L: ${stats.get('long_hold_pnl', 0):,.0f}")

    emit(
        "realized_pnl_rebuilt",
        source="cron_realized_pnl",
        severity="info",
        title=f"{instance}: {n_lots} lots, ${stats.get('total_realized_pnl', 0):,.0f} realized, "
              f"{stats.get('win_rate', 0):.0%} win rate",
        detail={"instance": instance, "decisions_stamped": n_dec, **stats},
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
