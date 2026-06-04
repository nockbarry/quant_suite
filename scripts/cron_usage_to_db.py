#!/usr/bin/env python3
"""Cron job: persist Claude Code token usage to the session_costs table.

Schedule: 5:25 PM ET Mon-Fri (after sessions have run for the day).

Closes the cost-observability gap flagged in the system evaluation
(memory/project_system_eval_20260530.md): usage_monitor already computes
exact token counts from Claude Code transcripts, but nothing persisted them
to the DB, so the system could not report what it costs to run. This writer
upserts real per-(date, model) usage + equivalent API cost.

Usage:
    PYTHONPATH=. python3 scripts/cron_usage_to_db.py [--days N]
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("usage-to-db")


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist token usage to session_costs")
    parser.add_argument(
        "--days", type=int, default=7,
        help="How many recent days to sync (default 7; idempotent upsert).",
    )
    args = parser.parse_args()

    from src.db.database import init_db
    from src.monitoring.usage_monitor import persist_daily_costs

    init_db()
    written = persist_daily_costs(days=args.days)
    logger.info(f"Done — {written} (date, model) cost rows upserted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
