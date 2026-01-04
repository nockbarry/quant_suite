"""Walk-forward optimization and validation for strategy evaluation.

Implements walk-forward analysis which combines in-sample optimization
with out-of-sample testing to evaluate strategy robustness.
"""

from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from typing import Any, Callable, Iterator, Type

import numpy as np
import pandas as pd

from ...core import Symbol
from ...strategies.base import Strategy
from ..backtest.engine import BacktestConfig, BacktestResult, VectorizedBacktest


@dataclass
class WalkForwardWindow:
    """A single walk-forward window with train and test periods."""

    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_data: dict[Symbol, pd.DataFrame]
    test_data: dict[Symbol, pd.DataFrame]

    @property
    def train_days(self) -> int:
        return (self.train_end - self.train_start).days

    @property
    def test_days(self) -> int:
        return (self.test_end - self.test_start).days


@dataclass
class OptimizationResult:
    """Result of parameter optimization on a single window."""

    window_id: int
    best_params: dict[str, Any]
    best_metric: float
    all_results: list[dict[str, Any]]
    optimization_metric: str


@dataclass
class WalkForwardFold:
    """Results from a single walk-forward fold."""

    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    # Optimization results
    optimized_params: dict[str, Any]
    train_metrics: dict[str, float]

    # Out-of-sample results
    test_metrics: dict[str, float]
    test_returns: pd.Series
    test_trades: pd.DataFrame

    @property
    def is_ratio(self) -> float:
        """In-sample vs out-of-sample performance ratio."""
        train_sharpe = self.train_metrics.get("sharpe_ratio", 0)
        test_sharpe = self.test_metrics.get("sharpe_ratio", 0)
        if train_sharpe != 0:
            return test_sharpe / train_sharpe
        return 0.0


@dataclass
class WalkForwardResult:
    """Aggregated results from walk-forward analysis."""

    strategy_name: str
    strategy_class: str
    folds: list[WalkForwardFold]
    config: "WalkForwardConfig"

    # Aggregated metrics
    combined_returns: pd.Series
    aggregated_metrics: dict[str, float]

    # Parameter stability analysis
    param_stability: dict[str, dict[str, float]]

    # Timing
    start_time: datetime
    end_time: datetime
    total_runtime_seconds: float

    def to_summary(self) -> dict[str, Any]:
        """Generate a summary dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "num_folds": len(self.folds),
            "total_test_days": sum(f.test_days for f in self.folds),
            "aggregated_metrics": self.aggregated_metrics,
            "avg_is_ratio": np.mean([f.is_ratio for f in self.folds]),
            "param_stability": self.param_stability,
            "runtime_seconds": self.total_runtime_seconds,
        }

    def get_parameter_evolution(self) -> pd.DataFrame:
        """Get parameter values across folds."""
        records = []
        for fold in self.folds:
            record = {
                "window_id": fold.window_id,
                "test_start": fold.test_start,
                **fold.optimized_params,
            }
            records.append(record)
        return pd.DataFrame(records)

    def get_metrics_by_fold(self) -> pd.DataFrame:
        """Get metrics for each fold."""
        records = []
        for fold in self.folds:
            record = {
                "window_id": fold.window_id,
                "train_start": fold.train_start,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                **{f"train_{k}": v for k, v in fold.train_metrics.items()},
                **{f"test_{k}": v for k, v in fold.test_metrics.items()},
                "is_ratio": fold.is_ratio,
            }
            records.append(record)
        return pd.DataFrame(records)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward analysis."""

    # Window sizing
    train_days: int = 252  # 1 year training
    test_days: int = 63    # 1 quarter testing
    step_days: int = 21    # 1 month step

    # Expanding vs rolling window
    expanding_train: bool = False
    min_train_days: int = 126  # Minimum for expanding

    # Gap between train and test (to avoid lookahead)
    # IMPORTANT: Must be >= target_horizon to prevent target variable leakage
    # For 5-day forward returns, gap must be at least 5 days
    gap_days: int = 5

    # Optimization settings
    optimization_metric: str = "sharpe_ratio"
    maximize_metric: bool = True

    # Backtest configuration
    backtest_config: BacktestConfig = field(default_factory=BacktestConfig)

    # Parameter grid for optimization
    param_grid: dict[str, list[Any]] = field(default_factory=dict)

    # Parallel processing
    n_jobs: int = 1
    verbose: bool = True


