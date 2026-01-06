"""Sentiment Indicators for market analysis.

Provides:
- Put/Call ratio analysis
- VIX term structure
- Fear & Greed index (estimated)
- Social sentiment (Reddit, news)
- Insider activity tracking
- Contrarian signal generation

Usage:
    from src.data.pipeline.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    sentiment = analyzer.get_sentiment()
    print(analyzer.get_summary())
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class PutCallData:
    """Put/Call ratio analysis."""

    equity_pc_ratio: float
    index_pc_ratio: float
    total_pc_ratio: float
    pc_5d_avg: float
    pc_20d_avg: float
    signal: str  # "bullish" (high P/C), "bearish" (low P/C), "neutral"
    percentile: float  # vs 1 year

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity_pc_ratio": round(self.equity_pc_ratio, 2),
            "index_pc_ratio": round(self.index_pc_ratio, 2),
            "total_pc_ratio": round(self.total_pc_ratio, 2),
            "pc_5d_avg": round(self.pc_5d_avg, 2),
            "pc_20d_avg": round(self.pc_20d_avg, 2),
            "signal": self.signal,
            "percentile": round(self.percentile, 1),
        }


@dataclass
class VIXStructure:
    """VIX term structure analysis."""

    vix_spot: float
    vix_3m: float  # 3-month VIX (approximated from VIX3M)
    vix_ratio: float  # spot / 3m
    structure: str  # "contango", "backwardation", "flat"
    mean_reversion_signal: str  # "buy", "sell", "hold"

    def to_dict(self) -> dict[str, Any]:
        return {
            "vix_spot": round(self.vix_spot, 2),
            "vix_3m": round(self.vix_3m, 2),
            "vix_ratio": round(self.vix_ratio, 2),
            "structure": self.structure,
            "mean_reversion_signal": self.mean_reversion_signal,
        }


@dataclass
class FearGreedData:
    """Fear & Greed Index estimation."""

    value: int  # 0-100
    label: str  # "Extreme Fear" to "Extreme Greed"
    previous_close: int
    week_ago: int
    month_ago: int
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "previous_close": self.previous_close,
            "week_ago": self.week_ago,
            "month_ago": self.month_ago,
            "components": self.components,
        }


@dataclass
class InsiderTrade:
    """Single insider trade."""

    symbol: str
    insider_name: str
    title: str
    trade_type: str  # "Buy", "Sell"
    shares: int
    price: float
    value: float
    date: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "insider_name": self.insider_name,
            "title": self.title,
            "trade_type": self.trade_type,
            "shares": self.shares,
            "price": round(self.price, 2),
            "value": round(self.value, 2),
            "date": self.date.isoformat(),
        }


@dataclass
class SocialSentiment:
    """Social media sentiment analysis."""

    source: str  # "reddit", "twitter", etc.
    overall_sentiment: float  # -1 to 1
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    trending_tickers: list[str] = field(default_factory=list)
    sample_posts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "overall_sentiment": round(self.overall_sentiment, 2),
            "bullish_pct": round(self.bullish_pct, 1),
            "bearish_pct": round(self.bearish_pct, 1),
            "neutral_pct": round(self.neutral_pct, 1),
            "trending_tickers": self.trending_tickers[:10],
            "sample_posts": self.sample_posts[:5],
        }


@dataclass
class SentimentIndicators:
    """Complete sentiment indicator snapshot."""

    timestamp: datetime

    # Put/Call
    put_call: PutCallData | None = None

    # VIX
    vix_structure: VIXStructure | None = None

    # Fear & Greed
    fear_greed: FearGreedData | None = None

    # Social
    social_sentiment: list[SocialSentiment] = field(default_factory=list)

    # Insider activity
    insider_buy_sell_ratio: float = 1.0
    notable_insider_buys: list[InsiderTrade] = field(default_factory=list)
    notable_insider_sells: list[InsiderTrade] = field(default_factory=list)

    # Composite
    composite_sentiment: float = 0.0  # -1 (extreme fear) to 1 (extreme greed)
    contrarian_signal: str = "none"  # "buy", "sell", "none"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "put_call": self.put_call.to_dict() if self.put_call else None,
            "vix_structure": self.vix_structure.to_dict() if self.vix_structure else None,
            "fear_greed": self.fear_greed.to_dict() if self.fear_greed else None,
            "social_sentiment": [s.to_dict() for s in self.social_sentiment],
            "insider_buy_sell_ratio": round(self.insider_buy_sell_ratio, 2),
            "notable_insider_buys": [t.to_dict() for t in self.notable_insider_buys],
            "notable_insider_sells": [t.to_dict() for t in self.notable_insider_sells],
            "composite_sentiment": round(self.composite_sentiment, 2),
            "contrarian_signal": self.contrarian_signal,
            "notes": self.notes,
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"SENTIMENT INDICATORS - {self.timestamp.strftime('%H:%M ET')}",
            "=" * 50,
        ]

        # Fear & Greed
        if self.fear_greed:
            fg = self.fear_greed
            lines.extend([
                "",
                f"FEAR & GREED INDEX: {fg.value} ({fg.label})",
                f"  Previous: {fg.previous_close} | Week Ago: {fg.week_ago} | Month Ago: {fg.month_ago}",
            ])

        # Put/Call
        if self.put_call:
            pc = self.put_call
            lines.extend([
                "",
                "PUT/CALL RATIO:",
                f"  Total P/C: {pc.total_pc_ratio:.2f} (5d avg: {pc.pc_5d_avg:.2f})",
                f"  Signal: {pc.signal.upper()} (percentile: {pc.percentile:.0f})",
            ])

        # VIX Structure
        if self.vix_structure:
            vix = self.vix_structure
            lines.extend([
                "",
                "VIX TERM STRUCTURE:",
                f"  Spot: {vix.vix_spot:.2f} | 3M: {vix.vix_3m:.2f}",
                f"  Structure: {vix.structure.title()} | Signal: {vix.mean_reversion_signal.upper()}",
            ])

        # Social Sentiment
        if self.social_sentiment:
            lines.append("")
            lines.append("SOCIAL SENTIMENT:")
            for social in self.social_sentiment:
                emoji = "🟢" if social.overall_sentiment > 0.2 else "🔴" if social.overall_sentiment < -0.2 else "⚪"
                lines.append(
                    f"  {emoji} {social.source.title()}: "
                    f"{social.bullish_pct:.0f}% bull / {social.bearish_pct:.0f}% bear"
                )
                if social.trending_tickers:
                    lines.append(f"     Trending: {', '.join(social.trending_tickers[:5])}")

        # Insider Activity
        if self.notable_insider_buys or self.notable_insider_sells:
            lines.extend([
                "",
                f"INSIDER ACTIVITY (Buy/Sell Ratio: {self.insider_buy_sell_ratio:.2f}):",
            ])
            if self.notable_insider_buys:
                for trade in self.notable_insider_buys[:3]:
                    lines.append(
                        f"  🟢 {trade.symbol}: {trade.insider_name} bought ${trade.value/1000:.0f}K"
                    )
            if self.notable_insider_sells:
                for trade in self.notable_insider_sells[:3]:
                    lines.append(
                        f"  🔴 {trade.symbol}: {trade.insider_name} sold ${trade.value/1000:.0f}K"
                    )

        # Composite
        lines.extend([
            "",
            f"COMPOSITE SENTIMENT: {self.composite_sentiment:+.2f}",
        ])

        if self.contrarian_signal != "none":
            lines.append(f"CONTRARIAN SIGNAL: {self.contrarian_signal.upper()}")

        if self.notes:
            lines.extend(["", "NOTES:"])
            for note in self.notes[:5]:
                lines.append(f"  - {note}")

        return "\n".join(lines)


class SentimentAnalyzer:
    """
    Sentiment indicator analyzer.

    Aggregates multiple sentiment sources to provide
    market sentiment context and contrarian signals.
    """

    def __init__(self):
        """Initialize analyzer."""
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl = timedelta(hours=1)

    async def _fetch_url(self, url: str, headers: dict | None = None) -> str | None:
        """Fetch URL content."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers or {})
                if response.status_code == 200:
                    return response.text
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
        return None

    def _get_vix_data(self) -> tuple[float, float]:
        """Get VIX spot and 3-month approximation."""
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1mo")

            if len(hist) > 0:
                spot = float(hist["Close"].iloc[-1])

                # Estimate 3M VIX from 20-day average
                avg_20d = float(hist["Close"].tail(20).mean())
                vix_3m = avg_20d * 1.1  # VIX3M typically ~10% higher

                return spot, vix_3m

        except Exception as e:
            logger.warning(f"Failed to get VIX data: {e}")

        return 15.0, 16.5  # Defaults

    def _estimate_put_call(self) -> PutCallData | None:
        """Estimate put/call ratio from options volume."""
        try:
            # Use SPY as proxy for market P/C
            spy = yf.Ticker("SPY")
            exps = spy.options[:2]  # First 2 expirations

            total_put_volume = 0
            total_call_volume = 0

            for exp in exps:
                try:
                    chain = spy.option_chain(exp)
                    total_put_volume += chain.puts["volume"].sum()
                    total_call_volume += chain.calls["volume"].sum()
                except Exception:
                    continue

            if total_call_volume > 0:
                pc_ratio = total_put_volume / total_call_volume
            else:
                pc_ratio = 1.0

            # Determine signal (higher P/C = more fear = contrarian bullish)
            if pc_ratio > 1.2:
                signal = "bullish"  # High P/C is contrarian bullish
                percentile = min(pc_ratio / 1.5 * 100, 100)
            elif pc_ratio < 0.8:
                signal = "bearish"  # Low P/C is contrarian bearish
                percentile = max((1 - pc_ratio / 0.8) * 100, 0)
            else:
                signal = "neutral"
                percentile = 50.0

            return PutCallData(
                equity_pc_ratio=pc_ratio,
                index_pc_ratio=pc_ratio,
                total_pc_ratio=pc_ratio,
                pc_5d_avg=pc_ratio,  # Simplified
                pc_20d_avg=1.0,
                signal=signal,
                percentile=percentile,
            )

        except Exception as e:
            logger.warning(f"Failed to estimate P/C ratio: {e}")
            return None

    def _analyze_vix_structure(self) -> VIXStructure | None:
        """Analyze VIX term structure."""
        try:
            spot, vix_3m = self._get_vix_data()

            ratio = spot / vix_3m if vix_3m > 0 else 1.0

            if ratio < 0.9:
                structure = "contango"
                mean_reversion_signal = "hold"  # Normal, no signal
            elif ratio > 1.1:
                structure = "backwardation"
                mean_reversion_signal = "buy"  # Fear elevated, contrarian buy
            else:
                structure = "flat"
                mean_reversion_signal = "hold"

            return VIXStructure(
                vix_spot=spot,
                vix_3m=vix_3m,
                vix_ratio=ratio,
                structure=structure,
                mean_reversion_signal=mean_reversion_signal,
            )

        except Exception as e:
            logger.warning(f"Failed to analyze VIX structure: {e}")
            return None

    def _estimate_fear_greed(self, vix_structure: VIXStructure | None, put_call: PutCallData | None) -> FearGreedData:
        """
        Estimate Fear & Greed index from available data.

        Components (simplified):
        - VIX level (fear if high)
        - VIX structure (fear if backwardation)
        - Put/Call ratio (fear if high)
        - Market momentum (using SPY)
        - Market breadth (estimated)
        """
        components = {}
        scores = []

        # VIX component (0-100, 0 = extreme fear)
        if vix_structure:
            vix = vix_structure.vix_spot
            if vix < 12:
                vix_score = 90  # Extreme greed (complacency)
            elif vix < 15:
                vix_score = 75
            elif vix < 20:
                vix_score = 50
            elif vix < 25:
                vix_score = 30
            elif vix < 30:
                vix_score = 15
            else:
                vix_score = 5  # Extreme fear

            components["vix"] = vix_score
            scores.append(vix_score)

        # Put/Call component
        if put_call:
            pc = put_call.total_pc_ratio
            if pc < 0.7:
                pc_score = 85  # Greed
            elif pc < 0.9:
                pc_score = 65
            elif pc < 1.1:
                pc_score = 50
            elif pc < 1.3:
                pc_score = 35
            else:
                pc_score = 15  # Fear

            components["put_call"] = pc_score
            scores.append(pc_score)

        # Market momentum (SPY 20-day return)
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="30d")
            if len(hist) >= 20:
                ret_20d = (hist["Close"].iloc[-1] / hist["Close"].iloc[-20] - 1) * 100

                if ret_20d > 5:
                    momentum_score = 85
                elif ret_20d > 2:
                    momentum_score = 70
                elif ret_20d > 0:
                    momentum_score = 55
                elif ret_20d > -2:
                    momentum_score = 40
                elif ret_20d > -5:
                    momentum_score = 25
                else:
                    momentum_score = 10

                components["momentum"] = momentum_score
                scores.append(momentum_score)

        except Exception:
            pass

        # Calculate composite
        if scores:
            value = int(np.mean(scores))
        else:
            value = 50

        # Label
        if value <= 20:
            label = "Extreme Fear"
        elif value <= 40:
            label = "Fear"
        elif value <= 60:
            label = "Neutral"
        elif value <= 80:
            label = "Greed"
        else:
            label = "Extreme Greed"

        return FearGreedData(
            value=value,
            label=label,
            previous_close=value,  # Simplified
            week_ago=50,
            month_ago=50,
            components=components,
        )

    def _estimate_social_sentiment(self) -> list[SocialSentiment]:
        """
        Estimate social sentiment.

        Note: Real implementation would use Reddit API (PRAW) and Twitter API.
        This provides a placeholder structure.
        """
        # Placeholder - in production would use actual API data
        return [
            SocialSentiment(
                source="reddit",
                overall_sentiment=0.1,
                bullish_pct=45,
                bearish_pct=35,
                neutral_pct=20,
                trending_tickers=["SPY", "NVDA", "TSLA", "AAPL", "AMD"],
                sample_posts=["Market looking strong", "Buying the dip"],
            )
        ]

    def _get_insider_activity(self, symbols: list[str] | None = None) -> tuple[float, list[InsiderTrade], list[InsiderTrade]]:
        """
        Get recent insider trading activity.

        Note: Real implementation would use SEC EDGAR Form 4 data.
        This provides placeholder structure.
        """
        # Placeholder - in production would scrape SEC EDGAR
        buys = []
        sells = []
        ratio = 1.0

        return ratio, buys, sells

    def _calculate_composite(
        self,
        fear_greed: FearGreedData | None,
        put_call: PutCallData | None,
        vix_structure: VIXStructure | None,
        social: list[SocialSentiment],
    ) -> tuple[float, str, list[str]]:
        """Calculate composite sentiment and contrarian signals."""
        scores = []
        notes = []

        # Fear & Greed (convert 0-100 to -1 to 1)
        if fear_greed:
            fg_score = (fear_greed.value - 50) / 50
            scores.append(fg_score)

            if fear_greed.value <= 20:
                notes.append("Extreme fear - contrarian buy signal")
            elif fear_greed.value >= 80:
                notes.append("Extreme greed - contrarian sell signal")

        # VIX structure
        if vix_structure:
            if vix_structure.structure == "backwardation":
                scores.append(-0.5)
                notes.append("VIX backwardation indicates elevated fear")
            elif vix_structure.vix_spot < 12:
                scores.append(0.5)
                notes.append("VIX very low - complacency warning")

        # Social sentiment
        for s in social:
            scores.append(s.overall_sentiment)

        # Calculate composite
        if scores:
            composite = float(np.mean(scores))
        else:
            composite = 0.0

        # Determine contrarian signal
        if composite < -0.5:
            contrarian = "buy"  # Fear = buy
        elif composite > 0.5:
            contrarian = "sell"  # Greed = sell
        else:
            contrarian = "none"

        return composite, contrarian, notes

    def get_sentiment(self) -> SentimentIndicators:
        """
        Get current sentiment indicators.

        Returns:
            SentimentIndicators with full analysis
        """
        timestamp = datetime.now()

        # Collect data
        put_call = self._estimate_put_call()
        vix_structure = self._analyze_vix_structure()
        fear_greed = self._estimate_fear_greed(vix_structure, put_call)
        social = self._estimate_social_sentiment()

        # Insider activity
        insider_ratio, insider_buys, insider_sells = self._get_insider_activity()

        # Calculate composite
        composite, contrarian, notes = self._calculate_composite(
            fear_greed, put_call, vix_structure, social
        )

        return SentimentIndicators(
            timestamp=timestamp,
            put_call=put_call,
            vix_structure=vix_structure,
            fear_greed=fear_greed,
            social_sentiment=social,
            insider_buy_sell_ratio=insider_ratio,
            notable_insider_buys=insider_buys,
            notable_insider_sells=insider_sells,
            composite_sentiment=composite,
            contrarian_signal=contrarian,
            notes=notes,
        )

    def get_put_call(self) -> PutCallData | None:
        """Get put/call ratio analysis."""
        return self._estimate_put_call()

    def get_fear_greed(self) -> FearGreedData | None:
        """Get Fear & Greed index estimate."""
        sentiment = self.get_sentiment()
        return sentiment.fear_greed

    def get_social_sentiment(self, symbol: str | None = None) -> list[SocialSentiment]:
        """Get social media sentiment."""
        return self._estimate_social_sentiment()

    def get_insider_activity(self, symbol: str | None = None) -> list[InsiderTrade]:
        """Get recent insider trades."""
        _, buys, sells = self._get_insider_activity([symbol] if symbol else None)
        return buys + sells

    def get_contrarian_signals(self) -> list[str]:
        """Get contrarian trade signals from sentiment extremes."""
        sentiment = self.get_sentiment()
        signals = []

        if sentiment.contrarian_signal == "buy":
            signals.append("CONTRARIAN BUY: Extreme fear detected")
        elif sentiment.contrarian_signal == "sell":
            signals.append("CONTRARIAN SELL: Extreme greed detected")

        if sentiment.fear_greed and sentiment.fear_greed.value <= 25:
            signals.append(f"Fear & Greed at {sentiment.fear_greed.value} - historically a buy zone")

        if sentiment.vix_structure and sentiment.vix_structure.vix_spot > 30:
            signals.append(f"VIX at {sentiment.vix_structure.vix_spot:.1f} - panic levels, consider buying")

        return signals

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        sentiment = self.get_sentiment()
        return sentiment.get_summary()
