"""Strategy tools for LLM agents.

Provides interfaces for creating, configuring, and optimizing trading strategies.
"""

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ...core import Symbol
from ...strategies.base import Strategy, RuleBasedStrategy, MLStrategy
from ...strategies.traditional.trend_following import (
    MovingAverageCrossover,
    BreakoutStrategy,
    TrendStrengthStrategy,
    MomentumStrategy,
)
from ...strategies.traditional.mean_reversion import (
    BollingerBandMeanReversion,
    RSIMeanReversion,
)

logger = logging.getLogger(__name__)


# Registry of available strategies
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "ma_crossover": MovingAverageCrossover,
    "breakout": BreakoutStrategy,
    "trend_strength": TrendStrengthStrategy,
    "momentum": MomentumStrategy,
    "bollinger_bands": BollingerBandMeanReversion,
    "rsi_mean_reversion": RSIMeanReversion,
}

# Try to import additional strategies
try:
    from ...strategies.traditional.factor_models import (
        CrossSectionalMomentumStrategy,
        ValueStrategy,
        LowVolatilityStrategy,
        MultiFactorStrategy,
    )
    STRATEGY_REGISTRY.update({
        "cross_sectional_momentum": CrossSectionalMomentumStrategy,
        "value": ValueStrategy,
        "low_volatility": LowVolatilityStrategy,
        "multi_factor": MultiFactorStrategy,
    })
except ImportError:
    pass

try:
    from ...strategies.alternative.contrarian import (
        InverseSentimentStrategy,
        SentimentDivergenceStrategy,
    )
    STRATEGY_REGISTRY.update({
        "inverse_sentiment": InverseSentimentStrategy,
        "sentiment_divergence": SentimentDivergenceStrategy,
    })
except ImportError:
    pass


# Tool schemas
TOOL_SCHEMAS = {
    "create_strategy": {
        "name": "create_strategy",
        "description": "Create a trading strategy with specified parameters",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy_type": {
                    "type": "string",
                    "enum": list(STRATEGY_REGISTRY.keys()),
                    "description": "Type of strategy to create",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Symbols to trade",
                },
                "parameters": {
                    "type": "object",
                    "description": "Strategy-specific parameters",
                },
            },
            "required": ["strategy_type", "symbols"],
        },
    },
    "list_strategies": {
        "name": "list_available_strategies",
        "description": "List all available strategy types with descriptions",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_parameters": {
        "name": "get_strategy_parameters",
        "description": "Get available parameters for a strategy type",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy_type": {
                    "type": "string",
                    "description": "Strategy type to get parameters for",
                },
            },
            "required": ["strategy_type"],
        },
    },
    "optimize_strategy": {
        "name": "optimize_strategy",
        "description": "Optimize strategy parameters using grid search",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy_type": {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "param_grid": {
                    "type": "object",
                    "description": "Parameter ranges to search",
                },
                "metric": {
                    "type": "string",
                    "enum": ["sharpe_ratio", "total_return", "sortino_ratio", "calmar_ratio"],
                    "description": "Metric to optimize",
                },
            },
            "required": ["strategy_type", "symbols", "param_grid"],
        },
    },
}


@dataclass
class StrategyResult:
    """Result from strategy operations."""

    success: bool
    strategy: Strategy | None = None
    data: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.success,
            "error": self.error,
        }
        if self.data:
            result["data"] = self.data
        if self.strategy:
            result["strategy_info"] = {
                "name": self.strategy.name,
                "type": type(self.strategy).__name__,
                "universe": [str(s) for s in self.strategy.universe],
            }
        return result


