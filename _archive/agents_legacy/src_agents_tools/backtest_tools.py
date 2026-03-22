"""Backtest tools for LLM agents.

Provides interfaces for running backtests, analyzing results, and comparing strategies.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ...core import Symbol
from ...strategies.base import Strategy
from ...evaluation.backtest import VectorizedBacktest, BacktestConfig, BacktestResult

logger = logging.getLogger(__name__)


# Tool schemas
TOOL_SCHEMAS = {
    "run_backtest": {
        "name": "run_backtest",
        "description": "Run a backtest for a trading strategy",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy_type": {
                    "type": "string",
                    "description": "Strategy type to backtest",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Symbols to trade",
                },
                "parameters": {
                    "type": "object",
                    "description": "Strategy parameters",
                },
                "start_date": {
                    "type": "string",
                    "description": "Backtest start date (YYYY-MM-DD)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Backtest end date (YYYY-MM-DD)",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Initial capital (default: 100000)",
                },
            },
            "required": ["strategy_type", "symbols", "start_date"],
        },
    },
    "compare_strategies": {
        "name": "compare_strategies",
        "description": "Compare multiple strategies on the same data",
        "parameters": {
            "type": "object",
            "properties": {
                "strategies": {
                    "type": "array",
                    "description": "List of strategy configurations",
                },
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["strategies", "start_date"],
        },
    },
    "analyze_trades": {
        "name": "analyze_trades",
        "description": "Analyze individual trades from a backtest",
        "parameters": {
            "type": "object",
            "properties": {
                "backtest_result": {
                    "type": "object",
                    "description": "Backtest result to analyze",
                },
            },
            "required": ["backtest_result"],
        },
    },
}


@dataclass
class BacktestToolResult:
    """Result from backtest operations."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    raw_result: BacktestResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }


