"""Flow service -- queries for ProcessEvent (activity stream) table."""

from src.db.database import get_db
from src.db.models import ProcessEvent


def list_events(
    limit: int = 100,
    event_type: str | None = None,
    source: str | None = None,
    symbol: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    """Return process events with optional filters. Most recent first."""
    with get_db() as session:
        q = session.query(ProcessEvent)
        if event_type:
            q = q.filter(ProcessEvent.event_type == event_type)
        if source:
            q = q.filter(ProcessEvent.source == source)
        if symbol:
            q = q.filter(ProcessEvent.symbol == symbol.upper())
        if severity:
            q = q.filter(ProcessEvent.severity == severity)
        rows = q.order_by(ProcessEvent.timestamp.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_event(event_id: str) -> dict | None:
    """Return a single event by id, or None."""
    with get_db() as session:
        row = session.query(ProcessEvent).filter(ProcessEvent.id == event_id).first()
        return row.to_dict() if row else None


def get_event_chain(event_id: str) -> list[dict]:
    """Follow parent_event_id links to build the causal chain.

    Returns a list from the root event down to the given event_id.
    """
    chain = []
    with get_db() as session:
        current_id = event_id
        visited = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            row = session.query(ProcessEvent).filter(ProcessEvent.id == current_id).first()
            if row is None:
                break
            chain.append(row.to_dict())
            current_id = row.parent_event_id

    # Reverse so root is first, target event is last
    chain.reverse()
    return chain


def get_decision_flow(decision_id: str) -> list[dict]:
    """Return all events linked to a specific decision, ordered chronologically."""
    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(ProcessEvent.decision_id == decision_id)
            .order_by(ProcessEvent.timestamp.asc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_child_events(event_id: str) -> list[dict]:
    """Return events whose parent_event_id matches the given event."""
    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(ProcessEvent.parent_event_id == event_id)
            .order_by(ProcessEvent.timestamp.asc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_filter_options() -> dict:
    """Return distinct values for event filters (event types, sources, severities, symbols)."""
    from sqlalchemy import distinct

    with get_db() as session:
        event_types = [
            r[0] for r in session.query(distinct(ProcessEvent.event_type)).all() if r[0]
        ]
        sources = [
            r[0] for r in session.query(distinct(ProcessEvent.source)).all() if r[0]
        ]
        severities = [
            r[0] for r in session.query(distinct(ProcessEvent.severity)).all() if r[0]
        ]
        symbols = [
            r[0] for r in session.query(distinct(ProcessEvent.symbol)).all() if r[0]
        ]

    return {
        "event_types": sorted(event_types),
        "sources": sorted(sources),
        "severities": sorted(severities),
        "symbols": sorted(symbols),
    }


# Aliases matching route expectations
get_decision_events = get_decision_flow
get_causal_chain = get_event_chain
