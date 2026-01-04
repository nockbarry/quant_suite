"""Factor-based quantitative strategies.

Implements cross-sectional factor strategies based on academic research
including Fama-French factors and related approaches.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import RuleBasedStrategy


class FactorType(str, Enum):
    """Types of factors for ranking."""

    MOMENTUM = "momentum"
    VALUE = "value"
    SIZE = "size"
    VOLATILITY = "volatility"
    QUALITY = "quality"
    REVERSAL = "reversal"


@dataclass
class FactorScore:
    """Score for a single asset on a factor."""

    symbol: Symbol
    factor: FactorType
    raw_value: float
    z_score: float
    percentile_rank: float
    metadata: dict[str, Any] = field(default_factory=dict)


class CrossSectionalMomentumStrategy(RuleBasedStrategy):
    """
    Cross-sectional momentum strategy.

    Ranks assets by their past returns and generates signals to go long
    the top performers and short the bottom performers.

    Based on Jegadeesh & Titman (1993) momentum effect.
    """

    name = "cs_momentum"
    description = "Cross-sectional momentum factor strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        formation_period: int = 252,
        skip_period: int = 21,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = False,
        volatility_adjusted: bool = True,
        **params: Any,
    ):
        """
        Initialize cross-sectional momentum strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            formation_period: Lookback period for momentum calculation (days)
            skip_period: Days to skip before formation period (avoid reversal)
            top_pct: Percentage of top performers to go long
            bottom_pct: Percentage of bottom performers to go short
            long_only: If True, only generate long signals
            volatility_adjusted: Adjust returns by volatility
        """
        super().__init__(
            universe,
            timeframe,
            formation_period=formation_period,
            skip_period=skip_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            volatility_adjusted=volatility_adjusted,
            **params,
        )
        self.formation_period = formation_period
        self.skip_period = skip_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only
        self.volatility_adjusted = volatility_adjusted

    def get_required_history(self) -> int:
        return self.formation_period + self.skip_period + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate cross-sectional momentum signals.

        Args:
            data: Dict mapping symbols to OHLCV DataFrames
            timestamp: Current timestamp

        Returns:
            List of signals for top and bottom momentum stocks
        """
        if not isinstance(data, dict):
            # Need multiple assets for cross-sectional strategy
            return []

        # Calculate momentum for each asset
        momentum_scores = {}
        volatilities = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]

            # Formation period return (skipping recent days)
            end_idx = -self.skip_period if self.skip_period > 0 else None
            start_idx = -self.formation_period - self.skip_period

            if end_idx:
                formation_return = close.iloc[end_idx] / close.iloc[start_idx] - 1
            else:
                formation_return = close.iloc[-1] / close.iloc[start_idx] - 1

            # Volatility for adjustment
            returns = close.pct_change()
            vol = returns.iloc[-63:].std() * np.sqrt(252)
            volatilities[symbol] = vol

            # Volatility-adjusted momentum (Sharpe-like)
            if self.volatility_adjusted and vol > 0.01:
                momentum_scores[symbol] = formation_return / vol
            else:
                momentum_scores[symbol] = formation_return

        if len(momentum_scores) < 5:
            return []

        # Rank assets by momentum
        sorted_symbols = sorted(momentum_scores.keys(), key=lambda x: momentum_scores[x], reverse=True)

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        # Calculate z-scores for signal strength
        values = list(momentum_scores.values())
        mean_mom = np.mean(values)
        std_mom = np.std(values) if len(values) > 1 else 1.0

        ts = timestamp or datetime.now()
        signals = []

        # Long signals
        for symbol in long_symbols:
            z_score = (momentum_scores[symbol] - mean_mom) / std_mom if std_mom > 0 else 0
            strength = np.tanh(z_score / 2)  # Normalize to [-1, 1]

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, strength)),
                    confidence=0.6,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": FactorType.MOMENTUM.value,
                        "momentum": float(momentum_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                        "n_assets": n_assets,
                    },
                )
            )

        # Short signals
        for symbol in short_symbols:
            z_score = (momentum_scores[symbol] - mean_mom) / std_mom if std_mom > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, strength)),
                    confidence=0.6,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": FactorType.MOMENTUM.value,
                        "momentum": float(momentum_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                        "n_assets": n_assets,
                    },
                )
            )

        return signals


