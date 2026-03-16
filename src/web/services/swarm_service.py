"""Swarm service — reads situation board, strategic context, and sentinel health."""

import json
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

SCHEDULER_DIR = paths.base / "scheduler"


def get_situation_board() -> dict:
    """Load situation board with computed fields."""
    path = SCHEDULER_DIR / "situation_board.json"
    if not path.exists():
        return {"date": "", "missing": True}
    try:
        with open(path) as f:
            board = json.load(f)
        # Compute age
        if board.get("last_updated"):
            updated = datetime.fromisoformat(board["last_updated"])
            board["_age_seconds"] = (datetime.now() - updated).total_seconds()
            board["_age_display"] = _format_age(board["_age_seconds"])
            board["_fresh"] = board["_age_seconds"] < 60
        else:
            board["_age_seconds"] = -1
            board["_fresh"] = False
        return board
    except Exception:
        return {"date": "", "missing": True}


def get_strategic_context() -> dict:
    """Load strategic context with computed fields."""
    path = SCHEDULER_DIR / "strategic_context.json"
    if not path.exists():
        return {"missing": True}
    try:
        with open(path) as f:
            ctx = json.load(f)
        # Compute thesis trend summaries
        momentum = ctx.get("thesis_momentum", {})
        ctx["_thesis_count"] = len(momentum)
        ctx["_rising"] = sum(1 for m in momentum.values() if m.get("trend") == "rising")
        ctx["_declining"] = sum(1 for m in momentum.values() if m.get("trend") == "declining")
        ctx["_stable"] = ctx["_thesis_count"] - ctx["_rising"] - ctx["_declining"]

        # Sort theses by conviction for display
        ctx["_theses_sorted"] = sorted(
            [
                {"name": name, "conviction": m.get("conviction_history", [{}])[-1].get("conviction", 0) if m.get("conviction_history") else 0, "trend": m.get("trend", "new")}
                for name, m in momentum.items()
            ],
            key=lambda x: -x["conviction"],
        )
        return ctx
    except Exception:
        return {"missing": True}


def get_sentinel_health() -> dict:
    """Load sentinel health status."""
    health_path = SCHEDULER_DIR / "health.json"
    state_path = SCHEDULER_DIR / "scheduler_state.json"
    result = {"running": False}

    if health_path.exists():
        try:
            with open(health_path) as f:
                health = json.load(f)
            if health.get("timestamp"):
                age = (datetime.now() - datetime.fromisoformat(health["timestamp"])).total_seconds()
                result["health_age"] = age
                result["running"] = age < 60
                result["health"] = health
        except Exception:
            pass

    if state_path.exists():
        try:
            with open(state_path) as f:
                state = json.load(f)
            sentinel = state.get("sessions", {}).get("sentinel", {})
            result["status"] = sentinel.get("status", "unknown")
            result["last_updated"] = sentinel.get("last_updated", "")
            # Get all session states
            result["sessions"] = state.get("sessions", {})
        except Exception:
            pass

    return result


def get_recent_completions(limit: int = 8) -> list[dict]:
    """Get recent session completion records."""
    completions_dir = SCHEDULER_DIR / "completions"
    if not completions_dir.exists():
        return []
    files = sorted(completions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            data["_filename"] = f.name
            results.append(data)
        except Exception:
            continue
    return results


def get_signal_digest() -> dict:
    """Load signal digest with computed fields."""
    path = SCHEDULER_DIR / "signal_digest.json"
    if not path.exists():
        return {"missing": True}
    try:
        with open(path) as f:
            digest = json.load(f)
        if digest.get("timestamp"):
            updated = datetime.fromisoformat(digest["timestamp"])
            digest["_age_seconds"] = (datetime.now() - updated).total_seconds()
            digest["_age_display"] = _format_age(digest["_age_seconds"])
            digest["_fresh"] = digest["_age_seconds"] < 3600
        # Summarize by source type
        source_counts = digest.get("source_counts", {})
        digest["_source_summary"] = sorted(
            [{"source": k, "count": v} for k, v in source_counts.items()],
            key=lambda x: -x["count"],
        )
        return digest
    except Exception:
        return {"missing": True}


def _format_age(seconds: float) -> str:
    if seconds < 0:
        return "unknown"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"