class BacktestTool:
    """Tool for running backtests."""

    def __init__(
        self,
        data_source: Any | None = None,
        default_capital: float = 100000,
    ):
        """
        Initialize backtest tool.

        Args:
            data_source: Data source for fetching market data
            default_capital: Default initial capital
        """
        self._data_source = data_source
        self._default_capital = default_capital
        self._results_cache: dict[str, BacktestResult] = {}

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema."""
        return TOOL_SCHEMAS["run_backtest"]

    async def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame | dict[str, pd.DataFrame],
        initial_capital: float | None = None,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ) -> BacktestToolResult:
        """
        Run backtest for a strategy.

        Args:
            strategy: Strategy to backtest
            data: Market data
            initial_capital: Initial capital
            commission: Commission rate
            slippage: Slippage rate

        Returns:
            BacktestToolResult with detailed metrics
        """
        try:
            capital = initial_capital or self._default_capital

            config = BacktestConfig(
                initial_capital=capital,
                commission=commission,
                slippage=slippage,
            )

            backtest = VectorizedBacktest(config)
            result = backtest.run(strategy, data)

            # Cache result
            result_id = f"{strategy.name}_{datetime.now().strftime('%H%M%S')}"
            self._results_cache[result_id] = result

            # Format results for LLM
            formatted = self._format_result(result, strategy, result_id)

            return BacktestToolResult(
                success=True,
                data=formatted,
                raw_result=result,
            )

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return BacktestToolResult(success=False, error=str(e))

    def _format_result(
        self,
        result: BacktestResult,
        strategy: Strategy,
        result_id: str,
    ) -> dict[str, Any]:
        """Format backtest result for LLM consumption."""
        # Core metrics
        metrics = result.metrics

        # Calculate additional statistics
        returns = result.returns
        equity = result.equity_curve

        # Monthly returns
        if len(returns) > 0:
            monthly_returns = returns.resample("ME").apply(
                lambda x: (1 + x).prod() - 1
            )
            monthly_stats = {
                "mean": round(monthly_returns.mean() * 100, 2),
                "std": round(monthly_returns.std() * 100, 2),
                "best": round(monthly_returns.max() * 100, 2),
                "worst": round(monthly_returns.min() * 100, 2),
                "positive_months": int((monthly_returns > 0).sum()),
                "negative_months": int((monthly_returns < 0).sum()),
            }
        else:
            monthly_stats = {}

        # Drawdown analysis
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max

        # Find drawdown periods
        drawdown_periods = self._find_drawdown_periods(drawdown)

        return {
            "result_id": result_id,
            "strategy": {
                "name": strategy.name,
                "type": type(strategy).__name__,
                "universe": [str(s) for s in strategy.universe],
            },
            "summary": {
                "total_return_pct": round(metrics.get("total_return", 0) * 100, 2),
                "annualized_return_pct": round(metrics.get("annualized_return", 0) * 100, 2),
                "sharpe_ratio": round(metrics.get("sharpe_ratio", 0), 2),
                "sortino_ratio": round(metrics.get("sortino_ratio", 0), 2),
                "calmar_ratio": round(metrics.get("calmar_ratio", 0), 2),
                "max_drawdown_pct": round(metrics.get("max_drawdown", 0) * 100, 2),
                "volatility_pct": round(metrics.get("volatility", 0) * 100, 2),
            },
            "risk_metrics": {
                "var_95": round(metrics.get("var_95", 0) * 100, 2),
                "cvar_95": round(metrics.get("cvar_95", 0) * 100, 2),
                "skewness": round(metrics.get("skewness", 0), 3),
                "kurtosis": round(metrics.get("kurtosis", 0), 3),
            },
            "trade_stats": {
                "total_trades": metrics.get("n_trades", 0),
                "win_rate_pct": round(metrics.get("win_rate", 0) * 100, 1),
                "profit_factor": round(metrics.get("profit_factor", 0), 2),
                "avg_trade_return_pct": round(metrics.get("avg_trade_return", 0) * 100, 2),
                "avg_win_pct": round(metrics.get("avg_win", 0) * 100, 2),
                "avg_loss_pct": round(metrics.get("avg_loss", 0) * 100, 2),
            },
            "monthly_stats": monthly_stats,
            "drawdown_analysis": {
                "max_drawdown_pct": round(drawdown.min() * 100, 2),
                "avg_drawdown_pct": round(drawdown.mean() * 100, 2),
                "max_drawdown_duration_days": drawdown_periods[0]["duration"] if drawdown_periods else 0,
                "worst_periods": drawdown_periods[:3],
            },
            "period": {
                "start": result.returns.index[0].strftime("%Y-%m-%d") if len(result.returns) > 0 else None,
                "end": result.returns.index[-1].strftime("%Y-%m-%d") if len(result.returns) > 0 else None,
                "trading_days": len(result.returns),
            },
            "equity_curve": {
                "initial": round(equity.iloc[0], 2) if len(equity) > 0 else None,
                "final": round(equity.iloc[-1], 2) if len(equity) > 0 else None,
                "peak": round(equity.max(), 2) if len(equity) > 0 else None,
                "trough": round(equity.min(), 2) if len(equity) > 0 else None,
            },
            "interpretation": self._generate_interpretation(metrics),
        }

    def _find_drawdown_periods(
        self,
        drawdown: pd.Series,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        """Find the worst drawdown periods."""
        periods = []

        # Find drawdown start/end points
        in_drawdown = False
        start_idx = None
        min_dd = 0

        for i, (idx, dd) in enumerate(drawdown.items()):
            if not in_drawdown and dd < 0:
                in_drawdown = True
                start_idx = idx
                min_dd = dd
            elif in_drawdown:
                if dd < min_dd:
                    min_dd = dd
                if dd >= 0 or i == len(drawdown) - 1:
                    in_drawdown = False
                    periods.append({
                        "start": start_idx.strftime("%Y-%m-%d") if hasattr(start_idx, "strftime") else str(start_idx),
                        "end": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                        "depth_pct": round(min_dd * 100, 2),
                        "duration": (idx - start_idx).days if hasattr(idx, "__sub__") else 0,
                    })

        # Sort by depth and return top N
        periods.sort(key=lambda x: x["depth_pct"])
        return periods[:top_n]

    def _generate_interpretation(self, metrics: dict[str, Any]) -> dict[str, str]:
        """Generate human-readable interpretation of results."""
        interpretation = {}

        # Overall assessment
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 2.0:
            interpretation["overall"] = "Excellent risk-adjusted performance"
        elif sharpe > 1.0:
            interpretation["overall"] = "Good risk-adjusted performance"
        elif sharpe > 0.5:
            interpretation["overall"] = "Moderate risk-adjusted performance"
        elif sharpe > 0:
            interpretation["overall"] = "Poor risk-adjusted performance"
        else:
            interpretation["overall"] = "Negative risk-adjusted returns"

        # Drawdown assessment
        max_dd = abs(metrics.get("max_drawdown", 0))
        if max_dd < 0.10:
            interpretation["risk"] = "Low drawdown risk"
        elif max_dd < 0.20:
            interpretation["risk"] = "Moderate drawdown risk"
        elif max_dd < 0.30:
            interpretation["risk"] = "High drawdown risk"
        else:
            interpretation["risk"] = "Very high drawdown risk - consider risk controls"

        # Win rate assessment
        win_rate = metrics.get("win_rate", 0)
        profit_factor = metrics.get("profit_factor", 0)

        if win_rate > 0.6 and profit_factor > 1.5:
            interpretation["trading"] = "High win rate with good profit factor"
        elif win_rate < 0.4 and profit_factor > 2.0:
            interpretation["trading"] = "Low win rate but large winners - trend following style"
        elif win_rate > 0.5:
            interpretation["trading"] = "Balanced trading approach"
        else:
            interpretation["trading"] = "Low win rate - ensure risk management is adequate"

        # Consistency
        sortino = metrics.get("sortino_ratio", 0)
        if sortino > sharpe * 1.2:
            interpretation["consistency"] = "Low downside volatility - consistent returns"
        elif sortino < sharpe * 0.8:
            interpretation["consistency"] = "High downside volatility - inconsistent returns"
        else:
            interpretation["consistency"] = "Normal return distribution"

        return interpretation


class BacktestAnalyzerTool:
    """Tool for detailed backtest analysis."""

    def __init__(self):
        """Initialize analyzer."""
        pass

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema."""
        return TOOL_SCHEMAS["analyze_trades"]

    def analyze_trades(
        self,
        result: BacktestResult,
    ) -> dict[str, Any]:
        """
        Analyze individual trades from a backtest.

        Args:
            result: Backtest result

        Returns:
            Trade analysis
        """
        try:
            trades = result.trades if hasattr(result, "trades") else []

            if not trades:
                return {
                    "success": True,
                    "data": {"message": "No individual trade data available"},
                }

            # Analyze trades
            trade_returns = [t.get("return", 0) for t in trades]
            trade_durations = [t.get("duration", 0) for t in trades]

            winners = [t for t in trades if t.get("return", 0) > 0]
            losers = [t for t in trades if t.get("return", 0) < 0]

            # By symbol analysis
            by_symbol = {}
            for trade in trades:
                symbol = trade.get("symbol", "unknown")
                if symbol not in by_symbol:
                    by_symbol[symbol] = {"trades": 0, "wins": 0, "total_return": 0}
                by_symbol[symbol]["trades"] += 1
                by_symbol[symbol]["total_return"] += trade.get("return", 0)
                if trade.get("return", 0) > 0:
                    by_symbol[symbol]["wins"] += 1

            # Format symbol stats
            symbol_stats = {
                s: {
                    "trades": v["trades"],
                    "win_rate": round(v["wins"] / v["trades"] * 100, 1),
                    "total_return_pct": round(v["total_return"] * 100, 2),
                }
                for s, v in by_symbol.items()
            }

            # Time analysis
            by_month = {}
            for trade in trades:
                if "entry_date" in trade:
                    month = trade["entry_date"][:7]
                    if month not in by_month:
                        by_month[month] = {"trades": 0, "return": 0}
                    by_month[month]["trades"] += 1
                    by_month[month]["return"] += trade.get("return", 0)

            return {
                "success": True,
                "data": {
                    "total_trades": len(trades),
                    "winners": len(winners),
                    "losers": len(losers),
                    "win_rate_pct": round(len(winners) / len(trades) * 100, 1) if trades else 0,
                    "avg_trade_return_pct": round(np.mean(trade_returns) * 100, 2) if trade_returns else 0,
                    "avg_winner_pct": round(np.mean([t["return"] for t in winners]) * 100, 2) if winners else 0,
                    "avg_loser_pct": round(np.mean([t["return"] for t in losers]) * 100, 2) if losers else 0,
                    "largest_winner_pct": round(max(trade_returns) * 100, 2) if trade_returns else 0,
                    "largest_loser_pct": round(min(trade_returns) * 100, 2) if trade_returns else 0,
                    "avg_duration_days": round(np.mean(trade_durations), 1) if trade_durations else 0,
                    "by_symbol": symbol_stats,
                    "by_month": by_month,
                    "consecutive": self._analyze_consecutive(trades),
                },
            }

        except Exception as e:
            logger.error(f"Trade analysis failed: {e}")
            return {"success": False, "error": str(e)}

    def _analyze_consecutive(self, trades: list[dict]) -> dict[str, int]:
        """Analyze consecutive wins/losses."""
        if not trades:
            return {"max_consecutive_wins": 0, "max_consecutive_losses": 0}

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in trades:
            if trade.get("return", 0) > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return {
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
        }

    def get_performance_attribution(
        self,
        result: BacktestResult,
        benchmark_returns: pd.Series | None = None,
    ) -> dict[str, Any]:
        """
        Get performance attribution analysis.

        Args:
            result: Backtest result
            benchmark_returns: Optional benchmark returns

        Returns:
            Attribution analysis
        """
        try:
            returns = result.returns

            attribution = {
                "total_return": round((1 + returns).prod() - 1, 4),
            }

            # Time-based attribution
            attribution["by_year"] = {}
            for year in returns.index.year.unique():
                year_returns = returns[returns.index.year == year]
                attribution["by_year"][int(year)] = round(
                    (1 + year_returns).prod() - 1, 4
                )

            # Market condition attribution (if benchmark provided)
            if benchmark_returns is not None:
                # Align data
                aligned = pd.DataFrame({
                    "strategy": returns,
                    "benchmark": benchmark_returns,
                }).dropna()

                if len(aligned) > 0:
                    # Up market vs down market
                    up_market = aligned[aligned["benchmark"] > 0]
                    down_market = aligned[aligned["benchmark"] <= 0]

                    attribution["market_conditions"] = {
                        "up_market": {
                            "strategy_return": round(up_market["strategy"].mean() * 252, 4),
                            "benchmark_return": round(up_market["benchmark"].mean() * 252, 4),
                            "capture_ratio": round(
                                up_market["strategy"].mean() / up_market["benchmark"].mean(), 2
                            ) if up_market["benchmark"].mean() != 0 else 0,
                        },
                        "down_market": {
                            "strategy_return": round(down_market["strategy"].mean() * 252, 4),
                            "benchmark_return": round(down_market["benchmark"].mean() * 252, 4),
                            "capture_ratio": round(
                                down_market["strategy"].mean() / down_market["benchmark"].mean(), 2
                            ) if down_market["benchmark"].mean() != 0 else 0,
                        },
                    }

                    # Alpha and beta
                    from scipy import stats
                    beta, alpha, r_value, _, _ = stats.linregress(
                        aligned["benchmark"], aligned["strategy"]
                    )
                    attribution["factor_analysis"] = {
                        "alpha_annualized": round(alpha * 252, 4),
                        "beta": round(beta, 3),
                        "r_squared": round(r_value ** 2, 3),
                    }

            return {"success": True, "data": attribution}

        except Exception as e:
            logger.error(f"Attribution analysis failed: {e}")
            return {"success": False, "error": str(e)}


