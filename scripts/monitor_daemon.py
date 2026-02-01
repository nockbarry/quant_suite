#!/usr/bin/env python3
"""Monitor Daemon - Background process that feeds the action queue for Claude.

This daemon runs continuously (via systemd, cron, or nohup) and:
1. Monitors unified state for alerts
2. Checks rules engine for triggers
3. Detects signal convergences
4. Monitors position stop losses
5. Queues actions for Claude to process

This is the "always-on" part of the system. It doesn't make decisions
or execute trades - it just flags things for Claude's attention.

Usage:
    # Run continuously (foreground)
    PYTHONPATH=. python3 scripts/monitor_daemon.py

    # Run as background process
    nohup PYTHONPATH=. python3 scripts/monitor_daemon.py &

    # Run single cycle (for cron)
    PYTHONPATH=. python3 scripts/monitor_daemon.py --once

    # Install as cron job (every 5 min during market hours)
    # */5 9-16 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/monitor_daemon.py --once >> ~/quant_results/logs/monitor_daemon.log 2>&1
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Flag to control mobile alerts
ENABLE_MOBILE_ALERTS = True

from src.monitoring.action_queue import (
    ActionQueue,
    ActionPriority,
    ActionType,
    QueuedAction,
    queue_signpost_trigger,
    queue_convergence,
    queue_stop_loss,
    queue_drawdown_alert,
    queue_rule_triggered,
    get_action_queue,
)
from src.synthesis.state import UnifiedState
from src.core.paths import paths

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonitorDaemon:
    """Background monitor that populates the action queue."""

    def __init__(self):
        self.queue = get_action_queue()
        self.last_check = None
        self.check_count = 0

        # Tracking to avoid duplicate alerts
        self.alerted_positions = {}  # symbol -> last alert time
        self.alerted_drawdown_level = 0

    def load_state(self) -> UnifiedState | None:
        """Load current unified state."""
        try:
            return UnifiedState.load(paths.live_state)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def check_position_stops(self, state: UnifiedState):
        """Check for positions hitting stop loss levels."""
        if not state.positions:
            return

        for pos in state.positions:
            # Skip if recently alerted
            last_alert = self.alerted_positions.get(pos.symbol)
            if last_alert and (datetime.now() - last_alert) < timedelta(hours=1):
                continue

            # Check for significant losses
            if pos.unrealized_pnl_pct < -10:
                queue_stop_loss(
                    symbol=pos.symbol,
                    current_loss_pct=pos.unrealized_pnl_pct,
                    stop_level_pct=-10,
                    thesis_id=pos.thesis_id,
                )
                self.alerted_positions[pos.symbol] = datetime.now()
                logger.info(f"Queued stop loss alert for {pos.symbol} ({pos.unrealized_pnl_pct:.1f}%)")

            elif pos.unrealized_pnl_pct < -15:
                queue_stop_loss(
                    symbol=pos.symbol,
                    current_loss_pct=pos.unrealized_pnl_pct,
                    stop_level_pct=-15,
                    thesis_id=pos.thesis_id,
                )
                self.alerted_positions[pos.symbol] = datetime.now()
                logger.info(f"Queued CRITICAL stop loss for {pos.symbol} ({pos.unrealized_pnl_pct:.1f}%)")

    def check_portfolio_drawdown(self, state: UnifiedState):
        """Check for portfolio-level drawdown."""
        if not state.portfolio:
            return

        daily_pnl_pct = state.portfolio.day_pnl_pct

        # 5-level drawdown protection
        levels = [
            (1, -3.0, "Reduce position sizes"),
            (2, -5.0, "No new longs"),
            (3, -7.0, "Close weakest positions"),
            (4, -10.0, "Close 50% of portfolio"),
            (5, -15.0, "Emergency close all"),
        ]

        for level, threshold, action in levels:
            if daily_pnl_pct < threshold and level > self.alerted_drawdown_level:
                queue_drawdown_alert(
                    drawdown_pct=daily_pnl_pct,
                    level=level,
                    action_required=action,
                )
                self.alerted_drawdown_level = level
                logger.warning(f"Queued drawdown alert level {level} ({daily_pnl_pct:.1f}%)")

        # Reset if recovered
        if daily_pnl_pct > -2.0:
            self.alerted_drawdown_level = 0

    def check_signpost_triggers(self, state: UnifiedState):
        """Check for recently triggered signposts."""
        if not state.theses:
            return

        for thesis in state.theses:
            # Check if thesis has signpost_alerts (from state)
            if hasattr(thesis, 'recent_triggers') and thesis.recent_triggers:
                for trigger in thesis.recent_triggers:
                    # Queue if triggered in last hour
                    if trigger.get('triggered_within_hours', 24) < 1:
                        queue_signpost_trigger(
                            symbol=thesis.positions[0] if thesis.positions else "PORTFOLIO",
                            thesis_id=thesis.id,
                            thesis_name=thesis.name,
                            signpost_description=trigger.get('description', ''),
                            outcome=trigger.get('outcome', 'unknown'),
                            suggested_action="REVIEW",
                        )
                        logger.info(f"Queued signpost trigger for thesis {thesis.name}")

    def check_convergences(self, state: UnifiedState):
        """Check for signal convergences."""
        try:
            from src.monitoring.signal_summary import get_signal_summary

            summary = get_signal_summary()

            for conv in summary.convergences:
                if conv.convergence_score >= 0.6:  # 60%+ strength
                    queue_convergence(
                        symbol=conv.symbol,
                        direction=conv.direction,
                        signal_count=len(conv.signals),
                        signals=[s.type for s in conv.signals],
                        suggested_action="BUY" if conv.direction == "bullish" else "SELL",
                        suggested_size_pct=2.0 if conv.convergence_score >= 0.8 else 1.0,
                    )
                    logger.info(f"Queued convergence for {conv.symbol} ({len(conv.signals)} signals)")

        except Exception as e:
            logger.error(f"Error checking convergences: {e}")

    def check_rules_engine(self, state: UnifiedState):
        """Check rules engine for triggered rules."""
        try:
            from src.execution.rules_engine import RulesEngine

            # This would need the rules engine to be set up
            # For now, just log that we would check
            logger.debug("Rules engine check - not implemented yet")

        except ImportError:
            pass  # Rules engine may not be set up

    def run_cycle(self):
        """Run a single monitoring cycle."""
        self.check_count += 1
        logger.info(f"Monitor daemon cycle #{self.check_count}")

        state = self.load_state()
        if not state:
            logger.warning("No state available, skipping cycle")
            return

        # Run all checks
        self.check_position_stops(state)
        self.check_portfolio_drawdown(state)
        self.check_signpost_triggers(state)
        self.check_convergences(state)
        self.check_rules_engine(state)

        # Clean up old processed items
        self.queue.clear_processed(older_than_hours=24)

        self.last_check = datetime.now()

        # Log summary
        summary = self.queue.get_summary()
        logger.info(f"Queue status: {summary['total_pending']} pending actions")

        # Send mobile alerts for critical/high priority items
        if ENABLE_MOBILE_ALERTS and summary['total_pending'] > 0:
            try:
                from src.monitoring.alert_bridge import alert_pending_actions
                from src.monitoring.action_queue import ActionPriority
                asyncio.run(alert_pending_actions(
                    priority_threshold=ActionPriority.HIGH,
                    max_alerts=3,
                ))
            except Exception as e:
                logger.warning(f"Failed to send mobile alerts: {e}")

    def run_continuous(self, interval_minutes: int = 5):
        """Run continuously with specified interval."""
        logger.info(f"Starting monitor daemon (interval: {interval_minutes}min)")

        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Error in monitor cycle: {e}")

            logger.info(f"Sleeping {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)


def is_market_hours() -> bool:
    """Check if we're in market hours."""
    now = datetime.now()
    # Market hours: 9:30 AM - 4:00 PM ET, Mon-Fri
    if now.weekday() >= 5:  # Weekend
        return False
    hour = now.hour
    minute = now.minute
    if hour < 9 or (hour == 9 and minute < 30):
        return False
    if hour >= 16:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Monitor daemon that feeds the action queue"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        help="Check interval in minutes (default: 5)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single cycle and exit"
    )
    parser.add_argument(
        "--market-hours-only",
        action="store_true",
        help="Only run during market hours"
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Disable mobile alerts"
    )

    args = parser.parse_args()

    # Set global alert flag
    global ENABLE_MOBILE_ALERTS
    if args.no_alerts:
        ENABLE_MOBILE_ALERTS = False
        logger.info("Mobile alerts disabled")

    daemon = MonitorDaemon()

    if args.once:
        if args.market_hours_only and not is_market_hours():
            logger.info("Outside market hours, skipping")
            return 0
        daemon.run_cycle()
    else:
        if args.market_hours_only:
            while True:
                if is_market_hours():
                    daemon.run_cycle()
                else:
                    logger.info("Outside market hours, sleeping 30 min...")
                    time.sleep(30 * 60)
                    continue
                time.sleep(args.interval * 60)
        else:
            daemon.run_continuous(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