class ValueStrategy(RuleBasedStrategy):
    """
    Value factor strategy using price-based metrics.

    Uses price distance from 52-week high as a value proxy.
    Assets trading far below their highs are considered "cheap" (value).

    Also incorporates:
    - Price-to-moving-average ratios
    - Mean reversion signals
    """

    name = "value_factor"
    description = "Price-based value factor strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_52w: int = 252,
        ma_period: int = 200,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = True,
        **params: Any,
    ):
        """
        Initialize value strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_52w: Period for 52-week high calculation
            ma_period: Moving average period for value measure
            top_pct: Percentage of "cheapest" stocks to go long
            bottom_pct: Percentage of "expensive" stocks to go short
            long_only: If True, only generate long signals
        """
        super().__init__(
            universe,
            timeframe,
            lookback_52w=lookback_52w,
            ma_period=ma_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            **params,
        )
        self.lookback_52w = lookback_52w
        self.ma_period = ma_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only

    def get_required_history(self) -> int:
        return max(self.lookback_52w, self.ma_period) + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate value factor signals."""
        if not isinstance(data, dict):
            return []

        value_scores = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]
            high = df["high"]

            # Distance from 52-week high (negative = cheaper)
            high_52w = high.iloc[-self.lookback_52w:].max()
            current_price = close.iloc[-1]
            dist_from_high = (current_price - high_52w) / high_52w

            # Price to MA ratio
            ma = close.rolling(self.ma_period).mean().iloc[-1]
            price_to_ma = (current_price - ma) / ma

            # Combined value score (lower = cheaper = better for value)
            # Negative values mean trading below highs/MA
            value_scores[symbol] = (dist_from_high + price_to_ma) / 2

        if len(value_scores) < 5:
            return []

        # Rank by value (lower score = more value = rank higher for longs)
        sorted_symbols = sorted(value_scores.keys(), key=lambda x: value_scores[x])

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        # Value stocks are those trading cheapest (most below highs)
        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        values = list(value_scores.values())
        mean_val = np.mean(values)
        std_val = np.std(values) if len(values) > 1 else 1.0

        ts = timestamp or datetime.now()
        signals = []

        for symbol in long_symbols:
            z_score = (mean_val - value_scores[symbol]) / std_val if std_val > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, abs(strength))),
                    confidence=0.55,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": FactorType.VALUE.value,
                        "value_score": float(value_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        for symbol in short_symbols:
            z_score = (value_scores[symbol] - mean_val) / std_val if std_val > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, -abs(strength))),
                    confidence=0.55,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": FactorType.VALUE.value,
                        "value_score": float(value_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        return signals


class LowVolatilityStrategy(RuleBasedStrategy):
    """
    Low volatility factor strategy.

    Goes long low-volatility assets and short high-volatility assets.
    Based on the low-volatility anomaly documented by Baker, Bradley & Wurgler.
    """

    name = "low_volatility"
    description = "Low volatility factor strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        volatility_period: int = 63,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = True,
        use_downside_vol: bool = True,
        **params: Any,
    ):
        """
        Initialize low volatility strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            volatility_period: Period for volatility calculation
            top_pct: Percentage of lowest vol stocks to go long
            bottom_pct: Percentage of highest vol stocks to go short
            long_only: If True, only generate long signals
            use_downside_vol: Use downside deviation instead of standard deviation
        """
        super().__init__(
            universe,
            timeframe,
            volatility_period=volatility_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            use_downside_vol=use_downside_vol,
            **params,
        )
        self.volatility_period = volatility_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only
        self.use_downside_vol = use_downside_vol

    def get_required_history(self) -> int:
        return self.volatility_period + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate low volatility factor signals."""
        if not isinstance(data, dict):
            return []

        vol_scores = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]
            returns = close.pct_change().iloc[-self.volatility_period:]

            if self.use_downside_vol:
                # Downside deviation (only negative returns)
                negative_returns = returns[returns < 0]
                if len(negative_returns) > 5:
                    vol = negative_returns.std() * np.sqrt(252)
                else:
                    vol = returns.std() * np.sqrt(252)
            else:
                vol = returns.std() * np.sqrt(252)

            vol_scores[symbol] = vol

        if len(vol_scores) < 5:
            return []

        # Rank by volatility (lower = better for low-vol strategy)
        sorted_symbols = sorted(vol_scores.keys(), key=lambda x: vol_scores[x])

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        # Low vol stocks for long, high vol for short
        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        values = list(vol_scores.values())
        mean_vol = np.mean(values)
        std_vol = np.std(values) if len(values) > 1 else 1.0

        ts = timestamp or datetime.now()
        signals = []

        for symbol in long_symbols:
            z_score = (mean_vol - vol_scores[symbol]) / std_vol if std_vol > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, abs(strength))),
                    confidence=0.6,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": FactorType.VOLATILITY.value,
                        "volatility": float(vol_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        for symbol in short_symbols:
            z_score = (vol_scores[symbol] - mean_vol) / std_vol if std_vol > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, -abs(strength))),
                    confidence=0.6,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": FactorType.VOLATILITY.value,
                        "volatility": float(vol_scores[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        return signals


class QualityStrategy(RuleBasedStrategy):
    """
    Quality factor strategy using price-based quality proxies.

    Quality is measured by:
    - Consistency of returns (lower volatility of returns)
    - Consistency of positive returns
    - Risk-adjusted performance (Sharpe-like measure)
    """

    name = "quality_factor"
    description = "Price-based quality factor strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_period: int = 252,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = True,
        **params: Any,
    ):
        """
        Initialize quality strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_period: Period for quality calculation
            top_pct: Percentage of highest quality stocks to go long
            bottom_pct: Percentage of lowest quality stocks to go short
            long_only: If True, only generate long signals
        """
        super().__init__(
            universe,
            timeframe,
            lookback_period=lookback_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            **params,
        )
        self.lookback_period = lookback_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only

    def get_required_history(self) -> int:
        return self.lookback_period + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate quality factor signals."""
        if not isinstance(data, dict):
            return []

        quality_scores = {}
        quality_details = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]
            returns = close.pct_change().iloc[-self.lookback_period:]

            # Quality metrics
            # 1. Consistency: % of positive return days
            pct_positive = (returns > 0).mean()

            # 2. Risk-adjusted return (annualized Sharpe)
            mean_ret = returns.mean() * 252
            std_ret = returns.std() * np.sqrt(252)
            sharpe = mean_ret / std_ret if std_ret > 0.01 else 0

            # 3. Drawdown quality (smaller max drawdown = higher quality)
            cumulative = (1 + returns).cumprod()
            rolling_max = cumulative.expanding().max()
            drawdowns = cumulative / rolling_max - 1
            max_drawdown = abs(drawdowns.min())
            drawdown_score = 1 - min(1, max_drawdown)  # 0 to 1, higher = better

            # Combined quality score
            quality = (pct_positive + (sharpe + 1) / 2 + drawdown_score) / 3

            quality_scores[symbol] = quality
            quality_details[symbol] = {
                "pct_positive": pct_positive,
                "sharpe": sharpe,
                "max_drawdown": max_drawdown,
            }

        if len(quality_scores) < 5:
            return []

        # Rank by quality (higher = better)
        sorted_symbols = sorted(quality_scores.keys(), key=lambda x: quality_scores[x], reverse=True)

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        values = list(quality_scores.values())
        mean_qual = np.mean(values)
        std_qual = np.std(values) if len(values) > 1 else 1.0

        ts = timestamp or datetime.now()
        signals = []

        for symbol in long_symbols:
            z_score = (quality_scores[symbol] - mean_qual) / std_qual if std_qual > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, abs(strength))),
                    confidence=0.55,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": FactorType.QUALITY.value,
                        "quality_score": float(quality_scores[symbol]),
                        "z_score": float(z_score),
                        **quality_details[symbol],
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        for symbol in short_symbols:
            z_score = (mean_qual - quality_scores[symbol]) / std_qual if std_qual > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, -abs(strength))),
                    confidence=0.55,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": FactorType.QUALITY.value,
                        "quality_score": float(quality_scores[symbol]),
                        "z_score": float(z_score),
                        **quality_details[symbol],
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        return signals


class ShortTermReversalStrategy(RuleBasedStrategy):
    """
    Short-term reversal strategy.

    Contrarian strategy that bets on mean reversion of recent losers/winners.
    Based on Jegadeesh (1990) and Lehmann (1990).
    """

    name = "st_reversal"
    description = "Short-term reversal factor strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_period: int = 5,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = False,
        **params: Any,
    ):
        """
        Initialize short-term reversal strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_period: Period for recent return calculation (typically 1-5 days)
            top_pct: Percentage of recent losers to go long (reversal)
            bottom_pct: Percentage of recent winners to go short (reversal)
            long_only: If True, only generate long signals
        """
        super().__init__(
            universe,
            timeframe,
            lookback_period=lookback_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            **params,
        )
        self.lookback_period = lookback_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only

    def get_required_history(self) -> int:
        return self.lookback_period + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate short-term reversal signals."""
        if not isinstance(data, dict):
            return []

        recent_returns = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]
            ret = close.iloc[-1] / close.iloc[-self.lookback_period - 1] - 1
            recent_returns[symbol] = ret

        if len(recent_returns) < 5:
            return []

        # Sort by recent return (reversal: buy losers, sell winners)
        sorted_symbols = sorted(recent_returns.keys(), key=lambda x: recent_returns[x])

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        # Long recent losers (reversal), short recent winners
        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        values = list(recent_returns.values())
        mean_ret = np.mean(values)
        std_ret = np.std(values) if len(values) > 1 else 1.0

        ts = timestamp or datetime.now()
        signals = []

        for symbol in long_symbols:
            z_score = (mean_ret - recent_returns[symbol]) / std_ret if std_ret > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, abs(strength))),
                    confidence=0.5,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": FactorType.REVERSAL.value,
                        "recent_return": float(recent_returns[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        for symbol in short_symbols:
            z_score = (recent_returns[symbol] - mean_ret) / std_ret if std_ret > 0 else 0
            strength = np.tanh(z_score / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, -abs(strength))),
                    confidence=0.5,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": FactorType.REVERSAL.value,
                        "recent_return": float(recent_returns[symbol]),
                        "z_score": float(z_score),
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        return signals


class MultiFactorStrategy(RuleBasedStrategy):
    """
    Multi-factor combination strategy.

    Combines multiple factor scores (momentum, value, quality, low-vol)
    with configurable weights to generate composite signals.

    Based on modern factor investing approaches.
    """

    name = "multi_factor"
    description = "Multi-factor combination strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        factor_weights: dict[str, float] | None = None,
        momentum_period: int = 252,
        momentum_skip: int = 21,
        value_period: int = 252,
        volatility_period: int = 63,
        quality_period: int = 252,
        top_pct: float = 0.20,
        bottom_pct: float = 0.20,
        long_only: bool = False,
        z_score_clip: float = 3.0,
        **params: Any,
    ):
        """
        Initialize multi-factor strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            factor_weights: Dict of factor weights (momentum, value, volatility, quality)
            momentum_period: Lookback for momentum
            momentum_skip: Skip period for momentum
            value_period: Lookback for value metrics
            volatility_period: Lookback for volatility
            quality_period: Lookback for quality metrics
            top_pct: Percentage of top composite scores to go long
            bottom_pct: Percentage of bottom composite scores to go short
            long_only: If True, only generate long signals
            z_score_clip: Clip z-scores at this value
        """
        # Default equal weights
        default_weights = {
            "momentum": 0.30,
            "value": 0.20,
            "volatility": 0.25,
            "quality": 0.25,
        }
        self.factor_weights = factor_weights or default_weights

        super().__init__(
            universe,
            timeframe,
            factor_weights=self.factor_weights,
            momentum_period=momentum_period,
            momentum_skip=momentum_skip,
            value_period=value_period,
            volatility_period=volatility_period,
            quality_period=quality_period,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            long_only=long_only,
            z_score_clip=z_score_clip,
            **params,
        )
        self.momentum_period = momentum_period
        self.momentum_skip = momentum_skip
        self.value_period = value_period
        self.volatility_period = volatility_period
        self.quality_period = quality_period
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct
        self.long_only = long_only
        self.z_score_clip = z_score_clip

    def get_required_history(self) -> int:
        return max(
            self.momentum_period + self.momentum_skip,
            self.value_period,
            self.volatility_period,
            self.quality_period,
        ) + 10

    def _calculate_factor_scores(
        self,
        data: dict[Symbol, pd.DataFrame],
    ) -> dict[Symbol, dict[str, float]]:
        """Calculate individual factor scores for each symbol."""
        factor_scores: dict[Symbol, dict[str, float]] = {}

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            close = df["close"]
            high = df["high"]
            returns = close.pct_change()

            scores = {}

            # Momentum (higher = better)
            end_idx = -self.momentum_skip if self.momentum_skip > 0 else None
            start_idx = -self.momentum_period - self.momentum_skip

            if end_idx:
                mom_return = close.iloc[end_idx] / close.iloc[start_idx] - 1
            else:
                mom_return = close.iloc[-1] / close.iloc[start_idx] - 1

            vol_for_mom = returns.iloc[-63:].std() * np.sqrt(252)
            scores["momentum"] = mom_return / max(vol_for_mom, 0.01)

            # Value (lower price relative to high = better, but we want higher = better)
            high_52w = high.iloc[-self.value_period:].max()
            dist_from_high = (close.iloc[-1] - high_52w) / high_52w
            scores["value"] = -dist_from_high  # Negate so lower price = higher score

            # Volatility (lower = better, negate so higher score = better)
            vol = returns.iloc[-self.volatility_period:].std() * np.sqrt(252)
            scores["volatility"] = -vol

            # Quality
            pct_positive = (returns.iloc[-self.quality_period:] > 0).mean()
            mean_ret = returns.iloc[-self.quality_period:].mean() * 252
            std_ret = returns.iloc[-self.quality_period:].std() * np.sqrt(252)
            sharpe = mean_ret / std_ret if std_ret > 0.01 else 0
            scores["quality"] = (pct_positive + (sharpe + 1) / 2) / 2

            factor_scores[symbol] = scores

        return factor_scores

    def _z_score_factors(
        self,
        factor_scores: dict[Symbol, dict[str, float]],
    ) -> dict[Symbol, dict[str, float]]:
        """Convert raw factor scores to z-scores."""
        if not factor_scores:
            return {}

        factors = list(next(iter(factor_scores.values())).keys())
        z_scores: dict[Symbol, dict[str, float]] = {s: {} for s in factor_scores}

        for factor in factors:
            values = [factor_scores[s][factor] for s in factor_scores]
            mean_val = np.mean(values)
            std_val = np.std(values) if len(values) > 1 else 1.0

            for symbol in factor_scores:
                raw = factor_scores[symbol][factor]
                z = (raw - mean_val) / std_val if std_val > 0 else 0
                z = np.clip(z, -self.z_score_clip, self.z_score_clip)
                z_scores[symbol][factor] = z

        return z_scores

    def _calculate_composite_scores(
        self,
        z_scores: dict[Symbol, dict[str, float]],
    ) -> dict[Symbol, float]:
        """Calculate weighted composite scores."""
        composite = {}

        for symbol, scores in z_scores.items():
            weighted_sum = 0.0
            total_weight = 0.0

            for factor, weight in self.factor_weights.items():
                if factor in scores:
                    weighted_sum += scores[factor] * weight
                    total_weight += weight

            composite[symbol] = weighted_sum / total_weight if total_weight > 0 else 0

        return composite

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate multi-factor signals."""
        if not isinstance(data, dict):
            return []

        # Calculate factor scores
        raw_scores = self._calculate_factor_scores(data)
        if len(raw_scores) < 5:
            return []

        # Z-score normalize
        z_scores = self._z_score_factors(raw_scores)

        # Calculate composite
        composite_scores = self._calculate_composite_scores(z_scores)

        # Rank by composite score (higher = better)
        sorted_symbols = sorted(composite_scores.keys(), key=lambda x: composite_scores[x], reverse=True)

        n_assets = len(sorted_symbols)
        n_long = max(1, int(n_assets * self.top_pct))
        n_short = max(1, int(n_assets * self.bottom_pct))

        long_symbols = sorted_symbols[:n_long]
        short_symbols = sorted_symbols[-n_short:] if not self.long_only else []

        ts = timestamp or datetime.now()
        signals = []

        for symbol in long_symbols:
            composite = composite_scores[symbol]
            strength = np.tanh(composite / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.1, min(1.0, strength)),
                    confidence=0.65,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "factor": "multi_factor",
                        "composite_score": float(composite),
                        "factor_z_scores": z_scores[symbol],
                        "factor_weights": self.factor_weights,
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        for symbol in short_symbols:
            composite = composite_scores[symbol]
            strength = np.tanh(composite / 2)

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=min(-0.1, max(-1.0, strength)),
                    confidence=0.65,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "factor": "multi_factor",
                        "composite_score": float(composite),
                        "factor_z_scores": z_scores[symbol],
                        "factor_weights": self.factor_weights,
                        "rank": sorted_symbols.index(symbol) + 1,
                    },
                )
            )

        return signals


def calculate_factor_exposures(
    returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate factor exposures (betas) for a set of assets.

    Uses OLS regression of asset returns on factor returns.

    Args:
        returns: DataFrame of asset returns (columns = assets)
        factor_returns: DataFrame of factor returns (columns = factors)

    Returns:
        DataFrame of factor exposures (rows = assets, columns = factors)
    """
    from scipy import stats

    # Align dates
    common_dates = returns.index.intersection(factor_returns.index)
    returns = returns.loc[common_dates]
    factor_returns = factor_returns.loc[common_dates]

    exposures = {}

    for asset in returns.columns:
        asset_ret = returns[asset].dropna()
        asset_exposures = {}

        for factor in factor_returns.columns:
            factor_ret = factor_returns[factor].loc[asset_ret.index].dropna()
            common = asset_ret.index.intersection(factor_ret.index)

            if len(common) < 30:
                asset_exposures[factor] = np.nan
                continue

            slope, _, r_value, p_value, std_err = stats.linregress(
                factor_ret.loc[common],
                asset_ret.loc[common],
            )

            asset_exposures[factor] = slope
            asset_exposures[f"{factor}_t_stat"] = slope / std_err if std_err > 0 else 0
            asset_exposures[f"{factor}_r2"] = r_value**2

        exposures[asset] = asset_exposures

    return pd.DataFrame(exposures).T


