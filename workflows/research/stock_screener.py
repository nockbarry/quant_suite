"""
Stock Screener

Screen stocks for interesting patterns and opportunities:
- Technical criteria (RSI, momentum, volatility)
- Pattern matching (strategy signals)
- Similarity-based discovery
- News-based filtering
- Daily stock picks with reasoning
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

class ScreenerCriteria(Enum):
    """Types of screening criteria."""
    TECHNICAL = "technical"
    MOMENTUM = "momentum"
    VALUE = "value"
    VOLATILITY = "volatility"
    SENTIMENT = "sentiment"
    PATTERN = "pattern"


@dataclass
class ScreenerResult:
    """Result from a stock screen."""
    symbol: str
    score: float  # Overall match score (0-1)
    criteria_matches: dict  # Which criteria matched
    metrics: dict  # Current metric values
    reason: str  # Why this stock matched
    screened_at: datetime = field(default_factory=datetime.now)


@dataclass
class StockPick:
    """A recommended stock pick with reasoning."""
    rank: int
    symbol: str
    signal: str  # "buy", "sell", "watch"
    confidence: float
    timeframe_days: int
    thesis: str
    supporting_factors: list
    risk_factors: list
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# STOCK SCREENER
# =============================================================================

class StockScreener:
    """
    Screen stocks for trading opportunities.

    Usage:
        screener = StockScreener()

        # Screen by criteria
        results = screener.screen_by_criteria({
            "rsi_14": "<30",
            "volume_ratio": ">2",
        })

        # Screen by pattern
        results = screener.screen_by_pattern("bollinger_reversal")

        # Find similar stocks
        results = screener.screen_by_similarity("AAPL")

        # Get daily picks
        picks = screener.get_daily_picks(10)
    """

    # Default universe - S&P 500 subset
    DEFAULT_UNIVERSE = [
        # Tech
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "INTC", "QCOM",
        "AVGO", "CRM", "ADBE", "ORCL", "CSCO", "IBM", "NOW", "INTU", "PYPL", "NFLX",
        # Finance
        "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA",
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR", "BMY",
        # Consumer
        "WMT", "HD", "MCD", "NKE", "SBUX", "TGT", "COST", "LOW", "DIS", "CMCSA",
        # Industrial
        "BA", "CAT", "GE", "HON", "UPS", "RTX", "LMT", "MMM", "DE", "EMR",
        # Energy
        "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "VLO", "OXY", "MPC", "HAL",
        # ETFs
        "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLV", "XLE", "XLI", "XLY",
    ]

    def __init__(self, universe: list[str] = None):
        self.universe = universe or self.DEFAULT_UNIVERSE
        self._price_cache = {}
        self._cache_time = None

    def _get_price_data(self, symbols: list[str], period: str = "60d") -> dict[str, pd.DataFrame]:
        """Fetch price data for symbols (with caching)."""
        import yfinance as yf

        # Check cache freshness
        now = datetime.now()
        if self._cache_time and (now - self._cache_time).seconds < 300:
            # Use cached data if less than 5 minutes old
            missing = [s for s in symbols if s not in self._price_cache]
            if not missing:
                return {s: self._price_cache[s] for s in symbols}
        else:
            missing = symbols
            self._price_cache = {}
            self._cache_time = now

        # Fetch missing data
        if missing:
            try:
                data = yf.download(missing, period=period, progress=False, group_by="ticker")

                for symbol in missing:
                    if len(missing) == 1:
                        df = data
                    else:
                        df = data[symbol] if symbol in data.columns.get_level_values(0) else pd.DataFrame()

                    if not df.empty:
                        df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
                        self._price_cache[symbol] = df

            except Exception as e:
                logger.error(f"Error fetching price data: {e}")

        return {s: self._price_cache.get(s, pd.DataFrame()) for s in symbols}

    def _compute_metrics(self, df: pd.DataFrame) -> dict:
        """Compute screening metrics from price data."""
        if df.empty or len(df) < 20:
            return {}

        close = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]

        metrics = {}

        # Returns
        metrics["return_1d"] = close.pct_change().iloc[-1]
        metrics["return_5d"] = close.pct_change(5).iloc[-1]
        metrics["return_20d"] = close.pct_change(20).iloc[-1]

        # Volatility
        returns = close.pct_change().dropna()
        metrics["volatility_20d"] = returns.rolling(20).std().iloc[-1] * np.sqrt(252)

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        metrics["rsi_14"] = rsi.iloc[-1]

        # Bollinger Bands
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        metrics["bb_position"] = (close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])

        # Volume
        metrics["volume_sma_20"] = volume.rolling(20).mean().iloc[-1]
        metrics["volume_ratio"] = volume.iloc[-1] / metrics["volume_sma_20"]

        # Trend
        metrics["sma_50"] = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
        metrics["sma_200"] = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        metrics["above_sma_50"] = close.iloc[-1] > metrics["sma_50"] if metrics["sma_50"] else None

        # Price levels
        metrics["current_price"] = close.iloc[-1]
        metrics["high_52w"] = high.rolling(252).max().iloc[-1] if len(high) >= 252 else high.max()
        metrics["low_52w"] = low.rolling(252).min().iloc[-1] if len(low) >= 252 else low.min()
        metrics["pct_from_52w_high"] = (close.iloc[-1] - metrics["high_52w"]) / metrics["high_52w"]

        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        metrics["atr_14"] = tr.rolling(14).mean().iloc[-1]
        metrics["atr_pct"] = metrics["atr_14"] / close.iloc[-1]

        return metrics

    def _parse_criteria(self, criteria_str: str, value: float) -> bool:
        """Parse and evaluate a criteria string like '<30' or '>2'."""
        criteria_str = criteria_str.strip()

        if criteria_str.startswith("<="):
            return value <= float(criteria_str[2:])
        elif criteria_str.startswith(">="):
            return value >= float(criteria_str[2:])
        elif criteria_str.startswith("<"):
            return value < float(criteria_str[1:])
        elif criteria_str.startswith(">"):
            return value > float(criteria_str[1:])
        elif criteria_str.startswith("=="):
            return value == float(criteria_str[2:])
        else:
            return value == float(criteria_str)

    def screen_by_criteria(
        self,
        criteria: dict[str, str],
        universe: list[str] = None,
    ) -> list[ScreenerResult]:
        """
        Screen stocks by technical/fundamental criteria.

        Args:
            criteria: Dict of metric -> condition (e.g., {"rsi_14": "<30", "volume_ratio": ">2"})
            universe: List of symbols to screen (default: self.universe)

        Returns:
            List of ScreenerResult for matching stocks
        """
        universe = universe or self.universe
        price_data = self._get_price_data(universe)

        results = []
        for symbol in universe:
            df = price_data.get(symbol, pd.DataFrame())
            if df.empty:
                continue

            metrics = self._compute_metrics(df)
            if not metrics:
                continue

            # Check each criterion
            matches = {}
            all_match = True

            for metric_name, condition in criteria.items():
                if metric_name not in metrics or metrics[metric_name] is None:
                    all_match = False
                    break

                match = self._parse_criteria(condition, metrics[metric_name])
                matches[metric_name] = match

                if not match:
                    all_match = False

            if all_match:
                # Calculate score based on how well criteria are matched
                score = sum(1.0 for m in matches.values() if m) / len(criteria)

                results.append(ScreenerResult(
                    symbol=symbol,
                    score=score,
                    criteria_matches=matches,
                    metrics=metrics,
                    reason=f"Matched {sum(matches.values())}/{len(criteria)} criteria",
                ))

        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)

        logger.info(f"Screen found {len(results)} matches from {len(universe)} symbols")
        return results

    def screen_by_pattern(
        self,
        pattern: str,
        universe: list[str] = None,
    ) -> list[ScreenerResult]:
        """
        Screen stocks by technical pattern.

        Patterns:
        - bollinger_reversal: Price below lower band with RSI oversold
        - momentum_breakout: Strong momentum with volume confirmation
        - mean_reversion: Extreme z-score with reversal signs
        - trend_following: Price above all moving averages
        - volume_climax: Extreme volume with price reversal
        """
        universe = universe or self.universe
        price_data = self._get_price_data(universe)

        results = []

        for symbol in universe:
            df = price_data.get(symbol, pd.DataFrame())
            if df.empty:
                continue

            metrics = self._compute_metrics(df)
            if not metrics:
                continue

            match = False
            score = 0.0
            reason = ""

            if pattern == "bollinger_reversal":
                # Price below lower band with RSI oversold
                if metrics.get("bb_position", 1) < 0.1 and metrics.get("rsi_14", 50) < 35:
                    match = True
                    score = (0.1 - metrics["bb_position"]) + (35 - metrics["rsi_14"]) / 35
                    reason = f"BB position {metrics['bb_position']:.2f}, RSI {metrics['rsi_14']:.0f}"

            elif pattern == "momentum_breakout":
                # Strong momentum with volume
                if (metrics.get("return_20d", 0) > 0.1 and
                    metrics.get("volume_ratio", 1) > 1.5 and
                    metrics.get("above_sma_50")):
                    match = True
                    score = metrics["return_20d"] * metrics["volume_ratio"]
                    reason = f"20d return {metrics['return_20d']*100:.1f}%, volume {metrics['volume_ratio']:.1f}x"

            elif pattern == "mean_reversion":
                # Extreme price move with reversal potential
                pct_from_high = metrics.get("pct_from_52w_high", 0)
                if pct_from_high < -0.3 and metrics.get("rsi_14", 50) < 40:
                    match = True
                    score = abs(pct_from_high) + (40 - metrics["rsi_14"]) / 40
                    reason = f"{pct_from_high*100:.0f}% from 52w high, RSI {metrics['rsi_14']:.0f}"

            elif pattern == "trend_following":
                # Price above moving averages
                price = metrics.get("current_price")
                sma50 = metrics.get("sma_50")
                sma200 = metrics.get("sma_200")

                if price and sma50 and sma200:
                    if price > sma50 > sma200:
                        match = True
                        score = (price / sma50 - 1) + (sma50 / sma200 - 1)
                        reason = f"Price > SMA50 > SMA200, uptrend"

            elif pattern == "volume_climax":
                # Extreme volume
                if metrics.get("volume_ratio", 1) > 3:
                    match = True
                    score = metrics["volume_ratio"] / 3
                    reason = f"Volume {metrics['volume_ratio']:.1f}x average"

            if match:
                results.append(ScreenerResult(
                    symbol=symbol,
                    score=score,
                    criteria_matches={"pattern": pattern},
                    metrics=metrics,
                    reason=reason,
                ))

        results.sort(key=lambda r: r.score, reverse=True)

        logger.info(f"Pattern '{pattern}' found {len(results)} matches")
        return results

    def screen_by_similarity(
        self,
        reference_symbol: str,
        top_k: int = 10,
        universe: list[str] = None,
    ) -> list[ScreenerResult]:
        """
        Find stocks similar to reference symbol.

        Similarity based on:
        - Return correlation
        - Volatility profile
        - Technical indicator similarity
        """
        universe = universe or self.universe
        if reference_symbol in universe:
            universe = [s for s in universe if s != reference_symbol]

        price_data = self._get_price_data([reference_symbol] + universe)

        ref_df = price_data.get(reference_symbol, pd.DataFrame())
        if ref_df.empty:
            return []

        ref_metrics = self._compute_metrics(ref_df)
        ref_returns = ref_df["close"].pct_change().dropna()

        results = []

        for symbol in universe:
            df = price_data.get(symbol, pd.DataFrame())
            if df.empty:
                continue

            metrics = self._compute_metrics(df)
            if not metrics:
                continue

            # Calculate similarity
            returns = df["close"].pct_change().dropna()

            # Return correlation
            min_len = min(len(ref_returns), len(returns))
            if min_len > 20:
                corr = ref_returns.iloc[-min_len:].corr(returns.iloc[-min_len:])
            else:
                corr = 0

            # Volatility similarity
            ref_vol = ref_metrics.get("volatility_20d", 0.2)
            vol = metrics.get("volatility_20d", 0.2)
            vol_sim = 1 - abs(ref_vol - vol) / max(ref_vol, vol)

            # RSI similarity
            ref_rsi = ref_metrics.get("rsi_14", 50)
            rsi = metrics.get("rsi_14", 50)
            rsi_sim = 1 - abs(ref_rsi - rsi) / 100

            # Overall similarity score
            score = 0.5 * max(corr, 0) + 0.3 * vol_sim + 0.2 * rsi_sim

            results.append(ScreenerResult(
                symbol=symbol,
                score=score,
                criteria_matches={
                    "correlation": corr,
                    "volatility_similarity": vol_sim,
                    "rsi_similarity": rsi_sim,
                },
                metrics=metrics,
                reason=f"Corr {corr:.2f}, Vol sim {vol_sim:.2f}",
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def screen_by_news(
        self,
        keywords: list[str],
        universe: list[str] = None,
    ) -> list[ScreenerResult]:
        """Screen by recent news content (placeholder)."""
        # This would integrate with news sources
        logger.info(f"News screen for keywords: {keywords}")
        return []

    def get_daily_picks(self, n: int = 10) -> list[StockPick]:
        """
        Generate daily stock picks with full reasoning.

        Combines multiple screens and ranks by opportunity quality.
        """
        picks = []

        # Screen for different opportunities
        oversold = self.screen_by_pattern("bollinger_reversal")
        momentum = self.screen_by_pattern("momentum_breakout")
        value = self.screen_by_pattern("mean_reversion")
        trending = self.screen_by_pattern("trend_following")

        # Process oversold for long opportunities
        for r in oversold[:3]:
            picks.append(StockPick(
                rank=0,
                symbol=r.symbol,
                signal="buy",
                confidence=min(0.7, 0.4 + r.score * 0.3),
                timeframe_days=10,
                thesis=f"Oversold bounce opportunity - {r.reason}",
                supporting_factors=[
                    f"RSI at extreme low ({r.metrics.get('rsi_14', 'N/A'):.0f})",
                    f"Below Bollinger lower band",
                    f"Potential mean reversion",
                ],
                risk_factors=[
                    "Could continue lower in strong downtrend",
                    "May need catalyst for reversal",
                ],
                entry_price=r.metrics.get("current_price"),
                target_price=r.metrics.get("current_price", 0) * 1.08,
                stop_loss=r.metrics.get("current_price", 0) * 0.95,
            ))

        # Process momentum for trend continuation
        for r in momentum[:3]:
            picks.append(StockPick(
                rank=0,
                symbol=r.symbol,
                signal="buy",
                confidence=min(0.65, 0.35 + r.score * 0.3),
                timeframe_days=20,
                thesis=f"Momentum breakout - {r.reason}",
                supporting_factors=[
                    f"Strong 20-day return ({r.metrics.get('return_20d', 0)*100:.1f}%)",
                    f"Volume confirmation ({r.metrics.get('volume_ratio', 1):.1f}x)",
                    f"Above key moving averages",
                ],
                risk_factors=[
                    "Momentum may exhaust",
                    "High volatility expected",
                ],
                entry_price=r.metrics.get("current_price"),
                target_price=r.metrics.get("current_price", 0) * 1.15,
                stop_loss=r.metrics.get("current_price", 0) * 0.92,
            ))

        # Process value for longer-term opportunities
        for r in value[:2]:
            picks.append(StockPick(
                rank=0,
                symbol=r.symbol,
                signal="buy",
                confidence=min(0.55, 0.3 + r.score * 0.25),
                timeframe_days=60,
                thesis=f"Deep value / mean reversion - {r.reason}",
                supporting_factors=[
                    f"Down significantly from highs",
                    f"Technical indicators oversold",
                ],
                risk_factors=[
                    "May be value trap",
                    "Longer holding period required",
                ],
                entry_price=r.metrics.get("current_price"),
            ))

        # Score and rank all picks
        for i, pick in enumerate(picks):
            pick.rank = i + 1

        # Sort by confidence
        picks.sort(key=lambda p: p.confidence, reverse=True)

        # Re-rank
        for i, pick in enumerate(picks):
            pick.rank = i + 1

        return picks[:n]

    def generate_picks_report(self, picks: list[StockPick]) -> str:
        """Generate markdown report of stock picks."""
        lines = [
            "# Daily Stock Picks",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Total Picks: {len(picks)}",
            "",
        ]

        for pick in picks:
            lines.extend([
                f"## #{pick.rank} {pick.symbol} - {pick.signal.upper()}",
                f"**Confidence**: {pick.confidence:.0%} | **Timeframe**: {pick.timeframe_days} days",
                "",
                f"### Thesis",
                pick.thesis,
                "",
                "### Supporting Factors",
                *[f"- {f}" for f in pick.supporting_factors],
                "",
                "### Risk Factors",
                *[f"- {f}" for f in pick.risk_factors],
                "",
            ])

            if pick.entry_price:
                lines.append(f"**Entry**: ${pick.entry_price:.2f}")
            if pick.target_price:
                lines.append(f" | **Target**: ${pick.target_price:.2f}")
            if pick.stop_loss:
                lines.append(f" | **Stop**: ${pick.stop_loss:.2f}")

            lines.extend(["", "---", ""])

        return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_daily_picks(n: int = 10) -> list[StockPick]:
    """Quick access to daily stock picks."""
    screener = StockScreener()
    return screener.get_daily_picks(n)


def screen_oversold(universe: list[str] = None) -> list[ScreenerResult]:
    """Quick screen for oversold stocks."""
    screener = StockScreener(universe)
    return screener.screen_by_criteria({
        "rsi_14": "<30",
        "bb_position": "<0.2",
    })


def screen_momentum(universe: list[str] = None) -> list[ScreenerResult]:
    """Quick screen for momentum stocks."""
    screener = StockScreener(universe)
    return screener.screen_by_pattern("momentum_breakout")
