#!/usr/bin/env python3
"""Thesis Maintenance Cron Job.

Runs daily at 6:10 AM ET to:
1. Generate thesis suggestions from converging signals
2. Auto-create theses from high-confidence suggestions (>=0.75, max 2/week)
3. Surface overdue thesis reviews to the situation board
4. Reset any thesis anchored at 100% conviction back to 95%

Usage:
    PYTHONPATH=. python scripts/cron_thesis_maintenance.py
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import paths
from src.knowledge.thesis import ThesisTracker
from src.knowledge.thesis_suggester import ThesisSuggester

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [thesis-maint] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

LOG_FILE = paths.base / "logs" / "thesis_maintenance.jsonl"


def log_event(event_type: str, detail: dict):
    """Append a structured log entry."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(), "type": event_type, **detail}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_suggestion_pipeline() -> dict:
    """Generate and auto-create thesis suggestions."""
    suggester = ThesisSuggester()

    # Step 1: scan for new convergences
    new_suggestions = suggester.generate_suggestions()
    logger.info(f"Generated {len(new_suggestions)} new suggestions")

    # Step 2: auto-create from high-confidence pending suggestions
    created = suggester.auto_create_from_suggestions()
    for thesis in created:
        logger.info(f"Auto-created thesis: {thesis.name} (id={thesis.id})")
        log_event("thesis_auto_created", {
            "thesis_id": thesis.id,
            "thesis_name": thesis.name,
            "conviction": thesis.conviction,
        })

    pending = suggester.get_pending_suggestions()
    return {
        "new_suggestions": len(new_suggestions),
        "auto_created": len(created),
        "pending_review": len(pending),
        "created_names": [t.name for t in created],
    }


def check_overdue_reviews() -> list[dict]:
    """Find theses overdue for review and push to situation board."""
    tracker = ThesisTracker(paths.theses)
    overdue = tracker.get_theses_due_for_review()

    if not overdue:
        logger.info("No theses overdue for review")
        return []

    overdue_info = []
    for thesis in overdue:
        days_overdue = 0
        if thesis.next_review:
            days_overdue = (datetime.now() - thesis.next_review).days
        overdue_info.append({
            "id": thesis.id,
            "name": thesis.name,
            "conviction": thesis.conviction,
            "days_overdue": days_overdue,
            "last_review": thesis.last_review.isoformat() if thesis.last_review else "never",
        })

    logger.info(f"{len(overdue)} theses overdue for review")

    # Push to situation board
    try:
        from src.swarm.situation_board import SituationBoard
        board = SituationBoard.load_or_create()
        names = ", ".join(t["name"][:25] for t in overdue_info[:5])
        board.add_observation(
            source="thesis-maintenance",
            obs_type="review_overdue",
            text=f"{len(overdue)} theses overdue for review: {names}",
            symbols=[],
        )
        board.save()
    except Exception as e:
        logger.warning(f"Failed to push to situation board: {e}")

    return overdue_info


def fix_conviction_anchoring() -> list[dict]:
    """Reset any thesis anchored at 100% conviction back to 95%."""
    tracker = ThesisTracker(paths.theses)
    fixed = []

    for thesis in tracker.get_active_theses():
        if thesis.conviction >= 100:
            thesis.update_conviction(
                new_value=95,
                reason="[auto] Conviction ceiling enforcement — 95% max to prevent anchoring",
            )
            tracker._save_thesis(thesis)
            logger.info(f"Reset {thesis.name} conviction: 100% → 95%")
            fixed.append({"name": thesis.name, "id": thesis.id})
            log_event("conviction_ceiling_reset", {
                "thesis_id": thesis.id,
                "thesis_name": thesis.name,
                "old": 100,
                "new": 95,
            })

    return fixed


def main():
    logger.info("=== Thesis Maintenance Start ===")
    start = datetime.now()

    # 1. Suggestion pipeline
    suggestion_result = run_suggestion_pipeline()
    logger.info(f"Suggestions: {suggestion_result}")

    # 2. Overdue reviews
    overdue = check_overdue_reviews()

    # 3. Conviction anchoring fix
    anchoring_fixes = fix_conviction_anchoring()

    # 4. Summary log
    duration = (datetime.now() - start).total_seconds()
    summary = {
        "suggestions": suggestion_result,
        "overdue_reviews": len(overdue),
        "overdue_theses": [t["name"] for t in overdue],
        "anchoring_fixes": [t["name"] for t in anchoring_fixes],
        "duration_seconds": round(duration, 1),
    }
    log_event("maintenance_complete", summary)

    # Print summary
    print(f"\n{'=' * 60}")
    print("THESIS MAINTENANCE SUMMARY")
    print(f"{'=' * 60}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"New suggestions: {suggestion_result['new_suggestions']}")
    print(f"Auto-created: {suggestion_result['auto_created']}")
    if suggestion_result["created_names"]:
        for name in suggestion_result["created_names"]:
            print(f"  + {name}")
    print(f"Pending review: {suggestion_result['pending_review']}")
    print(f"Overdue reviews: {len(overdue)}")
    for t in overdue:
        print(f"  ! {t['name']} ({t['days_overdue']}d overdue, conv={t['conviction']}%)")
    if anchoring_fixes:
        print(f"Conviction ceiling resets: {len(anchoring_fixes)}")
        for t in anchoring_fixes:
            print(f"  ~ {t['name']}: 100% → 95%")
    print(f"Duration: {duration:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
