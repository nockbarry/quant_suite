"""
Live signal generation module.

Provides real-time trading signals from validated indicators:
- Bollinger Bands bounce (IC=0.31)
- RSI extremes (IC=0.20)
- Stochastic extremes (IC=0.21)
- Williams %R (IC=0.21)
- Volume spike FADE (IC=0.69 inverted)
- Channel breakout FADE (IC=0.37 inverted)
- Mean reversion (IC=0.06)

Includes signal convergence detection for high-confidence setups.
"""

from .live_signal_generator import (
    SignalType,
    SignalDirection,
    SignalStrength,
    LiveSignal,
    SignalConvergence,
    LiveSignalGenerator,
    get_signal_summary,
)

__all__ = [
    "SignalType",
    "SignalDirection",
    "SignalStrength",
    "LiveSignal",
    "SignalConvergence",
    "LiveSignalGenerator",
    "get_signal_summary",
]
