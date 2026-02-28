"""State service — reads unified state.json for dashboard."""

import json
import os
from datetime import datetime
from pathlib import Path


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def get_live_state() -> dict:
    """Load current state.json."""
    state_path = _results_dir() / "live" / "state.json"
    if not state_path.exists():
        return {"error": "state.json not found", "positions": [], "market": {}, "sentiment": {}}
    try:
        data = json.loads(state_path.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return {"error": "Failed to parse state.json", "positions": [], "market": {}, "sentiment": {}}


def get_state_age_seconds() -> int:
    """How old is state.json in seconds."""
    state_path = _results_dir() / "live" / "state.json"
    if not state_path.exists():
        return -1
    mtime = state_path.stat().st_mtime
    return int(datetime.utcnow().timestamp() - mtime)


def get_portfolio_summary(state: dict) -> dict:
    """Extract portfolio summary from state."""
    positions = state.get("positions", [])
    total_value = sum(p.get("market_value", 0) for p in positions)
    total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    day_pnl = sum(p.get("day_pnl", 0) for p in positions)

    return {
        "position_count": len(positions),
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_value * 100) if total_value else 0,
        "day_pnl": day_pnl,
        "positions": positions,
    }
