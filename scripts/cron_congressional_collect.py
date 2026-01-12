#!/usr/bin/env python3
"""Daily Congressional Trades Collector.

Designed to run as a daily cron job to archive congressional trades.

Cron setup (run daily at 6 AM):
    0 6 * * * cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_congressional_collect.py >> /home/nock/quant_results/logs/congressional_collect.log 2>&1

Usage:
    PYTHONPATH=. python scripts/cron_congressional_collect.py
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def collect_daily():
    """Collect new congressional trades and archive them."""
    from src.data.sources.alternative.congressional_archive import CongressionalArchiver

    logger.info("=" * 60)
    logger.info(f"Congressional Trades Collection - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    archiver = CongressionalArchiver()

    try:
        # Collect from live RSS feeds
        result = await archiver.collect_daily()

        if result.get("status") == "success":
            logger.info(f"Collected {result['trades_collected']} trades")
            logger.info(f"Saved to: {result['path']}")
        elif result.get("status") == "no_trades":
            logger.info("No new trades found")
        else:
            logger.warning(f"Collection result: {result}")

        # Print current archive summary
        summary = archiver.get_summary()
        if summary.get("status") != "empty":
            logger.info(f"Total archived trades: {summary['total_trades']:,}")

        # Save collection log
        log_dir = paths.base / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "congressional_collection_history.json"
        history = []
        if log_file.exists():
            with open(log_file) as f:
                history = json.load(f)

        history.append({
            "timestamp": datetime.now().isoformat(),
            "result": result,
        })

        # Keep last 90 days of history
        history = history[-90:]

        with open(log_file, "w") as f:
            json.dump(history, f, indent=2)

        return result

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        return {"status": "error", "error": str(e)}

    finally:
        await archiver.close()


def main():
    result = asyncio.run(collect_daily())
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
