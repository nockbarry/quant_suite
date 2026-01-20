"""Market Calendar - Track events, predictions, and learnings.

A comprehensive calendar system for:
- Scheduled events (Fed meetings, earnings, economic releases)
- Expert predictions with attribution and tracking
- Claude predictions with reasoning
- Learning integration from briefings and research

Created: 2026-01-20
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import uuid

from src.core.paths import paths

logger = logging.getLogger(__name__)


class EventCategory(Enum):
    """Categories of calendar events."""
    FED = "fed"                      # Federal Reserve meetings, speeches
    ECONOMIC = "economic"            # CPI, jobs, GDP releases
    EARNINGS = "earnings"            # Earnings seasons, major reports
    POLITICAL = "political"          # Elections, policy deadlines
    GEOPOLITICAL = "geopolitical"    # International events, conflicts
    MARKET_STRUCTURE = "market"      # OpEx, rebalancing, witching
    SECTOR = "sector"                # Sector-specific events
    COMPANY = "company"              # Company-specific events
    CUSTOM = "custom"                # User-added events


class EventImpact(Enum):
    """Expected market impact level."""
    CRITICAL = "critical"    # Market-moving, prepare positions
    HIGH = "high"            # Significant volatility expected
    MEDIUM = "medium"        # Notable but manageable
    LOW = "low"              # Minor impact
    UNKNOWN = "unknown"      # Impact uncertain


class PredictionStatus(Enum):
    """Status of a prediction."""
    PENDING = "pending"      # Not yet resolved
    CORRECT = "correct"      # Prediction was accurate
    INCORRECT = "incorrect"  # Prediction was wrong
    PARTIAL = "partial"      # Partially correct
    EXPIRED = "expired"      # Event passed without clear resolution


@dataclass
class CalendarEvent:
    """A scheduled market event."""

    id: str
    title: str
    date: date
    category: EventCategory
    impact: EventImpact
    description: str
    symbols_affected: list[str] = field(default_factory=list)
    sectors_affected: list[str] = field(default_factory=list)

    # Optional timing
    time: Optional[str] = None  # e.g., "14:00 ET"
    end_date: Optional[date] = None  # For multi-day events

    # Recurrence
    recurring: bool = False
    recurrence_rule: Optional[str] = None  # e.g., "monthly", "quarterly"

    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None
    url: Optional[str] = None

    # Learnings attached to this event
    learnings: list[str] = field(default_factory=list)  # Learning IDs

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date.isoformat(),
            "category": self.category.value,
            "impact": self.impact.value,
            "description": self.description,
            "symbols_affected": self.symbols_affected,
            "sectors_affected": self.sectors_affected,
            "time": self.time,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "recurring": self.recurring,
            "recurrence_rule": self.recurrence_rule,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "url": self.url,
            "learnings": self.learnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarEvent":
        return cls(
            id=data["id"],
            title=data["title"],
            date=date.fromisoformat(data["date"]),
            category=EventCategory(data["category"]),
            impact=EventImpact(data["impact"]),
            description=data["description"],
            symbols_affected=data.get("symbols_affected", []),
            sectors_affected=data.get("sectors_affected", []),
            time=data.get("time"),
            end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
            recurring=data.get("recurring", False),
            recurrence_rule=data.get("recurrence_rule"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            source=data.get("source"),
            url=data.get("url"),
            learnings=data.get("learnings", []),
        )


@dataclass
class Prediction:
    """A market prediction with attribution."""

    id: str
    title: str
    prediction: str  # The actual prediction text
    source: str  # "claude", "fed", "goldman", "jpmorgan", etc.
    source_detail: Optional[str] = None  # Specific person/report

    # Timing
    made_date: date = field(default_factory=date.today)
    target_date: Optional[date] = None  # When prediction should resolve
    expiry_date: Optional[date] = None  # When prediction expires

    # Classification
    category: EventCategory = EventCategory.CUSTOM
    confidence: Optional[float] = None  # 0-1 confidence level

    # Market specifics
    symbols: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    direction: Optional[str] = None  # "bullish", "bearish", "neutral"
    target_price: Optional[float] = None
    target_range: Optional[tuple[float, float]] = None

    # Reasoning
    reasoning: str = ""
    key_assumptions: list[str] = field(default_factory=list)
    invalidation_triggers: list[str] = field(default_factory=list)

    # Resolution
    status: PredictionStatus = PredictionStatus.PENDING
    resolution_date: Optional[date] = None
    resolution_notes: str = ""
    actual_outcome: str = ""
    accuracy_score: Optional[float] = None  # 0-1 how accurate

    # Learnings
    learnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "prediction": self.prediction,
            "source": self.source,
            "source_detail": self.source_detail,
            "made_date": self.made_date.isoformat(),
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "category": self.category.value,
            "confidence": self.confidence,
            "symbols": self.symbols,
            "sectors": self.sectors,
            "direction": self.direction,
            "target_price": self.target_price,
            "target_range": list(self.target_range) if self.target_range else None,
            "reasoning": self.reasoning,
            "key_assumptions": self.key_assumptions,
            "invalidation_triggers": self.invalidation_triggers,
            "status": self.status.value,
            "resolution_date": self.resolution_date.isoformat() if self.resolution_date else None,
            "resolution_notes": self.resolution_notes,
            "actual_outcome": self.actual_outcome,
            "accuracy_score": self.accuracy_score,
            "learnings": self.learnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Prediction":
        return cls(
            id=data["id"],
            title=data["title"],
            prediction=data["prediction"],
            source=data["source"],
            source_detail=data.get("source_detail"),
            made_date=date.fromisoformat(data["made_date"]) if data.get("made_date") else date.today(),
            target_date=date.fromisoformat(data["target_date"]) if data.get("target_date") else None,
            expiry_date=date.fromisoformat(data["expiry_date"]) if data.get("expiry_date") else None,
            category=EventCategory(data.get("category", "custom")),
            confidence=data.get("confidence"),
            symbols=data.get("symbols", []),
            sectors=data.get("sectors", []),
            direction=data.get("direction"),
            target_price=data.get("target_price"),
            target_range=tuple(data["target_range"]) if data.get("target_range") else None,
            reasoning=data.get("reasoning", ""),
            key_assumptions=data.get("key_assumptions", []),
            invalidation_triggers=data.get("invalidation_triggers", []),
            status=PredictionStatus(data.get("status", "pending")),
            resolution_date=date.fromisoformat(data["resolution_date"]) if data.get("resolution_date") else None,
            resolution_notes=data.get("resolution_notes", ""),
            actual_outcome=data.get("actual_outcome", ""),
            accuracy_score=data.get("accuracy_score"),
            learnings=data.get("learnings", []),
        )

    def is_due_for_review(self) -> bool:
        """Check if this prediction should be reviewed."""
        today = date.today()
        if self.status != PredictionStatus.PENDING:
            return False
        if self.target_date and today >= self.target_date:
            return True
        if self.expiry_date and today >= self.expiry_date:
            return True
        return False


@dataclass
class CalendarLearning:
    """A learning attached to calendar events or predictions."""

    id: str
    content: str
    source: str  # "briefing", "research", "eod_review", "manual"

    # Linkage
    event_ids: list[str] = field(default_factory=list)
    prediction_ids: list[str] = field(default_factory=list)
    symbol: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5  # How confident in this learning

    # Validation
    validated: bool = False
    validation_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "event_ids": self.event_ids,
            "prediction_ids": self.prediction_ids,
            "symbol": self.symbol,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "confidence": self.confidence,
            "validated": self.validated,
            "validation_notes": self.validation_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarLearning":
        return cls(
            id=data["id"],
            content=data["content"],
            source=data["source"],
            event_ids=data.get("event_ids", []),
            prediction_ids=data.get("prediction_ids", []),
            symbol=data.get("symbol"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            tags=data.get("tags", []),
            confidence=data.get("confidence", 0.5),
            validated=data.get("validated", False),
            validation_notes=data.get("validation_notes", ""),
        )


class MarketCalendar:
    """
    Comprehensive market calendar with events, predictions, and learnings.

    Usage:
        calendar = MarketCalendar()

        # Get upcoming events
        events = calendar.get_events_in_range(date.today(), date.today() + timedelta(days=7))

        # Get predictions due for review
        due = calendar.get_predictions_due_for_review()

        # Add a learning
        calendar.add_learning("Fed more hawkish than expected", source="briefing", event_id="fomc_2026_01")
    """

    def __init__(self, calendar_dir: Optional[Path] = None):
        self.calendar_dir = calendar_dir or (paths.knowledge / "calendar")
        self.calendar_dir.mkdir(parents=True, exist_ok=True)

        self.events_file = self.calendar_dir / "events.json"
        self.predictions_file = self.calendar_dir / "predictions.json"
        self.learnings_file = self.calendar_dir / "learnings.json"

        self._events: dict[str, CalendarEvent] = {}
        self._predictions: dict[str, Prediction] = {}
        self._learnings: dict[str, CalendarLearning] = {}

        self._load()

    def _load(self) -> None:
        """Load calendar data from files."""
        if self.events_file.exists():
            with open(self.events_file) as f:
                data = json.load(f)
                self._events = {e["id"]: CalendarEvent.from_dict(e) for e in data}

        if self.predictions_file.exists():
            with open(self.predictions_file) as f:
                data = json.load(f)
                self._predictions = {p["id"]: Prediction.from_dict(p) for p in data}

        if self.learnings_file.exists():
            with open(self.learnings_file) as f:
                data = json.load(f)
                self._learnings = {l["id"]: CalendarLearning.from_dict(l) for l in data}

    def _save(self) -> None:
        """Save calendar data to files."""
        with open(self.events_file, "w") as f:
            json.dump([e.to_dict() for e in self._events.values()], f, indent=2)

        with open(self.predictions_file, "w") as f:
            json.dump([p.to_dict() for p in self._predictions.values()], f, indent=2)

        with open(self.learnings_file, "w") as f:
            json.dump([l.to_dict() for l in self._learnings.values()], f, indent=2)

    # =========================================================================
    # Event Management
    # =========================================================================

    def add_event(
        self,
        title: str,
        event_date: date,
        category: EventCategory,
        impact: EventImpact,
        description: str,
        **kwargs
    ) -> CalendarEvent:
        """Add a new event to the calendar."""
        event_id = kwargs.pop("id", None) or f"{category.value}_{event_date.isoformat()}_{uuid.uuid4().hex[:8]}"

        event = CalendarEvent(
            id=event_id,
            title=title,
            date=event_date,
            category=category,
            impact=impact,
            description=description,
            **kwargs
        )

        self._events[event.id] = event
        self._save()
        return event

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Get an event by ID."""
        return self._events.get(event_id)

    def get_events_in_range(
        self,
        start: date,
        end: date,
        category: Optional[EventCategory] = None,
        min_impact: Optional[EventImpact] = None,
    ) -> list[CalendarEvent]:
        """Get events in a date range."""
        impact_order = [EventImpact.LOW, EventImpact.MEDIUM, EventImpact.HIGH, EventImpact.CRITICAL]

        events = []
        for event in self._events.values():
            if event.date < start or event.date > end:
                continue
            if category and event.category != category:
                continue
            if min_impact:
                if impact_order.index(event.impact) < impact_order.index(min_impact):
                    continue
            events.append(event)

        return sorted(events, key=lambda e: e.date)

    def get_upcoming_events(self, days: int = 7, min_impact: Optional[EventImpact] = None) -> list[CalendarEvent]:
        """Get events in the next N days."""
        return self.get_events_in_range(
            date.today(),
            date.today() + timedelta(days=days),
            min_impact=min_impact
        )

    def get_events_for_symbol(self, symbol: str) -> list[CalendarEvent]:
        """Get all events affecting a symbol."""
        return [e for e in self._events.values() if symbol in e.symbols_affected]

    def get_events_for_sector(self, sector: str) -> list[CalendarEvent]:
        """Get all events affecting a sector."""
        return [e for e in self._events.values() if sector in e.sectors_affected]

    # =========================================================================
    # Prediction Management
    # =========================================================================

    def add_prediction(
        self,
        title: str,
        prediction: str,
        source: str,
        **kwargs
    ) -> Prediction:
        """Add a new prediction."""
        pred_id = kwargs.pop("id", None) or f"pred_{date.today().isoformat()}_{uuid.uuid4().hex[:8]}"

        pred = Prediction(
            id=pred_id,
            title=title,
            prediction=prediction,
            source=source,
            **kwargs
        )

        self._predictions[pred.id] = pred
        self._save()
        return pred

    def get_prediction(self, pred_id: str) -> Optional[Prediction]:
        """Get a prediction by ID."""
        return self._predictions.get(pred_id)

    def get_predictions_by_source(self, source: str) -> list[Prediction]:
        """Get all predictions from a source."""
        return [p for p in self._predictions.values() if p.source == source]

    def get_pending_predictions(self) -> list[Prediction]:
        """Get all pending predictions."""
        return [p for p in self._predictions.values() if p.status == PredictionStatus.PENDING]

    def get_predictions_due_for_review(self) -> list[Prediction]:
        """Get predictions that should be reviewed."""
        return [p for p in self._predictions.values() if p.is_due_for_review()]

    def resolve_prediction(
        self,
        pred_id: str,
        status: PredictionStatus,
        actual_outcome: str,
        accuracy_score: Optional[float] = None,
        notes: str = ""
    ) -> Optional[Prediction]:
        """Resolve a prediction with outcome."""
        pred = self._predictions.get(pred_id)
        if not pred:
            return None

        pred.status = status
        pred.resolution_date = date.today()
        pred.actual_outcome = actual_outcome
        pred.accuracy_score = accuracy_score
        pred.resolution_notes = notes

        self._save()
        return pred

    def get_prediction_accuracy(self, source: Optional[str] = None) -> dict:
        """Calculate prediction accuracy statistics."""
        preds = self._predictions.values()
        if source:
            preds = [p for p in preds if p.source == source]

        resolved = [p for p in preds if p.status != PredictionStatus.PENDING]
        if not resolved:
            return {"total": 0, "resolved": 0, "accuracy": None}

        correct = len([p for p in resolved if p.status == PredictionStatus.CORRECT])
        partial = len([p for p in resolved if p.status == PredictionStatus.PARTIAL])
        incorrect = len([p for p in resolved if p.status == PredictionStatus.INCORRECT])

        # Weighted accuracy: correct=1, partial=0.5, incorrect=0
        weighted = (correct + 0.5 * partial) / len(resolved) if resolved else 0

        return {
            "total": len(list(preds)),
            "resolved": len(resolved),
            "correct": correct,
            "partial": partial,
            "incorrect": incorrect,
            "accuracy": weighted,
        }

    # =========================================================================
    # Learning Management
    # =========================================================================

    def add_learning(
        self,
        content: str,
        source: str,
        event_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        **kwargs
    ) -> CalendarLearning:
        """Add a learning linked to events/predictions."""
        learning_id = f"learn_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        event_ids = kwargs.pop("event_ids", [])
        prediction_ids = kwargs.pop("prediction_ids", [])

        if event_id:
            event_ids.append(event_id)
        if prediction_id:
            prediction_ids.append(prediction_id)

        learning = CalendarLearning(
            id=learning_id,
            content=content,
            source=source,
            event_ids=event_ids,
            prediction_ids=prediction_ids,
            **kwargs
        )

        self._learnings[learning.id] = learning

        # Link back to events and predictions
        for eid in event_ids:
            if eid in self._events:
                self._events[eid].learnings.append(learning_id)

        for pid in prediction_ids:
            if pid in self._predictions:
                self._predictions[pid].learnings.append(learning_id)

        self._save()
        return learning

    def get_learnings_for_event(self, event_id: str) -> list[CalendarLearning]:
        """Get all learnings for an event."""
        return [l for l in self._learnings.values() if event_id in l.event_ids]

    def get_learnings_for_prediction(self, pred_id: str) -> list[CalendarLearning]:
        """Get all learnings for a prediction."""
        return [l for l in self._learnings.values() if pred_id in l.prediction_ids]

    def get_recent_learnings(self, days: int = 30) -> list[CalendarLearning]:
        """Get recent learnings."""
        cutoff = datetime.now() - timedelta(days=days)
        return [l for l in self._learnings.values() if l.created_at >= cutoff]

    # =========================================================================
    # Summary and Export
    # =========================================================================

    def get_week_summary(self, start_date: Optional[date] = None) -> str:
        """Get a summary of the upcoming week."""
        start = start_date or date.today()
        end = start + timedelta(days=7)

        events = self.get_events_in_range(start, end)
        predictions_due = [p for p in self.get_predictions_due_for_review()
                          if p.target_date and start <= p.target_date <= end]

        lines = [
            f"# Week of {start.strftime('%B %d, %Y')}",
            "",
        ]

        # Group events by date
        events_by_date: dict[date, list[CalendarEvent]] = {}
        for e in events:
            events_by_date.setdefault(e.date, []).append(e)

        for d in sorted(events_by_date.keys()):
            day_events = events_by_date[d]
            lines.append(f"## {d.strftime('%A, %B %d')}")
            for e in sorted(day_events, key=lambda x: (x.impact.value, x.time or "")):
                impact_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(e.impact.value, "⚪")
                time_str = f" ({e.time})" if e.time else ""
                lines.append(f"- {impact_emoji} **{e.title}**{time_str}")
                lines.append(f"  - {e.description}")
                if e.symbols_affected:
                    lines.append(f"  - Symbols: {', '.join(e.symbols_affected)}")
            lines.append("")

        if predictions_due:
            lines.append("## Predictions Due for Review")
            for p in predictions_due:
                lines.append(f"- **{p.title}** ({p.source})")
                lines.append(f"  - {p.prediction}")
            lines.append("")

        return "\n".join(lines)

    def get_month_summary(self, year: int, month: int) -> str:
        """Get a summary of a month."""
        from calendar import monthrange

        start = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end = date(year, month, last_day)

        events = self.get_events_in_range(start, end)

        # Count by category and impact
        by_category: dict[str, int] = {}
        by_impact: dict[str, int] = {}

        for e in events:
            by_category[e.category.value] = by_category.get(e.category.value, 0) + 1
            by_impact[e.impact.value] = by_impact.get(e.impact.value, 0) + 1

        lines = [
            f"# {start.strftime('%B %Y')} Calendar Summary",
            "",
            f"Total Events: {len(events)}",
            "",
            "## By Category",
        ]

        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: {count}")

        lines.extend(["", "## By Impact"])
        for imp, count in sorted(by_impact.items()):
            lines.append(f"- {imp}: {count}")

        lines.extend(["", "## Critical Events"])
        critical = [e for e in events if e.impact == EventImpact.CRITICAL]
        for e in sorted(critical, key=lambda x: x.date):
            lines.append(f"- {e.date.strftime('%b %d')}: {e.title}")

        return "\n".join(lines)

    def export_to_json(self) -> dict:
        """Export entire calendar to JSON."""
        return {
            "events": [e.to_dict() for e in self._events.values()],
            "predictions": [p.to_dict() for p in self._predictions.values()],
            "learnings": [l.to_dict() for l in self._learnings.values()],
            "exported_at": datetime.now().isoformat(),
        }

    def get_statistics(self) -> dict:
        """Get calendar statistics."""
        prediction_stats = self.get_prediction_accuracy()
        claude_stats = self.get_prediction_accuracy(source="claude")

        return {
            "total_events": len(self._events),
            "total_predictions": len(self._predictions),
            "total_learnings": len(self._learnings),
            "upcoming_events_7d": len(self.get_upcoming_events(7)),
            "upcoming_events_30d": len(self.get_upcoming_events(30)),
            "predictions_pending": len(self.get_pending_predictions()),
            "predictions_due_review": len(self.get_predictions_due_for_review()),
            "overall_prediction_accuracy": prediction_stats.get("accuracy"),
            "claude_prediction_accuracy": claude_stats.get("accuracy"),
        }


