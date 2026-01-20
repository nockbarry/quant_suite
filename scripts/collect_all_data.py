#!/usr/bin/env python3
"""Master Data Collection Script - Collects from ALL data sources.

Run this to activate all 35+ data sources.

Usage:
    PYTHONPATH=. python scripts/collect_all_data.py
    PYTHONPATH=. python scripts/collect_all_data.py --quick  # Essential only
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def collect_expanded_news():
    """Collect from 15+ RSS feeds."""
    try:
        from src.data.sources.alternative.expanded_news import ExpandedNewsCollector
        collector = ExpandedNewsCollector()
        result = await collector.collect_and_save()
        await collector.close()
        return {"expanded_news": result}
    except Exception as e:
        logger.error(f"Expanded news collection failed: {e}")
        return {"expanded_news": {"error": str(e)}}


async def collect_legal():
    """Collect legal/regulatory events."""
    try:
        from src.data.sources.alternative.legal_tracker import LegalTracker
        tracker = LegalTracker()
        result = await tracker.collect_all()
        await tracker.close()
        return {"legal": result}
    except Exception as e:
        logger.error(f"Legal collection failed: {e}")
        return {"legal": {"error": str(e)}}


async def collect_geopolitical():
    """Collect geopolitical events."""
    try:
        from src.data.sources.alternative.geopolitical import GeopoliticalMonitor
        monitor = GeopoliticalMonitor()
        result = await monitor.collect_all()
        await monitor.close()
        return {"geopolitical": result}
    except Exception as e:
        logger.error(f"Geopolitical collection failed: {e}")
        return {"geopolitical": {"error": str(e)}}


async def collect_sector_rotation():
    """Analyze sector rotation."""
    try:
        from src.synthesis.sector_rotation import SectorRotationDetector
        detector = SectorRotationDetector()
        strengths = await detector.analyze_sectors()
        signal = detector.detect_rotation(strengths)
        return {
            "sector_rotation": {
                "sectors_analyzed": len(strengths),
                "rotation_signal": signal.to_dict() if signal else None,
            }
        }
    except Exception as e:
        logger.error(f"Sector rotation failed: {e}")
        return {"sector_rotation": {"error": str(e)}}


async def collect_from_daemon():
    """Run the data collection daemon for all sources."""
    try:
        from src.data.sources.collection_daemon import DataCollectionDaemon
        daemon = DataCollectionDaemon()
        await daemon.collect_all_now()
        status = await daemon.get_collection_status()
        return {"daemon": status}
    except Exception as e:
        logger.error(f"Daemon collection failed: {e}")
        return {"daemon": {"error": str(e)}}


async def update_unified_state():
    """Update the unified state file."""
    try:
        from src.synthesis.daemon import LiveDaemon
        daemon = LiveDaemon()
        state = await daemon.update_now()
        return {"unified_state": "updated", "timestamp": state.timestamp.isoformat()}
    except Exception as e:
        logger.error(f"State update failed: {e}")
        return {"unified_state": {"error": str(e)}}


async def run_signpost_check():
    """Check signposts for triggered alerts."""
    try:
        from scripts.signpost_monitor import load_signposts, check_signposts, save_alerts
        signposts = load_signposts()
        triggered = check_signposts(signposts, alerts_only=True)
        if triggered:
            save_alerts(triggered)
        return {"signposts": {"checked": len(signposts), "triggered": len(triggered)}}
    except Exception as e:
        logger.error(f"Signpost check failed: {e}")
        return {"signposts": {"error": str(e)}}


async def collect_all(quick: bool = False):
    """Collect from all data sources."""
    logger.info("=" * 60)
    logger.info(f"Master Data Collection - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    results = {}
    start_time = datetime.now()

    # Essential collections (always run)
    essential_tasks = [
        ("expanded_news", collect_expanded_news()),
        ("unified_state", update_unified_state()),
        ("signposts", run_signpost_check()),
    ]

    # Extended collections (skip if --quick)
    extended_tasks = [
        ("legal", collect_legal()),
        ("geopolitical", collect_geopolitical()),
        ("sector_rotation", collect_sector_rotation()),
        ("daemon", collect_from_daemon()),
    ]

    tasks_to_run = essential_tasks if quick else essential_tasks + extended_tasks

    # Run all tasks concurrently
    logger.info(f"Running {len(tasks_to_run)} collection tasks...")

    for name, coro in tasks_to_run:
        try:
            logger.info(f"  Starting: {name}")
            result = await coro
            results.update(result)
            logger.info(f"  Completed: {name}")
        except Exception as e:
            logger.error(f"  Failed: {name} - {e}")
            results[name] = {"error": str(e)}

    # Calculate duration
    duration = (datetime.now() - start_time).total_seconds()

    # Summary
    logger.info("=" * 60)
    logger.info(f"Collection completed in {duration:.1f} seconds")
    logger.info("=" * 60)

    # Count successes and failures
    successes = sum(1 for v in results.values() if "error" not in v)
    failures = len(results) - successes

    logger.info(f"Results: {successes} succeeded, {failures} failed")

    # Save collection log
    log_dir = Path.home() / "quant_results" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "collection_log.json"
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration,
        "quick_mode": quick,
        "results": results,
    }

    # Append to log
    existing_log = []
    if log_file.exists():
        with open(log_file) as f:
            existing_log = json.load(f)

    existing_log.append(log_entry)
    existing_log = existing_log[-100:]  # Keep last 100

    with open(log_file, "w") as f:
        json.dump(existing_log, f, indent=2, default=str)

    return results


def main():
    parser = argparse.ArgumentParser(description="Master data collection")
    parser.add_argument("--quick", action="store_true", help="Run essential collections only")
    args = parser.parse_args()

    results = asyncio.run(collect_all(quick=args.quick))

    # Print summary
    print("\nCollection Summary:")
    print("-" * 40)
    for source, result in results.items():
        status = "✓" if "error" not in result else "✗"
        print(f"  {status} {source}")

    # Print any errors
    errors = {k: v["error"] for k, v in results.items() if "error" in v}
    if errors:
        print("\nErrors:")
        for source, error in errors.items():
            print(f"  {source}: {error}")


if __name__ == "__main__":
    main()
