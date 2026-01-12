#!/usr/bin/env python3
"""Paper Trading Review Cron Job.

Reviews paper trading performance for strategies in the promotion pipeline
and automatically advances candidates that meet gate requirements.
Run daily after market close (5:30 PM ET).

Usage:
    # Run once
    PYTHONPATH=. python scripts/cron_paper_trading_review.py

    # Add to crontab (run at 5:30 PM ET on weekdays)
    30 17 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python scripts/cron_paper_trading_review.py

Output:
    - Updates promotion_candidates.json
    - Summary report to stdout
    - Alerts for candidates ready for live trading
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.execution.promotion import (
    PromotionPipeline,
    PromotionStage,
    PromotionCandidate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PaperTradingReviewer:
    """Review and advance paper trading candidates."""

    def __init__(self):
        self.pipeline = PromotionPipeline()
        self.alerts_dir = paths.results / "alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

    def review_paper_trading(self) -> dict:
        """Review all paper trading candidates.

        Returns:
            Summary dict with review results
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "candidates_reviewed": 0,
            "advanced_to_review": [],
            "advanced_to_pending": [],
            "ready_for_live": [],
            "needs_attention": [],
            "metrics_updated": [],
        }

        # Get candidates in paper trading
        paper_candidates = self.pipeline.get_candidates_at_stage(
            PromotionStage.PAPER_TRADING
        )
        review_candidates = self.pipeline.get_candidates_at_stage(
            PromotionStage.PAPER_REVIEW
        )

        all_candidates = paper_candidates + review_candidates
        results["candidates_reviewed"] = len(all_candidates)

        logger.info(f"Reviewing {len(all_candidates)} paper trading candidates")

        for candidate in paper_candidates:
            # Update paper trading metrics from paper broker
            updated = self._update_paper_metrics(candidate)
            if updated:
                results["metrics_updated"].append(
                    f"{candidate.strategy_name}/{candidate.symbol}"
                )

            # Try to advance to PAPER_REVIEW
            if candidate.paper_days >= self.pipeline.gates.min_paper_days:
                success, reason = self.pipeline.advance_stage(
                    candidate.strategy_name,
                    candidate.symbol
                )
                if success:
                    results["advanced_to_review"].append(
                        f"{candidate.strategy_name}/{candidate.symbol}"
                    )
                    logger.info(
                        f"Advanced {candidate.strategy_name}/{candidate.symbol} "
                        f"to PAPER_REVIEW"
                    )
                else:
                    results["needs_attention"].append({
                        "candidate": f"{candidate.strategy_name}/{candidate.symbol}",
                        "reason": reason,
                    })

        # Check review candidates for advancement to LIVE_PENDING
        for candidate in review_candidates:
            success, reason = self.pipeline.advance_stage(
                candidate.strategy_name,
                candidate.symbol
            )
            if success:
                results["advanced_to_pending"].append(
                    f"{candidate.strategy_name}/{candidate.symbol}"
                )
                logger.info(
                    f"Advanced {candidate.strategy_name}/{candidate.symbol} "
                    f"to LIVE_PENDING"
                )
            else:
                if "Sharpe" in reason or "drawdown" in reason:
                    results["needs_attention"].append({
                        "candidate": f"{candidate.strategy_name}/{candidate.symbol}",
                        "reason": reason,
                    })

        # Get candidates ready for live (awaiting approval)
        ready_for_live = self.pipeline.get_ready_for_live()
        results["ready_for_live"] = [
            f"{c.strategy_name}/{c.symbol}" for c in ready_for_live
        ]

        return results

    def _update_paper_metrics(self, candidate: PromotionCandidate) -> bool:
        """Update paper trading metrics from paper broker data.

        Returns:
            True if metrics were updated
        """
        # Calculate paper trading days
        if candidate.paper_start_date:
            candidate.paper_days = (
                datetime.now() - candidate.paper_start_date
            ).days

        # Try to load paper trading results
        paper_results_path = (
            paths.results / "paper_trading" /
            f"{candidate.strategy_name}_{candidate.symbol}.json"
        )

        if paper_results_path.exists():
            try:
                with open(paper_results_path) as f:
                    data = json.load(f)

                candidate.paper_pnl = data.get("total_pnl", 0.0)
                candidate.paper_pnl_pct = data.get("total_pnl_pct", 0.0)
                candidate.paper_trades = data.get("num_trades", 0)
                candidate.paper_sharpe = data.get("sharpe_ratio")
                candidate.paper_max_drawdown = data.get("max_drawdown")
                candidate.paper_win_rate = data.get("win_rate")

                self.pipeline._save_candidates()
                return True

            except Exception as e:
                logger.warning(
                    f"Could not load paper results for "
                    f"{candidate.strategy_name}/{candidate.symbol}: {e}"
                )

        return False

    def generate_report(self, results: dict) -> str:
        """Generate markdown report from review results."""
        lines = [
            "# Paper Trading Review Report",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
            f"- Candidates reviewed: {results['candidates_reviewed']}",
            f"- Advanced to review: {len(results['advanced_to_review'])}",
            f"- Advanced to pending: {len(results['advanced_to_pending'])}",
            f"- Ready for live: {len(results['ready_for_live'])}",
            f"- Needs attention: {len(results['needs_attention'])}",
            "",
        ]

        if results['ready_for_live']:
            lines.append("## Ready for Live Trading (Awaiting Approval)")
            lines.append("")
            for name in results['ready_for_live']:
                lines.append(f"- **{name}**")
            lines.append("")
            lines.append("> Run `/promote` skill to approve these candidates")
            lines.append("")

        if results['advanced_to_review']:
            lines.append("## Advanced to Paper Review")
            lines.append("")
            for name in results['advanced_to_review']:
                lines.append(f"- {name}")
            lines.append("")

        if results['advanced_to_pending']:
            lines.append("## Advanced to Live Pending")
            lines.append("")
            for name in results['advanced_to_pending']:
                lines.append(f"- {name}")
            lines.append("")

        if results['needs_attention']:
            lines.append("## Needs Attention")
            lines.append("")
            for item in results['needs_attention']:
                lines.append(f"- **{item['candidate']}**: {item['reason']}")
            lines.append("")

        # Pipeline status
        lines.append("## Current Pipeline Status")
        lines.append("")
        lines.append(self.pipeline.generate_report())

        return "\n".join(lines)

    def save_alert_if_ready(self, results: dict) -> Optional[Path]:
        """Save alert file if candidates are ready for live trading."""
        if not results['ready_for_live']:
            return None

        alert = {
            "type": "promotion_ready",
            "timestamp": datetime.now().isoformat(),
            "message": f"{len(results['ready_for_live'])} candidates ready for live trading",
            "candidates": results['ready_for_live'],
            "action_required": "Run /promote skill to approve",
        }

        alert_path = self.alerts_dir / "promotion_ready.json"
        with open(alert_path, "w") as f:
            json.dump(alert, f, indent=2)

        logger.info(f"Saved promotion alert to {alert_path}")
        return alert_path


