"""Health service -- system health, autonomy status, and DB statistics."""

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, text

from src.db.database import get_db, get_sync_engine
from src.db.models import (
    AgentRun,
    AutonomyCheck,
    Company,
    DecisionConvergence,
    DecisionRecord,
    LearningRecord,
    LLMInteraction,
    ProcessEvent,
    Sector,
    SignalProvenanceRecord,
    ThesisRecord,
)


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def get_system_health() -> dict:
    """Check service heartbeats, DB stats, cron status."""
    now = datetime.utcnow()

    # State.json freshness
    state_path = _results_dir() / "live" / "state.json"
    state_age_seconds = -1
    state_exists = state_path.exists()
    if state_exists:
        state_age_seconds = int(now.timestamp() - state_path.stat().st_mtime)

    # DB connectivity
    db_ok = False
    try:
        with get_db() as session:
            session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # Recent agent activity (last hour)
    recent_agents = 0
    with get_db() as session:
        one_hour_ago = now - timedelta(hours=1)
        recent_agents = (
            session.query(func.count(AgentRun.id))
            .filter(AgentRun.started_at >= one_hour_ago)
            .scalar()
            or 0
        )

    # Last autonomy check
    last_check = None
    with get_db() as session:
        row = (
            session.query(AutonomyCheck)
            .order_by(AutonomyCheck.timestamp.desc())
            .first()
        )
        if row:
            last_check = row.to_dict()

    # Recent errors (last hour)
    recent_errors = 0
    with get_db() as session:
        one_hour_ago = now - timedelta(hours=1)
        recent_errors = (
            session.query(func.count(ProcessEvent.id))
            .filter(
                ProcessEvent.timestamp >= one_hour_ago,
                ProcessEvent.severity.in_(["warning", "critical"]),
            )
            .scalar()
            or 0
        )

    # Cron status -- check known output files for recency
    cron_checks = {}
    cron_files = {
        "news_collect": _results_dir() / "live" / "research" / "news_summary.json",
        "congressional_collect": _results_dir() / "live" / "research" / "congressional_trades.json",
        "insider_collect": _results_dir() / "live" / "research" / "insider_trades.json",
        "research_prep": _results_dir() / "live" / "research" / "feature_cache.json",
    }
    for name, path in cron_files.items():
        if path.exists():
            age = int(now.timestamp() - path.stat().st_mtime)
            cron_checks[name] = {"exists": True, "age_seconds": age, "stale": age > 86400}
        else:
            cron_checks[name] = {"exists": False, "age_seconds": -1, "stale": True}

    # Overall health
    issues = []
    if not db_ok:
        issues.append("Database unreachable")
    if not state_exists:
        issues.append("state.json missing")
    elif state_age_seconds > 600:
        issues.append(f"state.json stale ({state_age_seconds}s old)")
    if recent_errors > 5:
        issues.append(f"{recent_errors} warnings/errors in last hour")

    health_status = "healthy" if not issues else "degraded" if len(issues) <= 2 else "unhealthy"

    return {
        "status": health_status,
        "issues": issues,
        "checked_at": now.isoformat(),
        "database": {"connected": db_ok},
        "state_json": {
            "exists": state_exists,
            "age_seconds": state_age_seconds,
        },
        "recent_agents": recent_agents,
        "recent_errors": recent_errors,
        "last_autonomy_check": last_check,
        "cron_status": cron_checks,
    }


def get_autonomy_status() -> dict:
    """Return recent autonomy check records and summary."""
    with get_db() as session:
        rows = (
            session.query(AutonomyCheck)
            .order_by(AutonomyCheck.timestamp.desc())
            .limit(20)
            .all()
        )
        checks = [r.to_dict() for r in rows]

        # Summary over last 24h
        yesterday = datetime.utcnow() - timedelta(hours=24)
        day_stats = (
            session.query(
                func.count(AutonomyCheck.id),
                func.sum(AutonomyCheck.alerts_found),
                func.sum(AutonomyCheck.convergences_found),
                func.sum(AutonomyCheck.rules_triggered),
                func.sum(AutonomyCheck.trades_executed),
                func.sum(AutonomyCheck.llm_calls_made),
                func.avg(AutonomyCheck.duration_ms),
            )
            .filter(AutonomyCheck.timestamp >= yesterday)
            .first()
        )

    total_checks = day_stats[0] or 0
    return {
        "recent_checks": checks,
        "last_24h": {
            "total_checks": total_checks,
            "total_alerts": day_stats[1] or 0,
            "total_convergences": day_stats[2] or 0,
            "total_rules_triggered": day_stats[3] or 0,
            "total_trades_executed": day_stats[4] or 0,
            "total_llm_calls": day_stats[5] or 0,
            "avg_duration_ms": round(day_stats[6] or 0, 1),
        },
    }


def get_db_stats() -> dict:
    """Row counts and DB file size for every table."""
    with get_db() as session:
        table_counts = {
            "companies": session.query(func.count(Company.symbol)).scalar() or 0,
            "sectors": session.query(func.count(Sector.sector)).scalar() or 0,
            "theses": session.query(func.count(ThesisRecord.id)).scalar() or 0,
            "decisions": session.query(func.count(DecisionRecord.id)).scalar() or 0,
            "learnings": session.query(func.count(LearningRecord.id)).scalar() or 0,
            "signals": session.query(func.count(SignalProvenanceRecord.signal_id)).scalar() or 0,
            "convergences": session.query(func.count(DecisionConvergence.id)).scalar() or 0,
            "agent_runs": session.query(func.count(AgentRun.id)).scalar() or 0,
            "process_events": session.query(func.count(ProcessEvent.id)).scalar() or 0,
            "llm_interactions": session.query(func.count(LLMInteraction.id)).scalar() or 0,
            "autonomy_checks": session.query(func.count(AutonomyCheck.id)).scalar() or 0,
        }

    # DB file size
    db_path = _results_dir() / "athena.db"
    db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

    return {
        "table_counts": table_counts,
        "total_rows": sum(table_counts.values()),
        "db_size_bytes": db_size_bytes,
        "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
    }
