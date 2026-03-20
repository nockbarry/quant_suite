"""Alerts dashboard data service."""
import json
from datetime import datetime
from src.core.paths import paths


def get_alerts_dashboard_data() -> dict:
    """Load cross-reference alerts for the web dashboard."""
    alerts_file = paths.live / "cross_reference_alerts.json"

    alerts = []
    last_scan = None

    if alerts_file.exists():
        try:
            with open(alerts_file) as f:
                data = json.load(f)
            alerts = data.get("alerts", [])
            last_scan = data.get("timestamp")
        except (json.JSONDecodeError, OSError):
            pass

    # Also load SEC insider and treasury data for context
    sec_data = _load_json(paths.live / "sec_insider_alerts.json")
    treasury_data = _load_json(paths.live / "treasury_alerts.json")
    market_reactions = _load_json(paths.live / "market_reactions.json")

    return {
        "alerts": alerts,
        "red_flag_count": len([a for a in alerts if a.get("severity") == "red_flag"]),
        "warning_count": len([a for a in alerts if a.get("severity") == "warning"]),
        "info_count": len([a for a in alerts if a.get("severity") == "info"]),
        "last_scan": last_scan,
        "sec_insider": sec_data,
        "treasury_alerts": treasury_data,
        "market_reactions": market_reactions,
    }


def _load_json(path):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None