class WalkForwardSplitter:
    """
    Generates walk-forward windows from data.

    Handles both rolling and expanding window approaches.
    """

    def __init__(self, config: WalkForwardConfig):
        """
        Initialize splitter.

        Args:
            config: Walk-forward configuration
        """
        self.config = config

    def split(
        self,
        data: dict[Symbol, pd.DataFrame],
    ) -> Iterator[WalkForwardWindow]:
        """
        Generate walk-forward windows.

        Args:
            data: Dict mapping symbols to OHLCV DataFrames

        Yields:
            WalkForwardWindow objects
        """
        # Get common date range
        all_dates = None
        for df in data.values():
            if all_dates is None:
                all_dates = set(df.index)
            else:
                all_dates = all_dates.intersection(set(df.index))

        if not all_dates:
            return

        sorted_dates = sorted(all_dates)
        total_days = len(sorted_dates)

        window_id = 0
        current_start_idx = 0

        while True:
            # Calculate indices
            if self.config.expanding_train:
                train_start_idx = 0
                train_end_idx = max(
                    self.config.min_train_days + window_id * self.config.step_days,
                    self.config.min_train_days,
                )
            else:
                train_start_idx = current_start_idx
                train_end_idx = train_start_idx + self.config.train_days

            test_start_idx = train_end_idx + self.config.gap_days
            test_end_idx = test_start_idx + self.config.test_days

            # Check if we have enough data
            if test_end_idx > total_days:
                break

            # Get dates
            train_start = sorted_dates[train_start_idx]
            train_end = sorted_dates[train_end_idx - 1]
            test_start = sorted_dates[test_start_idx]
            test_end = sorted_dates[min(test_end_idx - 1, total_days - 1)]

            # Split data
            train_data = {}
            test_data = {}

            for symbol, df in data.items():
                train_mask = (df.index >= train_start) & (df.index <= train_end)
                test_mask = (df.index >= test_start) & (df.index <= test_end)

                if train_mask.any():
                    train_data[symbol] = df[train_mask].copy()
                if test_mask.any():
                    test_data[symbol] = df[test_mask].copy()

            if train_data and test_data:
                yield WalkForwardWindow(
                    window_id=window_id,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_data=train_data,
                    test_data=test_data,
                )

            window_id += 1
            current_start_idx += self.config.step_days

    def get_n_windows(self, n_days: int) -> int:
        """Estimate number of windows for given data length."""
        if self.config.expanding_train:
            available = n_days - self.config.min_train_days - self.config.test_days - self.config.gap_days
        else:
            available = n_days - self.config.train_days - self.config.test_days - self.config.gap_days

        if available < 0:
            return 0

        return available // self.config.step_days + 1


