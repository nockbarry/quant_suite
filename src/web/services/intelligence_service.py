"""Intelligence service — DB queries for the intelligence dashboard.

Follows the same pattern as decision_service.py.
"""

import json
import logging
from datetime import datetime, timedelta

from src.db.database import get_db
from src.db.models import DecisionRecord, PredictionRecord, ThesisRecord, LearningRecord

logger = logging.getLogger(__name__)


def list_predictions(
    limit: int = 50,
    symbol: str | None = None,
    status: str | None = None,
    prediction_type: str | None = None,
) -> list[dict]:
    """Return predictions with optional filters. Most recent first."""
    try:
        with get_db() as session:
            q = session.query(PredictionRecord)
            if symbol:
                q = q.filter(PredictionRecord.symbol == symbol.upper())
            if status:
                q = q.filter(PredictionRecord.status == status)
            if prediction_type:
                q = q.filter(PredictionRecord.prediction_type == prediction_type)
            rows = q.order_by(PredictionRecord.created.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]
    except Exception as e:
        logger.warning(f"list_predictions failed: {e}")
        return []


def get_prediction(pred_id: str) -> dict | None:
    """Return a single prediction by id."""
    try:
        with get_db() as session:
            row = session.query(PredictionRecord).filter(
                PredictionRecord.id == pred_id
            ).first()
            return row.to_dict() if row else None
    except Exception as e:
        logger.warning(f"get_prediction failed: {e}")
        return None


def get_prediction_scorecard() -> dict:
    """Accuracy breakdown by type, category, and overall."""
    from src.db.write_api import athena_db
    return athena_db.get_prediction_scorecard()


def get_calibration_data() -> dict:
    """Calibration bins for Chart.js scatter plot."""
    from src.intelligence.context_builder import DecisionContextBuilder
    builder = DecisionContextBuilder()
    cal = builder._get_calibration_data()
    return {
        "bins": cal.bins,
        "overconfident": cal.overconfident,
        "calibration_error": cal.calibration_error,
        "total_resolved": cal.total_resolved,
    }


def get_setup_type_performance() -> list[dict]:
    """Per-type metrics for the setup type table."""
    from src.intelligence.setup_scorer import SetupScorer
    scorer = SetupScorer()
    perfs = scorer.get_performance_by_type(min_samples=1)
    return [
        {
            "setup_type": p.setup_type,
            "total_decisions": p.total_decisions,
            "wins": p.wins,
            "losses": p.losses,
            "win_rate": round(p.win_rate, 3),
            "avg_return_pct": round(p.avg_return_pct, 2),
            "avg_hold_days": round(p.avg_hold_days, 1),
            "sample_adequate": p.sample_adequate,
        }
        for p in perfs
    ]


def get_signal_quality_leaderboard() -> list[dict]:
    """Signal types ranked by hit rate."""
    import os
    from pathlib import Path

    quality_path = Path(
        os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
    ) / "signal_quality" / "quality.json"

    if not quality_path.exists():
        return []

    try:
        data = json.loads(quality_path.read_text())
        result = []
        for name, metrics in data.items():
            if isinstance(metrics, dict):
                result.append({
                    "signal_type": name,
                    "hit_rate": metrics.get("hit_rate", 0),
                    "ic": metrics.get("ic", 0),
                    "trend": metrics.get("trend", "stable"),
                    "sample_size": metrics.get("sample_size", 0),
                })
        return sorted(result, key=lambda x: x["hit_rate"], reverse=True)
    except Exception as e:
        logger.warning(f"Signal quality leaderboard failed: {e}")
        return []


def get_intelligence_summary() -> dict:
    """High-level 'getting smarter' metrics."""
    try:
        with get_db() as session:
            # Total predictions
            total_preds = session.query(PredictionRecord).count()
            open_preds = session.query(PredictionRecord).filter(
                PredictionRecord.status == "open"
            ).count()
            resolved = session.query(PredictionRecord).filter(
                PredictionRecord.status.in_(["hit", "miss", "expired"])
            ).all()

            total_resolved = len(resolved)
            hits = sum(1 for r in resolved if r.status == "hit")
            accuracy = hits / total_resolved if total_resolved else 0

            briers = [r.brier_score for r in resolved if r.brier_score is not None]
            avg_brier = sum(briers) / len(briers) if briers else None

            # Decision win rate (rolling 30d)
            cutoff_30d = datetime.utcnow() - timedelta(days=30)
            recent_decisions = session.query(DecisionRecord).filter(
                DecisionRecord.timestamp >= cutoff_30d,
                DecisionRecord.realized_pnl_pct.isnot(None),
            ).all()

            decision_win_rate = 0
            if recent_decisions:
                wins = sum(1 for d in recent_decisions if (d.realized_pnl_pct or 0) > 0)
                decision_win_rate = wins / len(recent_decisions)

            # Best setup type
            from src.intelligence.setup_scorer import SetupScorer
            scorer = SetupScorer()
            best_setups = scorer.get_best_setups()

            return {
                "total_predictions": total_preds,
                "open_predictions": open_preds,
                "total_resolved": total_resolved,
                "prediction_accuracy": round(accuracy, 3),
                "avg_brier_score": round(avg_brier, 4) if avg_brier is not None else None,
                "decision_win_rate_30d": round(decision_win_rate, 3),
                "recent_decisions_30d": len(recent_decisions),
                "best_setup_types": best_setups,
            }
    except Exception as e:
        logger.warning(f"Intelligence summary failed: {e}")
        return {
            "total_predictions": 0, "open_predictions": 0,
            "total_resolved": 0, "prediction_accuracy": 0,
            "avg_brier_score": None, "decision_win_rate_30d": 0,
            "recent_decisions_30d": 0, "best_setup_types": [],
        }


def get_distinct_prediction_types() -> list[str]:
    """Return sorted list of unique prediction types."""
    try:
        with get_db() as session:
            rows = session.query(PredictionRecord.prediction_type).distinct().all()
            return sorted([r[0] for r in rows if r[0]])
    except Exception:
        return []


def get_distinct_prediction_statuses() -> list[str]:
    """Return sorted list of unique prediction statuses."""
    return ["open", "hit", "miss", "expired", "cancelled"]
