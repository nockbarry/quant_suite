"""LLM interaction service — queries for LLMInteraction records."""

from datetime import datetime, timedelta

from sqlalchemy import func

from src.db.database import get_db
from src.db.models import LLMInteraction


def list_interactions(
    limit: int = 50,
    trigger_type: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Return LLM interaction records with optional filters."""
    with get_db() as session:
        q = session.query(LLMInteraction)
        if trigger_type:
            q = q.filter(LLMInteraction.trigger_type == trigger_type)
        if model:
            q = q.filter(LLMInteraction.model == model)
        rows = q.order_by(LLMInteraction.timestamp.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_interaction(interaction_id: str) -> dict | None:
    """Return a single LLM interaction, or None."""
    with get_db() as session:
        row = (
            session.query(LLMInteraction)
            .filter(LLMInteraction.id == interaction_id)
            .first()
        )
        return row.to_dict() if row else None


def get_cost_summary() -> dict:
    """Return cost analysis: total, by model, by trigger type, daily."""
    with get_db() as session:
        # Total
        total = (
            session.query(
                func.count(LLMInteraction.id),
                func.sum(LLMInteraction.cost_usd),
                func.sum(LLMInteraction.tokens_input),
                func.sum(LLMInteraction.tokens_output),
            )
            .first()
        )

        # By model
        by_model = (
            session.query(
                LLMInteraction.model,
                func.count(LLMInteraction.id),
                func.sum(LLMInteraction.cost_usd),
                func.sum(LLMInteraction.tokens_input + LLMInteraction.tokens_output),
            )
            .group_by(LLMInteraction.model)
            .all()
        )

        # By trigger type
        by_trigger = (
            session.query(
                LLMInteraction.trigger_type,
                func.count(LLMInteraction.id),
                func.sum(LLMInteraction.cost_usd),
            )
            .group_by(LLMInteraction.trigger_type)
            .all()
        )

        # Today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today = (
            session.query(
                func.count(LLMInteraction.id),
                func.sum(LLMInteraction.cost_usd),
            )
            .filter(LLMInteraction.timestamp >= today_start)
            .first()
        )

    return {
        "total_calls": total[0] or 0,
        "total_cost": round(total[1] or 0, 4),
        "total_tokens_in": total[2] or 0,
        "total_tokens_out": total[3] or 0,
        "by_model": [
            {"model": m[0], "calls": m[1], "cost": round(m[2] or 0, 4), "tokens": m[3] or 0}
            for m in by_model
        ],
        "by_trigger": [
            {"trigger_type": t[0], "calls": t[1], "cost": round(t[2] or 0, 4)}
            for t in by_trigger
        ],
        "today_calls": today[0] or 0,
        "today_cost": round(today[1] or 0, 4),
    }
