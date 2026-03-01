"""Athena Event Bus — thin emit() that wires provenance, signals, and quality.

Every call to emit() does three things:
1. Delegates to autonomy/provenance.log_event() for DB + JSONL writes
2. Fires auto side-effects based on event_type prefix:
   - signal_*  → auto-creates SignalProvenanceRecord
   - decision_created with signal_ids → populates DecisionSignalLink
   - trade_outcome with signal_ids + pnl → updates signal quality + provenance
3. Calls registered subscriber callbacks (pattern-matched)

Every call is wrapped in try/except — never crashes the caller.
"""

import fnmatch
import json
import logging
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)

# Subscriber registry: pattern -> list of callbacks
_subscribers: dict[str, list[Callable]] = {}


def emit(
    event_type: str,
    source: str = "",
    symbol: str | None = None,
    severity: str = "info",
    title: str = "",
    detail: str | dict | None = None,
    parent_event_id: str | None = None,
    decision_id: str | None = None,
    thesis_id: str | None = None,
    agent_run_id: str | None = None,
    signal_id: str | None = None,
    **kwargs,
) -> str:
    """Emit an event into the Athena provenance chain.

    Returns the event_id on success, empty string on failure.
    Extra kwargs are passed to side-effect handlers (e.g. signal_ids, pnl).
    """
    event_id = ""
    try:
        from src.autonomy.provenance import log_event

        detail_for_log = detail
        if isinstance(detail, dict):
            # Merge kwargs into detail for richer provenance
            merged = {**detail, **{k: v for k, v in kwargs.items() if v is not None}}
            detail_for_log = merged
        elif kwargs:
            detail_for_log = detail or {}
            if isinstance(detail_for_log, str) and detail_for_log:
                detail_for_log = {"text": detail_for_log, **kwargs}
            else:
                detail_for_log = kwargs

        event_id = log_event(
            event_type=event_type,
            source=source,
            symbol=symbol,
            severity=severity,
            title=title,
            detail=detail_for_log,
            parent_event_id=parent_event_id,
            decision_id=decision_id,
            thesis_id=thesis_id,
            agent_run_id=agent_run_id,
            signal_id=signal_id,
        )
    except Exception as e:
        logger.warning(f"Event bus log_event failed for {event_type}: {e}")

    # Fire auto side-effects
    try:
        if event_type.startswith("signal_"):
            _handle_signal_provenance(event_id, event_type, symbol, source, severity, kwargs)
    except Exception as e:
        logger.debug(f"Signal provenance side-effect failed: {e}")

    try:
        if event_type == "decision_created" and kwargs.get("signal_ids"):
            _handle_decision_signals(event_id, kwargs)
    except Exception as e:
        logger.debug(f"Decision signal link side-effect failed: {e}")

    try:
        if event_type == "trade_outcome":
            _handle_trade_outcome(event_id, symbol, kwargs)
    except Exception as e:
        logger.debug(f"Trade outcome side-effect failed: {e}")

    # Fire subscriber callbacks
    try:
        _notify_subscribers(event_type, event_id, source, symbol, severity, title, detail, kwargs)
    except Exception as e:
        logger.debug(f"Subscriber notification failed: {e}")

    return event_id


def subscribe(event_pattern: str, callback: Callable) -> None:
    """Register a callback for events matching a glob pattern.

    Examples:
        subscribe("signal_*", my_handler)
        subscribe("thesis_*", on_thesis_event)
        subscribe("*", log_everything)
    """
    if event_pattern not in _subscribers:
        _subscribers[event_pattern] = []
    _subscribers[event_pattern].append(callback)


# ---------------------------------------------------------------------------
# Private side-effect handlers
# ---------------------------------------------------------------------------


def _handle_signal_provenance(
    event_id: str,
    event_type: str,
    symbol: str | None,
    source: str,
    severity: str,
    kwargs: dict,
) -> None:
    """Create a SignalProvenanceRecord in DB + file for signal_* events."""
    if not symbol:
        return

    from src.db.database import get_db
    from src.db.models import SignalProvenanceRecord
    from src.db.sync import sync_signal_provenance_to_file

    confidence = kwargs.get("confidence", 0.5)
    direction = kwargs.get("direction", "neutral")
    description = kwargs.get("description", "") or kwargs.get("signal_type", event_type)
    detection_method = kwargs.get("detection_method", source)

    # Use event_id as signal_id if none provided
    sid = kwargs.get("signal_id") or event_id

    now = datetime.utcnow()
    record_data = {
        "signal_id": sid,
        "source": source,
        "symbol": symbol,
        "first_detected": now.isoformat(),
        "detection_method": detection_method,
        "initial_confidence": confidence,
        "initial_direction": direction,
        "initial_description": str(description)[:500],
        "confidence_history": json.dumps([]),
        "corroborating_signals": json.dumps([]),
        "outcome": "pending",
        "metadata_json": json.dumps({k: v for k, v in kwargs.items()
                                      if k not in ("confidence", "direction", "description",
                                                    "detection_method", "signal_id")}),
        "decision_ids": json.dumps([]),
    }

    try:
        with get_db() as session:
            existing = session.query(SignalProvenanceRecord).filter(
                SignalProvenanceRecord.signal_id == sid
            ).first()
            if not existing:
                rec = SignalProvenanceRecord(
                    signal_id=sid,
                    source=source,
                    symbol=symbol,
                    first_detected=now,
                    detection_method=detection_method,
                    initial_confidence=confidence,
                    initial_direction=direction,
                    initial_description=str(description)[:500],
                    outcome="pending",
                    metadata_json=record_data["metadata_json"],
                )
                session.add(rec)
    except Exception as e:
        logger.debug(f"DB signal provenance write failed: {e}")

    try:
        sync_signal_provenance_to_file(record_data)
    except Exception as e:
        logger.debug(f"File signal provenance sync failed: {e}")

    # Auto-link corroborations (same symbol, same direction, different source)
    try:
        _auto_link_corroborations(sid, symbol, direction, source)
    except Exception:
        pass


