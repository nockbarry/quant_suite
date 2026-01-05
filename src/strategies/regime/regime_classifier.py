"""
Market Regime Classifier.

Classifies current market regime using multiple signals including
volatility, trend strength, correlation, and sentiment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import numpy as np
import pandas as pd


class MarketRegime(Enum):
    """Market regime classifications."""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    RANGE_BOUND = "range_bound"
    TRENDING = "trending"
    ROTATION = "rotation"
    MIXED = "mixed"


@dataclass
class RegimeIndicators:
    """Raw indicators used for regime classification."""
    vix: float
    vix_percentile: float
    realized_vol: float
    vrp: float  # Volatility Risk Premium (IV - RV)
    adx: float
    trend_direction: int  # 1=bullish, -1=bearish, 0=mixed
    avg_correlation: float
    put_call_ratio: float | None
    breadth: float | None  # % stocks above 50MA
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RegimeState:
    """Current regime state with confidence and recommendations."""
    regime: MarketRegime
    confidence: float
    indicators: RegimeIndicators
    recommended_strategies: list[str]
    avoid_strategies: list[str]
    reasoning: list[str]
    transition_signals: list[str]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "recommended_strategies": self.recommended_strategies,
            "avoid_strategies": self.avoid_strategies,
            "reasoning": self.reasoning,
            "indicators": {
                "vix": self.indicators.vix,
                "vix_percentile": self.indicators.vix_percentile,
                "adx": self.indicators.adx,
                "trend_direction": self.indicators.trend_direction,
                "avg_correlation": self.indicators.avg_correlation,
            },
            "timestamp": self.timestamp.isoformat(),
        }


class RegimeClassifier:
    """
    Classify current market regime using multiple signals.

    Uses a weighted voting system across different indicators to
    determine the most likely regime with confidence.
    """

    # Strategy recommendations by regime
    REGIME_STRATEGIES: dict[MarketRegime, tuple[list[str], list[str]]] = {
        MarketRegime.RISK_ON: (
            ["momentum", "growth", "breakout", "high_beta"],
            ["defensive", "volatility_short", "quality"]
        ),
        MarketRegime.RISK_OFF: (
            ["defensive", "volatility_long", "quality", "low_beta"],
            ["momentum", "growth", "high_beta", "breakout"]
        ),
        MarketRegime.RANGE_BOUND: (
            ["mean_reversion", "bollinger_reversal", "pairs_trading", "rsi_reversal"],
            ["trend_following", "breakout", "momentum"]
        ),
        MarketRegime.TRENDING: (
            ["trend_following", "momentum", "breakout", "channel_trading"],
            ["mean_reversion", "bollinger_reversal", "fade_strategies"]
        ),
        MarketRegime.ROTATION: (
            ["sector_momentum", "relative_strength", "factor_rotation"],
            ["index_beta", "buy_and_hold"]
        ),
        MarketRegime.MIXED: (
            ["balanced", "market_neutral"],
            []
        ),
    }

    # VIX thresholds
    VIX_LOW = 15
    VIX_NORMAL = 20
    VIX_ELEVATED = 25
    VIX_HIGH = 30

    # ADX thresholds
    ADX_WEAK = 20
    ADX_STRONG = 25
    ADX_VERY_STRONG = 40

    # Correlation thresholds
    CORR_LOW = 0.4
    CORR_MODERATE = 0.6
    CORR_HIGH = 0.75

    def __init__(self):
        self.history: list[RegimeState] = []

    def classify(
        self,
        vix: float,
        adx: float,
        trend_direction: int,
        avg_correlation: float,
        realized_vol: float | None = None,
        put_call_ratio: float | None = None,
        breadth: float | None = None,
        vix_history: pd.Series | None = None,
    ) -> RegimeState:
        """
        Classify current market regime.

        Args:
            vix: Current VIX level
            adx: Average Directional Index (trend strength)
            trend_direction: 1 for bullish, -1 for bearish, 0 for mixed
            avg_correlation: Average pairwise sector correlation
            realized_vol: Realized volatility (optional)
            put_call_ratio: Put/call ratio (optional)
            breadth: Market breadth (optional)
            vix_history: Historical VIX for percentile (optional)

        Returns:
            RegimeState with classification and recommendations
        """
        # Calculate VIX percentile
        vix_percentile = 50.0
        if vix_history is not None and len(vix_history) > 20:
            vix_percentile = (vix_history < vix).mean() * 100

        # Calculate VRP
        vrp = 0.0
        if realized_vol is not None:
            vrp = vix - realized_vol

        # Build indicators
        indicators = RegimeIndicators(
            vix=vix,
            vix_percentile=vix_percentile,
            realized_vol=realized_vol or vix * 0.8,  # Rough estimate if not provided
            vrp=vrp,
            adx=adx,
            trend_direction=trend_direction,
            avg_correlation=avg_correlation,
            put_call_ratio=put_call_ratio,
            breadth=breadth,
        )

        # Vote on regime
        votes: dict[MarketRegime, float] = {r: 0.0 for r in MarketRegime}
        reasoning = []

        # Rule 1: High VIX = Risk-Off (weight: 3)
        if vix > self.VIX_HIGH:
            votes[MarketRegime.RISK_OFF] += 3.0
            reasoning.append(f"VIX={vix:.1f} > {self.VIX_HIGH} indicates high fear")
        elif vix > self.VIX_ELEVATED:
            votes[MarketRegime.RISK_OFF] += 1.5
            reasoning.append(f"VIX={vix:.1f} elevated")
        elif vix < self.VIX_LOW:
            votes[MarketRegime.RISK_ON] += 2.0
            reasoning.append(f"VIX={vix:.1f} < {self.VIX_LOW} indicates low fear")

        # Rule 2: ADX trend strength (weight: 2)
        if adx > self.ADX_VERY_STRONG:
            votes[MarketRegime.TRENDING] += 2.5
            reasoning.append(f"ADX={adx:.1f} shows very strong trend")
        elif adx > self.ADX_STRONG:
            votes[MarketRegime.TRENDING] += 2.0
            reasoning.append(f"ADX={adx:.1f} shows strong trend")
        elif adx < self.ADX_WEAK:
            votes[MarketRegime.RANGE_BOUND] += 2.0
            votes[MarketRegime.ROTATION] += 0.5
            reasoning.append(f"ADX={adx:.1f} shows weak trend (range-bound)")

        # Rule 3: Correlation (weight: 1.5)
        if avg_correlation > self.CORR_HIGH:
            # High correlation = risk-on or risk-off
            if trend_direction > 0:
                votes[MarketRegime.RISK_ON] += 1.5
            else:
                votes[MarketRegime.RISK_OFF] += 1.5
            reasoning.append(f"High correlation ({avg_correlation:.2f}) = macro-driven")
        elif avg_correlation < self.CORR_LOW:
            votes[MarketRegime.ROTATION] += 2.0
            reasoning.append(f"Low correlation ({avg_correlation:.2f}) = sector rotation")

        # Rule 4: Trend direction with moderate ADX
        if trend_direction > 0 and adx >= self.ADX_WEAK:
            votes[MarketRegime.RISK_ON] += 1.0
        elif trend_direction < 0 and adx >= self.ADX_WEAK:
            votes[MarketRegime.RISK_OFF] += 1.0

        # Rule 5: VRP analysis
        if vrp > 5:  # IV much higher than RV
            votes[MarketRegime.RISK_OFF] += 0.5
            reasoning.append(f"High VRP ({vrp:.1f}) suggests fear")
        elif vrp < -3:  # RV higher than IV
            reasoning.append(f"Negative VRP ({vrp:.1f}) - realized vol elevated")

        # Rule 6: Put/Call ratio if available
        if put_call_ratio is not None:
            if put_call_ratio > 1.2:
                votes[MarketRegime.RISK_OFF] += 0.5
                reasoning.append(f"High put/call ({put_call_ratio:.2f}) = fear")
            elif put_call_ratio < 0.7:
                votes[MarketRegime.RISK_ON] += 0.5
                reasoning.append(f"Low put/call ({put_call_ratio:.2f}) = complacency")

        # Find winning regime
        max_votes = max(votes.values())
        winning_regime = max(votes.keys(), key=lambda r: votes[r])

        # Calculate confidence
        total_votes = sum(votes.values())
        if total_votes > 0:
            confidence = max_votes / total_votes
        else:
            confidence = 0.5
            winning_regime = MarketRegime.MIXED

        # If confidence is low, classify as mixed
        if confidence < 0.4:
            winning_regime = MarketRegime.MIXED
            confidence = 0.5
            reasoning.append("No clear regime - classified as mixed")

        # Get strategy recommendations
        recommended, avoid = self.REGIME_STRATEGIES[winning_regime]

        # Generate transition signals
        transitions = self._get_transition_signals(winning_regime, indicators)

        state = RegimeState(
            regime=winning_regime,
            confidence=confidence,
            indicators=indicators,
            recommended_strategies=recommended,
            avoid_strategies=avoid,
            reasoning=reasoning,
            transition_signals=transitions,
        )

        self.history.append(state)
        return state

    def _get_transition_signals(
        self,
        current_regime: MarketRegime,
        indicators: RegimeIndicators
    ) -> list[str]:
        """Get signals that would indicate regime change."""
        signals = []

        if current_regime == MarketRegime.RISK_ON:
            signals.append(f"VIX > {self.VIX_ELEVATED} would signal shift to risk-off")
            signals.append(f"ADX < {self.ADX_WEAK} would signal range-bound")

        elif current_regime == MarketRegime.RISK_OFF:
            signals.append(f"VIX < {self.VIX_NORMAL} would signal recovery")
            signals.append("Trend reversal with bullish confirmation")

        elif current_regime == MarketRegime.RANGE_BOUND:
            signals.append(f"ADX > {self.ADX_STRONG} would signal trend emerging")
            signals.append(f"VIX spike > {self.VIX_ELEVATED} would signal risk-off")

        elif current_regime == MarketRegime.TRENDING:
            signals.append(f"ADX < {self.ADX_WEAK} would signal trend exhaustion")
            signals.append("Failed breakout/breakdown patterns")

        elif current_regime == MarketRegime.ROTATION:
            signals.append(f"Correlation > {self.CORR_HIGH} would signal macro regime")
            signals.append(f"ADX > {self.ADX_STRONG} would signal trend")

        return signals

    def get_regime_strategy_map(self) -> dict[str, list[str]]:
        """Return mapping of regimes to effective strategies."""
        return {
            regime.value: strategies[0]
            for regime, strategies in self.REGIME_STRATEGIES.items()
        }

    def get_current_recommendation(self) -> dict | None:
        """Get current regime recommendation."""
        if not self.history:
            return None
        latest = self.history[-1]
        return {
            "regime": latest.regime.value,
            "confidence": latest.confidence,
            "use": latest.recommended_strategies[:3],
            "avoid": latest.avoid_strategies[:3],
        }


# ============================================================================
# EMPIRICAL REGIME-STRATEGY FRAMEWORK
# Based on analysis of 470+ strategy/symbol combinations on mid/small caps
# ============================================================================

class VolatilityTrendRegime(Enum):
    """Simplified regime based on volatility + trend (from empirical analysis)."""
    HIGH_VOL_UPTREND = "high_vol_uptrend"
    HIGH_VOL_DOWNTREND = "high_vol_downtrend"
    LOW_VOL_UPTREND = "low_vol_uptrend"
    LOW_VOL_DOWNTREND = "low_vol_downtrend"


@dataclass
class EmpiricalRegimeState:
    """Regime state based on our empirical analysis."""
    volatility_high: bool
    uptrend: bool
    combined: VolatilityTrendRegime
    vol_percentile: float
    trend_strength: float
    confidence: float

    def __str__(self) -> str:
        return (f"Regime: {self.combined.value} "
                f"(Vol: {self.vol_percentile:.0f}%ile, "
                f"Trend: {self.trend_strength:+.2f})")


@dataclass
class StrategyRecommendation:
    """Strategy recommendation for current regime."""
    strategy: str
    expected_sharpe: float
    confidence: str
    position_size_multiplier: float
    notes: str


# Empirical performance from mid/small cap analysis
EMPIRICAL_REGIME_PERFORMANCE = {
    # (strategy, regime): (expected_sharpe, confidence)
    # RSI strategies - best in high vol
    ("rsi_14_30", VolatilityTrendRegime.HIGH_VOL_UPTREND): (1.54, "HIGH"),
    ("rsi_14_30", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (0.70, "MEDIUM"),
    ("rsi_14_30", VolatilityTrendRegime.LOW_VOL_UPTREND): (1.05, "MEDIUM"),
    ("rsi_14_30", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (-0.18, "LOW"),

    ("rsi_14_25", VolatilityTrendRegime.HIGH_VOL_UPTREND): (1.37, "HIGH"),
    ("rsi_14_25", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (0.90, "MEDIUM"),
    ("rsi_14_25", VolatilityTrendRegime.LOW_VOL_UPTREND): (0.64, "MEDIUM"),
    ("rsi_14_25", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (0.13, "LOW"),

    # Mean reversion - works across regimes
    ("mean_rev_20_2.0", VolatilityTrendRegime.HIGH_VOL_UPTREND): (1.08, "HIGH"),
    ("mean_rev_20_2.0", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (0.84, "MEDIUM"),
    ("mean_rev_20_2.0", VolatilityTrendRegime.LOW_VOL_UPTREND): (0.38, "LOW"),
    ("mean_rev_20_2.0", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (0.62, "MEDIUM"),

    # Momentum - best in uptrend, FAILS in downtrend
    ("momentum_20", VolatilityTrendRegime.HIGH_VOL_UPTREND): (0.31, "LOW"),
    ("momentum_20", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (-1.90, "AVOID"),
    ("momentum_20", VolatilityTrendRegime.LOW_VOL_UPTREND): (2.48, "HIGH"),
    ("momentum_20", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (1.67, "MEDIUM"),

    ("momentum_50", VolatilityTrendRegime.HIGH_VOL_UPTREND): (0.79, "MEDIUM"),
    ("momentum_50", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (-2.41, "AVOID"),
    ("momentum_50", VolatilityTrendRegime.LOW_VOL_UPTREND): (2.19, "HIGH"),
    ("momentum_50", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (0.32, "LOW"),

    # Breakout - best in uptrend, risky in downtrend
    ("breakout_10", VolatilityTrendRegime.HIGH_VOL_UPTREND): (1.79, "HIGH"),
    ("breakout_10", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (-0.60, "AVOID"),
    ("breakout_10", VolatilityTrendRegime.LOW_VOL_UPTREND): (0.88, "MEDIUM"),
    ("breakout_10", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (0.90, "MEDIUM"),

    ("breakout_20", VolatilityTrendRegime.HIGH_VOL_UPTREND): (1.47, "HIGH"),
    ("breakout_20", VolatilityTrendRegime.HIGH_VOL_DOWNTREND): (-1.03, "AVOID"),
    ("breakout_20", VolatilityTrendRegime.LOW_VOL_UPTREND): (0.65, "MEDIUM"),
    ("breakout_20", VolatilityTrendRegime.LOW_VOL_DOWNTREND): (0.73, "MEDIUM"),
}


# Mid/small cap universe with alpha potential (from analysis)
MIDCAP_ALPHA_UNIVERSE = {
    "cybersecurity": ["CRWD", "NET", "ZS"],
    "cloud_data": ["DDOG", "SNOW", "PLTR"],
    "fintech": ["HOOD", "SOFI", "UPST", "AFRM"],
    "consumer_tech": ["DASH", "ABNB", "PINS", "SNAP"],
    "biotech": ["MRNA", "BNTX", "EXAS"],
    "solar_energy": ["ENPH", "SEDG", "RUN", "FSLR"],
    "ev": ["RIVN", "LCID", "NIO"],
    "meme_volatile": ["GME", "AMC", "NOK"],
}


class EmpiricalRegimeClassifier:
    """
    Regime classifier based on empirical analysis of mid/small cap strategies.

    Key findings from 470+ strategy/symbol combinations:
    - Mid/small caps: 70 strategies beat B&H (14.9% win rate)
    - Large caps: Only 20 beat B&H (3.8% win rate)
    - RSI/Mean-rev: Best in HIGH VOL (Sharpe 1.54)
    - Momentum: Best in UPTREND (Sharpe 2.48), FAILS in downtrend (-1.90)
    - Breakout: Best in UPTREND (Sharpe 1.79), FAILS in downtrend
    """

    def __init__(
        self,
        vol_window: int = 20,
        vol_lookback: int = 252,
        trend_window: int = 50,
    ):
        self.vol_window = vol_window
        self.vol_lookback = vol_lookback
        self.trend_window = trend_window

    def detect_regime(
        self,
        prices: pd.Series,
        returns: pd.Series | None = None,
    ) -> EmpiricalRegimeState:
        """
        Detect current regime using volatility and trend.

        Args:
            prices: Price series (min 252 days recommended)
            returns: Optional returns (computed if not provided)

        Returns:
            EmpiricalRegimeState with classification
        """
        if returns is None:
            returns = prices.pct_change().dropna()

        # Volatility regime
        vol = returns.rolling(self.vol_window).std() * np.sqrt(252)
        current_vol = vol.iloc[-1].item() if hasattr(vol.iloc[-1], 'item') else float(vol.iloc[-1])
        vol_lookback_data = vol.iloc[-self.vol_lookback:]
        vol_pct_raw = (vol_lookback_data < current_vol).mean() * 100
        vol_percentile = vol_pct_raw.item() if hasattr(vol_pct_raw, 'item') else float(vol_pct_raw)
        high_vol = vol_percentile >= 50

        # Trend regime
        sma = prices.rolling(self.trend_window).mean()
        current_price = prices.iloc[-1].item() if hasattr(prices.iloc[-1], 'item') else float(prices.iloc[-1])
        current_sma = sma.iloc[-1].item() if hasattr(sma.iloc[-1], 'item') else float(sma.iloc[-1])
        trend_strength = (current_price - current_sma) / current_sma
        trend_strength = float(np.clip(trend_strength, -1, 1))
        uptrend = current_price > current_sma

        # Combined regime
        if high_vol and uptrend:
            combined = VolatilityTrendRegime.HIGH_VOL_UPTREND
        elif high_vol and not uptrend:
            combined = VolatilityTrendRegime.HIGH_VOL_DOWNTREND
        elif not high_vol and uptrend:
            combined = VolatilityTrendRegime.LOW_VOL_UPTREND
        else:
            combined = VolatilityTrendRegime.LOW_VOL_DOWNTREND

        # Confidence
        vol_conf = abs(vol_percentile - 50) / 50
        trend_conf = min(abs(trend_strength) * 5, 1)
        confidence = (vol_conf + trend_conf) / 2

        return EmpiricalRegimeState(
            volatility_high=high_vol,
            uptrend=uptrend,
            combined=combined,
            vol_percentile=vol_percentile,
            trend_strength=trend_strength,
            confidence=confidence,
        )

    def get_strategy_recommendations(
        self,
        regime: EmpiricalRegimeState,
        strategies: list[str] | None = None,
    ) -> list[StrategyRecommendation]:
        """Get strategy recommendations sorted by expected Sharpe."""
        if strategies is None:
            strategies = list(set(s for s, _ in EMPIRICAL_REGIME_PERFORMANCE.keys()))

        recommendations = []
        for strategy in strategies:
            key = (strategy, regime.combined)
            if key not in EMPIRICAL_REGIME_PERFORMANCE:
                continue

            sharpe, conf = EMPIRICAL_REGIME_PERFORMANCE[key]
            if conf == "AVOID":
                continue

            size_mult = self._get_position_size(regime, sharpe, conf)
            notes = self._get_notes(strategy, regime)

            recommendations.append(StrategyRecommendation(
                strategy=strategy,
                expected_sharpe=sharpe,
                confidence=conf,
                position_size_multiplier=size_mult,
                notes=notes,
            ))

        recommendations.sort(key=lambda x: x.expected_sharpe, reverse=True)
        return recommendations

    def _get_position_size(self, regime: EmpiricalRegimeState, sharpe: float, conf: str) -> float:
        """Calculate position size multiplier."""
        base = 1.0
        if regime.volatility_high:
            base *= 0.8
        if not regime.uptrend:
            base *= 0.7
        conf_mult = {"HIGH": 1.2, "MEDIUM": 1.0, "LOW": 0.7}
        base *= conf_mult.get(conf, 1.0)
        if sharpe > 1.5:
            base *= 1.1
        elif sharpe < 0.5:
            base *= 0.8
        return np.clip(base, 0.3, 1.5)

    def _get_notes(self, strategy: str, regime: EmpiricalRegimeState) -> str:
        """Generate regime-specific strategy notes."""
        if "rsi" in strategy or "mean_rev" in strategy:
            if regime.volatility_high:
                return "High vol = bigger bounce opportunities"
            return "Standard conditions"
        elif "momentum" in strategy:
            if regime.uptrend:
                return "Riding existing momentum"
            return "CAUTION: Momentum fails in downtrends"
        elif "breakout" in strategy:
            if regime.uptrend:
                return "Breakouts have follow-through"
            return "CAUTION: False breakouts common"
        return "Standard conditions"

    def get_avoid_strategies(self, regime: EmpiricalRegimeState) -> list[str]:
        """Get strategies to avoid in current regime."""
        avoid = []
        for (strategy, r), (sharpe, conf) in EMPIRICAL_REGIME_PERFORMANCE.items():
            if r == regime.combined and (conf == "AVOID" or sharpe < 0):
                avoid.append(strategy)
        return list(set(avoid))

    def get_regime_strategy_map(self) -> dict[VolatilityTrendRegime, list[str]]:
        """Get recommended strategies by regime."""
        return {
            VolatilityTrendRegime.HIGH_VOL_UPTREND: [
                "rsi_14_30", "breakout_10", "mean_rev_20_2.0"
            ],
            VolatilityTrendRegime.HIGH_VOL_DOWNTREND: [
                "rsi_14_30", "rsi_14_25", "mean_rev_20_2.0"
            ],
            VolatilityTrendRegime.LOW_VOL_UPTREND: [
                "momentum_20", "momentum_50"
            ],
            VolatilityTrendRegime.LOW_VOL_DOWNTREND: [
                "mean_rev_20_2.0"  # Minimal exposure
            ],
        }


def get_symbols_for_regime(regime: EmpiricalRegimeState) -> list[str]:
    """Get recommended symbols based on regime."""
    symbols = []
    if regime.volatility_high:
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["solar_energy"])
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["meme_volatile"])
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["fintech"])
    else:
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["cloud_data"])
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["cybersecurity"])
    if regime.uptrend:
        symbols.extend(MIDCAP_ALPHA_UNIVERSE["consumer_tech"])
    return list(set(symbols))


def classify_from_market_data(
    spy_data: pd.DataFrame,
    vix_data: pd.DataFrame,
    sector_data: pd.DataFrame | None = None,
) -> RegimeState:
    """
    Convenience function to classify regime from market data.

    Args:
        spy_data: SPY OHLCV data
        vix_data: VIX data
        sector_data: Sector ETF data (XLK, XLF, etc.)

    Returns:
        RegimeState classification
    """
    classifier = RegimeClassifier()

    # Current VIX
    vix = vix_data['Close'].iloc[-1]

    # Calculate ADX (simplified)
    close = spy_data['Close']
    high = spy_data['High']
    low = spy_data['Low']

    # True Range
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)

    # Directional movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    # Smoothed (using EMA approximation)
    period = 14
    tr_smooth = pd.Series(tr).ewm(span=period).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(span=period).mean() / tr_smooth
    minus_di = 100 * pd.Series(minus_dm).ewm(span=period).mean() / tr_smooth

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(span=period).mean().iloc[-1]

    # Trend direction
    sma_50 = close.rolling(50).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()
    current = close.iloc[-1]

    if current > sma_50 > sma_200:
        trend_direction = 1
    elif current < sma_50 < sma_200:
        trend_direction = -1
    else:
        trend_direction = 0

    # Sector correlation
    avg_correlation = 0.6  # Default
    if sector_data is not None:
        sector_returns = sector_data.pct_change().dropna()
        corr_matrix = sector_returns.corr()
        # Average off-diagonal correlation
        mask = ~np.eye(len(corr_matrix), dtype=bool)
        avg_correlation = corr_matrix.where(mask).mean().mean()

    # Realized volatility
    realized_vol = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100

    return classifier.classify(
        vix=vix,
        adx=adx,
        trend_direction=trend_direction,
        avg_correlation=avg_correlation,
        realized_vol=realized_vol,
        vix_history=vix_data['Close'],
    )
