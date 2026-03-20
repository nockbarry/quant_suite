#!/usr/bin/env python3
"""Cron wrapper for the Cross-Reference Engine.

Loads all data sources, runs all cross-reference checks, saves alerts,
and pushes actionable alerts to the situation board.

Designed to run every 30 minutes. No network calls — reads only from disk.

Usage:
    PYTHONPATH=. python3 scripts/run_cross_reference.py
"""

import logging
import sys
import time
from datetime import datetime

# Configure logging for cron
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_cross_reference")


def main():
    start = time.time()
    logger.info("Cross-Reference Engine starting...")

    try:
        from src.intelligence.cross_reference import CrossReferenceEngine
    except ImportError as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)

    engine = CrossReferenceEngine()
    alerts = engine.run()

    elapsed = time.time() - start

    # Summary
    red_flags = [a for a in alerts if a.severity == "red_flag"]
    warnings = [a for a in alerts if a.severity == "warning"]
    infos = [a for a in alerts if a.severity == "info"]

    print(f"\n{'='*60}")
    print(f"Cross-Reference Scan Complete — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  Alerts: {len(alerts)} total ({len(red_flags)} red flags, {len(warnings)} warnings, {len(infos)} info)")
    print(f"  Elapsed: {elapsed:.1f}s")

    if red_flags:
        print(f"\n  RED FLAGS:")
        for a in red_flags:
            print(f"    [{a.alert_type}] {a.title}")
            print(f"      -> {a.recommended_action}")

    if warnings:
        print(f"\n  WARNINGS:")
        for a in warnings:
            print(f"    [{a.alert_type}] {a.title}")

    if not alerts:
        print("  No new alerts detected.")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