class ParameterOptimizer:
    """
    Optimizes strategy parameters using grid search or custom methods.
    """

    def __init__(
        self,
        strategy_class: Type[Strategy],
        param_grid: dict[str, list[Any]],
        optimization_metric: str = "sharpe_ratio",
        maximize: bool = True,
        backtest_config: BacktestConfig | None = None,
    ):
        """
        Initialize optimizer.

        Args:
            strategy_class: Strategy class to optimize
            param_grid: Dictionary of parameter names to lists of values
            optimization_metric: Metric to optimize
            maximize: If True, maximize metric; if False, minimize
            backtest_config: Backtest configuration
        """
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.optimization_metric = optimization_metric
        self.maximize = maximize
        self.backtest_config = backtest_config or BacktestConfig()

    def _generate_param_combinations(self) -> list[dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        if not self.param_grid:
            return [{}]

        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())

        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def optimize(
        self,
        data: dict[Symbol, pd.DataFrame],
        universe: list[Symbol],
        base_params: dict[str, Any] | None = None,
    ) -> OptimizationResult:
        """
        Optimize parameters on given data.

        Args:
            data: Training data
            universe: List of symbols
            base_params: Base parameters that won't be optimized

        Returns:
            OptimizationResult with best parameters
        """
        base_params = base_params or {}
        combinations = self._generate_param_combinations()

        results = []
        backtest = VectorizedBacktest(self.backtest_config)

        best_metric = float("-inf") if self.maximize else float("inf")
        best_params = combinations[0] if combinations else {}

        for params in combinations:
            full_params = {**base_params, **params}

            try:
                # Create strategy with parameters
                strategy = self.strategy_class(universe=universe, **full_params)

                # Run backtest
                result = backtest.run(strategy, data)

                metric_value = result.metrics.get(self.optimization_metric, 0)

                results.append({
                    "params": params,
                    "metric": metric_value,
                    "full_metrics": result.metrics,
                })

                # Check if best
                is_better = (
                    metric_value > best_metric if self.maximize
                    else metric_value < best_metric
                )
                if is_better:
                    best_metric = metric_value
                    best_params = params

            except Exception as e:
                results.append({
                    "params": params,
                    "metric": float("nan"),
                    "error": str(e),
                })

        return OptimizationResult(
            window_id=0,
            best_params=best_params,
            best_metric=best_metric,
            all_results=results,
            optimization_metric=self.optimization_metric,
        )


