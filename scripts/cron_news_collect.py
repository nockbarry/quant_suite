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


async def update_news_cache(news_items: list[dict]) -> None:
    """Update the news cache file used by signpost checker."""
    cache_path = paths.live / "news_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing cache
    existing_items = []
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                data = json.load(f)
                existing_items = data.get("items", [])
        except Exception:
            pass

    # Add new items and deduplicate
    all_items = news_items + existing_items
    seen_titles = set()
    deduped = []
    for item in all_items:
        title = item.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            deduped.append(item)

    # Keep only last 200 items
    deduped = deduped[:200]

    # Save
    with open(cache_path, "w") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "items": deduped,
        }, f, indent=2)

    logger.info(f"Updated news cache with {len(news_items)} new items ({len(deduped)} total)")


async def trigger_signpost_check(new_item_count: int) -> dict:
    """Trigger signpost check if significant news was collected."""
    if new_item_count < 3:
        return {"triggered": False, "reason": "Not enough new items"}

    try:
        # Import and run signpost checker
        from scripts.cron_thesis_signpost_check import SignpostChecker

        checker = SignpostChecker()
        alerts = await checker.check_all_signposts()

        if alerts:
            checker.save_alerts(alerts)
            logger.info(f"Signpost check triggered: {len(alerts)} potential triggers found")
            return {
                "triggered": True,
                "alerts_count": len(alerts),
                "alerts": [
                    {"thesis": a.thesis_name, "signpost": a.signpost_description}
                    for a in alerts[:5]
                ],
            }
        else:
            return {"triggered": True, "alerts_count": 0}

    except Exception as e:
        logger.warning(f"Signpost check failed: {e}")
        return {"triggered": False, "error": str(e)}


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
        new_items = result.get('new_items', 0)
        logger.info(f"News: {new_items} new items")

        # Update news cache for signpost checker
        if new_items > 0:
            # Get recent items to add to cache
            news_items = []
            archive_dir = paths.base / "news_archive" / "news"
            if archive_dir.exists():
                for news_file in sorted(archive_dir.glob("*.json"), reverse=True)[:3]:
                    try:
                        with open(news_file) as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                news_items.extend(data[:50])
                            elif isinstance(data, dict) and "items" in data:
                                news_items.extend(data["items"][:50])
                    except Exception:
                        pass

            if news_items:
                await update_news_cache(news_items)

        # Trigger signpost check if significant news
        signpost_result = await trigger_signpost_check(new_items)
        results["signpost_check"] = signpost_result

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
