"""Autonomous mode detection and scheduler data ingestion helpers.

Provides:
1. is_autonomous() — check if running in autonomous scheduled mode
2. get_session_completions_since() — completed sessions from scheduler
3. get_thesis_changes_since() — thesis conviction/status changes
4. get_new_research_since() — new research results and briefings
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.core.paths import paths

logger = logging.getLogger(__name__)

SCHEDULER_DIR = paths.base / "scheduler"
RESULTS_DIR = paths.base


def is_autonomous() -> bool:
    """Check if running in autonomous scheduled mode.

    Written by session_wrapper.sh before launch, removed after.
    Skills can check this to adjust behavior (skip user questions,
    auto-approve trades, etc.)
    """
    return (SCHEDULER_DIR / "autonomous_mode.json").exists()


def get_autonomous_config() -> dict:
    """Get autonomous mode configuration if active."""
    config_path = SCHEDULER_DIR / "autonomous_mode.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            return {"active": True}
    return {"active": False}


# --- Scheduler data ingestion helpers for operator loop ---


def get_session_completions_since(since: datetime) -> list[dict[str, Any]]:
    """Return completed autonomous sessions since the given timestamp.

    Reads from ~/quant_results/scheduler/completions/*.json
    Each file is written by session_wrapper.sh after a one-shot session finishes.
    """
    completions_dir = SCHEDULER_DIR / "completions"
    if not completions_dir.exists():
        return []

    results = []
    for path in sorted(completions_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            completed_at = datetime.fromisoformat(data.get("completed_at", "2000-01-01"))
            if completed_at > since:
                data["_file"] = path.name
                results.append(data)
        except Exception as e:
            logger.debug(f"Error reading completion {path}: {e}")

    return results


def get_thesis_changes_since(since: datetime) -> list[dict[str, Any]]:
    """Detect thesis conviction/status changes since last check.

    Compares current YAML files against a cached snapshot stored in
    ~/quant_results/scheduler/thesis_snapshot.json.  Returns a list of
    change dicts and updates the snapshot.
    """
    theses_dir = RESULTS_DIR / "theses"
    snapshot_path = SCHEDULER_DIR / "thesis_snapshot.json"

    if not theses_dir.exists():
        return []

    # Load previous snapshot
    prev_snapshot: dict[str, dict] = {}
    if snapshot_path.exists():
        try:
            with open(snapshot_path) as f:
                prev_snapshot = json.load(f)
        except Exception:
            pass

    # Build current snapshot and detect changes
    current_snapshot: dict[str, dict] = {}
    changes: list[dict[str, Any]] = []

    for thesis_file in theses_dir.glob("*.yaml"):
        try:
            with open(thesis_file) as f:
                thesis = yaml.safe_load(f)
            if not thesis:
                continue

            tid = thesis.get("id", thesis_file.stem)
            name = thesis.get("name", "Unknown")
            conviction = thesis.get("conviction", 50)
            status = thesis.get("status", "active")

            current_snapshot[tid] = {
                "name": name,
                "conviction": conviction,
                "status": status,
            }

            prev = prev_snapshot.get(tid)
            if prev is None:
                changes.append({
                    "type": "new_thesis",
                    "thesis_id": tid,
                    "name": name,
                    "conviction": conviction,
                    "status": status,
                })
            else:
                if prev.get("conviction") != conviction:
                    changes.append({
                        "type": "conviction_change",
                        "thesis_id": tid,
                        "name": name,
                        "old_conviction": prev.get("conviction"),
                        "new_conviction": conviction,
                    })
                if prev.get("status") != status:
                    changes.append({
                        "type": "status_change",
                        "thesis_id": tid,
                        "name": name,
                        "old_status": prev.get("status"),
                        "new_status": status,
                    })
        except Exception as e:
            logger.debug(f"Error reading thesis {thesis_file}: {e}")

    # Detect removed theses
    for tid, prev in prev_snapshot.items():
        if tid not in current_snapshot:
            changes.append({
                "type": "thesis_removed",
                "thesis_id": tid,
                "name": prev.get("name", "Unknown"),
            })

    # Save updated snapshot
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(snapshot_path, "w") as f:
            json.dump(current_snapshot, f, indent=2)
    except Exception as e:
        logger.debug(f"Error saving thesis snapshot: {e}")

    return changes


def get_new_research_since(since: datetime) -> list[dict[str, Any]]:
    """Find new research results and briefings since the given timestamp.

    Scans:
    - ~/quant_results/research_results/ for new research files
    - ~/quant_results/briefings/ for new briefings
    - ~/quant_results/scheduler/trade_triggers.json for convergence triggers
    """
    results: list[dict[str, Any]] = []
    since_ts = since.timestamp()

    # Scan research results
    research_dir = RESULTS_DIR / "research_results"
    if research_dir.exists():
        for path in research_dir.glob("*.json"):
            try:
                if path.stat().st_mtime > since_ts:
                    with open(path) as f:
                        data = json.load(f)
                    results.append({
                        "type": "research",
                        "file": path.name,
                        "title": data.get("title", path.stem),
                        "summary": data.get("summary", "")[:200],
                        "symbols": data.get("symbols", []),
                        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    })
            except Exception:
                continue

    # Scan briefings
    briefings_dir = RESULTS_DIR / "briefings"
    if briefings_dir.exists():
        for path in briefings_dir.glob("*.json"):
            try:
                if path.stat().st_mtime > since_ts:
                    with open(path) as f:
                        data = json.load(f)
                    results.append({
                        "type": "briefing",
                        "file": path.name,
                        "title": data.get("title", path.stem),
                        "summary": data.get("summary", "")[:200],
                        "symbols": data.get("symbols", data.get("watchlist", [])),
                        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    })
            except Exception:
                continue

    # Read trade triggers
    triggers_path = SCHEDULER_DIR / "trade_triggers.json"
    if triggers_path.exists():
        try:
            with open(triggers_path) as f:
                trigger_data = json.load(f)
            for trigger in trigger_data.get("triggers", []):
                created = trigger.get("created_at", "")
                if created:
                    try:
                        trigger_time = datetime.fromisoformat(created)
                        if trigger_time > since and not trigger.get("consumed", False):
                            results.append({
                                "type": "trade_trigger",
                                "symbol": trigger.get("symbol", ""),
                                "direction": trigger.get("direction", ""),
                                "signal_count": trigger.get("signal_count", 0),
                                "source": trigger.get("source", "operator"),
                                "created_at": created,
                            })
                    except ValueError:
                        continue
        except Exception:
            pass

    return results


def write_trade_trigger(
    symbol: str,
    direction: str,
    signal_count: int,
    signals: list[str],
    source: str = "operator",
) -> None:
    """Write a trade trigger for the health monitor to pick up.

    Called by operator loop when strong convergences are detected.
    Health monitor reads these and can launch trade-decision sessions.
    """
    triggers_path = SCHEDULER_DIR / "trade_triggers.json"
    triggers_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = {"triggers": [], "last_checked": None}
        if triggers_path.exists():
            with open(triggers_path) as f:
                data = json.load(f)

        data["triggers"].append({
            "symbol": symbol,
            "direction": direction,
            "signal_count": signal_count,
            "signals": signals,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "consumed": False,
        })

        with open(triggers_path, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        logger.error(f"Error writing trade trigger: {e}")

    # Log to ProcessEvent audit trail
    try:
        from src.autonomy.provenance import log_event
        log_event(
            event_type="trade_trigger",
            source=f"scheduler:{source}",
            symbol=symbol,
            severity="warning",
            title=f"Trade trigger: {signal_count} {direction} signals on {symbol}",
            detail={
                "direction": direction,
                "signal_count": signal_count,
                "signals": signals,
                "source": source,
            },
        )
    except Exception:
        pass


def write_session_completion(
    session_type: str,
    success: bool,
    summary: str,
    key_findings: list[str] | None = None,
    symbols: list[str] | None = None,
    duration_seconds: float = 0,
) -> None:
    """Write a session completion record for the operator to pick up.

    Called by session_wrapper.sh post-completion hook or by skills directly.
    """
    completions_dir = SCHEDULER_DIR / "completions"
    completions_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    filename = f"{session_type}_{now.strftime('%Y%m%d_%H%M%S')}.json"

    record = {
        "session_type": session_type,
        "success": success,
        "summary": summary,
        "key_findings": key_findings or [],
        "symbols": symbols or [],
        "duration_seconds": duration_seconds,
        "completed_at": now.isoformat(),
    }

    try:
        with open(completions_dir / filename, "w") as f:
            json.dump(record, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing session completion: {e}")

    # Log to ProcessEvent audit trail
    try:
        from src.autonomy.provenance import log_event
        log_event(
            event_type="session_completed",
            source=f"scheduler:{session_type}",
            severity="info" if success else "warning",
            title=f"Session {session_type}: {'completed' if success else 'failed'}",
            detail={
                "session_type": session_type,
                "success": success,
                "summary": summary[:500],
                "key_findings": key_findings or [],
                "symbols": symbols or [],
                "duration_seconds": duration_seconds,
            },
        )
    except Exception:
        pass
