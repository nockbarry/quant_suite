"""Web service layer for the Market Opinion System."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def list_opinions(limit: int = 50, symbol: str = None, instance_id: str = None) -> list[dict]:
    """List recent opinions with optional filters."""
    from src.db.database import get_db
    from src.db.models import MarketOpinionRecord

    try:
        with get_db() as session:
            q = session.query(MarketOpinionRecord).order_by(
                MarketOpinionRecord.created.desc()
            )
            if symbol:
                q = q.filter(MarketOpinionRecord.symbol == symbol.upper())
            if instance_id:
                q = q.filter(MarketOpinionRecord.instance_id == instance_id)
            return [o.to_dict() for o in q.limit(limit).all()]
    except Exception as e:
        logger.error(f"list_opinions failed: {e}")
        return []


def get_opinion_scorecard(instance_id: str = None) -> dict:
    """Get opinion accuracy scorecard."""
    from src.db.write_api import athena_db
    return athena_db.get_opinion_scorecard(instance_id)


def get_opinion_calibration() -> dict:
    """Read opinion calibration from file."""
    from src.core.paths import paths
    cal_path = paths.base / "intelligence" / "opinion_calibration.json"
    if cal_path.exists():
        try:
            return json.loads(cal_path.read_text())
        except Exception:
            pass
    return {"bins": [], "total_scored": 0}


def get_decision_quality_curves() -> dict:
    """Get decision quality curves for all instances."""
    from src.opinions.decision_quality import DecisionQualityTracker

    tracker = DecisionQualityTracker()
    result = {}

    # Get curves for each known instance
    for instance in ("auto", "beta", "gamma"):
        curve = tracker.get_quality_curve(instance_id=instance, horizon=10)
        if curve:
            result[instance] = curve

    # Also get overall summary
    result["summary"] = tracker.get_quality_summary()

    return result


def get_decision_quality_summary() -> dict:
    """Read decision quality summary from file."""
    from src.core.paths import paths
    path = paths.base / "intelligence" / "decision_quality.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"total": 0}


def get_opinion_divergence() -> dict:
    """Read cross-instance opinion divergence from meta-observer report."""
    from src.core.paths import paths
    report_path = paths.base / "parallel" / "meta_report_latest.json"
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text())
            return data.get("opinion_divergence", {})
        except Exception:
            pass
    return {}


def get_symbol_opinion_history(symbol: str, limit: int = 100) -> list[dict]:
    """Get opinion history for a single symbol across all instances."""
    from src.db.database import get_db
    from src.db.models import MarketOpinionRecord

    try:
        with get_db() as session:
            opinions = session.query(MarketOpinionRecord).filter(
                MarketOpinionRecord.symbol == symbol.upper()
            ).order_by(
                MarketOpinionRecord.created.desc()
            ).limit(limit).all()
            return [o.to_dict() for o in opinions]
    except Exception as e:
        logger.error(f"get_symbol_opinion_history failed: {e}")
        return []
