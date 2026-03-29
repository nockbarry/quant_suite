#!/usr/bin/env python3
"""Cron job: Track decision quality at 1d/5d/10d/30d horizons.

Schedule: 5:22 PM ET Mon-Fri (after opinion scorer, before belief updater)
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("decision-quality")


def main():
    from src.db.database import init_db

    init_db()

    from src.opinions.decision_quality import DecisionQualityTracker

    tracker = DecisionQualityTracker()

    # First backfill any untracked decisions
    backfilled = tracker.backfill_untracked_decisions()
    if backfilled:
        logger.info(f"Backfilled {backfilled} untracked decisions")

    # Then score due decisions
    summary = tracker.score_due_decisions()
    logger.info(
        f"Decision quality scoring: "
        f"1d={summary['scored_1d']}, 5d={summary['scored_5d']}, "
        f"10d={summary['scored_10d']}, 30d={summary['scored_30d']}, "
        f"errors={summary['errors']}"
    )

    # Print quality summary
    quality = tracker.get_quality_summary()
    for horizon in (1, 5, 10, 30):
        h = quality.get(f"{horizon}d", {})
        if h:
            logger.info(
                f"  {horizon}d quality: {h['avg_quality']:.1%} correct, "
                f"avg return {h['avg_return']:+.1f}%, "
                f"alpha vs SPY {h['avg_alpha']:+.1f}% "
                f"(n={h['count']})"
            )

    return 0 if summary.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
