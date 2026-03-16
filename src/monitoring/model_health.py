"""
ML Model Health Monitoring.

Tracks model performance, drift, and staleness to ensure
the ML components are producing reliable signals.

Key metrics:
- Prediction accuracy (rolling)
- Feature importance stability
- Concept drift detection
- Model staleness
- Input distribution shifts
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Model health status."""
    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    RETRAIN_NEEDED = "retrain_needed"
    OFFLINE = "offline"


class DriftType(str, Enum):
    """Types of drift detected."""
    NONE = "none"
    COVARIATE = "covariate"  # Input distribution changed
    CONCEPT = "concept"      # Relationship changed
    LABEL = "label"         # Target distribution changed


@dataclass
class PredictionLog:
    """Log of a model prediction."""
    timestamp: datetime
    model_name: str
    symbol: str
    prediction: float
    confidence: float
    actual: float | None = None
    features_hash: str = ""

    @property
    def is_correct(self) -> bool | None:
        if self.actual is None:
            return None
        return (self.prediction > 0) == (self.actual > 0)

    @property
    def error(self) -> float | None:
        if self.actual is None:
            return None
        return abs(self.prediction - self.actual)


@dataclass
class ModelHealthMetrics:
    """Health metrics for a single model."""
    model_name: str
    status: ModelStatus
    last_prediction: datetime | None
    last_training: datetime | None
    predictions_count_24h: int
    accuracy_7d: float | None
    accuracy_30d: float | None
    mean_absolute_error: float | None
    drift_detected: DriftType
    drift_score: float
    feature_importance_stability: float
    staleness_days: float
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "status": self.status.value,
            "last_prediction": self.last_prediction.isoformat() if self.last_prediction else None,
            "last_training": self.last_training.isoformat() if self.last_training else None,
            "predictions_24h": self.predictions_count_24h,
            "accuracy_7d": round(self.accuracy_7d, 3) if self.accuracy_7d else None,
            "accuracy_30d": round(self.accuracy_30d, 3) if self.accuracy_30d else None,
            "mae": round(self.mean_absolute_error, 4) if self.mean_absolute_error else None,
            "drift_type": self.drift_detected.value,
            "drift_score": round(self.drift_score, 3),
            "feature_stability": round(self.feature_importance_stability, 3),
            "staleness_days": round(self.staleness_days, 1),
            "issues": self.issues,
        }


@dataclass
class OverallModelHealth:
    """Overall health status of all models."""
    timestamp: datetime
    models: list[ModelHealthMetrics]
    summary: dict[str, int]

    @property
    def overall_status(self) -> ModelStatus:
        statuses = [m.status for m in self.models]
        if ModelStatus.OFFLINE in statuses or ModelStatus.RETRAIN_NEEDED in statuses:
            return ModelStatus.DEGRADED
        if ModelStatus.WARNING in statuses or ModelStatus.DEGRADED in statuses:
            return ModelStatus.WARNING
        return ModelStatus.HEALTHY

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "summary": self.summary,
            "models": [m.to_dict() for m in self.models],
        }


