"""ML Signal Generator for Production.

Integrates trained ML models into the signal synthesis pipeline:
- Loads validated models from registry
- Computes features in real-time
- Generates ML-based trading signals
- Combines with statistical signals

This module bridges the ML training pipeline with the trading system.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import numpy as np

from ..ml import (
    ModelServer,
    ModelRegistry,
    PredictionResult,
    TARGETS,
)
from ..ml.training.configs import TargetType
from ..data.feature_engineering import (
    FeatureComputer,
    EnhancedTechnicalFeatures,
    AlternativeDataFeatures,
    LatentKnowledgeFeatures,
)
from ..data.features import FeatureEngine

logger = logging.getLogger(__name__)


@dataclass
class MLSignal:
    """Trading signal from ML model."""
    symbol: str
    timestamp: datetime
    direction: int  # 1 = bullish, -1 = bearish, 0 = neutral
    strength: float  # 0-1 signal strength
    confidence: float  # 0-1 model confidence
    signal_type: str  # BUY, SELL, HOLD
    target: str  # Which target this is for
    model_count: int  # Number of models in ensemble
    reasoning: str
    predictions: dict[str, float] = field(default_factory=dict)
    features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "signal_type": self.signal_type,
            "target": self.target,
            "model_count": self.model_count,
            "reasoning": self.reasoning,
        }


class MLSignalGenerator:
    """
    Generate ML-based trading signals.

    Combines predictions from multiple trained models to generate
    actionable trading signals integrated with the synthesis layer.

    Example:
        ```python
        generator = MLSignalGenerator()

        # Generate signals for watchlist
        signals = await generator.generate_signals(
            symbols=["AAPL", "MSFT", "GOOGL"],
            target="direction_5d",
        )

        for symbol, signal in signals.items():
            print(f"{symbol}: {signal.signal_type} ({signal.confidence:.2f})")
        ```
    """

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        confidence_threshold: float = 0.6,
        min_models: int = 2,
    ):
        """
        Initialize ML signal generator.

        Args:
            models_dir: Directory with trained models
            confidence_threshold: Minimum confidence for signal
            min_models: Minimum models required for ensemble
        """
        self.models_dir = models_dir or Path("~/quant_results/models").expanduser()
        self.confidence_threshold = confidence_threshold
        self.min_models = min_models

        # Initialize components
        self.registry = ModelRegistry(self.models_dir)
        self.model_server = ModelServer(self.registry)

        # Feature computers
        self.feature_engine = FeatureEngine()
        self.feature_computer = FeatureComputer()
        self.enhanced_features = EnhancedTechnicalFeatures()
        self.alt_features = AlternativeDataFeatures()
        self.latent_features = LatentKnowledgeFeatures()

        # Load models on initialization
        self._load_models()

    def _load_models(self) -> None:
        """Load all models from disk."""
        n_loaded = self.registry.load_all_from_disk()
        logger.info(f"Loaded {n_loaded} models from {self.models_dir}")

        # Log available targets
        for target in TARGETS.keys():
            models = self.registry.list_models_for_target(target)
            if models:
                logger.info(f"  {target}: {len(models)} models")

    async def compute_features(
        self,
        symbol: str,
        price_data: pd.DataFrame,
        alt_data: Optional[dict] = None,
    ) -> pd.DataFrame:
        """
        Compute all features for a symbol.

        Args:
            symbol: Symbol to compute features for
            price_data: OHLCV DataFrame
            alt_data: Optional alternative data dict

        Returns:
            DataFrame with all features
        """
        result = pd.DataFrame(index=price_data.index)

        # Basic technical features
        try:
            technical = self.feature_engine.add_all_features(price_data.copy())
            result = pd.concat([result, technical], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute technical features: {e}")

        # Enhanced technical features
        try:
            enhanced = self.enhanced_features.compute_all(price_data)
            result = pd.concat([result, enhanced], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute enhanced features: {e}")

        # Latent knowledge features
        try:
            latent = self.latent_features.compute_all(price_data, symbol=symbol)
            result = pd.concat([result, latent], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute latent features: {e}")

        # Alternative data features (if provided)
        if alt_data:
            try:
                alt = self.alt_features.compute_all(
                    symbol=symbol,
                    **alt_data,
                )
                # Align indices
                alt = alt.reindex(result.index, method='ffill')
                result = pd.concat([result, alt], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute alternative features: {e}")

        # Remove duplicate columns
        result = result.loc[:, ~result.columns.duplicated()]

        # Handle missing values
        result = result.ffill().bfill()

        return result

    async def generate_signal(
        self,
        symbol: str,
        features: pd.DataFrame,
        target: str = "direction_5d",
    ) -> MLSignal:
        """
        Generate ML signal for a single symbol.

        Args:
            symbol: Symbol to generate signal for
            features: Pre-computed features DataFrame
            target: Target to predict

        Returns:
            MLSignal with prediction and confidence
        """
        # Get latest features row
        if len(features) == 0:
            return self._empty_signal(symbol, target, "No features available")

        latest_features = features.iloc[[-1]]  # Keep as DataFrame

        # Get model count
        model_ids = self.registry.list_models_for_target(target, validated_only=True)

        if len(model_ids) < self.min_models:
            return self._empty_signal(
                symbol, target,
                f"Insufficient models ({len(model_ids)} < {self.min_models})"
            )

        try:
            # Get ensemble prediction
            result = await self.model_server.get_ensemble_prediction(
                symbol=symbol,
                features=latest_features,
                target=target,
            )

            # Convert to signal
            return self._prediction_to_signal(result, len(model_ids))

        except Exception as e:
            logger.error(f"Failed to generate signal for {symbol}: {e}")
            return self._empty_signal(symbol, target, str(e))

    async def generate_signals(
        self,
        symbols: list[str],
        price_data_by_symbol: dict[str, pd.DataFrame],
        target: str = "direction_5d",
        alt_data_by_symbol: Optional[dict[str, dict]] = None,
    ) -> dict[str, MLSignal]:
        """
        Generate ML signals for multiple symbols.

        Args:
            symbols: List of symbols
            price_data_by_symbol: Dict of symbol -> OHLCV DataFrame
            target: Target to predict
            alt_data_by_symbol: Optional alternative data by symbol

        Returns:
            Dict of symbol -> MLSignal
        """
        signals = {}

        for symbol in symbols:
            if symbol not in price_data_by_symbol:
                logger.warning(f"No price data for {symbol}")
                signals[symbol] = self._empty_signal(symbol, target, "No price data")
                continue

            # Compute features
            alt_data = alt_data_by_symbol.get(symbol) if alt_data_by_symbol else None
            features = await self.compute_features(
                symbol=symbol,
                price_data=price_data_by_symbol[symbol],
                alt_data=alt_data,
            )

            # Generate signal
            signal = await self.generate_signal(symbol, features, target)
            signals[symbol] = signal

        return signals

    def _prediction_to_signal(
        self,
        result: PredictionResult,
        model_count: int,
    ) -> MLSignal:
        """Convert prediction result to trading signal."""
        # Determine signal type
        if result.confidence < self.confidence_threshold:
            signal_type = "HOLD"
            direction = 0
        elif result.direction > 0:
            signal_type = "BUY" if result.confidence > 0.7 else "WEAK_BUY"
            direction = 1
        else:
            signal_type = "SELL" if result.confidence > 0.7 else "WEAK_SELL"
            direction = -1

        # Calculate strength
        strength = result.confidence * abs(result.prediction - 0.5) * 2

        # Build reasoning
        reasoning = (
            f"Ensemble of {model_count} models predicts "
            f"{'bullish' if direction > 0 else 'bearish' if direction < 0 else 'neutral'} "
            f"with {result.confidence:.1%} confidence"
        )

        return MLSignal(
            symbol=result.symbol,
            timestamp=result.timestamp,
            direction=direction,
            strength=strength,
            confidence=result.confidence,
            signal_type=signal_type,
            target=result.target_name,
            model_count=model_count,
            reasoning=reasoning,
            predictions={"ensemble": result.prediction},
            features=result.feature_values,
        )

    def _empty_signal(
        self,
        symbol: str,
        target: str,
        reason: str,
    ) -> MLSignal:
        """Create empty/neutral signal."""
        return MLSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            direction=0,
            strength=0.0,
            confidence=0.0,
            signal_type="HOLD",
            target=target,
            model_count=0,
            reasoning=reason,
        )

    def get_available_targets(self) -> list[str]:
        """Get list of targets with validated models."""
        targets = []
        for target in TARGETS.keys():
            models = self.registry.list_models_for_target(target, validated_only=True)
            if len(models) >= self.min_models:
                targets.append(target)
        return targets

    def get_model_summary(self) -> dict:
        """Get summary of available models."""
        summary = {
            "total_models": len(self.registry.list_models(validated_only=False)),
            "validated_models": len(self.registry.list_models(validated_only=True)),
            "targets": {},
        }

        for target in TARGETS.keys():
            all_models = self.registry.list_models_for_target(target, validated_only=False)
            validated = self.registry.list_models_for_target(target, validated_only=True)
            summary["targets"][target] = {
                "total": len(all_models),
                "validated": len(validated),
                "ready": len(validated) >= self.min_models,
            }

        return summary


# =============================================================================
# INTEGRATION WITH SIGNAL AGGREGATOR
# =============================================================================


async def add_ml_signals_to_aggregated(
    aggregated_signals: dict,
    ml_generator: MLSignalGenerator,
    price_data_by_symbol: dict[str, pd.DataFrame],
) -> dict:
    """
    Add ML signals to aggregated signal output.

    This function integrates ML predictions with the existing
    signal aggregation framework.

    Args:
        aggregated_signals: Existing aggregated signals dict
        ml_generator: Initialized MLSignalGenerator
        price_data_by_symbol: Price data for each symbol

    Returns:
        Enhanced aggregated signals with ML predictions
    """
    # Get symbols from existing signals
    symbols = list(aggregated_signals.keys())

    # Generate ML signals for each available target
    for target in ml_generator.get_available_targets():
        ml_signals = await ml_generator.generate_signals(
            symbols=symbols,
            price_data_by_symbol=price_data_by_symbol,
            target=target,
        )

        # Add to aggregated signals
        for symbol, ml_signal in ml_signals.items():
            if symbol in aggregated_signals:
                if "ml_signals" not in aggregated_signals[symbol]:
                    aggregated_signals[symbol]["ml_signals"] = {}

                aggregated_signals[symbol]["ml_signals"][target] = {
                    "direction": ml_signal.direction,
                    "strength": ml_signal.strength,
                    "confidence": ml_signal.confidence,
                    "signal_type": ml_signal.signal_type,
                    "model_count": ml_signal.model_count,
                    "reasoning": ml_signal.reasoning,
                }

    return aggregated_signals


def compute_ml_composite_signal(ml_signals: dict[str, dict]) -> dict:
    """
    Compute composite signal from multiple ML targets.

    Args:
        ml_signals: Dict of target -> signal dict

    Returns:
        Composite signal dict
    """
    if not ml_signals:
        return {
            "direction": 0,
            "strength": 0.0,
            "confidence": 0.0,
            "signal_type": "HOLD",
        }

    # Weight by confidence
    total_weight = 0.0
    weighted_direction = 0.0
    weighted_strength = 0.0
    confidences = []

    for target, signal in ml_signals.items():
        weight = signal.get("confidence", 0)
        total_weight += weight
        weighted_direction += signal.get("direction", 0) * weight
        weighted_strength += signal.get("strength", 0) * weight
        confidences.append(weight)

    if total_weight > 0:
        avg_direction = weighted_direction / total_weight
        avg_strength = weighted_strength / total_weight
        avg_confidence = np.mean(confidences)
    else:
        avg_direction = 0
        avg_strength = 0
        avg_confidence = 0

    # Determine composite signal type
    if avg_confidence < 0.5:
        signal_type = "HOLD"
        direction = 0
    elif avg_direction > 0.3:
        signal_type = "BUY" if avg_strength > 0.3 else "WEAK_BUY"
        direction = 1
    elif avg_direction < -0.3:
        signal_type = "SELL" if avg_strength > 0.3 else "WEAK_SELL"
        direction = -1
    else:
        signal_type = "HOLD"
        direction = 0

    return {
        "direction": direction,
        "strength": avg_strength,
        "confidence": avg_confidence,
        "signal_type": signal_type,
        "n_targets": len(ml_signals),
    }