def construct_factor_portfolio(
    data: dict[Symbol, pd.DataFrame],
    factor: FactorType,
    long_weight: float = 1.0,
    short_weight: float = -1.0,
    n_long: int = 10,
    n_short: int = 10,
) -> dict[Symbol, float]:
    """
    Construct a long-short factor portfolio.

    Args:
        data: Dict mapping symbols to OHLCV DataFrames
        factor: Factor type to use for ranking
        long_weight: Total weight for long positions
        short_weight: Total weight for short positions
        n_long: Number of long positions
        n_short: Number of short positions

    Returns:
        Dict mapping symbols to portfolio weights
    """
    # Use appropriate strategy based on factor
    strategy_map = {
        FactorType.MOMENTUM: CrossSectionalMomentumStrategy,
        FactorType.VALUE: ValueStrategy,
        FactorType.VOLATILITY: LowVolatilityStrategy,
        FactorType.QUALITY: QualityStrategy,
        FactorType.REVERSAL: ShortTermReversalStrategy,
    }

    universe = list(data.keys())
    n_assets = len(universe)

    if factor not in strategy_map:
        raise ValueError(f"Unknown factor: {factor}")

    strategy_class = strategy_map[factor]
    strategy = strategy_class(
        universe=universe,
        top_pct=n_long / n_assets,
        bottom_pct=n_short / n_assets,
        long_only=False,
    )

    signals = strategy.generate_signals(data)

    weights = {}
    long_signals = [s for s in signals if s.direction == Direction.LONG]
    short_signals = [s for s in signals if s.direction == Direction.SHORT]

    # Equal weight within long/short legs
    for signal in long_signals:
        weights[signal.symbol] = long_weight / len(long_signals)

    for signal in short_signals:
        weights[signal.symbol] = short_weight / len(short_signals)

    return weights
