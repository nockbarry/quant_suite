"""VWAP (Volume Weighted Average Price) intraday strategy.

VWAP is a key institutional benchmark. Price relative to VWAP
often indicates whether buyers or sellers are in control.

Strategy logic:
- Long: Price pulls back to VWAP from above, bounces with volume
- Short: Price rallies to VWAP from below, rejects with volume
- Uses volume confirmation and session timing
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


class VWAPStrategy(IntradayStrategy):
    """
    VWAP mean reversion strategy.

    Trades pullbacks to VWAP with volume confirmation.
    """

    name = "vwap_bounce"
    description = "VWAP pullback/bounce strategy with volume confirmation"
    version = "1.0.0"

    def __init__(
        self,
        config: IntradayStrategyConfig | None = None,
        vwap_deviation_pct: float = 0.3,  # Enter when within 0.3% of VWAP
        min_volume_ratio: float = 1.2,  # Volume must be 1.2x average
        stop_loss_atr_mult: float = 1.5,  # Stop at 1.5x ATR from entry
        take_profit_atr_mult: float = 2.5,  # Target at 2.5x ATR
        atr_period: int = 14,
    ):
        """
        Initialize VWAP strategy.

        Args:
            config: Strategy configuration
            vwap_deviation_pct: Max deviation from VWAP to enter
            min_volume_ratio: Minimum volume vs average
            stop_loss_atr_mult: Stop loss in ATR multiples
            take_profit_atr_mult: Take profit in ATR multiples
            atr_period: ATR calculation period
        """
        config = config or IntradayStrategyConfig(
            name="vwap_bounce",
            universe=["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
        )
        super().__init__(config)

        self.vwap_deviation_pct = vwap_deviation_pct
        self.min_volume_ratio = min_volume_ratio
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_atr_mult = take_profit_atr_mult
        self.atr_period = atr_period

    def get_required_bars(self) -> int:
        """Need bars since market open + ATR period."""
        return 78 + self.atr_period  # 78 bars = full session at 5-min

    def generate_signals(
        self,
        data: pd.DataFrame,
        timestamp: datetime | None = None,
    ) -> list[IntradaySignal]:
        """
        Generate VWAP bounce signals.

        Args:
            data: Minute OHLCV data with columns: open, high, low, close, volume
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

        # Calculate VWAP and ATR
        vwap = self._calculate_vwap(data)
        atr = self._calculate_atr(data, self.atr_period)

        if vwap is None or atr is None or atr == 0:
            return signals

        # Current price data
        close = data["close"].iloc[-1]
        volume = data["volume"].iloc[-1]
        avg_volume = data["volume"].rolling(20).mean().iloc[-1]

        # Price relative to VWAP
        vwap_deviation = (close - vwap) / vwap * 100
        volume_ratio = volume / avg_volume if avg_volume > 0 else 0

        # Trend context (last hour)
        hourly_trend = self._get_trend(data, periods=12)  # 12 5-min bars = 1 hour

        # Generate signal
        symbol = data.get("symbol", data.index.name) or "UNKNOWN"

        # Long signal: Price near/below VWAP, uptrend context, volume confirmation
        if (
            -self.vwap_deviation_pct <= vwap_deviation <= self.vwap_deviation_pct
            and hourly_trend > 0
            and volume_ratio >= self.min_volume_ratio
            and self._is_bouncing_up(data)
        ):
            stop_loss = close - (atr * self.stop_loss_atr_mult)
            take_profit = close + (atr * self.take_profit_atr_mult)

            strength = min(1.0, 0.5 + volume_ratio * 0.2 + hourly_trend * 0.3)
            confidence = min(1.0, 0.6 + (self.vwap_deviation_pct - abs(vwap_deviation)) * 0.5)

            signals.append(self.create_signal(
                symbol=symbol,
                direction=Direction.LONG,
                entry_price=close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strength=strength,
                confidence=confidence,
                reason=f"VWAP bounce long: {vwap_deviation:.2f}% from VWAP, vol {volume_ratio:.1f}x",
                timestamp=timestamp,
                vwap=vwap,
                vwap_deviation=vwap_deviation,
                volume_ratio=volume_ratio,
                atr=atr,
                hourly_trend=hourly_trend,
            ))

        # Short signal: Price near/above VWAP, downtrend context, volume confirmation
        elif (
            -self.vwap_deviation_pct <= vwap_deviation <= self.vwap_deviation_pct
            and hourly_trend < 0
            and volume_ratio >= self.min_volume_ratio
            and self._is_bouncing_down(data)
        ):
            stop_loss = close + (atr * self.stop_loss_atr_mult)
            take_profit = close - (atr * self.take_profit_atr_mult)

            strength = min(1.0, 0.5 + volume_ratio * 0.2 + abs(hourly_trend) * 0.3)
            confidence = min(1.0, 0.6 + (self.vwap_deviation_pct - abs(vwap_deviation)) * 0.5)

            signals.append(self.create_signal(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_price=close,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strength=-strength,
                confidence=confidence,
                reason=f"VWAP rejection short: {vwap_deviation:.2f}% from VWAP, vol {volume_ratio:.1f}x",
                timestamp=timestamp,
                vwap=vwap,
                vwap_deviation=vwap_deviation,
                volume_ratio=volume_ratio,
                atr=atr,
                hourly_trend=hourly_trend,
            ))

        return signals

    def _calculate_vwap(self, data: pd.DataFrame) -> float | None:
        """Calculate VWAP from session data."""
        if "volume" not in data.columns:
            return None

        # Filter to today's data only
        # In real usage, data should already be filtered to current session

        typical_price = (data["high"] + data["low"] + data["close"]) / 3
        cumulative_volume = data["volume"].cumsum()
        cumulative_tp_vol = (typical_price * data["volume"]).cumsum()

        if cumulative_volume.iloc[-1] == 0:
            return None

        vwap = cumulative_tp_vol.iloc[-1] / cumulative_volume.iloc[-1]
        return float(vwap)

    def _calculate_atr(self, data: pd.DataFrame, period: int) -> float | None:
        """Calculate Average True Range."""
        if len(data) < period:
            return None

        high = data["high"]
        low = data["low"]
        close = data["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]

        return float(atr) if not pd.isna(atr) else None

    def _get_trend(self, data: pd.DataFrame, periods: int) -> float:
        """
        Get trend direction over recent periods.

        Returns:
            Value from -1 (strong down) to 1 (strong up)
        """
        if len(data) < periods:
            return 0

        recent = data["close"].iloc[-periods:]
        if len(recent) < 2:
            return 0

        # Simple linear regression slope
        x = np.arange(len(recent))
        slope, _ = np.polyfit(x, recent, 1)

        # Normalize by price
        normalized_slope = slope / recent.mean() * 100

        # Clip to -1, 1
        return float(np.clip(normalized_slope, -1, 1))

    def _is_bouncing_up(self, data: pd.DataFrame) -> bool:
        """Check if price is bouncing up (for long entry)."""
        if len(data) < 3:
            return False

        # Last 3 candles: down, down, up (bounce pattern)
        c1 = data["close"].iloc[-3]
        c2 = data["close"].iloc[-2]
        c3 = data["close"].iloc[-1]

        # Or: lower wick (buying pressure)
        last_candle = data.iloc[-1]
        lower_wick = last_candle["close"] - last_candle["low"]
        body = abs(last_candle["close"] - last_candle["open"])

        has_buying_wick = lower_wick > body * 1.5 if body > 0 else False

        return (c1 > c2 and c3 > c2) or has_buying_wick

    def _is_bouncing_down(self, data: pd.DataFrame) -> bool:
        """Check if price is bouncing down (for short entry)."""
        if len(data) < 3:
            return False

        c1 = data["close"].iloc[-3]
        c2 = data["close"].iloc[-2]
        c3 = data["close"].iloc[-1]

        # Upper wick (selling pressure)
        last_candle = data.iloc[-1]
        upper_wick = last_candle["high"] - last_candle["close"]
        body = abs(last_candle["close"] - last_candle["open"])

        has_selling_wick = upper_wick > body * 1.5 if body > 0 else False

        return (c1 < c2 and c3 < c2) or has_selling_wick
