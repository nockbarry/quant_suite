"""Agent service -- queries for AgentRun table."""

import json

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

        # Average duration (julianday difference * 86400 = seconds)
        avg_dur_result = session.query(
            func.avg(
                func.julianday(AgentRun.completed_at) - func.julianday(AgentRun.started_at)
            )
        ).filter(
            AgentRun.completed_at.isnot(None),
            AgentRun.started_at.isnot(None),
        ).scalar()
        avg_duration_sec = round((avg_dur_result or 0) * 86400, 1)

        # Sum signals_generated across all types
        total_signals = sum(v.get("signals_generated", 0) for v in per_type.values())

        # Count decisions_influenced across all runs
        total_decisions = 0
        for (dec_json,) in session.query(AgentRun.decisions_influenced).filter(
            AgentRun.decisions_influenced != "[]",
            AgentRun.decisions_influenced.isnot(None),
        ).all():
            try:
                total_decisions += len(json.loads(dec_json or "[]"))
            except Exception:
                pass

    return {
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "avg_duration_sec": avg_duration_sec,
        "signals_generated": total_signals,
        "decisions_influenced": total_decisions,
        "per_type": per_type,
    }


def get_distinct_agent_types() -> list[str]:
    """Return sorted list of unique agent types."""
    with get_db() as session:
        rows = session.query(AgentRun.agent_type).distinct().all()
        return sorted([r[0] for r in rows if r[0]])


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


def get_active_runs() -> list[dict]:
    """Return currently running agent runs."""
    with get_db() as session:
        rows = (
            session.query(AgentRun)
            .filter(AgentRun.status == "running")
            .order_by(AgentRun.started_at.desc())
            .all()
        )
        results = []
        now = datetime.utcnow()
        for r in rows:
            d = r.to_dict()
            # Add elapsed time for UI
            if r.started_at:
                elapsed = int((now - r.started_at).total_seconds())
                if elapsed < 60:
                    d["elapsed_display"] = f"{elapsed}s"
                elif elapsed < 3600:
                    d["elapsed_display"] = f"{elapsed // 60}m {elapsed % 60}s"
                else:
                    d["elapsed_display"] = f"{elapsed // 3600}h {(elapsed % 3600) // 60}m"
            results.append(d)
        return results


def get_cost_by_day(days: int = 14) -> list[dict]:
    """Return daily cost aggregates for chart data."""
    from sqlalchemy import cast, Date

    with get_db() as session:
        rows = (
            session.query(
                func.date(AgentRun.started_at).label("day"),
                func.sum(AgentRun.cost_usd).label("cost"),
                func.count(AgentRun.id).label("runs"),
            )
            .filter(AgentRun.started_at.isnot(None))
            .group_by(func.date(AgentRun.started_at))
            .order_by(func.date(AgentRun.started_at).desc())
            .limit(days)
            .all()
        )
        return [
            {"day": str(r[0]), "cost": round(r[1] or 0, 4), "runs": r[2] or 0}
            for r in reversed(rows)
        ]


def get_agent_roi() -> list[dict]:
    """Return cost vs signals per agent_type for ROI chart."""
    with get_db() as session:
        type_stats = (
            session.query(
                AgentRun.agent_type,
                func.count(AgentRun.id).label("run_count"),
                func.sum(AgentRun.cost_usd).label("total_cost"),
            )
            .group_by(AgentRun.agent_type)
            .all()
        )

        results = []
        for row in type_stats:
            agent_type = row[0]
            total_cost = round(row[2] or 0, 4)

            # Count signals
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
                    signal_count += len(json.loads(signals_json or "[]"))
                except Exception:
                    pass

            results.append({
                "agent_type": agent_type,
                "run_count": row[1] or 0,
                "total_cost": total_cost,
                "signals": signal_count,
            })

        return results


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return latest ProcessEvents for feed initialization."""
    from src.db.models import ProcessEvent

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .order_by(ProcessEvent.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]


# Need datetime for elapsed calculation
from datetime import datetime

# Aliases matching route expectations
list_runs = list_agent_runs
get_run = get_agent_run
get_child_runs = get_agent_children
get_aggregate_metrics = get_agent_metrics
