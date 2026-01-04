"""
Trading Analytics

Rules, heuristics, and analytics for trading decisions:
- Market regime detection
- Earnings/event proximity checks
- Position sizing rules
- Entry/exit rule generation
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

class MarketRegime(Enum):
    """Market regime types."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    NEUTRAL = "neutral"


class VolatilityRegime(Enum):
    """Volatility regime types."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RegimeAnalysis:
    """Analysis of current market regime."""
    primary_regime: MarketRegime
    volatility_regime: VolatilityRegime
    confidence: float
    regime_duration_days: int
    indicators: dict = field(default_factory=dict)


@dataclass
class EntryRule:
    """Rule for trade entry."""
    name: str
    condition: str
    description: str
    priority: int = 1


@dataclass
class ExitRule:
    """Rule for trade exit."""
    name: str
    condition: str
    description: str
    rule_type: str = "stop_loss"  # stop_loss, take_profit, time_based, trailing


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""
    symbol: str
    recommended_size: float  # Fraction of portfolio
    max_size: float
    rationale: str
    risk_metrics: dict = field(default_factory=dict)


# =============================================================================
# TRADING ANALYTICS
# =============================================================================

class TradingAnalytics:
    """
    Analytics, rules, and heuristics for trading.

    Usage:
        analytics = TradingAnalytics()

        # Detect regime
        regime = analytics.detect_regime()

        # Check event sensitivity
        is_sensitive = analytics.is_earnings_sensitive("AAPL")

        # Calculate position size
        size = analytics.calculate_position_size("AAPL", confidence=0.7)

        # Get strategy rules
        entry_rules = analytics.get_entry_rules("momentum")
    """

    # Risk parameters
    MAX_POSITION_SIZE = 0.10  # 10% max per position
    BASE_RISK_PER_TRADE = 0.02  # 2% risk per trade
    KELLY_FRACTION = 0.5  # Half Kelly for safety

    def __init__(self):
        self._price_cache = {}

    def _get_market_data(self, symbol: str = "SPY", period: str = "120d") -> pd.DataFrame:
        """Fetch market data."""
        import yfinance as yf

        if symbol not in self._price_cache:
            df = yf.download(symbol, period=period, progress=False)
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
            self._price_cache[symbol] = df

        return self._price_cache[symbol]

    # -------------------------------------------------------------------------
    # REGIME DETECTION
    # -------------------------------------------------------------------------

    def detect_regime(self, lookback: int = 60) -> RegimeAnalysis:
        """
        Detect current market regime.

        Uses SPY as market proxy:
        - Trending: Strong directional momentum
        - Mean-reverting: High RSI reversion
        - Volatile: High realized volatility
        - Crisis: Extreme drawdown + high volatility
        """
        df = self._get_market_data("SPY")

        if len(df) < lookback:
            return RegimeAnalysis(
                primary_regime=MarketRegime.NEUTRAL,
                volatility_regime=VolatilityRegime.NORMAL,
                confidence=0.5,
                regime_duration_days=0,
            )

        close = df["close"]
        returns = close.pct_change().dropna()

        # Calculate indicators
        indicators = {}

        # Trend strength (ADX-like)
        momentum_20 = close.pct_change(20).iloc[-1]
        momentum_60 = close.pct_change(60).iloc[-1]
        indicators["momentum_20d"] = momentum_20
        indicators["momentum_60d"] = momentum_60

        # Volatility
        vol_20 = returns.rolling(20).std().iloc[-1] * np.sqrt(252)
        vol_60 = returns.rolling(60).std().iloc[-1] * np.sqrt(252)
        vol_percentile = returns.rolling(252).std().rank(pct=True).iloc[-1] if len(returns) >= 252 else 0.5
        indicators["volatility_20d"] = vol_20
        indicators["volatility_percentile"] = vol_percentile

        # Drawdown
        peak = close.cummax()
        drawdown = (close - peak) / peak
        current_dd = drawdown.iloc[-1]
        indicators["current_drawdown"] = current_dd

        # RSI mean reversion signal
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        indicators["rsi_14"] = rsi.iloc[-1]

        # Determine volatility regime
        if vol_percentile > 0.9 or vol_20 > 0.35:
            vol_regime = VolatilityRegime.EXTREME
        elif vol_percentile > 0.7 or vol_20 > 0.25:
            vol_regime = VolatilityRegime.HIGH
        elif vol_percentile < 0.3 or vol_20 < 0.10:
            vol_regime = VolatilityRegime.LOW
        else:
            vol_regime = VolatilityRegime.NORMAL

        # Determine primary regime
        if current_dd < -0.20 and vol_regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]:
            regime = MarketRegime.CRISIS
            confidence = 0.8
        elif abs(momentum_60) > 0.15 and momentum_20 * momentum_60 > 0:
            # Strong trend in same direction
            regime = MarketRegime.TRENDING_UP if momentum_60 > 0 else MarketRegime.TRENDING_DOWN
            confidence = min(0.8, abs(momentum_60) * 3)
        elif vol_regime == VolatilityRegime.EXTREME:
            regime = MarketRegime.HIGH_VOLATILITY
            confidence = 0.7
        elif vol_regime == VolatilityRegime.LOW:
            regime = MarketRegime.LOW_VOLATILITY
            confidence = 0.6
        elif rsi.iloc[-1] < 30 or rsi.iloc[-1] > 70:
            regime = MarketRegime.MEAN_REVERTING
            confidence = 0.6
        else:
            regime = MarketRegime.NEUTRAL
            confidence = 0.5

        # Estimate regime duration (simplified)
        regime_duration = self._estimate_regime_duration(returns, regime)

        return RegimeAnalysis(
            primary_regime=regime,
            volatility_regime=vol_regime,
            confidence=confidence,
            regime_duration_days=regime_duration,
            indicators=indicators,
        )

    def _estimate_regime_duration(self, returns: pd.Series, regime: MarketRegime) -> int:
        """Estimate how long current regime has persisted."""
        # Simplified: count days with consistent characteristics
        vol_20 = returns.rolling(20).std() * np.sqrt(252)

        if regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
            # Count days with consistent momentum
            momentum = returns.rolling(20).mean()
            if regime == MarketRegime.TRENDING_UP:
                duration = (momentum > 0).iloc[::-1].cumsum().iloc[-1]
            else:
                duration = (momentum < 0).iloc[::-1].cumsum().iloc[-1]
        elif regime == MarketRegime.HIGH_VOLATILITY:
            # Count high vol days
            high_vol = vol_20 > vol_20.quantile(0.7)
            duration = high_vol.iloc[::-1].cumsum().iloc[-1]
        else:
            duration = 10

        return int(min(duration, 252))

    def get_regime_appropriate_strategies(self, regime: MarketRegime) -> list[str]:
        """Get strategies that work well in current regime."""
        regime_strategies = {
            MarketRegime.TRENDING_UP: [
                "momentum", "trend_following", "breakout",
            ],
            MarketRegime.TRENDING_DOWN: [
                "short_momentum", "put_spread", "defensive",
            ],
            MarketRegime.MEAN_REVERTING: [
                "rsi_reversal", "bollinger_reversal", "pairs_trading",
            ],
            MarketRegime.HIGH_VOLATILITY: [
                "volatility_selling", "iron_condor", "straddle",
            ],
            MarketRegime.LOW_VOLATILITY: [
                "momentum", "trend_following", "carry",
            ],
            MarketRegime.CRISIS: [
                "defensive", "cash", "tail_hedge",
            ],
            MarketRegime.NEUTRAL: [
                "multi_factor", "market_neutral", "arbitrage",
            ],
        }

        return regime_strategies.get(regime, ["multi_factor"])

    # -------------------------------------------------------------------------
    # EVENT SENSITIVITY
    # -------------------------------------------------------------------------

    def is_earnings_sensitive(self, symbol: str, days_to_earnings: int = 5) -> bool:
        """Check if symbol is near earnings announcement."""
        # This would integrate with earnings calendar
        # For now, return False as placeholder
        return False

    def is_ex_dividend(self, symbol: str, days: int = 3) -> bool:
        """Check if near ex-dividend date."""
        # This would integrate with dividend calendar
        return False

    def is_options_expiry(self, days_to_expiry: int = 2) -> bool:
        """Check if near monthly options expiry (3rd Friday)."""
        today = datetime.now()
        # Find 3rd Friday of current month
        first_day = today.replace(day=1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(weeks=2)

        days_to = (third_friday - today).days
        return 0 <= days_to <= days_to_expiry

    def get_event_calendar(self, symbol: str, days_ahead: int = 14) -> list[dict]:
        """Get upcoming events for symbol."""
        events = []

        # Check options expiry
        if self.is_options_expiry(days_to_expiry=days_ahead):
            events.append({
                "type": "options_expiry",
                "description": "Monthly options expiration",
                "impact": "high_gamma",
            })

        return events

    # -------------------------------------------------------------------------
    # POSITION SIZING
    # -------------------------------------------------------------------------

    def calculate_position_size(
        self,
        symbol: str,
        confidence: float,
        portfolio_value: float = 100000,
        max_risk_pct: float = None,
    ) -> PositionSizeResult:
        """
        Calculate recommended position size.

        Uses modified Kelly criterion with:
        - Confidence as win probability estimate
        - Historical volatility for risk
        - Correlation adjustment for portfolio
        """
        df = self._get_market_data(symbol, period="60d")

        if df.empty:
            return PositionSizeResult(
                symbol=symbol,
                recommended_size=0.02,
                max_size=self.MAX_POSITION_SIZE,
                rationale="Insufficient data, using minimum size",
            )

        # Calculate volatility
        returns = df["close"].pct_change().dropna()
        vol = returns.std() * np.sqrt(252)

        # Base size from Kelly
        # Kelly = (p * b - q) / b where p = win prob, q = loss prob, b = win/loss ratio
        # Simplified: size proportional to confidence / volatility
        win_prob = confidence
        loss_prob = 1 - confidence
        win_loss_ratio = 1.5  # Assumed

        kelly_fraction = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio
        kelly_fraction = max(0, kelly_fraction) * self.KELLY_FRACTION  # Half Kelly

        # Volatility adjustment
        vol_adjustment = 0.20 / max(vol, 0.10)  # Scale to 20% baseline vol
        vol_adjustment = min(2.0, max(0.5, vol_adjustment))

        # Calculate size
        base_size = kelly_fraction * vol_adjustment
        recommended_size = min(base_size, self.MAX_POSITION_SIZE)

        # Risk metrics
        atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
        risk_metrics = {
            "volatility": vol,
            "atr": atr,
            "kelly_fraction": kelly_fraction,
            "vol_adjustment": vol_adjustment,
        }

        rationale = f"Kelly-based sizing with {vol:.0%} vol adjustment"

        return PositionSizeResult(
            symbol=symbol,
            recommended_size=round(recommended_size, 4),
            max_size=self.MAX_POSITION_SIZE,
            rationale=rationale,
            risk_metrics=risk_metrics,
        )

    def adjust_for_correlation(
        self,
        positions: dict[str, float],
        new_symbol: str,
        correlation_limit: float = 0.7,
    ) -> float:
        """
        Adjust position size based on portfolio correlation.

        Args:
            positions: Current positions {symbol: size}
            new_symbol: New position to add
            correlation_limit: Max acceptable correlation

        Returns:
            Adjustment factor (0 to 1)
        """
        if not positions:
            return 1.0

        # Fetch returns for all symbols
        symbols = list(positions.keys()) + [new_symbol]
        all_data = {}

        for symbol in symbols:
            df = self._get_market_data(symbol, period="60d")
            if not df.empty:
                all_data[symbol] = df["close"].pct_change().dropna()

        if new_symbol not in all_data:
            return 1.0

        new_returns = all_data[new_symbol]

        # Calculate correlations with existing positions
        max_corr = 0
        for symbol, size in positions.items():
            if symbol in all_data:
                corr = new_returns.corr(all_data[symbol])
                max_corr = max(max_corr, abs(corr))

        # Reduce size if high correlation
        if max_corr > correlation_limit:
            adjustment = (1 - max_corr) / (1 - correlation_limit)
            return max(0.3, adjustment)  # At least 30% of original size

        return 1.0

    # -------------------------------------------------------------------------
    # ENTRY/EXIT RULES
    # -------------------------------------------------------------------------

    def get_entry_rules(self, strategy: str) -> list[EntryRule]:
        """Get entry rules for a strategy."""
        rules = {
            "momentum": [
                EntryRule("momentum_positive", "return_20d > 0.05", "20-day momentum > 5%", 1),
                EntryRule("above_sma", "price > sma_50", "Price above 50-day SMA", 2),
                EntryRule("volume_confirm", "volume_ratio > 1.2", "Volume 20% above average", 3),
            ],
            "rsi_reversal": [
                EntryRule("rsi_oversold", "rsi_14 < 30", "RSI below 30", 1),
                EntryRule("not_trending_down", "return_60d > -0.20", "Not in severe downtrend", 2),
                EntryRule("volume_spike", "volume_ratio > 1.5", "Volume spike on reversal", 3),
            ],
            "bollinger_reversal": [
                EntryRule("below_lower", "bb_position < 0", "Price below lower band", 1),
                EntryRule("rsi_oversold", "rsi_14 < 35", "RSI confirming oversold", 2),
            ],
            "trend_following": [
                EntryRule("price_above_sma", "price > sma_200", "Price above 200-day SMA", 1),
                EntryRule("golden_cross", "sma_50 > sma_200", "50-day above 200-day SMA", 2),
                EntryRule("adx_strong", "adx > 25", "Strong trend (ADX > 25)", 3),
            ],
        }

        return rules.get(strategy, [])

    def get_exit_rules(self, strategy: str) -> list[ExitRule]:
        """Get exit rules for a strategy."""
        rules = {
            "momentum": [
                ExitRule("stop_loss", "unrealized_loss > 0.08", "8% stop loss", "stop_loss"),
                ExitRule("trailing_stop", "from_high > 0.10", "10% trailing stop", "trailing"),
                ExitRule("momentum_fade", "return_20d < 0", "Momentum turned negative", "signal"),
            ],
            "rsi_reversal": [
                ExitRule("stop_loss", "unrealized_loss > 0.05", "5% stop loss", "stop_loss"),
                ExitRule("target_reached", "unrealized_gain > 0.10", "10% profit target", "take_profit"),
                ExitRule("time_stop", "days_held > 20", "Time-based exit after 20 days", "time_based"),
            ],
            "bollinger_reversal": [
                ExitRule("stop_loss", "unrealized_loss > 0.06", "6% stop loss", "stop_loss"),
                ExitRule("mean_reached", "bb_position > 0.5", "Price at middle band", "take_profit"),
            ],
            "trend_following": [
                ExitRule("trend_broken", "price < sma_50", "Price below 50-day SMA", "signal"),
                ExitRule("trailing_stop", "from_high > 0.15", "15% trailing stop", "trailing"),
            ],
        }

        return rules.get(strategy, [])

    def generate_trade_plan(
        self,
        symbol: str,
        strategy: str,
        direction: str = "long",
        confidence: float = 0.6,
    ) -> dict:
        """
        Generate complete trade plan with entries, exits, and sizing.

        Returns dict with all trade parameters.
        """
        df = self._get_market_data(symbol)

        if df.empty:
            return {"error": "No price data available"}

        current_price = df["close"].iloc[-1]
        atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]

        # Get rules
        entry_rules = self.get_entry_rules(strategy)
        exit_rules = self.get_exit_rules(strategy)

        # Calculate sizing
        size_result = self.calculate_position_size(symbol, confidence)

        # Calculate price levels
        if direction == "long":
            stop_loss = current_price - 2 * atr
            take_profit = current_price + 3 * atr
        else:
            stop_loss = current_price + 2 * atr
            take_profit = current_price - 3 * atr

        return {
            "symbol": symbol,
            "strategy": strategy,
            "direction": direction,
            "confidence": confidence,
            "current_price": float(current_price),
            "position_size": size_result.recommended_size,
            "entry_rules": [r.name for r in entry_rules],
            "exit_rules": [r.name for r in exit_rules],
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "risk_reward_ratio": abs((take_profit - current_price) / (current_price - stop_loss)),
            "atr": float(atr),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_current_regime() -> RegimeAnalysis:
    """Quick regime detection."""
    analytics = TradingAnalytics()
    return analytics.detect_regime()


def get_position_size(symbol: str, confidence: float) -> PositionSizeResult:
    """Quick position sizing."""
    analytics = TradingAnalytics()
    return analytics.calculate_position_size(symbol, confidence)
