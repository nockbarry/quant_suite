#!/usr/bin/env python3
"""Daily News and Events Collector.

Designed to run as a daily cron job to archive news and track events.

Cron setup (run every 4 hours):
    0 */4 * * * cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_news_collect.py >> /home/nock/quant_results/logs/news_collect.log 2>&1

Usage:
    PYTHONPATH=. python scripts/cron_news_collect.py
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


async def collect_all():
    """Collect news and events."""
    from src.data.sources.alternative.news_archive import NewsArchiver

    logger.info("=" * 60)
    logger.info(f"News Collection - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    archiver = NewsArchiver()
    results = {}

    try:
        # Collect RSS news
        result = await archiver.collect_daily()
        results["news"] = result
        logger.info(f"News: {result.get('new_items', 0)} new items")

        # Print summary
        summary = archiver.get_summary()
        logger.info(f"Archive: {summary['total_news_items']} total news items")

        # Save collection log
        log_dir = paths.base / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "news_collection_history.json"
        history = []
        if log_file.exists():
            with open(log_file) as f:
                history = json.load(f)

        history.append({
            "timestamp": datetime.now().isoformat(),
            "results": results,
        })

        # Keep last 90 days
        history = history[-2160:]  # 90 days * 24 hours / 4 hour intervals

        with open(log_file, "w") as f:
            json.dump(history, f, indent=2)

        return results

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        return {"status": "error", "error": str(e)}

    finally:
        await archiver.close()


def main():
    result = asyncio.run(collect_all())
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