# Convenience functions for direct LLM use
async def run_backtest(
    strategy_type: str,
    symbols: list[str],
    start_date: str,
    end_date: str | None = None,
    parameters: dict[str, Any] | None = None,
    initial_capital: float = 100000,
) -> dict[str, Any]:
    """
    Run a backtest for a trading strategy.

    Args:
        strategy_type: Type of strategy
        symbols: Symbols to trade
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        parameters: Strategy parameters
        initial_capital: Initial capital

    Returns:
        Backtest results
    """
    from .strategy_tools import StrategyBuilderTool
    from .data_tools import DataQueryTool

    try:
        # Create strategy
        builder = StrategyBuilderTool()
        strategy_result = builder.create(strategy_type, symbols, parameters)

        if not strategy_result.success:
            return strategy_result.to_dict()

        strategy = strategy_result.strategy

        # Get data
        data_tool = DataQueryTool()
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        data_result = await data_tool.query(symbols, start_date, end_date)

        if not data_result.success:
            return {"success": False, "error": f"Failed to get data: {data_result.error}"}

        # Convert to DataFrame format
        data_dict = {}
        for symbol, raw_data in data_result.data.items():
            data_dict[Symbol(symbol)] = pd.DataFrame(
                {
                    "open": raw_data["open"],
                    "high": raw_data["high"],
                    "low": raw_data["low"],
                    "close": raw_data["close"],
                    "volume": raw_data["volume"],
                },
                index=pd.to_datetime(raw_data["dates"]),
            )

        # Run backtest
        backtest_tool = BacktestTool(default_capital=initial_capital)
        result = await backtest_tool.run(strategy, data_dict, initial_capital)

        return result.to_dict()

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return {"success": False, "error": str(e)}


