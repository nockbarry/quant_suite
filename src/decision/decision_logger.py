"""
Decision Logger for tracking LLM trading decisions and outcomes.

Provides:
- Recording decisions with full context
- Tracking outcomes (P&L, accuracy of reasoning)
- Learning loop feedback for improvement
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum
import json
import uuid

from src.core.paths import paths


class Action(str, Enum):
    """Trading action types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    ADD = "ADD"  # Add to position
    TRIM = "TRIM"  # Reduce position


class DecisionStatus(str, Enum):
    """Decision lifecycle status."""
    PENDING = "pending"  # Decision made, not yet executed
    EXECUTED = "executed"  # Order submitted
    FILLED = "filled"  # Order filled
    REJECTED = "rejected"  # Order rejected
    CANCELLED = "cancelled"  # Decision cancelled
    CLOSED = "closed"  # Position closed, can evaluate outcome


@dataclass
class TradingDecision:
    """A trading decision made by the LLM decision engine."""

    # Core decision
    id: str
    timestamp: datetime
    symbol: str
    action: Action
    confidence: float  # 0-1

    # Position details
    size_pct: float  # % of portfolio
    limit_price: Optional[float]
    stop_loss_pct: float
    take_profit_pct: float
    expected_hold_days: int

    # Reasoning
    reasoning: str
    key_factors: list[str]
    risks: list[str]

    # Context at decision time
    context: dict  # Snapshot of market state, briefing summary, etc.

    # Tracking
    status: DecisionStatus = DecisionStatus.PENDING
    execution_price: Optional[float] = None
    execution_time: Optional[datetime] = None

    # Outcome (filled after position closes)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    actual_hold_days: Optional[int] = None
    realized_pnl: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    outcome_notes: Optional[str] = None

    # Thesis and learning integration (new fields)
    thesis_id: Optional[str] = None  # Link to investment thesis
    pre_mortem: Optional[str] = None  # "It's 30 days later and I lost. What happened?"
    adversarial_notes: Optional[str] = None  # What the adversary said
    learning_extracted: bool = False  # Has learning been extracted from this?

    # Strategy tracking
    setup_type: str = ""  # e.g., "mean_reversion", "momentum", "breakout", "thesis_driven"

    # Signal provenance
    signal_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action.value,
            "confidence": self.confidence,
            "size_pct": self.size_pct,
            "limit_price": self.limit_price,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "expected_hold_days": self.expected_hold_days,
            "reasoning": self.reasoning,
            "key_factors": self.key_factors,
            "risks": self.risks,
            "context": self.context,
            "status": self.status.value,
            "execution_price": self.execution_price,
            "execution_time": self.execution_time.isoformat() if self.execution_time else None,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "actual_hold_days": self.actual_hold_days,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "outcome_notes": self.outcome_notes,
            "thesis_id": self.thesis_id,
            "pre_mortem": self.pre_mortem,
            "adversarial_notes": self.adversarial_notes,
            "learning_extracted": self.learning_extracted,
            "setup_type": self.setup_type,
            "signal_ids": self.signal_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradingDecision":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            symbol=data["symbol"],
            action=Action(data["action"]),
            confidence=data["confidence"],
            size_pct=data["size_pct"],
            limit_price=data.get("limit_price"),
            stop_loss_pct=data["stop_loss_pct"],
            take_profit_pct=data["take_profit_pct"],
            expected_hold_days=data["expected_hold_days"],
            reasoning=data["reasoning"],
            key_factors=data["key_factors"],
            risks=data["risks"],
            context=data["context"],
            status=DecisionStatus(data.get("status", "pending")),
            execution_price=data.get("execution_price"),
            execution_time=datetime.fromisoformat(data["execution_time"]) if data.get("execution_time") else None,
            exit_price=data.get("exit_price"),
            exit_time=datetime.fromisoformat(data["exit_time"]) if data.get("exit_time") else None,
            actual_hold_days=data.get("actual_hold_days"),
            realized_pnl=data.get("realized_pnl"),
            realized_pnl_pct=data.get("realized_pnl_pct"),
            outcome_notes=data.get("outcome_notes"),
            thesis_id=data.get("thesis_id"),
            pre_mortem=data.get("pre_mortem"),
            adversarial_notes=data.get("adversarial_notes"),
            learning_extracted=data.get("learning_extracted", False),
            setup_type=data.get("setup_type", ""),
            signal_ids=data.get("signal_ids", []),
        )


