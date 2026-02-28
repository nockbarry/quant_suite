"""Dual-write layer: DB writes also update YAML/JSON files for backward compat.

state.json remains the real-time cache. This module ensures that when data is
written to the DB, the corresponding file is also updated.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import yaml


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def _json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def sync_company_to_file(data: dict):
    """Write company data to YAML file."""
    symbol = data.get("symbol", "")
    if not symbol:
        return
    path = _results_dir() / "knowledge" / "companies" / f"{symbol}.yaml"
    _ensure_dir(path)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def sync_sector_to_file(data: dict):
    """Write sector data to YAML file."""
    sector = data.get("sector", "")
    if not sector:
        return
    path = _results_dir() / "knowledge" / "sectors" / f"{sector}.yaml"
    _ensure_dir(path)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def sync_thesis_to_file(data: dict):
    """Write thesis data to YAML file."""
    thesis_id = data.get("id", "")
    if not thesis_id:
        return
    path = _results_dir() / "theses" / f"{thesis_id}.yaml"
    _ensure_dir(path)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def sync_learning_to_file(data: dict):
    """Append learning to monthly JSON file."""
    created = data.get("created", "")
    if isinstance(created, str) and created:
        month_key = created[:7]  # YYYY-MM
    else:
        month_key = datetime.utcnow().strftime("%Y-%m")

    path = _results_dir() / "learnings" / f"{month_key}.json"
    _ensure_dir(path)

    existing = []
    if path.exists():
        try:
            content = json.loads(path.read_text())
            existing = content if isinstance(content, list) else content.get("learnings", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Update or append
    found = False
    for i, item in enumerate(existing):
        if item.get("id") == data.get("id"):
            existing[i] = data
            found = True
            break
    if not found:
        existing.append(data)

    path.write_text(json.dumps(existing, indent=2, default=_json_serial))


def sync_decision_to_file(data: dict):
    """Append/update decision in daily JSON file."""
    timestamp = data.get("timestamp", "")
    if isinstance(timestamp, str) and timestamp:
        date_key = timestamp[:10]  # YYYY-MM-DD
    else:
        date_key = datetime.utcnow().strftime("%Y-%m-%d")

    path = _results_dir() / "decisions" / f"decisions_{date_key}.json"
    _ensure_dir(path)

    existing = []
    if path.exists():
        try:
            content = json.loads(path.read_text())
            existing = content if isinstance(content, list) else content.get("decisions", [])
        except (json.JSONDecodeError, KeyError):
            pass

    found = False
    for i, item in enumerate(existing):
        if item.get("id") == data.get("id"):
            existing[i] = data
            found = True
            break
    if not found:
        existing.append(data)

    path.write_text(json.dumps(existing, indent=2, default=_json_serial))


def sync_signal_provenance_to_file(data: dict):
    """Write signal provenance to individual JSON file."""
    signal_id = data.get("signal_id", "")
    if not signal_id:
        return
    path = _results_dir() / "signal_provenance" / f"{signal_id}.json"
    _ensure_dir(path)
    path.write_text(json.dumps(data, indent=2, default=_json_serial))


def append_jsonl(path: Path, data: dict):
    """Append a JSON line to a JSONL file."""
    _ensure_dir(path)
    with open(path, "a") as f:
        f.write(json.dumps(data, default=_json_serial) + "\n")
