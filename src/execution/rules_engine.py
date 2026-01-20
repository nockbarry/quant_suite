#!/usr/bin/env python3
"""Execution Rules Engine - Rules-based trade execution with human oversight.

Defines rules for automated execution (pre-approved) and queued execution
(needs human confirmation).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ApprovalType(Enum):
    AUTO = "auto"        # Pre-approved, execute immediately
    QUEUE = "queue"      # Queue for human review
    NOTIFY = "notify"    # Execute but notify human
    BLOCK = "block"      # Never auto-execute


class TradeAction(Enum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


@dataclass
class ExecutionRule:
    """A rule for automated trade execution."""
    rule_id: str
    name: str
    description: str
    trigger_condition: str  # Python expression to evaluate
    action: TradeAction
    symbol_source: str      # "trigger", "config", or specific symbol
    size_type: str          # "full", "half", "fixed", "percent"
    size_value: float       # Percent of portfolio or fixed shares
    approval: ApprovalType
    priority: int = 5       # 1-10, higher = more important
    enabled: bool = True
    cooldown_minutes: int = 60  # Don't re-trigger within this window
    last_triggered: Optional[datetime] = None

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "trigger_condition": self.trigger_condition,
            "action": self.action.value,
            "symbol_source": self.symbol_source,
            "size_type": self.size_type,
            "size_value": self.size_value,
            "approval": self.approval.value,
            "priority": self.priority,
            "enabled": self.enabled,
            "cooldown_minutes": self.cooldown_minutes,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
        }


@dataclass
class QueuedTrade:
    """A trade queued for human review."""
    trade_id: str
    rule_id: str
    symbol: str
    action: TradeAction
    quantity: int
    reason: str
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # pending, approved, rejected, expired, executed
    executed_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "trade_id": self.trade_id,
            "rule_id": self.rule_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "quantity": self.quantity,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "metadata": self.metadata,
        }


# Default execution rules
DEFAULT_RULES = [
    # Signpost exits - AUTO (pre-approved by creating signpost)
    ExecutionRule(
        rule_id="signpost_exit",
        name="Signpost Exit",
        description="Exit position when signpost level is breached",
        trigger_condition="signpost.triggered and signpost.action.startswith('EXIT')",
        action=TradeAction.CLOSE,
        symbol_source="trigger",
        size_type="full",
        size_value=100,
        approval=ApprovalType.AUTO,
        priority=10,
    ),

    # VIX mean reversion - QUEUE (needs confirmation)
    ExecutionRule(
        rule_id="vix_mean_reversion",
        name="VIX Mean Reversion Entry",
        description="Buy SPY when VIX spikes above 30",
        trigger_condition="vix > 30 and vix_structure == 'backwardation'",
        action=TradeAction.BUY,
        symbol_source="SPY",
        size_type="percent",
        size_value=5.0,
        approval=ApprovalType.QUEUE,
        priority=8,
    ),

    # Thesis add on oversold - QUEUE
    ExecutionRule(
        rule_id="thesis_oversold_add",
        name="Add to Thesis on Oversold",
        description="Add to position when thesis stock is oversold but thesis valid",
        trigger_condition="rsi_14 < 30 and thesis.conviction > 60 and position_size < thesis.target_size",
        action=TradeAction.BUY,
        symbol_source="trigger",
        size_type="percent",
        size_value=2.0,
        approval=ApprovalType.QUEUE,
        priority=6,
    ),

    # Concentration limit - NOTIFY
    ExecutionRule(
        rule_id="concentration_trim",
        name="Trim Over-Concentrated Position",
        description="Trim position that exceeds 20% of portfolio",
        trigger_condition="position_pct > 20",
        action=TradeAction.SELL,
        symbol_source="trigger",
        size_type="percent",
        size_value=5.0,  # Trim 5% at a time
        approval=ApprovalType.NOTIFY,
        priority=7,
    ),

    # Stop loss - AUTO
    ExecutionRule(
        rule_id="stop_loss",
        name="Stop Loss",
        description="Exit position at stop loss level",
        trigger_condition="position_pnl_pct < -15",
        action=TradeAction.CLOSE,
        symbol_source="trigger",
        size_type="full",
        size_value=100,
        approval=ApprovalType.AUTO,
        priority=10,
    ),

    # Drawdown protection - NOTIFY
    ExecutionRule(
        rule_id="drawdown_protection",
        name="Portfolio Drawdown Protection",
        description="Reduce exposure when portfolio drawdown exceeds 10%",
        trigger_condition="portfolio_drawdown_pct > 10",
        action=TradeAction.SELL,
        symbol_source="largest_position",
        size_type="percent",
        size_value=10.0,
        approval=ApprovalType.NOTIFY,
        priority=9,
    ),

    # Gold breakout - QUEUE
    ExecutionRule(
        rule_id="gold_breakout",
        name="Gold Thesis Confirmation",
        description="Add to gold when GDX breaks above $103",
        trigger_condition="symbol == 'GDX' and price > 103 and not triggered_today",
        action=TradeAction.BUY,
        symbol_source="GDX",
        size_type="percent",
        size_value=2.0,
        approval=ApprovalType.QUEUE,
        priority=6,
    ),
]


class RulesEngine:
    """Execute trades based on predefined rules."""

    def __init__(self, rules_dir: Optional[Path] = None):
        self.rules_dir = rules_dir or Path.home() / "quant_results" / "rules"
        self.rules_dir.mkdir(parents=True, exist_ok=True)

        self.rules: list[ExecutionRule] = []
        self.trade_queue: list[QueuedTrade] = []
        self.execution_log: list[dict] = []

        self._load_rules()
        self._load_queue()

    def _load_rules(self):
        """Load rules from file or use defaults."""
        rules_file = self.rules_dir / "execution_rules.json"

        if rules_file.exists():
            with open(rules_file) as f:
                data = json.load(f)
            self.rules = [
                ExecutionRule(
                    rule_id=r["rule_id"],
                    name=r["name"],
                    description=r["description"],
                    trigger_condition=r["trigger_condition"],
                    action=TradeAction(r["action"]),
                    symbol_source=r["symbol_source"],
                    size_type=r["size_type"],
                    size_value=r["size_value"],
                    approval=ApprovalType(r["approval"]),
                    priority=r.get("priority", 5),
                    enabled=r.get("enabled", True),
                    cooldown_minutes=r.get("cooldown_minutes", 60),
                )
                for r in data
            ]
        else:
            self.rules = DEFAULT_RULES.copy()
            self._save_rules()

    def _save_rules(self):
        """Save rules to file."""
        rules_file = self.rules_dir / "execution_rules.json"
        with open(rules_file, "w") as f:
            json.dump([r.to_dict() for r in self.rules], f, indent=2)

    def _load_queue(self):
        """Load queued trades from file."""
        queue_file = self.rules_dir / "trade_queue.json"

        if queue_file.exists():
            with open(queue_file) as f:
                data = json.load(f)
            self.trade_queue = [
                QueuedTrade(
                    trade_id=t["trade_id"],
                    rule_id=t["rule_id"],
                    symbol=t["symbol"],
                    action=TradeAction(t["action"]),
                    quantity=t["quantity"],
                    reason=t["reason"],
                    created_at=datetime.fromisoformat(t["created_at"]),
                    expires_at=datetime.fromisoformat(t["expires_at"]),
                    status=t["status"],
                    metadata=t.get("metadata", {}),
                )
                for t in data
            ]

    def _save_queue(self):
        """Save queued trades to file."""
        queue_file = self.rules_dir / "trade_queue.json"
        with open(queue_file, "w") as f:
            json.dump([t.to_dict() for t in self.trade_queue], f, indent=2)

    def add_rule(self, rule: ExecutionRule):
        """Add a new execution rule."""
        self.rules.append(rule)
        self._save_rules()

    def update_rule(self, rule_id: str, **kwargs):
        """Update an existing rule."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                for key, value in kwargs.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                break
        self._save_rules()

    def disable_rule(self, rule_id: str):
        """Disable a rule."""
        self.update_rule(rule_id, enabled=False)

    def enable_rule(self, rule_id: str):
        """Enable a rule."""
        self.update_rule(rule_id, enabled=True)

    def evaluate_condition(self, condition: str, context: dict) -> bool:
        """Safely evaluate a rule condition."""
        try:
            # Create safe evaluation context
            safe_context = {
                "abs": abs,
                "min": min,
                "max": max,
                "len": len,
                **context,
            }
            return eval(condition, {"__builtins__": {}}, safe_context)
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def check_cooldown(self, rule: ExecutionRule) -> bool:
        """Check if rule is within cooldown period."""
        if rule.last_triggered is None:
            return True
        cooldown_end = rule.last_triggered + timedelta(minutes=rule.cooldown_minutes)
        return datetime.now() > cooldown_end

    async def evaluate_rules(self, context: dict) -> list[dict]:
        """Evaluate all rules against current context."""
        triggered = []

        for rule in self.rules:
            if not rule.enabled:
                continue

            if not self.check_cooldown(rule):
                continue

            if self.evaluate_condition(rule.trigger_condition, context):
                triggered.append({
                    "rule": rule,
                    "context": context,
                })

        # Sort by priority (highest first)
        triggered.sort(key=lambda x: x["rule"].priority, reverse=True)

        return triggered

    async def process_triggered_rules(self, triggered: list[dict],
                                      execute_fn: Optional[Callable] = None) -> list[dict]:
        """Process triggered rules based on approval type."""
        results = []

        for item in triggered:
            rule = item["rule"]
            context = item["context"]

            # Determine symbol
            if rule.symbol_source == "trigger":
                symbol = context.get("symbol", context.get("signpost", {}).get("symbol"))
            elif rule.symbol_source == "largest_position":
                symbol = context.get("largest_position_symbol")
            else:
                symbol = rule.symbol_source

            if not symbol:
                logger.warning(f"Could not determine symbol for rule {rule.rule_id}")
                continue

            # Calculate quantity
            if rule.size_type == "full":
                quantity = context.get("position_qty", 0)
            elif rule.size_type == "half":
                quantity = context.get("position_qty", 0) // 2
            elif rule.size_type == "percent":
                portfolio_value = context.get("portfolio_value", 100000)
                price = context.get("price", 100)
                quantity = int((portfolio_value * rule.size_value / 100) / price)
            else:  # fixed
                quantity = int(rule.size_value)

            if quantity <= 0:
                continue

            trade_info = {
                "rule_id": rule.rule_id,
                "symbol": symbol,
                "action": rule.action,
                "quantity": quantity,
                "reason": rule.description,
            }

            if rule.approval == ApprovalType.AUTO:
                # Execute immediately
                if execute_fn:
                    result = await execute_fn(trade_info)
                    trade_info["executed"] = True
                    trade_info["result"] = result
                else:
                    trade_info["would_execute"] = True

                # Update last triggered
                rule.last_triggered = datetime.now()
                self._save_rules()

            elif rule.approval == ApprovalType.QUEUE:
                # Add to queue for human review
                queued = QueuedTrade(
                    trade_id=f"q_{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    rule_id=rule.rule_id,
                    symbol=symbol,
                    action=rule.action,
                    quantity=quantity,
                    reason=rule.description,
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=4),
                    metadata={"context": {k: str(v)[:100] for k, v in context.items()}},
                )
                self.trade_queue.append(queued)
                self._save_queue()
                trade_info["queued"] = True
                trade_info["trade_id"] = queued.trade_id

            elif rule.approval == ApprovalType.NOTIFY:
                # Execute but notify
                if execute_fn:
                    result = await execute_fn(trade_info)
                    trade_info["executed"] = True
                    trade_info["result"] = result
                    trade_info["notification_sent"] = True

                rule.last_triggered = datetime.now()
                self._save_rules()

            results.append(trade_info)

        return results

    def get_pending_trades(self) -> list[QueuedTrade]:
        """Get trades pending human approval."""
        now = datetime.now()
        pending = []

        for trade in self.trade_queue:
            if trade.status == "pending":
                if trade.expires_at < now:
                    trade.status = "expired"
                else:
                    pending.append(trade)

        self._save_queue()
        return pending

    async def approve_trade(self, trade_id: str, execute_fn: Optional[Callable] = None) -> dict:
        """Approve and execute a queued trade."""
        for trade in self.trade_queue:
            if trade.trade_id == trade_id and trade.status == "pending":
                trade.status = "approved"

                if execute_fn:
                    result = await execute_fn({
                        "symbol": trade.symbol,
                        "action": trade.action,
                        "quantity": trade.quantity,
                    })
                    trade.status = "executed"
                    trade.executed_at = datetime.now()
                    self._save_queue()
                    return {"success": True, "result": result}

                self._save_queue()
                return {"success": True, "status": "approved"}

        return {"success": False, "error": "Trade not found or not pending"}

    def reject_trade(self, trade_id: str, reason: str = "") -> dict:
        """Reject a queued trade."""
        for trade in self.trade_queue:
            if trade.trade_id == trade_id and trade.status == "pending":
                trade.status = "rejected"
                trade.metadata["rejection_reason"] = reason
                self._save_queue()
                return {"success": True}

        return {"success": False, "error": "Trade not found or not pending"}

    def get_rules_summary(self) -> str:
        """Get human-readable rules summary."""
        lines = ["Execution Rules:", "=" * 50]

        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            status = "ENABLED" if rule.enabled else "DISABLED"
            lines.append(f"\n[{rule.priority}] {rule.name} ({status})")
            lines.append(f"    {rule.description}")
            lines.append(f"    Action: {rule.action.value.upper()}")
            lines.append(f"    Approval: {rule.approval.value}")
            lines.append(f"    Condition: {rule.trigger_condition[:50]}...")

        return "\n".join(lines)


async def main():
    """Test rules engine."""
    engine = RulesEngine()

    print(engine.get_rules_summary())

    # Test rule evaluation
    context = {
        "symbol": "SPY",
        "price": 682.0,
        "vix": 32,
        "vix_structure": "backwardation",
        "position_qty": 100,
        "portfolio_value": 100000,
        "signpost": {
            "symbol": "CEG",
            "triggered": True,
            "action": "EXIT CEG position",
        },
    }

    triggered = await engine.evaluate_rules(context)
    print(f"\nTriggered rules: {len(triggered)}")

    for item in triggered:
        print(f"  - {item['rule'].name} ({item['rule'].approval.value})")

    # Process without actual execution
    results = await engine.process_triggered_rules(triggered)
    print(f"\nResults: {json.dumps(results, indent=2, default=str)}")

    # Check queue
    pending = engine.get_pending_trades()
    print(f"\nPending trades: {len(pending)}")


if __name__ == "__main__":
    asyncio.run(main())
