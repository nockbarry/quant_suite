#!/usr/bin/env python3
"""
Weekly Improvement Review Cron Job

Runs every Sunday at 6 PM to:
1. Analyze agent performance
2. Calculate signal quality metrics
3. Review portfolio performance
4. Generate improvement suggestions
5. Save report to ~/quant_results/improvements/reviews/

Usage:
    python3 scripts/cron_weekly_improvement_review.py
    python3 scripts/cron_weekly_improvement_review.py --dry-run
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths
from src.monitoring.improvement_tracker import get_improvement_tracker
from src.monitoring.signal_quality_tracker import get_signal_quality_tracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_weekly_review(dry_run: bool = False) -> dict:
    """Run the weekly improvement review."""
    logger.info("Starting weekly improvement review...")

    results = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "signal_quality": {},
        "improvement_review": {},
        "summary": {},
    }

    # 1. Calculate signal quality metrics
    logger.info("Calculating signal quality metrics...")
    try:
        quality_tracker = get_signal_quality_tracker()
        quality_metrics = quality_tracker.calculate_quality(days=30)
        quality_summary = quality_tracker.get_summary()

        results["signal_quality"] = quality_summary
        logger.info(f"Signal quality: {len(quality_metrics)} types analyzed")

        for signal_type, quality in quality_metrics.items():
            logger.info(
                f"  {signal_type}: hit_rate={quality.hit_rate:.0%}, "
                f"acted_on={quality.acted_on}, trend={quality.trend}"
            )
    except Exception as e:
        logger.error(f"Error calculating signal quality: {e}")
        results["signal_quality"] = {"error": str(e)}

    # 2. Run improvement review
    logger.info("Running improvement tracker review...")
    try:
        improvement_tracker = get_improvement_tracker()
        review = improvement_tracker.run_weekly_review(dry_run=dry_run)

        results["improvement_review"] = {
            "review_date": review.review_date.isoformat(),
            "period": f"{review.period_start.date()} to {review.period_end.date()}",
            "overall_trend": review.overall_trend,
            "new_suggestions": len(review.new_suggestions),
            "suggestions_resolved": review.suggestions_resolved,
            "suggestions_pending": review.suggestions_pending,
            "key_findings": review.key_findings,
            "next_focus_areas": review.next_focus_areas,
        }

        logger.info(f"Improvement review: trend={review.overall_trend}")
        logger.info(f"  New suggestions: {len(review.new_suggestions)}")
        logger.info(f"  Resolved: {review.suggestions_resolved}")
        logger.info(f"  Pending: {review.suggestions_pending}")

        if review.key_findings:
            logger.info("Key findings:")
            for finding in review.key_findings:
                logger.info(f"  - {finding}")

        if review.next_focus_areas:
            logger.info("Focus areas:")
            for area in review.next_focus_areas:
                logger.info(f"  - {area}")

        if review.new_suggestions:
            logger.info("New improvement suggestions:")
            for suggestion in review.new_suggestions:
                logger.info(f"  [{suggestion.priority.upper()}] {suggestion.title}")
                logger.info(f"    Action: {suggestion.suggested_action}")

    except Exception as e:
        logger.error(f"Error running improvement review: {e}")
        results["improvement_review"] = {"error": str(e)}

    # 3. Generate summary
    try:
        tracker_summary = improvement_tracker.get_summary()
        results["summary"] = {
            "total_suggestions": tracker_summary["total_suggestions"],
            "pending_high_priority": tracker_summary["pending_high_priority"],
            "signal_types_tracked": results["signal_quality"].get("total_types", 0),
            "avg_signal_hit_rate": results["signal_quality"].get("avg_hit_rate", 0),
            "degrading_signals": results["signal_quality"].get("degrading", []),
        }
    except Exception as e:
        logger.error(f"Error generating summary: {e}")

    # 4. Save results
    if not dry_run:
        results_dir = paths.base / "improvements"
        results_dir.mkdir(parents=True, exist_ok=True)

        summary_file = results_dir / f"weekly_summary_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(summary_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to: {summary_file}")

    return results


def print_summary(results: dict) -> None:
    """Print a formatted summary of the review."""
    print("\n" + "=" * 70)
    print("WEEKLY IMPROVEMENT REVIEW SUMMARY")
    print("=" * 70)

    print(f"\nTimestamp: {results['timestamp']}")
    if results.get("dry_run"):
        print("MODE: DRY RUN (no changes saved)")

    # Signal Quality
    sq = results.get("signal_quality", {})
    print("\n--- SIGNAL QUALITY ---")
    if "error" in sq:
        print(f"  Error: {sq['error']}")
    else:
        print(f"  Signal types tracked: {sq.get('total_types', 0)}")
        print(f"  Average hit rate: {sq.get('avg_hit_rate', 0):.0%}")
        if sq.get("best_signal"):
            print(f"  Best: {sq['best_signal']} ({sq.get('best_hit_rate', 0):.0%})")
        if sq.get("worst_signal"):
            print(f"  Worst: {sq['worst_signal']} ({sq.get('worst_hit_rate', 0):.0%})")
        if sq.get("degrading"):
            print(f"  DEGRADING: {', '.join(sq['degrading'])}")
        if sq.get("improving"):
            print(f"  Improving: {', '.join(sq['improving'])}")

    # Improvement Review
    ir = results.get("improvement_review", {})
    print("\n--- IMPROVEMENT TRACKER ---")
    if "error" in ir:
        print(f"  Error: {ir['error']}")
    else:
        print(f"  Period: {ir.get('period', 'N/A')}")
        print(f"  Overall trend: {ir.get('overall_trend', 'unknown').upper()}")
        print(f"  New suggestions: {ir.get('new_suggestions', 0)}")
        print(f"  Resolved: {ir.get('suggestions_resolved', 0)}")
        print(f"  Pending: {ir.get('suggestions_pending', 0)}")

        if ir.get("key_findings"):
            print("\n  Key Findings:")
            for finding in ir["key_findings"]:
                print(f"    - {finding}")

        if ir.get("next_focus_areas"):
            print("\n  Focus Areas:")
            for area in ir["next_focus_areas"]:
                print(f"    - {area}")

    # Summary
    summary = results.get("summary", {})
    print("\n--- OVERALL STATUS ---")
    print(f"  Total improvement suggestions: {summary.get('total_suggestions', 0)}")
    print(f"  High priority pending: {summary.get('pending_high_priority', 0)}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Weekly Improvement Review")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis without saving (preview mode)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    results = run_weekly_review(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_summary(results)


if __name__ == "__main__":
    main()