def initialize_2026_calendar() -> MarketCalendar:
    """Initialize calendar with 2026 events and predictions."""
    calendar = MarketCalendar()

    # Only initialize if empty
    if calendar._events:
        logger.info("Calendar already initialized")
        return calendar

    logger.info("Initializing 2026 calendar...")

    # Import the initialization data
    from src.knowledge.calendar_data import (
        get_fed_events_2026,
        get_economic_events_2026,
        get_earnings_events_2026,
        get_political_events_2026,
        get_market_structure_events_2026,
        get_expert_predictions_2026,
        get_claude_predictions_2026,
    )

    # Add all events (rename 'date' to 'event_date' for method signature)
    def add_event_from_data(data: dict):
        if "date" in data and "event_date" not in data:
            data = data.copy()
            data["event_date"] = data.pop("date")
        calendar.add_event(**data)

    for event_data in get_fed_events_2026():
        add_event_from_data(event_data)

    for event_data in get_economic_events_2026():
        add_event_from_data(event_data)

    for event_data in get_earnings_events_2026():
        add_event_from_data(event_data)

    for event_data in get_political_events_2026():
        add_event_from_data(event_data)

    for event_data in get_market_structure_events_2026():
        add_event_from_data(event_data)

    # Add predictions
    for pred_data in get_expert_predictions_2026():
        calendar.add_prediction(**pred_data)

    for pred_data in get_claude_predictions_2026():
        calendar.add_prediction(**pred_data)

    logger.info(f"Initialized calendar with {len(calendar._events)} events and {len(calendar._predictions)} predictions")
    return calendar
