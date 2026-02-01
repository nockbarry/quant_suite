#!/usr/bin/env python3
"""Alert Bridge - Connects action queue to mobile notifications.

This module bridges the action queue (populated by daemons) to mobile
alerts (Telegram/Discord). It ensures human oversight of autonomous
trading operations.

Usage:
    # Send alerts for all pending critical items
    PYTHONPATH=. python -m src.monitoring.alert_bridge

    # Check and alert on specific action
    from src.monitoring.alert_bridge import alert_for_action
    await alert_for_action(action_id)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.monitoring.action_queue import (
    ActionQueue,
    ActionPriority,
    ActionType,
    QueuedAction,
    get_action_queue,
)
from src.alerts.mobile_bot import (
    MobileAlertBot,
    MobileAlert,
    AlertLevel,
    send_mobile_alert,
)

logger = logging.getLogger(__name__)

# Track which actions have been alerted to avoid duplicates
ALERTED_ACTIONS_FILE = Path.home() / "quant_results" / "live" / "alerted_actions.json"


def load_alerted_actions() -> dict:
    """Load set of action IDs that have been alerted."""
    import json
    if ALERTED_ACTIONS_FILE.exists():
        try:
            with open(ALERTED_ACTIONS_FILE) as f:
                data = json.load(f)
                # Clean old entries (>24h)
                cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
                return {k: v for k, v in data.items() if v > cutoff}
        except Exception:
            return {}
    return {}


def save_alerted_actions(alerted: dict):
    """Save alerted action IDs."""
    import json
    ALERTED_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTED_ACTIONS_FILE, 'w') as f:
        json.dump(alerted, f)


def action_to_alert_level(action: QueuedAction) -> AlertLevel:
    """Convert action priority to alert level."""
    mapping = {
        ActionPriority.CRITICAL: AlertLevel.CRITICAL,
        ActionPriority.HIGH: AlertLevel.HIGH,
        ActionPriority.MEDIUM: AlertLevel.MEDIUM,
        ActionPriority.LOW: AlertLevel.LOW,
    }
    return mapping.get(action.priority, AlertLevel.MEDIUM)


def format_action_for_alert(action: QueuedAction) -> MobileAlert:
    """Convert a queued action to a mobile alert."""

    # Build title based on action type
    type_titles = {
        ActionType.CONVERGENCE: f"Convergence: {action.symbol}",
        ActionType.SIGNPOST_TRIGGERED: f"Signpost: {action.symbol or 'Thesis'}",
        ActionType.STOP_LOSS: f"STOP LOSS: {action.symbol}",
        ActionType.TAKE_PROFIT: f"Take Profit: {action.symbol}",
        ActionType.DRAWDOWN_ALERT: "Portfolio Drawdown",
        ActionType.RULE_TRIGGERED: f"Rule Fired: {action.symbol}",
        ActionType.DATA_ALERT: f"Data Alert: {action.symbol}",
        ActionType.THESIS_REVIEW: f"Thesis Review: {action.thesis_id}",
        ActionType.POSITION_ALERT: f"Position: {action.symbol}",
        ActionType.REGIME_CHANGE: "Market Regime Change",
    }
    title = type_titles.get(action.action_type, f"{action.action_type.value}: {action.symbol}")

    # Build message
    message = action.reason
    if action.data:
        # Add key data points
        if "signal_count" in action.data:
            message += f"\nSignals: {action.data['signal_count']}"
        if "direction" in action.data:
            message += f"\nDirection: {action.data['direction']}"
        if "current_loss_pct" in action.data:
            message += f"\nLoss: {action.data['current_loss_pct']:.1f}%"
        if "drawdown_pct" in action.data:
            message += f"\nDrawdown: {action.data['drawdown_pct']:.1f}%"
        if "level" in action.data:
            message += f"\nLevel: {action.data['level']}"

    # Build action required string
    action_required = action.suggested_action
    if action.suggested_size_pct:
        action_required += f" ({action.suggested_size_pct}%)"
    if action.thesis_id:
        action_required += f"\nThesis: {action.thesis_id[:20]}..."

    symbols = [action.symbol] if action.symbol else []

    return MobileAlert(
        title=title,
        message=message,
        level=action_to_alert_level(action),
        symbols=symbols,
        action_required=action_required,
        timestamp=action.created_at,
    )


async def alert_for_action(action: QueuedAction, bot: Optional[MobileAlertBot] = None) -> bool:
    """Send mobile alert for a specific action."""
    close_bot = False
    if bot is None:
        bot = MobileAlertBot()
        close_bot = True

    try:
        alert = format_action_for_alert(action)
        result = await bot.send_alert(alert)

        if result.get("sent"):
            logger.info(f"Alert sent for action {action.action_id}: {action.action_type.value}")
            return True
        else:
            logger.debug(f"Alert filtered: {result.get('reason', 'unknown')}")
            return False

    finally:
        if close_bot:
            await bot.close()


async def alert_pending_actions(
    priority_threshold: ActionPriority = ActionPriority.HIGH,
    max_alerts: int = 5,
) -> dict:
    """Send alerts for pending actions above threshold.

    Returns dict with counts of alerts sent.
    """
    queue = get_action_queue()
    pending = queue.get_pending(max_items=20)

    # Filter by priority
    to_alert = [
        a for a in pending
        if a.priority.value <= priority_threshold.value
    ]

    # Check which ones we've already alerted
    alerted = load_alerted_actions()
    to_alert = [a for a in to_alert if a.action_id not in alerted]

    # Limit alerts
    to_alert = to_alert[:max_alerts]

    if not to_alert:
        logger.info("No new actions to alert")
        return {"total": 0, "sent": 0, "filtered": 0}

    bot = MobileAlertBot()
    results = {"total": len(to_alert), "sent": 0, "filtered": 0}

    try:
        for action in to_alert:
            sent = await alert_for_action(action, bot)
            if sent:
                results["sent"] += 1
                alerted[action.action_id] = datetime.now().isoformat()
            else:
                results["filtered"] += 1

        # Save alerted actions
        save_alerted_actions(alerted)

    finally:
        await bot.close()

    logger.info(f"Alert results: {results}")
    return results


async def send_trade_approval_request(
    symbol: str,
    action: str,
    size_pct: float,
    reason: str,
    thesis_id: Optional[str] = None,
) -> bool:
    """Send a trade that needs human approval.

    This is for QUEUE-type rules that require human confirmation.
    """
    message = f"{action} {size_pct}% position\n{reason}"
    if thesis_id:
        message += f"\nThesis: {thesis_id}"

    return await send_mobile_alert(
        title=f"Approve Trade: {symbol}",
        message=message,
        level="critical",
        symbols=[symbol],
        action="Reply APPROVE or REJECT",
    )


async def send_session_summary(
    check_count: int,
    trades_today: int,
    daily_pnl_pct: float,
    pending_actions: int,
    observations: list[str],
) -> bool:
    """Send session status summary (e.g., at end of operator session)."""
    message = f"Checks: {check_count}\n"
    message += f"Trades: {trades_today}\n"
    message += f"P&L: {daily_pnl_pct:+.2f}%\n"
    message += f"Pending: {pending_actions}"

    if observations:
        message += f"\n\nRecent:\n- " + "\n- ".join(observations[-3:])

    return await send_mobile_alert(
        title="Session Summary",
        message=message,
        level="medium",
        action="Review before next session",
    )


async def main():
    """Check and alert on pending actions."""
    import argparse

    parser = argparse.ArgumentParser(description="Send mobile alerts for pending actions")
    parser.add_argument(
        "--threshold", "-t",
        choices=["critical", "high", "medium", "low"],
        default="high",
        help="Minimum priority to alert (default: high)"
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=5,
        help="Maximum alerts to send (default: 5)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test alert"
    )

    args = parser.parse_args()

    if args.test:
        print("Sending test alert...")
        result = await send_mobile_alert(
            title="Test Alert",
            message="This is a test from Project Athena autonomous operator",
            level="high",
            symbols=["SPY"],
            action="No action required - just testing",
        )
        print(f"Result: {result}")
        return

    threshold = ActionPriority[args.threshold.upper()]
    results = await alert_pending_actions(
        priority_threshold=threshold,
        max_alerts=args.max,
    )

    print(f"Alert Results:")
    print(f"  Total pending: {results['total']}")
    print(f"  Alerts sent: {results['sent']}")
    print(f"  Filtered: {results['filtered']}")


if __name__ == "__main__":
    asyncio.run(main())