class ModelHealthMonitor:
    """
    Monitors health and performance of ML models.

    Tracks:
    - Prediction accuracy over time
    - Feature importance drift
    - Input distribution shifts
    - Model staleness
    - Concept drift
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.models_dir = self.results_dir / "models"
        self.predictions_log = self.results_dir / "logs" / "predictions.jsonl"

        # Thresholds
        self.ACCURACY_WARNING = 0.55  # Below this = warning
        self.ACCURACY_CRITICAL = 0.50  # Below this = retrain
        self.DRIFT_WARNING = 0.1
        self.DRIFT_CRITICAL = 0.2
        self.STALENESS_WARNING_DAYS = 30
        self.STALENESS_CRITICAL_DAYS = 90

        # Cache
        self._predictions_cache: list[PredictionLog] = []
        self._last_cache_load: datetime | None = None

    def _load_predictions(self, days: int = 30) -> list[PredictionLog]:
        """Load recent predictions from log."""
        if not self.predictions_log.exists():
            return []

        # Use cache if fresh
        if self._last_cache_load and (datetime.now() - self._last_cache_load) < timedelta(minutes=5):
            return self._predictions_cache

        cutoff = datetime.now() - timedelta(days=days)
        predictions = []

        try:
            with open(self.predictions_log) as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        ts = datetime.fromisoformat(data["timestamp"])
                        if ts > cutoff:
                            predictions.append(PredictionLog(
                                timestamp=ts,
                                model_name=data["model_name"],
                                symbol=data.get("symbol", ""),
                                prediction=data["prediction"],
                                confidence=data.get("confidence", 0.5),
                                actual=data.get("actual"),
                                features_hash=data.get("features_hash", ""),
                            ))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.error(f"Error loading predictions: {e}")

        self._predictions_cache = predictions
        self._last_cache_load = datetime.now()
        return predictions

    async def check_all_models(self) -> OverallModelHealth:
        """Check health of all models."""
        models = []

        # Find model directories
        if self.models_dir.exists():
            for model_dir in self.models_dir.iterdir():
                if model_dir.is_dir():
                    metrics = await self._check_model(model_dir.name)
                    models.append(metrics)

        # If no models found, check for model files directly
        if not models:
            for model_file in self.models_dir.glob("*.pkl"):
                metrics = await self._check_model(model_file.stem)
                models.append(metrics)

        # Summary
        summary = {status.value: 0 for status in ModelStatus}
        for m in models:
            summary[m.status.value] += 1

        return OverallModelHealth(
            timestamp=datetime.now(),
            models=models,
            summary=summary,
        )

    async def _check_model(self, model_name: str) -> ModelHealthMetrics:
        """Check health of a specific model."""
        issues = []

        # Check model file
        model_path = self.models_dir / model_name
        if not model_path.exists():
            model_path = self.models_dir / f"{model_name}.pkl"

        last_training = None
        staleness_days = float("inf")

        if model_path.exists():
            mtime = datetime.fromtimestamp(model_path.stat().st_mtime)
            last_training = mtime
            staleness_days = (datetime.now() - mtime).days
        else:
            issues.append("Model file not found")

        # Load predictions for this model
        all_preds = self._load_predictions(days=30)
        model_preds = [p for p in all_preds if p.model_name == model_name]

        # Calculate metrics
        predictions_24h = len([
            p for p in model_preds
            if p.timestamp > datetime.now() - timedelta(hours=24)
        ])

        last_prediction = None
        if model_preds:
            last_prediction = max(p.timestamp for p in model_preds)

        # Accuracy (for predictions with actuals)
        accuracy_7d = self._calculate_accuracy(model_preds, days=7)
        accuracy_30d = self._calculate_accuracy(model_preds, days=30)
        mae = self._calculate_mae(model_preds, days=30)

        # Drift detection
        drift_type, drift_score = self._detect_drift(model_preds)

        # Feature importance stability
        fi_stability = self._check_feature_stability(model_name)

        # Determine status
        status = self._determine_status(
            accuracy_30d, drift_score, staleness_days, predictions_24h, issues
        )

        # Generate issues
        if staleness_days > self.STALENESS_CRITICAL_DAYS:
            issues.append(f"Model is {staleness_days:.0f} days old - needs retraining")
        elif staleness_days > self.STALENESS_WARNING_DAYS:
            issues.append(f"Model is {staleness_days:.0f} days old")

        if accuracy_30d and accuracy_30d < self.ACCURACY_CRITICAL:
            issues.append(f"Low accuracy: {accuracy_30d:.1%}")

        if drift_score > self.DRIFT_WARNING:
            issues.append(f"Drift detected: {drift_type.value} (score: {drift_score:.2f})")

        if predictions_24h == 0 and last_prediction:
            hours_since = (datetime.now() - last_prediction).total_seconds() / 3600
            if hours_since > 24:
                issues.append(f"No predictions in {hours_since:.0f} hours")

        return ModelHealthMetrics(
            model_name=model_name,
            status=status,
            last_prediction=last_prediction,
            last_training=last_training,
            predictions_count_24h=predictions_24h,
            accuracy_7d=accuracy_7d,
            accuracy_30d=accuracy_30d,
            mean_absolute_error=mae,
            drift_detected=drift_type,
            drift_score=drift_score,
            feature_importance_stability=fi_stability,
            staleness_days=staleness_days,
            issues=issues,
        )

    def _calculate_accuracy(self, predictions: list[PredictionLog], days: int) -> float | None:
        """Calculate directional accuracy for recent predictions."""
        cutoff = datetime.now() - timedelta(days=days)
        recent = [p for p in predictions if p.timestamp > cutoff and p.actual is not None]

        if len(recent) < 10:
            return None

        correct = sum(1 for p in recent if p.is_correct)
        return correct / len(recent)

    def _calculate_mae(self, predictions: list[PredictionLog], days: int) -> float | None:
        """Calculate mean absolute error."""
        cutoff = datetime.now() - timedelta(days=days)
        recent = [p for p in predictions if p.timestamp > cutoff and p.actual is not None]

        if len(recent) < 10:
            return None

        errors = [p.error for p in recent if p.error is not None]
        return np.mean(errors) if errors else None

    def _detect_drift(self, predictions: list[PredictionLog]) -> tuple[DriftType, float]:
        """Detect drift in predictions."""
        if len(predictions) < 50:
            return DriftType.NONE, 0.0

        # Split into two halves
        sorted_preds = sorted(predictions, key=lambda p: p.timestamp)
        midpoint = len(sorted_preds) // 2
        early = sorted_preds[:midpoint]
        late = sorted_preds[midpoint:]

        # Compare prediction distributions
        early_preds = [p.prediction for p in early]
        late_preds = [p.prediction for p in late]

        # Simple distribution shift using mean/std comparison
        early_mean, early_std = np.mean(early_preds), np.std(early_preds)
        late_mean, late_std = np.mean(late_preds), np.std(late_preds)

        mean_shift = abs(late_mean - early_mean) / (early_std + 1e-6)
        std_shift = abs(late_std - early_std) / (early_std + 1e-6)

        covariate_score = (mean_shift + std_shift) / 2

        # Check for concept drift (accuracy change)
        concept_score = 0.0
        early_acc = sum(1 for p in early if p.is_correct) / len(early) if early else 0
        late_acc = sum(1 for p in late if p.is_correct) / len(late) if late else 0
        concept_score = abs(late_acc - early_acc)

        # Return the more severe drift
        if concept_score > covariate_score and concept_score > 0.1:
            return DriftType.CONCEPT, concept_score
        elif covariate_score > 0.1:
            return DriftType.COVARIATE, covariate_score

        return DriftType.NONE, max(concept_score, covariate_score)

    def _check_feature_stability(self, model_name: str) -> float:
        """Check stability of feature importance over time."""
        # Look for feature importance logs
        fi_file = self.models_dir / model_name / "feature_importance.json"
        if not fi_file.exists():
            return 1.0  # Assume stable if no history

        try:
            with open(fi_file) as f:
                fi_history = json.load(f)

            if len(fi_history) < 2:
                return 1.0

            # Compare most recent to previous
            recent = fi_history[-1]
            previous = fi_history[-2]

            # Calculate correlation of feature rankings
            common_features = set(recent.keys()) & set(previous.keys())
            if len(common_features) < 5:
                return 0.5

            recent_ranks = [recent[f] for f in common_features]
            prev_ranks = [previous[f] for f in common_features]

            correlation = np.corrcoef(recent_ranks, prev_ranks)[0, 1]
            return max(0, correlation)

        except Exception as e:
            logger.error(f"Error checking feature stability: {e}")
            return 1.0

    def _determine_status(
        self,
        accuracy: float | None,
        drift_score: float,
        staleness_days: float,
        predictions_24h: int,
        issues: list[str],
    ) -> ModelStatus:
        """Determine overall model status."""
        if not issues and staleness_days == float("inf"):
            return ModelStatus.OFFLINE

        if staleness_days > self.STALENESS_CRITICAL_DAYS:
            return ModelStatus.RETRAIN_NEEDED

        if accuracy is not None and accuracy < self.ACCURACY_CRITICAL:
            return ModelStatus.RETRAIN_NEEDED

        if drift_score > self.DRIFT_CRITICAL:
            return ModelStatus.DEGRADED

        if (
            (accuracy and accuracy < self.ACCURACY_WARNING) or
            drift_score > self.DRIFT_WARNING or
            staleness_days > self.STALENESS_WARNING_DAYS
        ):
            return ModelStatus.WARNING

        return ModelStatus.HEALTHY

    def log_prediction(
        self,
        model_name: str,
        symbol: str,
        prediction: float,
        confidence: float = 0.5,
        actual: float | None = None,
        features_hash: str = "",
    ) -> None:
        """Log a prediction for tracking."""
        self.predictions_log.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "symbol": symbol,
            "prediction": prediction,
            "confidence": confidence,
            "actual": actual,
            "features_hash": features_hash,
        }

        with open(self.predictions_log, "a") as f:
            f.write(json.dumps(record) + "\n")

    def update_actual(
        self,
        model_name: str,
        symbol: str,
        prediction_time: datetime,
        actual: float,
    ) -> bool:
        """Update a prediction with actual outcome."""
        if not self.predictions_log.exists():
            return False

        # Read all lines, find and update the matching prediction
        lines = []
        updated = False

        with open(self.predictions_log) as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    ts = datetime.fromisoformat(data["timestamp"])

                    # Match by time (within 1 minute), model, and symbol
                    if (
                        data["model_name"] == model_name and
                        data.get("symbol") == symbol and
                        abs((ts - prediction_time).total_seconds()) < 60 and
                        data.get("actual") is None
                    ):
                        data["actual"] = actual
                        updated = True

                    lines.append(json.dumps(data) + "\n")
                except (json.JSONDecodeError, KeyError):
                    lines.append(line)

        if updated:
            with open(self.predictions_log, "w") as f:
                f.writelines(lines)

        return updated

    def save_health_report(self, health: OverallModelHealth) -> Path:
        """Save health report to file."""
        output_dir = self.results_dir / "live"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "model_health.json"

        with open(output_path, "w") as f:
            json.dump(health.to_dict(), f, indent=2)

        return output_path


# Singleton
_monitor: ModelHealthMonitor | None = None


def get_model_health_monitor() -> ModelHealthMonitor:
    """Get the global model health monitor."""
    global _monitor
    if _monitor is None:
        _monitor = ModelHealthMonitor()
    return _monitor


async def check_model_health() -> dict:
    """Quick check of all model health."""
    monitor = get_model_health_monitor()
    health = await monitor.check_all_models()
    return health.to_dict()