def main():
    parser = argparse.ArgumentParser(
        description="Review paper trading and advance candidates"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save changes"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full markdown report"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    reviewer = PaperTradingReviewer()

    # Run review
    results = reviewer.review_paper_trading()

    # Output
    print("\n" + "=" * 60)
    print("PAPER TRADING REVIEW SUMMARY")
    print("=" * 60)
    print(f"Timestamp: {results['timestamp']}")
    print(f"Candidates reviewed: {results['candidates_reviewed']}")
    print(f"Metrics updated: {len(results['metrics_updated'])}")
    print(f"Advanced to review: {len(results['advanced_to_review'])}")
    print(f"Advanced to pending: {len(results['advanced_to_pending'])}")
    print(f"Ready for live: {len(results['ready_for_live'])}")
    print(f"Needs attention: {len(results['needs_attention'])}")

    if results['ready_for_live']:
        print("\n*** CANDIDATES READY FOR LIVE TRADING ***")
        for name in results['ready_for_live']:
            print(f"  - {name}")
        print("\nRun '/promote' skill to approve these candidates")

    if results['needs_attention']:
        print("\n*** NEEDS ATTENTION ***")
        for item in results['needs_attention']:
            print(f"  - {item['candidate']}: {item['reason']}")

    print("=" * 60)

    # Save alert if needed
    if not args.dry_run:
        reviewer.save_alert_if_ready(results)

    # Full report if requested
    if args.report:
        report = reviewer.generate_report(results)
        report_path = paths.results / "reports" / f"paper_review_{datetime.now().strftime('%Y%m%d')}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nFull report saved to: {report_path}")

    return len(results['ready_for_live'])


if __name__ == "__main__":
    exit_code = main()
    exit(0)
