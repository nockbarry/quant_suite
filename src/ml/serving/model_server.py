"""Model Server for Production Predictions.

Manages trained models and provides prediction interface:
- Model registry for validated models
- Feature preparation
- Ensemble predictions
- Confidence scoring
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd

from ..training.pipeline import TrainedModel
from ..training.configs import TargetType

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Result from model prediction."""
    symbol: str
    timestamp: datetime
    prediction: float
    confidence: float
    direction: int  # 1 = bullish, -1 = bearish, 0 = neutral
    model_id: str
    target_name: str
    feature_values: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "prediction": self.prediction,
            "confidence": self.confidence,
            "direction": self.direction,
            "model_id": self.model_id,
            "target_name": self.target_name,
        }


class ModelRegistry:
    """
    Registry of validated models.

    Manages model storage, loading, and metadata.
    Only models that pass MCPT validation are registered.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or Path("~/quant_results/models").expanduser()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, TrainedModel] = {}
        self._metadata: dict[str, dict] = {}

    def register(
        self,
        model: TrainedModel,
        metrics: Optional[dict] = None,
    ) -> str:
        """
        Register a validated model.

        Args:
            model: Trained model to register
            metrics: Optional additional metrics

        Returns:
            Model ID
        """
        if not model.mcpt_result or not model.mcpt_result.is_significant:
            logger.warning(
                f"Model {model.model_id} is not statistically significant. "
                "Registering anyway but marked as unvalidated."
            )

        self._models[model.model_id] = model
        self._metadata[model.model_id] = {
            "registered_at": datetime.now().isoformat(),
            "target": model.target_config.name,
            "model_type": model.config.model_type.value,
            "mcpt_p_value": model.mcpt_result.p_value if model.mcpt_result else None,
            "is_validated": model.mcpt_result.is_significant if model.mcpt_result else False,
            "metrics": metrics or model.metrics,
        }

        # Save to disk
        model.save(self.models_dir)

        logger.info(f"Registered model: {model.model_id}")
        return model.model_id

    def load(self, model_id: str) -> TrainedModel:
        """Load a model by ID."""
        if model_id in self._models:
            return self._models[model_id]

        # Try loading from disk
        model_path = self.models_dir / f"{model_id}.joblib"
        if model_path.exists():
            model = TrainedModel.load(model_path)
            self._models[model_id] = model
            return model

        raise ValueError(f"Model not found: {model_id}")

    def list_models(self, validated_only: bool = True) -> list[str]:
        """List all registered models."""
        if validated_only:
            return [
                mid for mid, meta in self._metadata.items()
                if meta.get("is_validated", False)
            ]
        return list(self._metadata.keys())

    def list_models_for_target(
        self,
        target: str,
        validated_only: bool = True,
    ) -> list[str]:
        """List models for a specific target."""
        return [
            mid for mid, meta in self._metadata.items()
            if meta.get("target") == target
            and (not validated_only or meta.get("is_validated", False))
        ]

    def get_metadata(self, model_id: str) -> dict:
        """Get metadata for a model."""
        return self._metadata.get(model_id, {})

    def load_all_from_disk(self) -> int:
        """Load all models from disk."""
        count = 0
        for model_path in self.models_dir.glob("*.joblib"):
            try:
                model = TrainedModel.load(model_path)
                self._models[model.model_id] = model
                self._metadata[model.model_id] = {
                    "loaded_from_disk": True,
                    "target": model.target_config.name,
                    "model_type": model.config.model_type.value,
                    "is_validated": model.mcpt_result.is_significant if model.mcpt_result else False,
                }
                count += 1
            except Exception as e:
                logger.warning(f"Failed to load {model_path}: {e}")
        logger.info(f"Loaded {count} models from disk")
        return count


class ModelServer:
    """
    Model server for production predictions.

    Provides a unified interface for getting predictions from
    trained models, with support for:
    - Single model predictions
    - Ensemble predictions
    - Confidence-weighted signals
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
    ):
        self.registry = registry or ModelRegistry()

    async def get_prediction(
        self,
        symbol: str,
        features: pd.DataFrame,
        model_id: str,
    ) -> PredictionResult:
        """
        Get prediction from a specific model.

        Args:
            symbol: Symbol to predict
            features: Features DataFrame (single row)
            model_id: Model ID to use

        Returns:
            PredictionResult
        """
        model = self.registry.load(model_id)

        # Get prediction
        if model.target_config.target_type == TargetType.CLASSIFICATION:
            proba = model.predict_proba(features)
            if proba.ndim > 1:
                prediction = proba[0, 1]  # Probability of positive class
            else:
                prediction = proba[0]
            confidence = abs(prediction - 0.5) * 2  # Scale to 0-1
            direction = 1 if prediction > 0.5 else -1
        else:
            prediction = model.predict(features)[0]
            # Use prediction magnitude for confidence
            confidence = min(1.0, abs(prediction) / 0.05)  # Normalize by 5%
            direction = 1 if prediction > 0 else -1

        # Get key feature values
        feature_values = {}
        for col in model.feature_columns[:10]:  # Top 10 features
            if col in features.columns:
                feature_values[col] = float(features[col].iloc[0])

        return PredictionResult(
            symbol=symbol,
            timestamp=datetime.now(),
            prediction=float(prediction),
            confidence=float(confidence),
            direction=int(direction),
            model_id=model_id,
            target_name=model.target_config.name,
            feature_values=feature_values,
        )

    async def get_ensemble_prediction(
        self,
        symbol: str,
        features: pd.DataFrame,
        target: str,
        weighting: str = "equal",  # equal, confidence, performance
    ) -> PredictionResult:
        """
        Get ensemble prediction from all models for a target.

        Args:
            symbol: Symbol to predict
            features: Features DataFrame
            target: Target name (e.g., "direction_5d")
            weighting: How to weight model predictions

        Returns:
            Ensemble PredictionResult
        """
        model_ids = self.registry.list_models_for_target(target)

        if not model_ids:
            raise ValueError(f"No validated models for target: {target}")

        predictions = []
        confidences = []

        for model_id in model_ids:
            try:
                result = await self.get_prediction(symbol, features, model_id)
                predictions.append(result.prediction)
                confidences.append(result.confidence)
            except Exception as e:
                logger.warning(f"Failed prediction from {model_id}: {e}")

        if not predictions:
            raise ValueError("All models failed")

        # Ensemble
        if weighting == "confidence":
            weights = np.array(confidences)
            weights = weights / weights.sum()
            ensemble_pred = np.average(predictions, weights=weights)
        else:  # equal
            ensemble_pred = np.mean(predictions)

        ensemble_conf = np.mean(confidences)

        return PredictionResult(
            symbol=symbol,
            timestamp=datetime.now(),
            prediction=float(ensemble_pred),
            confidence=float(ensemble_conf),
            direction=1 if ensemble_pred > 0.5 else -1,
            model_id=f"ensemble_{len(model_ids)}_models",
            target_name=target,
            metadata={
                "n_models": len(model_ids),
                "model_ids": model_ids,
            },
        )

    async def get_all_predictions(
        self,
        symbols: list[str],
        features_by_symbol: dict[str, pd.DataFrame],
        target: str,
    ) -> dict[str, PredictionResult]:
        """
        Get predictions for multiple symbols.

        Args:
            symbols: List of symbols
            features_by_symbol: Dict mapping symbol to features DataFrame
            target: Target name

        Returns:
            Dict mapping symbol to PredictionResult
        """
        results = {}

        for symbol in symbols:
            if symbol not in features_by_symbol:
                logger.warning(f"No features for {symbol}")
                continue

            try:
                result = await self.get_ensemble_prediction(
                    symbol=symbol,
                    features=features_by_symbol[symbol],
                    target=target,
                )
                results[symbol] = result
            except Exception as e:
                logger.warning(f"Failed prediction for {symbol}: {e}")

        return results

    def get_signal_from_prediction(
        self,
        result: PredictionResult,
        threshold: float = 0.6,
    ) -> dict:
        """
        Convert prediction to trading signal.

        Args:
            result: Prediction result
            threshold: Confidence threshold for signal

        Returns:
            Signal dict with direction and strength
        """
        if result.confidence < threshold:
            return {
                "direction": 0,
                "strength": 0.0,
                "signal": "HOLD",
                "reason": f"Confidence {result.confidence:.2f} below threshold {threshold}",
            }

        strength = result.confidence * abs(result.prediction - 0.5) * 2

        if result.direction > 0:
            signal = "BUY" if strength > 0.3 else "WEAK_BUY"
        else:
            signal = "SELL" if strength > 0.3 else "WEAK_SELL"

        return {
            "direction": result.direction,
            "strength": strength,
            "signal": signal,
            "reason": f"Model {result.model_id}: {result.prediction:.3f} ({result.confidence:.2f} conf)",
        }
