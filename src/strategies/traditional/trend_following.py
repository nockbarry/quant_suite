"""Trend following strategies."""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import RuleBasedStrategy


class MovingAverageCrossover(RuleBasedStrategy):
    """
    Moving Average Crossover strategy.

    Generates buy signals when fast MA crosses above slow MA,
    and sell signals when fast MA crosses below slow MA.
    """

    name = "ma_crossover"
    description = "Moving average crossover trend following strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        fast_period: int = 10,
        slow_period: int = 50,
        ma_type: str = "sma",
        **params: Any,
    ):
        """
        Initialize MA Crossover strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            fast_period: Fast MA period
            slow_period: Slow MA period
            ma_type: Type of MA - 'sma' or 'ema'
        """
        super().__init__(
            universe,
            timeframe,
            fast_period=fast_period,
            slow_period=slow_period,
            ma_type=ma_type,
            **params,
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.ma_type = ma_type

    def get_required_history(self) -> int:
        """Need enough history for slow MA plus a few extra bars."""
        return self.slow_period + 5

    def _calculate_ma(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate moving average."""
        if self.ma_type == "ema":
            return series.ewm(span=period, adjust=False).mean()
        return series.rolling(period).mean()

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on MA crossover.

        Args:
            data: OHLCV data
            timestamp: Current timestamp

        Returns:
            List of signals
        """
        signals = []

        # Handle both single DataFrame and dict of DataFrames
        if isinstance(data, dict):
            for symbol, df in data.items():
                signals.extend(self._generate_symbol_signals(symbol, df, timestamp))
        else:
            # Single symbol - assume first symbol in universe
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
        if len(df) < self.slow_period + 1:
            return []

        close = df["close"]
        fast_ma = self._calculate_ma(close, self.fast_period)
        slow_ma = self._calculate_ma(close, self.slow_period)

        # Get current and previous values
        fast_curr = fast_ma.iloc[-1]
        fast_prev = fast_ma.iloc[-2]
        slow_curr = slow_ma.iloc[-1]
        slow_prev = slow_ma.iloc[-2]

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Bullish crossover
        if fast_prev <= slow_prev and fast_curr > slow_curr:
            strength = (fast_curr - slow_curr) / slow_curr
            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=min(1.0, abs(strength) * 10),
                    confidence=0.7,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={
                        "fast_ma": float(fast_curr),
                        "slow_ma": float(slow_curr),
                        "crossover": "bullish",
                    },
                )
            )

        # Bearish crossover
        elif fast_prev >= slow_prev and fast_curr < slow_curr:
            strength = (slow_curr - fast_curr) / slow_curr
            signals.append(
                self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=-min(1.0, abs(strength) * 10),
                    confidence=0.7,
                    timestamp=ts,
                    signal_type=SignalType.ENTRY_SHORT,
                    metadata={
                        "fast_ma": float(fast_curr),
                        "slow_ma": float(slow_curr),
                        "crossover": "bearish",
                    },
                )
            )

        return signals


