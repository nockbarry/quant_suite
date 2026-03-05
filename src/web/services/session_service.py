"""Session service — queries for autonomous session activity and news matches."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func

from src.db.database import get_db
from src.db.models import ProcessEvent

SCHEDULER_DIR = Path.home() / "quant_results" / "scheduler"

# Event types logged by the autonomous pipeline
SESSION_EVENT_TYPES = {
    "session_started",
    "session_completed",
    "session_failed",
    "operator_check",
    "trade_trigger",
    "thesis_change",
    "news_thesis_match",
}


def get_todays_sessions() -> list[dict]:
    """Get today's autonomous sessions grouped by type.

    Returns ProcessEvents where source starts with 'scheduler:',
    grouped by session type with start/end times.
    """
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(
                ProcessEvent.source.like("scheduler:%"),
                ProcessEvent.event_type.in_(["session_started", "session_completed", "session_failed"]),
                ProcessEvent.timestamp >= today,
            )
            .order_by(ProcessEvent.timestamp.asc())
            .all()
        )

        # Group by session type
        sessions: dict[str, dict] = {}
        for row in rows:
            source = row.source or ""
            session_type = source.replace("scheduler:", "")
            if session_type not in sessions:
                sessions[session_type] = {
                    "session_type": session_type,
                    "events": [],
                    "started_at": None,
                    "completed_at": None,
                    "status": "unknown",
                }
            s = sessions[session_type]
            s["events"].append(row.to_dict())
            if row.event_type == "session_started":
                s["started_at"] = row.timestamp.isoformat() if row.timestamp else None
                s["status"] = "running"
            elif row.event_type == "session_completed":
                s["completed_at"] = row.timestamp.isoformat() if row.timestamp else None
                s["status"] = "completed"
            elif row.event_type == "session_failed":
                s["completed_at"] = row.timestamp.isoformat() if row.timestamp else None
                s["status"] = "failed"

        return list(sessions.values())


def get_live_status() -> dict:
    """Get current live status from scheduler state and lock files."""
    result = {
        "scheduler_state": None,
        "running_sessions": [],
        "last_updated": None,
    }

    # Read scheduler state
    state_file = SCHEDULER_DIR / "scheduler_state.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                result["scheduler_state"] = json.load(f)
                result["last_updated"] = result["scheduler_state"].get("last_updated")
        except Exception:
            pass

    # Check lock files for running sessions
    locks_dir = SCHEDULER_DIR / "locks"
    if locks_dir.exists():
        for lock_file in locks_dir.glob("*.lock"):
            session_type = lock_file.stem
            try:
                pid = lock_file.read_text().strip()
                result["running_sessions"].append({
                    "session_type": session_type,
                    "pid": pid,
                    "lock_file": str(lock_file),
                })
            except Exception:
                pass

    return result


def get_news_matches(hours: int = 24) -> list[dict]:
    """Get recent news-thesis match events."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(
                ProcessEvent.event_type == "news_thesis_match",
                ProcessEvent.timestamp >= cutoff,
            )
            .order_by(ProcessEvent.timestamp.desc())
            .limit(50)
            .all()
        )
        return [r.to_dict() for r in rows]


def get_day_timeline(date_str: str | None = None) -> list[dict]:
    """Get all autonomous events for a given day, chronological."""
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    next_day = day + timedelta(days=1)

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(
                ProcessEvent.source.like("scheduler:%") | ProcessEvent.event_type.in_(SESSION_EVENT_TYPES),
                ProcessEvent.timestamp >= day,
                ProcessEvent.timestamp < next_day,
            )
            .order_by(ProcessEvent.timestamp.asc())
            .limit(500)
            .all()
        )
        return [r.to_dict() for r in rows]


def get_session_stats(days: int = 7) -> dict:
    """Get aggregate stats for autonomous sessions."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    with get_db() as session:
        # Count by event type
        counts = (
            session.query(
                ProcessEvent.event_type,
                func.count(ProcessEvent.id),
            )
            .filter(
                ProcessEvent.event_type.in_(SESSION_EVENT_TYPES),
                ProcessEvent.timestamp >= cutoff,
            )
            .group_by(ProcessEvent.event_type)
            .all()
        )

        stats = {
            "period_days": days,
            "sessions_started": 0,
            "sessions_completed": 0,
            "sessions_failed": 0,
            "operator_checks": 0,
            "trade_triggers": 0,
            "news_matches": 0,
            "thesis_changes": 0,
        }

        for event_type, count in counts:
            if event_type == "session_started":
                stats["sessions_started"] = count
            elif event_type == "session_completed":
                stats["sessions_completed"] = count
            elif event_type == "session_failed":
                stats["sessions_failed"] = count
            elif event_type == "operator_check":
                stats["operator_checks"] = count
            elif event_type == "trade_trigger":
                stats["trade_triggers"] = count
            elif event_type == "news_thesis_match":
                stats["news_matches"] = count
            elif event_type == "thesis_change":
                stats["thesis_changes"] = count

        return stats


def get_operator_checks(hours: int = 24, limit: int = 20) -> list[dict]:
    """Get recent operator check events."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    with get_db() as session:
        rows = (
            session.query(ProcessEvent)
            .filter(
                ProcessEvent.event_type == "operator_check",
                ProcessEvent.timestamp >= cutoff,
            )
            .order_by(ProcessEvent.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]
