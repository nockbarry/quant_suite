#!/usr/bin/env python3
"""Automated belief update — run 5:30 PM weekdays (after prediction scorer).

Updates signal weights, suggests thesis conviction changes, computes calibration,
and generates a learning summary.

Cron:
    30 17 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_belief_update.py
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_belief_update():
    """Run daily belief update."""
    from src.db.database import init_db
    from src.intelligence.belief_updater import BeliefUpdater

    init_db()

    updater = BeliefUpdater()
    report = updater.run_daily_update()

    # Print summary
    print(report.learning_summary)
    print()

    if report.thesis_suggestions:
        print("=== ACTION ITEMS ===")
        for s in report.thesis_suggestions:
            print(f"  [{s.thesis_name}] Suggest {'increase' if s.suggested_change > 0 else 'decrease'} "
                  f"conviction by {abs(s.suggested_change)}% — {s.reason}")

    return report


if __name__ == "__main__":
    report = run_belief_update()
    logger.info(f"Belief update complete: {len(report.signal_updates)} signal updates, "
                f"{len(report.thesis_suggestions)} thesis suggestions")
