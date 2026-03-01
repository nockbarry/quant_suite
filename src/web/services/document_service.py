"""Document service -- CRUD + queries for Document, Insight, Experiment."""

import json
import os
from pathlib import Path

from sqlalchemy import or_

from src.db.database import get_db
from src.db.models import Document, Insight, Experiment


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def list_documents(
    doc_type: str | None = None,
    symbol: str | None = None,
    search: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Return documents with optional filters. Ordered by created desc."""
    with get_db() as session:
        q = session.query(Document)
        if doc_type:
            q = q.filter(Document.doc_type == doc_type)
        if symbol:
            q = q.filter(Document.symbols.contains(f'"{symbol}"'))
        if source:
            q = q.filter(Document.source == source)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                or_(
                    Document.title.ilike(pattern),
                    Document.summary.ilike(pattern),
                    Document.tags.ilike(pattern),
                )
            )
        total = q.count()
        rows = q.order_by(Document.created.desc()).offset(offset).limit(limit).all()
        return [r.to_dict() for r in rows], total


def get_document(doc_id: str) -> dict | None:
    """Return a single document with full content."""
    with get_db() as session:
        row = session.query(Document).filter(Document.id == doc_id).first()
        if not row:
            return None
        d = row.to_dict()
        # Load content from file if not inline
        if not d.get("content_inline") and d.get("file_path"):
            try:
                d["content_loaded"] = Path(d["file_path"]).read_text()
            except Exception:
                d["content_loaded"] = None
        return d


def get_documents_for_thesis(thesis_id: str) -> list[dict]:
    """Return documents linked to a thesis."""
    with get_db() as session:
        rows = (
            session.query(Document)
            .filter(Document.thesis_id == thesis_id)
            .order_by(Document.created.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_documents_for_agent_run(agent_run_id: str) -> list[dict]:
    """Return documents produced by an agent run."""
    with get_db() as session:
        rows = (
            session.query(Document)
            .filter(Document.agent_run_id == agent_run_id)
            .order_by(Document.created.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_documents_for_decision(decision_id: str) -> list[dict]:
    """Return documents linked to a decision."""
    with get_db() as session:
        rows = (
            session.query(Document)
            .filter(Document.decision_id == decision_id)
            .order_by(Document.created.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


def get_doc_type_counts() -> dict[str, int]:
    """Return count of documents by doc_type."""
    from sqlalchemy import func

    with get_db() as session:
        rows = (
            session.query(Document.doc_type, func.count(Document.id))
            .group_by(Document.doc_type)
            .all()
        )
        return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def list_insights(
    category: str | None = None,
    search: str | None = None,
    validated_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Return insights with optional filters."""
    with get_db() as session:
        q = session.query(Insight)
        if category:
            q = q.filter(Insight.category == category)
        if validated_only:
            q = q.filter(Insight.validated == True)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                or_(
                    Insight.title.ilike(pattern),
                    Insight.description.ilike(pattern),
                )
            )
        rows = q.order_by(Insight.created_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_insight(insight_id: str) -> dict | None:
    """Return a single insight."""
    with get_db() as session:
        row = session.query(Insight).filter(Insight.id == insight_id).first()
        return row.to_dict() if row else None


def get_insight_categories() -> dict[str, int]:
    """Return count of insights by category."""
    from sqlalchemy import func

    with get_db() as session:
        rows = (
            session.query(Insight.category, func.count(Insight.id))
            .group_by(Insight.category)
            .all()
        )
        return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


def list_experiments(
    strategy: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return experiments with optional filters."""
    with get_db() as session:
        q = session.query(Experiment)
        if strategy:
            q = q.filter(Experiment.strategy == strategy)
        if symbol:
            q = q.filter(Experiment.symbol == symbol)
        rows = q.order_by(Experiment.run_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_experiment(exp_id: str) -> dict | None:
    """Return a single experiment."""
    with get_db() as session:
        row = session.query(Experiment).filter(Experiment.id == exp_id).first()
        return row.to_dict() if row else None
