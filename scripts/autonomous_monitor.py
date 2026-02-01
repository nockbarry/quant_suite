#!/usr/bin/env python3
"""Autonomous Monitor - Long-running monitoring for Claude Code sessions.

This script enables Claude to operate autonomously for hours by:
1. Running a monitoring loop with configurable intervals
2. Processing the action queue from background daemons
3. Executing trades within authority
4. Outputting status that Claude can read and act on

Usage (from Claude Code):
    # Run monitoring loop for 2 hours with 5-minute checks
    PYTHONPATH=. python3 scripts/autonomous_monitor.py --duration 120 --interval 5

    # Run single check and exit
    PYTHONPATH=. python3 scripts/autonomous_monitor.py --once

    # Check action queue only
    PYTHONPATH=. python3 scripts/autonomous_monitor.py --queue-only

The output is structured so Claude can parse and act on it.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.action_queue import (
    ActionQueue,
    ActionPriority,
    ActionType,
    QueuedAction,
    get_action_queue,
)
from src.monitoring.autonomous_operator import (
    AutonomousOperator,
    ExecutionAuthority,
    TradeProposal,
    TradeType,
    get_autonomous_operator,
    start_autonomous_session,
)
from src.monitoring.operator_loop import get_operator_loop
from src.synthesis.state import UnifiedState
from src.core.paths import paths


def get_portfolio_context():
    """Get current portfolio context."""
    state = UnifiedState.load(paths.live_state)
    if not state or not state.portfolio:
        return None, None, None, None

    portfolio_value = state.portfolio.equity
    daily_pnl_pct = state.portfolio.day_pnl_pct
    current_positions = {p.symbol: p.market_value for p in state.positions}

    return state, portfolio_value, current_positions, daily_pnl_pct


def format_action_for_claude(action: QueuedAction) -> str:
    """Format a queued action for Claude to understand."""
    lines = []
    lines.append(f"  [{action.priority.name}] {action.action_type.value}")
    if action.symbol:
        lines.append(f"    Symbol: {action.symbol}")
    lines.append(f"    Suggested: {action.suggested_action}")
    if action.suggested_size_pct:
        lines.append(f"    Size: {action.suggested_size_pct}%")
    lines.append(f"    Reason: {action.reason}")
    if action.thesis_id:
        lines.append(f"    Thesis: {action.thesis_id}")
    lines.append(f"    ID: {action.action_id}")
    return "\n".join(lines)


def run_check(operator: AutonomousOperator, check_num: int) -> dict:
    """Run a single monitoring check and return structured results."""
    results = {
        "check_num": check_num,
        "timestamp": datetime.now().isoformat(),
        "actions_pending": [],
        "actions_critical": [],
        "portfolio": {},
        "alerts": [],
        "recommendations": [],
    }

    # Get portfolio state
    state, portfolio_value, current_positions, daily_pnl_pct = get_portfolio_context()
    if not state:
        results["error"] = "Could not load portfolio state"
        return results

    results["portfolio"] = {
        "equity": portfolio_value,
        "daily_pnl_pct": daily_pnl_pct,
        "positions": len(current_positions),
    }

    # Check action queue
    queue = get_action_queue()
    pending = queue.get_pending(max_items=20)
    critical = [a for a in pending if a.priority == ActionPriority.CRITICAL]

    results["actions_pending"] = [a.to_dict() for a in pending]
    results["actions_critical"] = [a.to_dict() for a in critical]

    # Run operator check for additional alerts
    try:
        loop = get_operator_loop()
        observation = loop.operator_check()

        for alert in observation.alerts:
            results["alerts"].append({
                "level": alert.level,
                "title": alert.title,
                "message": alert.message,
                "symbol": alert.symbol,
            })

        for action_item in observation.action_items:
            results["recommendations"].append({
                "priority": action_item.priority,
                "action": action_item.action,
                "reason": action_item.reason,
            })

    except Exception as e:
        results["operator_error"] = str(e)

    # Record the check
    operator.record_check([
        f"Check #{check_num}: {len(pending)} pending actions, {len(critical)} critical"
    ])

    return results


async def send_mobile_alerts_for_critical(results: dict):
    """Send mobile alerts for critical actions."""
    critical = results.get("actions_critical", [])
    if not critical:
        return

    try:
        from src.monitoring.alert_bridge import alert_pending_actions
        from src.monitoring.action_queue import ActionPriority
        await alert_pending_actions(
            priority_threshold=ActionPriority.CRITICAL,
            max_alerts=3,
        )
    except Exception as e:
        print(f"Failed to send mobile alerts: {e}")


def print_check_results(results: dict, verbose: bool = False):
    """Print check results in a format Claude can easily parse."""
    print("\n" + "=" * 60)
    print(f"AUTONOMOUS CHECK #{results['check_num']} - {results['timestamp'][:19]}")
    print("=" * 60)

    # Portfolio
    p = results.get("portfolio", {})
    if p:
        print(f"\n📊 PORTFOLIO")
        print(f"   Equity: ${p.get('equity', 0):,.2f}")
        print(f"   Day P&L: {p.get('daily_pnl_pct', 0):+.2f}%")
        print(f"   Positions: {p.get('positions', 0)}")

    # Critical actions - these need immediate attention
    critical = results.get("actions_critical", [])
    if critical:
        print(f"\n🚨 CRITICAL ACTIONS ({len(critical)}) - REQUIRE IMMEDIATE ATTENTION")
        for a in critical:
            print(f"   [{a['action_type']}] {a.get('symbol', 'N/A')}")
            print(f"      Action: {a['suggested_action']}")
            print(f"      Reason: {a['reason']}")
            print(f"      ID: {a['action_id']}")

    # Other pending actions
    pending = [a for a in results.get("actions_pending", [])
               if a not in critical]
    if pending:
        print(f"\n📋 PENDING ACTIONS ({len(pending)})")
        for a in pending[:5]:  # Show top 5
            priority = ActionPriority(a['priority']).name
            print(f"   [{priority}] {a['action_type']}: {a.get('symbol', 'N/A')}")
            print(f"      {a['reason'][:60]}...")

    # Alerts
    alerts = results.get("alerts", [])
    if alerts:
        print(f"\n⚠️ ALERTS ({len(alerts)})")
        for a in alerts[:5]:
            level_icon = "🔴" if a['level'] == "critical" else "🟡" if a['level'] == "warning" else "ℹ️"
            print(f"   {level_icon} {a['title']}: {a['message']}")

    # Recommendations
    recs = results.get("recommendations", [])
    if recs:
        print(f"\n💡 RECOMMENDATIONS ({len(recs)})")
        for r in recs[:3]:
            print(f"   [{r['priority'].upper()}] {r['action']}")
            print(f"      Reason: {r['reason']}")

    # Summary line for Claude to key on
    print("\n" + "-" * 60)
    if critical:
        print("⚡ ACTION REQUIRED: Process critical items above")
    elif pending:
        print(f"📌 {len(pending)} items pending review")
    else:
        print("✅ No actions required")
    print("=" * 60)


def run_loop(duration_minutes: int, interval_minutes: int, authority: str):
    """Run the monitoring loop for the specified duration."""
    # Initialize operator
    auth = ExecutionAuthority(authority.lower())
    operator = get_autonomous_operator(authority=auth)
    session = operator.start_session(resume=True)

    print(f"\n{'='*60}")
    print("AUTONOMOUS MONITOR STARTING")
    print(f"{'='*60}")
    print(f"Duration: {duration_minutes} minutes")
    print(f"Interval: {interval_minutes} minutes")
    print(f"Authority: {auth.value.upper()}")
    print(f"Session: {session.session_id}")
    print(f"{'='*60}\n")

    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    check_num = session.check_count

    try:
        while datetime.now() < end_time:
            check_num += 1

            # Run check
            results = run_check(operator, check_num)
            print_check_results(results)

            # Check for critical items that need Claude's attention
            critical = results.get("actions_critical", [])
            if critical:
                print("\n" + "!" * 60)
                print("CRITICAL ITEMS DETECTED - CLAUDE SHOULD PROCESS THESE")
                print("!" * 60)
                # Send mobile alert for human oversight
                asyncio.run(send_mobile_alerts_for_critical(results))

            # Calculate sleep time
            remaining = (end_time - datetime.now()).total_seconds() / 60
            sleep_minutes = min(interval_minutes, remaining)

            if sleep_minutes > 0:
                print(f"\n⏳ Next check in {sleep_minutes:.1f} minutes...")
                print(f"   Remaining: {remaining:.0f} minutes")
                print(f"   Press Ctrl+C to exit early\n")
                time.sleep(sleep_minutes * 60)

    except KeyboardInterrupt:
        print("\n\n🛑 Monitor stopped by user")

    # Final summary
    print(f"\n{'='*60}")
    print("AUTONOMOUS MONITOR SESSION COMPLETE")
    print(f"{'='*60}")
    print(f"Checks performed: {check_num - session.check_count + 1}")
    print(f"Duration: {(datetime.now() - start_time).total_seconds() / 60:.1f} minutes")
    print(operator.get_session_summary())


def check_queue_only():
    """Just check and display the action queue."""
    queue = get_action_queue()
    pending = queue.get_pending(max_items=50)

    print(f"\n{'='*60}")
    print("ACTION QUEUE STATUS")
    print(f"{'='*60}")

    summary = queue.get_summary()
    print(f"\nTotal pending: {summary['total_pending']}")

    if summary['by_priority']:
        print("\nBy Priority:")
        for p, count in summary['by_priority'].items():
            print(f"  {p}: {count}")

    if summary['by_type']:
        print("\nBy Type:")
        for t, count in summary['by_type'].items():
            print(f"  {t}: {count}")

    if pending:
        print(f"\n{'='*60}")
        print("PENDING ACTIONS")
        print(f"{'='*60}")
        for action in pending:
            print(f"\n{format_action_for_claude(action)}")

    print(f"\n{'='*60}")


def run_once():
    """Run a single check and exit."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    results = run_check(operator, session.check_count + 1)
    print_check_results(results, verbose=True)

    # Return exit code based on critical items
    if results.get("actions_critical"):
        return 1  # Critical items need attention
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous monitoring for Claude Code sessions"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=120,
        help="Duration in minutes (default: 120)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        help="Check interval in minutes (default: 5)"
    )
    parser.add_argument(
        "--authority", "-a",
        default="thesis",
        choices=["full", "thesis", "approved", "notify", "disabled"],
        help="Execution authority level (default: thesis)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single check and exit"
    )
    parser.add_argument(
        "--queue-only",
        action="store_true",
        help="Only check action queue, don't run full check"
    )

    args = parser.parse_args()

    if args.queue_only:
        check_queue_only()
        return 0
    elif args.once:
        return run_once()
    else:
        run_loop(args.duration, args.interval, args.authority)
        return 0


if __name__ == "__main__":
    sys.exit(main())
