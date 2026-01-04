"""Mean reversion strategies."""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import RuleBasedStrategy


class BollingerBandMeanReversion(RuleBasedStrategy):
    """
    Bollinger Band mean reversion strategy.

    Generates buy signals when price touches lower band,
    and sell signals when price touches upper band.
    """

    name = "bb_mean_reversion"
    description = "Bollinger Band mean reversion strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_filter: bool = True,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        **params: Any,
    ):
        """
        Initialize Bollinger Band strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            bb_period: Bollinger Band period
            bb_std: Standard deviation multiplier
            rsi_filter: Use RSI confirmation
            rsi_oversold: RSI oversold level
            rsi_overbought: RSI overbought level
        """
        super().__init__(
            universe,
            timeframe,
            bb_period=bb_period,
            bb_std=bb_std,
            rsi_filter=rsi_filter,
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            **params,
        )
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_filter = rsi_filter
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def get_required_history(self) -> int:
        return max(self.bb_period, 14) + 5

    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate Bollinger Band signals."""
        signals = []

        if isinstance(data, dict):
            for symbol, df in data.items():
                signals.extend(self._generate_symbol_signals(symbol, df, timestamp))
        else:
            if self.universe:
                signals.extend(
                    self._generate_symbol_signals(self.universe[0], data, timestamp)
                )

        return signals

    def _generate_symbol_signals(
        self,
        symbol: Symbol,
        df: pd.DataFrame,
        timestamp: datetime | None,
    ) -> list[Signal]:
        """Generate signals for a single symbol."""
        if len(df) < self.get_required_history():
            return []

        close = df["close"]

        # Calculate Bollinger Bands
        sma = close.rolling(self.bb_period).mean()
        std = close.rolling(self.bb_period).std()
        upper_band = sma + self.bb_std * std
        lower_band = sma - self.bb_std * std

        current_close = close.iloc[-1]
        current_upper = upper_band.iloc[-1]
        current_lower = lower_band.iloc[-1]
        current_sma = sma.iloc[-1]

        # Calculate %B (position within bands)
        pct_b = (current_close - current_lower) / (current_upper - current_lower)

        # RSI filter
        if self.rsi_filter:
            rsi = self._calculate_rsi(close)
            current_rsi = rsi.iloc[-1]
        else:
            current_rsi = 50  # Neutral

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Oversold: price near lower band and RSI oversold
        if pct_b < 0.1:
            if not self.rsi_filter or current_rsi < self.rsi_oversold:
                strength = 1 - pct_b  # Stronger signal when more oversold
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=min(1.0, strength),
                        confidence=0.7,
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_LONG,
                        metadata={
                            "pct_b": float(pct_b),
                            "rsi": float(current_rsi),
                            "lower_band": float(current_lower),
                        },
                    )
                )

        # Overbought: price near upper band and RSI overbought
        elif pct_b > 0.9:
            if not self.rsi_filter or current_rsi > self.rsi_overbought:
                strength = pct_b  # Stronger signal when more overbought
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=-min(1.0, strength),
                        confidence=0.7,
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_SHORT,
                        metadata={
                            "pct_b": float(pct_b),
                            "rsi": float(current_rsi),
                            "upper_band": float(current_upper),
                        },
                    )
                )

        return signals


class PairsTradingStrategy(RuleBasedStrategy):
    """
    Statistical arbitrage pairs trading strategy.

    Trades the spread between two correlated assets when
    it deviates from its historical mean.
    """

    name = "pairs_trading"
    description = "Statistical arbitrage pairs trading strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_period: int = 60,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.5,
        max_holding_period: int = 20,
        **params: Any,
    ):
        """
        Initialize Pairs Trading strategy.

        Note: Universe should contain exactly 2 symbols.

        Args:
            universe: List of 2 symbols to trade as a pair
            timeframe: Trading timeframe
            lookback_period: Period for spread calculation
            entry_zscore: Z-score threshold for entry
            exit_zscore: Z-score threshold for exit
            max_holding_period: Maximum holding period
        """
        if len(universe) != 2:
            raise ValueError("Pairs trading requires exactly 2 symbols")

        super().__init__(
            universe,
            timeframe,
            lookback_period=lookback_period,
            entry_zscore=entry_zscore,
            exit_zscore=exit_zscore,
            max_holding_period=max_holding_period,
            **params,
        )
        self.lookback_period = lookback_period
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.max_holding_period = max_holding_period
        self.hedge_ratio: float | None = None

    def get_required_history(self) -> int:
        return self.lookback_period + 10

    def _calculate_hedge_ratio(self, y: pd.Series, x: pd.Series) -> float:
        """Calculate hedge ratio using OLS regression."""
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        return slope

    def _calculate_spread(
        self,
        df1: pd.DataFrame,
        df2: pd.DataFrame,
    ) -> tuple[pd.Series, float, float, float]:
        """Calculate spread and statistics."""
        y = df1["close"]
        x = df2["close"]

        # Calculate hedge ratio on lookback period
        hedge_ratio = self._calculate_hedge_ratio(
            y.iloc[-self.lookback_period:],
            x.iloc[-self.lookback_period:],
        )

        # Calculate spread
        spread = y - hedge_ratio * x

        # Z-score
        spread_mean = spread.iloc[-self.lookback_period:].mean()
        spread_std = spread.iloc[-self.lookback_period:].std()
        zscore = (spread.iloc[-1] - spread_mean) / spread_std

        return spread, zscore, hedge_ratio, spread_std

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate pairs trading signals."""
        if not isinstance(data, dict):
            return []

        if len(data) != 2:
            return []

        symbols = list(data.keys())
        df1 = data[symbols[0]]
        df2 = data[symbols[1]]

        if len(df1) < self.get_required_history() or len(df2) < self.get_required_history():
            return []

        # Align data
        common_index = df1.index.intersection(df2.index)
        if len(common_index) < self.lookback_period:
            return []

        df1 = df1.loc[common_index]
        df2 = df2.loc[common_index]

        spread, zscore, hedge_ratio, spread_std = self._calculate_spread(df1, df2)
        self.hedge_ratio = hedge_ratio

        ts = timestamp or df1.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Spread is too high: short the spread (short symbol1, long symbol2)
        if zscore > self.entry_zscore:
            signals.extend([
                self.create_signal(
                    symbol=symbols[0],
                    direction=Direction.SHORT,
                    strength=-min(1.0, abs(zscore) / 3),
                    confidence=min(1.0, abs(zscore) / 4),
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "zscore": float(zscore),
                        "hedge_ratio": float(hedge_ratio),
                        "pair": symbols[1],
                        "position": "short_spread",
                    },
                ),
                self.create_signal(
                    symbol=symbols[1],
                    direction=Direction.LONG,
                    strength=min(1.0, abs(zscore) / 3),
                    confidence=min(1.0, abs(zscore) / 4),
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "zscore": float(zscore),
                        "hedge_ratio": float(hedge_ratio),
                        "pair": symbols[0],
                        "position": "short_spread",
                    },
                ),
            ])

        # Spread is too low: long the spread (long symbol1, short symbol2)
        elif zscore < -self.entry_zscore:
            signals.extend([
                self.create_signal(
                    symbol=symbols[0],
                    direction=Direction.LONG,
                    strength=min(1.0, abs(zscore) / 3),
                    confidence=min(1.0, abs(zscore) / 4),
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "zscore": float(zscore),
                        "hedge_ratio": float(hedge_ratio),
                        "pair": symbols[1],
                        "position": "long_spread",
                    },
                ),
                self.create_signal(
                    symbol=symbols[1],
                    direction=Direction.SHORT,
                    strength=-min(1.0, abs(zscore) / 3),
                    confidence=min(1.0, abs(zscore) / 4),
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "zscore": float(zscore),
                        "hedge_ratio": float(hedge_ratio),
                        "pair": symbols[0],
                        "position": "long_spread",
                    },
                ),
            ])

        # Exit signal: spread has mean-reverted
        elif abs(zscore) < self.exit_zscore:
            for symbol in symbols:
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.FLAT,
                        strength=0.0,
                        confidence=0.8,
                        timestamp=ts,
                        signal_type=SignalType.EXIT_LONG,
                        metadata={
                            "zscore": float(zscore),
                            "exit_reason": "mean_reversion",
                        },
                    )
                )

        return signals


