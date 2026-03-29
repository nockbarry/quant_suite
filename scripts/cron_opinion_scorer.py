#!/usr/bin/env python3
"""Cron job: Score market opinions at 5d/10d/30d horizons.

Schedule: 5:20 PM ET Mon-Fri (after prediction scorer, before belief updater)
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("opinion-scorer")


def main():
    from src.db.database import init_db

    init_db()

    from src.opinions.scorer import OpinionScorer

    scorer = OpinionScorer()
    summary = scorer.score_due_opinions()

    logger.info(
        f"Opinion scoring complete: "
        f"5d={summary['scored_5d']}, 10d={summary['scored_10d']}, "
        f"30d={summary['scored_30d']}, errors={summary['errors']}"
    )

    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