async def compare_strategies(
    strategies: list[dict[str, Any]],
    start_date: str,
    end_date: str | None = None,
    initial_capital: float = 100000,
) -> dict[str, Any]:
    """
    Compare multiple strategies on the same data.

    Args:
        strategies: List of strategy configs (type, symbols, parameters)
        start_date: Start date
        end_date: End date
        initial_capital: Initial capital

    Returns:
        Comparison results
    """
    try:
        results = []

        for config in strategies:
            result = await run_backtest(
                strategy_type=config["type"],
                symbols=config.get("symbols", []),
                start_date=start_date,
                end_date=end_date,
                parameters=config.get("parameters", {}),
                initial_capital=initial_capital,
            )

            if result["success"]:
                results.append({
                    "name": config.get("name", config["type"]),
                    "config": config,
                    "metrics": result["data"]["summary"],
                    "risk_metrics": result["data"]["risk_metrics"],
                    "trade_stats": result["data"]["trade_stats"],
                })

        if not results:
            return {"success": False, "error": "All strategies failed"}

        # Rank strategies
        rankings = {
            "by_sharpe": sorted(results, key=lambda x: x["metrics"]["sharpe_ratio"], reverse=True),
            "by_return": sorted(results, key=lambda x: x["metrics"]["total_return_pct"], reverse=True),
            "by_risk_adjusted": sorted(
                results,
                key=lambda x: x["metrics"]["sharpe_ratio"] / (1 + abs(x["metrics"]["max_drawdown_pct"] / 100)),
                reverse=True,
            ),
        }

        return {
            "success": True,
            "data": {
                "n_strategies": len(results),
                "results": results,
                "rankings": {
                    k: [r["name"] for r in v[:3]]
                    for k, v in rankings.items()
                },
                "best_overall": rankings["by_risk_adjusted"][0]["name"],
                "comparison_table": self._create_comparison_table(results),
            },
        }

    except Exception as e:
        logger.error(f"Strategy comparison failed: {e}")
        return {"success": False, "error": str(e)}


