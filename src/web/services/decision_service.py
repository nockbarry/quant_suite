"""Decision service -- CRUD + lineage queries for DecisionRecord."""

import json
from datetime import datetime

from sqlalchemy.orm import joinedload

from src.db.database import get_db
from src.db.models import (
    DecisionRecord,
    DecisionSignalLink,
    DecisionConvergence,
    LLMInteraction,
    ProcessEvent,
    SignalProvenanceRecord,
    ThesisRecord,
)
from src.db.sync import sync_decision_to_file


def list_decisions(
    limit: int = 50,
    symbol: str | None = None,
    action: str | None = None,
    status: str | None = None,
    thesis_id: str | None = None,
    setup_type: str | None = None,
) -> list[dict]:
    """Return decisions with optional filters. Most recent first.

    Enriches each decision dict with thesis_name when a thesis_id is present.
    """
    with get_db() as session:
        q = session.query(DecisionRecord)
        if symbol:
            q = q.filter(DecisionRecord.symbol == symbol.upper())
        if action:
            q = q.filter(DecisionRecord.action == action.upper())
        if status:
            q = q.filter(DecisionRecord.status == status)
        if thesis_id:
            q = q.filter(DecisionRecord.thesis_id == thesis_id)
        if setup_type:
            q = q.filter(DecisionRecord.setup_type == setup_type)
        rows = q.order_by(DecisionRecord.timestamp.desc()).limit(limit).all()
        decisions = [r.to_dict() for r in rows]

        # Enrich with thesis names
        thesis_ids = {d["thesis_id"] for d in decisions if d.get("thesis_id")}
        if thesis_ids:
            thesis_rows = session.query(ThesisRecord.id, ThesisRecord.name).filter(
                ThesisRecord.id.in_(thesis_ids)
            ).all()
            thesis_names = {r[0]: r[1] for r in thesis_rows}
            for d in decisions:
                d["thesis_name"] = thesis_names.get(d.get("thesis_id"), "")
        else:
            for d in decisions:
                d["thesis_name"] = ""

        return decisions


def get_decision(decision_id: str) -> dict | None:
    """Return a single decision by id, or None."""
    with get_db() as session:
        row = session.query(DecisionRecord).filter(DecisionRecord.id == decision_id).first()
        return row.to_dict() if row else None


def get_decision_lineage(decision_id: str) -> dict | None:
    """Full lineage for a decision: signal_links, convergence, llm_interaction.

    Returns a dict with 'decision', 'signal_links', 'convergence', 'llm_interaction'
    keys, or None if decision not found.
    """
    with get_db() as session:
        decision = session.query(DecisionRecord).filter(DecisionRecord.id == decision_id).first()
        if decision is None:
            return None

        # Signal links with full signal data
        links = (
            session.query(DecisionSignalLink)
            .options(joinedload(DecisionSignalLink.signal))
            .filter(DecisionSignalLink.decision_id == decision_id)
            .all()
        )
        signal_links = []
        for link in links:
            link_data = {
                "contribution": link.contribution,
                "signal_confidence_at_decision_time": link.signal_confidence_at_decision_time,
                "signal": link.signal.to_dict() if link.signal else None,
            }
            signal_links.append(link_data)

        # Convergence
        convergence = None
        if decision.convergence_id:
            conv_row = (
                session.query(DecisionConvergence)
                .filter(DecisionConvergence.id == decision.convergence_id)
                .first()
            )
            convergence = conv_row.to_dict() if conv_row else None

        # LLM interaction
        llm_interaction = None
        if decision.llm_interaction_id:
            llm_row = (
                session.query(LLMInteraction)
                .filter(LLMInteraction.id == decision.llm_interaction_id)
                .first()
            )
            llm_interaction = llm_row.to_dict() if llm_row else None

        # Context events (from SessionContext persistence)
        context_events = (
            session.query(ProcessEvent)
            .filter(ProcessEvent.decision_id == decision_id)
            .order_by(ProcessEvent.timestamp)
            .all()
        )

        context_by_type: dict[str, list[dict]] = {}
        for evt in context_events:
            evt_dict = evt.to_dict()
            et = evt.event_type or "other"
            context_by_type.setdefault(et, []).append(evt_dict)

        return {
            "decision": decision.to_dict(),
            "signal_links": signal_links,
            "convergence": convergence,
            "llm_interaction": llm_interaction,
            "context_events": context_by_type,
        }


