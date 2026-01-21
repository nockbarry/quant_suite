"""
Live Signal Generator

Operationalizes validated signals for real-time trading:
- Bollinger Bands (IC=0.31) - contrarian bounce
- RSI Oversold (IC=0.20) - contrarian
- Stochastic (IC=0.21) - contrarian
- Williams %R (IC=0.21) - contrarian
- Volume Spike (IC=-0.69) - CONTRARIAN (fade the move)
- Channel Breakout (IC=-0.37) - CONTRARIAN (fade the breakout)
- Mean Reversion (IC=0.06) - weak but usable

Includes signal convergence detection for high-confidence setups.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np


class SignalType(Enum):
    """Types of validated signals."""
    BOLLINGER_BOUNCE = "bollinger_bounce"
    RSI_EXTREME = "rsi_extreme"
    STOCHASTIC_EXTREME = "stochastic_extreme"
    WILLIAMS_R_EXTREME = "williams_r_extreme"
    VOLUME_SPIKE_FADE = "volume_spike_fade"  # Contrarian
    CHANNEL_BREAKOUT_FADE = "channel_breakout_fade"  # Contrarian
    MEAN_REVERSION = "mean_reversion"
    VWAP_BOUNCE = "vwap_bounce"  # Intraday
    ORB_FADE = "orb_fade"  # Intraday - fade failed breakouts


class SignalDirection(Enum):
    """Signal direction."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalStrength(Enum):
    """Signal strength based on validation metrics."""
    STRONG = "strong"  # IC > 0.25 or convergence
    MODERATE = "moderate"  # IC 0.15-0.25
    WEAK = "weak"  # IC < 0.15


@dataclass
class LiveSignal:
    """A real-time trading signal."""
    timestamp: datetime
    symbol: str
    signal_type: SignalType
    direction: SignalDirection
    strength: SignalStrength

    # Signal details
    price_at_signal: float
    trigger_value: float  # The indicator value that triggered
    threshold: float  # The threshold that was crossed

    # Validation metrics (from backtest)
    historical_ic: float
    historical_hit_rate: float
    historical_sharpe: float

    # Context
    description: str
    trading_implication: str
    suggested_action: str

    # Risk management
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None
    max_position_pct: float = 5.0  # Max position size %

    # Convergence
    converging_signals: list[str] = field(default_factory=list)
    convergence_score: int = 1  # Number of aligned signals

    # Expiry
    valid_until: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "direction": self.direction.value,
            "strength": self.strength.value,
            "price_at_signal": self.price_at_signal,
            "trigger_value": self.trigger_value,
            "threshold": self.threshold,
            "historical_ic": self.historical_ic,
            "historical_hit_rate": self.historical_hit_rate,
            "historical_sharpe": self.historical_sharpe,
            "description": self.description,
            "trading_implication": self.trading_implication,
            "suggested_action": self.suggested_action,
            "suggested_stop": self.suggested_stop,
            "suggested_target": self.suggested_target,
            "max_position_pct": self.max_position_pct,
            "converging_signals": self.converging_signals,
            "convergence_score": self.convergence_score,
        }


@dataclass
class SignalConvergence:
    """Multiple signals aligned on same symbol."""
    timestamp: datetime
    symbol: str
    direction: SignalDirection
    signals: list[LiveSignal]
    convergence_score: int
    combined_confidence: float

    # Summary
    summary: str
    recommendation: str


