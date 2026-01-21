"""
Intraday Candle Analysis Module

Provides comprehensive candle pattern recognition and interpretation for:
- Day trading signal generation
- Agent/LLM context for trade decisions
- ML feature engineering

Supported timeframes: 1min, 5min, 15min, 30min, 1hr
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np


class CandlePattern(Enum):
    """Recognized candle patterns."""
    # Single candle patterns
    DOJI = "doji"
    SPINNING_TOP = "spinning_top"
    HAMMER = "hammer"
    INVERTED_HAMMER = "inverted_hammer"
    HANGING_MAN = "hanging_man"
    SHOOTING_STAR = "shooting_star"
    MARUBOZU_BULL = "marubozu_bull"
    MARUBOZU_BEAR = "marubozu_bear"

    # Two candle patterns
    BULLISH_ENGULFING = "bullish_engulfing"
    BEARISH_ENGULFING = "bearish_engulfing"
    BULLISH_HARAMI = "bullish_harami"
    BEARISH_HARAMI = "bearish_harami"
    TWEEZER_TOP = "tweezer_top"
    TWEEZER_BOTTOM = "tweezer_bottom"
    PIERCING_LINE = "piercing_line"
    DARK_CLOUD_COVER = "dark_cloud_cover"

    # Three candle patterns
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"
    THREE_WHITE_SOLDIERS = "three_white_soldiers"
    THREE_BLACK_CROWS = "three_black_crows"
    THREE_INSIDE_UP = "three_inside_up"
    THREE_INSIDE_DOWN = "three_inside_down"

    # Continuation patterns
    RISING_THREE = "rising_three"
    FALLING_THREE = "falling_three"

    # No pattern
    NONE = "none"


class PatternBias(Enum):
    """Pattern directional bias."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class PatternStrength(Enum):
    """Pattern strength/reliability."""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class CandleMetrics:
    """Metrics for a single candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    # Derived metrics
    body_size: float = 0.0
    upper_wick: float = 0.0
    lower_wick: float = 0.0
    range: float = 0.0
    body_pct: float = 0.0  # Body as % of range
    is_bullish: bool = False
    is_doji: bool = False

    # Relative metrics (vs recent candles)
    volume_ratio: float = 1.0  # vs 20-period avg
    range_ratio: float = 1.0  # vs 20-period avg ATR

    def __post_init__(self):
        self.range = self.high - self.low
        self.body_size = abs(self.close - self.open)
        self.is_bullish = self.close > self.open

        if self.is_bullish:
            self.upper_wick = self.high - self.close
            self.lower_wick = self.open - self.low
        else:
            self.upper_wick = self.high - self.open
            self.lower_wick = self.close - self.low

        self.body_pct = self.body_size / self.range if self.range > 0 else 0
        self.is_doji = self.body_pct < 0.1


@dataclass
class PatternMatch:
    """A detected candle pattern."""
    pattern: CandlePattern
    bias: PatternBias
    strength: PatternStrength
    confidence: float  # 0-1
    candles_used: int
    start_idx: int
    end_idx: int

    # Context
    price_at_signal: float
    volume_confirmation: bool
    trend_alignment: bool  # Pattern aligns with recent trend

    # Interpretation for agents
    interpretation: str = ""
    trading_implication: str = ""
    risk_note: str = ""


@dataclass
class CandleInterpretation:
    """
    Human/agent-readable interpretation of candle action.
    Designed to provide context for LLM-based trading decisions.
    """
    timestamp: datetime
    timeframe: str
    symbol: str

    # Current candle summary
    candle_type: str  # e.g., "strong bullish", "doji", "hammer"
    price_action: str  # Plain English description

    # Pattern detection
    patterns_detected: list[PatternMatch] = field(default_factory=list)
    primary_pattern: Optional[PatternMatch] = None

    # Multi-timeframe context
    trend_1min: str = "neutral"
    trend_5min: str = "neutral"
    trend_15min: str = "neutral"

    # Key levels interaction
    near_vwap: bool = False
    vwap_position: str = "at"  # "above", "below", "at"
    near_open_range: bool = False
    or_position: str = "within"  # "above", "below", "within"

    # Volume analysis
    volume_interpretation: str = ""
    is_climactic_volume: bool = False

    # Momentum
    momentum_state: str = "neutral"  # "accelerating", "decelerating", "neutral"

    # Summary for agents
    agent_summary: str = ""
    suggested_bias: PatternBias = PatternBias.NEUTRAL
    confidence_level: float = 0.5

    # ML features (numeric)
    ml_features: dict = field(default_factory=dict)


class CandlePatternRecognizer:
    """
    Recognizes candle patterns from OHLCV data.
    """

    def __init__(self, doji_threshold: float = 0.1, wick_ratio_threshold: float = 2.0):
        self.doji_threshold = doji_threshold
        self.wick_ratio_threshold = wick_ratio_threshold

    def analyze_candle(self, row: pd.Series, prev_candles: pd.DataFrame = None) -> CandleMetrics:
        """Analyze a single candle and compute metrics."""
        metrics = CandleMetrics(
            timestamp=row.name if isinstance(row.name, datetime) else datetime.now(),
            open=float(row['Open']),
            high=float(row['High']),
            low=float(row['Low']),
            close=float(row['Close']),
            volume=int(row['Volume']) if 'Volume' in row else 0,
        )

        # Calculate relative metrics if we have history
        if prev_candles is not None and len(prev_candles) >= 20:
            avg_volume = prev_candles['Volume'].tail(20).mean()
            if avg_volume > 0:
                metrics.volume_ratio = metrics.volume / avg_volume

            # ATR calculation
            tr = pd.concat([
                prev_candles['High'] - prev_candles['Low'],
                abs(prev_candles['High'] - prev_candles['Close'].shift(1)),
                abs(prev_candles['Low'] - prev_candles['Close'].shift(1))
            ], axis=1).max(axis=1)
            avg_tr = tr.tail(20).mean()
            if avg_tr > 0:
                metrics.range_ratio = metrics.range / avg_tr

        return metrics

    def detect_single_candle_pattern(self, candle: CandleMetrics) -> Optional[PatternMatch]:
        """Detect single-candle patterns."""

        # Doji
        if candle.is_doji:
            return PatternMatch(
                pattern=CandlePattern.DOJI,
                bias=PatternBias.NEUTRAL,
                strength=PatternStrength.MODERATE,
                confidence=0.7,
                candles_used=1,
                start_idx=0,
                end_idx=0,
                price_at_signal=candle.close,
                volume_confirmation=candle.volume_ratio > 1.5,
                trend_alignment=False,
                interpretation="Doji indicates indecision - buyers and sellers in equilibrium",
                trading_implication="Wait for confirmation candle before acting",
                risk_note="Doji at extremes can signal reversal"
            )

        # Hammer (bullish)
        if (candle.lower_wick > candle.body_size * self.wick_ratio_threshold and
            candle.upper_wick < candle.body_size * 0.5 and
            candle.body_pct < 0.4):
            return PatternMatch(
                pattern=CandlePattern.HAMMER,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.MODERATE,
                confidence=0.65,
                candles_used=1,
                start_idx=0,
                end_idx=0,
                price_at_signal=candle.close,
                volume_confirmation=candle.volume_ratio > 1.2,
                trend_alignment=False,
                interpretation="Hammer shows rejection of lower prices - bulls stepped in",
                trading_implication="Potential reversal signal, especially after downtrend",
                risk_note="Requires confirmation; invalid if next candle closes below hammer low"
            )

        # Shooting Star (bearish)
        if (candle.upper_wick > candle.body_size * self.wick_ratio_threshold and
            candle.lower_wick < candle.body_size * 0.5 and
            candle.body_pct < 0.4):
            return PatternMatch(
                pattern=CandlePattern.SHOOTING_STAR,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.MODERATE,
                confidence=0.65,
                candles_used=1,
                start_idx=0,
                end_idx=0,
                price_at_signal=candle.close,
                volume_confirmation=candle.volume_ratio > 1.2,
                trend_alignment=False,
                interpretation="Shooting star shows rejection of higher prices - sellers stepped in",
                trading_implication="Potential reversal signal, especially after uptrend",
                risk_note="Requires confirmation; invalid if next candle closes above shooting star high"
            )

        # Marubozu (strong trend candles)
        if candle.body_pct > 0.9:  # Body is 90%+ of range
            if candle.is_bullish:
                return PatternMatch(
                    pattern=CandlePattern.MARUBOZU_BULL,
                    bias=PatternBias.BULLISH,
                    strength=PatternStrength.STRONG,
                    confidence=0.75,
                    candles_used=1,
                    start_idx=0,
                    end_idx=0,
                    price_at_signal=candle.close,
                    volume_confirmation=candle.volume_ratio > 1.0,
                    trend_alignment=True,
                    interpretation="Bullish marubozu shows strong buying pressure with no hesitation",
                    trading_implication="Strong momentum - trend likely to continue",
                    risk_note="Extended moves often need consolidation"
                )
            else:
                return PatternMatch(
                    pattern=CandlePattern.MARUBOZU_BEAR,
                    bias=PatternBias.BEARISH,
                    strength=PatternStrength.STRONG,
                    confidence=0.75,
                    candles_used=1,
                    start_idx=0,
                    end_idx=0,
                    price_at_signal=candle.close,
                    volume_confirmation=candle.volume_ratio > 1.0,
                    trend_alignment=True,
                    interpretation="Bearish marubozu shows strong selling pressure with no hesitation",
                    trading_implication="Strong momentum - trend likely to continue",
                    risk_note="Extended moves often need consolidation"
                )

        # Spinning top
        if (candle.body_pct < 0.3 and
            candle.upper_wick > candle.body_size and
            candle.lower_wick > candle.body_size):
            return PatternMatch(
                pattern=CandlePattern.SPINNING_TOP,
                bias=PatternBias.NEUTRAL,
                strength=PatternStrength.WEAK,
                confidence=0.5,
                candles_used=1,
                start_idx=0,
                end_idx=0,
                price_at_signal=candle.close,
                volume_confirmation=False,
                trend_alignment=False,
                interpretation="Spinning top shows indecision with both buying and selling pressure",
                trading_implication="Market is undecided - wait for clearer signal",
                risk_note="Often appears before reversals but needs confirmation"
            )

        return None

    def detect_two_candle_pattern(self, candles: list[CandleMetrics]) -> Optional[PatternMatch]:
        """Detect two-candle patterns."""
        if len(candles) < 2:
            return None

        prev, curr = candles[-2], candles[-1]

        # Bullish Engulfing
        if (not prev.is_bullish and curr.is_bullish and
            curr.open < prev.close and curr.close > prev.open and
            curr.body_size > prev.body_size):
            return PatternMatch(
                pattern=CandlePattern.BULLISH_ENGULFING,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.STRONG,
                confidence=0.75,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio > 1.2,
                trend_alignment=False,
                interpretation="Bullish engulfing: buyers completely overwhelmed sellers",
                trading_implication="Strong reversal signal - consider long entry",
                risk_note="Stop below engulfing candle low"
            )

        # Bearish Engulfing
        if (prev.is_bullish and not curr.is_bullish and
            curr.open > prev.close and curr.close < prev.open and
            curr.body_size > prev.body_size):
            return PatternMatch(
                pattern=CandlePattern.BEARISH_ENGULFING,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.STRONG,
                confidence=0.75,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio > 1.2,
                trend_alignment=False,
                interpretation="Bearish engulfing: sellers completely overwhelmed buyers",
                trading_implication="Strong reversal signal - consider short entry or exit longs",
                risk_note="Stop above engulfing candle high"
            )

        # Bullish Harami
        if (not prev.is_bullish and curr.is_bullish and
            curr.open > prev.close and curr.close < prev.open and
            curr.body_size < prev.body_size * 0.5):
            return PatternMatch(
                pattern=CandlePattern.BULLISH_HARAMI,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.MODERATE,
                confidence=0.6,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio < 0.8,  # Lower volume expected
                trend_alignment=False,
                interpretation="Bullish harami: selling pressure waning, buyers emerging",
                trading_implication="Potential reversal - wait for confirmation",
                risk_note="Needs third candle confirmation to be reliable"
            )

        # Bearish Harami
        if (prev.is_bullish and not curr.is_bullish and
            curr.open < prev.close and curr.close > prev.open and
            curr.body_size < prev.body_size * 0.5):
            return PatternMatch(
                pattern=CandlePattern.BEARISH_HARAMI,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.MODERATE,
                confidence=0.6,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio < 0.8,
                trend_alignment=False,
                interpretation="Bearish harami: buying pressure waning, sellers emerging",
                trading_implication="Potential reversal - wait for confirmation",
                risk_note="Needs third candle confirmation to be reliable"
            )

        # Piercing Line
        if (not prev.is_bullish and curr.is_bullish and
            curr.open < prev.low and
            curr.close > (prev.open + prev.close) / 2 and
            curr.close < prev.open):
            return PatternMatch(
                pattern=CandlePattern.PIERCING_LINE,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.MODERATE,
                confidence=0.65,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio > 1.0,
                trend_alignment=False,
                interpretation="Piercing line: gap down reversed, bulls fighting back strongly",
                trading_implication="Reversal signal after downtrend",
                risk_note="More reliable at support levels"
            )

        # Dark Cloud Cover
        if (prev.is_bullish and not curr.is_bullish and
            curr.open > prev.high and
            curr.close < (prev.open + prev.close) / 2 and
            curr.close > prev.open):
            return PatternMatch(
                pattern=CandlePattern.DARK_CLOUD_COVER,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.MODERATE,
                confidence=0.65,
                candles_used=2,
                start_idx=-2,
                end_idx=-1,
                price_at_signal=curr.close,
                volume_confirmation=curr.volume_ratio > 1.0,
                trend_alignment=False,
                interpretation="Dark cloud cover: gap up reversed, bears fighting back strongly",
                trading_implication="Reversal signal after uptrend",
                risk_note="More reliable at resistance levels"
            )

        return None

    def detect_three_candle_pattern(self, candles: list[CandleMetrics]) -> Optional[PatternMatch]:
        """Detect three-candle patterns."""
        if len(candles) < 3:
            return None

        c1, c2, c3 = candles[-3], candles[-2], candles[-1]

        # Morning Star
        if (not c1.is_bullish and c1.body_pct > 0.5 and
            c2.body_pct < 0.3 and  # Small body (star)
            c3.is_bullish and c3.body_pct > 0.5 and
            c3.close > (c1.open + c1.close) / 2):
            return PatternMatch(
                pattern=CandlePattern.MORNING_STAR,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.STRONG,
                confidence=0.8,
                candles_used=3,
                start_idx=-3,
                end_idx=-1,
                price_at_signal=c3.close,
                volume_confirmation=c3.volume_ratio > 1.0,
                trend_alignment=False,
                interpretation="Morning star: classic bottom reversal - selling exhausted, buyers taking control",
                trading_implication="Strong buy signal, especially at support",
                risk_note="Stop below the star candle low"
            )

        # Evening Star
        if (c1.is_bullish and c1.body_pct > 0.5 and
            c2.body_pct < 0.3 and  # Small body (star)
            not c3.is_bullish and c3.body_pct > 0.5 and
            c3.close < (c1.open + c1.close) / 2):
            return PatternMatch(
                pattern=CandlePattern.EVENING_STAR,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.STRONG,
                confidence=0.8,
                candles_used=3,
                start_idx=-3,
                end_idx=-1,
                price_at_signal=c3.close,
                volume_confirmation=c3.volume_ratio > 1.0,
                trend_alignment=False,
                interpretation="Evening star: classic top reversal - buying exhausted, sellers taking control",
                trading_implication="Strong sell signal, especially at resistance",
                risk_note="Stop above the star candle high"
            )

        # Three White Soldiers
        if (c1.is_bullish and c2.is_bullish and c3.is_bullish and
            c1.body_pct > 0.6 and c2.body_pct > 0.6 and c3.body_pct > 0.6 and
            c2.open > c1.open and c2.close > c1.close and
            c3.open > c2.open and c3.close > c2.close):
            return PatternMatch(
                pattern=CandlePattern.THREE_WHITE_SOLDIERS,
                bias=PatternBias.BULLISH,
                strength=PatternStrength.STRONG,
                confidence=0.8,
                candles_used=3,
                start_idx=-3,
                end_idx=-1,
                price_at_signal=c3.close,
                volume_confirmation=True,
                trend_alignment=True,
                interpretation="Three white soldiers: sustained buying pressure, trend reversal confirmed",
                trading_implication="Strong bullish momentum - look for pullback entries",
                risk_note="Can be exhaustion if appears after extended move"
            )

        # Three Black Crows
        if (not c1.is_bullish and not c2.is_bullish and not c3.is_bullish and
            c1.body_pct > 0.6 and c2.body_pct > 0.6 and c3.body_pct > 0.6 and
            c2.open < c1.open and c2.close < c1.close and
            c3.open < c2.open and c3.close < c2.close):
            return PatternMatch(
                pattern=CandlePattern.THREE_BLACK_CROWS,
                bias=PatternBias.BEARISH,
                strength=PatternStrength.STRONG,
                confidence=0.8,
                candles_used=3,
                start_idx=-3,
                end_idx=-1,
                price_at_signal=c3.close,
                volume_confirmation=True,
                trend_alignment=True,
                interpretation="Three black crows: sustained selling pressure, trend reversal confirmed",
                trading_implication="Strong bearish momentum - avoid longs, look for shorts",
                risk_note="Can be exhaustion if appears after extended move"
            )

        return None

    def detect_all_patterns(self, df: pd.DataFrame, lookback: int = 20) -> list[PatternMatch]:
        """
        Detect all patterns in the dataframe.
        Returns patterns detected in the most recent candles.
        """
        if len(df) < 3:
            return []

        # Analyze recent candles
        candles = []
        for i in range(max(0, len(df) - lookback), len(df)):
            prev_data = df.iloc[:i] if i > 0 else None
            metrics = self.analyze_candle(df.iloc[i], prev_data)
            candles.append(metrics)

        patterns = []

        # Check latest candle for single patterns
        single = self.detect_single_candle_pattern(candles[-1])
        if single:
            patterns.append(single)

        # Check for two-candle patterns
        if len(candles) >= 2:
            two = self.detect_two_candle_pattern(candles[-2:])
            if two:
                patterns.append(two)

        # Check for three-candle patterns
        if len(candles) >= 3:
            three = self.detect_three_candle_pattern(candles[-3:])
            if three:
                patterns.append(three)

        return patterns


class CandleInterpreter:
    """
    Generates human/agent-readable interpretations of candle action.
    """

    def __init__(self):
        self.recognizer = CandlePatternRecognizer()

    def describe_candle(self, candle: CandleMetrics) -> str:
        """Generate plain English description of a candle."""

        # Size description
        if candle.range_ratio > 2:
            size = "very large"
        elif candle.range_ratio > 1.5:
            size = "large"
        elif candle.range_ratio < 0.5:
            size = "small"
        else:
            size = "normal-sized"

        # Direction
        if candle.is_doji:
            direction = "doji (indecision)"
        elif candle.is_bullish:
            if candle.body_pct > 0.8:
                direction = "strongly bullish"
            else:
                direction = "bullish"
        else:
            if candle.body_pct > 0.8:
                direction = "strongly bearish"
            else:
                direction = "bearish"

        # Wick analysis
        wick_desc = ""
        if candle.lower_wick > candle.body_size * 2:
            wick_desc = " with long lower wick (buying pressure)"
        elif candle.upper_wick > candle.body_size * 2:
            wick_desc = " with long upper wick (selling pressure)"
        elif candle.upper_wick > candle.body_size and candle.lower_wick > candle.body_size:
            wick_desc = " with wicks on both sides (indecision)"

        # Volume
        vol_desc = ""
        if candle.volume_ratio > 2:
            vol_desc = " on very high volume"
        elif candle.volume_ratio > 1.5:
            vol_desc = " on above-average volume"
        elif candle.volume_ratio < 0.5:
            vol_desc = " on low volume"

        return f"{size.capitalize()} {direction} candle{wick_desc}{vol_desc}"

    def interpret_price_action(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        vwap: Optional[float] = None,
        or_high: Optional[float] = None,
        or_low: Optional[float] = None,
    ) -> CandleInterpretation:
        """
        Generate comprehensive interpretation of recent price action.
        """
        if len(df) < 5:
            return CandleInterpretation(
                timestamp=datetime.now(),
                timeframe=timeframe,
                symbol=symbol,
                candle_type="insufficient data",
                price_action="Not enough candles for analysis",
            )

        # Analyze current candle
        current_candle = self.recognizer.analyze_candle(df.iloc[-1], df.iloc[:-1])

        # Detect patterns
        patterns = self.recognizer.detect_all_patterns(df)
        primary_pattern = patterns[0] if patterns else None

        # Determine trends
        trend_5 = self._calculate_trend(df.tail(5))
        trend_10 = self._calculate_trend(df.tail(10))
        trend_20 = self._calculate_trend(df.tail(20))

        # VWAP analysis
        current_price = float(df.iloc[-1]['Close'])
        near_vwap = False
        vwap_position = "unknown"
        if vwap:
            vwap_diff = (current_price - vwap) / vwap
            near_vwap = abs(vwap_diff) < 0.002  # Within 0.2%
            vwap_position = "above" if vwap_diff > 0.002 else "below" if vwap_diff < -0.002 else "at"

        # Opening range analysis
        near_or = False
        or_position = "unknown"
        if or_high and or_low:
            if current_price > or_high:
                or_position = "above"
                near_or = (current_price - or_high) / or_high < 0.003
            elif current_price < or_low:
                or_position = "below"
                near_or = (or_low - current_price) / or_low < 0.003
            else:
                or_position = "within"
                near_or = True

        # Volume interpretation
        vol_interp = self._interpret_volume(df)
        is_climactic = current_candle.volume_ratio > 3

        # Momentum state
        momentum = self._calculate_momentum_state(df)

        # Build interpretation
        interp = CandleInterpretation(
            timestamp=current_candle.timestamp,
            timeframe=timeframe,
            symbol=symbol,
            candle_type=self.describe_candle(current_candle),
            price_action=self._build_price_action_narrative(df, current_candle, patterns),
            patterns_detected=patterns,
            primary_pattern=primary_pattern,
            trend_1min=trend_5,  # Proxy for shorter trend
            trend_5min=trend_10,
            trend_15min=trend_20,
            near_vwap=near_vwap,
            vwap_position=vwap_position,
            near_open_range=near_or,
            or_position=or_position,
            volume_interpretation=vol_interp,
            is_climactic_volume=is_climactic,
            momentum_state=momentum,
        )

        # Generate agent summary
        interp.agent_summary = self._generate_agent_summary(interp, current_candle)
        interp.suggested_bias = self._determine_bias(interp, patterns)
        interp.confidence_level = self._calculate_confidence(interp, patterns)

        # Generate ML features
        interp.ml_features = self._generate_ml_features(df, current_candle, vwap, or_high, or_low)

        return interp

    def _calculate_trend(self, df: pd.DataFrame) -> str:
        """Calculate trend direction."""
        if len(df) < 2:
            return "neutral"

        closes = df['Close'].values
        pct_change = (closes[-1] - closes[0]) / closes[0]

        if pct_change > 0.005:
            return "bullish"
        elif pct_change < -0.005:
            return "bearish"
        return "neutral"

    def _interpret_volume(self, df: pd.DataFrame) -> str:
        """Interpret volume pattern."""
        if len(df) < 10:
            return "insufficient data"

        recent_vol = df['Volume'].tail(5).mean()
        avg_vol = df['Volume'].tail(20).mean()

        if avg_vol == 0:
            return "no volume data"

        ratio = recent_vol / avg_vol

        if ratio > 1.5:
            return "volume expanding - increased participation"
        elif ratio < 0.7:
            return "volume contracting - reduced interest"
        return "volume normal"

    def _calculate_momentum_state(self, df: pd.DataFrame) -> str:
        """Calculate momentum state."""
        if len(df) < 10:
            return "neutral"

        # Rate of change
        roc_5 = (df['Close'].iloc[-1] / df['Close'].iloc[-5] - 1) * 100
        roc_10 = (df['Close'].iloc[-1] / df['Close'].iloc[-10] - 1) * 100

        # Acceleration
        if abs(roc_5) > abs(roc_10 / 2):
            if roc_5 > 0:
                return "accelerating up"
            else:
                return "accelerating down"
        elif abs(roc_5) < abs(roc_10 / 3):
            return "decelerating"
        return "neutral"

    def _build_price_action_narrative(
        self,
        df: pd.DataFrame,
        current: CandleMetrics,
        patterns: list[PatternMatch]
    ) -> str:
        """Build narrative description of price action."""
        parts = []

        # Current candle description
        parts.append(f"Current candle is {self.describe_candle(current)}.")

        # Pattern description
        if patterns:
            pattern_names = [p.pattern.value.replace("_", " ") for p in patterns]
            parts.append(f"Detected patterns: {', '.join(pattern_names)}.")

        # Recent action
        if len(df) >= 5:
            high_5 = df['High'].tail(5).max()
            low_5 = df['Low'].tail(5).min()
            curr_close = float(df.iloc[-1]['Close'])

            if curr_close >= high_5 * 0.998:
                parts.append("Price at 5-period highs.")
            elif curr_close <= low_5 * 1.002:
                parts.append("Price at 5-period lows.")

        return " ".join(parts)

    def _generate_agent_summary(self, interp: CandleInterpretation, candle: CandleMetrics) -> str:
        """Generate concise summary for agent/LLM consumption."""
        parts = []

        # Candle type
        parts.append(f"{interp.symbol} {interp.timeframe}: {interp.candle_type}")

        # Pattern
        if interp.primary_pattern:
            p = interp.primary_pattern
            parts.append(f"Pattern: {p.pattern.value} ({p.bias.value}, {p.strength.value})")
            parts.append(f"→ {p.interpretation}")

        # Key levels
        levels = []
        if interp.vwap_position != "unknown":
            levels.append(f"VWAP: {interp.vwap_position}")
        if interp.or_position != "unknown":
            levels.append(f"OR: {interp.or_position}")
        if levels:
            parts.append(f"Levels: {', '.join(levels)}")

        # Volume
        if interp.is_climactic_volume:
            parts.append("⚠️ CLIMACTIC VOLUME")
        elif "expanding" in interp.volume_interpretation:
            parts.append("Volume expanding")

        # Momentum
        if "accelerating" in interp.momentum_state:
            parts.append(f"Momentum {interp.momentum_state}")

        return " | ".join(parts)

    def _determine_bias(self, interp: CandleInterpretation, patterns: list[PatternMatch]) -> PatternBias:
        """Determine overall bias from interpretation."""
        if not patterns:
            # Use trends
            bullish_trends = sum(1 for t in [interp.trend_1min, interp.trend_5min, interp.trend_15min] if t == "bullish")
            bearish_trends = sum(1 for t in [interp.trend_1min, interp.trend_5min, interp.trend_15min] if t == "bearish")

            if bullish_trends >= 2:
                return PatternBias.BULLISH
            elif bearish_trends >= 2:
                return PatternBias.BEARISH
            return PatternBias.NEUTRAL

        # Use strongest pattern
        strong_patterns = [p for p in patterns if p.strength == PatternStrength.STRONG]
        if strong_patterns:
            return strong_patterns[0].bias

        return patterns[0].bias

    def _calculate_confidence(self, interp: CandleInterpretation, patterns: list[PatternMatch]) -> float:
        """Calculate confidence level 0-1."""
        confidence = 0.5  # Base

        # Pattern confidence
        if patterns:
            pattern_conf = max(p.confidence for p in patterns)
            confidence = pattern_conf

        # Trend alignment bonus
        trends = [interp.trend_1min, interp.trend_5min, interp.trend_15min]
        if len(set(trends)) == 1 and trends[0] != "neutral":
            confidence += 0.1

        # Volume confirmation
        if interp.is_climactic_volume:
            confidence += 0.05

        # Key level bonus
        if interp.near_vwap or interp.near_open_range:
            confidence += 0.05

        return min(0.95, confidence)

    def _generate_ml_features(
        self,
        df: pd.DataFrame,
        candle: CandleMetrics,
        vwap: Optional[float],
        or_high: Optional[float],
        or_low: Optional[float]
    ) -> dict:
        """Generate numeric features for ML models."""
        features = {
            # Candle features
            "body_pct": candle.body_pct,
            "upper_wick_ratio": candle.upper_wick / candle.range if candle.range > 0 else 0,
            "lower_wick_ratio": candle.lower_wick / candle.range if candle.range > 0 else 0,
            "is_bullish": 1 if candle.is_bullish else 0,
            "is_doji": 1 if candle.is_doji else 0,
            "volume_ratio": candle.volume_ratio,
            "range_ratio": candle.range_ratio,

            # Price action features
            "close_vs_high": (candle.close - candle.low) / candle.range if candle.range > 0 else 0.5,
        }

        # VWAP features
        if vwap and vwap > 0:
            features["vwap_distance"] = (candle.close - vwap) / vwap
        else:
            features["vwap_distance"] = 0

        # Opening range features
        if or_high and or_low and or_high > or_low:
            or_range = or_high - or_low
            features["or_position"] = (candle.close - or_low) / or_range
            features["or_breakout_up"] = 1 if candle.close > or_high else 0
            features["or_breakout_down"] = 1 if candle.close < or_low else 0
        else:
            features["or_position"] = 0.5
            features["or_breakout_up"] = 0
            features["or_breakout_down"] = 0

        # Trend features from recent candles
        if len(df) >= 5:
            features["roc_5"] = (df['Close'].iloc[-1] / df['Close'].iloc[-5] - 1) * 100
            features["high_5_dist"] = (df['Close'].iloc[-1] - df['High'].tail(5).max()) / df['Close'].iloc[-1]
            features["low_5_dist"] = (df['Close'].iloc[-1] - df['Low'].tail(5).min()) / df['Close'].iloc[-1]

        return features
