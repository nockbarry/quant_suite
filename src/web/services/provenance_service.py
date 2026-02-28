"""Provenance service -- queries for SignalProvenanceRecord and DecisionConvergence."""

from sqlalchemy.orm import joinedload

from src.db.database import get_db
from src.db.models import (
    SignalProvenanceRecord,
    DecisionConvergence,
    DecisionSignalLink,
)


def list_signals(
    symbol: str | None = None,
    source: str | None = None,
    direction: str | None = None,
    outcome: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return signal provenance records with optional filters."""
    with get_db() as session:
        q = session.query(SignalProvenanceRecord)
        if symbol:
            q = q.filter(SignalProvenanceRecord.symbol == symbol.upper())
        if source:
            q = q.filter(SignalProvenanceRecord.source == source)
        if direction:
            q = q.filter(SignalProvenanceRecord.direction == direction)
        if outcome:
            q = q.filter(SignalProvenanceRecord.outcome == outcome)
        rows = q.order_by(SignalProvenanceRecord.first_detected.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_signal(signal_id: str) -> dict | None:
    """Return a single signal provenance record, or None."""
    with get_db() as session:
        row = (
            session.query(SignalProvenanceRecord)
            .filter(SignalProvenanceRecord.signal_id == signal_id)
            .first()
        )
        return row.to_dict() if row else None


def get_signal_decisions(signal_id: str) -> list[dict]:
    """Return all decisions that used a given signal (via DecisionSignalLink)."""
    with get_db() as session:
        links = (
            session.query(DecisionSignalLink)
            .options(joinedload(DecisionSignalLink.decision))
            .filter(DecisionSignalLink.signal_id == signal_id)
            .all()
        )
        results = []
        for link in links:
            if link.decision:
                decision_data = link.decision.to_dict()
                decision_data["signal_contribution"] = link.contribution
                decision_data["signal_confidence_at_decision_time"] = link.signal_confidence_at_decision_time
                results.append(decision_data)
        return results


def list_convergences(limit: int = 50) -> list[dict]:
    """Return convergence records, most recent first."""
    with get_db() as session:
        rows = (
            session.query(DecisionConvergence)
            .order_by(DecisionConvergence.detected_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]


def get_convergence(convergence_id: str) -> dict | None:
    """Return a single convergence record, or None."""
    with get_db() as session:
        row = (
            session.query(DecisionConvergence)
            .filter(DecisionConvergence.id == convergence_id)
            .first()
        )
        return row.to_dict() if row else None


def group_by_symbol(signals: list[dict]) -> dict[str, list[dict]]:
    """Group a list of signal dicts by their symbol."""
    grouped: dict[str, list[dict]] = {}
    for sig in signals:
        sym = sig.get("symbol", "UNKNOWN")
        grouped.setdefault(sym, []).append(sig)
    return grouped
