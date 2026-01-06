"""Intraday momentum strategy.

Captures strong directional moves with volume confirmation.
Best used during opening bell and power hour when volume is high.

Strategy logic:
- Identifies strong momentum bars (large moves with high volume)
- Enters on continuation after pullback
- Uses ATR-based stops
"""

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction
from .base import (
    IntradayStrategy,
    IntradayStrategyConfig,
    IntradaySignal,
    SessionPhase,
    get_session_phase,
)


class IntradayMomentumStrategy(IntradayStrategy):
    """
    Intraday momentum continuation strategy.

    Trades momentum breakouts with volume confirmation.
    """

    name = "intraday_momentum"
    description = "Momentum continuation with volume confirmation"
    version = "1.0.0"

    def __init__(
        self,
        config: IntradayStrategyConfig | None = None,
        momentum_threshold: float = 0.5,  # Price move % to trigger
        volume_multiplier: float = 1.5,  # Volume vs average
        pullback_pct: float = 0.2,  # Pullback to enter
        atr_period: int = 14,
        stop_atr_mult: float = 1.0,
        target_atr_mult: float = 2.0,
        lookback_bars: int = 6,  # Bars to identify momentum
    ):
        """
        Initialize momentum strategy.

        Args:
            config: Strategy configuration
            momentum_threshold: % move to identify momentum
            volume_multiplier: Volume vs average for confirmation
            pullback_pct: % pullback from high/low to enter
            atr_period: ATR calculation period
            stop_atr_mult: Stop loss in ATR multiples
            target_atr_mult: Take profit in ATR multiples
            lookback_bars: Bars to look back for momentum
        """
        config = config or IntradayStrategyConfig(
            name="intraday_momentum",
            universe=["SPY", "QQQ", "AAPL", "NVDA", "AMD", "TSLA"],
            allowed_phases=[SessionPhase.OPENING, SessionPhase.POWER_HOUR],
        )
        super().__init__(config)

        self.momentum_threshold = momentum_threshold
        self.volume_multiplier = volume_multiplier
        self.pullback_pct = pullback_pct
        self.atr_period = atr_period
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        self.lookback_bars = lookback_bars

    def get_required_bars(self) -> int:
        """Required bars for calculations."""
        return max(self.atr_period, self.lookback_bars, 20) + 10

    def generate_signals(
        self,
        data: pd.DataFrame,
        timestamp: datetime | None = None,
    ) -> list[IntradaySignal]:
        """
        Generate momentum signals.

        Args:
            data: Minute OHLCV data
            timestamp: Current timestamp

        Returns:
            List of IntradaySignal objects
        """
        signals = []
        timestamp = timestamp or datetime.now()

        # Check trading conditions
        can_trade, reason = self.should_trade(timestamp)
        if not can_trade:
            return signals

        if len(data) < self.get_required_bars():
            return signals

        # Prefer opening and power hour
        phase = get_session_phase(timestamp)
        if phase not in [SessionPhase.OPENING, SessionPhase.POWER_HOUR]:
            return signals

        # Calculate indicators
        atr = self._calculate_atr(data)
        if atr is None or atr == 0:
            return signals

        # Identify momentum
        momentum_direction = self._identify_momentum(data)
        if momentum_direction == 0:
            return signals

        # Check for pullback entry
        entry_signal = self._check_pullback_entry(data, momentum_direction)
        if entry_signal is None:
            return signals

        symbol = data.get("symbol", data.index.name) or "UNKNOWN"
        close = data["close"].iloc[-1]

        # Calculate stops and targets
        if momentum_direction > 0:  # Long
            stop_loss = close - (atr * self.stop_atr_mult)
            take_profit = close + (atr * self.target_atr_mult)
            direction = Direction.LONG
        else:  # Short
            stop_loss = close + (atr * self.stop_atr_mult)
            take_profit = close - (atr * self.target_atr_mult)
            direction = Direction.SHORT

        # Signal strength based on momentum and volume
        strength = entry_signal.get("strength", 0.6)
        confidence = entry_signal.get("confidence", 0.6)

        signals.append(self.create_signal(
            symbol=symbol,
            direction=direction,
            entry_price=close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strength=strength * momentum_direction,
            confidence=confidence,
            reason=entry_signal.get("reason", "Momentum continuation"),
            timestamp=timestamp,
            atr=atr,
            momentum_bars=entry_signal.get("momentum_bars", 0),
            volume_ratio=entry_signal.get("volume_ratio", 1.0),
            pullback_from_high=entry_signal.get("pullback_pct", 0),
        ))

        return signals

    def _calculate_atr(self, data: pd.DataFrame) -> float | None:
        """Calculate ATR."""
        if len(data) < self.atr_period:
            return None

        high = data["high"]
        low = data["low"]
        close = data["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean().iloc[-1]

        return float(atr) if not pd.isna(atr) else None

    def _identify_momentum(self, data: pd.DataFrame) -> int:
        """
        Identify if there's recent momentum.

        Returns:
            1 for bullish momentum, -1 for bearish, 0 for none
        """
        recent = data.iloc[-self.lookback_bars:]

        # Calculate move over lookback period
        start_price = recent["close"].iloc[0]
        end_price = recent["close"].iloc[-1]
        move_pct = (end_price - start_price) / start_price * 100

        # Check volume
        avg_volume = data["volume"].rolling(20).mean().iloc[-1]
        recent_volume = recent["volume"].mean()
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 0

        # Need both move and volume
        if abs(move_pct) < self.momentum_threshold:
            return 0
        if volume_ratio < self.volume_multiplier:
            return 0

        return 1 if move_pct > 0 else -1

    def _check_pullback_entry(
        self,
        data: pd.DataFrame,
        momentum_direction: int,
    ) -> dict[str, Any] | None:
        """
        Check if there's a valid pullback entry.

        Returns:
            Entry signal dict or None
        """
        recent = data.iloc[-self.lookback_bars:]
        current_close = data["close"].iloc[-1]

        if momentum_direction > 0:  # Bullish - look for pullback from high
            session_high = recent["high"].max()
            pullback_pct = (session_high - current_close) / session_high * 100

            # Want a pullback but not too deep
            if not (self.pullback_pct * 0.5 <= pullback_pct <= self.pullback_pct * 2):
                return None

            # Check for reversal candle (buying)
            last = data.iloc[-1]
            if last["close"] <= last["open"]:  # Red candle - still pulling back
                return None

        else:  # Bearish - look for bounce from low
            session_low = recent["low"].min()
            pullback_pct = (current_close - session_low) / session_low * 100

            if not (self.pullback_pct * 0.5 <= pullback_pct <= self.pullback_pct * 2):
                return None

            # Check for reversal candle (selling)
            last = data.iloc[-1]
            if last["close"] >= last["open"]:  # Green candle - still bouncing
                return None

        # Calculate signal quality
        avg_volume = data["volume"].rolling(20).mean().iloc[-1]
        current_volume = data["volume"].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # Higher volume on reversal = stronger signal
        strength = min(1.0, 0.5 + volume_ratio * 0.2)
        confidence = min(1.0, 0.5 + (1 - pullback_pct / self.pullback_pct) * 0.3)

        return {
            "strength": strength,
            "confidence": confidence,
            "pullback_pct": pullback_pct,
            "volume_ratio": volume_ratio,
            "momentum_bars": self.lookback_bars,
            "reason": f"Momentum {'long' if momentum_direction > 0 else 'short'} pullback entry: "
                     f"{pullback_pct:.2f}% pullback, vol {volume_ratio:.1f}x",
        }
