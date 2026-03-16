#!/usr/bin/env python3
"""Claude Execute - Trade execution interface for Claude's autonomous operation.

This script provides Claude with a simple interface to:
1. Check if a trade is allowed under current safety rails
2. Execute trades with proper logging
3. View current authority and limits

Usage:
    # Check if a trade is allowed
    python scripts/claude_execute.py check BUY AAPL 5%

    # Execute a trade (with confirmation)
    python scripts/claude_execute.py execute BUY AAPL 10 --thesis venezuela123 --reason "Signpost triggered"

    # Close a position
    python scripts/claude_execute.py execute CLOSE ERY --reason "Thesis conflict"

    # View current session and authority
    python scripts/claude_execute.py status

    # Set execution authority
    python scripts/claude_execute.py authority THESIS_ONLY

    # Add focus area for session
    python scripts/claude_execute.py focus "Monitor energy concentration"
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.autonomous_operator import (
    AutonomousOperator,
    ExecutionAuthority,
    TradeProposal,
    TradeType,
    SafetyRails,
    get_autonomous_operator,
    start_autonomous_session,
)
from src.synthesis.state import UnifiedState
from src.core.paths import paths


def get_portfolio_context():
    """Get current portfolio context for safety checks."""
    state = UnifiedState.load(paths.live_state)
    if not state:
        return None, None, None

    portfolio_value = state.portfolio.equity if state.portfolio else 0
    daily_pnl_pct = state.portfolio.day_pnl_pct if state.portfolio else 0

    current_positions = {}
    if state.positions:
        for pos in state.positions:
            current_positions[pos.symbol] = pos.market_value

    return portfolio_value, current_positions, daily_pnl_pct


def cmd_check(args):
    """Check if a trade is allowed."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    portfolio_value, current_positions, daily_pnl_pct = get_portfolio_context()
    if not portfolio_value:
        print("ERROR: Could not load portfolio state")
        return 1

    # Parse size
    size_pct = None
    quantity = None
    if args.size:
        if args.size.endswith('%'):
            size_pct = float(args.size[:-1])
        else:
            quantity = int(args.size)

    # Determine trade type
    trade_type = TradeType.THESIS_ADD if args.action == "BUY" else TradeType.THESIS_TRIM
    if args.action == "CLOSE":
        trade_type = TradeType.THESIS_EXIT

    proposal = TradeProposal(
        symbol=args.symbol,
        action=args.action.upper(),
        quantity=quantity,
        size_pct=size_pct,
        trade_type=trade_type,
        thesis_id=args.thesis,
        reasoning=args.reason or "",
        confidence=0.7,
    )

    allowed, reason = operator.check_trade_allowed(
        proposal, portfolio_value, current_positions, daily_pnl_pct
    )

    print(f"\n{'='*50}")
    print(f"TRADE CHECK: {args.action.upper()} {args.symbol}")
    print(f"{'='*50}")
    print(f"Size: {args.size or 'not specified'}")
    print(f"Thesis: {args.thesis or 'none'}")
    print(f"Authority: {session.authority.value.upper()}")
    print(f"{'='*50}")

    if allowed:
        print(f"✅ ALLOWED: {reason}")
        return 0
    else:
        print(f"❌ BLOCKED: {reason}")
        return 1


