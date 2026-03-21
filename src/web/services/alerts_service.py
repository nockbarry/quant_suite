"""Alerts dashboard data service."""
import json
from datetime import datetime, timedelta
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

    # Load adaptive trigger history
    adaptive_triggers, trigger_count_24h = _load_adaptive_triggers()

    return {
        "alerts": alerts,
        "red_flag_count": len([a for a in alerts if a.get("severity") == "red_flag"]),
        "warning_count": len([a for a in alerts if a.get("severity") == "warning"]),
        "info_count": len([a for a in alerts if a.get("severity") == "info"]),
        "last_scan": last_scan,
        "sec_insider": sec_data,
        "treasury_alerts": treasury_data,
        "market_reactions": market_reactions,
        "adaptive_triggers": adaptive_triggers,
        "trigger_count_24h": trigger_count_24h,
    }


def _load_adaptive_triggers() -> tuple[list[dict], int]:
    """Load adaptive trigger history from JSONL log.

    Returns:
        Tuple of (last 20 triggers, count within 24h)
    """
    trigger_log = paths.base / "logs" / "adaptive_triggers.jsonl"
    triggers = []

    if trigger_log.exists():
        try:
            with open(trigger_log) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            triggers.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass

    # Count triggers within last 24h
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    count_24h = len([
        t for t in triggers
        if t.get("timestamp", "") >= cutoff
    ])

    return triggers[-20:], count_24h


def _load_json(path):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None
