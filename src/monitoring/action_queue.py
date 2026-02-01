#!/usr/bin/env python3
"""Action Queue - Bridge between background daemons and Claude Code sessions.

This module provides a queue for background processes to signal that Claude
should take action. Claude polls this queue during operator sessions.

Architecture:
```
Background Daemons              Action Queue               Claude Code
─────────────────               ────────────               ───────────
• LiveDaemon          ───►      action_queue.json    ◄───  Polls every N min
• SignpostMonitor     ───►      (priority queue)           Processes items
• DrawdownProtection  ───►                                 Executes trades
• RulesEngine         ───►                                 Clears processed
```

Queue Item Types:
- SIGNPOST_TRIGGERED: A thesis signpost hit
- CONVERGENCE: 3+ signals aligned on a symbol
- DRAWDOWN_ALERT: Portfolio loss threshold hit
- RULE_TRIGGERED: Execution rule fired
- STOP_LOSS: Stop loss level hit
- TAKE_PROFIT: Take profit level hit
- DATA_ALERT: Significant data event (earnings miss, FDA, etc.)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from enum import Enum
import fcntl

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions Claude can take."""
    SIGNPOST_TRIGGERED = "signpost_triggered"
    CONVERGENCE = "convergence"
    DRAWDOWN_ALERT = "drawdown_alert"
    RULE_TRIGGERED = "rule_triggered"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    DATA_ALERT = "data_alert"
    THESIS_REVIEW = "thesis_review"
    POSITION_ALERT = "position_alert"
    REGIME_CHANGE = "regime_change"


class ActionPriority(Enum):
    """Priority levels for actions."""
    CRITICAL = 1   # Execute immediately (stop loss, drawdown)
    HIGH = 2       # Execute soon (signpost, convergence)
    MEDIUM = 3     # Execute when convenient (rule triggered)
    LOW = 4        # Informational (thesis review)


@dataclass
class QueuedAction:
    """An action waiting for Claude to process."""
    action_id: str
    action_type: ActionType
    priority: ActionPriority
    created_at: datetime

    # What to do
    symbol: Optional[str] = None
    suggested_action: str = ""  # BUY, SELL, CLOSE, REVIEW, ALERT
    suggested_size_pct: Optional[float] = None
    thesis_id: Optional[str] = None

    # Context
    reason: str = ""
    source: str = ""  # Which daemon/process created this
    data: dict = field(default_factory=dict)

    # Status
    processed: bool = False
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    result: Optional[str] = None

    # Expiry
    expires_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "symbol": self.symbol,
            "suggested_action": self.suggested_action,
            "suggested_size_pct": self.suggested_size_pct,
            "thesis_id": self.thesis_id,
            "reason": self.reason,
            "source": self.source,
            "data": self.data,
            "processed": self.processed,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "processed_by": self.processed_by,
            "result": self.result,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QueuedAction":
        return cls(
            action_id=d["action_id"],
            action_type=ActionType(d["action_type"]),
            priority=ActionPriority(d["priority"]),
            created_at=datetime.fromisoformat(d["created_at"]),
            symbol=d.get("symbol"),
            suggested_action=d.get("suggested_action", ""),
            suggested_size_pct=d.get("suggested_size_pct"),
            thesis_id=d.get("thesis_id"),
            reason=d.get("reason", ""),
            source=d.get("source", ""),
            data=d.get("data", {}),
            processed=d.get("processed", False),
            processed_at=datetime.fromisoformat(d["processed_at"]) if d.get("processed_at") else None,
            processed_by=d.get("processed_by"),
            result=d.get("result"),
            expires_at=datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None,
        )


