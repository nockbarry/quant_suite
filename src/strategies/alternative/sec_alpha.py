"""
SEC Filing Alpha Strategy

Generate trading signals from SEC filing content analysis:
- Risk factor changes between filings
- MD&A sentiment and tone shifts
- Accounting complexity/readability
- Filing timing and amendments

Research shows that:
- Negative tone changes in MD&A predict negative returns
- New risk factors often precede adverse events
- Complex language can signal obfuscation
"""

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

class FilingSignal(Enum):
    """Signal types from filing analysis."""
    STRONG_BULLISH = 2
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1
    STRONG_BEARISH = -2


@dataclass
class FilingAlphaSignal:
    """Trading signal from SEC filing analysis."""
    symbol: str
    signal: FilingSignal
    confidence: float  # 0 to 1
    signal_date: datetime
    filing_date: datetime
    filing_type: str
    components: dict = field(default_factory=dict)  # Individual signal components
    rationale: str = ""


@dataclass
class FilingFeatures:
    """Features extracted from SEC filings for ML."""
    symbol: str
    filing_date: datetime
    filing_type: str

    # Sentiment features
    overall_sentiment: float
    risk_sentiment: float
    mda_sentiment: float
    sentiment_change: float  # vs prior filing

    # Risk factor features
    risk_factor_count: int
    new_risks_count: int
    removed_risks_count: int

    # Complexity features
    fog_index: float  # Readability
    word_count: int
    complex_word_pct: float

    # Timing features
    days_since_quarter_end: int
    is_amended: bool


# =============================================================================
# SEC FILING ALPHA STRATEGY
# =============================================================================