class StrategyBuilderTool:
    """Tool for building and configuring strategies."""

    def __init__(self):
        """Initialize strategy builder."""
        self._created_strategies: dict[str, Strategy] = {}

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema."""
        return TOOL_SCHEMAS["create_strategy"]

    def create(
        self,
        strategy_type: str,
        symbols: list[str],
        parameters: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> StrategyResult:
        """
        Create a strategy instance.

        Args:
            strategy_type: Type of strategy
            symbols: Symbols to trade
            parameters: Strategy parameters
            name: Optional custom name

        Returns:
            StrategyResult with created strategy
        """
        try:
            if strategy_type not in STRATEGY_REGISTRY:
                return StrategyResult(
                    success=False,
                    error=f"Unknown strategy type: {strategy_type}. "
                    f"Available: {list(STRATEGY_REGISTRY.keys())}",
                )

            strategy_class = STRATEGY_REGISTRY[strategy_type]
            params = parameters or {}

            # Convert symbols to Symbol objects
            universe = [Symbol(s) if isinstance(s, str) else s for s in symbols]

            # Create strategy
            strategy = strategy_class(universe=universe, **params)

            # Assign custom name if provided
            if name:
                strategy.name = name

            # Store for later reference
            strategy_id = name or f"{strategy_type}_{datetime.now().strftime('%H%M%S')}"
            self._created_strategies[strategy_id] = strategy

            return StrategyResult(
                success=True,
                strategy=strategy,
                data={
                    "strategy_id": strategy_id,
                    "strategy_type": strategy_type,
                    "parameters": params,
                    "universe": [str(s) for s in universe],
                },
            )

        except Exception as e:
            logger.error(f"Strategy creation failed: {e}")
            return StrategyResult(success=False, error=str(e))

    def get_strategy(self, strategy_id: str) -> Strategy | None:
        """Get a previously created strategy."""
        return self._created_strategies.get(strategy_id)

    def list_created(self) -> list[dict[str, Any]]:
        """List all created strategies."""
        return [
            {
                "id": sid,
                "name": s.name,
                "type": type(s).__name__,
                "universe": [str(sym) for sym in s.universe],
            }
            for sid, s in self._created_strategies.items()
        ]


class StrategyOptimizerTool:
    """Tool for optimizing strategy parameters."""

    def __init__(self, builder: StrategyBuilderTool | None = None):
        """Initialize optimizer."""
        self._builder = builder or StrategyBuilderTool()

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema."""
        return TOOL_SCHEMAS["optimize_strategy"]

    async def optimize(
        self,
        strategy_type: str,
        symbols: list[str],
        param_grid: dict[str, list[Any]],
        data: pd.DataFrame | dict[str, pd.DataFrame],
        metric: str = "sharpe_ratio",
        n_jobs: int = 1,
    ) -> dict[str, Any]:
        """
        Optimize strategy parameters via grid search.

        Args:
            strategy_type: Strategy type
            symbols: Symbols to trade
            param_grid: Parameter grid to search
            data: Market data for backtesting
            metric: Metric to optimize
            n_jobs: Number of parallel jobs

        Returns:
            Optimization results
        """
        from ...evaluation.backtest import VectorizedBacktest, BacktestConfig

        try:
            if strategy_type not in STRATEGY_REGISTRY:
                return {"success": False, "error": f"Unknown strategy: {strategy_type}"}

            strategy_class = STRATEGY_REGISTRY[strategy_type]

            # Generate parameter combinations
            param_combinations = self._generate_combinations(param_grid)

            if not param_combinations:
                return {"success": False, "error": "No parameter combinations generated"}

            results = []
            best_result = None
            best_metric_value = float("-inf")

            # Evaluate each combination
            for params in param_combinations:
                try:
                    # Create strategy
                    universe = [Symbol(s) if isinstance(s, str) else s for s in symbols]
                    strategy = strategy_class(universe=universe, **params)

                    # Run backtest
                    config = BacktestConfig(initial_capital=100000)
                    backtest = VectorizedBacktest(config)
                    bt_result = backtest.run(strategy, data)

                    # Get metric value
                    metric_value = bt_result.metrics.get(metric, 0)

                    result_entry = {
                        "parameters": params,
                        "metrics": {
                            "sharpe_ratio": round(bt_result.metrics.get("sharpe_ratio", 0), 3),
                            "total_return": round(bt_result.metrics.get("total_return", 0) * 100, 2),
                            "max_drawdown": round(bt_result.metrics.get("max_drawdown", 0) * 100, 2),
                            "win_rate": round(bt_result.metrics.get("win_rate", 0) * 100, 1),
                        },
                        "target_metric": round(metric_value, 4),
                    }
                    results.append(result_entry)

                    if metric_value > best_metric_value:
                        best_metric_value = metric_value
                        best_result = result_entry

                except Exception as e:
                    logger.warning(f"Parameter combination {params} failed: {e}")
                    continue

            if not results:
                return {"success": False, "error": "All parameter combinations failed"}

            # Sort by target metric
            results.sort(key=lambda x: x["target_metric"], reverse=True)

            return {
                "success": True,
                "data": {
                    "best_parameters": best_result["parameters"] if best_result else None,
                    "best_metrics": best_result["metrics"] if best_result else None,
                    "optimization_metric": metric,
                    "n_combinations_tested": len(results),
                    "top_5_results": results[:5],
                    "parameter_sensitivity": self._compute_sensitivity(results, param_grid),
                },
            }

        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            return {"success": False, "error": str(e)}

    def _generate_combinations(
        self,
        param_grid: dict[str, list[Any]],
    ) -> list[dict[str, Any]]:
        """Generate all parameter combinations."""
        import itertools

        keys = list(param_grid.keys())
        values = list(param_grid.values())

        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _compute_sensitivity(
        self,
        results: list[dict],
        param_grid: dict[str, list],
    ) -> dict[str, Any]:
        """Compute parameter sensitivity analysis."""
        sensitivity = {}

        for param_name, param_values in param_grid.items():
            if len(param_values) < 2:
                continue

            # Group results by this parameter
            param_metrics = {}
            for value in param_values:
                matching = [
                    r["target_metric"]
                    for r in results
                    if r["parameters"].get(param_name) == value
                ]
                if matching:
                    param_metrics[str(value)] = {
                        "mean": round(np.mean(matching), 4),
                        "std": round(np.std(matching), 4),
                        "count": len(matching),
                    }

            # Compute sensitivity score (variance of means)
            if param_metrics:
                means = [v["mean"] for v in param_metrics.values()]
                sensitivity[param_name] = {
                    "sensitivity_score": round(np.std(means), 4),
                    "best_value": max(param_metrics, key=lambda k: param_metrics[k]["mean"]),
                    "value_metrics": param_metrics,
                }

        return sensitivity


