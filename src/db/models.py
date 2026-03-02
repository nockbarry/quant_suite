"""SQLAlchemy models for the complete Athena provenance chain.

Models mirror existing dataclasses (Thesis, CompanyBrief, etc.) while adding
new provenance tables that close gaps in the decision lineage.

The lineage chain:
    DATA SOURCE → SIGNAL → CONVERGENCE → DECISION CONTEXT →
    LLM REASONING → ADVERSARIAL CHALLENGE → DECISION →
    EXECUTION → OUTCOME → LEARNING
"""

import json
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _safe_json_loads(text: str | None, default=None):
    """Safely parse JSON, returning default on failure."""
    try:
        return json.loads(text) if text else (default if default is not None else text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else text


# ---------------------------------------------------------------------------
# Core knowledge tables (mirror existing YAML/JSON dataclasses)
# ---------------------------------------------------------------------------


class Company(Base):
    """Mirrors CompanyBrief dataclass from src/knowledge/base.py."""

    __tablename__ = "companies"

    symbol = Column(String(10), primary_key=True)
    name = Column(String(200), nullable=False)
    updated = Column(DateTime, default=datetime.utcnow)

    # Business understanding
    business_model = Column(Text, default="")
    moat = Column(Text, default="")
    earnings_quality = Column(Text, default="")
    management_view = Column(Text, default="")
    sector = Column(String(100), default="")
    market_cap_tier = Column(String(20), default="")

    # Key dynamics (JSON lists)
    key_risks = Column(Text, default="[]")  # JSON list
    key_catalysts = Column(Text, default="[]")  # JSON list
    sector_position = Column(Text, default="")

    # Trading notes
    typical_volatility = Column(Text, default="")
    earnings_behavior = Column(Text, default="")
    correlation_notes = Column(Text, default="")
    best_setups = Column(Text, default="")
    avoid_when = Column(Text, default="")

    # Valuation
    valuation_notes = Column(Text, default="")
    historical_range = Column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "updated": self.updated.isoformat() if self.updated else None,
            "business_model": self.business_model,
            "moat": self.moat,
            "earnings_quality": self.earnings_quality,
            "management_view": self.management_view,
            "sector": self.sector,
            "market_cap_tier": self.market_cap_tier,
            "key_risks": json.loads(self.key_risks or "[]"),
            "key_catalysts": json.loads(self.key_catalysts or "[]"),
            "sector_position": self.sector_position,
            "typical_volatility": self.typical_volatility,
            "earnings_behavior": self.earnings_behavior,
            "correlation_notes": self.correlation_notes,
            "best_setups": self.best_setups,
            "avoid_when": self.avoid_when,
            "valuation_notes": self.valuation_notes,
            "historical_range": self.historical_range,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        d = dict(data)
        if isinstance(d.get("updated"), str):
            d["updated"] = datetime.fromisoformat(d["updated"])
        for field in ("key_risks", "key_catalysts"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        return cls(**d)


class Sector(Base):
    """Mirrors SectorContext dataclass from src/knowledge/base.py."""

    __tablename__ = "sectors"

    sector = Column(String(100), primary_key=True)
    updated = Column(DateTime, default=datetime.utcnow)

    current_cycle_position = Column(String(50), default="")
    cycle_sensitivity = Column(String(50), default="")

    key_drivers = Column(Text, default="[]")  # JSON list
    leading_indicators = Column(Text, default="[]")  # JSON list

    correlations = Column(Text, default="{}")  # JSON dict
    rotation_patterns = Column(Text, default="")

    current_assessment = Column(Text, default="")
    relative_strength = Column(String(50), default="")

    leaders = Column(Text, default="[]")  # JSON list
    laggards = Column(Text, default="[]")  # JSON list

    what_works_here = Column(Text, default="")
    what_to_avoid = Column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "sector": self.sector,
            "updated": self.updated.isoformat() if self.updated else None,
            "current_cycle_position": self.current_cycle_position,
            "cycle_sensitivity": self.cycle_sensitivity,
            "key_drivers": json.loads(self.key_drivers or "[]"),
            "leading_indicators": json.loads(self.leading_indicators or "[]"),
            "correlations": json.loads(self.correlations or "{}"),
            "rotation_patterns": self.rotation_patterns,
            "current_assessment": self.current_assessment,
            "relative_strength": self.relative_strength,
            "leaders": json.loads(self.leaders or "[]"),
            "laggards": json.loads(self.laggards or "[]"),
            "what_works_here": self.what_works_here,
            "what_to_avoid": self.what_to_avoid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sector":
        d = dict(data)
        if isinstance(d.get("updated"), str):
            d["updated"] = datetime.fromisoformat(d["updated"])
        for field in ("key_drivers", "leading_indicators", "leaders", "laggards"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        if isinstance(d.get("correlations"), dict):
            d["correlations"] = json.dumps(d["correlations"])
        return cls(**d)


class ThesisRecord(Base):
    """Mirrors Thesis dataclass from src/knowledge/thesis.py."""

    __tablename__ = "theses"

    id = Column(String(100), primary_key=True)
    name = Column(String(300), nullable=False)
    created = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active", index=True)
    summary = Column(Text, default="")
    bull_case = Column(Text, default="")
    bear_case = Column(Text, default="")
    conviction = Column(Float, default=50.0)

    positions = Column(Text, default="[]")  # JSON list of symbols
    invalidation_triggers = Column(Text, default="[]")  # JSON list

    last_review = Column(DateTime, nullable=True)
    next_review = Column(DateTime, nullable=True)
    review_interval_days = Column(Integer, default=7)

    conviction_history = Column(Text, default="[]")  # JSON list of updates
    notes = Column(Text, default="[]")  # JSON list

    # Relationships
    signposts = relationship("SignpostRecord", back_populates="thesis", cascade="all, delete-orphan")
    decisions = relationship("DecisionRecord", back_populates="thesis")

    __table_args__ = (
        Index("ix_theses_status_conviction", "status", "conviction"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created": self.created.isoformat() if self.created else None,
            "status": self.status,
            "summary": self.summary,
            "bull_case": self.bull_case,
            "bear_case": self.bear_case,
            "conviction": self.conviction,
            "positions": json.loads(self.positions or "[]"),
            "invalidation_triggers": json.loads(self.invalidation_triggers or "[]"),
            "last_review": self.last_review.isoformat() if self.last_review else None,
            "next_review": self.next_review.isoformat() if self.next_review else None,
            "review_interval_days": self.review_interval_days,
            "conviction_history": json.loads(self.conviction_history or "[]"),
            "notes": json.loads(self.notes or "[]"),
            "signposts": [s.to_dict() for s in self.signposts] if self.signposts else [],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisRecord":
        d = dict(data)
        # Remove signposts — handled separately
        signpost_data = d.pop("signposts", [])
        for field in ("created", "last_review", "next_review"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = datetime.fromisoformat(d[field])
                except (ValueError, TypeError):
                    d[field] = None
        for field in ("positions", "invalidation_triggers", "conviction_history", "notes"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        record = cls(**d)
        record.signposts = [SignpostRecord.from_dict(s, d["id"]) for s in signpost_data]
        return record


class SignpostRecord(Base):
    """Mirrors Signpost dataclass from src/knowledge/thesis.py."""

    __tablename__ = "signposts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    bullish_if = Column(Text, default="")
    bearish_if = Column(Text, default="")
    target_date = Column(String(20), nullable=True)
    triggered_at = Column(DateTime, nullable=True)
    outcome = Column(String(20), nullable=True)

    thesis = relationship("ThesisRecord", back_populates="signposts")

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "status": self.status,
            "bullish_if": self.bullish_if,
            "bearish_if": self.bearish_if,
            "target_date": self.target_date,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: dict, thesis_id: str = "") -> "SignpostRecord":
        d = dict(data)
        d["thesis_id"] = thesis_id
        if isinstance(d.get("triggered_at"), str):
            try:
                d["triggered_at"] = datetime.fromisoformat(d["triggered_at"])
            except (ValueError, TypeError):
                d["triggered_at"] = None
        # Remove 'id' if present (auto-generated)
        d.pop("id", None)
        return cls(**d)


class LearningRecord(Base):
    """Mirrors Learning dataclass from src/knowledge/learnings.py."""

    __tablename__ = "learnings"

    id = Column(String(100), primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, index=True)

    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=True)
    symbol = Column(String(10), index=True)
    action = Column(String(10))

    outcome = Column(String(20))  # win, loss, scratch
    pnl_pct = Column(Float, default=0.0)
    hold_days = Column(Integer, default=0)

    what_happened = Column(Text, default="")
    what_i_learned = Column(Text, default="")
    how_this_changes_approach = Column(Text, default="")

    pattern_name = Column(String(100), nullable=True)
    pattern_description = Column(Text, nullable=True)
    pattern_setup = Column(Text, nullable=True)
    pattern_typical_outcome = Column(Text, nullable=True)
    pattern_action = Column(Text, nullable=True)

    tags = Column(Text, default="[]")  # JSON list
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True)
    confidence_at_entry = Column(Float, nullable=True)

    decision = relationship("DecisionRecord", foreign_keys=[decision_id])

    __table_args__ = (
        Index("ix_learnings_outcome", "outcome"),
        Index("ix_learnings_pattern", "pattern_name"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created": self.created.isoformat() if self.created else None,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "action": self.action,
            "outcome": self.outcome,
            "pnl_pct": self.pnl_pct,
            "hold_days": self.hold_days,
            "what_happened": self.what_happened,
            "what_i_learned": self.what_i_learned,
            "how_this_changes_approach": self.how_this_changes_approach,
            "pattern_name": self.pattern_name,
            "pattern_description": self.pattern_description,
            "pattern_setup": self.pattern_setup,
            "pattern_typical_outcome": self.pattern_typical_outcome,
            "pattern_action": self.pattern_action,
            "tags": json.loads(self.tags or "[]"),
            "thesis_id": self.thesis_id,
            "confidence_at_entry": self.confidence_at_entry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningRecord":
        d = dict(data)
        if isinstance(d.get("created"), str):
            d["created"] = datetime.fromisoformat(d["created"])
        if isinstance(d.get("tags"), list):
            d["tags"] = json.dumps(d["tags"])
        return cls(**d)


class PredictionRecord(Base):
    """Explicit, testable predictions linked to decisions and theses.

    Closes the feedback loop: every decision implies predictions,
    this table makes them explicit and scoreable.
    """

    __tablename__ = "predictions"

    id = Column(String(100), primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, index=True)

    # Linkage
    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=True)
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True)
    symbol = Column(String(10), nullable=False, index=True)

    # Prediction content
    prediction_type = Column(String(30), nullable=False, index=True)
    # price_target, direction, relative_perf, timeframe_move, event_outcome, thesis_validation
    direction = Column(String(10), default="bullish")  # bullish, bearish, neutral
    target_value = Column(Float, nullable=True)  # price target or % move
    target_description = Column(Text, default="")  # free-text for complex predictions
    confidence = Column(Float, default=0.5)  # 0-1 predicted probability
    timeframe_days = Column(Integer, default=10)
    resolve_by = Column(DateTime, nullable=True, index=True)

    # Reasoning metadata
    reasoning_category = Column(String(50), default="thesis_driven", index=True)
    # thesis_driven, technical, geopolitical, earnings, momentum, mean_reversion,
    # event_driven, sentiment, insider_following, congressional
    setup_type = Column(String(50), default="")
    key_reasoning = Column(Text, default="")

    # Resolution
    status = Column(String(20), default="open", index=True)
    # open, hit, miss, expired, cancelled
    resolved_at = Column(DateTime, nullable=True)
    actual_value = Column(Float, nullable=True)
    resolution_notes = Column(Text, default="")

    # Scoring
    brier_score = Column(Float, nullable=True)  # (confidence - outcome)^2
    accuracy_score = Column(Float, nullable=True)  # 1.0=hit, 0.0=miss
    timing_error_days = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_predictions_type_status", "prediction_type", "status"),
        Index("ix_predictions_reasoning_cat", "reasoning_category"),
        Index("ix_predictions_resolve_by", "resolve_by"),
        Index("ix_predictions_symbol_status", "symbol", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created": self.created.isoformat() if self.created else None,
            "decision_id": self.decision_id,
            "thesis_id": self.thesis_id,
            "symbol": self.symbol,
            "prediction_type": self.prediction_type,
            "direction": self.direction,
            "target_value": self.target_value,
            "target_description": self.target_description,
            "confidence": self.confidence,
            "timeframe_days": self.timeframe_days,
            "resolve_by": self.resolve_by.isoformat() if self.resolve_by else None,
            "reasoning_category": self.reasoning_category,
            "setup_type": self.setup_type,
            "key_reasoning": self.key_reasoning,
            "status": self.status,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "actual_value": self.actual_value,
            "resolution_notes": self.resolution_notes,
            "brier_score": self.brier_score,
            "accuracy_score": self.accuracy_score,
            "timing_error_days": self.timing_error_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PredictionRecord":
        d = dict(data)
        for field in ("created", "resolve_by", "resolved_at"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = datetime.fromisoformat(d[field])
                except (ValueError, TypeError):
                    d[field] = None
        return cls(**d)


class DecisionRecord(Base):
    """Mirrors TradingDecision dataclass with provenance extensions."""

    __tablename__ = "decisions"

    id = Column(String(100), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    action = Column(String(10), nullable=False)  # BUY, SELL, HOLD, CLOSE, ADD, TRIM
    confidence = Column(Float, default=0.0)

    # Position details
    size_pct = Column(Float, default=0.0)
    limit_price = Column(Float, nullable=True)
    stop_loss_pct = Column(Float, default=15.0)
    take_profit_pct = Column(Float, default=0.0)
    expected_hold_days = Column(Integer, default=5)

    # Reasoning
    reasoning = Column(Text, default="")
    key_factors = Column(Text, default="[]")  # JSON list
    risks = Column(Text, default="[]")  # JSON list

    # Context snapshot
    context = Column(Text, default="{}")  # JSON dict

    # Tracking
    status = Column(String(20), default="pending", index=True)
    execution_price = Column(Float, nullable=True)
    execution_time = Column(DateTime, nullable=True)

    # Outcome
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    actual_hold_days = Column(Integer, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    realized_pnl_pct = Column(Float, nullable=True)
    outcome_notes = Column(Text, nullable=True)

    # Thesis & learning
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True, index=True)
    pre_mortem = Column(Text, nullable=True)
    adversarial_notes = Column(Text, nullable=True)
    learning_extracted = Column(Boolean, default=False)

    # Strategy tracking
    setup_type = Column(String(50), default="thesis_driven")

    # NEW: Provenance linkage fields
    signal_ids = Column(Text, default="[]")  # JSON list of signal IDs
    convergence_id = Column(String(100), nullable=True)
    llm_interaction_id = Column(String(100), ForeignKey("llm_interactions.id"), nullable=True)
    briefing_id = Column(String(100), nullable=True)

    # Relationships
    thesis = relationship("ThesisRecord", back_populates="decisions")
    signal_links = relationship("DecisionSignalLink", back_populates="decision", cascade="all, delete-orphan")
    llm_interaction = relationship("LLMInteraction", foreign_keys=[llm_interaction_id])
    learnings = relationship("LearningRecord", foreign_keys=[LearningRecord.decision_id], overlaps="decision")

    __table_args__ = (
        Index("ix_decisions_thesis_status", "thesis_id", "status"),
        Index("ix_decisions_setup_type", "setup_type"),
        Index("ix_decisions_symbol_timestamp", "symbol", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "size_pct": self.size_pct,
            "limit_price": self.limit_price,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "expected_hold_days": self.expected_hold_days,
            "reasoning": self.reasoning,
            "key_factors": json.loads(self.key_factors or "[]"),
            "risks": json.loads(self.risks or "[]"),
            "context": json.loads(self.context or "{}"),
            "status": self.status,
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
            "signal_ids": json.loads(self.signal_ids or "[]"),
            "convergence_id": self.convergence_id,
            "llm_interaction_id": self.llm_interaction_id,
            "briefing_id": self.briefing_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionRecord":
        d = dict(data)
        for field in ("timestamp", "execution_time", "exit_time"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = datetime.fromisoformat(d[field])
                except (ValueError, TypeError):
                    d[field] = None
        for field in ("key_factors", "risks", "signal_ids"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        if isinstance(d.get("context"), dict):
            d["context"] = json.dumps(d["context"])
        return cls(**d)


class SignalProvenanceRecord(Base):
    """Mirrors SignalProvenance dataclass from src/knowledge/signal_provenance.py."""

    __tablename__ = "signal_provenance"

    signal_id = Column(String(100), primary_key=True)
    source = Column(String(30), nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    first_detected = Column(DateTime, default=datetime.utcnow, index=True)
    detection_method = Column(String(100), default="")

    initial_confidence = Column(Float, default=0.5)
    initial_direction = Column(String(10), default="neutral")  # bullish, bearish, neutral
    initial_description = Column(Text, default="")

    confidence_history = Column(Text, default="[]")  # JSON list
    corroborating_signals = Column(Text, default="[]")  # JSON list

    linked_thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True)
    linked_thesis_name = Column(String(300), nullable=True)
    thesis_created_from_signal = Column(Boolean, default=False)
    days_to_thesis = Column(Integer, nullable=True)
    thesis_linked_at = Column(DateTime, nullable=True)

    outcome = Column(String(20), default="pending")  # pending, hit, miss, expired, abandoned
    outcome_date = Column(DateTime, nullable=True)
    pnl_contribution = Column(Float, nullable=True)
    outcome_notes = Column(Text, default="")

    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # NEW: Decisions that used this signal
    decision_ids = Column(Text, default="[]")  # JSON list

    decision_links = relationship("DecisionSignalLink", back_populates="signal")

    __table_args__ = (
        Index("ix_signal_prov_source_symbol", "source", "symbol"),
        Index("ix_signal_prov_outcome", "outcome"),
    )

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "symbol": self.symbol,
            "first_detected": self.first_detected.isoformat() if self.first_detected else None,
            "detection_method": self.detection_method,
            "initial_confidence": self.initial_confidence,
            "initial_direction": self.initial_direction,
            "initial_description": self.initial_description,
            "confidence_history": json.loads(self.confidence_history or "[]"),
            "corroborating_signals": json.loads(self.corroborating_signals or "[]"),
            "linked_thesis_id": self.linked_thesis_id,
            "linked_thesis_name": self.linked_thesis_name,
            "thesis_created_from_signal": self.thesis_created_from_signal,
            "days_to_thesis": self.days_to_thesis,
            "thesis_linked_at": self.thesis_linked_at.isoformat() if self.thesis_linked_at else None,
            "outcome": self.outcome,
            "outcome_date": self.outcome_date.isoformat() if self.outcome_date else None,
            "pnl_contribution": self.pnl_contribution,
            "outcome_notes": self.outcome_notes,
            "metadata": json.loads(self.metadata_json or "{}"),
            "decision_ids": json.loads(self.decision_ids or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Provenance tables (NEW — close lineage gaps)
# ---------------------------------------------------------------------------


class DecisionSignalLink(Base):
    """Links signals to the decisions they influenced."""

    __tablename__ = "decision_signal_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=False, index=True)
    signal_id = Column(String(100), ForeignKey("signal_provenance.signal_id"), nullable=False, index=True)
    contribution = Column(String(20), default="supporting")  # primary, supporting, confirming
    signal_confidence_at_decision_time = Column(Float, nullable=True)

    decision = relationship("DecisionRecord", back_populates="signal_links")
    signal = relationship("SignalProvenanceRecord", back_populates="decision_links")

    __table_args__ = (
        Index("ix_dsl_decision_signal", "decision_id", "signal_id", unique=True),
    )


class DecisionConvergence(Base):
    """Records convergences (3+ aligned signals) linked to decisions."""

    __tablename__ = "decision_convergences"

    id = Column(String(100), primary_key=True)
    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=True, index=True)
    symbols = Column(Text, default="[]")  # JSON list
    signal_count = Column(Integer, default=0)
    weighted_score = Column(Float, default=0.0)
    agent_sources = Column(Text, default="[]")  # JSON list
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    direction = Column(String(10), default="neutral")
    detail = Column(Text, default="{}")  # JSON — full convergence data

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "symbols": json.loads(self.symbols or "[]"),
            "signal_count": self.signal_count,
            "weighted_score": self.weighted_score,
            "agent_sources": json.loads(self.agent_sources or "[]"),
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "direction": self.direction,
            "detail": json.loads(self.detail or "{}"),
        }


class LLMInteraction(Base):
    """Full LLM interaction log for decision audit trail."""

    __tablename__ = "llm_interactions"

    id = Column(String(100), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    trigger_type = Column(String(30), default="")  # convergence, alert, rule, scheduled
    trigger_id = Column(String(100), nullable=True)
    model = Column(String(100), default="")
    system_prompt_hash = Column(String(64), default="")
    user_prompt = Column(Text, default="")
    response = Column(Text, default="")
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    decision_id = Column(String(100), nullable=True, index=True)
    latency_ms = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_llm_trigger_type", "trigger_type"),
        Index("ix_llm_model", "model"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "trigger_type": self.trigger_type,
            "trigger_id": self.trigger_id,
            "model": self.model,
            "system_prompt_hash": self.system_prompt_hash,
            "user_prompt": self.user_prompt,
            "response": self.response,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": self.cost_usd,
            "decision_id": self.decision_id,
            "latency_ms": self.latency_ms,
        }


class AgentRun(Base):
    """Agent execution log with richer context than current JSONL."""

    __tablename__ = "agent_runs"

    id = Column(String(100), primary_key=True)
    agent_type = Column(String(30), nullable=False, index=True)
    task = Column(Text, default="")
    trigger_reason = Column(Text, default="")
    parent_run_id = Column(String(100), ForeignKey("agent_runs.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running", index=True)  # running, completed, failed
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)

    # What it found
    signals_generated = Column(Text, default="[]")  # JSON list of signal_ids
    decisions_influenced = Column(Text, default="[]")  # JSON list of decision_ids
    findings_summary = Column(Text, default="")
    raw_output = Column(Text, default="")

    # Heartbeat and process tracking
    heartbeat_at = Column(DateTime, nullable=True)
    pid = Column(Integer, nullable=True)

    # Artifacts and provenance
    artifacts = Column(Text, default="{}")  # JSON: {canonical_path, saved_path, stream_log_path}
    session_id = Column(String(100), nullable=True)  # Claude Code session_id for CLI provenance

    # Relationships
    children = relationship("AgentRun", backref="parent", remote_side=[id])
    events = relationship("ProcessEvent", back_populates="agent_run")

    __table_args__ = (
        Index("ix_agent_runs_type_status", "agent_type", "status"),
        Index("ix_agent_runs_completed", "completed_at"),
    )

    def to_dict(self) -> dict:
        # Compute human-readable duration
        duration_display = None
        if self.started_at and self.completed_at:
            delta = int((self.completed_at - self.started_at).total_seconds())
            if delta < 60:
                duration_display = f"{delta}s"
            elif delta < 3600:
                duration_display = f"{delta // 60}m {delta % 60}s"
            else:
                duration_display = f"{delta // 3600}h {(delta % 3600) // 60}m"

        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "task": self.task,
            "trigger_reason": self.trigger_reason,
            "parent_run_id": self.parent_run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "signals_generated": _safe_json_loads(self.signals_generated, []),
            "decisions_influenced": _safe_json_loads(self.decisions_influenced, []),
            "findings_summary": self.findings_summary,
            "raw_output": self.raw_output or "",
            "artifacts": _safe_json_loads(self.artifacts, {}),
            "session_id": self.session_id,
            "duration_display": duration_display,
        }


class ProcessEvent(Base):
    """Activity stream — every significant system event."""

    __tablename__ = "process_events"

    id = Column(String(100), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    source = Column(String(60), default="")  # autonomy_loop, agent:*, cron:*, human, llm
    symbol = Column(String(10), nullable=True, index=True)
    severity = Column(String(10), default="info")  # info, warning, critical
    title = Column(String(300), default="")
    detail = Column(Text, default="")  # JSON or text

    # Linkage for causal chains
    parent_event_id = Column(String(100), ForeignKey("process_events.id"), nullable=True)
    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=True, index=True)
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True, index=True)
    agent_run_id = Column(String(100), ForeignKey("agent_runs.id"), nullable=True, index=True)
    signal_id = Column(String(100), ForeignKey("signal_provenance.signal_id"), nullable=True)

    # Relationships
    agent_run = relationship("AgentRun", back_populates="events")
    children = relationship("ProcessEvent", backref="parent", remote_side=[id])

    __table_args__ = (
        Index("ix_events_type_timestamp", "event_type", "timestamp"),
        Index("ix_events_source", "source"),
        Index("ix_events_severity", "severity"),
        Index("ix_events_agent_timestamp", "agent_run_id", "timestamp"),
    )

    def to_dict(self) -> dict:
        detail_parsed = _safe_json_loads(self.detail, self.detail or "")

        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "source": self.source,
            "symbol": self.symbol,
            "severity": self.severity,
            "title": self.title,
            "detail": detail_parsed,
            "parent_event_id": self.parent_event_id,
            "decision_id": self.decision_id,
            "thesis_id": self.thesis_id,
            "agent_run_id": self.agent_run_id,
            "signal_id": self.signal_id,
        }


class ThesisPositionLink(Base):
    """Junction table linking theses to their position symbols."""

    __tablename__ = "thesis_position_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tpl_thesis_symbol", "thesis_id", "symbol", unique=True),
    )


class LearningTag(Base):
    """Junction table for learning tags (enables tag-based queries)."""

    __tablename__ = "learning_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    learning_id = Column(String(100), ForeignKey("learnings.id"), nullable=False, index=True)
    tag = Column(String(100), nullable=False, index=True)

    __table_args__ = (
        Index("ix_lt_learning_tag", "learning_id", "tag", unique=True),
    )


class Document(Base):
    """Universal content index for every file the system produces.

    Catalogs briefings, EOD reviews, critic reports, research results,
    validation reports, macro research, etc. Files stay where they are;
    this table is the index.
    """

    __tablename__ = "documents"

    id = Column(String(100), primary_key=True)
    doc_type = Column(String(50), nullable=False, index=True)  # briefing, eod_review, critic_report, etc.
    title = Column(String(500), nullable=False)
    summary = Column(Text, default="")  # first 500 chars or LLM-generated
    file_path = Column(Text, nullable=True)  # absolute path on disk
    content_inline = Column(Text, nullable=True)  # for docs <10KB
    created = Column(DateTime, default=datetime.utcnow, index=True)

    # Cross-reference FKs (all optional)
    agent_run_id = Column(String(100), ForeignKey("agent_runs.id"), nullable=True, index=True)
    thesis_id = Column(String(100), ForeignKey("theses.id"), nullable=True, index=True)
    decision_id = Column(String(100), ForeignKey("decisions.id"), nullable=True, index=True)

    # Metadata
    symbols = Column(Text, default="[]")  # JSON list
    tags = Column(Text, default="[]")  # JSON list
    source = Column(String(100), default="")  # skill:morning-briefing, agent:research, cron, etc.

    __table_args__ = (
        Index("ix_documents_type_created", "doc_type", "created"),
        Index("ix_documents_source", "source"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doc_type": self.doc_type,
            "title": self.title,
            "summary": self.summary,
            "file_path": self.file_path,
            "content_inline": self.content_inline,
            "created": self.created.isoformat() if self.created else None,
            "agent_run_id": self.agent_run_id,
            "thesis_id": self.thesis_id,
            "decision_id": self.decision_id,
            "symbols": _safe_json_loads(self.symbols, []),
            "tags": _safe_json_loads(self.tags, []),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        d = dict(data)
        if isinstance(d.get("created"), str):
            try:
                d["created"] = datetime.fromisoformat(d["created"])
            except (ValueError, TypeError):
                d["created"] = None
        for field in ("symbols", "tags"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        return cls(**d)


class Insight(Base):
    """Research insight from session tracker or agent discovery.

    Absorbs the 112+ insights from workflows/research/session_tracker
    into the DB for cross-referencing and browsing.
    """

    __tablename__ = "insights"

    id = Column(String(100), primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    category = Column(String(50), default="", index=True)  # feature, event, pattern, etc.
    tags = Column(Text, default="[]")  # JSON list
    evidence = Column(Text, default="{}")  # JSON dict

    confidence = Column(Float, default=0.5)
    validated = Column(Boolean, default=False)
    actionable = Column(Boolean, default=True)
    implemented = Column(Boolean, default=False)

    source_session = Column(String(100), nullable=True)
    agent_run_id = Column(String(100), ForeignKey("agent_runs.id"), nullable=True, index=True)
    related_insights = Column(Text, default="[]")  # JSON list of insight IDs

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_insights_category_confidence", "category", "confidence"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "tags": _safe_json_loads(self.tags, []),
            "evidence": _safe_json_loads(self.evidence, {}),
            "confidence": self.confidence,
            "validated": self.validated,
            "actionable": self.actionable,
            "implemented": self.implemented,
            "source_session": self.source_session,
            "agent_run_id": self.agent_run_id,
            "related_insights": _safe_json_loads(self.related_insights, []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        d = dict(data)
        for field in ("created_at", "updated_at"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = datetime.fromisoformat(d[field])
                except (ValueError, TypeError):
                    d[field] = None
        for field in ("tags", "related_insights"):
            if isinstance(d.get(field), list):
                d[field] = json.dumps(d[field])
        if isinstance(d.get("evidence"), dict):
            d["evidence"] = json.dumps(d["evidence"])
        return cls(**d)


class Experiment(Base):
    """Research experiment from session tracker or agent research.

    Absorbs the 61+ experiments from workflows/research/session_tracker
    into the DB for cross-referencing and browsing.
    """

    __tablename__ = "experiments"

    id = Column(String(100), primary_key=True)
    strategy = Column(String(200), nullable=False, index=True)
    symbol = Column(String(10), nullable=True, index=True)
    params = Column(Text, default="{}")  # JSON dict
    result = Column(Text, default="")
    sharpe = Column(Float, nullable=True)
    p_value = Column(Float, nullable=True)
    notes = Column(Text, default="")

    session_id = Column(String(100), nullable=True)
    agent_run_id = Column(String(100), ForeignKey("agent_runs.id"), nullable=True, index=True)
    insight_id = Column(String(100), ForeignKey("insights.id"), nullable=True, index=True)

    run_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_experiments_strategy_symbol", "strategy", "symbol"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "params": _safe_json_loads(self.params, {}),
            "result": self.result,
            "sharpe": self.sharpe,
            "p_value": self.p_value,
            "notes": self.notes,
            "session_id": self.session_id,
            "agent_run_id": self.agent_run_id,
            "insight_id": self.insight_id,
            "run_at": self.run_at.isoformat() if self.run_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Experiment":
        d = dict(data)
        if isinstance(d.get("run_at"), str):
            try:
                d["run_at"] = datetime.fromisoformat(d["run_at"])
            except (ValueError, TypeError):
                d["run_at"] = None
        if isinstance(d.get("params"), dict):
            d["params"] = json.dumps(d["params"])
        return cls(**d)


class AutonomyCheck(Base):
    """Log of each autonomy event loop check cycle."""

    __tablename__ = "autonomy_checks"

    id = Column(String(100), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    check_number = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    state_age_seconds = Column(Integer, default=0)
    alerts_found = Column(Integer, default=0)
    convergences_found = Column(Integer, default=0)
    rules_triggered = Column(Integer, default=0)
    llm_calls_made = Column(Integer, default=0)
    trades_executed = Column(Integer, default=0)
    actions_taken = Column(Text, default="[]")  # JSON
    errors = Column(Text, default="[]")  # JSON

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "check_number": self.check_number,
            "duration_ms": self.duration_ms,
            "state_age_seconds": self.state_age_seconds,
            "alerts_found": self.alerts_found,
            "convergences_found": self.convergences_found,
            "rules_triggered": self.rules_triggered,
            "llm_calls_made": self.llm_calls_made,
            "trades_executed": self.trades_executed,
            "actions_taken": json.loads(self.actions_taken or "[]"),
            "errors": json.loads(self.errors or "[]"),
        }