def _create_comparison_table(results: list[dict]) -> list[dict]:
    """Create comparison table."""
    table = []
    for r in results:
        table.append({
            "Strategy": r["name"],
            "Return (%)": r["metrics"]["total_return_pct"],
            "Sharpe": r["metrics"]["sharpe_ratio"],
            "Max DD (%)": r["metrics"]["max_drawdown_pct"],
            "Win Rate (%)": r["trade_stats"]["win_rate_pct"],
            "Trades": r["trade_stats"]["total_trades"],
        })
    return table


def analyze_trades(backtest_data: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze trades from a backtest result.

    Args:
        backtest_data: Backtest result data

    Returns:
        Trade analysis
    """
    analyzer = BacktestAnalyzerTool()
    # This would need the raw BacktestResult - simplified for now
    return {
        "success": True,
        "data": {
            "message": "Trade analysis requires raw backtest result object",
            "summary_from_data": backtest_data.get("trade_stats", {}),
        },
    }


def get_performance_attribution(
    backtest_data: dict[str, Any],
    benchmark: str | None = None,
) -> dict[str, Any]:
    """
    Get performance attribution analysis.

    Args:
        backtest_data: Backtest result data
        benchmark: Optional benchmark symbol

    Returns:
        Attribution analysis
    """
    # Simplified attribution from summary data
    return {
        "success": True,
        "data": {
            "total_return": backtest_data.get("summary", {}).get("total_return_pct", 0),
            "risk_adjusted": backtest_data.get("summary", {}).get("sharpe_ratio", 0),
            "interpretation": backtest_data.get("interpretation", {}),
        },
    }


async def run_walk_forward(
    strategy_type: str,
    symbols: list[str],
    param_grid: dict[str, list[Any]],
    start_date: str,
    end_date: str | None = None,
    n_splits: int = 5,
    optimization_metric: str = "sharpe_ratio",
) -> dict[str, Any]:
    """
    Run walk-forward optimization.

    Args:
        strategy_type: Strategy type
        symbols: Symbols to trade
        param_grid: Parameter grid for optimization
        start_date: Start date
        end_date: End date
        n_splits: Number of walk-forward splits
        optimization_metric: Metric to optimize

    Returns:
        Walk-forward results
    """
    try:
        from ...evaluation.validation.walk_forward import (
            WalkForwardOptimizer,
            WalkForwardConfig,
        )
        from .strategy_tools import STRATEGY_REGISTRY
        from .data_tools import DataQueryTool

        if strategy_type not in STRATEGY_REGISTRY:
            return {"success": False, "error": f"Unknown strategy: {strategy_type}"}

        strategy_class = STRATEGY_REGISTRY[strategy_type]

        # Get data
        data_tool = DataQueryTool()
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        data_result = await data_tool.query(symbols, start_date, end_date)
        if not data_result.success:
            return {"success": False, "error": f"Failed to get data: {data_result.error}"}

        # Convert to DataFrame
        if len(symbols) == 1:
            raw = data_result.data[symbols[0]]
            data = pd.DataFrame(
                {
                    "open": raw["open"],
                    "high": raw["high"],
                    "low": raw["low"],
                    "close": raw["close"],
                    "volume": raw["volume"],
                },
                index=pd.to_datetime(raw["dates"]),
            )
        else:
            data = {}
            for symbol, raw in data_result.data.items():
                data[Symbol(symbol)] = pd.DataFrame(
                    {
                        "open": raw["open"],
                        "high": raw["high"],
                        "low": raw["low"],
                        "close": raw["close"],
                        "volume": raw["volume"],
                    },
                    index=pd.to_datetime(raw["dates"]),
                )

        # Configure walk-forward
        config = WalkForwardConfig(
            n_splits=n_splits,
            train_ratio=0.7,
            optimization_metric=optimization_metric,
        )

        # Run optimization
        optimizer = WalkForwardOptimizer(config)
        universe = [Symbol(s) if isinstance(s, str) else s for s in symbols]

        result = optimizer.optimize(
            strategy_class=strategy_class,
            data=data,
            param_grid=param_grid,
            universe=universe,
        )

        # Format results
        fold_summaries = []
        for fold in result.folds:
            fold_summaries.append({
                "fold": fold.fold_id,
                "train_period": f"{fold.train_start.strftime('%Y-%m-%d')} to {fold.train_end.strftime('%Y-%m-%d')}",
                "test_period": f"{fold.test_start.strftime('%Y-%m-%d')} to {fold.test_end.strftime('%Y-%m-%d')}",
                "best_params": fold.best_params,
                "is_metrics": {k: round(v, 3) for k, v in fold.in_sample_metrics.items()},
                "oos_metrics": {k: round(v, 3) for k, v in fold.out_of_sample_metrics.items()},
            })

        return {
            "success": True,
            "data": {
                "n_folds": len(result.folds),
                "combined_oos_metrics": {
                    k: round(v, 3) for k, v in result.combined_metrics.items()
                },
                "parameter_stability": result.parameter_stability,
                "is_oos_ratio": round(result.is_oos_ratio, 2),
                "folds": fold_summaries,
                "robustness_score": _compute_robustness_score(result),
            },
        }

    except Exception as e:
        logger.error(f"Walk-forward optimization failed: {e}")
        return {"success": False, "error": str(e)}


def _compute_robustness_score(result: Any) -> dict[str, Any]:
    """Compute strategy robustness score."""
    # Score based on IS/OOS consistency and parameter stability
    is_oos_score = min(result.is_oos_ratio, 1.0) * 0.4

    # Parameter stability score
    stability_scores = []
    for param, values in result.parameter_stability.items():
        if isinstance(values, list) and len(values) > 1:
            # Lower std = more stable
            std = np.std(values)
            mean = np.mean(values)
            cv = std / abs(mean) if mean != 0 else 1.0
            stability_scores.append(max(0, 1 - cv))

    param_score = np.mean(stability_scores) * 0.3 if stability_scores else 0.15

    # Fold consistency score
    oos_sharpes = [f.out_of_sample_metrics.get("sharpe_ratio", 0) for f in result.folds]
    if oos_sharpes:
        positive_ratio = sum(1 for s in oos_sharpes if s > 0) / len(oos_sharpes)
        consistency_score = positive_ratio * 0.3
    else:
        consistency_score = 0.15

    total_score = is_oos_score + param_score + consistency_score

    return {
        "total_score": round(total_score, 2),
        "is_oos_consistency": round(is_oos_score / 0.4, 2),
        "parameter_stability": round(param_score / 0.3, 2),
        "fold_consistency": round(consistency_score / 0.3, 2),
        "interpretation": (
            "High robustness" if total_score > 0.7 else
            "Moderate robustness" if total_score > 0.5 else
            "Low robustness - consider more testing"
        ),
    }