class LiveSignalGenerator:
    """
    Generates real-time signals from validated indicators.
    """

    # Validation metrics from backtest
    SIGNAL_METRICS = {
        SignalType.BOLLINGER_BOUNCE: {"ic": 0.31, "hit_rate": 0.614, "sharpe": 1.17},
        SignalType.RSI_EXTREME: {"ic": 0.20, "hit_rate": 0.538, "sharpe": 0.41},
        SignalType.STOCHASTIC_EXTREME: {"ic": 0.21, "hit_rate": 0.540, "sharpe": 0.27},
        SignalType.WILLIAMS_R_EXTREME: {"ic": 0.21, "hit_rate": 0.540, "sharpe": 0.27},
        SignalType.VOLUME_SPIKE_FADE: {"ic": 0.69, "hit_rate": 0.684, "sharpe": 3.44},  # Inverted
        SignalType.CHANNEL_BREAKOUT_FADE: {"ic": 0.37, "hit_rate": 0.605, "sharpe": 1.08},  # Inverted
        SignalType.MEAN_REVERSION: {"ic": 0.06, "hit_rate": 0.500, "sharpe": 0.25},
    }

    def __init__(self):
        self.recent_signals: dict[str, list[LiveSignal]] = {}  # By symbol

    def generate_bollinger_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate Bollinger Band bounce signal.
        BULLISH when price touches lower band, BEARISH when touching upper band.
        """
        if len(df) < 25:
            return None

        close = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        std20 = df['Close'].rolling(20).std().iloc[-1]

        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20

        # Position within bands (-1 to +1)
        bb_position = (close - ma20) / (2 * std20) if std20 > 0 else 0

        if bb_position < -0.9:  # Near lower band
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.BOLLINGER_BOUNCE,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.STRONG,
                price_at_signal=close,
                trigger_value=bb_position,
                threshold=-0.9,
                historical_ic=0.31,
                historical_hit_rate=0.614,
                historical_sharpe=1.17,
                description=f"Price at lower Bollinger Band (BB position: {bb_position:.2f})",
                trading_implication="Oversold condition - expect mean reversion bounce",
                suggested_action="BUY on confirmation, target middle band",
                suggested_stop=lower - (upper - lower) * 0.1,
                suggested_target=ma20,
                max_position_pct=7.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif bb_position > 0.9:  # Near upper band
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.BOLLINGER_BOUNCE,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.STRONG,
                price_at_signal=close,
                trigger_value=bb_position,
                threshold=0.9,
                historical_ic=0.31,
                historical_hit_rate=0.614,
                historical_sharpe=1.17,
                description=f"Price at upper Bollinger Band (BB position: {bb_position:.2f})",
                trading_implication="Overbought condition - expect mean reversion pullback",
                suggested_action="SELL/SHORT on confirmation, target middle band",
                suggested_stop=upper + (upper - lower) * 0.1,
                suggested_target=ma20,
                max_position_pct=7.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_rsi_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate RSI extreme signal.
        BULLISH when RSI < 30 (oversold), BEARISH when RSI > 70 (overbought).
        """
        if len(df) < 20:
            return None

        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        current_rsi = rsi.iloc[-1]
        close = df['Close'].iloc[-1]

        if current_rsi < 30:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.RSI_EXTREME,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_rsi,
                threshold=30,
                historical_ic=0.20,
                historical_hit_rate=0.538,
                historical_sharpe=0.41,
                description=f"RSI oversold at {current_rsi:.1f}",
                trading_implication="Oversold - contrarian buy opportunity",
                suggested_action="BUY when RSI turns up from oversold",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif current_rsi > 70:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.RSI_EXTREME,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_rsi,
                threshold=70,
                historical_ic=0.20,
                historical_hit_rate=0.538,
                historical_sharpe=0.41,
                description=f"RSI overbought at {current_rsi:.1f}",
                trading_implication="Overbought - contrarian sell opportunity",
                suggested_action="SELL/reduce when RSI turns down from overbought",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_stochastic_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate Stochastic oscillator signal.
        BULLISH when %K < 20, BEARISH when %K > 80.
        """
        if len(df) < 20:
            return None

        # Calculate Stochastic %K
        low14 = df['Low'].rolling(14).min()
        high14 = df['High'].rolling(14).max()
        stoch_k = 100 * (df['Close'] - low14) / (high14 - low14)

        current_k = stoch_k.iloc[-1]
        close = df['Close'].iloc[-1]

        if pd.isna(current_k):
            return None

        if current_k < 20:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.STOCHASTIC_EXTREME,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_k,
                threshold=20,
                historical_ic=0.21,
                historical_hit_rate=0.540,
                historical_sharpe=0.27,
                description=f"Stochastic oversold at {current_k:.1f}",
                trading_implication="Oversold - expect bounce",
                suggested_action="BUY on %K crossing above %D",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif current_k > 80:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.STOCHASTIC_EXTREME,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_k,
                threshold=80,
                historical_ic=0.21,
                historical_hit_rate=0.540,
                historical_sharpe=0.27,
                description=f"Stochastic overbought at {current_k:.1f}",
                trading_implication="Overbought - expect pullback",
                suggested_action="SELL on %K crossing below %D",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_williams_r_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate Williams %R signal.
        BULLISH when %R < -80, BEARISH when %R > -20.
        """
        if len(df) < 20:
            return None

        high14 = df['High'].rolling(14).max()
        low14 = df['Low'].rolling(14).min()
        williams_r = -100 * (high14 - df['Close']) / (high14 - low14)

        current_wr = williams_r.iloc[-1]
        close = df['Close'].iloc[-1]

        if pd.isna(current_wr):
            return None

        if current_wr < -80:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.WILLIAMS_R_EXTREME,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_wr,
                threshold=-80,
                historical_ic=0.21,
                historical_hit_rate=0.540,
                historical_sharpe=0.27,
                description=f"Williams %R oversold at {current_wr:.1f}",
                trading_implication="Oversold territory - contrarian buy",
                suggested_action="BUY when %R starts rising",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif current_wr > -20:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.WILLIAMS_R_EXTREME,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=current_wr,
                threshold=-20,
                historical_ic=0.21,
                historical_hit_rate=0.540,
                historical_sharpe=0.27,
                description=f"Williams %R overbought at {current_wr:.1f}",
                trading_implication="Overbought territory - contrarian sell",
                suggested_action="SELL when %R starts falling",
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_volume_spike_fade_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate CONTRARIAN volume spike signal.

        IMPORTANT: Validation showed volume spikes work INVERSELY (IC=-0.69).
        - High volume UP day → expect pullback → BEARISH
        - High volume DOWN day → expect bounce → BULLISH
        """
        if len(df) < 25:
            return None

        # Volume relative to 20-day average
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
        current_vol = df['Volume'].iloc[-1]
        vol_ratio = current_vol / vol_avg if vol_avg > 0 else 1

        # Daily return
        daily_return = (df['Close'].iloc[-1] / df['Close'].iloc[-2] - 1) if len(df) >= 2 else 0
        close = df['Close'].iloc[-1]

        # High volume threshold
        if vol_ratio < 2:
            return None

        # CONTRARIAN: Fade the volume spike
        if daily_return > 0.01:  # Up day with high volume → FADE IT (bearish)
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.VOLUME_SPIKE_FADE,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.STRONG,
                price_at_signal=close,
                trigger_value=vol_ratio,
                threshold=2.0,
                historical_ic=0.69,  # Inverted from -0.69
                historical_hit_rate=0.684,
                historical_sharpe=3.44,
                description=f"High volume UP day ({vol_ratio:.1f}x avg) - FADE signal",
                trading_implication="Volume spikes on up moves predict pullbacks",
                suggested_action="SELL/SHORT - expect mean reversion",
                max_position_pct=7.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif daily_return < -0.01:  # Down day with high volume → FADE IT (bullish)
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.VOLUME_SPIKE_FADE,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.STRONG,
                price_at_signal=close,
                trigger_value=vol_ratio,
                threshold=2.0,
                historical_ic=0.69,
                historical_hit_rate=0.684,
                historical_sharpe=3.44,
                description=f"High volume DOWN day ({vol_ratio:.1f}x avg) - FADE signal",
                trading_implication="Volume spikes on down moves predict bounces",
                suggested_action="BUY - expect mean reversion bounce",
                max_position_pct=7.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_channel_breakout_fade_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate CONTRARIAN channel breakout signal.

        IMPORTANT: Validation showed breakouts work INVERSELY (IC=-0.37).
        - Breakout above 20-day high → expect failure → BEARISH
        - Breakout below 20-day low → expect failure → BULLISH
        """
        if len(df) < 25:
            return None

        close = df['Close'].iloc[-1]
        high20 = df['High'].rolling(20).max().iloc[-2]  # Previous day's 20-day high
        low20 = df['Low'].rolling(20).min().iloc[-2]  # Previous day's 20-day low

        # CONTRARIAN: Fade the breakout
        if close > high20:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.CHANNEL_BREAKOUT_FADE,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=close,
                threshold=high20,
                historical_ic=0.37,  # Inverted from -0.37
                historical_hit_rate=0.605,
                historical_sharpe=1.08,
                description=f"Breakout above 20-day high ${high20:.2f} - FADE signal",
                trading_implication="Channel breakouts tend to fail - expect pullback",
                suggested_action="SELL/SHORT - fade the breakout",
                suggested_stop=close * 1.03,
                suggested_target=high20,
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif close < low20:
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.CHANNEL_BREAKOUT_FADE,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.MODERATE,
                price_at_signal=close,
                trigger_value=close,
                threshold=low20,
                historical_ic=0.37,
                historical_hit_rate=0.605,
                historical_sharpe=1.08,
                description=f"Breakout below 20-day low ${low20:.2f} - FADE signal",
                trading_implication="Channel breakouts tend to fail - expect bounce",
                suggested_action="BUY - fade the breakdown",
                suggested_stop=close * 0.97,
                suggested_target=low20,
                max_position_pct=5.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_mean_reversion_signal(self, df: pd.DataFrame, symbol: str) -> Optional[LiveSignal]:
        """
        Generate mean reversion signal based on distance from 20-day MA.
        """
        if len(df) < 25:
            return None

        close = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        distance_pct = (close - ma20) / ma20 * 100

        # Only trigger on significant deviations
        if abs(distance_pct) < 5:
            return None

        if distance_pct < -5:  # Far below MA
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.MEAN_REVERSION,
                direction=SignalDirection.BULLISH,
                strength=SignalStrength.WEAK,
                price_at_signal=close,
                trigger_value=distance_pct,
                threshold=-5,
                historical_ic=0.06,
                historical_hit_rate=0.500,
                historical_sharpe=0.25,
                description=f"Price {abs(distance_pct):.1f}% below 20-day MA",
                trading_implication="Extended move - expect reversion to mean",
                suggested_action="BUY with tight stop",
                suggested_target=ma20,
                max_position_pct=3.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        elif distance_pct > 5:  # Far above MA
            return LiveSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                signal_type=SignalType.MEAN_REVERSION,
                direction=SignalDirection.BEARISH,
                strength=SignalStrength.WEAK,
                price_at_signal=close,
                trigger_value=distance_pct,
                threshold=5,
                historical_ic=0.06,
                historical_hit_rate=0.500,
                historical_sharpe=0.25,
                description=f"Price {distance_pct:.1f}% above 20-day MA",
                trading_implication="Extended move - expect reversion to mean",
                suggested_action="SELL/reduce with tight stop",
                suggested_target=ma20,
                max_position_pct=3.0,
                valid_until=datetime.now() + timedelta(days=5),
            )

        return None

    def generate_all_signals(self, df: pd.DataFrame, symbol: str) -> list[LiveSignal]:
        """Generate all validated signals for a symbol."""
        signals = []

        # Generate each signal type
        generators = [
            self.generate_bollinger_signal,
            self.generate_rsi_signal,
            self.generate_stochastic_signal,
            self.generate_williams_r_signal,
            self.generate_volume_spike_fade_signal,
            self.generate_channel_breakout_fade_signal,
            self.generate_mean_reversion_signal,
        ]

        for generator in generators:
            try:
                signal = generator(df, symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                continue

        # Store recent signals
        self.recent_signals[symbol] = signals

        return signals

    def detect_convergence(self, signals: list[LiveSignal]) -> Optional[SignalConvergence]:
        """
        Detect when multiple signals converge on the same direction.
        3+ aligned signals = high confidence setup.
        """
        if len(signals) < 2:
            return None

        # Group by direction
        bullish = [s for s in signals if s.direction == SignalDirection.BULLISH]
        bearish = [s for s in signals if s.direction == SignalDirection.BEARISH]

        # Check for convergence (3+ signals aligned)
        if len(bullish) >= 3:
            # Calculate combined confidence
            avg_ic = np.mean([s.historical_ic for s in bullish])
            avg_hit_rate = np.mean([s.historical_hit_rate for s in bullish])

            # Update signals with convergence info
            signal_names = [s.signal_type.value for s in bullish]
            for s in bullish:
                s.converging_signals = signal_names
                s.convergence_score = len(bullish)

            return SignalConvergence(
                timestamp=datetime.now(),
                symbol=bullish[0].symbol,
                direction=SignalDirection.BULLISH,
                signals=bullish,
                convergence_score=len(bullish),
                combined_confidence=avg_hit_rate + 0.1 * (len(bullish) - 2),  # Bonus for convergence
                summary=f"{len(bullish)} BULLISH signals converging: {', '.join(signal_names)}",
                recommendation=f"HIGH CONFIDENCE BUY - {len(bullish)} validated signals aligned",
            )

        elif len(bearish) >= 3:
            avg_ic = np.mean([s.historical_ic for s in bearish])
            avg_hit_rate = np.mean([s.historical_hit_rate for s in bearish])

            signal_names = [s.signal_type.value for s in bearish]
            for s in bearish:
                s.converging_signals = signal_names
                s.convergence_score = len(bearish)

            return SignalConvergence(
                timestamp=datetime.now(),
                symbol=bearish[0].symbol,
                direction=SignalDirection.BEARISH,
                signals=bearish,
                convergence_score=len(bearish),
                combined_confidence=avg_hit_rate + 0.1 * (len(bearish) - 2),
                summary=f"{len(bearish)} BEARISH signals converging: {', '.join(signal_names)}",
                recommendation=f"HIGH CONFIDENCE SELL - {len(bearish)} validated signals aligned",
            )

        return None

    def scan_symbols(self, symbols: list[str], get_data_func) -> dict:
        """
        Scan multiple symbols for signals.

        Args:
            symbols: List of symbols to scan
            get_data_func: Function that takes symbol and returns DataFrame

        Returns:
            Dictionary with signals and convergences
        """
        all_signals = []
        convergences = []

        for symbol in symbols:
            try:
                df = get_data_func(symbol)
                if df is None or len(df) < 25:
                    continue

                signals = self.generate_all_signals(df, symbol)
                all_signals.extend(signals)

                # Check for convergence
                convergence = self.detect_convergence(signals)
                if convergence:
                    convergences.append(convergence)

            except Exception as e:
                continue

        # Sort by strength
        all_signals.sort(key=lambda s: (
            s.convergence_score,
            s.historical_ic,
            s.historical_hit_rate
        ), reverse=True)

        return {
            "signals": all_signals,
            "convergences": convergences,
            "total_signals": len(all_signals),
            "total_convergences": len(convergences),
            "bullish_count": sum(1 for s in all_signals if s.direction == SignalDirection.BULLISH),
            "bearish_count": sum(1 for s in all_signals if s.direction == SignalDirection.BEARISH),
        }


def get_signal_summary(signals: list[LiveSignal], convergences: list[SignalConvergence]) -> str:
    """Generate human-readable signal summary."""
    lines = []
    lines.append("=" * 60)
    lines.append("LIVE SIGNAL SUMMARY")
    lines.append("=" * 60)

    # Convergences first (highest priority)
    if convergences:
        lines.append("\n🎯 HIGH CONFIDENCE CONVERGENCES:")
        for conv in convergences:
            lines.append(f"\n  {conv.symbol} - {conv.direction.value.upper()}")
            lines.append(f"  {conv.summary}")
            lines.append(f"  → {conv.recommendation}")

    # Group signals by symbol
    by_symbol = {}
    for s in signals:
        if s.symbol not in by_symbol:
            by_symbol[s.symbol] = []
        by_symbol[s.symbol].append(s)

    lines.append(f"\n📊 ALL SIGNALS ({len(signals)} total):")

    for symbol, sym_signals in sorted(by_symbol.items()):
        bullish = [s for s in sym_signals if s.direction == SignalDirection.BULLISH]
        bearish = [s for s in sym_signals if s.direction == SignalDirection.BEARISH]

        lines.append(f"\n  {symbol}:")
        if bullish:
            lines.append(f"    BULLISH: {', '.join(s.signal_type.value for s in bullish)}")
        if bearish:
            lines.append(f"    BEARISH: {', '.join(s.signal_type.value for s in bearish)}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