def _auto_link_corroborations(
    signal_id: str, symbol: str, direction: str, source: str
) -> None:
    """Find and link corroborating signals (same symbol+direction, different source)."""
    from src.db.database import get_db
    from src.db.models import SignalProvenanceRecord

    try:
        with get_db() as session:
            recent = (
                session.query(SignalProvenanceRecord)
                .filter(
                    SignalProvenanceRecord.symbol == symbol,
                    SignalProvenanceRecord.initial_direction == direction,
                    SignalProvenanceRecord.source != source,
                    SignalProvenanceRecord.outcome == "pending",
                    SignalProvenanceRecord.signal_id != signal_id,
                )
                .limit(10)
                .all()
            )
            for other in recent:
                # Add cross-references
                my_corr = json.loads(other.corroborating_signals or "[]")
                if signal_id not in my_corr:
                    my_corr.append(signal_id)
                    other.corroborating_signals = json.dumps(my_corr)
    except Exception:
        pass


def _handle_decision_signals(event_id: str, kwargs: dict) -> None:
    """Populate DecisionSignalLink rows from decision's signal_ids."""
    from src.db.database import get_db
    from src.db.models import DecisionSignalLink, SignalProvenanceRecord

    decision_id = kwargs.get("decision_id", "")
    signal_ids = kwargs.get("signal_ids", [])
    if not decision_id or not signal_ids:
        return

    try:
        with get_db() as session:
            for i, sid in enumerate(signal_ids):
                # Check signal exists (soft — don't fail if missing)
                exists = session.query(SignalProvenanceRecord).filter(
                    SignalProvenanceRecord.signal_id == sid
                ).first()

                if exists:
                    contribution = "primary" if i == 0 else "supporting"
                    link = DecisionSignalLink(
                        decision_id=decision_id,
                        signal_id=sid,
                        contribution=contribution,
                        signal_confidence_at_decision_time=exists.initial_confidence,
                    )
                    session.add(link)

                    # Also update the signal's decision_ids list
                    dec_ids = json.loads(exists.decision_ids or "[]")
                    if decision_id not in dec_ids:
                        dec_ids.append(decision_id)
                        exists.decision_ids = json.dumps(dec_ids)
    except Exception as e:
        logger.debug(f"Decision signal link failed: {e}")


def _handle_trade_outcome(event_id: str, symbol: str | None, kwargs: dict) -> None:
    """Update signal quality tracker + provenance outcomes on trade close."""
    signal_ids = kwargs.get("signal_ids", [])
    pnl = kwargs.get("pnl")
    pnl_pct = kwargs.get("pnl_pct")
    direction = kwargs.get("direction", "bullish")

    # Update signal quality tracker
    if signal_ids and pnl is not None:
        try:
            from src.monitoring.signal_quality_tracker import get_signal_quality_tracker
            tracker = get_signal_quality_tracker()
            for sid in signal_ids:
                # Infer signal_type from the signal_id or use generic
                tracker.log_outcome(
                    signal_type=kwargs.get("signal_type", "technical"),
                    symbol=symbol or "",
                    direction=direction,
                    signal_strength=kwargs.get("confidence", 0.5),
                    acted_on=True,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
        except Exception as e:
            logger.debug(f"Signal quality tracker update failed: {e}")

    # Update SignalProvenanceRecord outcomes
    if signal_ids:
        try:
            from src.db.database import get_db
            from src.db.models import SignalProvenanceRecord

            outcome = "hit" if (pnl or 0) > 0 else "miss"
            now = datetime.utcnow()

            with get_db() as session:
                for sid in signal_ids:
                    rec = session.query(SignalProvenanceRecord).filter(
                        SignalProvenanceRecord.signal_id == sid
                    ).first()
                    if rec and rec.outcome == "pending":
                        rec.outcome = outcome
                        rec.outcome_date = now
                        rec.pnl_contribution = pnl
                        rec.outcome_notes = kwargs.get("outcome_notes", "")
        except Exception as e:
            logger.debug(f"Signal provenance outcome update failed: {e}")


def _notify_subscribers(
    event_type: str,
    event_id: str,
    source: str,
    symbol: str | None,
    severity: str,
    title: str,
    detail: str | dict | None,
    kwargs: dict,
) -> None:
    """Fire subscriber callbacks for matching patterns."""
    for pattern, callbacks in _subscribers.items():
        if fnmatch.fnmatch(event_type, pattern):
            for cb in callbacks:
                try:
                    cb(
                        event_type=event_type,
                        event_id=event_id,
                        source=source,
                        symbol=symbol,
                        severity=severity,
                        title=title,
                        detail=detail,
                        **kwargs,
                    )
                except Exception as e:
                    logger.debug(f"Subscriber {cb.__name__} failed for {event_type}: {e}")
