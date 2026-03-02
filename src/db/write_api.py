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
import os
import threading
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
                now = datetime.utcnow()
                run = AgentRun(
                    id=run_id,
                    agent_type=agent_type,
                    task=task[:500] if task else "",
                    trigger_reason=trigger_reason,
                    parent_run_id=parent_run_id,
                    session_id=session_id,
                    started_at=now,
                    status="running",
                    pid=os.getpid(),
                    heartbeat_at=now,
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

    def heartbeat_agent(self, run_id: str) -> bool:
        """Update heartbeat timestamp for a running agent."""
        from src.db.database import get_db
        from src.db.models import AgentRun

        try:
            with get_db() as session:
                run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
                if run and run.status == "running":
                    run.heartbeat_at = datetime.utcnow()
                    return True
        except Exception as e:
            logger.debug(f"heartbeat_agent failed for {run_id}: {e}")
        return False

    def recover_stale_agents(self, max_age_hours: int = 4, heartbeat_timeout_minutes: int = 10) -> int:
        """Mark stuck 'running' agents as failed.

        Recovery triggers:
        1. Started more than max_age_hours ago (original behavior)
        2. Has heartbeat but heartbeat is older than heartbeat_timeout_minutes
        """
        from src.db.database import get_db
        from src.db.models import AgentRun

        age_cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        hb_cutoff = datetime.utcnow() - timedelta(minutes=heartbeat_timeout_minutes)
        count = 0

        try:
            with get_db() as session:
                stale = (
                    session.query(AgentRun)
                    .filter(AgentRun.status == "running")
                    .all()
                )
                for run in stale:
                    reason = None
                    if run.started_at < age_cutoff:
                        reason = f"running for >{max_age_hours}h"
                    elif run.heartbeat_at and run.heartbeat_at < hb_cutoff:
                        reason = f"heartbeat stale (last: {run.heartbeat_at.isoformat()})"

                    if reason:
                        run.status = "failed"
                        run.completed_at = datetime.utcnow()
                        run.findings_summary = (
                            f"AUTO-RECOVERED: {reason}. "
                            f"Original task: {run.task[:200]}"
                        )
                        count += 1
                        logger.info(f"Recovered stale agent: {run.id} ({run.agent_type}) — {reason}")
        except Exception as e:
            logger.warning(f"recover_stale_agents failed: {e}")

        return count

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def save_document(
        self,
        doc_type: str,
        title: str,
        file_path: str | None = None,
        content_inline: str | None = None,
        summary: str = "",
        symbols: list[str] | None = None,
        tags: list[str] | None = None,
        source: str = "",
        agent_run_id: str | None = None,
        thesis_id: str | None = None,
        decision_id: str | None = None,
        doc_id: str | None = None,
        created: datetime | None = None,
    ) -> str:
        """Index a document in the DB. Returns the document id."""
        from src.db.database import get_db
        from src.db.models import Document

        if not doc_id:
            doc_id = f"doc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        # Auto-generate summary from content if not provided
        if not summary and content_inline:
            summary = content_inline[:500]
        elif not summary and file_path:
            try:
                text = open(file_path).read(600)
                # Skip YAML front matter or JSON opening
                if text.startswith("---"):
                    lines = text.split("\n")
                    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), 0)
                    summary = "\n".join(lines[end + 1:])[:500].strip()
                elif text.startswith("{"):
                    summary = f"JSON document: {title}"
                else:
                    summary = text[:500].strip()
            except Exception:
                summary = title

        try:
            with get_db() as session:
                existing = session.query(Document).filter(Document.id == doc_id).first()
                if existing:
                    existing.title = title
                    existing.summary = summary
                    if file_path:
                        existing.file_path = file_path
                    if content_inline is not None:
                        existing.content_inline = content_inline
                    existing.symbols = json.dumps(symbols or [])
                    existing.tags = json.dumps(tags or [])
                    existing.source = source
                    existing.agent_run_id = agent_run_id
                    existing.thesis_id = thesis_id
                    existing.decision_id = decision_id
                else:
                    doc = Document(
                        id=doc_id,
                        doc_type=doc_type,
                        title=title,
                        summary=summary,
                        file_path=file_path,
                        content_inline=content_inline,
                        created=created or datetime.utcnow(),
                        symbols=json.dumps(symbols or []),
                        tags=json.dumps(tags or []),
                        source=source,
                        agent_run_id=agent_run_id,
                        thesis_id=thesis_id,
                        decision_id=decision_id,
                    )
                    session.add(doc)
        except Exception as e:
            logger.warning(f"DB save_document failed for {doc_id}: {e}")

        self._broadcast({
            "type": "document_indexed",
            "doc_id": doc_id,
            "doc_type": doc_type,
            "title": title,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return doc_id

    def save_insight(self, data: dict) -> str:
        """Upsert a research insight into the DB."""
        from src.db.database import get_db
        from src.db.models import Insight

        insight_id = data.get("id", "")
        if not insight_id:
            return ""

        try:
            with get_db() as session:
                existing = session.query(Insight).filter(Insight.id == insight_id).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            if key in ("tags", "related_insights") and isinstance(val, list):
                                val = json.dumps(val)
                            elif key == "evidence" and isinstance(val, dict):
                                val = json.dumps(val)
                            elif key in ("created_at", "updated_at") and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    valid_cols = {c.key for c in Insight.__table__.columns}
                    clean = {k: v for k, v in data.items() if k in valid_cols}
                    record = Insight.from_dict(clean)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB save_insight failed for {insight_id}: {e}")

        return insight_id

    def save_experiment(self, data: dict) -> str:
        """Upsert a research experiment into the DB."""
        from src.db.database import get_db
        from src.db.models import Experiment

        exp_id = data.get("id", "")
        if not exp_id:
            return ""

        try:
            with get_db() as session:
                existing = session.query(Experiment).filter(Experiment.id == exp_id).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            if key == "params" and isinstance(val, dict):
                                val = json.dumps(val)
                            elif key == "run_at" and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    valid_cols = {c.key for c in Experiment.__table__.columns}
                    clean = {k: v for k, v in data.items() if k in valid_cols}
                    record = Experiment.from_dict(clean)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB save_experiment failed for {exp_id}: {e}")

        return exp_id

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def save_prediction(self, data: dict) -> str:
        """Upsert a prediction. Auto-generates ID and resolve_by if missing."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord

        pred_id = data.get("id", "")
        if not pred_id:
            pred_id = f"pred_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
            data["id"] = pred_id

        # Auto-compute resolve_by from timeframe_days
        if "resolve_by" not in data and "timeframe_days" in data:
            created = data.get("created")
            if isinstance(created, str):
                try:
                    base = datetime.fromisoformat(created)
                except (ValueError, TypeError):
                    base = datetime.utcnow()
            elif isinstance(created, datetime):
                base = created
            else:
                base = datetime.utcnow()
            data["resolve_by"] = (base + timedelta(days=data["timeframe_days"])).isoformat()

        data.setdefault("status", "open")

        try:
            with get_db() as session:
                existing = session.query(PredictionRecord).filter(
                    PredictionRecord.id == pred_id
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            if key in ("created", "resolve_by", "resolved_at") and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    continue
                            setattr(existing, key, val)
                else:
                    valid_cols = {c.key for c in PredictionRecord.__table__.columns}
                    clean = {k: v for k, v in data.items() if k in valid_cols}
                    record = PredictionRecord.from_dict(clean)
                    session.add(record)
        except Exception as e:
            logger.warning(f"DB save_prediction failed for {pred_id}: {e}")

        self._broadcast({
            "type": "prediction_created",
            "pred_id": pred_id,
            "symbol": data.get("symbol", ""),
            "prediction_type": data.get("prediction_type", ""),
            "direction": data.get("direction", ""),
            "timestamp": datetime.utcnow().isoformat(),
        })
        return pred_id

    def resolve_prediction(
        self,
        pred_id: str,
        status: str,
        actual_value: float | None = None,
        notes: str = "",
        brier_score: float | None = None,
        accuracy_score: float | None = None,
        timing_error_days: int | None = None,
    ) -> bool:
        """Score and close a prediction."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord

        try:
            with get_db() as session:
                pred = session.query(PredictionRecord).filter(
                    PredictionRecord.id == pred_id
                ).first()
                if not pred:
                    return False
                pred.status = status
                pred.resolved_at = datetime.utcnow()
                if actual_value is not None:
                    pred.actual_value = actual_value
                pred.resolution_notes = notes
                if brier_score is not None:
                    pred.brier_score = brier_score
                if accuracy_score is not None:
                    pred.accuracy_score = accuracy_score
                if timing_error_days is not None:
                    pred.timing_error_days = timing_error_days
        except Exception as e:
            logger.warning(f"DB resolve_prediction failed for {pred_id}: {e}")
            return False

        self._broadcast({
            "type": "prediction_resolved",
            "pred_id": pred_id,
            "status": status,
            "brier_score": brier_score,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return True

    def get_open_predictions(self, symbol: str | None = None) -> list[dict]:
        """Query open predictions, optionally filtered by symbol."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord

        try:
            with get_db() as session:
                q = session.query(PredictionRecord).filter(
                    PredictionRecord.status == "open"
                )
                if symbol:
                    q = q.filter(PredictionRecord.symbol == symbol.upper())
                rows = q.order_by(PredictionRecord.resolve_by.asc()).all()
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.warning(f"get_open_predictions failed: {e}")
            return []

    def get_prediction_scorecard(self) -> dict:
        """Accuracy breakdown by type, category, and overall."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord
        from sqlalchemy import func

        try:
            with get_db() as session:
                resolved = session.query(PredictionRecord).filter(
                    PredictionRecord.status.in_(["hit", "miss", "expired"])
                ).all()

                if not resolved:
                    return {"total": 0, "by_type": {}, "by_category": {}, "avg_brier": None}

                total = len(resolved)
                hits = sum(1 for r in resolved if r.status == "hit")
                briers = [r.brier_score for r in resolved if r.brier_score is not None]

                # By type
                by_type = {}
                for r in resolved:
                    t = r.prediction_type or "unknown"
                    if t not in by_type:
                        by_type[t] = {"total": 0, "hits": 0}
                    by_type[t]["total"] += 1
                    if r.status == "hit":
                        by_type[t]["hits"] += 1
                for v in by_type.values():
                    v["accuracy"] = v["hits"] / v["total"] if v["total"] else 0

                # By category
                by_category = {}
                for r in resolved:
                    c = r.reasoning_category or "unknown"
                    if c not in by_category:
                        by_category[c] = {"total": 0, "hits": 0}
                    by_category[c]["total"] += 1
                    if r.status == "hit":
                        by_category[c]["hits"] += 1
                for v in by_category.values():
                    v["accuracy"] = v["hits"] / v["total"] if v["total"] else 0

                return {
                    "total": total,
                    "hits": hits,
                    "accuracy": hits / total if total else 0,
                    "avg_brier": sum(briers) / len(briers) if briers else None,
                    "by_type": by_type,
                    "by_category": by_category,
                }
        except Exception as e:
            logger.warning(f"get_prediction_scorecard failed: {e}")
            return {"total": 0, "by_type": {}, "by_category": {}, "avg_brier": None}

    # ------------------------------------------------------------------
    # Document queries (read methods for agents/skills)
    # ------------------------------------------------------------------

    def get_recent_documents(self, doc_type: str | None = None, limit: int = 20) -> list[dict]:
        """Return recent documents, optionally filtered by type."""
        from src.db.database import get_db
        from src.db.models import Document

        try:
            with get_db() as session:
                q = session.query(Document)
                if doc_type:
                    q = q.filter(Document.doc_type == doc_type)
                rows = q.order_by(Document.created.desc()).limit(limit).all()
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.warning(f"get_recent_documents failed: {e}")
            return []

    def get_documents_for_symbol(self, symbol: str, limit: int = 20) -> list[dict]:
        """Return documents mentioning a symbol."""
        from src.db.database import get_db
        from src.db.models import Document

        try:
            with get_db() as session:
                rows = (
                    session.query(Document)
                    .filter(Document.symbols.contains(f'"{symbol}"'))
                    .order_by(Document.created.desc())
                    .limit(limit)
                    .all()
                )
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.warning(f"get_documents_for_symbol failed: {e}")
            return []

    def search_documents(self, query: str, limit: int = 20) -> list[dict]:
        """Search documents by title, summary, or tags."""
        from src.db.database import get_db
        from src.db.models import Document

        try:
            with get_db() as session:
                pattern = f"%{query}%"
                rows = (
                    session.query(Document)
                    .filter(
                        (Document.title.ilike(pattern))
                        | (Document.summary.ilike(pattern))
                        | (Document.tags.ilike(pattern))
                    )
                    .order_by(Document.created.desc())
                    .limit(limit)
                    .all()
                )
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.warning(f"search_documents failed: {e}")
            return []

    def search_insights(self, query: str = "", category: str = "", limit: int = 50) -> list[dict]:
        """Search insights by text and/or category."""
        from src.db.database import get_db
        from src.db.models import Insight

        try:
            with get_db() as session:
                q = session.query(Insight)
                if category:
                    q = q.filter(Insight.category == category)
                if query:
                    pattern = f"%{query}%"
                    q = q.filter(
                        (Insight.title.ilike(pattern))
                        | (Insight.description.ilike(pattern))
                        | (Insight.tags.ilike(pattern))
                    )
                rows = q.order_by(Insight.created_at.desc()).limit(limit).all()
                return [r.to_dict() for r in rows]
        except Exception as e:
            logger.warning(f"search_insights failed: {e}")
            return []

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
    """Context manager that auto-tracks agent lifecycle with heartbeat.

    Usage:
        with tracked_agent("research", "Analyze NVDA") as run:
            run.set_findings("Found 3 signals")
            run.set_cost(0.15)
        # Auto-completes on exit, auto-fails on exception
        # Heartbeat thread runs every 30s while agent is active
    """
    run_id = athena_db.start_agent_run(agent_type, task, parent_run_id)
    run = _TrackedRun(run_id)

    # Start heartbeat daemon thread
    stop_event = threading.Event()

    def _heartbeat_loop():
        while not stop_event.wait(30):
            try:
                athena_db.heartbeat_agent(run_id)
            except Exception:
                pass

    hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"hb-{run_id[:20]}")
    hb_thread.start()

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
    finally:
        stop_event.set()
