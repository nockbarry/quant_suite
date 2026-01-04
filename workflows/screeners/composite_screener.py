"""
Composite stock screener combining price and alternative data signals.

Designed for discovering budget picks that can't be found from price data alone.
Combines signals from:
- Insider trading activity (Form 4)
- Options flow (put/call ratio, unusual activity)
- Social sentiment (Reddit/WSB)
- News sentiment
- Price momentum
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
import asyncio

import numpy as np
import pandas as pd


@dataclass
class ScreenerSignal:
    """Individual signal from a data source."""

    source: str  # e.g., "insider", "reddit", "options", "news", "momentum"
    signal: Literal["bullish", "bearish", "neutral"]
    strength: float  # 0-1, how strong the signal is
    confidence: float  # 0-1, confidence in the signal
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "signal": self.signal,
            "strength": self.strength,
            "confidence": self.confidence,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CompositeScore:
    """Aggregated score for a symbol combining all signals."""

    symbol: str
    overall_score: float  # -1 to 1
    overall_signal: Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"]
    signals: list[ScreenerSignal] = field(default_factory=list)
    price_data: dict[str, Any] = field(default_factory=dict)
    alt_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "overall_score": self.overall_score,
            "overall_signal": self.overall_signal,
            "n_signals": len(self.signals),
            "n_bullish": sum(1 for s in self.signals if s.signal == "bullish"),
            "n_bearish": sum(1 for s in self.signals if s.signal == "bearish"),
            "signals": [s.to_dict() for s in self.signals],
            "price_data": self.price_data,
            "alt_data": self.alt_data,
        }


class CompositeScreener:
    """
    Multi-signal stock screener combining price and alternative data.

    Signal Weights (configurable):
    - Insider Activity: 0.30 (strongest signal - insider buying is meaningful)
    - Options Flow: 0.20 (unusual activity can be predictive)
    - Reddit Sentiment: 0.15 (contrarian indicator)
    - News Sentiment: 0.15
    - Price Momentum: 0.20

    Usage:
        screener = CompositeScreener()
        results = await screener.screen(["AAPL", "NVDA", "TSLA"])
        for score in results[:5]:
            print(f"{score.symbol}: {score.overall_signal} ({score.overall_score:.2f})")
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
    ):
        """
        Initialize the screener.

        Args:
            weights: Custom signal weights (should sum to ~1.0)
        """
        self.weights = weights or {
            "insider": 0.30,
            "options_flow": 0.20,
            "reddit_sentiment": 0.15,
            "news_sentiment": 0.15,
            "momentum": 0.20,
        }

    async def screen(
        self,
        symbols: list[str],
        lookback_days: int = 30,
        min_signals: int = 1,
        price_data: dict[str, pd.DataFrame] | None = None,
    ) -> list[CompositeScore]:
        """
        Screen symbols with composite signals.

        Args:
            symbols: List of symbols to screen
            lookback_days: Days of history to analyze
            min_signals: Minimum number of signals required for inclusion
            price_data: Optional pre-loaded OHLCV data

        Returns:
            List of CompositeScore sorted by overall_score (best first)
        """
        results = []

        for symbol in symbols:
            try:
                score = await self._score_symbol(
                    symbol,
                    lookback_days,
                    price_data.get(symbol) if price_data else None,
                )
                if len(score.signals) >= min_signals:
                    results.append(score)
            except Exception as e:
                # Log but continue with other symbols
                continue

            # Small delay for rate limiting
            await asyncio.sleep(0.1)

        # Sort by overall score (highest first)
        results.sort(key=lambda x: x.overall_score, reverse=True)
        return results

    async def _score_symbol(
        self,
        symbol: str,
        lookback_days: int,
        price_df: pd.DataFrame | None = None,
    ) -> CompositeScore:
        """Generate composite score for a single symbol."""
        signals: list[ScreenerSignal] = []
        alt_data: dict[str, Any] = {}
        price_data: dict[str, Any] = {}

        # 1. Price Momentum (always available if we have price data)
        if price_df is not None and len(price_df) > lookback_days:
            momentum_signal = self._get_momentum_signal(price_df, lookback_days)
            if momentum_signal:
                signals.append(momentum_signal)
                price_data["momentum"] = momentum_signal.details

        # 2. Insider Activity (simulated - in real use, would call InsiderDataSource)
        insider_signal = await self._get_insider_signal_simulated(symbol)
        if insider_signal:
            signals.append(insider_signal)
            alt_data["insider"] = insider_signal.details

        # 3. Options Flow (simulated - in real use, would call OptionsFlowSource)
        options_signal = await self._get_options_signal_simulated(symbol)
        if options_signal:
            signals.append(options_signal)
            alt_data["options"] = options_signal.details

        # 4. Reddit Sentiment (simulated - in real use, would call RedditDataSource)
        reddit_signal = await self._get_reddit_signal_simulated(symbol)
        if reddit_signal:
            signals.append(reddit_signal)
            alt_data["reddit"] = reddit_signal.details

        # 5. News Sentiment (simulated - in real use, would call NewsDataSource)
        news_signal = await self._get_news_signal_simulated(symbol)
        if news_signal:
            signals.append(news_signal)
            alt_data["news"] = news_signal.details

        # Calculate composite score
        overall_score = self._calculate_composite_score(signals)

        # Determine overall signal
        if overall_score >= 0.5:
            overall_signal = "strong_buy"
        elif overall_score >= 0.2:
            overall_signal = "buy"
        elif overall_score <= -0.5:
            overall_signal = "strong_sell"
        elif overall_score <= -0.2:
            overall_signal = "sell"
        else:
            overall_signal = "neutral"

        return CompositeScore(
            symbol=symbol,
            overall_score=overall_score,
            overall_signal=overall_signal,
            signals=signals,
            price_data=price_data,
            alt_data=alt_data,
        )

    def _get_momentum_signal(
        self,
        df: pd.DataFrame,
        lookback: int,
    ) -> ScreenerSignal | None:
        """Extract momentum signal from price data."""
        try:
            close = df["close"]

            # Calculate multiple momentum metrics
            ret_5d = (close.iloc[-1] / close.iloc[-5] - 1) if len(close) > 5 else 0
            ret_20d = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) > 20 else 0
            ret_60d = (close.iloc[-1] / close.iloc[-60] - 1) if len(close) > 60 else 0

            # RSI
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / (loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50

            # Combine signals
            momentum_score = (ret_5d * 0.3 + ret_20d * 0.4 + ret_60d * 0.3)

            if momentum_score > 0.05:
                signal = "bullish"
                strength = min(1.0, momentum_score * 5)
            elif momentum_score < -0.05:
                signal = "bearish"
                strength = min(1.0, abs(momentum_score) * 5)
            else:
                signal = "neutral"
                strength = 0.3

            # RSI adjustment (oversold = bullish, overbought = bearish)
            if current_rsi < 30:
                if signal != "bullish":
                    signal = "bullish"
                    strength = max(strength, 0.6)
            elif current_rsi > 70:
                if signal != "bearish":
                    signal = "bearish"
                    strength = max(strength, 0.6)

            return ScreenerSignal(
                source="momentum",
                signal=signal,
                strength=strength,
                confidence=0.7,
                details={
                    "return_5d": ret_5d,
                    "return_20d": ret_20d,
                    "return_60d": ret_60d,
                    "rsi": current_rsi,
                    "momentum_score": momentum_score,
                },
            )
        except Exception:
            return None

    async def _get_insider_signal_simulated(self, symbol: str) -> ScreenerSignal | None:
        """
        Simulated insider trading signal.

        In production, this would call InsiderDataSource from
        src/data/sources/alternative/insider.py
        """
        # Simulate some insider activity based on symbol hash
        np.random.seed(hash(symbol) % 2**32)

        # Random but deterministic for each symbol
        has_activity = np.random.random() > 0.5

        if not has_activity:
            return None

        buys = np.random.randint(0, 5)
        sells = np.random.randint(0, 3)
        net_value = (buys - sells) * np.random.randint(10000, 500000)

        if buys > sells and buys >= 2:
            signal = "bullish"
            strength = min(1.0, buys / 5)
        elif sells > buys and sells >= 2:
            signal = "bearish"
            strength = min(0.8, sells / 4)
        else:
            signal = "neutral"
            strength = 0.3

        return ScreenerSignal(
            source="insider",
            signal=signal,
            strength=strength,
            confidence=0.8 if (buys + sells) >= 3 else 0.5,
            details={
                "total_buys": buys,
                "total_sells": sells,
                "net_value": net_value,
                "cluster_buying": buys >= 3,
            },
        )

    async def _get_options_signal_simulated(self, symbol: str) -> ScreenerSignal | None:
        """
        Simulated options flow signal.

        In production, this would call OptionsFlowSource from
        src/data/sources/alternative/options_flow.py
        """
        np.random.seed((hash(symbol) + 1) % 2**32)

        has_data = np.random.random() > 0.3

        if not has_data:
            return None

        # Simulate put/call ratio (contrarian indicator)
        pc_ratio = np.random.uniform(0.3, 2.0)
        unusual_activity = np.random.randint(0, 5)

        # High P/C ratio = contrarian bullish
        if pc_ratio > 1.3:
            signal = "bullish"
            strength = min(0.8, (pc_ratio - 1) * 0.8)
        elif pc_ratio < 0.6:
            signal = "bearish"
            strength = min(0.6, (0.8 - pc_ratio))
        else:
            signal = "neutral"
            strength = 0.3

        return ScreenerSignal(
            source="options_flow",
            signal=signal,
            strength=strength,
            confidence=0.6 if unusual_activity > 0 else 0.4,
            details={
                "put_call_ratio": pc_ratio,
                "unusual_activity_count": unusual_activity,
                "interpretation": "high P/C = contrarian bullish" if pc_ratio > 1 else "normal",
            },
        )

    async def _get_reddit_signal_simulated(self, symbol: str) -> ScreenerSignal | None:
        """
        Simulated Reddit sentiment signal.

        In production, this would call RedditDataSource from
        src/data/sources/alternative/reddit.py
        """
        np.random.seed((hash(symbol) + 2) % 2**32)

        # Not all stocks have Reddit mentions
        has_mentions = np.random.random() > 0.4

        if not has_mentions:
            return None

        mention_count = np.random.randint(5, 500)
        sentiment_score = np.random.uniform(-0.5, 0.5)

        if sentiment_score > 0.2:
            signal = "bullish"
            strength = min(0.7, sentiment_score * 1.4)
        elif sentiment_score < -0.2:
            signal = "bearish"
            strength = min(0.7, abs(sentiment_score) * 1.4)
        else:
            signal = "neutral"
            strength = 0.3

        return ScreenerSignal(
            source="reddit_sentiment",
            signal=signal,
            strength=strength,
            confidence=min(1.0, mention_count / 200),
            details={
                "mention_count": mention_count,
                "sentiment_score": sentiment_score,
                "trending": mention_count > 100,
            },
        )

    async def _get_news_signal_simulated(self, symbol: str) -> ScreenerSignal | None:
        """
        Simulated news sentiment signal.

        In production, this would call NewsDataSource from
        src/data/sources/alternative/news.py
        """
        np.random.seed((hash(symbol) + 3) % 2**32)

        has_news = np.random.random() > 0.3

        if not has_news:
            return None

        article_count = np.random.randint(1, 30)
        avg_sentiment = np.random.uniform(-0.4, 0.4)

        if avg_sentiment > 0.15:
            signal = "bullish"
            strength = min(0.6, avg_sentiment * 1.5)
        elif avg_sentiment < -0.15:
            signal = "bearish"
            strength = min(0.6, abs(avg_sentiment) * 1.5)
        else:
            signal = "neutral"
            strength = 0.3

        return ScreenerSignal(
            source="news_sentiment",
            signal=signal,
            strength=strength,
            confidence=min(0.8, article_count / 20),
            details={
                "article_count": article_count,
                "avg_sentiment": avg_sentiment,
            },
        )

    def _calculate_composite_score(self, signals: list[ScreenerSignal]) -> float:
        """Calculate weighted composite score from all signals."""
        if not signals:
            return 0.0

        weighted_sum = 0.0
        weight_total = 0.0

        for signal in signals:
            weight = self.weights.get(signal.source, 0.1)

            # Convert signal to numeric value
            if signal.signal == "bullish":
                value = signal.strength * signal.confidence
            elif signal.signal == "bearish":
                value = -signal.strength * signal.confidence
            else:
                value = 0.0

            weighted_sum += value * weight
            weight_total += weight

        if weight_total == 0:
            return 0.0

        # Normalize to [-1, 1]
        return max(-1.0, min(1.0, weighted_sum / weight_total))


# Convenience functions for Claude Code

async def find_budget_picks(
    symbols: list[str],
    min_signals: int = 2,
    price_data: dict[str, pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """
    Find budget picks using alternative data signals.

    This is a main entry point for Claude Code.

    Args:
        symbols: Universe of symbols to screen
        min_signals: Minimum alternative data signals required
        price_data: Optional pre-loaded OHLCV data

    Returns:
        List of picks sorted by composite score, as dictionaries

    Example:
        picks = await find_budget_picks(
            ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD"],
            min_signals=2
        )
        for pick in picks[:5]:
            print(f"{pick['symbol']}: {pick['overall_signal']}")
    """
    screener = CompositeScreener()
    results = await screener.screen(
        symbols,
        min_signals=min_signals,
        price_data=price_data,
    )
    return [r.to_dict() for r in results]


async def screen_momentum(
    symbols: list[str],
    price_data: dict[str, pd.DataFrame],
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Screen for momentum stocks based on price data.

    Simpler screening focused on price momentum without alternative data.

    Args:
        symbols: Universe of symbols
        price_data: OHLCV data for each symbol
        top_n: Number of top picks to return

    Returns:
        List of momentum picks
    """
    results = []

    for symbol in symbols:
        df = price_data.get(symbol)
        if df is None or len(df) < 60:
            continue

        close = df["close"]

        # Calculate momentum metrics
        ret_20d = (close.iloc[-1] / close.iloc[-20] - 1)
        ret_60d = (close.iloc[-1] / close.iloc[-60] - 1)

        # Volatility-adjusted momentum
        vol = close.pct_change().rolling(20).std().iloc[-1]
        momentum_score = ret_20d / (vol + 0.01)

        results.append({
            "symbol": symbol,
            "momentum_score": momentum_score,
            "return_20d": ret_20d,
            "return_60d": ret_60d,
            "volatility": vol,
        })

    # Sort by momentum score
    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    return results[:top_n]
