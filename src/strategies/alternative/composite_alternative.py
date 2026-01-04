"""
Composite Alternative Strategy

Combines multiple alternative data signals into a unified trading signal:
- SEC Filing Alpha: Sentiment and risk factor analysis from filings
- Narrative Momentum: News embedding drift and sentiment acceleration
- Sentiment Signals: FinBERT and lexicon-based sentiment
- Correlation/Dispersion: Market regime and correlation breakdown signals

The composite uses adaptive weighting based on:
- Recent signal performance
- Market regime
- Confidence levels
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

class CompositeSignal(Enum):
    """Combined signal strength."""
    STRONG_BULLISH = 2
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1
    STRONG_BEARISH = -2


@dataclass
class SignalComponent:
    """Individual signal component."""
    name: str
    value: float  # -2 to 2
    confidence: float  # 0 to 1
    weight: float  # 0 to 1
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class CompositeAlternativeSignal:
    """Combined alternative data signal."""
    symbol: str
    signal: CompositeSignal
    confidence: float
    signal_date: datetime
    components: list[SignalComponent] = field(default_factory=list)
    weighted_score: float = 0.0
    rationale: str = ""
    regime: str = "normal"  # Market regime context


@dataclass
class CompositeFeatures:
    """Features for ML from composite analysis."""
    symbol: str
    date: datetime

    # SEC Filing features
    filing_sentiment: float
    filing_risk_change: float

    # Narrative features
    narrative_velocity: float
    sentiment_momentum: float

    # News features
    news_sentiment: float
    headline_count: int

    # Technical context
    price_momentum: float
    volatility: float
    volume_ratio: float

    # Composite scores
    bullish_component_count: int
    bearish_component_count: int
    signal_agreement: float  # How aligned are signals


# =============================================================================
# COMPOSITE ALTERNATIVE STRATEGY
# =============================================================================

class CompositeAlternative:
    """
    Combine multiple alternative data signals.

    Usage:
        strategy = CompositeAlternative()

        # Get combined signal
        signal = await strategy.generate_signal("AAPL")

        # Get with custom weights
        signal = await strategy.generate_signal("AAPL", weights={
            "sec_alpha": 0.3,
            "narrative": 0.3,
            "sentiment": 0.2,
            "news": 0.2,
        })

        # Screen universe
        signals = await strategy.screen_universe(["AAPL", "MSFT", "GOOGL"])
    """

    DEFAULT_WEIGHTS = {
        "sec_alpha": 0.25,
        "narrative": 0.25,
        "sentiment": 0.25,
        "news": 0.25,
    }

    def __init__(self, weights: dict = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._components_cache = {}
        self._sec_alpha = None
        self._narrative = None
        self._news_scraper = None

    @property
    def sec_alpha(self):
        """Lazy load SEC alpha strategy."""
        if self._sec_alpha is None:
            try:
                from src.strategies.alternative.sec_alpha import SECFilingAlpha
                self._sec_alpha = SECFilingAlpha()
            except ImportError:
                logger.warning("SECFilingAlpha not available")
        return self._sec_alpha

    @property
    def narrative(self):
        """Lazy load narrative momentum strategy."""
        if self._narrative is None:
            try:
                from src.strategies.alternative.narrative_momentum import NarrativeMomentum
                self._narrative = NarrativeMomentum()
            except ImportError:
                logger.warning("NarrativeMomentum not available")
        return self._narrative

    @property
    def news_scraper(self):
        """Lazy load news scraper."""
        if self._news_scraper is None:
            try:
                from src.data.sources.web.news_scraper import NewsResearchScraper
                self._news_scraper = NewsResearchScraper()
            except ImportError:
                logger.warning("NewsResearchScraper not available")
        return self._news_scraper

    async def generate_signal(
        self,
        symbol: str,
        weights: dict = None,
    ) -> Optional[CompositeAlternativeSignal]:
        """
        Generate combined alternative signal.

        Args:
            symbol: Stock symbol
            weights: Optional custom weights for components

        Returns:
            CompositeAlternativeSignal or None
        """
        weights = weights or self.weights
        components = []

        # Get SEC Filing Alpha signal
        sec_component = await self._get_sec_component(symbol)
        if sec_component:
            sec_component.weight = weights.get("sec_alpha", 0.25)
            components.append(sec_component)

        # Get Narrative Momentum signal
        narrative_component = await self._get_narrative_component(symbol)
        if narrative_component:
            narrative_component.weight = weights.get("narrative", 0.25)
            components.append(narrative_component)

        # Get news sentiment
        news_component = await self._get_news_component(symbol)
        if news_component:
            news_component.weight = weights.get("news", 0.25)
            components.append(news_component)

        # Get technical sentiment context
        technical_component = await self._get_technical_component(symbol)
        if technical_component:
            technical_component.weight = weights.get("sentiment", 0.25)
            components.append(technical_component)

        if not components:
            logger.warning(f"No components available for {symbol}")
            return None

        # Calculate weighted score
        total_weight = sum(c.weight for c in components)
        if total_weight == 0:
            return None

        weighted_score = sum(
            c.value * c.confidence * c.weight
            for c in components
        ) / total_weight

        # Determine signal
        signal, confidence = self._score_to_signal(weighted_score, components)

        # Build rationale
        rationale_parts = []
        for c in sorted(components, key=lambda x: abs(x.value), reverse=True):
            direction = "bullish" if c.value > 0 else "bearish" if c.value < 0 else "neutral"
            rationale_parts.append(f"{c.name}: {direction} ({c.confidence:.0%})")

        return CompositeAlternativeSignal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            signal_date=datetime.now(),
            components=components,
            weighted_score=weighted_score,
            rationale="; ".join(rationale_parts),
        )

    async def _get_sec_component(self, symbol: str) -> Optional[SignalComponent]:
        """Get SEC filing alpha component."""
        if not self.sec_alpha:
            return None

        try:
            signal = await self.sec_alpha.generate_signal(symbol)
            if signal:
                return SignalComponent(
                    name="sec_alpha",
                    value=signal.signal.value,
                    confidence=signal.confidence,
                    weight=0.0,
                    metadata=signal.components,
                )
        except Exception as e:
            logger.debug(f"SEC alpha error for {symbol}: {e}")

        return None

    async def _get_narrative_component(self, symbol: str) -> Optional[SignalComponent]:
        """Get narrative momentum component."""
        if not self.narrative:
            return None

        try:
            signal = await self.narrative.generate_signal(symbol)
            if signal:
                return SignalComponent(
                    name="narrative",
                    value=signal.signal.value,
                    confidence=signal.confidence,
                    weight=0.0,
                    metadata=signal.components,
                )
        except Exception as e:
            logger.debug(f"Narrative error for {symbol}: {e}")

        return None

    async def _get_news_component(self, symbol: str) -> Optional[SignalComponent]:
        """Get news sentiment component."""
        if not self.news_scraper:
            return None

        try:
            headlines = await self.news_scraper.fetch_headlines(symbol, max_results=20)
            features = self.news_scraper.compute_news_features(headlines)

            sentiment = features.get("sentiment_score", 0)
            headline_count = features.get("headline_count", 0)

            # Convert sentiment to signal value
            if sentiment > 0.3:
                value = 2.0
            elif sentiment > 0.1:
                value = 1.0
            elif sentiment < -0.3:
                value = -2.0
            elif sentiment < -0.1:
                value = -1.0
            else:
                value = 0.0

            # Confidence based on volume
            confidence = min(0.8, 0.3 + headline_count * 0.03)

            return SignalComponent(
                name="news",
                value=value,
                confidence=confidence,
                weight=0.0,
                metadata=features,
            )
        except Exception as e:
            logger.debug(f"News error for {symbol}: {e}")

        return None

    async def _get_technical_component(self, symbol: str) -> Optional[SignalComponent]:
        """Get technical/momentum context."""
        try:
            import yfinance as yf

            df = yf.download(symbol, period="30d", progress=False)
            if df.empty:
                return None

            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            # Calculate momentum
            returns = df["close"].pct_change()
            momentum_5d = returns.tail(5).sum()
            momentum_20d = returns.tail(20).sum()

            # RSI
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Generate signal based on technicals
            if momentum_20d > 0.05 and current_rsi < 70:
                value = 1.0
            elif momentum_20d < -0.05 and current_rsi > 30:
                value = -1.0
            else:
                value = 0.0

            # RSI extreme amplifies
            if current_rsi < 30:
                value = max(value, 1.0)  # Oversold = bullish
            elif current_rsi > 70:
                value = min(value, -1.0)  # Overbought = bearish

            confidence = 0.5 + abs(momentum_20d) * 2  # Higher momentum = higher confidence
            confidence = min(0.7, confidence)

            return SignalComponent(
                name="technical",
                value=value,
                confidence=confidence,
                weight=0.0,
                metadata={
                    "momentum_5d": momentum_5d,
                    "momentum_20d": momentum_20d,
                    "rsi": current_rsi,
                },
            )
        except Exception as e:
            logger.debug(f"Technical error for {symbol}: {e}")

        return None

    def _score_to_signal(
        self,
        score: float,
        components: list[SignalComponent],
    ) -> tuple[CompositeSignal, float]:
        """Convert weighted score to signal."""
        # Agreement factor: boost confidence if signals align
        values = [c.value for c in components]
        if all(v > 0 for v in values) or all(v < 0 for v in values):
            agreement_boost = 0.1
        elif all(v >= 0 for v in values) or all(v <= 0 for v in values):
            agreement_boost = 0.05
        else:
            agreement_boost = 0.0

        # Base confidence from average component confidence
        avg_confidence = np.mean([c.confidence for c in components])
        confidence = min(0.85, avg_confidence + agreement_boost)

        if score >= 1.5:
            return CompositeSignal.STRONG_BULLISH, confidence
        elif score >= 0.5:
            return CompositeSignal.BULLISH, confidence * 0.9
        elif score <= -1.5:
            return CompositeSignal.STRONG_BEARISH, confidence
        elif score <= -0.5:
            return CompositeSignal.BEARISH, confidence * 0.9
        else:
            return CompositeSignal.NEUTRAL, 0.5

    async def screen_universe(
        self,
        symbols: list[str],
        min_confidence: float = 0.6,
        weights: dict = None,
    ) -> list[CompositeAlternativeSignal]:
        """
        Screen universe for composite signals.

        Args:
            symbols: List of symbols to screen
            min_confidence: Minimum confidence for signal
            weights: Optional custom weights

        Returns:
            List of signals meeting threshold
        """
        signals = []

        for symbol in symbols:
            try:
                signal = await self.generate_signal(symbol, weights)

                if signal and signal.confidence >= min_confidence:
                    if signal.signal != CompositeSignal.NEUTRAL:
                        signals.append(signal)
            except Exception as e:
                logger.debug(f"Error screening {symbol}: {e}")
                continue

        # Sort by absolute weighted score (strongest signals first)
        signals.sort(key=lambda s: abs(s.weighted_score), reverse=True)

        logger.info(f"Found {len(signals)} composite signals from {len(symbols)} symbols")
        return signals

    async def get_features(self, symbol: str) -> Optional[CompositeFeatures]:
        """Extract ML features from composite analysis."""
        try:
            # Get component signals
            sec_comp = await self._get_sec_component(symbol)
            narrative_comp = await self._get_narrative_component(symbol)
            news_comp = await self._get_news_component(symbol)
            technical_comp = await self._get_technical_component(symbol)

            components = [c for c in [sec_comp, narrative_comp, news_comp, technical_comp] if c]

            if not components:
                return None

            # Extract values
            filing_sentiment = sec_comp.metadata.get("overall_sentiment", 0) if sec_comp else 0
            filing_risk = sec_comp.metadata.get("sentiment_change", 0) if sec_comp else 0
            narrative_velocity = narrative_comp.metadata.get("narrative_velocity", 0) if narrative_comp else 0
            sentiment_momentum = narrative_comp.metadata.get("sentiment_momentum", 0) if narrative_comp else 0
            news_sentiment = news_comp.metadata.get("sentiment_score", 0) if news_comp else 0
            headline_count = news_comp.metadata.get("headline_count", 0) if news_comp else 0
            price_momentum = technical_comp.metadata.get("momentum_20d", 0) if technical_comp else 0
            rsi = technical_comp.metadata.get("rsi", 50) if technical_comp else 50

            # Calculate agreement metrics
            values = [c.value for c in components]
            bullish_count = sum(1 for v in values if v > 0)
            bearish_count = sum(1 for v in values if v < 0)

            # Signal agreement: std dev of values (lower = more agreement)
            if len(values) > 1:
                signal_agreement = 1.0 - min(1.0, np.std(values) / 2)
            else:
                signal_agreement = 1.0

            return CompositeFeatures(
                symbol=symbol,
                date=datetime.now(),
                filing_sentiment=filing_sentiment,
                filing_risk_change=filing_risk,
                narrative_velocity=narrative_velocity,
                sentiment_momentum=sentiment_momentum,
                news_sentiment=news_sentiment,
                headline_count=headline_count,
                price_momentum=price_momentum,
                volatility=abs(rsi - 50) / 50,  # Simplified
                volume_ratio=1.0,  # Would need baseline
                bullish_component_count=bullish_count,
                bearish_component_count=bearish_count,
                signal_agreement=signal_agreement,
            )

        except Exception as e:
            logger.error(f"Error extracting features for {symbol}: {e}")
            return None

    def signals_to_dataframe(self, signals: list[CompositeAlternativeSignal]) -> pd.DataFrame:
        """Convert signals to DataFrame."""
        data = []
        for s in signals:
            row = {
                "symbol": s.symbol,
                "signal": s.signal.value,
                "signal_name": s.signal.name,
                "confidence": s.confidence,
                "weighted_score": s.weighted_score,
                "signal_date": s.signal_date,
                "rationale": s.rationale,
                "component_count": len(s.components),
            }

            # Add component details
            for c in s.components:
                row[f"{c.name}_value"] = c.value
                row[f"{c.name}_confidence"] = c.confidence

            data.append(row)

        return pd.DataFrame(data)

    async def get_features_dataframe(self, symbols: list[str]) -> pd.DataFrame:
        """Get features for multiple symbols."""
        features = []

        for symbol in symbols:
            try:
                f = await self.get_features(symbol)
                if f:
                    features.append({
                        "symbol": f.symbol,
                        "date": f.date,
                        "filing_sentiment": f.filing_sentiment,
                        "filing_risk_change": f.filing_risk_change,
                        "narrative_velocity": f.narrative_velocity,
                        "sentiment_momentum": f.sentiment_momentum,
                        "news_sentiment": f.news_sentiment,
                        "headline_count": f.headline_count,
                        "price_momentum": f.price_momentum,
                        "volatility": f.volatility,
                        "volume_ratio": f.volume_ratio,
                        "bullish_count": f.bullish_component_count,
                        "bearish_count": f.bearish_component_count,
                        "signal_agreement": f.signal_agreement,
                    })
            except Exception as e:
                logger.debug(f"Error getting features for {symbol}: {e}")
                continue

        return pd.DataFrame(features)


# =============================================================================
# ADAPTIVE WEIGHTING
# =============================================================================

class AdaptiveComposite(CompositeAlternative):
    """
    Composite strategy with adaptive weight learning.

    Adjusts component weights based on recent performance.
    """

    def __init__(self):
        super().__init__()
        self.performance_history = []

    def update_weights_from_performance(
        self,
        results: pd.DataFrame,
        decay_factor: float = 0.9,
    ) -> dict:
        """
        Update weights based on component performance.

        Args:
            results: DataFrame with 'component', 'predicted_return', 'actual_return'
            decay_factor: Weight for recent vs historical performance

        Returns:
            Updated weights
        """
        if results.empty:
            return self.weights

        # Calculate accuracy for each component
        component_scores = {}

        for component in results["component"].unique():
            comp_results = results[results["component"] == component]

            # Accuracy: how often prediction direction matched actual
            correct = (
                (comp_results["predicted_return"] > 0) ==
                (comp_results["actual_return"] > 0)
            ).mean()

            # Magnitude: how much return captured
            magnitude = comp_results["actual_return"].abs().mean()

            component_scores[component] = correct * (1 + magnitude)

        # Normalize to weights
        total = sum(component_scores.values())
        if total > 0:
            new_weights = {
                k: v / total
                for k, v in component_scores.items()
            }

            # Blend with current weights
            for k in self.weights:
                if k in new_weights:
                    self.weights[k] = (
                        decay_factor * self.weights[k] +
                        (1 - decay_factor) * new_weights[k]
                    )

        return self.weights


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_composite_signal(symbol: str) -> Optional[CompositeAlternativeSignal]:
    """Quick signal generation for single symbol."""
    strategy = CompositeAlternative()
    return await strategy.generate_signal(symbol)


async def screen_composite_signals(
    symbols: list[str],
    min_confidence: float = 0.6,
) -> list[CompositeAlternativeSignal]:
    """Quick screening of multiple symbols."""
    strategy = CompositeAlternative()
    return await strategy.screen_universe(symbols, min_confidence)


async def get_top_picks(n: int = 10) -> list[CompositeAlternativeSignal]:
    """Get top N picks from default universe."""
    universe = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "JNJ", "WMT", "PG", "UNH", "HD", "MA",
    ]

    strategy = CompositeAlternative()
    signals = await strategy.screen_universe(universe, min_confidence=0.5)

    return signals[:n]