class ActionQueue:
    """
    Queue for actions that Claude should process.

    Thread-safe via file locking for concurrent daemon access.
    """

    QUEUE_FILE = Path.home() / "quant_results" / "live" / "action_queue.json"

    def __init__(self):
        self.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load_queue(self) -> list[QueuedAction]:
        """Load queue from file."""
        if not self.QUEUE_FILE.exists():
            return []

        try:
            with open(self.QUEUE_FILE, 'r') as f:
                data = json.load(f)
            return [QueuedAction.from_dict(d) for d in data.get("actions", [])]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error loading queue: {e}")
            return []

    def _save_queue(self, actions: list[QueuedAction]):
        """Save queue to file with locking."""
        data = {
            "updated_at": datetime.now().isoformat(),
            "actions": [a.to_dict() for a in actions],
        }

        # Write with file locking
        with open(self.QUEUE_FILE, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def enqueue(self, action: QueuedAction) -> str:
        """Add an action to the queue."""
        actions = self._load_queue()

        # Check for duplicate (same type + symbol within last hour)
        for existing in actions:
            if (
                not existing.processed
                and existing.action_type == action.action_type
                and existing.symbol == action.symbol
                and (datetime.now() - existing.created_at) < timedelta(hours=1)
            ):
                logger.info(f"Duplicate action ignored: {action.action_type.value} {action.symbol}")
                return existing.action_id

        actions.append(action)
        self._save_queue(actions)
        logger.info(f"Queued action: {action.action_type.value} {action.symbol or ''} [{action.priority.name}]")
        return action.action_id

    def get_pending(self, max_items: int = 10) -> list[QueuedAction]:
        """Get pending actions sorted by priority."""
        actions = self._load_queue()
        now = datetime.now()

        # Filter: not processed, not expired
        pending = [
            a for a in actions
            if not a.processed
            and (a.expires_at is None or a.expires_at > now)
        ]

        # Sort by priority (lower number = higher priority), then by created_at
        pending.sort(key=lambda a: (a.priority.value, a.created_at))

        return pending[:max_items]

    def get_critical(self) -> list[QueuedAction]:
        """Get only CRITICAL priority actions."""
        pending = self.get_pending(max_items=100)
        return [a for a in pending if a.priority == ActionPriority.CRITICAL]

    def mark_processed(
        self,
        action_id: str,
        processed_by: str = "claude",
        result: str = "",
    ):
        """Mark an action as processed."""
        actions = self._load_queue()

        for action in actions:
            if action.action_id == action_id:
                action.processed = True
                action.processed_at = datetime.now()
                action.processed_by = processed_by
                action.result = result
                break

        self._save_queue(actions)

    def clear_processed(self, older_than_hours: int = 24):
        """Remove old processed actions."""
        actions = self._load_queue()
        cutoff = datetime.now() - timedelta(hours=older_than_hours)

        actions = [
            a for a in actions
            if not a.processed or (a.processed_at and a.processed_at > cutoff)
        ]

        self._save_queue(actions)

    def get_summary(self) -> dict:
        """Get queue summary for display."""
        actions = self._load_queue()
        pending = [a for a in actions if not a.processed]

        by_priority = {}
        for p in ActionPriority:
            count = len([a for a in pending if a.priority == p])
            if count > 0:
                by_priority[p.name] = count

        by_type = {}
        for t in ActionType:
            count = len([a for a in pending if a.action_type == t])
            if count > 0:
                by_type[t.value] = count

        return {
            "total_pending": len(pending),
            "by_priority": by_priority,
            "by_type": by_type,
            "oldest": pending[0].created_at.isoformat() if pending else None,
        }


# Convenience functions for daemons to use
def queue_signpost_trigger(
    symbol: str,
    thesis_id: str,
    thesis_name: str,
    signpost_description: str,
    outcome: str,  # bullish or bearish
    suggested_action: str = "REVIEW",
) -> str:
    """Queue a signpost trigger for Claude to process."""
    queue = ActionQueue()
    action = QueuedAction(
        action_id=f"sp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}",
        action_type=ActionType.SIGNPOST_TRIGGERED,
        priority=ActionPriority.HIGH,
        created_at=datetime.now(),
        symbol=symbol,
        suggested_action=suggested_action,
        thesis_id=thesis_id,
        reason=f"{thesis_name}: {signpost_description} ({outcome})",
        source="signpost_monitor",
        data={"outcome": outcome, "signpost": signpost_description},
        expires_at=datetime.now() + timedelta(hours=4),
    )
    return queue.enqueue(action)


def queue_convergence(
    symbol: str,
    direction: str,
    signal_count: int,
    signals: list[str],
    suggested_action: str = "REVIEW",
    suggested_size_pct: float = None,
) -> str:
    """Queue a signal convergence for Claude to process."""
    queue = ActionQueue()

    # Higher signal count = higher priority
    priority = ActionPriority.HIGH if signal_count >= 4 else ActionPriority.MEDIUM

    action = QueuedAction(
        action_id=f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}",
        action_type=ActionType.CONVERGENCE,
        priority=priority,
        created_at=datetime.now(),
        symbol=symbol,
        suggested_action=suggested_action,
        suggested_size_pct=suggested_size_pct,
        reason=f"{signal_count} {direction} signals: {', '.join(signals)}",
        source="smart_alerter",
        data={"direction": direction, "signal_count": signal_count, "signals": signals},
        expires_at=datetime.now() + timedelta(hours=2),
    )
    return queue.enqueue(action)


