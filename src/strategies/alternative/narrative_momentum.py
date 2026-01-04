"""
Narrative Momentum Strategy

Generate trading signals from news and text embedding analysis:
- Narrative velocity: rate of change in news topic embedding space
- Sentiment momentum: acceleration in sentiment scores
- Topic concentration: when coverage becomes focused on specific themes
- Narrative divergence: when news narrative deviates from price action

Research shows that:
- Narrative shifts often precede price moves by 1-5 days
- High topic concentration often signals important developments
- Sentiment momentum tends to persist (momentum effect)
- Narrative-price divergence can signal reversals
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

class NarrativeSignal(Enum):
    """Signal types from narrative analysis."""
    STRONG_BULLISH = 2
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1
    STRONG_BEARISH = -2


@dataclass
class NarrativeMomentumSignal:
    """Trading signal from narrative momentum analysis."""
    symbol: str
    signal: NarrativeSignal
    confidence: float  # 0 to 1
    signal_date: datetime
    components: dict = field(default_factory=dict)
    rationale: str = ""
    timeframe_days: int = 5  # Expected signal horizon


@dataclass
class NarrativeFeatures:
    """Features for ML from narrative analysis."""
    symbol: str
    date: datetime

    # Embedding features
    narrative_velocity: float  # Rate of embedding change
    narrative_acceleration: float  # 2nd derivative
    topic_concentration: float  # HHI of topic weights
    narrative_distance: float  # Distance from historical centroid

    # Sentiment features
    sentiment_score: float  # Current sentiment
    sentiment_momentum: float  # Rate of sentiment change
    sentiment_volatility: float  # Variance in sentiment

    # News volume features
    headline_count: int
    volume_spike: float  # vs average
    source_diversity: int

    # Divergence features
    narrative_price_correlation: float  # Correlation with returns
    sentiment_price_gap: float  # Sentiment vs price direction


# =============================================================================
# NARRATIVE MOMENTUM STRATEGY
# =============================================================================

class NarrativeMomentum:
    """
    Generate trading signals from news narrative momentum.

    Usage:
        strategy = NarrativeMomentum()

        # Get signal for single symbol
        signal = await strategy.generate_signal("AAPL")

        # Get features for ML
        features = await strategy.get_narrative_features("AAPL")

        # Screen universe for signals
        signals = await strategy.screen_universe(["AAPL", "MSFT", "GOOGL"])
    """

    # Thresholds for signal generation
    VELOCITY_THRESHOLD = 0.15  # Narrative shift magnitude
    SENTIMENT_THRESHOLD = 0.20  # Sentiment level to trigger
    MOMENTUM_THRESHOLD = 0.10  # Sentiment change rate
    CONCENTRATION_THRESHOLD = 0.4  # Topic concentration

    def __init__(self, lookback_days: int = 14):
        self.lookback_days = lookback_days
        self._embedder = None
        self._news_scraper = None

    @property
    def embedder(self):
        """Lazy load document embedder."""
        if self._embedder is None:
            try:
                from src.data.feature_engineering.text_embeddings import DocumentEmbedder
                self._embedder = DocumentEmbedder()
            except ImportError:
                logger.warning("DocumentEmbedder not available")
                self._embedder = FallbackEmbedder()
        return self._embedder

    @property
    def news_scraper(self):
        """Lazy load news scraper."""
        if self._news_scraper is None:
            try:
                from src.data.sources.web.news_scraper import NewsResearchScraper
                self._news_scraper = NewsResearchScraper()
            except ImportError:
                logger.warning("NewsResearchScraper not available")
                self._news_scraper = FallbackNewsScraper()
        return self._news_scraper

    async def generate_signal(self, symbol: str) -> Optional[NarrativeMomentumSignal]:
        """
        Generate trading signal from narrative momentum.

        Args:
            symbol: Stock symbol

        Returns:
            NarrativeMomentumSignal or None if no signal
        """
        try:
            # Get narrative shift analysis
            shift = self.embedder.track_narrative_shift(
                symbol,
                window_days=self.lookback_days,
            )

            # Get news features
            headlines = await self.news_scraper.fetch_headlines(symbol, max_results=30)
            news_features = self.news_scraper.compute_news_features(headlines)

            # Build signal components
            components = {
                "narrative_velocity": shift.shift_magnitude,
                "topic_concentration": self._calculate_concentration(shift.dominant_topics),
                "sentiment_score": news_features.get("sentiment_score", 0),
                "headline_count": news_features.get("headline_count", 0),
                "positive_ratio": news_features.get("positive_ratio", 0),
                "negative_ratio": news_features.get("negative_ratio", 0),
            }

            # Calculate sentiment momentum (approximate from positive/negative ratio)
            sentiment_momentum = (
                components["positive_ratio"] - components["negative_ratio"]
            )
            components["sentiment_momentum"] = sentiment_momentum

            # Calculate signal
            signal, confidence, rationale = self._calculate_signal(components)

            return NarrativeMomentumSignal(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                signal_date=datetime.now(),
                components=components,
                rationale=rationale,
            )

        except Exception as e:
            logger.error(f"Error generating narrative signal for {symbol}: {e}")
            return None

    def _calculate_concentration(self, topics: list) -> float:
        """Calculate topic concentration (HHI-like)."""
        if not topics:
            return 0.0

        # Simple: inverse of topic count
        # More topics = lower concentration
        return 1.0 / max(len(topics), 1)

    def _calculate_signal(self, components: dict) -> tuple[NarrativeSignal, float, str]:
        """Calculate signal from narrative components."""
        score = 0.0
        reasons = []

        # Narrative velocity contribution
        velocity = components.get("narrative_velocity", 0)
        if velocity > self.VELOCITY_THRESHOLD:
            # Strong narrative shift - need to determine direction
            sentiment = components.get("sentiment_score", 0)
            if sentiment > 0:
                score += 1.5
                reasons.append(f"Positive narrative shift ({velocity:.2f})")
            else:
                score -= 1.5
                reasons.append(f"Negative narrative shift ({velocity:.2f})")

        # Sentiment contribution
        sentiment = components.get("sentiment_score", 0)
        if sentiment > self.SENTIMENT_THRESHOLD:
            score += 1.0
            reasons.append(f"Strong positive sentiment ({sentiment:.2f})")
        elif sentiment < -self.SENTIMENT_THRESHOLD:
            score -= 1.0
            reasons.append(f"Strong negative sentiment ({sentiment:.2f})")

        # Sentiment momentum contribution
        momentum = components.get("sentiment_momentum", 0)
        if momentum > self.MOMENTUM_THRESHOLD:
            score += 0.5
            reasons.append("Positive sentiment momentum")
        elif momentum < -self.MOMENTUM_THRESHOLD:
            score -= 0.5
            reasons.append("Negative sentiment momentum")

        # Topic concentration bonus
        concentration = components.get("topic_concentration", 0)
        if concentration > self.CONCENTRATION_THRESHOLD:
            # High concentration amplifies signal
            score *= 1.2
            reasons.append("High topic concentration (focused narrative)")

        # News volume as confirmation
        headline_count = components.get("headline_count", 0)
        if headline_count >= 10:
            score *= 1.1
            reasons.append(f"High news volume ({headline_count} headlines)")

        # Determine final signal
        if score >= 2.0:
            signal = NarrativeSignal.STRONG_BULLISH
            confidence = min(0.8, 0.5 + abs(score) * 0.08)
        elif score >= 1.0:
            signal = NarrativeSignal.BULLISH
            confidence = min(0.7, 0.4 + abs(score) * 0.08)
        elif score <= -2.0:
            signal = NarrativeSignal.STRONG_BEARISH
            confidence = min(0.8, 0.5 + abs(score) * 0.08)
        elif score <= -1.0:
            signal = NarrativeSignal.BEARISH
            confidence = min(0.7, 0.4 + abs(score) * 0.08)
        else:
            signal = NarrativeSignal.NEUTRAL
            confidence = 0.5

        rationale = "; ".join(reasons) if reasons else "No significant narrative signals"

        return signal, confidence, rationale

    async def get_narrative_features(self, symbol: str) -> Optional[NarrativeFeatures]:
        """
        Extract ML features from narrative analysis.

        Args:
            symbol: Stock symbol

        Returns:
            NarrativeFeatures for ML models
        """
        try:
            # Get narrative shift
            shift = self.embedder.track_narrative_shift(
                symbol,
                window_days=self.lookback_days,
            )

            # Get news
            headlines = await self.news_scraper.fetch_headlines(symbol, max_results=50)
            news_features = self.news_scraper.compute_news_features(headlines)

            # Calculate features
            sentiment_score = news_features.get("sentiment_score", 0)
            positive_ratio = news_features.get("positive_ratio", 0)
            negative_ratio = news_features.get("negative_ratio", 0)

            # Sentiment momentum (simplified)
            sentiment_momentum = positive_ratio - negative_ratio

            # Narrative-price correlation (would need price data)
            # For now, placeholder
            narrative_price_corr = 0.0

            return NarrativeFeatures(
                symbol=symbol,
                date=datetime.now(),
                narrative_velocity=shift.shift_magnitude,
                narrative_acceleration=0.0,  # Would need historical velocity
                topic_concentration=self._calculate_concentration(shift.dominant_topics),
                narrative_distance=shift.shift_magnitude,
                sentiment_score=sentiment_score,
                sentiment_momentum=sentiment_momentum,
                sentiment_volatility=abs(positive_ratio - negative_ratio),
                headline_count=news_features.get("headline_count", 0),
                volume_spike=1.0,  # Would need historical baseline
                source_diversity=news_features.get("source_diversity", 1),
                narrative_price_correlation=narrative_price_corr,
                sentiment_price_gap=0.0,  # Would need price data
            )

        except Exception as e:
            logger.error(f"Error extracting narrative features for {symbol}: {e}")
            return None

    async def screen_universe(
        self,
        symbols: list[str],
        min_confidence: float = 0.6,
    ) -> list[NarrativeMomentumSignal]:
        """
        Screen universe for narrative momentum signals.

        Args:
            symbols: List of symbols to screen
            min_confidence: Minimum confidence for signal

        Returns:
            List of signals meeting threshold
        """
        signals = []

        for symbol in symbols:
            try:
                signal = await self.generate_signal(symbol)

                if signal and signal.confidence >= min_confidence:
                    if signal.signal != NarrativeSignal.NEUTRAL:
                        signals.append(signal)
            except Exception as e:
                logger.debug(f"Error screening {symbol}: {e}")
                continue

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        logger.info(f"Found {len(signals)} narrative signals from {len(symbols)} symbols")
        return signals

    def signals_to_dataframe(self, signals: list[NarrativeMomentumSignal]) -> pd.DataFrame:
        """Convert signals to DataFrame for analysis."""
        data = []
        for s in signals:
            data.append({
                "symbol": s.symbol,
                "signal": s.signal.value,
                "signal_name": s.signal.name,
                "confidence": s.confidence,
                "signal_date": s.signal_date,
                "timeframe_days": s.timeframe_days,
                "rationale": s.rationale,
                **s.components,
            })

        return pd.DataFrame(data)

    async def get_features_dataframe(self, symbols: list[str]) -> pd.DataFrame:
        """Get narrative features for multiple symbols as DataFrame."""
        features = []

        for symbol in symbols:
            try:
                f = await self.get_narrative_features(symbol)
                if f:
                    features.append({
                        "symbol": f.symbol,
                        "date": f.date,
                        "narrative_velocity": f.narrative_velocity,
                        "narrative_acceleration": f.narrative_acceleration,
                        "topic_concentration": f.topic_concentration,
                        "narrative_distance": f.narrative_distance,
                        "sentiment_score": f.sentiment_score,
                        "sentiment_momentum": f.sentiment_momentum,
                        "sentiment_volatility": f.sentiment_volatility,
                        "headline_count": f.headline_count,
                        "volume_spike": f.volume_spike,
                        "source_diversity": f.source_diversity,
                        "narrative_price_correlation": f.narrative_price_correlation,
                        "sentiment_price_gap": f.sentiment_price_gap,
                    })
            except Exception as e:
                logger.debug(f"Error getting features for {symbol}: {e}")
                continue

        return pd.DataFrame(features)


# =============================================================================
# FALLBACK IMPLEMENTATIONS
# =============================================================================

class FallbackEmbedder:
    """Fallback when DocumentEmbedder not available."""

    def track_narrative_shift(self, symbol: str, window_days: int = 14):
        """Return default narrative shift."""
        @dataclass
        class FallbackShift:
            shift_magnitude: float = 0.1
            dominant_topics: list = field(default_factory=lambda: ["general"])

        return FallbackShift()


class FallbackNewsScraper:
    """Fallback when NewsResearchScraper not available."""

    async def fetch_headlines(self, symbol: str, max_results: int = 20):
        """Return empty headlines."""
        return []

    def compute_news_features(self, headlines: list) -> dict:
        """Return default features."""
        return {
            "headline_count": 0,
            "sentiment_score": 0.0,
            "positive_ratio": 0.0,
            "negative_ratio": 0.0,
            "source_diversity": 0,
        }


# =============================================================================
# COMBINED NARRATIVE SIGNAL
# =============================================================================

class NarrativeEnsemble:
    """
    Combine multiple narrative signals for stronger predictions.

    Combines:
    - Narrative momentum
    - SEC filing alpha
    - News sentiment
    """

    def __init__(self):
        self.narrative = NarrativeMomentum()
        self._sec_alpha = None

    @property
    def sec_alpha(self):
        """Lazy load SEC alpha."""
        if self._sec_alpha is None:
            try:
                from src.strategies.alternative.sec_alpha import SECFilingAlpha
                self._sec_alpha = SECFilingAlpha()
            except ImportError:
                self._sec_alpha = None
        return self._sec_alpha

    async def generate_ensemble_signal(
        self,
        symbol: str,
        weights: dict = None,
    ) -> dict:
        """
        Generate combined signal from multiple sources.

        Args:
            symbol: Stock symbol
            weights: Optional weights for each source

        Returns:
            Dict with combined signal info
        """
        weights = weights or {
            "narrative": 0.4,
            "sec": 0.3,
            "sentiment": 0.3,
        }

        results = {}
        total_score = 0.0
        total_weight = 0.0

        # Get narrative signal
        narrative_signal = await self.narrative.generate_signal(symbol)
        if narrative_signal:
            results["narrative"] = {
                "signal": narrative_signal.signal.value,
                "confidence": narrative_signal.confidence,
            }
            total_score += narrative_signal.signal.value * weights["narrative"]
            total_weight += weights["narrative"]

        # Get SEC alpha signal
        if self.sec_alpha:
            try:
                sec_signal = await self.sec_alpha.generate_signal(symbol)
                if sec_signal:
                    results["sec"] = {
                        "signal": sec_signal.signal.value,
                        "confidence": sec_signal.confidence,
                    }
                    total_score += sec_signal.signal.value * weights["sec"]
                    total_weight += weights["sec"]
            except Exception as e:
                logger.debug(f"SEC alpha error for {symbol}: {e}")

        # Calculate ensemble
        if total_weight > 0:
            ensemble_score = total_score / total_weight
            if ensemble_score >= 1.5:
                ensemble_signal = "STRONG_BULLISH"
            elif ensemble_score >= 0.5:
                ensemble_signal = "BULLISH"
            elif ensemble_score <= -1.5:
                ensemble_signal = "STRONG_BEARISH"
            elif ensemble_score <= -0.5:
                ensemble_signal = "BEARISH"
            else:
                ensemble_signal = "NEUTRAL"
        else:
            ensemble_score = 0
            ensemble_signal = "NEUTRAL"

        return {
            "symbol": symbol,
            "ensemble_signal": ensemble_signal,
            "ensemble_score": ensemble_score,
            "components": results,
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_narrative_signal(symbol: str) -> Optional[NarrativeMomentumSignal]:
    """Quick signal generation for single symbol."""
    strategy = NarrativeMomentum()
    return await strategy.generate_signal(symbol)


async def screen_for_narrative_momentum(
    symbols: list[str],
    min_confidence: float = 0.6,
) -> list[NarrativeMomentumSignal]:
    """Quick screening of multiple symbols."""
    strategy = NarrativeMomentum()
    return await strategy.screen_universe(symbols, min_confidence)


async def get_ensemble_signal(symbol: str) -> dict:
    """Get combined narrative ensemble signal."""
    ensemble = NarrativeEnsemble()
    return await ensemble.generate_ensemble_signal(symbol)
