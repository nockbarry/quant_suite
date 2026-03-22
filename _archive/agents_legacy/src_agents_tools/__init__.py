"""LLM Agent Tools for the Quant Suite.

Provides structured interfaces for LLM agents to:
- Query and analyze market data
- Create and modify trading strategies
- Run backtests and evaluate performance
- Monitor live trading systems

All tools return structured JSON for easy LLM consumption.
"""

from .data_tools import (
    DataQueryTool,
    FeatureEngineTool,
    MarketAnalysisTool,
    get_market_data,
    get_features,
    get_correlation_matrix,
    get_market_summary,
    get_symbol_info,
)
from .strategy_tools import (
    StrategyBuilderTool,
    StrategyOptimizerTool,
    create_strategy,
    list_available_strategies,
    get_strategy_parameters,
    optimize_strategy,
    compose_strategies,
)
from .backtest_tools import (
    BacktestTool,
    BacktestAnalyzerTool,
    run_backtest,
    compare_strategies,
    analyze_trades,
    get_performance_attribution,
    run_walk_forward,
)
from .monitoring_tools import (
    PerformanceMonitor,
    AlertManager,
    get_live_performance,
    get_position_summary,
    check_risk_limits,
    get_recent_signals,
    get_system_status,
)

__all__ = [
    # Data tools
    "DataQueryTool",
    "FeatureEngineTool",
    "MarketAnalysisTool",
    "get_market_data",
    "get_features",
    "get_correlation_matrix",
    "get_market_summary",
    "get_symbol_info",
    # Strategy tools
    "StrategyBuilderTool",
    "StrategyOptimizerTool",
    "create_strategy",
    "list_available_strategies",
    "get_strategy_parameters",
    "optimize_strategy",
    "compose_strategies",
    # Backtest tools
    "BacktestTool",
    "BacktestAnalyzerTool",
    "run_backtest",
    "compare_strategies",
    "analyze_trades",
    "get_performance_attribution",
    "run_walk_forward",
    # Monitoring tools
    "PerformanceMonitor",
    "AlertManager",
    "get_live_performance",
    "get_position_summary",
    "check_risk_limits",
    "get_recent_signals",
    "get_system_status",
]
