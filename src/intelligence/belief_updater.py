"""Belief Update System — daily update of signal weights, calibration, and learning summary.

Run after prediction scoring (5:30 PM) to:
1. Update signal quality weights from outcomes
2. Suggest thesis conviction changes based on prediction accuracy
3. Update calibration data
4. Generate natural language learning summary
5. Track "getting smarter" metrics over time

Usage:
    from src.intelligence.belief_updater import BeliefUpdater
    updater = BeliefUpdater()
    report = updater.run_daily_update()
    print(report.learning_summary)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


@dataclass
class SignalUpdate:
    signal_type: str
    old_weight: float
    new_weight: float
    hit_rate: float
    sample_size: int


@dataclass
class ThesisSuggestion:
    thesis_id: str
    thesis_name: str
    current_conviction: float
    suggested_change: float  # positive = increase, negative = decrease
    reason: str
    prediction_accuracy: float
    prediction_count: int


@dataclass
class BeliefUpdateReport:
    timestamp: str = ""
    signal_updates: list[SignalUpdate] = field(default_factory=list)
    thesis_suggestions: list[ThesisSuggestion] = field(default_factory=list)
    calibration: dict = field(default_factory=dict)
    learning_summary: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "signal_updates": [
                {
                    "signal_type": u.signal_type,
                    "old_weight": u.old_weight,
                    "new_weight": u.new_weight,
                    "hit_rate": u.hit_rate,
                    "sample_size": u.sample_size,
                }
                for u in self.signal_updates
            ],
            "thesis_suggestions": [
                {
                    "thesis_id": s.thesis_id,
                    "thesis_name": s.thesis_name,
                    "current_conviction": s.current_conviction,
                    "suggested_change": s.suggested_change,
                    "reason": s.reason,
                    "prediction_accuracy": s.prediction_accuracy,
                    "prediction_count": s.prediction_count,
                }
                for s in self.thesis_suggestions
            ],
            "calibration": self.calibration,
            "learning_summary": self.learning_summary,
            "metrics": self.metrics,
        }


class BeliefUpdater:
    """Automated belief update after prediction scoring."""

    def run_daily_update(self) -> BeliefUpdateReport:
        """Run all belief updates and generate report."""
        report = BeliefUpdateReport(
            timestamp=datetime.utcnow().isoformat(),
        )

        report.signal_updates = self._update_signal_quality()
        report.thesis_suggestions = self._suggest_thesis_updates()
        report.calibration = self._update_calibration()
        report.metrics = self._compute_metrics()
        report.learning_summary = self._generate_learning_summary(report)
        self._persist_report(report)
        self._append_metrics_history(report.metrics)

        return report

    def _update_signal_quality(self) -> list[SignalUpdate]:
        """Read signal outcome history, compute new weights, write weights.json."""
        outcomes_path = _results_dir() / "signal_quality" / "outcomes.jsonl"
        weights_path = _results_dir() / "signal_quality" / "weights.json"
        quality_path = _results_dir() / "signal_quality" / "quality.json"

        if not outcomes_path.exists():
            return []

        # Read outcomes
        outcomes_by_type: dict[str, list] = {}
        try:
            for line in outcomes_path.read_text().strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                sig_type = entry.get("signal_type", "unknown")
                outcomes_by_type.setdefault(sig_type, []).append(entry)
        except Exception as e:
            logger.warning(f"Failed to read signal outcomes: {e}")
            return []

        # Read current weights
        old_weights = {}
        if weights_path.exists():
            try:
                old_weights = json.loads(weights_path.read_text())
            except Exception:
                pass

        # Compute new weights: hit_rate * information_coefficient
        new_weights = {}
        updates = []
        quality_data = {}

        for sig_type, entries in outcomes_by_type.items():
            hits = sum(1 for e in entries if e.get("pnl", 0) > 0)
            hit_rate = hits / len(entries) if entries else 0

            # IC approximation from pnl correlation with signal strength
            strengths = [e.get("signal_strength", 0.5) for e in entries]
            pnls = [e.get("pnl", 0) for e in entries]
            ic = self._simple_correlation(strengths, pnls)

            weight = round(hit_rate * max(ic, 0.01), 4)
            new_weights[sig_type] = weight

            old_w = old_weights.get(sig_type, 0.5)

            # Determine trend
            if weight > old_w + 0.02:
                trend = "improving"
            elif weight < old_w - 0.02:
                trend = "declining"
            else:
                trend = "stable"

            quality_data[sig_type] = {
                "hit_rate": round(hit_rate, 3),
                "ic": round(ic, 3),
                "weight": weight,
                "sample_size": len(entries),
                "trend": trend,
            }

            updates.append(SignalUpdate(
                signal_type=sig_type,
                old_weight=old_w,
                new_weight=weight,
                hit_rate=round(hit_rate, 3),
                sample_size=len(entries),
            ))

        # Persist
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            weights_path.write_text(json.dumps(new_weights, indent=2))
            quality_path.write_text(json.dumps(quality_data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to write signal weights: {e}")

        return updates

    def _suggest_thesis_updates(self) -> list[ThesisSuggestion]:
        """Suggest conviction changes based on prediction accuracy per thesis."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord, ThesisRecord

        suggestions = []

        try:
            with get_db() as session:
                # Get theses with resolved predictions
                theses = session.query(ThesisRecord).filter(
                    ThesisRecord.status == "active"
                ).all()

                for thesis in theses:
                    preds = session.query(PredictionRecord).filter(
                        PredictionRecord.thesis_id == thesis.id,
                        PredictionRecord.status.in_(["hit", "miss"]),
                    ).all()

                    if len(preds) < 3:
                        continue

                    hits = sum(1 for p in preds if p.status == "hit")
                    accuracy = hits / len(preds)

                    # Suggestion logic
                    suggested_change = 0
                    reason = ""
                    if accuracy >= 0.75 and len(preds) >= 5:
                        suggested_change = 5
                        reason = f"{accuracy:.0%} prediction accuracy over {len(preds)} predictions — strong confirmation"
                    elif accuracy >= 0.6:
                        suggested_change = 2
                        reason = f"{accuracy:.0%} accuracy — mild confirmation"
                    elif accuracy <= 0.35:
                        suggested_change = -10
                        reason = f"Only {accuracy:.0%} accuracy — predictions consistently wrong"
                    elif accuracy <= 0.45:
                        suggested_change = -5
                        reason = f"{accuracy:.0%} accuracy — below coin flip"

                    if suggested_change != 0:
                        suggestions.append(ThesisSuggestion(
                            thesis_id=thesis.id,
                            thesis_name=thesis.name,
                            current_conviction=thesis.conviction or 0,
                            suggested_change=suggested_change,
                            reason=reason,
                            prediction_accuracy=round(accuracy, 3),
                            prediction_count=len(preds),
                        ))
        except Exception as e:
            logger.warning(f"Thesis suggestion query failed: {e}")

        return suggestions

    def _update_calibration(self) -> dict:
        """Compute and persist calibration data."""
        from src.intelligence.context_builder import DecisionContextBuilder

        builder = DecisionContextBuilder()
        cal = builder._get_calibration_data()

        cal_data = {
            "bins": cal.bins,
            "overconfident": cal.overconfident,
            "calibration_error": cal.calibration_error,
            "total_resolved": cal.total_resolved,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Persist
        cal_path = _results_dir() / "intelligence" / "calibration.json"
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cal_path.write_text(json.dumps(cal_data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to write calibration: {e}")

        return cal_data

    def _compute_metrics(self) -> dict:
        """Compute "getting smarter" metrics."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord, DecisionRecord
        from datetime import timedelta

        metrics = {}
        cutoff_30d = datetime.utcnow() - timedelta(days=30)

        try:
            with get_db() as session:
                # Prediction accuracy (rolling 30d)
                recent_preds = session.query(PredictionRecord).filter(
                    PredictionRecord.resolved_at >= cutoff_30d,
                    PredictionRecord.status.in_(["hit", "miss"]),
                ).all()
                if recent_preds:
                    hits = sum(1 for p in recent_preds if p.status == "hit")
                    metrics["prediction_accuracy_30d"] = round(hits / len(recent_preds), 3)
                    briers = [p.brier_score for p in recent_preds if p.brier_score is not None]
                    metrics["avg_brier_30d"] = round(sum(briers) / len(briers), 4) if briers else None
                else:
                    metrics["prediction_accuracy_30d"] = None
                    metrics["avg_brier_30d"] = None

                # Decision win rate (rolling 30d)
                recent_decisions = session.query(DecisionRecord).filter(
                    DecisionRecord.timestamp >= cutoff_30d,
                    DecisionRecord.realized_pnl_pct.isnot(None),
                ).all()
                if recent_decisions:
                    wins = sum(1 for d in recent_decisions if (d.realized_pnl_pct or 0) > 0)
                    metrics["decision_win_rate_30d"] = round(wins / len(recent_decisions), 3)
                else:
                    metrics["decision_win_rate_30d"] = None
        except Exception as e:
            logger.warning(f"Metrics computation failed: {e}")

        metrics["date"] = datetime.utcnow().strftime("%Y-%m-%d")
        return metrics

    def _generate_learning_summary(self, report: BeliefUpdateReport) -> str:
        """Generate natural language learning summary."""
        lines = [f"=== BELIEF UPDATE — {report.timestamp[:10]} ===", ""]

        # Signal updates
        improving = [u for u in report.signal_updates if u.new_weight > u.old_weight + 0.02]
        declining = [u for u in report.signal_updates if u.new_weight < u.old_weight - 0.02]
        if improving:
            lines.append("IMPROVING SIGNALS:")
            for u in improving:
                lines.append(f"  {u.signal_type}: {u.hit_rate:.0%} hit rate ({u.sample_size} samples)")
        if declining:
            lines.append("DECLINING SIGNALS:")
            for u in declining:
                lines.append(f"  {u.signal_type}: {u.hit_rate:.0%} hit rate ({u.sample_size} samples)")
        if not improving and not declining:
            lines.append("Signal quality stable.")
        lines.append("")

        # Thesis suggestions
        if report.thesis_suggestions:
            lines.append("THESIS CONVICTION SUGGESTIONS:")
            for s in report.thesis_suggestions:
                direction = "increase" if s.suggested_change > 0 else "decrease"
                lines.append(f"  {s.thesis_name}: {direction} by {abs(s.suggested_change)}% — {s.reason}")
            lines.append("")

        # Calibration
        cal = report.calibration
        if cal.get("total_resolved", 0) > 0:
            lines.append("CALIBRATION:")
            if cal.get("overconfident"):
                lines.append(f"  Overconfident by ~{cal.get('calibration_error', 0):.0%}")
            else:
                lines.append(f"  Calibration error: {cal.get('calibration_error', 0):.1%}")
            lines.append("")

        # Metrics
        m = report.metrics
        lines.append("METRICS:")
        if m.get("prediction_accuracy_30d") is not None:
            lines.append(f"  Prediction accuracy (30d): {m['prediction_accuracy_30d']:.0%}")
        if m.get("decision_win_rate_30d") is not None:
            lines.append(f"  Decision win rate (30d): {m['decision_win_rate_30d']:.0%}")
        if m.get("avg_brier_30d") is not None:
            lines.append(f"  Avg Brier score (30d): {m['avg_brier_30d']:.4f}")

        return "\n".join(lines)

    def _persist_report(self, report: BeliefUpdateReport):
        """Save report to intelligence directory."""
        report_dir = _results_dir() / "intelligence"
        report_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.utcnow().strftime("%Y%m%d")
        report_path = report_dir / f"daily_update_{date_str}.json"

        try:
            report_path.write_text(json.dumps(report.to_dict(), indent=2))
            logger.info(f"Belief update report saved: {report_path}")
        except Exception as e:
            logger.warning(f"Failed to persist belief update report: {e}")

    def _append_metrics_history(self, metrics: dict):
        """Append daily metrics to history JSONL for trend tracking."""
        history_path = _results_dir() / "intelligence" / "metrics_history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(history_path, "a") as f:
                f.write(json.dumps(metrics) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append metrics history: {e}")

    @staticmethod
    def _simple_correlation(x: list[float], y: list[float]) -> float:
        """Simple Pearson correlation without numpy dependency."""
        n = len(x)
        if n < 3:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = (sum((xi - mean_x) ** 2 for xi in x) / n) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y) / n) ** 0.5

        if std_x < 1e-10 or std_y < 1e-10:
            return 0.0

        return cov / (std_x * std_y)
