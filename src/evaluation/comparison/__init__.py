"""Strategy Comparison Module.

Provides tools for comparing validated trading strategies.
"""

from .dashboard import (
    StrategyComparison,
    StrategyDashboard,
    get_strategy_leaderboard,
)

__all__ = [
    "StrategyComparison",
    "StrategyDashboard",
    "get_strategy_leaderboard",
]