class SECFilingAlpha:
    """
    Generate trading signals from SEC filing analysis.

    Usage:
        strategy = SECFilingAlpha()

        # Get signal for single symbol
        signal = await strategy.generate_signal("AAPL")

        # Get features for ML
        features = await strategy.get_filing_features("AAPL")

        # Screen universe for signals
        signals = await strategy.screen_universe(["AAPL", "MSFT", "GOOGL"])
    """

    # Thresholds for signal generation
    SENTIMENT_THRESHOLD = 0.15  # Sentiment change to trigger signal
    RISK_CHANGE_THRESHOLD = 3   # New risk factors to trigger concern
    COMPLEXITY_THRESHOLD = 18   # Fog index above this = concerning

    def __init__(self):
        self._scraper = None

    @property
    def scraper(self):
        """Lazy load SEC scraper."""
        if self._scraper is None:
            from src.data.sources.web.sec_filings import SECFilingScraper
            self._scraper = SECFilingScraper()
        return self._scraper

    async def close(self):
        """Close scraper session."""
        if self._scraper:
            await self._scraper.close()

    async def generate_signal(self, symbol: str) -> Optional[FilingAlphaSignal]:
        """
        Generate trading signal from recent SEC filings.

        Args:
            symbol: Stock symbol

        Returns:
            FilingAlphaSignal or None if no signal
        """
        try:
            # Get recent 10-K or 10-Q with comparison
            doc, comparison = await self.scraper.get_filing_with_comparison(
                symbol, filing_type="10-K"
            )

            if doc.full_text == "":
                logger.warning(f"No filing content for {symbol}")
                return None

            # Get filing sentiment
            sentiment = self.scraper.get_filing_sentiment(doc)

            # Build signal components
            components = {
                "overall_sentiment": sentiment.overall_sentiment,
                "risk_sentiment": sentiment.section_sentiments.get("risk_factors", 0),
                "mda_sentiment": sentiment.section_sentiments.get("mda", 0),
            }

            if comparison:
                components["sentiment_change"] = comparison.sentiment_change
                components["new_risks"] = len(comparison.new_risk_factors)
                components["removed_risks"] = len(comparison.removed_risk_factors)
            else:
                components["sentiment_change"] = 0
                components["new_risks"] = 0
                components["removed_risks"] = 0

            # Calculate signal
            signal, confidence, rationale = self._calculate_signal(components)

            return FilingAlphaSignal(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                signal_date=datetime.now(),
                filing_date=doc.filing.filed_date,
                filing_type=doc.filing.filing_type,
                components=components,
                rationale=rationale,
            )

        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None

    def _calculate_signal(self, components: dict) -> tuple[FilingSignal, float, str]:
        """Calculate signal from components."""
        score = 0.0
        reasons = []

        # Sentiment contribution
        sentiment = components.get("overall_sentiment", 0)
        if sentiment > 0.2:
            score += 1.0
            reasons.append("Positive overall sentiment")
        elif sentiment < -0.2:
            score -= 1.0
            reasons.append("Negative overall sentiment")

        # Sentiment change contribution
        change = components.get("sentiment_change", 0)
        if change > self.SENTIMENT_THRESHOLD:
            score += 1.5
            reasons.append(f"Sentiment improved {change:.0%}")
        elif change < -self.SENTIMENT_THRESHOLD:
            score -= 1.5
            reasons.append(f"Sentiment declined {abs(change):.0%}")

        # Risk factor changes
        new_risks = components.get("new_risks", 0)
        removed_risks = components.get("removed_risks", 0)

        if new_risks > self.RISK_CHANGE_THRESHOLD:
            score -= 1.0
            reasons.append(f"{new_risks} new risk factors added")

        if removed_risks > self.RISK_CHANGE_THRESHOLD:
            score += 0.5
            reasons.append(f"{removed_risks} risk factors removed")

        # Determine signal
        if score >= 2.0:
            signal = FilingSignal.STRONG_BULLISH
            confidence = min(0.8, 0.5 + abs(score) * 0.1)
        elif score >= 1.0:
            signal = FilingSignal.BULLISH
            confidence = min(0.7, 0.4 + abs(score) * 0.1)
        elif score <= -2.0:
            signal = FilingSignal.STRONG_BEARISH
            confidence = min(0.8, 0.5 + abs(score) * 0.1)
        elif score <= -1.0:
            signal = FilingSignal.BEARISH
            confidence = min(0.7, 0.4 + abs(score) * 0.1)
        else:
            signal = FilingSignal.NEUTRAL
            confidence = 0.5

        rationale = "; ".join(reasons) if reasons else "No significant signals"

        return signal, confidence, rationale

    async def get_filing_features(self, symbol: str) -> Optional[FilingFeatures]:
        """
        Extract ML features from recent filing.

        Args:
            symbol: Stock symbol

        Returns:
            FilingFeatures for ML models
        """
        try:
            doc, comparison = await self.scraper.get_filing_with_comparison(
                symbol, filing_type="10-K"
            )

            if doc.full_text == "":
                return None

            sentiment = self.scraper.get_filing_sentiment(doc)

            # Calculate fog index (simplified)
            words = doc.full_text.split()
            word_count = len(words)
            sentences = doc.full_text.count(".") + doc.full_text.count("!") + doc.full_text.count("?")
            sentences = max(sentences, 1)

            # Complex words (3+ syllables, approximated by length)
            complex_words = sum(1 for w in words if len(w) > 8)
            complex_word_pct = complex_words / max(word_count, 1)

            avg_sentence_length = word_count / sentences
            fog_index = 0.4 * (avg_sentence_length + complex_word_pct * 100)

            # Days since quarter end (approximate)
            filing_month = doc.filing.filed_date.month
            quarter_end_month = ((filing_month - 1) // 3) * 3 + 3
            days_since = (doc.filing.filed_date.month - quarter_end_month) * 30

            # Risk factor count (approximate from word count in section)
            risk_text = doc.sections.get("risk_factors", "")
            risk_factor_count = risk_text.count("•") + risk_text.count("risk") // 5

            return FilingFeatures(
                symbol=symbol,
                filing_date=doc.filing.filed_date,
                filing_type=doc.filing.filing_type,
                overall_sentiment=sentiment.overall_sentiment,
                risk_sentiment=sentiment.section_sentiments.get("risk_factors", 0),
                mda_sentiment=sentiment.section_sentiments.get("mda", 0),
                sentiment_change=comparison.sentiment_change if comparison else 0,
                risk_factor_count=risk_factor_count,
                new_risks_count=len(comparison.new_risk_factors) if comparison else 0,
                removed_risks_count=len(comparison.removed_risk_factors) if comparison else 0,
                fog_index=fog_index,
                word_count=word_count,
                complex_word_pct=complex_word_pct,
                days_since_quarter_end=days_since,
                is_amended="/A" in doc.filing.filing_type,
            )

        except Exception as e:
            logger.error(f"Error extracting features for {symbol}: {e}")
            return None

    async def screen_universe(
        self,
        symbols: list[str],
        min_confidence: float = 0.6,
    ) -> list[FilingAlphaSignal]:
        """
        Screen universe for filing-based signals.

        Args:
            symbols: List of symbols to screen
            min_confidence: Minimum confidence for signal

        Returns:
            List of signals meeting threshold
        """
        signals = []

        for symbol in symbols:
            signal = await self.generate_signal(symbol)

            if signal and signal.confidence >= min_confidence:
                if signal.signal != FilingSignal.NEUTRAL:
                    signals.append(signal)

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        logger.info(f"Found {len(signals)} filing signals from {len(symbols)} symbols")
        return signals

    def signals_to_dataframe(self, signals: list[FilingAlphaSignal]) -> pd.DataFrame:
        """Convert signals to DataFrame for analysis."""
        data = []
        for s in signals:
            data.append({
                "symbol": s.symbol,
                "signal": s.signal.value,
                "signal_name": s.signal.name,
                "confidence": s.confidence,
                "signal_date": s.signal_date,
                "filing_date": s.filing_date,
                "filing_type": s.filing_type,
                "rationale": s.rationale,
                **s.components,
            })

        return pd.DataFrame(data)

    async def get_features_dataframe(self, symbols: list[str]) -> pd.DataFrame:
        """Get filing features for multiple symbols as DataFrame."""
        features = []

        for symbol in symbols:
            f = await self.get_filing_features(symbol)
            if f:
                features.append({
                    "symbol": f.symbol,
                    "filing_date": f.filing_date,
                    "filing_type": f.filing_type,
                    "overall_sentiment": f.overall_sentiment,
                    "risk_sentiment": f.risk_sentiment,
                    "mda_sentiment": f.mda_sentiment,
                    "sentiment_change": f.sentiment_change,
                    "risk_factor_count": f.risk_factor_count,
                    "new_risks_count": f.new_risks_count,
                    "removed_risks_count": f.removed_risks_count,
                    "fog_index": f.fog_index,
                    "word_count": f.word_count,
                    "complex_word_pct": f.complex_word_pct,
                    "days_since_quarter_end": f.days_since_quarter_end,
                    "is_amended": f.is_amended,
                })

        return pd.DataFrame(features)


# =============================================================================
# BACKTEST INTEGRATION
# =============================================================================

class SECFilingAlphaBacktest:
    """
    Backtest SEC filing alpha strategy.

    Note: Historical filing data requires SEC EDGAR archives.
    This provides the framework for backtesting.
    """

    def __init__(self, strategy: SECFilingAlpha = None):
        self.strategy = strategy or SECFilingAlpha()

    async def backtest(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Backtest strategy on historical data.

        Returns DataFrame with dates, signals, and returns.
        """
        # This would require historical filing data
        # For now, return placeholder
        logger.info(f"Backtest for {len(symbols)} symbols from {start_date} to {end_date}")

        return pd.DataFrame({
            "date": pd.date_range(start_date, end_date, freq="D"),
            "signal": 0,
            "return": 0.0,
        })

    def calculate_metrics(self, backtest_results: pd.DataFrame) -> dict:
        """Calculate backtest performance metrics."""
        returns = backtest_results["return"]

        return {
            "total_return": returns.sum(),
            "sharpe_ratio": returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0,
            "win_rate": (returns > 0).mean(),
            "max_drawdown": (returns.cumsum() - returns.cumsum().cummax()).min(),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_filing_signal(symbol: str) -> Optional[FilingAlphaSignal]:
    """Quick signal generation for single symbol."""
    strategy = SECFilingAlpha()
    try:
        return await strategy.generate_signal(symbol)
    finally:
        await strategy.close()


async def screen_for_filing_alpha(
    symbols: list[str],
    min_confidence: float = 0.6,
) -> list[FilingAlphaSignal]:
    """Quick screening of multiple symbols."""
    strategy = SECFilingAlpha()
    try:
        return await strategy.screen_universe(symbols, min_confidence)
    finally:
        await strategy.close()
