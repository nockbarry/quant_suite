"""Universal write API for Athena DB.

Provides a single facade for all data writes. Every method:
1. Writes to DB via get_db()
2. Syncs to file via src/db/sync
3. Optionally broadcasts a WebSocket event

Usage:
    from src.db.write_api import athena_db

    athena_db.upsert_thesis(thesis_dict)
    athena_db.start_agent_run("research", "Analyze NVDA")

    with tracked_agent("research", "Analyze NVDA") as run:
        run.set_findings("Found 3 signals")
        run.set_cost(0.15)
"""

import asyncio
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)


class _TrackedRun:
    """Context manager state for a tracked agent run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.findings: str = ""
        self.cost_usd: float = 0.0
        self.tokens_used: int = 0

    def set_findings(self, summary: str):
        self.findings = summary

    def set_cost(self, cost_usd: float):
        self.cost_usd = cost_usd

    def set_tokens(self, tokens: int):
        self.tokens_used = tokens


class AthenaWriteAPI:
    """Unified write API — DB + file sync + WebSocket broadcast."""

    # ------------------------------------------------------------------
    # Thesis
    # ------------------------------------------------------------------

    def upsert_thesis(self, data: dict) -> str:
        """Upsert a thesis into DB and sync to YAML file."""
        from src.db.database import get_db
        from src.db.models import ThesisRecord, SignpostRecord
        from src.db.sync import sync_thesis_to_file

        thesis_id = data.get("id", "")
        if not thesis_id:
            return ""

        try:
            with get_db() as session:
                existing = session.query(ThesisRecord).filter(
                    ThesisRecord.id == thesis_id
                ).first()

                if existing:
                    # Update scalar fields
                    for field in (
                        "name", "status", "summary", "bull_case", "bear_case",
                        "conviction", "review_interval_days",
                    ):
                        if field in data:
                            setattr(existing, field, data[field])
                    for field in (
                        "positions", "invalidation_triggers", "conviction_history", "notes",
                    ):
                        if field in data:
                            val = data[field]
                            setattr(existing, field, json.dumps(val) if isinstance(val, list) else val)
                    for field in ("created", "last_review", "next_review"):
                        if field in data and data[field]:
                            val = data[field]
                            if isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    val = None
                            setattr(existing, field, val)
                    # Replace signposts
                    if "signposts" in data:
                        existing.signposts.clear()
                        session.flush()
                        for s in data["signposts"]:
                            existing.signposts.append(
                                SignpostRecord.from_dict(s, thesis_id)
                            )
                else:
                    record = ThesisRecord.from_dict(data)
                    session.add(record)

                # Sync position links
                self._sync_thesis_positions(session, thesis_id, data.get("positions", []))
        except Exception as e:
            logger.warning(f"DB upsert failed for thesis {thesis_id}: {e}")

        # File sync
        try:
            sync_thesis_to_file(data)
        except Exception as e:
            logger.warning(f"File sync failed for thesis {thesis_id}: {e}")

        return thesis_id

    def update_conviction(self, thesis_id: str, value: float, reason: str) -> bool:
        """Update thesis conviction and broadcast event."""
        from src.db.database import get_db
        from src.db.models import ThesisRecord

        old_value = None
        try:
            with get_db() as session:
                thesis = session.query(ThesisRecord).filter(
                    ThesisRecord.id == thesis_id
                ).first()
                if not thesis:
                    return False
                old_value = thesis.conviction
                thesis.conviction = value
                # Append to conviction_history JSON
                history = json.loads(thesis.conviction_history or "[]")
                history.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "old_value": old_value,
                    "new_value": value,
                    "reason": reason,
                })
                thesis.conviction_history = json.dumps(history)
        except Exception as e:
            logger.warning(f"DB conviction update failed for {thesis_id}: {e}")
            return False

        self._broadcast({
            "type": "thesis_conviction_changed",
            "thesis_id": thesis_id,
            "old_value": old_value,
            "new_value": value,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def _sync_thesis_positions(self, session, thesis_id: str, positions: list):
        """Sync ThesisPositionLink junction table."""
        from src.db.models import ThesisPositionLink

        try:
            # Get existing
            existing = {
                r.symbol
                for r in session.query(ThesisPositionLink).filter(
                    ThesisPositionLink.thesis_id == thesis_id
                ).all()
            }
            new_set = set(positions)

            # Add new
            for symbol in new_set - existing:
                session.add(ThesisPositionLink(thesis_id=thesis_id, symbol=symbol))

            # Remove old
            for symbol in existing - new_set:
                session.query(ThesisPositionLink).filter(
                    ThesisPositionLink.thesis_id == thesis_id,
                    ThesisPositionLink.symbol == symbol,
                ).delete()
        except Exception as e:
            logger.debug(f"Position link sync issue: {e}")

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def upsert_decision(self, data: dict) -> str:
        """Upsert a decision into DB and sync to file."""
        from src.db.database import get_db
        from src.db.models import DecisionRecord
        from src.db.sync import sync_decision_to_file

        decision_id = data.get("id", "")
        if not decision_id:
            return ""

        try:
            with get_db() as session:
                existing = session.query(DecisionRecord).filter(
                    DecisionRecord.id == decision_id
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            if key in ("key_factors", "risks", "signal_ids") and isinstance(val, list):
                                val = json.dumps(val)
                            elif key == "context" and isinstance(val, dict):
                                val = json.dumps(val)
                            elif key in ("timestamp", "execution_time", "exit_time") and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    # Strip unknown keys before creating
                    valid_cols = {c.key for c in DecisionRecord.__table__.columns}
                    clean = {k: v for k, v in data.items() if k in valid_cols}
                    record = DecisionRecord.from_dict(clean)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB upsert failed for decision {decision_id}: {e}")

        try:
            sync_decision_to_file(data)
        except Exception as e:
            logger.warning(f"File sync failed for decision {decision_id}: {e}")

        self._broadcast({
            "type": "decision_created",
            "decision_id": decision_id,
            "symbol": data.get("symbol", ""),
            "action": data.get("action", ""),
            "confidence": data.get("confidence", 0),
            "timestamp": datetime.utcnow().isoformat(),
        })
        return decision_id

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def upsert_learning(self, data: dict) -> str:
        """Upsert a learning into DB and sync to file."""
        from src.db.database import get_db
        from src.db.models import LearningRecord
        from src.db.sync import sync_learning_to_file

        learning_id = data.get("id", "")
        if not learning_id:
            return ""

        try:
            with get_db() as session:
                existing = session.query(LearningRecord).filter(
                    LearningRecord.id == learning_id
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            if key == "tags" and isinstance(val, list):
                                val = json.dumps(val)
                            elif key == "created" and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    # Strip unknown keys before creating
                    valid_cols = {c.key for c in LearningRecord.__table__.columns}
                    clean = {k: v for k, v in data.items() if k in valid_cols}
                    record = LearningRecord.from_dict(clean)
                    session.add(record)

                # Sync tags
                self._sync_learning_tags(session, learning_id, data.get("tags", []))
        except Exception as e:
            logger.warning(f"DB upsert failed for learning {learning_id}: {e}")

        try:
            sync_learning_to_file(data)
        except Exception as e:
            logger.warning(f"File sync failed for learning {learning_id}: {e}")

        return learning_id

    def _sync_learning_tags(self, session, learning_id: str, tags: list):
        """Sync LearningTag junction table."""
        from src.db.models import LearningTag

        try:
            existing = {
                r.tag
                for r in session.query(LearningTag).filter(
                    LearningTag.learning_id == learning_id
                ).all()
            }
            new_set = set(tags)

            for tag in new_set - existing:
                session.add(LearningTag(learning_id=learning_id, tag=tag))

            for tag in existing - new_set:
                session.query(LearningTag).filter(
                    LearningTag.learning_id == learning_id,
                    LearningTag.tag == tag,
                ).delete()
        except Exception as e:
            logger.debug(f"Learning tag sync issue: {e}")

    # ------------------------------------------------------------------
    # Company / Sector
    # ------------------------------------------------------------------

    def upsert_company(self, data: dict) -> str:
        """Upsert a company into DB and sync to file."""
        from src.db.database import get_db
        from src.db.models import Company
        from src.db.sync import sync_company_to_file

        symbol = data.get("symbol", "")
        if not symbol:
            return ""

        try:
            with get_db() as session:
                existing = session.query(Company).filter(
                    Company.symbol == symbol
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "symbol":
                            continue
                        if hasattr(existing, key):
                            if key in ("key_risks", "key_catalysts") and isinstance(val, list):
                                val = json.dumps(val)
                            elif key == "updated" and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    record = Company.from_dict(data)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB upsert failed for company {symbol}: {e}")

        try:
            sync_company_to_file(data)
        except Exception as e:
            logger.warning(f"File sync failed for company {symbol}: {e}")

        return symbol

    def upsert_sector(self, data: dict) -> str:
        """Upsert a sector into DB and sync to file."""
        from src.db.database import get_db
        from src.db.models import Sector
        from src.db.sync import sync_sector_to_file

        sector = data.get("sector", "")
        if not sector:
            return ""

        try:
            with get_db() as session:
                existing = session.query(Sector).filter(
                    Sector.sector == sector
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "sector":
                            continue
                        if hasattr(existing, key):
                            if key in ("key_drivers", "leading_indicators", "leaders", "laggards") and isinstance(val, list):
                                val = json.dumps(val)
                            elif key == "correlations" and isinstance(val, dict):
                                val = json.dumps(val)
                            elif key == "updated" and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    record = Sector.from_dict(data)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB upsert failed for sector {sector}: {e}")

        try:
            sync_sector_to_file(data)
        except Exception as e:
            logger.warning(f"File sync failed for sector {sector}: {e}")

        return sector

    # ------------------------------------------------------------------
    # Agent tracking
    # ------------------------------------------------------------------

    def start_agent_run(
        self,
        agent_type: str,
        task: str,
        parent_run_id: str | None = None,
        trigger_reason: str = "",
        session_id: str | None = None,
    ) -> str:
        """Start a new agent run. Returns run_id."""
        from src.db.database import get_db
        from src.db.models import AgentRun

        run_id = f"{agent_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        try:
            with get_db() as session:
                run = AgentRun(
                    id=run_id,
                    agent_type=agent_type,
                    task=task[:500] if task else "",
                    trigger_reason=trigger_reason,
                    parent_run_id=parent_run_id,
                    session_id=session_id,
                    started_at=datetime.utcnow(),
                    status="running",
                )
                session.add(run)
        except Exception as e:
            logger.warning(f"DB start_agent_run failed: {e}")

        self._broadcast({
            "type": "agent_started",
            "run_id": run_id,
            "agent_type": agent_type,
            "task": task[:200] if task else "",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return run_id

    def complete_agent_run(
        self,
        run_id: str,
        findings_summary: str = "",
        cost_usd: float = 0.0,
        tokens_used: int = 0,
    ) -> bool:
        """Mark an agent run as completed."""
        from src.db.database import get_db
        from src.db.models import AgentRun

        try:
            with get_db() as session:
                run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
                if not run:
                    return False
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.findings_summary = findings_summary[:5000] if findings_summary else ""
                run.cost_usd = cost_usd
                run.tokens_used = tokens_used
        except Exception as e:
            logger.warning(f"DB complete_agent_run failed for {run_id}: {e}")
            return False

        self._broadcast({
            "type": "agent_completed",
            "run_id": run_id,
            "findings_summary": findings_summary[:200] if findings_summary else "",
            "cost_usd": cost_usd,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def fail_agent_run(self, run_id: str, error: str = "") -> bool:
        """Mark an agent run as failed."""
        from src.db.database import get_db
        from src.db.models import AgentRun

        try:
            with get_db() as session:
                run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
                if not run:
                    return False
                run.status = "failed"
                run.completed_at = datetime.utcnow()
                run.findings_summary = f"ERROR: {error[:2000]}" if error else ""
        except Exception as e:
            logger.warning(f"DB fail_agent_run failed for {run_id}: {e}")
            return False

        self._broadcast({
            "type": "agent_failed",
            "run_id": run_id,
            "error": error[:200] if error else "",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def recover_stale_agents(self, max_age_hours: int = 4) -> int:
        """Mark stuck 'running' agents older than max_age_hours as failed."""
        from src.db.database import get_db
        from src.db.models import AgentRun

        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        count = 0

        try:
            with get_db() as session:
                stale = (
                    session.query(AgentRun)
                    .filter(
                        AgentRun.status == "running",
                        AgentRun.started_at < cutoff,
                    )
                    .all()
                )
                for run in stale:
                    run.status = "failed"
                    run.completed_at = datetime.utcnow()
                    run.findings_summary = (
                        f"AUTO-RECOVERED: Agent was running for >{max_age_hours}h. "
                        f"Original task: {run.task[:200]}"
                    )
                    count += 1
                    logger.info(f"Recovered stale agent: {run.id} ({run.agent_type})")
        except Exception as e:
            logger.warning(f"recover_stale_agents failed: {e}")

        return count

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def log_event(
        self,
        event_type: str,
        source: str = "",
        title: str = "",
        detail: str = "",
        symbol: str | None = None,
        severity: str = "info",
        agent_run_id: str | None = None,
        thesis_id: str | None = None,
        decision_id: str | None = None,
    ) -> str:
        """Log a process event to DB and broadcast."""
        from src.db.database import get_db
        from src.db.models import ProcessEvent

        event_id = f"evt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        try:
            with get_db() as session:
                evt = ProcessEvent(
                    id=event_id,
                    timestamp=datetime.utcnow(),
                    event_type=event_type,
                    source=source,
                    title=title[:300] if title else "",
                    detail=detail,
                    symbol=symbol,
                    severity=severity,
                    agent_run_id=agent_run_id,
                    thesis_id=thesis_id,
                    decision_id=decision_id,
                )
                session.add(evt)
        except Exception as e:
            logger.warning(f"DB log_event failed: {e}")

        self._broadcast({
            "type": event_type,
            "id": event_id,
            "source": source,
            "title": title,
            "symbol": symbol,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return event_id

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    def _broadcast(self, event: dict):
        """Best-effort push to /ws/events WebSocket channel."""
        try:
            from src.web.routes.websocket import broadcast_event, _main_loop

            if _main_loop and not _main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(broadcast_event(event), _main_loop)
        except Exception:
            pass  # Best-effort — no web server running is fine


# Singleton
athena_db = AthenaWriteAPI()


# ------------------------------------------------------------------
# Context manager for agent tracking
# ------------------------------------------------------------------

@contextmanager
def tracked_agent(agent_type: str, task: str, parent_run_id: str | None = None):
    """Context manager that auto-tracks agent lifecycle.

    Usage:
        with tracked_agent("research", "Analyze NVDA") as run:
            run.set_findings("Found 3 signals")
            run.set_cost(0.15)
        # Auto-completes on exit, auto-fails on exception
    """
    run_id = athena_db.start_agent_run(agent_type, task, parent_run_id)
    run = _TrackedRun(run_id)
    try:
        yield run
        athena_db.complete_agent_run(
            run_id,
            findings_summary=run.findings,
            cost_usd=run.cost_usd,
            tokens_used=run.tokens_used,
        )
    except Exception as e:
        athena_db.fail_agent_run(run_id, str(e))
        raise