def list_available_strategies() -> dict[str, Any]:
    """
    List all available strategy types.

    Returns:
        Dict with strategy information
    """
    strategies = []

    for name, cls in STRATEGY_REGISTRY.items():
        # Get class docstring
        doc = cls.__doc__ or "No description available"
        doc = doc.split("\n")[0].strip()  # First line only

        # Determine strategy category
        module = cls.__module__
        if "trend" in module:
            category = "trend_following"
        elif "mean_reversion" in module or "reversion" in name:
            category = "mean_reversion"
        elif "factor" in module:
            category = "factor"
        elif "alternative" in module or "sentiment" in name:
            category = "alternative"
        elif "ml" in module:
            category = "machine_learning"
        else:
            category = "other"

        strategies.append({
            "name": name,
            "class": cls.__name__,
            "category": category,
            "description": doc,
        })

    # Group by category
    by_category = {}
    for s in strategies:
        cat = s["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(s)

    return {
        "success": True,
        "data": {
            "strategies": strategies,
            "by_category": by_category,
            "total_count": len(strategies),
        },
    }


def get_strategy_parameters(strategy_type: str) -> dict[str, Any]:
    """
    Get available parameters for a strategy type.

    Args:
        strategy_type: Strategy type name

    Returns:
        Dict with parameter information
    """
    if strategy_type not in STRATEGY_REGISTRY:
        return {
            "success": False,
            "error": f"Unknown strategy: {strategy_type}",
        }

    strategy_class = STRATEGY_REGISTRY[strategy_type]

    # Get __init__ signature
    sig = inspect.signature(strategy_class.__init__)
    parameters = []

    for name, param in sig.parameters.items():
        if name in ["self", "universe", "kwargs"]:
            continue

        param_info = {
            "name": name,
            "required": param.default == inspect.Parameter.empty,
        }

        # Get default value
        if param.default != inspect.Parameter.empty:
            default = param.default
            if isinstance(default, (int, float, str, bool, type(None))):
                param_info["default"] = default
            else:
                param_info["default"] = str(default)

        # Try to infer type from annotation or default
        if param.annotation != inspect.Parameter.empty:
            param_info["type"] = str(param.annotation)
        elif param.default is not None and param.default != inspect.Parameter.empty:
            param_info["type"] = type(param.default).__name__

        # Add suggested ranges for common parameters
        param_info["suggested_range"] = _get_suggested_range(name)

        parameters.append(param_info)

    return {
        "success": True,
        "data": {
            "strategy_type": strategy_type,
            "class_name": strategy_class.__name__,
            "parameters": parameters,
            "description": (strategy_class.__doc__ or "").split("\n")[0].strip(),
        },
    }


def _get_suggested_range(param_name: str) -> dict[str, Any] | None:
    """Get suggested parameter ranges for common parameters."""
    ranges = {
        "fast_period": {"min": 5, "max": 50, "typical": [10, 20, 30]},
        "slow_period": {"min": 20, "max": 200, "typical": [50, 100, 150]},
        "lookback_period": {"min": 10, "max": 100, "typical": [20, 50, 60]},
        "lookback": {"min": 10, "max": 100, "typical": [20, 50, 60]},
        "rsi_period": {"min": 5, "max": 30, "typical": [14, 21]},
        "bb_period": {"min": 10, "max": 50, "typical": [20, 30]},
        "bb_std": {"min": 1.0, "max": 3.0, "typical": [2.0, 2.5]},
        "atr_period": {"min": 10, "max": 30, "typical": [14, 20]},
        "entry_threshold": {"min": 0.0, "max": 1.0, "typical": [0.3, 0.5, 0.7]},
        "exit_threshold": {"min": 0.0, "max": 1.0, "typical": [0.3, 0.5]},
        "stop_loss": {"min": 0.01, "max": 0.10, "typical": [0.02, 0.05]},
        "take_profit": {"min": 0.02, "max": 0.20, "typical": [0.05, 0.10]},
    }

    return ranges.get(param_name)


def create_strategy(
    strategy_type: str,
    symbols: list[str],
    parameters: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """
    Create a trading strategy.

    Args:
        strategy_type: Type of strategy (see list_available_strategies)
        symbols: List of symbols to trade
        parameters: Strategy-specific parameters
        name: Optional custom name

    Returns:
        Dict with strategy info
    """
    builder = StrategyBuilderTool()
    result = builder.create(strategy_type, symbols, parameters, name)
    return result.to_dict()


async def optimize_strategy(
    strategy_type: str,
    symbols: list[str],
    param_grid: dict[str, list[Any]],
    data: pd.DataFrame | dict[str, pd.DataFrame],
    metric: str = "sharpe_ratio",
) -> dict[str, Any]:
    """
    Optimize strategy parameters.

    Args:
        strategy_type: Strategy type
        symbols: Symbols to trade
        param_grid: Parameter grid to search
        data: Market data for backtesting
        metric: Metric to optimize

    Returns:
        Optimization results
    """
    optimizer = StrategyOptimizerTool()
    return await optimizer.optimize(strategy_type, symbols, param_grid, data, metric)


def compose_strategies(
    strategies: list[dict[str, Any]],
    weights: list[float] | None = None,
    aggregation: str = "weighted_mean",
) -> dict[str, Any]:
    """
    Compose multiple strategies into an ensemble.

    Args:
        strategies: List of strategy configs
        weights: Optional weights for each strategy
        aggregation: Aggregation method

    Returns:
        Dict with composed strategy info
    """
    try:
        builder = StrategyBuilderTool()
        created_strategies = []

        for i, config in enumerate(strategies):
            result = builder.create(
                strategy_type=config["type"],
                symbols=config.get("symbols", []),
                parameters=config.get("parameters", {}),
                name=config.get("name", f"strategy_{i}"),
            )
            if result.success and result.strategy:
                created_strategies.append(result.strategy)
            else:
                return {
                    "success": False,
                    "error": f"Failed to create strategy {i}: {result.error}",
                }

        # Normalize weights
        if weights is None:
            weights = [1.0 / len(created_strategies)] * len(created_strategies)
        else:
            total = sum(weights)
            weights = [w / total for w in weights]

        # Import and create ensemble
        from ..strategy_agent import MultiStrategyAgent

        ensemble = MultiStrategyAgent(
            strategies=created_strategies,
            aggregation_method=aggregation,
        )

        return {
            "success": True,
            "data": {
                "name": "composed_strategy",
                "n_strategies": len(created_strategies),
                "strategies": [
                    {
                        "name": s.name,
                        "type": type(s).__name__,
                        "weight": w,
                    }
                    for s, w in zip(created_strategies, weights)
                ],
                "aggregation_method": aggregation,
            },
        }

    except Exception as e:
        logger.error(f"Strategy composition failed: {e}")
        return {"success": False, "error": str(e)}
