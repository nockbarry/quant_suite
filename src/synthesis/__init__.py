"""Synthesis Layer - Unified State Engine.

Aggregates all data sources, signals, and state into a single unified view
that can be read from one file.

Usage:
    from src.synthesis import UnifiedState, LiveDaemon

    # Read current state (preferred - one read)
    state = UnifiedState.load()

    # Or generate fresh state
    daemon = LiveDaemon()
    state = await daemon.update_now()
"""

from .state import (
    UnifiedState,
    MarketSnapshot,
    PortfolioSnapshot,
    PositionSnapshot,
    RiskSnapshot,
    SentimentSnapshot,
    CalendarEvent,
    ResearchIndex,
    ThesisSummary,
    PendingDecision,
    LearningSummary,
)
from .signals import AggregatedSignal, SignalAggregator
from .daemon import LiveDaemon
from .ml_signals import (
    MLSignal,
    MLSignalGenerator,
    add_ml_signals_to_aggregated,
    compute_ml_composite_signal,
)

__all__ = [
    # State
    "UnifiedState",
    "MarketSnapshot",
    "PortfolioSnapshot",
    "PositionSnapshot",
    "RiskSnapshot",
    "SentimentSnapshot",
    "CalendarEvent",
    "ResearchIndex",
    "ThesisSummary",
    "PendingDecision",
    "LearningSummary",
    # Signals
    "AggregatedSignal",
    "SignalAggregator",
    # Daemon
    "LiveDaemon",
    # ML Signals
    "MLSignal",
    "MLSignalGenerator",
    "add_ml_signals_to_aggregated",
    "compute_ml_composite_signal",
]