class WalkForwardOptimizer:
    """
    Walk-forward optimization framework.

    Combines in-sample parameter optimization with out-of-sample testing
    to evaluate strategy robustness and avoid overfitting.
    """

    def __init__(
        self,
        strategy_class: Type[Strategy],
        config: WalkForwardConfig,
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            strategy_class: Strategy class to optimize
            config: Walk-forward configuration
        """
        self.strategy_class = strategy_class
        self.config = config
        self.splitter = WalkForwardSplitter(config)

    def run(
        self,
        data: dict[Symbol, pd.DataFrame],
        universe: list[Symbol] | None = None,
        base_params: dict[str, Any] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> WalkForwardResult:
        """
        Run walk-forward optimization.

        Args:
            data: Dict mapping symbols to OHLCV DataFrames
            universe: List of symbols (defaults to data keys)
            base_params: Base parameters that won't be optimized
            progress_callback: Optional callback(current, total, message)

        Returns:
            WalkForwardResult with aggregated performance
        """
        start_time = datetime.now()
        universe = universe or list(data.keys())
        base_params = base_params or {}

        folds = []
        all_test_returns = []

        # Generate windows
        windows = list(self.splitter.split(data))
        n_windows = len(windows)

        if self.config.verbose:
            print(f"Running walk-forward optimization with {n_windows} windows")

        for i, window in enumerate(windows):
            if progress_callback:
                progress_callback(i + 1, n_windows, f"Processing window {window.window_id}")

            if self.config.verbose:
                print(f"\nWindow {window.window_id}: Train {window.train_start.date()} to {window.train_end.date()}, "
                      f"Test {window.test_start.date()} to {window.test_end.date()}")

            # Step 1: Optimize on training data
            optimizer = ParameterOptimizer(
                strategy_class=self.strategy_class,
                param_grid=self.config.param_grid,
                optimization_metric=self.config.optimization_metric,
                maximize=self.config.maximize_metric,
                backtest_config=self.config.backtest_config,
            )

            opt_result = optimizer.optimize(
                window.train_data,
                universe,
                base_params,
            )

            if self.config.verbose:
                print(f"  Best params: {opt_result.best_params}")
                print(f"  Train {self.config.optimization_metric}: {opt_result.best_metric:.4f}")

            # Step 2: Test on out-of-sample data with optimized params
            full_params = {**base_params, **opt_result.best_params}
            strategy = self.strategy_class(universe=universe, **full_params)

            backtest = VectorizedBacktest(self.config.backtest_config)

            # Training backtest (for metrics comparison)
            train_result = backtest.run(strategy, window.train_data)

            # Test backtest
            test_result = backtest.run(strategy, window.test_data)

            if self.config.verbose:
                print(f"  Test {self.config.optimization_metric}: "
                      f"{test_result.metrics.get(self.config.optimization_metric, 0):.4f}")

            # Record fold results
            fold = WalkForwardFold(
                window_id=window.window_id,
                train_start=window.train_start,
                train_end=window.train_end,
                test_start=window.test_start,
                test_end=window.test_end,
                optimized_params=opt_result.best_params,
                train_metrics=train_result.metrics,
                test_metrics=test_result.metrics,
                test_returns=test_result.returns,
                test_trades=test_result.trades,
            )

            folds.append(fold)
            all_test_returns.append(test_result.returns)

        # Combine out-of-sample returns
        combined_returns = self._combine_returns(all_test_returns)

        # Calculate aggregated metrics
        aggregated_metrics = self._calculate_aggregated_metrics(folds, combined_returns)

        # Analyze parameter stability
        param_stability = self._analyze_param_stability(folds)

        end_time = datetime.now()

        return WalkForwardResult(
            strategy_name=self.strategy_class.name,
            strategy_class=self.strategy_class.__name__,
            folds=folds,
            config=self.config,
            combined_returns=combined_returns,
            aggregated_metrics=aggregated_metrics,
            param_stability=param_stability,
            start_time=start_time,
            end_time=end_time,
            total_runtime_seconds=(end_time - start_time).total_seconds(),
        )

    def _combine_returns(
        self,
        returns_list: list[pd.Series],
    ) -> pd.Series:
        """Combine returns from multiple test periods."""
        if not returns_list:
            return pd.Series(dtype=float)

        # Concatenate chronologically
        combined = pd.concat(returns_list).sort_index()

        # Handle overlapping indices (take last value)
        combined = combined[~combined.index.duplicated(keep="last")]

        return combined

    def _calculate_aggregated_metrics(
        self,
        folds: list[WalkForwardFold],
        combined_returns: pd.Series,
    ) -> dict[str, float]:
        """Calculate aggregated performance metrics."""
        if len(combined_returns) < 2:
            return {}

        # Calculate from combined returns
        period_returns = combined_returns.pct_change().dropna()

        if len(period_returns) == 0:
            return {}

        initial_value = self.config.backtest_config.initial_capital
        total_return = (combined_returns.iloc[-1] / initial_value) - 1

        days = (combined_returns.index[-1] - combined_returns.index[0]).days
        years = days / 365.25 if days > 0 else 1

        cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        volatility = period_returns.std() * np.sqrt(252)
        sharpe = (period_returns.mean() * 252) / volatility if volatility > 0 else 0

        # Drawdown
        cumulative = (1 + period_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Aggregate fold metrics
        test_metrics = [f.test_metrics for f in folds]
        avg_fold_sharpe = np.mean([m.get("sharpe_ratio", 0) for m in test_metrics])
        std_fold_sharpe = np.std([m.get("sharpe_ratio", 0) for m in test_metrics])

        # IS/OOS analysis
        is_ratios = [f.is_ratio for f in folds]
        avg_is_ratio = np.mean(is_ratios)

        # Win rate across folds
        profitable_folds = sum(1 for f in folds if f.test_metrics.get("total_return", 0) > 0)
        fold_win_rate = profitable_folds / len(folds) if folds else 0

        return {
            "total_return": float(total_return),
            "cagr": float(cagr),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "avg_fold_sharpe": float(avg_fold_sharpe),
            "std_fold_sharpe": float(std_fold_sharpe),
            "sharpe_stability": float(avg_fold_sharpe / std_fold_sharpe) if std_fold_sharpe > 0 else 0,
            "avg_is_ratio": float(avg_is_ratio),
            "fold_win_rate": float(fold_win_rate),
            "num_folds": len(folds),
            "total_trades": sum(len(f.test_trades) for f in folds),
        }

    def _analyze_param_stability(
        self,
        folds: list[WalkForwardFold],
    ) -> dict[str, dict[str, float]]:
        """Analyze stability of optimized parameters across folds."""
        if not folds or not folds[0].optimized_params:
            return {}

        param_names = list(folds[0].optimized_params.keys())
        stability = {}

        for param in param_names:
            values = [f.optimized_params.get(param) for f in folds]

            # Filter numeric values
            numeric_values = [v for v in values if isinstance(v, (int, float))]

            if numeric_values:
                stability[param] = {
                    "mean": float(np.mean(numeric_values)),
                    "std": float(np.std(numeric_values)),
                    "min": float(np.min(numeric_values)),
                    "max": float(np.max(numeric_values)),
                    "cv": float(np.std(numeric_values) / np.mean(numeric_values))
                    if np.mean(numeric_values) != 0 else 0,
                }
            else:
                # For categorical parameters, show mode
                from collections import Counter
                counter = Counter(values)
                most_common = counter.most_common(1)[0] if counter else (None, 0)
                stability[param] = {
                    "most_common": most_common[0],
                    "frequency": most_common[1] / len(values) if values else 0,
                }

        return stability


def run_walk_forward(
    strategy_class: Type[Strategy],
    data: dict[Symbol, pd.DataFrame],
    param_grid: dict[str, list[Any]] | None = None,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 21,
    optimization_metric: str = "sharpe_ratio",
    **kwargs: Any,
) -> WalkForwardResult:
    """
    Convenience function to run walk-forward optimization.

    Args:
        strategy_class: Strategy class to optimize
        data: Dict mapping symbols to OHLCV DataFrames
        param_grid: Parameter grid for optimization
        train_days: Training window size
        test_days: Test window size
        step_days: Step size between windows
        optimization_metric: Metric to optimize
        **kwargs: Additional WalkForwardConfig parameters

    Returns:
        WalkForwardResult
    """
    config = WalkForwardConfig(
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
        optimization_metric=optimization_metric,
        param_grid=param_grid or {},
        **kwargs,
    )

    optimizer = WalkForwardOptimizer(strategy_class, config)
    return optimizer.run(data)


def walk_forward_summary(result: WalkForwardResult) -> str:
    """Generate a text summary of walk-forward results."""
    lines = [
        "=" * 60,
        "WALK-FORWARD OPTIMIZATION RESULTS",
        "=" * 60,
        f"Strategy: {result.strategy_name} ({result.strategy_class})",
        f"Number of folds: {len(result.folds)}",
        f"Runtime: {result.total_runtime_seconds:.1f} seconds",
        "",
        "AGGREGATED PERFORMANCE (Out-of-Sample)",
        "-" * 40,
    ]

    metrics = result.aggregated_metrics
    lines.extend([
        f"Total Return: {metrics.get('total_return', 0):.2%}",
        f"CAGR: {metrics.get('cagr', 0):.2%}",
        f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.3f}",
        f"Max Drawdown: {metrics.get('max_drawdown', 0):.2%}",
        f"Volatility: {metrics.get('volatility', 0):.2%}",
        "",
        "STABILITY ANALYSIS",
        "-" * 40,
        f"Avg Fold Sharpe: {metrics.get('avg_fold_sharpe', 0):.3f}",
        f"Sharpe Std Dev: {metrics.get('std_fold_sharpe', 0):.3f}",
        f"Sharpe Stability: {metrics.get('sharpe_stability', 0):.2f}",
        f"Avg IS/OOS Ratio: {metrics.get('avg_is_ratio', 0):.2%}",
        f"Fold Win Rate: {metrics.get('fold_win_rate', 0):.1%}",
        "",
    ])

    if result.param_stability:
        lines.extend([
            "PARAMETER STABILITY",
            "-" * 40,
        ])
        for param, stats in result.param_stability.items():
            if "mean" in stats:
                lines.append(
                    f"{param}: mean={stats['mean']:.4f}, std={stats['std']:.4f}, "
                    f"CV={stats['cv']:.2%}"
                )
            else:
                lines.append(
                    f"{param}: most_common={stats['most_common']}, "
                    f"freq={stats['frequency']:.1%}"
                )

    lines.append("=" * 60)
    return "\n".join(lines)
