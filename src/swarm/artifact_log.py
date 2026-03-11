"""Cross-session artifact provenance logging.

Tracks when sessions read upstream artifacts, enabling verification
that the information flow pipeline is working.

Usage:
    from src.swarm.artifact_log import log_artifact_read

    log_artifact_read("morning-briefing", "eod_review", "/path/to/file.json", found=True)
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ARTIFACT_LOG_PATH = (
    Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    / "scheduler"
    / "artifact_reads.jsonl"
)


def log_artifact_read(
    session_type: str,
    artifact_type: str,
    artifact_path: str = "",
    found: bool = True,
    detail: str = "",
):
    """Log that a session read (or failed to find) an upstream artifact.

    Args:
        session_type: The session reading the artifact (e.g. "morning-briefing")
        artifact_type: What kind of artifact (e.g. "eod_review", "evening_research", "analyst_assessment")
        artifact_path: File path of the artifact (optional)
        found: Whether the artifact was found and had content
        detail: Brief note about what was found
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_type": session_type,
        "artifact_type": artifact_type,
        "artifact_path": artifact_path,
        "found": found,
        "detail": detail[:200],
    }

    try:
        ARTIFACT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ARTIFACT_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log artifact read: {e}")


def get_recent_reads(hours: int = 24) -> list[dict]:
    """Get artifact reads from the last N hours."""
    if not ARTIFACT_LOG_PATH.exists():
        return []

    cutoff = datetime.now().timestamp() - (hours * 3600)
    reads = []

    try:
        for line in ARTIFACT_LOG_PATH.read_text().strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts >= cutoff:
                reads.append(entry)
    except Exception as e:
        logger.debug(f"Failed to read artifact log: {e}")

    return reads


def check_flow_health() -> dict:
    """Check if cross-session information flow is working.

    Returns a dict with pass/fail for each expected flow.
    """
    reads = get_recent_reads(hours=24)

    # Expected flows (session → artifact it should read)
    expected_flows = {
        "morning-briefing → eod_review": any(
            r["session_type"] == "morning-briefing" and r["artifact_type"] == "eod_review"
            for r in reads
        ),
        "morning-briefing → evening_research": any(
            r["session_type"] == "morning-briefing" and r["artifact_type"] == "evening_research"
            for r in reads
        ),
        "trade-decision → analyst_assessment": any(
            r["session_type"] == "trade-decision" and r["artifact_type"] == "analyst_assessment"
            for r in reads
        ),
        "trade-decision → calibration": any(
            r["session_type"] == "trade-decision" and r["artifact_type"] == "calibration"
            for r in reads
        ),
        "internal-review → previous_review": any(
            r["session_type"] == "internal-review" and r["artifact_type"] == "previous_review"
            for r in reads
        ),
    }

    active_flows = sum(1 for v in expected_flows.values() if v)
    total = len(expected_flows)

    return {
        "flows": expected_flows,
        "active": active_flows,
        "total": total,
        "health": "healthy" if active_flows >= 3 else "degraded" if active_flows >= 1 else "disconnected",
    }