def queue_stop_loss(
    symbol: str,
    current_loss_pct: float,
    stop_level_pct: float,
    thesis_id: str = None,
) -> str:
    """Queue a stop loss trigger - CRITICAL priority."""
    queue = ActionQueue()
    action = QueuedAction(
        action_id=f"sl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}",
        action_type=ActionType.STOP_LOSS,
        priority=ActionPriority.CRITICAL,
        created_at=datetime.now(),
        symbol=symbol,
        suggested_action="CLOSE",
        thesis_id=thesis_id,
        reason=f"Stop loss hit: {current_loss_pct:.1f}% (limit: {stop_level_pct:.1f}%)",
        source="risk_monitor",
        data={"current_loss_pct": current_loss_pct, "stop_level_pct": stop_level_pct},
        expires_at=datetime.now() + timedelta(hours=1),
    )
    return queue.enqueue(action)


def queue_drawdown_alert(
    drawdown_pct: float,
    level: int,  # 1-5
    action_required: str,
) -> str:
    """Queue a portfolio drawdown alert."""
    queue = ActionQueue()

    priority = ActionPriority.CRITICAL if level >= 4 else ActionPriority.HIGH

    action = QueuedAction(
        action_id=f"dd_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        action_type=ActionType.DRAWDOWN_ALERT,
        priority=priority,
        created_at=datetime.now(),
        suggested_action=action_required,
        reason=f"Portfolio drawdown level {level}: {drawdown_pct:.1f}%",
        source="drawdown_protection",
        data={"drawdown_pct": drawdown_pct, "level": level},
        expires_at=datetime.now() + timedelta(hours=1),
    )
    return queue.enqueue(action)


def queue_rule_triggered(
    rule_id: str,
    rule_name: str,
    symbol: str,
    action: str,
    size_pct: float = None,
    thesis_id: str = None,
) -> str:
    """Queue a rule trigger from rules engine."""
    queue = ActionQueue()
    queued = QueuedAction(
        action_id=f"rule_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}",
        action_type=ActionType.RULE_TRIGGERED,
        priority=ActionPriority.MEDIUM,
        created_at=datetime.now(),
        symbol=symbol,
        suggested_action=action,
        suggested_size_pct=size_pct,
        thesis_id=thesis_id,
        reason=f"Rule '{rule_name}' triggered",
        source="rules_engine",
        data={"rule_id": rule_id, "rule_name": rule_name},
        expires_at=datetime.now() + timedelta(hours=4),
    )
    return queue.enqueue(queued)


# Singleton
_queue: Optional[ActionQueue] = None


def get_action_queue() -> ActionQueue:
    """Get global action queue instance."""
    global _queue
    if _queue is None:
        _queue = ActionQueue()
    return _queue
