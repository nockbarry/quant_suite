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


def get_cross_instance_accuracy() -> dict:
    """Compare opinion and decision accuracy across all instances.

    Reads each instance's DB directly to compute per-instance metrics.
    Returns dict with per-instance accuracy + comparison insights.
    """
    import sqlite3
    from pathlib import Path

    instances = {
        "auto": Path.home() / "quant_results" / "athena.db",
        "beta": Path.home() / "quant_results_beta" / "athena.db",
        "gamma": Path.home() / "quant_results_gamma" / "athena.db",
    }

    result = {}
    for inst, db_path in instances.items():
        if not db_path.exists():
            continue

        try:
            conn = sqlite3.connect(str(db_path))

            # Opinion stats
            total_opinions = conn.execute(
                "SELECT COUNT(*) FROM market_opinions"
            ).fetchone()[0]
            scored_opinions = conn.execute(
                "SELECT COUNT(*) FROM market_opinions WHERE score_10d_direction IS NOT NULL"
            ).fetchone()[0]

            inst_data = {
                "total_opinions": total_opinions,
                "scored_opinions": scored_opinions,
            }

            if scored_opinions > 0:
                avg_dir = conn.execute(
                    "SELECT AVG(score_10d_direction) FROM market_opinions "
                    "WHERE score_10d_direction IS NOT NULL"
                ).fetchone()[0]
                avg_range = conn.execute(
                    "SELECT AVG(score_10d_range) FROM market_opinions "
                    "WHERE score_10d_range IS NOT NULL"
                ).fetchone()[0]
                avg_prox = conn.execute(
                    "SELECT AVG(score_10d_proximity) FROM market_opinions "
                    "WHERE score_10d_proximity IS NOT NULL"
                ).fetchone()[0]
                inst_data["direction_accuracy_10d"] = round(avg_dir, 3) if avg_dir else None
                inst_data["range_accuracy_10d"] = round(avg_range, 3) if avg_range else None
                inst_data["proximity_10d"] = round(avg_prox, 3) if avg_prox else None

                # Per-thesis accuracy (top and bottom)
                rows = conn.execute(
                    "SELECT thesis_id, COUNT(*) as n, AVG(score_10d_direction) as acc "
                    "FROM market_opinions "
                    "WHERE score_10d_direction IS NOT NULL AND thesis_id IS NOT NULL AND thesis_id != '' "
                    "GROUP BY thesis_id HAVING n >= 5 ORDER BY acc DESC"
                ).fetchall()
                inst_data["thesis_accuracy"] = [
                    {"thesis_id": r[0][:8], "n": r[1], "accuracy": round(r[2], 3)}
                    for r in rows
                ]

            # Decision quality
            try:
                dq_rows = conn.execute(
                    "SELECT COUNT(*), AVG(quality_10d), AVG(return_10d), AVG(spy_return_10d) "
                    "FROM decision_quality WHERE quality_10d IS NOT NULL"
                ).fetchone()
                if dq_rows and dq_rows[0] > 0:
                    inst_data["decision_quality_10d"] = {
                        "count": dq_rows[0],
                        "avg_quality": round(dq_rows[1], 3),
                        "avg_return": round(dq_rows[2], 2),
                        "avg_alpha": round(dq_rows[2] - dq_rows[3], 2) if dq_rows[3] else None,
                    }
            except Exception:
                pass  # Table might not exist in beta/gamma yet

            conn.close()
            result[inst] = inst_data

        except Exception as e:
            logger.error(f"Error reading {inst} DB: {e}")
            result[inst] = {"error": str(e)}

    return result


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
