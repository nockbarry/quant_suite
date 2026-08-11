"""Provenance event logging — the activity stream for Athena.

Every significant system event gets logged here, creating the audit trail
that connects data → signal → convergence → decision → execution → outcome.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from src.db.database import get_db
from src.db.models import ProcessEvent
from src.db.sync import append_jsonl


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def generate_id(prefix: str = "evt") -> str:
    """Generate a short unique ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def log_event(
    event_type: str,
    source: str = "autonomy_loop",
    symbol: str | None = None,
    severity: str = "info",
    title: str | None = None,
    detail: str | dict | None = None,
    parent_event_id: str | None = None,
    decision_id: str | None = None,
    thesis_id: str | None = None,
    agent_run_id: str | None = None,
    signal_id: str | None = None,
) -> str:
    """Log a process event to DB and JSONL file.

    Returns the event ID.
    """
    event_id = generate_id("evt")
    now = datetime.utcnow()

    if title is None:
        title = event_type.replace("_", " ").title()

    detail_str = ""
    if detail is not None:
        if isinstance(detail, dict):
            detail_str = json.dumps(detail)
        else:
            detail_str = str(detail)

    event = ProcessEvent(
        id=event_id,
        timestamp=now,
        event_type=event_type,
        source=source,
        symbol=symbol,
        severity=severity,
        title=title,
        detail=detail_str,
        parent_event_id=parent_event_id,
        decision_id=decision_id,
        thesis_id=thesis_id,
        agent_run_id=agent_run_id,
        signal_id=signal_id,
    )

    # Build dict before DB session for JSONL backup
    event_dict = {
        "id": event_id,
        "timestamp": now.isoformat(),
        "event_type": event_type,
        "source": source,
        "symbol": symbol,
        "severity": severity,
        "title": title,
        "detail": detail_str,
        "parent_event_id": parent_event_id,
        "decision_id": decision_id,
        "thesis_id": thesis_id,
        "agent_run_id": agent_run_id,
        "signal_id": signal_id,
    }

    # Write to DB
    try:
        with get_db() as session:
            session.add(event)
    except Exception as e:
        # Don't let DB failures crash the event loop
        print(f"WARN: Failed to log event to DB: {e}")

    # Also append to JSONL for backward compat
    try:
        from src.core.logrotate import rotate_if_large

        log_path = _results_dir() / "logs" / "process_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rotate_if_large(log_path)
        append_jsonl(log_path, event_dict)
    except Exception as e:
        print(f"WARN: Failed to log event to JSONL: {e}")

    return event_id


def log_signal_detected(
    symbol: str,
    source: str,
    signal_id: str,
    description: str,
    confidence: float,
    direction: str,
    parent_event_id: str | None = None,
) -> str:
    """Convenience: log a signal detection event."""
    return log_event(
        event_type="signal_detected",
        source=source,
        symbol=symbol,
        title=f"{direction.upper()} signal on {symbol} ({source})",
        detail={
            "signal_id": signal_id,
            "description": description,
            "confidence": confidence,
            "direction": direction,
        },
        signal_id=signal_id,
        parent_event_id=parent_event_id,
    )


def log_convergence_detected(
    symbol: str,
    signal_count: int,
    weighted_score: float,
    direction: str,
    convergence_id: str,
    parent_event_id: str | None = None,
) -> str:
    """Convenience: log a convergence detection event."""
    return log_event(
        event_type="convergence_detected",
        source="autonomy_loop",
        symbol=symbol,
        severity="warning" if signal_count >= 4 else "info",
        title=f"Convergence: {signal_count} {direction} signals on {symbol}",
        detail={
            "convergence_id": convergence_id,
            "signal_count": signal_count,
            "weighted_score": weighted_score,
            "direction": direction,
        },
        parent_event_id=parent_event_id,
    )


def log_llm_called(
    interaction_id: str,
    model: str,
    tokens: int,
    cost: float,
    trigger_type: str,
    parent_event_id: str | None = None,
) -> str:
    """Convenience: log an LLM API call."""
    return log_event(
        event_type="llm_called",
        source="llm",
        title=f"LLM called ({model}, {tokens} tokens, ${cost:.3f})",
        detail={
            "interaction_id": interaction_id,
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "trigger_type": trigger_type,
        },
        parent_event_id=parent_event_id,
    )


def log_trade_event(
    event_type: str,
    decision_id: str,
    symbol: str,
    detail: dict,
    severity: str = "info",
    parent_event_id: str | None = None,
) -> str:
    """Convenience: log trade-related events."""
    action = detail.get("action", "")
    title_map = {
        "trade_submitted": f"Trade submitted: {action} {symbol}",
        "trade_filled": f"Trade filled: {action} {symbol} @ ${detail.get('price', '?')}",
        "trade_failed": f"Trade FAILED: {action} {symbol} — {detail.get('reason', '?')}",
        "decision_proposed": f"Decision: {action} {symbol} @ {detail.get('confidence', 0):.0%}",
        "decision_challenged": f"Adversarial check on {symbol}",
        "decision_approved": f"Decision approved: {action} {symbol}",
        "decision_rejected": f"Decision rejected: {action} {symbol}",
    }

    return log_event(
        event_type=event_type,
        source="autonomy_loop",
        symbol=symbol,
        severity=severity,
        title=title_map.get(event_type, f"{event_type}: {symbol}"),
        detail=detail,
        decision_id=decision_id,
        parent_event_id=parent_event_id,
    )
