#!/usr/bin/env python3
"""Bug Monitor cron wrapper.

Scans all logs for errors, categorizes bugs, and pushes critical ones to
the situation board. Auto-fixable recurring bugs get upgrade proposals.

Usage:
    PYTHONPATH=. python3 scripts/run_bug_monitor.py
    PYTHONPATH=. python3 scripts/run_bug_monitor.py --hours 48
"""
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bug_monitor")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan logs for bugs")
    parser.add_argument("--hours", type=int, default=24, help="Scan window in hours")
    args = parser.parse_args()

    from src.intelligence.bug_monitor import BugMonitor

    monitor = BugMonitor()
    bugs = monitor.scan_all(hours=args.hours)
    summary = monitor.get_summary()

    # Print summary
    print(f"\n=== Bug Monitor Report ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"Total bugs:      {summary['total']}")
    print(f"  Crashes:       {summary['crashes']}")
    print(f"  Errors:        {summary['errors']}")
    print(f"  Warnings:      {summary['warnings']}")
    print(f"  Silent fails:  {summary['silent_failures']}")
    print(f"  Auto-fixable:  {summary['auto_fixable']}")
    print(f"  Recurring(3+): {summary['recurring']}")

    if summary.get("top_errors"):
        print("\nTop errors:")
        for error_type, msg, count in summary["top_errors"]:
            print(f"  [{count}x] {error_type}: {msg}")

    # Push critical bugs to situation board
    critical = monitor.get_critical_bugs()
    if critical:
        try:
            from src.swarm.situation_board import SituationBoard
            board = SituationBoard.load()
            for bug in critical[:5]:  # Max 5 to avoid spam
                board.add_observation(
                    source="bug_monitor",
                    obs_type="system_error",
                    text=f"[{bug.severity.upper()}] {bug.error_type}: {bug.error_message[:80]} ({bug.occurrence_count}x)",
                    symbols=[],
                )
            board.save()
            logger.info(f"Pushed {min(len(critical), 5)} critical bugs to situation board")
        except Exception as e:
            logger.warning(f"Could not push to situation board: {e}")

    # Create upgrade proposals for recurring auto-fixable bugs
    auto_fixable_recurring = [
        b for b in monitor.get_auto_fixable()
        if b.occurrence_count >= 3
    ]
    if auto_fixable_recurring:
        try:
            from src.upgrades.auto_upgrader import UpgradeProposal
            from src.core.paths import paths

            proposals_dir = paths.base / "upgrades"
            proposals_dir.mkdir(parents=True, exist_ok=True)

            for bug in auto_fixable_recurring[:3]:  # Max 3 proposals per run
                proposal_id = f"upgrade_bugfix_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{bug.bug_id[-6:]}"
                proposal = UpgradeProposal(
                    id=proposal_id,
                    timestamp=datetime.now().isoformat(),
                    tier=1 if bug.severity != "crash" else 2,
                    category="bugfix",
                    description=f"Fix {bug.error_type} in {Path(bug.affected_module).name}: {bug.fix_description}",
                    files_to_modify=[bug.affected_module] if bug.affected_module else [],
                    files_to_create=[],
                    rationale=f"Recurring error ({bug.occurrence_count}x): {bug.error_message[:100]}",
                    evidence=f"Seen {bug.occurrence_count} times between {bug.first_seen[:16]} and {bug.last_seen[:16]}. "
                             f"Source: {bug.source_file}",
                    estimated_impact=f"Eliminate {bug.error_type} in {Path(bug.affected_module).name if bug.affected_module else 'unknown'}",
                    risk_level="low",
                )

                proposal_file = proposals_dir / f"{proposal_id}.json"
                with open(proposal_file, 'w') as f:
                    from dataclasses import asdict
                    json.dump(asdict(proposal), f, indent=2)

                # Link bug to proposal
                bug.fix_proposal_id = proposal_id
                logger.info(f"Created upgrade proposal: {proposal_id} for {bug.error_type}")

            # Re-save report with proposal links
            monitor._save_report()

        except Exception as e:
            logger.warning(f"Could not create upgrade proposals: {e}")

    print(f"\nReport saved: {monitor.REPORT_FILE}")
    return 0 if summary["crashes"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
