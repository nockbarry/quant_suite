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
                        "price_targets",
                    ):
                        if field in data:
                            val = data[field]
                            setattr(existing, field, json.dumps(val) if isinstance(val, (list, dict)) else val)
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

    def update_price_targets(self, thesis_id: str, price_targets: dict) -> bool:
        """Update price targets for a thesis and auto-create price_target predictions.

        Also logs ProcessEvents and creates per-symbol research documents
        for full provenance tracking.
        """
        from src.db.database import get_db
        from src.db.models import ThesisRecord

        thesis_name = ""
        thesis_conviction = 50.0
        try:
            with get_db() as session:
                thesis = session.query(ThesisRecord).filter(
                    ThesisRecord.id == thesis_id
                ).first()
                if not thesis:
                    return False
                thesis_name = thesis.name or thesis_id[:8]
                thesis_conviction = thesis.conviction or 50.0
                thesis.price_targets = json.dumps(price_targets)
        except Exception as e:
            logger.warning(f"DB update_price_targets failed for {thesis_id}: {e}")
            return False

        # Auto-create price_target predictions + provenance for each vehicle
        for symbol, pt in price_targets.items():
            self._create_price_target_prediction(
                thesis_id, symbol, pt, thesis_conviction
            )

            # Log ProcessEvent for audit trail
            try:
                self.log_event(
                    event_type="price_target_set",
                    source="thesis_tracker",
                    title=f"Price target: {symbol} base=${pt.get('base_target', 0):.2f} ({thesis_name})",
                    detail=json.dumps({
                        "symbol": symbol,
                        "bull": pt.get("bull_target"),
                        "base": pt.get("base_target"),
                        "bear": pt.get("bear_target"),
                        "entry": pt.get("entry_price"),
                        "timeframe_days": pt.get("timeframe_days", 90),
                        "notes": pt.get("notes", "")[:500],
                    }),
                    symbol=symbol,
                    thesis_id=thesis_id,
                    severity="info",
                )
            except Exception as e:
                logger.debug(f"ProcessEvent logging failed for {symbol}: {e}")

            # Create analyst research document for discoverability
            notes = pt.get("notes", "")
            if notes:
                try:
                    self.save_document(
                        doc_type="price_target_analysis",
                        title=f"{symbol} target: bear=${pt.get('bear_target', 0):.2f} / base=${pt.get('base_target', 0):.2f} / bull=${pt.get('bull_target', 0):.2f}",
                        content_inline=notes[:2000],
                        source="thesis_tracker:set_price_targets",
                        thesis_id=thesis_id,
                        symbols=[symbol],
                        tags=["price_target", "analyst_consensus"],
                    )
                except Exception as e:
                    logger.debug(f"Document indexing failed for {symbol}: {e}")

        return True

    def _create_price_target_prediction(
        self, thesis_id: str, symbol: str, pt: dict,
        thesis_conviction: float = 50.0,
    ):
        """Create or update a price_target prediction from thesis targets.

        Confidence is derived from thesis conviction (not hardcoded):
          conviction 95% → confidence 0.74
          conviction 72% → confidence 0.68
          conviction 50% → confidence 0.63
        """
        base_target = pt.get("base_target")
        if not base_target:
            return

        entry_price = pt.get("entry_price", 0)
        direction = "bullish" if base_target > entry_price else "bearish"
        timeframe = pt.get("timeframe_days", 90)
        # Derive confidence from thesis conviction: 0.5 + (conviction/100 * 0.25)
        confidence = round(min(0.90, 0.50 + (thesis_conviction / 100) * 0.25), 2)

        from src.db.database import get_db
        from src.db.models import PredictionRecord

        try:
            with get_db() as session:
                existing = session.query(PredictionRecord).filter(
                    PredictionRecord.thesis_id == thesis_id,
                    PredictionRecord.symbol == symbol,
                    PredictionRecord.prediction_type == "price_target",
                    PredictionRecord.status == "open",
                ).first()

                desc = (
                    f"Thesis target: bull=${pt.get('bull_target', 0):.2f}, "
                    f"base=${base_target:.2f}, bear=${pt.get('bear_target', 0):.2f}"
                )

                if existing:
                    existing.target_value = base_target
                    existing.direction = direction
                    existing.timeframe_days = timeframe
                    existing.target_description = desc
                    existing.confidence = confidence
                    existing.resolve_by = datetime.utcnow() + timedelta(days=timeframe)
                    logger.info(f"Updated price_target prediction for {symbol} -> ${base_target:.2f} (conf={confidence})")
                    return

            # No existing — create new
            self.save_prediction({
                "thesis_id": thesis_id,
                "symbol": symbol,
                "prediction_type": "price_target",
                "direction": direction,
                "target_value": base_target,
                "target_description": desc,
                "confidence": confidence,
                "timeframe_days": timeframe,
                "reasoning_category": "thesis_driven",
                "setup_type": "price_target",
                "key_reasoning": pt.get("notes", ""),
            })
            logger.info(f"Created price_target prediction for {symbol} -> ${base_target:.2f} (conf={confidence})")
        except Exception as e:
            logger.warning(f"Failed to create price_target prediction for {symbol}: {e}")

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


    # ------------------------------------------------------------------
    # Market Opinions
    # ------------------------------------------------------------------

    def save_opinion_batch(self, opinions: list[dict]) -> int:
        """Save a batch of market opinions in one transaction. Returns count saved."""
        from src.db.database import get_db
        from src.db.models import MarketOpinionRecord

        if not opinions:
            return 0

        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        saved = 0

        try:
            with get_db() as session:
                for op in opinions:
                    op.setdefault("id", f"op_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}")
                    op.setdefault("batch_id", batch_id)
                    op.setdefault("created", datetime.utcnow().isoformat())
                    op.setdefault("status", "open")

                    record = MarketOpinionRecord.from_dict(op)
                    session.add(record)
                    saved += 1

                session.commit()
        except Exception as e:
            logger.error(f"Failed to save opinion batch: {e}")
            return 0

        logger.info(f"Saved {saved} opinions (batch={batch_id})")
        return saved

    def score_opinion(self, opinion_id: str, horizon: int, scores: dict) -> bool:
        """Update scoring fields for an opinion at a given horizon (5, 10, or 30)."""
        from src.db.database import get_db
        from src.db.models import MarketOpinionRecord

        try:
            with get_db() as session:
                record = session.query(MarketOpinionRecord).filter(
                    MarketOpinionRecord.id == opinion_id
                ).first()
                if not record:
                    return False

                prefix = f"score_{horizon}d_"
                for key, val in scores.items():
                    col_name = f"{prefix}{key}" if not key.startswith("actual") else f"actual_{horizon}d_price"
                    if key == "actual_price":
                        col_name = f"actual_{horizon}d_price"
                    elif key == "actual_relative":
                        col_name = f"actual_relative_{horizon}d"
                    elif key == "score_relative":
                        col_name = f"score_relative_{horizon}d"
                    elif not key.startswith("score_"):
                        col_name = f"{prefix}{key}"
                    else:
                        col_name = key.replace("_Xd_", f"_{horizon}d_")

                    if hasattr(record, col_name):
                        setattr(record, col_name, val)

                setattr(record, f"scored_{horizon}d_at", datetime.utcnow())

                # Update status progression
                if horizon == 5:
                    record.status = "scored_5d"
                elif horizon == 10:
                    record.status = "scored_10d"
                elif horizon == 30:
                    record.status = "scored_30d"

                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to score opinion {opinion_id}: {e}")
            return False

    def get_opinion_scorecard(self, instance_id: str | None = None) -> dict:
        """Accuracy breakdown by horizon, symbol, and session type."""
        from src.db.database import get_db
        from src.db.models import MarketOpinionRecord

        try:
            with get_db() as session:
                q = session.query(MarketOpinionRecord).filter(
                    MarketOpinionRecord.status != "open"
                )
                if instance_id:
                    q = q.filter(MarketOpinionRecord.instance_id == instance_id)

                opinions = q.all()
                if not opinions:
                    return {"total_scored": 0}

                result = {"total_scored": len(opinions)}
                for horizon in (5, 10, 30):
                    scored = [o for o in opinions if getattr(o, f"score_{horizon}d_direction") is not None]
                    if scored:
                        dir_acc = sum(getattr(o, f"score_{horizon}d_direction") for o in scored) / len(scored)
                        range_acc = sum(getattr(o, f"score_{horizon}d_range") or 0 for o in scored) / len(scored)
                        avg_prox = sum(getattr(o, f"score_{horizon}d_proximity") or 0 for o in scored) / len(scored)
                        result[f"{horizon}d"] = {
                            "count": len(scored),
                            "direction_accuracy": round(dir_acc, 3),
                            "range_accuracy": round(range_acc, 3),
                            "avg_proximity": round(avg_prox, 3),
                        }

                return result
        except Exception as e:
            logger.error(f"Failed to get opinion scorecard: {e}")
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Decision Quality
    # ------------------------------------------------------------------

    def save_decision_quality(self, data: dict) -> str:
        """Save a decision quality tracking record."""
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord

        dq_id = data.get("id", f"dq_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}")
        data["id"] = dq_id

        try:
            with get_db() as session:
                existing = session.query(DecisionQualityRecord).filter(
                    DecisionQualityRecord.decision_id == data.get("decision_id")
                ).first()
                if existing:
                    for key, val in data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            setattr(existing, key, val)
                    dq_id = existing.id
                else:
                    record = DecisionQualityRecord.from_dict(data)
                    session.add(record)

                session.commit()
        except Exception as e:
            logger.error(f"Failed to save decision quality: {e}")
            return ""

        return dq_id

    def update_decision_quality(self, decision_id: str, updates: dict) -> bool:
        """Update scoring fields on a decision quality record."""
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord

        try:
            with get_db() as session:
                record = session.query(DecisionQualityRecord).filter(
                    DecisionQualityRecord.decision_id == decision_id
                ).first()
                if not record:
                    return False

                for key, val in updates.items():
                    if hasattr(record, key):
                        setattr(record, key, val)

                record.last_scored_at = datetime.utcnow()
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update decision quality for {decision_id}: {e}")
            return False


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
