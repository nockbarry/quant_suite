"""Enhanced intraday technical analysis.

Provides comprehensive technical analysis beyond basic indicators:
- Support/resistance level detection
- Candlestick pattern recognition
- Multi-timeframe analysis
- Trend detection with higher highs/lower lows
- Volume profile analysis
- VWAP relationship tracking

Usage:
    from src.data.pipeline.intraday_technicals import IntradayTechnicalAnalyzer

    analyzer = IntradayTechnicalAnalyzer(["SLB", "HAL", "XLE"])
    technicals = analyzer.get_technicals("SLB")
    print(technicals.get_summary())
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from .intraday import compute_intraday_indicators, get_session_data

logger = logging.getLogger(__name__)


@dataclass
class IntradayTechnicals:
    """Complete intraday technical analysis for a symbol."""

    symbol: str
    timestamp: datetime

    # Price Data
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    change_pct: float

    # Volume Analysis
    volume: int
    avg_volume_20d: int
    volume_ratio: float
    cumulative_volume: int

    # VWAP
    vwap: float
    price_vs_vwap: float
    vwap_position: str  # "above", "below", "at"

    # Trend Analysis
    trend_1h: str  # "uptrend", "downtrend", "ranging"
    trend_4h: str
    higher_highs: bool
    lower_lows: bool
    trend_strength: float  # 0-1

    # Support/Resistance
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    support_distance: float = 0.0
    resistance_distance: float = 0.0
    support_tests_today: int = 0

    # Candlestick Patterns
    patterns: list[str] = field(default_factory=list)
    reversal_signal: bool = False
    continuation_signal: bool = False

    # Moving Averages
    ema_9: float = 0.0
    ema_21: float = 0.0
    sma_50: float = 0.0
    ma_alignment: str = "mixed"  # "bullish", "bearish", "mixed"

    # Momentum
    rsi_14: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    momentum_bias: str = "neutral"  # "bullish", "bearish", "neutral"

    # Range Analysis
    atr_14: float = 0.0
    todays_range: float = 0.0
    range_pct_of_atr: float = 0.0

    # Pivot Points
    pivot: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    s1: float = 0.0
    s2: float = 0.0

    # Summary
    bias: str = "neutral"  # "bullish", "bearish", "neutral"
    strength: str = "moderate"  # "strong", "moderate", "weak"
    action_signal: str = "hold"  # "buy", "sell", "hold", "watch"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "price": {
                "current": self.price,
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "prev_close": self.prev_close,
                "change_pct": self.change_pct,
            },
            "volume": {
                "current": self.volume,
                "avg_20d": self.avg_volume_20d,
                "ratio": self.volume_ratio,
                "cumulative": self.cumulative_volume,
            },
            "vwap": {
                "value": self.vwap,
                "vs_price": self.price_vs_vwap,
                "position": self.vwap_position,
            },
            "trend": {
                "trend_1h": self.trend_1h,
                "trend_4h": self.trend_4h,
                "higher_highs": self.higher_highs,
                "lower_lows": self.lower_lows,
                "strength": self.trend_strength,
            },
            "levels": {
                "support": self.support_levels,
                "resistance": self.resistance_levels,
                "nearest_support": self.nearest_support,
                "nearest_resistance": self.nearest_resistance,
                "support_distance": self.support_distance,
                "resistance_distance": self.resistance_distance,
                "support_tests": self.support_tests_today,
            },
            "patterns": {
                "detected": self.patterns,
                "reversal_signal": self.reversal_signal,
                "continuation_signal": self.continuation_signal,
            },
            "moving_averages": {
                "ema_9": self.ema_9,
                "ema_21": self.ema_21,
                "sma_50": self.sma_50,
                "alignment": self.ma_alignment,
            },
            "momentum": {
                "rsi_14": self.rsi_14,
                "macd": self.macd,
                "macd_signal": self.macd_signal,
                "macd_histogram": self.macd_histogram,
                "bias": self.momentum_bias,
            },
            "range": {
                "atr_14": self.atr_14,
                "todays_range": self.todays_range,
                "range_pct_of_atr": self.range_pct_of_atr,
            },
            "pivots": {
                "pivot": self.pivot,
                "r1": self.r1,
                "r2": self.r2,
                "s1": self.s1,
                "s2": self.s2,
            },
            "summary": {
                "bias": self.bias,
                "strength": self.strength,
                "action": self.action_signal,
                "notes": self.notes,
            },
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"{self.symbol} Technical Summary ({self.timestamp.strftime('%H:%M ET')})",
            "=" * 50,
            f"  Price: ${self.price:.2f} ({self.change_pct:+.2f}%)",
            f"  VWAP: ${self.vwap:.2f} ({self.vwap_position}, ${self.price_vs_vwap:+.2f})",
            f"  Volume: {self.volume_ratio:.1f}x avg",
            "",
            f"  Trend: {self.trend_1h} (1h), {self.trend_4h} (4h)",
            f"  Trend Strength: {self.trend_strength:.0%}",
            "",
            f"  RSI: {self.rsi_14:.0f} | MACD Hist: {self.macd_histogram:+.3f}",
            f"  Momentum: {self.momentum_bias}",
            "",
        ]

        if self.support_levels:
            lines.append(f"  Support: ${self.nearest_support:.2f} (${self.support_distance:.2f} away)")
        if self.resistance_levels:
            lines.append(f"  Resistance: ${self.nearest_resistance:.2f} (${self.resistance_distance:.2f} away)")

        if self.patterns:
            lines.append(f"\n  Patterns: {', '.join(self.patterns)}")

        lines.extend([
            "",
            f"  Bias: {self.bias.upper()} | Strength: {self.strength}",
            f"  Action: {self.action_signal.upper()}",
        ])

        if self.notes:
            lines.append(f"\n  Notes: {'; '.join(self.notes)}")

        return "\n".join(lines)


@dataclass
class MultiTimeframeTechnicals:
    """Aligned analysis across timeframes."""

    symbol: str
    tf_1m: IntradayTechnicals | None
    tf_5m: IntradayTechnicals | None
    tf_15m: IntradayTechnicals | None
    alignment: str  # "aligned_bullish", "aligned_bearish", "mixed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframes": {
                "1m": self.tf_1m.to_dict() if self.tf_1m else None,
                "5m": self.tf_5m.to_dict() if self.tf_5m else None,
                "15m": self.tf_15m.to_dict() if self.tf_15m else None,
            },
            "alignment": self.alignment,
        }


class IntradayTechnicalAnalyzer:
    """
    Comprehensive intraday technical analyzer.

    Features:
    - Multi-timeframe analysis
    - Support/resistance detection
    - Candlestick pattern recognition
    - Trend analysis with swing detection
    - Volume profile
    """

    # Candlestick pattern definitions
    BULLISH_PATTERNS = ["hammer", "bullish_engulfing", "morning_star", "piercing_line", "three_white_soldiers"]
    BEARISH_PATTERNS = ["shooting_star", "bearish_engulfing", "evening_star", "dark_cloud_cover", "three_black_crows"]
    NEUTRAL_PATTERNS = ["doji", "spinning_top"]

    def __init__(self, symbols: list[str]):
        """
        Initialize analyzer.

        Args:
            symbols: List of symbols to analyze
        """
        self.symbols = symbols
        self._data_cache: dict[str, dict[str, pd.DataFrame]] = {}
        self._cache_time: dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def refresh_data(self, symbol: str) -> None:
        """Refresh cached data for a symbol."""
        try:
            ticker = yf.Ticker(symbol)

            # Fetch multiple timeframes
            data = {}

            # 1-minute bars (last 7 days max)
            hist_1m = ticker.history(period="5d", interval="1m")
            if not hist_1m.empty:
                hist_1m.columns = hist_1m.columns.str.lower()
                data["1m"] = get_session_data(hist_1m)

            # 5-minute bars
            hist_5m = ticker.history(period="30d", interval="5m")
            if not hist_5m.empty:
                hist_5m.columns = hist_5m.columns.str.lower()
                data["5m"] = get_session_data(hist_5m)

            # 15-minute bars
            hist_15m = ticker.history(period="60d", interval="15m")
            if not hist_15m.empty:
                hist_15m.columns = hist_15m.columns.str.lower()
                data["15m"] = get_session_data(hist_15m)

            self._data_cache[symbol] = data
            self._cache_time[symbol] = datetime.now()

        except Exception as e:
            logger.error(f"Failed to refresh data for {symbol}: {e}")

    def _needs_refresh(self, symbol: str) -> bool:
        """Check if data needs refresh."""
        if symbol not in self._cache_time:
            return True
        return datetime.now() - self._cache_time[symbol] > self._cache_ttl

    def get_technicals(self, symbol: str, timeframe: str = "5m") -> IntradayTechnicals:
        """
        Get technical analysis for a symbol.

        Args:
            symbol: Stock symbol
            timeframe: "1m", "5m", or "15m"

        Returns:
            IntradayTechnicals object
        """
        # Ensure we have data
        if symbol not in self._data_cache or timeframe not in self._data_cache.get(symbol, {}):
            # Synchronous fallback
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't await in running loop, use thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(lambda: asyncio.run(self.refresh_data(symbol))).result()
                else:
                    loop.run_until_complete(self.refresh_data(symbol))
            except Exception:
                asyncio.run(self.refresh_data(symbol))

        df = self._data_cache.get(symbol, {}).get(timeframe, pd.DataFrame())

        if df.empty:
            return self._empty_technicals(symbol)

        # Compute indicators
        df = compute_intraday_indicators(df)

        return self._analyze(symbol, df, timeframe)

    def _analyze(self, symbol: str, df: pd.DataFrame, timeframe: str) -> IntradayTechnicals:
        """Perform full technical analysis."""
        if df.empty:
            return self._empty_technicals(symbol)

        # Get basic data
        latest = df.iloc[-1]
        today = date.today()
        today_data = df[df.index.date == today]

        # Price data
        price = float(latest["close"])
        open_price = float(today_data["open"].iloc[0]) if not today_data.empty else price
        high = float(today_data["high"].max()) if not today_data.empty else price
        low = float(today_data["low"].min()) if not today_data.empty else price

        # Get previous close
        prev_day = df[df.index.date < today]
        prev_close = float(prev_day["close"].iloc[-1]) if not prev_day.empty else open_price

        change_pct = ((price / prev_close) - 1) * 100 if prev_close > 0 else 0

        # Volume
        volume = int(today_data["volume"].sum()) if not today_data.empty else 0
        avg_volume = int(df["volume"].mean()) if len(df) > 0 else 1
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        cumulative_volume = volume

        # VWAP
        vwap = float(latest.get("vwap", price))
        price_vs_vwap = price - vwap
        vwap_position = "above" if price > vwap else "below" if price < vwap else "at"

        # Trend analysis
        trend_1h, trend_4h = self._analyze_trend(df, timeframe)
        higher_highs, lower_lows = self._detect_swing_pattern(df)
        trend_strength = self._calculate_trend_strength(df)

        # Support/Resistance
        support_levels, resistance_levels = self._find_levels(df, price)
        nearest_support = max([s for s in support_levels if s < price], default=0)
        nearest_resistance = min([r for r in resistance_levels if r > price], default=0)
        support_distance = price - nearest_support if nearest_support > 0 else 0
        resistance_distance = nearest_resistance - price if nearest_resistance > 0 else 0
        support_tests = self._count_support_tests(today_data, nearest_support) if nearest_support > 0 else 0

        # Candlestick patterns
        patterns = self._detect_patterns(df)
        reversal_signal = any(p in self.BULLISH_PATTERNS + self.BEARISH_PATTERNS for p in patterns)
        continuation_signal = any(p.startswith("three_") for p in patterns)

        # Moving averages
        ema_9 = float(latest.get("ema_9", price))
        ema_21 = float(latest.get("ema_21", price))
        sma_50 = float(df["close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else price
        ma_alignment = self._determine_ma_alignment(price, ema_9, ema_21, sma_50)

        # Momentum
        rsi_14 = float(latest.get("rsi", 50))
        macd, macd_signal, macd_hist = self._calculate_macd(df)
        momentum_bias = self._determine_momentum_bias(rsi_14, macd_hist)

        # Range analysis
        atr_14 = float(latest.get("atr", 0))
        todays_range = high - low
        range_pct_of_atr = (todays_range / atr_14 * 100) if atr_14 > 0 else 0

        # Pivot points
        pivot, r1, r2, s1, s2 = self._calculate_pivots(prev_day)

        # Generate summary
        bias = self._determine_overall_bias(trend_1h, momentum_bias, ma_alignment, vwap_position)
        strength = self._determine_strength(trend_strength, volume_ratio, abs(change_pct))
        action_signal = self._determine_action(bias, strength, rsi_14, patterns)
        notes = self._generate_notes(
            vwap_position, volume_ratio, rsi_14, patterns,
            support_distance, resistance_distance, support_tests
        )

        return IntradayTechnicals(
            symbol=symbol,
            timestamp=datetime.now(),
            price=price,
            open=open_price,
            high=high,
            low=low,
            prev_close=prev_close,
            change_pct=change_pct,
            volume=volume,
            avg_volume_20d=avg_volume,
            volume_ratio=volume_ratio,
            cumulative_volume=cumulative_volume,
            vwap=vwap,
            price_vs_vwap=price_vs_vwap,
            vwap_position=vwap_position,
            trend_1h=trend_1h,
            trend_4h=trend_4h,
            higher_highs=higher_highs,
            lower_lows=lower_lows,
            trend_strength=trend_strength,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            support_distance=support_distance,
            resistance_distance=resistance_distance,
            support_tests_today=support_tests,
            patterns=patterns,
            reversal_signal=reversal_signal,
            continuation_signal=continuation_signal,
            ema_9=ema_9,
            ema_21=ema_21,
            sma_50=sma_50,
            ma_alignment=ma_alignment,
            rsi_14=rsi_14,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            momentum_bias=momentum_bias,
            atr_14=atr_14,
            todays_range=todays_range,
            range_pct_of_atr=range_pct_of_atr,
            pivot=pivot,
            r1=r1,
            r2=r2,
            s1=s1,
            s2=s2,
            bias=bias,
            strength=strength,
            action_signal=action_signal,
            notes=notes,
        )

    def _empty_technicals(self, symbol: str) -> IntradayTechnicals:
        """Return empty technicals object."""
        return IntradayTechnicals(
            symbol=symbol,
            timestamp=datetime.now(),
            price=0,
            open=0,
            high=0,
            low=0,
            prev_close=0,
            change_pct=0,
            volume=0,
            avg_volume_20d=0,
            volume_ratio=0,
            cumulative_volume=0,
            vwap=0,
            price_vs_vwap=0,
            vwap_position="unknown",
            trend_1h="unknown",
            trend_4h="unknown",
            higher_highs=False,
            lower_lows=False,
            trend_strength=0,
            notes=["No data available"],
        )

    def _analyze_trend(self, df: pd.DataFrame, timeframe: str) -> tuple[str, str]:
        """Analyze trend over different periods."""
        if len(df) < 20:
            return "unknown", "unknown"

        # 1-hour trend (based on last ~12 bars for 5m)
        bars_1h = {"1m": 60, "5m": 12, "15m": 4}.get(timeframe, 12)
        recent_1h = df.tail(bars_1h)

        # 4-hour trend (based on last ~48 bars for 5m)
        bars_4h = {"1m": 240, "5m": 48, "15m": 16}.get(timeframe, 48)
        recent_4h = df.tail(min(bars_4h, len(df)))

        def classify_trend(data: pd.DataFrame) -> str:
            if len(data) < 3:
                return "unknown"

            ema = data["close"].ewm(span=len(data)//2 or 1).mean()
            price = data["close"].iloc[-1]

            slope = (ema.iloc[-1] - ema.iloc[0]) / len(ema) if len(ema) > 1 else 0
            above_ema = price > ema.iloc[-1]

            if slope > 0.01 and above_ema:
                return "uptrend"
            elif slope < -0.01 and not above_ema:
                return "downtrend"
            else:
                return "ranging"

        return classify_trend(recent_1h), classify_trend(recent_4h)

    def _detect_swing_pattern(self, df: pd.DataFrame) -> tuple[bool, bool]:
        """Detect higher highs / lower lows pattern."""
        if len(df) < 20:
            return False, False

        # Get swing highs and lows
        highs = df["high"].rolling(5, center=True).max() == df["high"]
        lows = df["low"].rolling(5, center=True).min() == df["low"]

        swing_highs = df.loc[highs, "high"].tail(3)
        swing_lows = df.loc[lows, "low"].tail(3)

        higher_highs = len(swing_highs) >= 2 and swing_highs.is_monotonic_increasing
        lower_lows = len(swing_lows) >= 2 and swing_lows.is_monotonic_decreasing

        return higher_highs, lower_lows

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """Calculate trend strength (0-1)."""
        if len(df) < 20:
            return 0.5

        # Use ADX-like calculation
        tr = pd.concat([
            df["high"] - df["low"],
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()

        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        plus_di = 100 * (plus_dm.rolling(14).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr.replace(0, np.nan))

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()

        strength = float(adx.iloc[-1]) / 100 if not pd.isna(adx.iloc[-1]) else 0.5
        return min(1.0, max(0.0, strength))

    def _find_levels(self, df: pd.DataFrame, current_price: float) -> tuple[list[float], list[float]]:
        """Find support and resistance levels using price clustering."""
        if len(df) < 20:
            return [], []

        # Use pivot highs and lows
        highs = df["high"].rolling(5, center=True).max() == df["high"]
        lows = df["low"].rolling(5, center=True).min() == df["low"]

        pivot_highs = df.loc[highs, "high"].unique()
        pivot_lows = df.loc[lows, "low"].unique()

        # Cluster nearby levels (within 0.5%)
        def cluster_levels(levels: np.ndarray, threshold: float = 0.005) -> list[float]:
            if len(levels) == 0:
                return []

            sorted_levels = sorted(levels)
            clusters = []
            current_cluster = [sorted_levels[0]]

            for level in sorted_levels[1:]:
                if (level - current_cluster[-1]) / current_cluster[-1] < threshold:
                    current_cluster.append(level)
                else:
                    clusters.append(np.mean(current_cluster))
                    current_cluster = [level]

            clusters.append(np.mean(current_cluster))
            return [round(c, 2) for c in clusters]

        resistance = [r for r in cluster_levels(pivot_highs) if r > current_price][:3]
        support = [s for s in cluster_levels(pivot_lows) if s < current_price][-3:]

        return support, resistance

    def _count_support_tests(self, df: pd.DataFrame, support: float, tolerance: float = 0.005) -> int:
        """Count how many times price tested a support level."""
        if df.empty or support == 0:
            return 0

        lower_bound = support * (1 - tolerance)
        upper_bound = support * (1 + tolerance)

        tests = ((df["low"] >= lower_bound) & (df["low"] <= upper_bound)).sum()
        return int(tests)

    def _detect_patterns(self, df: pd.DataFrame) -> list[str]:
        """Detect candlestick patterns in recent bars."""
        if len(df) < 3:
            return []

        patterns = []
        last_3 = df.tail(3)

        for i, row in last_3.iterrows():
            open_price = row["open"]
            close = row["close"]
            high = row["high"]
            low = row["low"]

            body = abs(close - open_price)
            upper_shadow = high - max(open_price, close)
            lower_shadow = min(open_price, close) - low
            total_range = high - low

            if total_range == 0:
                continue

            body_pct = body / total_range
            upper_pct = upper_shadow / total_range
            lower_pct = lower_shadow / total_range

            # Doji
            if body_pct < 0.1:
                patterns.append("doji")

            # Hammer (bullish)
            elif lower_pct > 0.6 and body_pct < 0.3 and close > open_price:
                patterns.append("hammer")

            # Shooting star (bearish)
            elif upper_pct > 0.6 and body_pct < 0.3 and close < open_price:
                patterns.append("shooting_star")

            # Spinning top
            elif body_pct < 0.3 and upper_pct > 0.3 and lower_pct > 0.3:
                patterns.append("spinning_top")

        # Multi-bar patterns
        if len(last_3) >= 2:
            prev = last_3.iloc[-2]
            curr = last_3.iloc[-1]

            # Bullish engulfing
            if (prev["close"] < prev["open"] and
                curr["close"] > curr["open"] and
                curr["open"] < prev["close"] and
                curr["close"] > prev["open"]):
                patterns.append("bullish_engulfing")

            # Bearish engulfing
            elif (prev["close"] > prev["open"] and
                  curr["close"] < curr["open"] and
                  curr["open"] > prev["close"] and
                  curr["close"] < prev["open"]):
                patterns.append("bearish_engulfing")

        return list(set(patterns))  # Remove duplicates

    def _calculate_macd(self, df: pd.DataFrame) -> tuple[float, float, float]:
        """Calculate MACD indicator."""
        if len(df) < 26:
            return 0, 0, 0

        close = df["close"]
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        histogram = macd - signal

        return float(macd.iloc[-1]), float(signal.iloc[-1]), float(histogram.iloc[-1])

    def _determine_ma_alignment(self, price: float, ema_9: float, ema_21: float, sma_50: float) -> str:
        """Determine moving average alignment."""
        if price > ema_9 > ema_21 > sma_50:
            return "bullish"
        elif price < ema_9 < ema_21 < sma_50:
            return "bearish"
        else:
            return "mixed"

    def _determine_momentum_bias(self, rsi: float, macd_hist: float) -> str:
        """Determine momentum bias."""
        if rsi > 60 and macd_hist > 0:
            return "bullish"
        elif rsi < 40 and macd_hist < 0:
            return "bearish"
        else:
            return "neutral"

    def _calculate_pivots(self, prev_day: pd.DataFrame) -> tuple[float, float, float, float, float]:
        """Calculate pivot points from previous day."""
        if prev_day.empty:
            return 0, 0, 0, 0, 0

        high = prev_day["high"].max()
        low = prev_day["low"].min()
        close = prev_day["close"].iloc[-1]

        pivot = (high + low + close) / 3
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)

        return float(pivot), float(r1), float(r2), float(s1), float(s2)

    def _determine_overall_bias(self, trend: str, momentum: str, ma_alignment: str, vwap: str) -> str:
        """Determine overall bias from multiple factors."""
        bullish = 0
        bearish = 0

        if trend == "uptrend":
            bullish += 1
        elif trend == "downtrend":
            bearish += 1

        if momentum == "bullish":
            bullish += 1
        elif momentum == "bearish":
            bearish += 1

        if ma_alignment == "bullish":
            bullish += 1
        elif ma_alignment == "bearish":
            bearish += 1

        if vwap == "above":
            bullish += 1
        elif vwap == "below":
            bearish += 1

        if bullish > bearish + 1:
            return "bullish"
        elif bearish > bullish + 1:
            return "bearish"
        else:
            return "neutral"

    def _determine_strength(self, trend_strength: float, volume_ratio: float, change_pct: float) -> str:
        """Determine signal strength."""
        score = trend_strength * 0.4 + min(volume_ratio, 2) / 2 * 0.3 + min(abs(change_pct), 3) / 3 * 0.3

        if score > 0.7:
            return "strong"
        elif score > 0.4:
            return "moderate"
        else:
            return "weak"

    def _determine_action(self, bias: str, strength: str, rsi: float, patterns: list[str]) -> str:
        """Determine suggested action."""
        # Oversold/overbought override
        if rsi < 30:
            return "watch"  # Potential bounce
        elif rsi > 70:
            return "watch"  # Potential pullback

        # Pattern-based
        if any(p in self.BULLISH_PATTERNS for p in patterns) and bias != "bearish":
            return "buy"
        elif any(p in self.BEARISH_PATTERNS for p in patterns) and bias != "bullish":
            return "sell"

        # Trend-based
        if bias == "bullish" and strength == "strong":
            return "buy"
        elif bias == "bearish" and strength == "strong":
            return "sell"
        else:
            return "hold"

    def _generate_notes(
        self,
        vwap_position: str,
        volume_ratio: float,
        rsi: float,
        patterns: list[str],
        support_distance: float,
        resistance_distance: float,
        support_tests: int,
    ) -> list[str]:
        """Generate human-readable notes."""
        notes = []

        if vwap_position == "below":
            notes.append("Trading below VWAP (bearish)")
        elif vwap_position == "above":
            notes.append("Trading above VWAP (bullish)")

        if volume_ratio > 1.5:
            notes.append(f"Elevated volume ({volume_ratio:.1f}x avg)")
        elif volume_ratio < 0.5:
            notes.append("Low volume, watch for breakout")

        if rsi < 30:
            notes.append("RSI oversold - potential bounce")
        elif rsi > 70:
            notes.append("RSI overbought - potential pullback")

        if patterns:
            notes.append(f"Patterns detected: {', '.join(patterns)}")

        if support_tests >= 2:
            notes.append(f"Support tested {support_tests}x - watch for break")

        if support_distance > 0 and support_distance < 0.5:
            notes.append(f"Very close to support (${support_distance:.2f})")

        return notes

    def get_multi_timeframe(self, symbol: str) -> MultiTimeframeTechnicals:
        """Get analysis across multiple timeframes."""
        tf_1m = self.get_technicals(symbol, "1m")
        tf_5m = self.get_technicals(symbol, "5m")
        tf_15m = self.get_technicals(symbol, "15m")

        # Determine alignment
        biases = [tf_1m.bias, tf_5m.bias, tf_15m.bias]
        bullish_count = biases.count("bullish")
        bearish_count = biases.count("bearish")

        if bullish_count >= 2:
            alignment = "aligned_bullish"
        elif bearish_count >= 2:
            alignment = "aligned_bearish"
        else:
            alignment = "mixed"

        return MultiTimeframeTechnicals(
            symbol=symbol,
            tf_1m=tf_1m,
            tf_5m=tf_5m,
            tf_15m=tf_15m,
            alignment=alignment,
        )

    def get_all(self, timeframe: str = "5m") -> dict[str, IntradayTechnicals]:
        """Get technicals for all watched symbols."""
        return {symbol: self.get_technicals(symbol, timeframe) for symbol in self.symbols}

    def detect_patterns(self, symbol: str) -> list[str]:
        """Get detected patterns for a symbol."""
        technicals = self.get_technicals(symbol)
        return technicals.patterns

    def find_levels(self, symbol: str) -> dict[str, list[float]]:
        """Get support/resistance levels for a symbol."""
        technicals = self.get_technicals(symbol)
        return {
            "support": technicals.support_levels,
            "resistance": technicals.resistance_levels,
        }

    def get_summary(self, symbol: str) -> str:
        """Get human-readable summary for a symbol."""
        return self.get_technicals(symbol).get_summary()
