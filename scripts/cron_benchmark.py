#!/usr/bin/env python3
"""Cron job: weekly benchmark report — account vs SPY, QQQ, frozen own-basket.

Fix #2 from the 2026-06-09 fresh evaluation. Runs Sunday 4:00 PM (before
/system-review at 4:30, which reads ~/quant_results/benchmarks/benchmark_latest.json).

Usage:
    PYTHONPATH=. python3 scripts/cron_benchmark.py
"""

import asyncio
import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("benchmark")


async def main_async() -> int:
    from scripts.quick_trade import get_broker
    from src.core.events import emit
    from src.core.instance import InstanceConfig
    from src.analytics.benchmark import compute_report
    from src.knowledge.thesis import ThesisTracker

    instance = InstanceConfig.instance_name()

    broker = get_broker(paper=True)
    await broker.connect()
    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        hist = broker._trading_client.get_portfolio_history(
            GetPortfolioHistoryRequest(period="6M", timeframe="1D"))
        equity = {
            datetime.date.fromtimestamp(t).strftime("%Y-%m-%d"): float(e)
            for t, e in zip(hist.timestamp, hist.equity) if e
        }
    finally:
        try:
            await broker.disconnect()
        except Exception:
            pass

    symbols = sorted({
        s for t in ThesisTracker().get_active_theses() for s in (t.positions or [])
    })
    if not symbols:
        logger.warning("No active thesis vehicles — skipping benchmark")
        return 0

    report = compute_report(symbols, equity, account_label=instance)

    logger.info(f"[{instance}] Benchmark report (frozen {report['frozen_at']}):")
    for window, row in report["windows"].items():
        cells = "  ".join(f"{k}={v:+.2f}%" if v is not None else f"{k}=n/a"
                          for k, v in row.items())
        logger.info(f"  {window:14} {cells}")

    sf = report["windows"].get("since_frozen", {})
    emit(
        "benchmark_report",
        source="cron_benchmark",
        severity="info",
        title=f"{instance} vs frozen basket since {report['frozen_at']}: "
              f"acct {sf.get('account')}% vs basket {sf.get('frozen_basket')}%",
        detail=report["windows"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
