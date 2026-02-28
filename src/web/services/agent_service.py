"""Agent service -- queries for AgentRun table."""

from sqlalchemy import func

from src.db.database import get_db
from src.db.models import AgentRun


def list_agent_runs(
    limit: int = 50,
    agent_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Return agent runs with optional filters. Most recent first."""
    with get_db() as session:
        q = session.query(AgentRun)
        if agent_type:
            q = q.filter(AgentRun.agent_type == agent_type)
        if status:
            q = q.filter(AgentRun.status == status)
        rows = q.order_by(AgentRun.started_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_agent_run(run_id: str) -> dict | None:
    """Return a single agent run by id, or None."""
    with get_db() as session:
        row = session.query(AgentRun).filter(AgentRun.id == run_id).first()
        return row.to_dict() if row else None


def get_agent_metrics() -> dict:
    """Aggregate metrics: cost per type, signals per type, effectiveness."""
    with get_db() as session:
        # Per-type aggregates
        type_stats = (
            session.query(
                AgentRun.agent_type,
                func.count(AgentRun.id).label("run_count"),
                func.sum(AgentRun.cost_usd).label("total_cost"),
                func.sum(AgentRun.tokens_used).label("total_tokens"),
                func.avg(AgentRun.cost_usd).label("avg_cost"),
            )
            .group_by(AgentRun.agent_type)
            .all()
        )

        per_type = {}
        for row in type_stats:
            agent_type = row[0]
            per_type[agent_type] = {
                "run_count": row[1] or 0,
                "total_cost": round(row[2] or 0, 4),
                "total_tokens": row[3] or 0,
                "avg_cost": round(row[4] or 0, 4),
            }

        # Signals generated per type (count non-empty signals_generated lists)
        # signals_generated is a JSON list; count entries where length > 2 (not "[]")
        for agent_type in per_type:
            signal_runs = (
                session.query(AgentRun.signals_generated)
                .filter(
                    AgentRun.agent_type == agent_type,
                    AgentRun.signals_generated != "[]",
                    AgentRun.signals_generated.isnot(None),
                )
                .all()
            )
            signal_count = 0
            for (signals_json,) in signal_runs:
                try:
                    import json
                    signal_count += len(json.loads(signals_json or "[]"))
                except Exception:
                    pass
            per_type[agent_type]["signals_generated"] = signal_count

        # Effectiveness: completed vs failed
        for agent_type in per_type:
            completed = (
                session.query(func.count(AgentRun.id))
                .filter(AgentRun.agent_type == agent_type, AgentRun.status == "completed")
                .scalar()
                or 0
            )
            failed = (
                session.query(func.count(AgentRun.id))
                .filter(AgentRun.agent_type == agent_type, AgentRun.status == "failed")
                .scalar()
                or 0
            )
            total = completed + failed
            per_type[agent_type]["completed"] = completed
            per_type[agent_type]["failed"] = failed
            per_type[agent_type]["success_rate"] = round(completed / total, 4) if total else 0.0

        # Global totals
        total_runs = session.query(func.count(AgentRun.id)).scalar() or 0
        total_cost = session.query(func.sum(AgentRun.cost_usd)).scalar() or 0
        total_tokens = session.query(func.sum(AgentRun.tokens_used)).scalar() or 0

    return {
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "per_type": per_type,
    }


def get_agent_children(run_id: str) -> list[dict]:
    """Return child agent runs spawned by a parent run."""
    with get_db() as session:
        rows = (
            session.query(AgentRun)
            .filter(AgentRun.parent_run_id == run_id)
            .order_by(AgentRun.started_at.asc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_run_events(run_id: str) -> list[dict]:
    """Return process events linked to an agent run."""
    from src.db.models import ProcessEvent

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(ProcessEvent.agent_run_id == run_id)
            .order_by(ProcessEvent.timestamp.asc())
            .all()
        )
        return [r.to_dict() for r in rows]


# Aliases matching route expectations
list_runs = list_agent_runs
get_run = get_agent_run
get_child_runs = get_agent_children
get_aggregate_metrics = get_agent_metrics
