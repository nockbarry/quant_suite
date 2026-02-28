"""Health monitoring — heartbeat system for all Athena services."""

import json
import os
from datetime import datetime
from pathlib import Path


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def write_heartbeat(service_name: str, **extra):
    """Write a heartbeat file for a service."""
    heartbeat = {
        "service": service_name,
        "timestamp": datetime.utcnow().isoformat(),
        **extra,
    }
    health_dir = _results_dir() / "live" / "health"
    health_dir.mkdir(parents=True, exist_ok=True)
    (health_dir / f"{service_name}.json").write_text(json.dumps(heartbeat, indent=2))


def read_heartbeat(service_name: str) -> dict | None:
    """Read a service heartbeat. Returns None if not found."""
    path = _results_dir() / "live" / "health" / f"{service_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_all_heartbeats() -> dict[str, dict]:
    """Get heartbeats for all services."""
    health_dir = _results_dir() / "live" / "health"
    if not health_dir.exists():
        return {}

    heartbeats = {}
    for json_file in health_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            service = data.get("service", json_file.stem)
            heartbeats[service] = data
        except (json.JSONDecodeError, OSError):
            continue

    return heartbeats


def check_service_health(service_name: str, max_age_seconds: int = 600) -> dict:
    """Check if a service is healthy based on heartbeat age."""
    heartbeat = read_heartbeat(service_name)
    if heartbeat is None:
        return {"service": service_name, "status": "unknown", "reason": "No heartbeat found"}

    try:
        ts = datetime.fromisoformat(heartbeat["timestamp"])
        age = (datetime.utcnow() - ts).total_seconds()
    except (KeyError, ValueError):
        return {"service": service_name, "status": "unknown", "reason": "Invalid timestamp"}

    if age > max_age_seconds:
        return {"service": service_name, "status": "stale", "age_seconds": int(age), "reason": f"Heartbeat {int(age)}s old (max {max_age_seconds}s)"}

    return {"service": service_name, "status": "healthy", "age_seconds": int(age), **heartbeat}