class BreakoutStrategy(RuleBasedStrategy):
    """
    Breakout strategy based on price channels.

    Generates buy signals when price breaks above N-day high,
    and sell signals when price breaks below N-day low.
    """

    name = "breakout"
    description = "Price channel breakout strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_period: int = 20,
        exit_period: int = 10,
        use_atr_filter: bool = True,
        atr_multiplier: float = 1.5,
        **params: Any,
    ):
        """
        Initialize Breakout strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_period: Period for channel calculation
            exit_period: Period for exit channel
            use_atr_filter: Use ATR filter for volatility
            atr_multiplier: ATR multiplier for breakout confirmation
        """
        super().__init__(
            universe,
            timeframe,
            lookback_period=lookback_period,
            exit_period=exit_period,
            use_atr_filter=use_atr_filter,
            atr_multiplier=atr_multiplier,
            **params,
        )
        self.lookback_period = lookback_period
        self.exit_period = exit_period
        self.use_atr_filter = use_atr_filter
        self.atr_multiplier = atr_multiplier

    def get_required_history(self) -> int:
        return self.lookback_period + 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate breakout signals."""
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
        if len(df) < self.lookback_period + 1:
            return []

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Calculate channels (exclude current bar)
        upper_channel = high.iloc[-self.lookback_period - 1 : -1].max()
        lower_channel = low.iloc[-self.lookback_period - 1 : -1].min()

        current_close = close.iloc[-1]
        prev_close = close.iloc[-2]

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Calculate ATR for volatility filter
        if self.use_atr_filter:
            tr = pd.concat([
                high - low,
                abs(high - close.shift(1)),
                abs(low - close.shift(1)),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            breakout_threshold = atr * self.atr_multiplier
        else:
            breakout_threshold = 0

        # Bullish breakout
        if current_close > upper_channel and prev_close <= upper_channel:
            if current_close - upper_channel > breakout_threshold or not self.use_atr_filter:
                strength = (current_close - upper_channel) / upper_channel
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=min(1.0, strength * 10),
                        confidence=0.75,
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_LONG,
                        metadata={
                            "breakout_level": float(upper_channel),
                            "breakout_type": "upper",
                        },
                    )
                )

        # Bearish breakout
        elif current_close < lower_channel and prev_close >= lower_channel:
            if lower_channel - current_close > breakout_threshold or not self.use_atr_filter:
                strength = (lower_channel - current_close) / lower_channel
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=-min(1.0, strength * 10),
                        confidence=0.75,
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_SHORT,
                        metadata={
                            "breakout_level": float(lower_channel),
                            "breakout_type": "lower",
                        },
                    )
                )

        return signals


class TrendStrengthStrategy(RuleBasedStrategy):
    """
    Trend strength strategy using ADX indicator.

    Only trades in the direction of strong trends as indicated by ADX.
    """

    name = "trend_strength"
    description = "ADX-based trend strength strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        ma_period: int = 20,
        **params: Any,
    ):
        """
        Initialize Trend Strength strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            adx_period: ADX calculation period
            adx_threshold: Minimum ADX for trend signal
            ma_period: MA period for trend direction
        """
        super().__init__(
            universe,
            timeframe,
            adx_period=adx_period,
            adx_threshold=adx_threshold,
            ma_period=ma_period,
            **params,
        )
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.ma_period = ma_period

    def get_required_history(self) -> int:
        return max(self.adx_period, self.ma_period) * 2 + 5

    def _calculate_adx(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate ADX, +DI, and -DI."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1)),
        ], axis=1).max(axis=1)

        # Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        # Smoothed values
        atr = tr.rolling(self.adx_period).mean()
        plus_di = 100 * (plus_dm.rolling(self.adx_period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(self.adx_period).mean() / atr)

        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(self.adx_period).mean()

        return adx, plus_di, minus_di

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate trend strength signals."""
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
        adx, plus_di, minus_di = self._calculate_adx(df)
        ma = close.rolling(self.ma_period).mean()

        current_adx = adx.iloc[-1]
        current_plus_di = plus_di.iloc[-1]
        current_minus_di = minus_di.iloc[-1]
        current_close = close.iloc[-1]
        current_ma = ma.iloc[-1]

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        signals = []

        # Only generate signals when trend is strong
        if current_adx >= self.adx_threshold:
            # Bullish: +DI > -DI and price above MA
            if current_plus_di > current_minus_di and current_close > current_ma:
                strength = (current_plus_di - current_minus_di) / 100
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=min(1.0, strength),
                        confidence=min(1.0, current_adx / 50),
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_LONG,
                        metadata={
                            "adx": float(current_adx),
                            "plus_di": float(current_plus_di),
                            "minus_di": float(current_minus_di),
                        },
                    )
                )

            # Bearish: -DI > +DI and price below MA
            elif current_minus_di > current_plus_di and current_close < current_ma:
                strength = (current_minus_di - current_plus_di) / 100
                signals.append(
                    self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=-min(1.0, strength),
                        confidence=min(1.0, current_adx / 50),
                        timestamp=ts,
                        signal_type=SignalType.ENTRY_SHORT,
                        metadata={
                            "adx": float(current_adx),
                            "plus_di": float(current_plus_di),
                            "minus_di": float(current_minus_di),
                        },
                    )
                )

        return signals


class MomentumStrategy(RuleBasedStrategy):
    """
    Time-series momentum strategy.

    Trades based on past returns over a lookback period.
    """

    name = "momentum"
    description = "Time-series momentum strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_period: int = 252,
        holding_period: int = 21,
        volatility_scaling: bool = True,
        **params: Any,
    ):
        """
        Initialize Momentum strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_period: Period for momentum calculation
            holding_period: Holding period
            volatility_scaling: Scale by volatility
        """
        super().__init__(
            universe,
            timeframe,
            lookback_period=lookback_period,
            holding_period=holding_period,
            volatility_scaling=volatility_scaling,
            **params,
        )
        self.lookback_period = lookback_period
        self.holding_period = holding_period
        self.volatility_scaling = volatility_scaling

    def get_required_history(self) -> int:
        return self.lookback_period + 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate momentum signals."""
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
        if len(df) < self.lookback_period + 1:
            return []

        close = df["close"]

        # Calculate momentum (past return)
        momentum = close.iloc[-1] / close.iloc[-self.lookback_period] - 1

        ts = timestamp or df.index[-1]
        if not isinstance(ts, datetime):
            ts = ts.to_pydatetime()

        # Volatility scaling
        if self.volatility_scaling:
            returns = close.pct_change()
            vol = returns.iloc[-63:].std() * np.sqrt(252)  # Annualized vol
            scaled_momentum = momentum / max(vol, 0.01)
        else:
            scaled_momentum = momentum

        # Convert to signal strength (-1 to 1)
        strength = np.tanh(scaled_momentum)

        if abs(strength) > 0.1:  # Minimum threshold
            direction = Direction.LONG if strength > 0 else Direction.SHORT
            signal_type = SignalType.ENTRY_LONG if strength > 0 else SignalType.ENTRY_SHORT

            return [
                self.create_signal(
                    symbol=symbol,
                    direction=direction,
                    strength=strength,
                    confidence=min(1.0, abs(strength)),
                    timestamp=ts,
                    signal_type=signal_type,
                    metadata={
                        "momentum": float(momentum),
                        "lookback": self.lookback_period,
                    },
                )
            ]

        return []
