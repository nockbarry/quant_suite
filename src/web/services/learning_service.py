"""Learning service -- queries for LearningRecord table."""

import json
from datetime import datetime

from sqlalchemy import func

from src.db.database import get_db
from src.db.models import LearningRecord
from src.db.sync import sync_learning_to_file


def list_learnings(
    limit: int = 50,
    symbol: str | None = None,
    outcome: str | None = None,
    pattern_name: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """Return learnings with optional filters. Most recent first."""
    with get_db() as session:
        q = session.query(LearningRecord)
        if symbol:
            q = q.filter(LearningRecord.symbol == symbol.upper())
        if outcome:
            q = q.filter(LearningRecord.outcome == outcome)
        if pattern_name:
            q = q.filter(LearningRecord.pattern_name == pattern_name)
        if tag:
            # tags is a JSON list -- use LIKE for SQLite
            q = q.filter(LearningRecord.tags.like(f'%"{tag}"%'))
        rows = q.order_by(LearningRecord.created.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_learning(learning_id: str) -> dict | None:
    """Return a single learning by id, or None."""
    with get_db() as session:
        row = session.query(LearningRecord).filter(LearningRecord.id == learning_id).first()
        return row.to_dict() if row else None


def create_learning(data: dict) -> dict:
    """Insert a new learning record. Dual-writes to JSON file."""
    data.setdefault("created", datetime.utcnow().isoformat())
    row = LearningRecord.from_dict(data)
    with get_db() as session:
        session.add(row)
        session.flush()
        result = row.to_dict()
    sync_learning_to_file(result)
    return result


def get_learning_stats() -> dict:
    """Aggregate statistics across all learnings."""
    with get_db() as session:
        total = session.query(func.count(LearningRecord.id)).scalar() or 0

        outcome_counts = (
            session.query(LearningRecord.outcome, func.count(LearningRecord.id))
            .group_by(LearningRecord.outcome)
            .all()
        )
        outcomes = {outcome: count for outcome, count in outcome_counts if outcome}

        avg_pnl = session.query(func.avg(LearningRecord.pnl_pct)).scalar() or 0.0
        avg_hold = session.query(func.avg(LearningRecord.hold_days)).scalar() or 0.0

        pattern_counts = (
            session.query(LearningRecord.pattern_name, func.count(LearningRecord.id))
            .filter(LearningRecord.pattern_name.isnot(None))
            .group_by(LearningRecord.pattern_name)
            .order_by(func.count(LearningRecord.id).desc())
            .limit(10)
            .all()
        )
        top_patterns = {name: count for name, count in pattern_counts if name}

        # Symbol distribution
        symbol_counts = (
            session.query(LearningRecord.symbol, func.count(LearningRecord.id))
            .group_by(LearningRecord.symbol)
            .order_by(func.count(LearningRecord.id).desc())
            .limit(10)
            .all()
        )
        top_symbols = {sym: count for sym, count in symbol_counts if sym}

    return {
        "total": total,
        "outcomes": outcomes,
        "avg_pnl_pct": round(avg_pnl, 2),
        "avg_hold_days": round(avg_hold, 1),
        "top_patterns": top_patterns,
        "top_symbols": top_symbols,
    }