def cmd_execute(args):
    """Execute a trade."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    portfolio_value, current_positions, daily_pnl_pct = get_portfolio_context()
    if not portfolio_value:
        print("ERROR: Could not load portfolio state")
        return 1

    # Determine trade type
    trade_type = TradeType.THESIS_ADD
    if args.action.upper() == "SELL":
        trade_type = TradeType.THESIS_TRIM
    elif args.action.upper() == "CLOSE":
        trade_type = TradeType.THESIS_EXIT
    if args.stop_loss:
        trade_type = TradeType.STOP_LOSS

    proposal = TradeProposal(
        symbol=args.symbol,
        action=args.action.upper(),
        quantity=int(args.quantity) if args.quantity else None,
        trade_type=trade_type,
        thesis_id=args.thesis,
        reasoning=args.reason or "",
        confidence=args.confidence or 0.7,
        urgency=args.urgency or "normal",
    )

    # Check first
    allowed, reason = operator.check_trade_allowed(
        proposal, portfolio_value, current_positions, daily_pnl_pct
    )

    print(f"\n{'='*50}")
    print(f"EXECUTE: {args.action.upper()} {args.symbol} {args.quantity or ''}")
    print(f"{'='*50}")
    print(f"Thesis: {args.thesis or 'none'}")
    print(f"Reason: {args.reason or 'none'}")
    print(f"Authority: {session.authority.value.upper()}")

    if not allowed:
        print(f"{'='*50}")
        print(f"❌ BLOCKED: {reason}")
        return 1

    if args.dry_run:
        print(f"{'='*50}")
        print("🔍 DRY RUN - Would execute trade")
        return 0

    # Execute
    print(f"{'='*50}")
    print("Executing...")

    result = asyncio.run(operator.execute_trade(
        proposal, portfolio_value, current_positions, daily_pnl_pct
    ))

    if result.success:
        print(f"✅ SUCCESS: {result.message}")

        # Record decision
        operator.record_decision({
            "type": "trade_executed",
            "symbol": args.symbol,
            "action": args.action.upper(),
            "quantity": args.quantity,
            "thesis_id": args.thesis,
            "reasoning": args.reason,
        })
        return 0
    else:
        print(f"❌ FAILED: {result.message}")
        return 1


def cmd_status(args):
    """Show current session status."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    print(operator.get_session_summary())

    # Also show safety rails
    rails = session.safety_rails
    print("\nSAFETY RAILS:")
    print(f"  Max trade size: {rails.max_single_trade_pct}%")
    print(f"  Max daily trades: {rails.max_daily_trades}")
    print(f"  Max daily loss: {rails.max_daily_loss_pct}%")
    print(f"  Max position: {rails.max_position_pct}%")
    print(f"  Max sector: {rails.max_sector_pct}%")
    print(f"  Trading hours: {rails.allowed_hours[0]}-{rails.allowed_hours[1]} ET")

    return 0


def cmd_authority(args):
    """Set execution authority."""
    try:
        authority = ExecutionAuthority(args.level.lower())
    except ValueError:
        print(f"Invalid authority level: {args.level}")
        print(f"Valid levels: {[e.value for e in ExecutionAuthority]}")
        return 1

    operator = get_autonomous_operator(authority=authority)
    operator.authority = authority
    session = operator.start_session(resume=True)
    session.authority = authority
    operator._save_session()

    print(f"✅ Authority set to: {authority.value.upper()}")
    print(f"\nWhat this means:")

    descriptions = {
        ExecutionAuthority.FULL: "Execute any trade within risk limits",
        ExecutionAuthority.THESIS_ONLY: "Only execute trades linked to active theses",
        ExecutionAuthority.APPROVED: "Only execute stop-loss and signpost exits",
        ExecutionAuthority.NOTIFY: "Don't execute, just log and notify",
        ExecutionAuthority.DISABLED: "No execution, monitoring only",
    }
    print(f"  {descriptions.get(authority, 'Unknown')}")

    return 0


def cmd_focus(args):
    """Add focus area for session."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    if args.clear:
        session.focus_areas = []
        print("Focus areas cleared")
    else:
        session.focus_areas.append(args.area)
        print(f"Added focus: {args.area}")

    operator._save_session()

    print(f"\nCurrent focus areas:")
    for f in session.focus_areas:
        print(f"  - {f}")

    return 0


def cmd_observe(args):
    """Record an observation."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    session.observations.append(args.observation)
    operator._save_session()

    print(f"✅ Recorded: {args.observation}")
    return 0


def cmd_pending(args):
    """Manage pending actions."""
    operator = get_autonomous_operator()
    session = operator.start_session(resume=True)

    if args.add:
        operator.add_pending_action({
            "id": datetime.now().strftime("%H%M%S"),
            "description": args.add,
            "priority": args.priority or "medium",
        })
        print(f"Added pending action: {args.add}")
    elif args.complete:
        operator.complete_pending_action(args.complete)
        print(f"Completed action: {args.complete}")
    else:
        print("Pending actions:")
        for a in session.pending_actions:
            print(f"  [{a.get('id')}] [{a.get('priority', 'medium')}] {a.get('description')}")

    return 0


