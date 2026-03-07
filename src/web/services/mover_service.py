"""Mover service — reads market mover scan results for web display."""

import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path.home() / "quant_results"
LATEST_PATH = RESULTS_DIR / "live" / "market_movers_latest.json"
HISTORY_PATH = RESULTS_DIR / "logs" / "market_movers_history.json"


def get_latest_scan() -> dict:
    """Load latest market mover scan with computed display fields."""
    if not LATEST_PATH.exists():
        return {"missing": True, "movers_found": 0}
    try:
        with open(LATEST_PATH) as f:
            data = json.load(f)
        if data.get("timestamp"):
            try:
                updated = datetime.fromisoformat(data["timestamp"])
                age = (datetime.now() - updated).total_seconds()
                data["_age_seconds"] = age
                data["_age_display"] = _format_age(age)
                data["_fresh"] = age < 7200  # fresh if <2h old
            except Exception:
                data["_fresh"] = False
        return data
    except Exception:
        return {"missing": True, "movers_found": 0}


def get_scan_history(limit: int = 14) -> list[dict]:
    """Load recent scan history entries."""
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        entries = data if isinstance(data, list) else []
        return entries[-limit:]
    except Exception:
        return []


def get_mover_detail(symbol: str) -> dict | None:
    """Get full detail for a specific mover from the latest scan."""
    scan = get_latest_scan()
    if scan.get("missing"):
        return None
    for key in ("top_context", "gainers", "losers", "volume_spikes"):
        for mover in scan.get(key, []):
            if mover.get("symbol") == symbol:
                return mover
    return None


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f}h ago"
    else:
        return f"{seconds / 86400:.1f}d ago"
