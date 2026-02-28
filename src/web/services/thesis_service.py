"""Thesis service -- CRUD + queries for ThesisRecord and SignpostRecord."""

import json
from datetime import datetime

from sqlalchemy.orm import joinedload

from src.db.database import get_db
from src.db.models import ThesisRecord, SignpostRecord, DecisionRecord
from src.db.sync import sync_thesis_to_file


def list_theses(status_filter: str | None = None) -> list[dict]:
    """Return theses, optionally filtered by status. Ordered by conviction desc."""
    with get_db() as session:
        q = session.query(ThesisRecord).options(joinedload(ThesisRecord.signposts))
        if status_filter:
            q = q.filter(ThesisRecord.status == status_filter)
        rows = q.order_by(ThesisRecord.conviction.desc()).all()
        return [r.to_dict() for r in rows]


def get_thesis(thesis_id: str) -> dict | None:
    """Return a single thesis with signposts, or None."""
    with get_db() as session:
        row = (
            session.query(ThesisRecord)
            .options(joinedload(ThesisRecord.signposts))
            .filter(ThesisRecord.id == thesis_id)
            .first()
        )
        return row.to_dict() if row else None


def create_thesis(data: dict) -> dict:
    """Insert a new thesis with signposts. Dual-writes to YAML."""
    row = ThesisRecord.from_dict(data)
    with get_db() as session:
        session.add(row)
        session.flush()
        result = row.to_dict()
    sync_thesis_to_file(result)
    return result


def update_thesis(thesis_id: str, data: dict) -> dict | None:
    """Update thesis fields (not signposts -- use dedicated methods). Dual-writes."""
    with get_db() as session:
        row = (
            session.query(ThesisRecord)
            .options(joinedload(ThesisRecord.signposts))
            .filter(ThesisRecord.id == thesis_id)
            .first()
        )
        if row is None:
            return None

        signpost_data = data.pop("signposts", None)

        for key, value in data.items():
            if key == "id":
                continue
            if key in ("positions", "invalidation_triggers", "conviction_history", "notes") and isinstance(value, list):
                value = json.dumps(value)
            if key in ("created", "last_review", "next_review") and isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    continue
            if hasattr(row, key):
                setattr(row, key, value)

        # Replace signposts if provided
        if signpost_data is not None:
            session.query(SignpostRecord).filter(SignpostRecord.thesis_id == thesis_id).delete()
            for sp in signpost_data:
                session.add(SignpostRecord.from_dict(sp, thesis_id))

        session.flush()
        # Refresh to pick up new signposts
        session.refresh(row)
        result = row.to_dict()

    sync_thesis_to_file(result)
    return result


def update_conviction(thesis_id: str, new_value: float, reason: str = "") -> dict | None:
    """Update conviction and append to history. Dual-writes."""
    with get_db() as session:
        row = (
            session.query(ThesisRecord)
            .options(joinedload(ThesisRecord.signposts))
            .filter(ThesisRecord.id == thesis_id)
            .first()
        )
        if row is None:
            return None

        old_value = row.conviction
        row.conviction = new_value

        history = json.loads(row.conviction_history or "[]")
        history.append({
            "from": old_value,
            "to": new_value,
            "reason": reason,
            "date": datetime.utcnow().isoformat(),
        })
        row.conviction_history = json.dumps(history)
        row.last_review = datetime.utcnow()

        session.flush()
        result = row.to_dict()

    sync_thesis_to_file(result)
    return result


def get_thesis_decisions(thesis_id: str) -> list[dict]:
    """Return all decisions linked to a thesis."""
    with get_db() as session:
        rows = (
            session.query(DecisionRecord)
            .filter(DecisionRecord.thesis_id == thesis_id)
            .order_by(DecisionRecord.timestamp.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_thesis_performance(thesis_id: str) -> dict:
    """Compute performance summary for a thesis from its decisions."""
    with get_db() as session:
        decisions = (
            session.query(DecisionRecord)
            .filter(DecisionRecord.thesis_id == thesis_id)
            .all()
        )

    if not decisions:
        return {
            "thesis_id": thesis_id,
            "total_decisions": 0,
            "total_realized_pnl": 0.0,
            "avg_realized_pnl_pct": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "open_count": 0,
        }

    realized = [d for d in decisions if d.realized_pnl is not None]
    wins = [d for d in realized if (d.realized_pnl or 0) > 0]
    losses = [d for d in realized if (d.realized_pnl or 0) < 0]
    open_count = sum(1 for d in decisions if d.status in ("pending", "executed"))

    total_pnl = sum(d.realized_pnl or 0 for d in realized)
    avg_pnl_pct = (
        sum(d.realized_pnl_pct or 0 for d in realized) / len(realized)
        if realized
        else 0.0
    )
    win_rate = len(wins) / len(realized) if realized else 0.0

    return {
        "thesis_id": thesis_id,
        "total_decisions": len(decisions),
        "total_realized_pnl": round(total_pnl, 2),
        "avg_realized_pnl_pct": round(avg_pnl_pct, 2),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate, 4),
        "open_count": open_count,
    }