def create_decision(data: dict) -> dict:
    """Insert a new decision record. Dual-writes to JSON file."""
    data.setdefault("timestamp", datetime.utcnow().isoformat())
    row = DecisionRecord.from_dict(data)
    with get_db() as session:
        session.add(row)
        session.flush()
        result = row.to_dict()
    sync_decision_to_file(result)
    return result


def update_decision_status(decision_id: str, status: str) -> dict | None:
    """Update only the status field of a decision."""
    return update_decision(decision_id, {"status": status})


def update_decision(decision_id: str, data: dict) -> dict | None:
    """Update decision fields. Dual-writes to JSON file."""
    with get_db() as session:
        row = session.query(DecisionRecord).filter(DecisionRecord.id == decision_id).first()
        if row is None:
            return None

        for key, value in data.items():
            if key == "id":
                continue
            if key in ("key_factors", "risks", "signal_ids") and isinstance(value, list):
                value = json.dumps(value)
            if key == "context" and isinstance(value, dict):
                value = json.dumps(value)
            if key in ("timestamp", "execution_time", "exit_time") and isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    continue
            if hasattr(row, key):
                setattr(row, key, value)

        session.flush()
        result = row.to_dict()

    sync_decision_to_file(result)
    return result


def get_thesis_options() -> list[dict]:
    """Return list of {id, name} for active theses (for filter dropdown)."""
    with get_db() as session:
        rows = session.query(ThesisRecord.id, ThesisRecord.name).filter(
            ThesisRecord.status == "active"
        ).order_by(ThesisRecord.name).all()
        return [{"id": r[0], "name": r[1]} for r in rows]


def get_distinct_setup_types() -> list[str]:
    """Return sorted list of unique setup types from decisions."""
    with get_db() as session:
        rows = session.query(DecisionRecord.setup_type).distinct().all()
        return sorted([r[0] for r in rows if r[0]])


def get_decision_context(decision_id: str, panel_type: str | None = None) -> dict:
    """Get context events for a decision, optionally filtered by panel type.

    Panel types map to ProcessEvent.event_type:
      - market_snapshot
      - web_search
      - news_item
      - operator_obs
      - agent_output
      - reasoning

    Also checks DecisionRecord.context JSON for embedded context data.
    """
    with get_db() as session:
        decision = session.query(DecisionRecord).filter(DecisionRecord.id == decision_id).first()
        if decision is None:
            return {"events": [], "embedded_context": {}}

        # Query ProcessEvent rows linked to this decision
        q = session.query(ProcessEvent).filter(ProcessEvent.decision_id == decision_id)
        if panel_type:
            q = q.filter(ProcessEvent.event_type == panel_type)
        events = q.order_by(ProcessEvent.timestamp).all()

        # Also extract embedded context from DecisionRecord.context JSON
        embedded = {}
        if decision.context:
            try:
                ctx = json.loads(decision.context) if isinstance(decision.context, str) else decision.context
            except (json.JSONDecodeError, TypeError):
                ctx = {}

            if panel_type:
                # Map panel_type to context keys
                key_map = {
                    "market_snapshot": "market_snapshot",
                    "web_search": "web_searches",
                    "news_item": "news_items",
                    "operator_obs": "operator_observations",
                    "agent_output": "agent_outputs",
                    "reasoning": "reasoning_steps",
                }
                key = key_map.get(panel_type)
                if key and key in ctx:
                    embedded[key] = ctx[key]
            else:
                # Return all embedded context
                for key in ("market_snapshot", "web_searches", "news_items",
                            "operator_observations", "agent_outputs", "reasoning_steps",
                            "session_id", "context_captured_at"):
                    if key in ctx:
                        embedded[key] = ctx[key]

        return {
            "events": [e.to_dict() for e in events],
            "embedded_context": embedded,
        }