class DecisionLogger:
    """
    Logs and tracks trading decisions for learning.

    Maintains:
    - Decision history with full context
    - Outcome tracking for closed positions
    - Performance analytics by reasoning pattern
    """

    def __init__(
        self,
        decisions_dir: str | Path | None = None,
    ):
        self.decisions_dir = Path(decisions_dir) if decisions_dir else paths.decisions
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.daily_file: Optional[Path] = None
        self._ensure_daily_file()

    def _ensure_daily_file(self) -> Path:
        """Ensure today's decision file exists."""
        today = datetime.now().strftime("%Y-%m-%d")
        self.daily_file = self.decisions_dir / f"decisions_{today}.json"

        if not self.daily_file.exists():
            with open(self.daily_file, "w") as f:
                json.dump({"date": today, "decisions": []}, f, indent=2)

        return self.daily_file

    def log_decision(self, decision: TradingDecision) -> str:
        """Log a new trading decision and sync to DB."""
        self._ensure_daily_file()

        with open(self.daily_file, "r") as f:
            data = json.load(f)

        # Handle both list and dict formats
        if isinstance(data, list):
            data = {"date": datetime.now().strftime("%Y-%m-%d"), "decisions": data}
        data["decisions"].append(decision.to_dict())

        with open(self.daily_file, "w") as f:
            json.dump(data, f, indent=2)

        # Sync to DB
        try:
            from src.db.write_api import athena_db
            athena_db.upsert_decision(decision.to_dict())
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"DB sync failed for decision {decision.id}: {e}")

        # Index the daily decisions file as a document
        try:
            from src.db.write_api import athena_db
            athena_db.save_document(
                doc_type="decision",
                title=f"Decision: {decision.action.value} {decision.symbol} ({decision.confidence:.0%})",
                file_path=str(self.daily_file),
                source="decision_engine",
                decision_id=decision.id,
                thesis_id=decision.thesis_id,
                symbols=[decision.symbol],
                tags=[decision.action.value.lower(), decision.setup_type or "unclassified"],
            )
        except Exception:
            pass

        # Emit decision_created event
        try:
            from src.core.events import emit
            emit(
                "decision_created",
                source="decision_engine",
                symbol=decision.symbol,
                title=f"Decision: {decision.action.value} {decision.symbol} @ {decision.confidence:.0%}",
                detail={"action": decision.action.value, "confidence": decision.confidence,
                        "size_pct": decision.size_pct, "setup_type": decision.setup_type},
                decision_id=decision.id,
                thesis_id=decision.thesis_id,
                signal_ids=decision.signal_ids,
            )
        except Exception:
            pass

        return decision.id

    def update_decision(self, decision_id: str, updates: dict) -> bool:
        """Update an existing decision (e.g., mark as executed, add outcome)."""
        self._ensure_daily_file()

        with open(self.daily_file, "r") as f:
            data = json.load(f)

        for decision in data["decisions"]:
            if decision["id"] == decision_id:
                decision.update(updates)
                with open(self.daily_file, "w") as f:
                    json.dump(data, f, indent=2)

                # Sync to DB
                try:
                    from src.db.write_api import athena_db
                    athena_db.upsert_decision(decision)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"DB sync failed for decision update {decision_id}: {e}")

                # Emit lifecycle events
                try:
                    from src.core.events import emit
                    new_status = updates.get("status", "")
                    symbol = decision.get("symbol", "")
                    if new_status == "executed":
                        emit(
                            "trade_executed",
                            source="decision_engine",
                            symbol=symbol,
                            title=f"Trade executed: {decision.get('action', '')} {symbol} @ ${updates.get('execution_price', '?')}",
                            detail={"execution_price": updates.get("execution_price")},
                            decision_id=decision_id,
                        )
                    elif new_status == "closed" and updates.get("realized_pnl") is not None:
                        emit(
                            "trade_outcome",
                            source="decision_engine",
                            symbol=symbol,
                            title=f"Trade closed: {symbol} P&L ${updates.get('realized_pnl', 0):+.2f}",
                            detail={"exit_price": updates.get("exit_price"),
                                    "realized_pnl": updates.get("realized_pnl"),
                                    "realized_pnl_pct": updates.get("realized_pnl_pct")},
                            decision_id=decision_id,
                            signal_ids=decision.get("signal_ids", []),
                            pnl=updates.get("realized_pnl"),
                            pnl_pct=updates.get("realized_pnl_pct"),
                        )
                except Exception:
                    pass

                return True

        return False

    def get_today_decisions(self) -> list[TradingDecision]:
        """Get all decisions made today."""
        self._ensure_daily_file()

        with open(self.daily_file, "r") as f:
            data = json.load(f)

        return [TradingDecision.from_dict(d) for d in data["decisions"]]

    def get_pending_decisions(self) -> list[TradingDecision]:
        """Get decisions that haven't been executed yet."""
        decisions = self.get_today_decisions()
        return [d for d in decisions if d.status == DecisionStatus.PENDING]

    def get_decisions_by_thesis(self, thesis_id: str, days: int = 30) -> list[TradingDecision]:
        """Get all decisions linked to a specific thesis.

        Args:
            thesis_id: Thesis ID to search for
            days: Number of days to look back

        Returns:
            List of TradingDecisions linked to the thesis, sorted by date descending
        """
        decisions = []

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = self.decisions_dir / f"decisions_{date}.json"

            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    for d in data["decisions"]:
                        if d.get("thesis_id") == thesis_id:
                            decisions.append(TradingDecision.from_dict(d))
                except (json.JSONDecodeError, KeyError):
                    continue

        return decisions

    def get_decisions_by_symbol(self, symbol: str, days: int = 30) -> list[TradingDecision]:
        """Get all decisions for a specific symbol.

        Args:
            symbol: Stock symbol to search for
            days: Number of days to look back

        Returns:
            List of TradingDecisions for the symbol, sorted by date descending
        """
        decisions = []

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = self.decisions_dir / f"decisions_{date}.json"

            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    for d in data["decisions"]:
                        if d.get("symbol") == symbol:
                            decisions.append(TradingDecision.from_dict(d))
                except (json.JSONDecodeError, KeyError):
                    continue

        return decisions

    def get_decision(self, decision_id: str) -> Optional[TradingDecision]:
        """Get a specific decision by ID."""
        decisions = self.get_today_decisions()
        for d in decisions:
            if d.id == decision_id:
                return d
        return None

    def record_execution(
        self,
        decision_id: str,
        execution_price: float,
        execution_time: Optional[datetime] = None,
    ) -> bool:
        """Record that a decision was executed."""
        return self.update_decision(decision_id, {
            "status": DecisionStatus.EXECUTED.value,
            "execution_price": execution_price,
            "execution_time": (execution_time or datetime.now()).isoformat(),
        })

    def record_outcome(
        self,
        decision_id: str,
        exit_price: float,
        exit_time: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Record the outcome of a closed position."""
        decision = self.get_decision(decision_id)
        if not decision or not decision.execution_price:
            return False

        entry = decision.execution_price
        pnl = exit_price - entry
        pnl_pct = (pnl / entry) * 100

        exit_dt = exit_time or datetime.now()
        hold_days = (exit_dt - decision.execution_time).days if decision.execution_time else 0

        return self.update_decision(decision_id, {
            "status": DecisionStatus.CLOSED.value,
            "exit_price": exit_price,
            "exit_time": exit_dt.isoformat(),
            "actual_hold_days": hold_days,
            "realized_pnl": pnl,
            "realized_pnl_pct": pnl_pct,
            "outcome_notes": notes,
        })

    def get_performance_summary(self, days: int = 30) -> dict:
        """
        Get performance summary across recent decisions.

        Returns:
            Summary with win rate, avg return, accuracy metrics
        """
        all_decisions = []

        # Load decisions from recent days
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = self.decisions_dir / f"decisions_{date}.json"

            if filepath.exists():
                with open(filepath, "r") as f:
                    data = json.load(f)
                    all_decisions.extend(data["decisions"])

        # Filter to closed decisions
        closed = [d for d in all_decisions if d.get("status") == "closed"]

        if not closed:
            return {
                "total_decisions": len(all_decisions),
                "closed_decisions": 0,
                "win_rate": None,
                "avg_return_pct": None,
                "total_pnl": None,
            }

        # Calculate metrics
        wins = [d for d in closed if d.get("realized_pnl_pct", 0) > 0]
        returns = [d.get("realized_pnl_pct", 0) for d in closed]
        total_pnl = sum(d.get("realized_pnl", 0) for d in closed)

        # Accuracy of reasoning (was high confidence correct?)
        high_conf = [d for d in closed if d.get("confidence", 0) >= 0.7]
        high_conf_wins = [d for d in high_conf if d.get("realized_pnl_pct", 0) > 0]

        return {
            "total_decisions": len(all_decisions),
            "closed_decisions": len(closed),
            "win_rate": len(wins) / len(closed) if closed else None,
            "avg_return_pct": sum(returns) / len(returns) if returns else None,
            "total_pnl": total_pnl,
            "high_confidence_accuracy": len(high_conf_wins) / len(high_conf) if high_conf else None,
            "by_action": self._group_by_action(closed),
        }

    def _group_by_action(self, decisions: list[dict]) -> dict:
        """Group performance by action type."""
        by_action = {}
        for d in decisions:
            action = d.get("action", "UNKNOWN")
            if action not in by_action:
                by_action[action] = {"count": 0, "wins": 0, "total_pnl": 0}

            by_action[action]["count"] += 1
            if d.get("realized_pnl_pct", 0) > 0:
                by_action[action]["wins"] += 1
            by_action[action]["total_pnl"] += d.get("realized_pnl", 0)

        return by_action

    def get_performance_by_setup_type(self, days: int = 30) -> dict:
        """
        Get performance breakdown by setup type.

        Returns:
            Dict with setup type -> {count, wins, win_rate, total_pnl, avg_pnl}
        """
        all_decisions = []

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = self.decisions_dir / f"decisions_{date}.json"

            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        all_decisions.extend(data["decisions"])
                except (json.JSONDecodeError, KeyError):
                    continue

        # Filter to closed decisions
        closed = [d for d in all_decisions if d.get("status") == "closed"]

        by_setup = {}
        for d in closed:
            setup = d.get("setup_type", "unknown") or "unknown"
            if setup not in by_setup:
                by_setup[setup] = {"count": 0, "wins": 0, "total_pnl": 0.0, "pnl_list": []}

            by_setup[setup]["count"] += 1
            pnl = d.get("realized_pnl", 0) or 0
            by_setup[setup]["total_pnl"] += pnl
            by_setup[setup]["pnl_list"].append(pnl)

            if d.get("realized_pnl_pct", 0) > 0:
                by_setup[setup]["wins"] += 1

        # Calculate derived metrics
        for setup, stats in by_setup.items():
            stats["win_rate"] = stats["wins"] / stats["count"] if stats["count"] > 0 else 0
            stats["avg_pnl"] = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0
            del stats["pnl_list"]  # Remove internal tracking list

        return by_setup


def create_decision(
    symbol: str,
    action: Action,
    confidence: float,
    size_pct: float,
    reasoning: str,
    key_factors: list[str],
    risks: list[str],
    context: dict,
    stop_loss_pct: float = 5.0,
    take_profit_pct: float = 15.0,
    expected_hold_days: int = 5,
    limit_price: Optional[float] = None,
    thesis_id: Optional[str] = None,
    pre_mortem: Optional[str] = None,
    adversarial_notes: Optional[str] = None,
    setup_type: str = "",
    signal_ids: Optional[list[str]] = None,
) -> TradingDecision:
    """
    Factory function to create a new trading decision.

    Args:
        setup_type: Strategy/setup type, e.g., "mean_reversion", "momentum",
                   "breakout", "thesis_driven", "earnings", "technical"

    Example:
        decision = create_decision(
            symbol="SLB",
            action=Action.BUY,
            confidence=0.75,
            size_pct=10.0,
            reasoning="Venezuela reconstruction thesis confirmed...",
            key_factors=["Contract announcements", "Pre-market strength"],
            risks=["Geopolitical uncertainty", "Oil price volatility"],
            context={"briefing_date": "2026-01-06", "market_sentiment": "bullish"},
            setup_type="thesis_driven",
        )
    """
    # Enrich context with session context (web searches, news, market snapshot, etc.)
    enriched_context = {**context}
    try:
        from src.context.session_context import SessionContext
        from src.context.market_snapshot import capture_market_snapshot

        session_ctx = SessionContext.get()

        # Load shared context from other sessions (operator, briefing) if this
        # process has no events yet (common in autonomous trade-decision sessions)
        if session_ctx.event_count() == 0:
            session_ctx.load_shared_context(hours=4.0)

        if session_ctx.event_count() > 0:
            enriched_context.update(session_ctx.snapshot_for_decision(symbol))

        # Always capture market snapshot at decision time
        if "market_snapshot" not in enriched_context or not enriched_context["market_snapshot"]:
            enriched_context["market_snapshot"] = capture_market_snapshot()
    except Exception:
        pass  # Don't block decision creation if context enrichment fails

    # Auto-run adversarial analysis if not provided
    if adversarial_notes is None:
        try:
            from src.decision.adversary import AdversarialAgent
            adversary = AdversarialAgent()
            adv_analysis = adversary.challenge(
                symbol=symbol,
                proposed_action=action.value,
                reasoning=reasoning,
                confidence=confidence,
                context=enriched_context,
                setup_type=setup_type,
            )
            adversarial_notes = adv_analysis.summary
        except Exception:
            pass

    # Auto-generate pre-mortem if not provided
    if pre_mortem is None:
        try:
            from src.decision.adversary import AdversarialAgent
            adversary = AdversarialAgent()
            pre_mortem = adversary._generate_pre_mortem(symbol, action.value, enriched_context)
        except Exception:
            pass

    decision = TradingDecision(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(),
        symbol=symbol,
        action=action,
        confidence=confidence,
        size_pct=size_pct,
        limit_price=limit_price,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        expected_hold_days=expected_hold_days,
        reasoning=reasoning,
        key_factors=key_factors,
        risks=risks,
        context=enriched_context,
        thesis_id=thesis_id,
        pre_mortem=pre_mortem,
        adversarial_notes=adversarial_notes,
        setup_type=setup_type or context.get("setup_type", ""),
        signal_ids=signal_ids or [],
    )

    # Persist context events as ProcessEvent records linked to this decision
    try:
        from src.context.session_context import SessionContext
        SessionContext.get().persist_to_db(decision_id=decision.id, symbol=symbol)
    except Exception:
        pass

    # Auto-create direction prediction for the intelligence feedback loop
    try:
        from src.db.write_api import athena_db
        from src.intelligence.setup_types import normalize_setup_type

        if action in (Action.BUY, Action.ADD):
            pred_direction = "bullish"
        elif action in (Action.SELL, Action.CLOSE, Action.TRIM):
            pred_direction = "bearish"
        else:
            pred_direction = None

        if pred_direction:
            norm_setup = normalize_setup_type(setup_type or "thesis_driven")
            hold_days = expected_hold_days or 10
            athena_db.save_prediction({
                "decision_id": decision.id,
                "thesis_id": thesis_id,
                "symbol": symbol,
                "prediction_type": "direction",
                "direction": pred_direction,
                "target_value": limit_price,
                "target_description": f"{'Bullish' if pred_direction == 'bullish' else 'Bearish'} on {symbol} ({action.value})",
                "confidence": confidence,
                "timeframe_days": hold_days,
                "reasoning_category": norm_setup,
                "setup_type": norm_setup,
                "key_reasoning": (reasoning or "")[:500],
                "created": decision.timestamp.isoformat(),
            })
    except Exception:
        pass  # Never block decision creation

    return decision
