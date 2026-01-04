"""
Analysis runner for Claude Code.

Provides simple entry points for running analyses with automatic
session management and artifact persistence.

All outputs are saved to ~/quant_results/ for easy viewing.

Main Entry Points:
    - analyze_strategy_mcpt: Run MCPT analysis with visualizations
    - screen_stocks: Run stock screening with alt data
    - find_budget_picks: Find undervalued stocks using alt data
    - list_recent_sessions: View past analysis sessions
    - load_session: Load results from a previous session

Example Usage:
    from workflows.runner import analyze_strategy_mcpt, list_recent_sessions

    # Run MCPT analysis
    result = await analyze_strategy_mcpt(
        strategy_name="SMA_10_30",
        strategy_returns=backtest.returns,
        permutation_returns=[p.returns for p in permuted],
        symbols=["AAPL", "NVDA"]
    )
    print(f"Report at: {result.session.session_path}/report.html")

    # List recent sessions
    sessions = list_recent_sessions(limit=10)
    for s in sessions:
        print(f"{s['session_id']}: {s['name']}")
"""

from .session import (
    Session,
    SessionConfig,
    SessionManager,
    SessionResult,
    create_session,
    get_results_dir,
    list_sessions,
    load_session,
)
from .runner import (
    AnalysisResult,
    AnalysisRunner,
    analyze_strategy_mcpt,
    screen_stocks,
)
from ..screeners.composite_screener import (
    CompositeScreener,
    CompositeScore,
    ScreenerSignal,
    find_budget_picks,
    screen_momentum,
)

# Alias for convenience
list_recent_sessions = list_sessions

__all__ = [
    # Session management
    "Session",
    "SessionConfig",
    "SessionManager",
    "SessionResult",
    "create_session",
    "list_sessions",
    "list_recent_sessions",
    "load_session",
    "get_results_dir",
    # Analysis runner
    "AnalysisResult",
    "AnalysisRunner",
    "analyze_strategy_mcpt",
    "screen_stocks",
    # Screeners
    "CompositeScreener",
    "CompositeScore",
    "ScreenerSignal",
    "find_budget_picks",
    "screen_momentum",
]