def cmd_handoff(args):
    """Generate handoff context for next session."""
    operator = get_autonomous_operator()
    operator.start_session(resume=True)

    context = operator.get_handoff_context()

    if args.json:
        print(json.dumps(context, indent=2, default=str))
    else:
        print("\n" + "="*60)
        print("SESSION HANDOFF CONTEXT")
        print("="*60)
        print(f"\nSession: {context['session_id']}")
        print(f"Duration: {context['session_duration_hours']:.1f} hours")
        print(f"Trades today: {context['trades_today']}")
        print(f"Daily P&L: {context['daily_pnl_pct']:+.2f}%")
        print(f"Authority: {context['authority'].upper()}")

        print(f"\nFocus Areas:")
        for f in context['focus_areas']:
            print(f"  - {f}")

        print(f"\nPending Actions:")
        for a in context['pending_actions']:
            print(f"  - {a.get('description', str(a))}")

        print(f"\nKey Observations:")
        for o in context['key_observations'][-5:]:
            print(f"  - {o}")

        print(f"\nRecent Trades:")
        for t in context['recent_trades'][-5:]:
            print(f"  - {t.get('symbol')} {t.get('action')}: {t.get('message', '')[:50]}")

        print("="*60)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Claude Execute - Trade execution interface for autonomous operation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check if a trade is allowed")
    check_parser.add_argument("action", choices=["BUY", "SELL", "CLOSE", "buy", "sell", "close"])
    check_parser.add_argument("symbol", help="Stock symbol")
    check_parser.add_argument("size", nargs="?", help="Quantity or percentage (e.g., 10 or 5%)")
    check_parser.add_argument("--thesis", help="Thesis ID")
    check_parser.add_argument("--reason", help="Trade reasoning")

    # Execute command
    exec_parser = subparsers.add_parser("execute", help="Execute a trade")
    exec_parser.add_argument("action", choices=["BUY", "SELL", "CLOSE", "buy", "sell", "close"])
    exec_parser.add_argument("symbol", help="Stock symbol")
    exec_parser.add_argument("quantity", nargs="?", help="Number of shares")
    exec_parser.add_argument("--thesis", help="Thesis ID")
    exec_parser.add_argument("--reason", help="Trade reasoning")
    exec_parser.add_argument("--confidence", type=float, help="Confidence 0-1")
    exec_parser.add_argument("--urgency", choices=["low", "normal", "high", "immediate"])
    exec_parser.add_argument("--stop-loss", action="store_true", help="This is a stop-loss trade")
    exec_parser.add_argument("--dry-run", action="store_true", help="Check but don't execute")

    # Status command
    subparsers.add_parser("status", help="Show current session status")

    # Authority command
    auth_parser = subparsers.add_parser("authority", help="Set execution authority")
    auth_parser.add_argument("level", help="Authority level (full, thesis, approved, notify, disabled)")

    # Focus command
    focus_parser = subparsers.add_parser("focus", help="Set focus area")
    focus_parser.add_argument("area", nargs="?", help="Focus area to add")
    focus_parser.add_argument("--clear", action="store_true", help="Clear all focus areas")

    # Observe command
    obs_parser = subparsers.add_parser("observe", help="Record an observation")
    obs_parser.add_argument("observation", help="Observation to record")

    # Pending command
    pend_parser = subparsers.add_parser("pending", help="Manage pending actions")
    pend_parser.add_argument("--add", help="Add pending action")
    pend_parser.add_argument("--complete", help="Complete action by ID")
    pend_parser.add_argument("--priority", choices=["low", "medium", "high"])

    # Handoff command
    handoff_parser = subparsers.add_parser("handoff", help="Generate handoff context")
    handoff_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "check": cmd_check,
        "execute": cmd_execute,
        "status": cmd_status,
        "authority": cmd_authority,
        "focus": cmd_focus,
        "observe": cmd_observe,
        "pending": cmd_pending,
        "handoff": cmd_handoff,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