class RSIMeanReversion(RuleBasedStrategy):
    """
    RSI-based mean reversion strategy.

    Trades when RSI reaches extreme levels indicating
    oversold or overbought conditions.
    """

    name = "rsi_mean_reversion"
    description = "RSI-based mean reversion strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        extreme_oversold: float = 20.0,
        extreme_overbought: float = 80.0,
        **params: Any,
    ):
        """
        Initialize RSI Mean Reversion strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            rsi_period: RSI calculation period
            oversold: Oversold threshold
            overbought: Overbought threshold
            extreme_oversold: Extreme oversold threshold
            extreme_overbought: Extreme overbought threshold
        """
        super().__init__(
            universe,
            timeframe,
            rsi_period=rsi_period,
            oversold=oversold,
            overbought=overbought,
            extreme_oversold=extreme_oversold,
            extreme_overbought=extreme_overbought,
            **params,
        )
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.extreme_oversold = extreme_oversold
        self.extreme_overbought = extreme_overbought

    def get_required_history(self) -> int:
        return self.rsi_period + 10

    def _calculate_rsi(self, series: pd.Series) -> pd.Series:
        """Calculate RSI."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate RSI signals."""
        signals = []

        if isinstance(data, dict):
            for symbol, df in data.items():
                signals.extend(self._generate_symbol_signals(symbol, df, timestamp))
        else:
            if self.universe:
                signals.extend(
                    self._generate_symbol_signals(self.universe[0], data, timestamp)
                )

        return signals

    def _generate_symbol_signals(
        self,
        symbol: Symbol,
        df: pd.DataFrame,
        timestamp: datetime | None,
    ) -> list[Signal]:
        """Generate signals for a single symbol."""
        if len(df) < self.get_required_history():
            return []

        close = df["close"]
        rsi = self._calculate_rsi(close)

        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Oversold with RSI turning up
        if current_rsi < self.oversold and current_rsi > prev_rsi:
            if current_rsi < self.extreme_oversold:
                strength = 1.0
                confidence = 0.8
            else:
                strength = (self.oversold - current_rsi) / (self.oversold - self.extreme_oversold)
                confidence = 0.6

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=min(1.0, strength),
                    confidence=confidence,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "rsi": float(current_rsi),
                        "condition": "oversold",
                    },
                )
            )

        # Overbought with RSI turning down
        elif current_rsi > self.overbought and current_rsi < prev_rsi:
            if current_rsi > self.extreme_overbought:
                strength = 1.0
                confidence = 0.8
            else:
                strength = (current_rsi - self.overbought) / (self.extreme_overbought - self.overbought)
                confidence = 0.6

            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=-min(1.0, strength),
                    confidence=confidence,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "rsi": float(current_rsi),
                        "condition": "overbought",
                    },
                )
            )

        return signals
