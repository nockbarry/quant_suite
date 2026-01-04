"""
TextSignalGenerator: Generate Trading Signals from Text Features.

Provides various strategies for converting text features into trading signals:
- Sentiment-based signals
- Narrative momentum signals
- Attention-based signals
- Combined multi-factor signals

All signals are designed for text-based alpha with proper temporal alignment.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TextSignal:
    """Trading signal generated from text analysis."""
    symbol: str
    date: date
    direction: int  # 1 = long, -1 = short, 0 = neutral
    strength: float  # Signal strength [0, 1]
    confidence: float  # Model confidence [0, 1]
    strategy: str  # Strategy name
    features_used: dict  # Feature values used


class TextSignalGenerator:
    """
    Generate trading signals from text features.

    Provides multiple signal generation strategies that can be combined
    or used independently. All signals respect point-in-time constraints.

    Example Usage:
        generator = TextSignalGenerator()

        # Generate sentiment momentum signal
        signal = generator.sentiment_momentum_signal(
            features=text_features,
            symbol="AAPL",
            signal_date=date(2026, 1, 3)
        )

        # Combined signal from all strategies
        combined = generator.combined_signal(features, symbol, signal_date)
    """

    # Default thresholds
    DEFAULT_SENTIMENT_THRESHOLD = 0.2
    DEFAULT_MOMENTUM_THRESHOLD = 0.1
    DEFAULT_NOVELTY_THRESHOLD = 0.3

    def __init__(
        self,
        sentiment_threshold: float | None = None,
        momentum_threshold: float | None = None,
        novelty_threshold: float | None = None,
    ):
        """
        Initialize TextSignalGenerator.

        Args:
            sentiment_threshold: Threshold for sentiment signals
            momentum_threshold: Threshold for momentum signals
            novelty_threshold: Threshold for novelty signals
        """
        self.sentiment_threshold = sentiment_threshold or self.DEFAULT_SENTIMENT_THRESHOLD
        self.momentum_threshold = momentum_threshold or self.DEFAULT_MOMENTUM_THRESHOLD
        self.novelty_threshold = novelty_threshold or self.DEFAULT_NOVELTY_THRESHOLD

    def sentiment_mean_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
    ) -> TextSignal:
        """
        Generate signal based on average sentiment.

        Long when sentiment is strongly positive, short when negative.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal

        Returns:
            TextSignal with direction and strength
        """
        sentiment = features.get("text_sentiment_mean", 0.0)

        if np.isnan(sentiment):
            return self._neutral_signal(symbol, signal_date, "sentiment_mean", features)

        # Determine direction
        if sentiment > self.sentiment_threshold:
            direction = 1
        elif sentiment < -self.sentiment_threshold:
            direction = -1
        else:
            direction = 0

        # Strength is absolute sentiment value normalized
        strength = min(abs(sentiment), 1.0)

        # Confidence based on data quality
        confidence = 1.0 if not np.isnan(sentiment) else 0.0

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=confidence,
            strategy="sentiment_mean",
            features_used={"text_sentiment_mean": sentiment},
        )

    def sentiment_momentum_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
    ) -> TextSignal:
        """
        Generate signal based on sentiment momentum.

        Long when sentiment is improving, short when deteriorating.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal

        Returns:
            TextSignal with direction and strength
        """
        momentum = features.get("text_sentiment_momentum", 0.0)

        if np.isnan(momentum):
            return self._neutral_signal(symbol, signal_date, "sentiment_momentum", features)

        # Direction based on momentum sign
        if momentum > self.momentum_threshold:
            direction = 1
        elif momentum < -self.momentum_threshold:
            direction = -1
        else:
            direction = 0

        # Strength normalized to [0, 1]
        strength = min(abs(momentum) / 0.5, 1.0)  # Normalize assuming max momentum ~0.5

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=0.8 if not np.isnan(momentum) else 0.0,
            strategy="sentiment_momentum",
            features_used={"text_sentiment_momentum": momentum},
        )

    def narrative_shift_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
    ) -> TextSignal:
        """
        Generate signal based on narrative shift.

        Large narrative shifts can indicate new information.
        Combined with sentiment to determine direction.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal

        Returns:
            TextSignal with direction and strength
        """
        narrative_shift = features.get("text_narrative_shift", 0.0)
        sentiment = features.get("text_sentiment_mean", 0.0)

        if np.isnan(narrative_shift):
            return self._neutral_signal(symbol, signal_date, "narrative_shift", features)

        # Significant narrative shift indicates potential opportunity
        if narrative_shift < self.novelty_threshold:
            # No significant shift
            return self._neutral_signal(symbol, signal_date, "narrative_shift", features)

        # Direction from sentiment (if available)
        if not np.isnan(sentiment):
            direction = 1 if sentiment > 0 else -1 if sentiment < 0 else 0
        else:
            direction = 0

        # Strength from shift magnitude
        strength = min(narrative_shift, 1.0)

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=0.6,  # Lower confidence due to interpretation
            strategy="narrative_shift",
            features_used={
                "text_narrative_shift": narrative_shift,
                "text_sentiment_mean": sentiment,
            },
        )

    def attention_velocity_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
    ) -> TextSignal:
        """
        Generate signal based on mention velocity.

        Unusual increases in coverage can precede price moves.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal

        Returns:
            TextSignal with direction and strength
        """
        velocity = features.get("text_mention_velocity", 0.0)
        sentiment = features.get("text_sentiment_mean", 0.0)

        if np.isnan(velocity):
            return self._neutral_signal(symbol, signal_date, "attention_velocity", features)

        # High velocity = increased attention
        velocity_threshold = 0.5  # log(1.65) - about 65% increase

        if abs(velocity) < velocity_threshold:
            return self._neutral_signal(symbol, signal_date, "attention_velocity", features)

        # Direction from sentiment if attention is high
        if not np.isnan(sentiment):
            direction = 1 if sentiment > 0 else -1 if sentiment < 0 else 1 if velocity > 0 else -1
        else:
            # Default: increased attention often precedes positive moves
            direction = 1 if velocity > 0 else -1

        strength = min(abs(velocity), 1.0)

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=0.5,  # Attention signals are noisy
            strategy="attention_velocity",
            features_used={
                "text_mention_velocity": velocity,
                "text_sentiment_mean": sentiment,
            },
        )

    def contrarian_sentiment_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
    ) -> TextSignal:
        """
        Generate contrarian signal based on extreme sentiment.

        When sentiment is extremely positive/negative, bet on reversal.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal

        Returns:
            TextSignal with direction and strength
        """
        sentiment = features.get("text_sentiment_mean", 0.0)
        volatility = features.get("text_sentiment_volatility", 0.0)

        if np.isnan(sentiment):
            return self._neutral_signal(symbol, signal_date, "contrarian_sentiment", features)

        # Only trigger on extreme sentiment
        extreme_threshold = 0.6

        if abs(sentiment) < extreme_threshold:
            return self._neutral_signal(symbol, signal_date, "contrarian_sentiment", features)

        # Contrarian: opposite direction of extreme sentiment
        direction = -1 if sentiment > 0 else 1

        # Strength based on how extreme
        strength = min((abs(sentiment) - extreme_threshold) / 0.4, 1.0)

        # Higher confidence if sentiment volatility is low (stable extreme)
        confidence = 0.7 if (not np.isnan(volatility) and volatility < 0.3) else 0.4

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=confidence,
            strategy="contrarian_sentiment",
            features_used={
                "text_sentiment_mean": sentiment,
                "text_sentiment_volatility": volatility,
            },
        )

    def combined_signal(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
        strategies: list[str] | None = None,
        weights: dict[str, float] | None = None,
    ) -> TextSignal:
        """
        Generate combined signal from multiple strategies.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal
            strategies: List of strategies to combine (default: all)
            weights: Optional strategy weights (default: equal)

        Returns:
            Combined TextSignal
        """
        # Available strategies
        strategy_map = {
            "sentiment_mean": self.sentiment_mean_signal,
            "sentiment_momentum": self.sentiment_momentum_signal,
            "narrative_shift": self.narrative_shift_signal,
            "attention_velocity": self.attention_velocity_signal,
            "contrarian_sentiment": self.contrarian_sentiment_signal,
        }

        # Default to all strategies except contrarian (conflicting)
        if strategies is None:
            strategies = ["sentiment_mean", "sentiment_momentum", "narrative_shift", "attention_velocity"]

        # Default equal weights
        if weights is None:
            weights = {s: 1.0 / len(strategies) for s in strategies}

        # Generate signals from each strategy
        signals = []
        for strategy_name in strategies:
            if strategy_name not in strategy_map:
                continue

            signal_fn = strategy_map[strategy_name]
            signal = signal_fn(features, symbol, signal_date)
            signals.append((signal, weights.get(strategy_name, 0.0)))

        if not signals:
            return self._neutral_signal(symbol, signal_date, "combined", features)

        # Combine signals
        total_weight = sum(w for _, w in signals)
        if total_weight == 0:
            return self._neutral_signal(symbol, signal_date, "combined", features)

        # Weighted average of direction * strength
        combined_score = sum(
            s.direction * s.strength * s.confidence * w
            for s, w in signals
        ) / total_weight

        # Direction from combined score
        if combined_score > 0.1:
            direction = 1
        elif combined_score < -0.1:
            direction = -1
        else:
            direction = 0

        # Strength and confidence
        strength = min(abs(combined_score), 1.0)
        confidence = np.mean([s.confidence for s, _ in signals])

        # Collect features used
        features_used = {}
        for s, _ in signals:
            features_used.update(s.features_used)

        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=direction,
            strength=strength,
            confidence=confidence,
            strategy="combined",
            features_used=features_used,
        )

    def get_signal_as_float(
        self,
        features: dict[str, float],
        symbol: str,
        signal_date: date,
        strategy: str = "combined",
    ) -> float:
        """
        Get signal as single float value for backtesting.

        Args:
            features: Dictionary of computed text features
            symbol: Stock symbol
            signal_date: Date for signal
            strategy: Strategy to use

        Returns:
            Signal value in [-1, 1]
        """
        strategy_map = {
            "sentiment_mean": self.sentiment_mean_signal,
            "sentiment_momentum": self.sentiment_momentum_signal,
            "narrative_shift": self.narrative_shift_signal,
            "attention_velocity": self.attention_velocity_signal,
            "contrarian_sentiment": self.contrarian_sentiment_signal,
            "combined": self.combined_signal,
        }

        signal_fn = strategy_map.get(strategy)
        if signal_fn is None:
            return 0.0

        signal = signal_fn(features, symbol, signal_date)
        return signal.direction * signal.strength * signal.confidence

    def _neutral_signal(
        self,
        symbol: str,
        signal_date: date,
        strategy: str,
        features: dict[str, float],
    ) -> TextSignal:
        """Create a neutral (no trade) signal."""
        return TextSignal(
            symbol=symbol,
            date=signal_date,
            direction=0,
            strength=0.0,
            confidence=0.0,
            strategy=strategy,
            features_used=features,
        )

    def create_signal_generator_fn(
        self,
        strategy: str = "combined",
    ) -> Callable[[dict[str, float], str, date], float]:
        """
        Create a signal generator function for use with TextBacktester.

        Args:
            strategy: Strategy to use

        Returns:
            Function(features, symbol, date) -> signal
        """
        def signal_fn(features: dict[str, float], symbol: str, signal_date: date) -> float:
            return self.get_signal_as_float(features, symbol, signal_date, strategy)

        return signal_fn

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TextSignalGenerator(sentiment_thresh={self.sentiment_threshold}, "
            f"momentum_thresh={self.momentum_threshold})"
        )
