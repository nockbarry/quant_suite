#!/usr/bin/env python3
"""Signal Provenance Tracker - Track signals from discovery to thesis to outcome.

Provides:
- Signal origin tracking (source, first detection, method)
- Confidence evolution over time
- Corroborating signal linking
- Thesis linkage (which signals led to which theses)
- Outcome tracking (did the signal work?)

This enables:
- Learning which signal sources are most valuable
- Understanding signal-to-thesis latency
- Identifying missed opportunities
- Measuring signal quality over time
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

from src.core.paths import paths

logger = logging.getLogger(__name__)


class SignalSource(Enum):
    """Where the signal originated."""
    WSB = "wsb"               # Reddit WallStreetBets
    STOCKTWITS = "stocktwits"
    TWITTER = "twitter"
    NEWS = "news"             # News/RSS feeds
    STATISTICAL = "statistical"  # Quantitative signal
    TECHNICAL = "technical"   # Legacy: maps to statistical signals
    TECHNICAL_ANALYSIS = "technical_analysis"  # Legacy: signal_summary.py
    AGENT = "agent"           # Claude agent
    MANUAL = "manual"         # Human entered
    INSIDER = "insider"       # Insider trading data
    CONGRESSIONAL = "congressional"  # Congressional trades
    OPTIONS = "options"       # Options flow
    WSB_TRACKER = "wsb_tracker"  # WSB tracker provenance


class SignalOutcome(Enum):
    """Outcome of a signal."""
    PENDING = "pending"
    HIT = "hit"           # Signal was correct
    MISS = "miss"         # Signal was wrong
    EXPIRED = "expired"   # Signal timed out
    ABANDONED = "abandoned"  # Never acted on


@dataclass
class ConfidenceUpdate:
    """Record of confidence change over time."""
    timestamp: datetime
    confidence: float
    reason: str
    source: Optional[str] = None  # What caused the update

    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConfidenceUpdate":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            confidence=data["confidence"],
            reason=data["reason"],
            source=data.get("source"),
        )


@dataclass
class SignalProvenance:
    """Complete provenance record for a signal.

    Tracks a signal from first detection through thesis creation to outcome.
    """
    signal_id: str
    source: SignalSource
    symbol: str
    first_detected: datetime
    detection_method: str  # How it was detected (e.g., "mention spike", "DD post")

    # Initial state
    initial_confidence: float
    initial_direction: str  # bullish, bearish, neutral
    initial_description: str

    # Evolution
    confidence_history: list = field(default_factory=list)  # List of ConfidenceUpdate
    corroborating_signals: list = field(default_factory=list)  # List of signal_ids

    # Thesis linkage
    linked_thesis_id: Optional[str] = None
    linked_thesis_name: Optional[str] = None
    thesis_created_from_signal: bool = False
    days_to_thesis: Optional[int] = None  # Days from signal to thesis creation
    thesis_linked_at: Optional[datetime] = None

    # Outcome tracking
    outcome: SignalOutcome = SignalOutcome.PENDING
    outcome_date: Optional[datetime] = None
    pnl_contribution: Optional[float] = None
    outcome_notes: str = ""

    # Metadata
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def current_confidence(self) -> float:
        """Get the most recent confidence value."""
        if self.confidence_history:
            return self.confidence_history[-1].confidence
        return self.initial_confidence

    @property
    def signal_age_days(self) -> int:
        """Days since first detection."""
        return (datetime.now() - self.first_detected).days

    @property
    def has_thesis(self) -> bool:
        """Whether this signal is linked to a thesis."""
        return self.linked_thesis_id is not None

    @property
    def corroboration_count(self) -> int:
        """Number of corroborating signals."""
        return len(self.corroborating_signals)

    def update_confidence(self, confidence: float, reason: str, source: str = None):
        """Update confidence with a new value."""
        update = ConfidenceUpdate(
            timestamp=datetime.now(),
            confidence=confidence,
            reason=reason,
            source=source,
        )
        self.confidence_history.append(update)
        self.updated_at = datetime.now()

    def add_corroboration(self, signal_id: str):
        """Add a corroborating signal."""
        if signal_id not in self.corroborating_signals:
            self.corroborating_signals.append(signal_id)
            self.updated_at = datetime.now()

    def link_thesis(self, thesis_id: str, thesis_name: str, is_new_thesis: bool = False):
        """Link this signal to a thesis."""
        self.linked_thesis_id = thesis_id
        self.linked_thesis_name = thesis_name
        self.thesis_created_from_signal = is_new_thesis
        self.thesis_linked_at = datetime.now()
        self.days_to_thesis = (self.thesis_linked_at - self.first_detected).days
        self.updated_at = datetime.now()

    def set_outcome(self, outcome: SignalOutcome, pnl: float = None, notes: str = ""):
        """Set the final outcome of this signal."""
        self.outcome = outcome
        self.outcome_date = datetime.now()
        self.pnl_contribution = pnl
        self.outcome_notes = notes
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "source": self.source.value,
            "symbol": self.symbol,
            "first_detected": self.first_detected.isoformat(),
            "detection_method": self.detection_method,
            "initial_confidence": self.initial_confidence,
            "initial_direction": self.initial_direction,
            "initial_description": self.initial_description,
            "confidence_history": [c.to_dict() for c in self.confidence_history],
            "corroborating_signals": self.corroborating_signals,
            "linked_thesis_id": self.linked_thesis_id,
            "linked_thesis_name": self.linked_thesis_name,
            "thesis_created_from_signal": self.thesis_created_from_signal,
            "days_to_thesis": self.days_to_thesis,
            "thesis_linked_at": self.thesis_linked_at.isoformat() if self.thesis_linked_at else None,
            "outcome": self.outcome.value,
            "outcome_date": self.outcome_date.isoformat() if self.outcome_date else None,
            "pnl_contribution": self.pnl_contribution,
            "outcome_notes": self.outcome_notes,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Computed fields
            "current_confidence": self.current_confidence,
            "signal_age_days": self.signal_age_days,
            "corroboration_count": self.corroboration_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalProvenance":
        """Create from dictionary."""
        return cls(
            signal_id=data["signal_id"],
            source=SignalSource(data["source"]),
            symbol=data["symbol"],
            first_detected=datetime.fromisoformat(data["first_detected"]),
            detection_method=data["detection_method"],
            initial_confidence=data["initial_confidence"],
            initial_direction=data["initial_direction"],
            initial_description=data["initial_description"],
            confidence_history=[
                ConfidenceUpdate.from_dict(c) for c in data.get("confidence_history", [])
            ],
            corroborating_signals=data.get("corroborating_signals", []),
            linked_thesis_id=data.get("linked_thesis_id"),
            linked_thesis_name=data.get("linked_thesis_name"),
            thesis_created_from_signal=data.get("thesis_created_from_signal", False),
            days_to_thesis=data.get("days_to_thesis"),
            thesis_linked_at=datetime.fromisoformat(data["thesis_linked_at"]) if data.get("thesis_linked_at") else None,
            outcome=SignalOutcome(data.get("outcome", "pending")),
            outcome_date=datetime.fromisoformat(data["outcome_date"]) if data.get("outcome_date") else None,
            pnl_contribution=data.get("pnl_contribution"),
            outcome_notes=data.get("outcome_notes", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
        )


class SignalProvenanceTracker:
    """Track and manage signal provenance records."""

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or paths.base / "signal_provenance"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SignalProvenance] = {}
        self._load_all()

    def _load_all(self):
        """Load all provenance records (skip event files)."""
        for file_path in self.base_path.glob("*.json"):
            if file_path.name.startswith("evt_"):
                continue  # Event files, not provenance records
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    signal = SignalProvenance.from_dict(data)
                    self._cache[signal.signal_id] = signal
            except Exception as e:
                logger.warning(f"Could not load {file_path}: {e}")

    def _save(self, signal: SignalProvenance):
        """Save a signal to disk."""
        file_path = self.base_path / f"{signal.signal_id}.json"
        with open(file_path, "w") as f:
            json.dump(signal.to_dict(), f, indent=2)

    def create_signal(
        self,
        source: SignalSource,
        symbol: str,
        confidence: float,
        direction: str,
        description: str,
        detection_method: str = "",
        metadata: dict = None,
    ) -> SignalProvenance:
        """Create a new signal provenance record."""
        signal_id = str(uuid.uuid4())[:8]

        signal = SignalProvenance(
            signal_id=signal_id,
            source=source,
            symbol=symbol,
            first_detected=datetime.now(),
            detection_method=detection_method,
            initial_confidence=confidence,
            initial_direction=direction,
            initial_description=description,
            metadata=metadata or {},
        )

        self._cache[signal_id] = signal
        self._save(signal)
        logger.info(f"Created signal provenance: {signal_id} for {symbol}")

        return signal

    def get_signal(self, signal_id: str) -> Optional[SignalProvenance]:
        """Get a signal by ID."""
        return self._cache.get(signal_id)

    def get_signals_for_symbol(self, symbol: str) -> list[SignalProvenance]:
        """Get all signals for a symbol."""
        return [s for s in self._cache.values() if s.symbol == symbol]

    def get_signals_by_source(self, source: SignalSource) -> list[SignalProvenance]:
        """Get all signals from a source."""
        return [s for s in self._cache.values() if s.source == source]

    def get_unlinked_signals(self, min_confidence: float = 0.5) -> list[SignalProvenance]:
        """Get signals not linked to any thesis."""
        return [
            s for s in self._cache.values()
            if not s.has_thesis and s.current_confidence >= min_confidence
        ]

    def get_early_signals(self, max_age_days: int = 7) -> list[SignalProvenance]:
        """Get recent signals that might be early alpha."""
        return [
            s for s in self._cache.values()
            if s.signal_age_days <= max_age_days and s.outcome == SignalOutcome.PENDING
        ]

    def get_convergent_signals(self, min_corroboration: int = 2) -> list[SignalProvenance]:
        """Get signals with multiple corroborating signals."""
        return [
            s for s in self._cache.values()
            if s.corroboration_count >= min_corroboration
        ]

    def update_signal(self, signal_id: str, **kwargs):
        """Update a signal's attributes."""
        signal = self._cache.get(signal_id)
        if signal:
            for key, value in kwargs.items():
                if hasattr(signal, key):
                    setattr(signal, key, value)
            signal.updated_at = datetime.now()
            self._save(signal)

    def link_signal_to_thesis(
        self,
        signal_id: str,
        thesis_id: str,
        thesis_name: str,
        is_new_thesis: bool = False
    ):
        """Link a signal to a thesis."""
        signal = self._cache.get(signal_id)
        if signal:
            signal.link_thesis(thesis_id, thesis_name, is_new_thesis)
            self._save(signal)
            logger.info(f"Linked signal {signal_id} to thesis {thesis_name}")

    def find_corroborations(self, signal: SignalProvenance) -> list[SignalProvenance]:
        """Find signals that corroborate this one."""
        corroborating = []
        for other in self._cache.values():
            if other.signal_id == signal.signal_id:
                continue
            if other.symbol == signal.symbol:
                # Same symbol, same direction, different source
                if other.initial_direction == signal.initial_direction:
                    if other.source != signal.source:
                        corroborating.append(other)
        return corroborating

    def auto_link_corroborations(self, signal: SignalProvenance):
        """Automatically link corroborating signals."""
        corroborations = self.find_corroborations(signal)
        for corr in corroborations:
            signal.add_corroboration(corr.signal_id)
            corr.add_corroboration(signal.signal_id)
            self._save(corr)
        self._save(signal)

    def get_signal_quality_stats(self) -> dict:
        """Get statistics on signal quality by source."""
        stats = {}

        for source in SignalSource:
            signals = self.get_signals_by_source(source)
            resolved = [s for s in signals if s.outcome != SignalOutcome.PENDING]

            if resolved:
                hits = sum(1 for s in resolved if s.outcome == SignalOutcome.HIT)
                total_pnl = sum(s.pnl_contribution or 0 for s in resolved)
                avg_days_to_thesis = sum(
                    s.days_to_thesis or 0 for s in resolved if s.has_thesis
                ) / max(sum(1 for s in resolved if s.has_thesis), 1)

                stats[source.value] = {
                    "total_signals": len(signals),
                    "resolved": len(resolved),
                    "hit_rate": hits / len(resolved) if resolved else 0,
                    "total_pnl": total_pnl,
                    "avg_days_to_thesis": avg_days_to_thesis,
                }
            else:
                stats[source.value] = {
                    "total_signals": len(signals),
                    "resolved": 0,
                    "hit_rate": 0,
                    "total_pnl": 0,
                    "avg_days_to_thesis": 0,
                }

        return stats

    def generate_report(self) -> str:
        """Generate ASCII report of signal provenance."""
        lines = [
            "SIGNAL PROVENANCE REPORT",
            "═" * 60,
            "",
        ]

        # Stats by source
        stats = self.get_signal_quality_stats()
        lines.append("SIGNAL QUALITY BY SOURCE")
        lines.append("─" * 40)

        for source, data in sorted(stats.items(), key=lambda x: x[1]["total_signals"], reverse=True):
            if data["total_signals"] > 0:
                lines.append(
                    f"  {source:15} | "
                    f"signals: {data['total_signals']:3} | "
                    f"hit rate: {data['hit_rate']:.0%} | "
                    f"P&L: ${data['total_pnl']:+.0f}"
                )

        # Unlinked signals
        unlinked = self.get_unlinked_signals()
        if unlinked:
            lines.extend([
                "",
                "UNLINKED SIGNALS (No Thesis)",
                "─" * 40,
            ])
            for signal in sorted(unlinked, key=lambda s: s.current_confidence, reverse=True)[:10]:
                lines.append(
                    f"  {signal.symbol:6} | "
                    f"{signal.source.value:10} | "
                    f"conf: {signal.current_confidence:.0%} | "
                    f"age: {signal.signal_age_days}d | "
                    f"corr: {signal.corroboration_count}"
                )

        # Early signals
        early = self.get_early_signals()
        if early:
            lines.extend([
                "",
                "EARLY SIGNALS (<7 days)",
                "─" * 40,
            ])
            for signal in sorted(early, key=lambda s: s.corroboration_count, reverse=True)[:10]:
                direction_icon = "↑" if signal.initial_direction == "bullish" else "↓"
                lines.append(
                    f"  {direction_icon} {signal.symbol:6} | "
                    f"{signal.source.value:10} | "
                    f"age: {signal.signal_age_days}d | "
                    f"corr: {signal.corroboration_count}"
                )

        lines.extend(["", "═" * 60])
        return "\n".join(lines)


# Singleton instance
_provenance_tracker: Optional[SignalProvenanceTracker] = None


def get_provenance_tracker() -> SignalProvenanceTracker:
    """Get singleton provenance tracker instance."""
    global _provenance_tracker
    if _provenance_tracker is None:
        _provenance_tracker = SignalProvenanceTracker()
    return _provenance_tracker


# Convenience functions
def create_signal_provenance(
    source: str,
    symbol: str,
    confidence: float,
    direction: str,
    description: str,
    detection_method: str = "",
) -> SignalProvenance:
    """Create a new signal provenance record."""
    tracker = get_provenance_tracker()
    return tracker.create_signal(
        source=SignalSource(source),
        symbol=symbol,
        confidence=confidence,
        direction=direction,
        description=description,
        detection_method=detection_method,
    )


def link_signal_to_thesis(signal_id: str, thesis_id: str, thesis_name: str, is_new: bool = False):
    """Link a signal to a thesis."""
    tracker = get_provenance_tracker()
    tracker.link_signal_to_thesis(signal_id, thesis_id, thesis_name, is_new)


if __name__ == "__main__":
    tracker = SignalProvenanceTracker()
    print(tracker.generate_report())
