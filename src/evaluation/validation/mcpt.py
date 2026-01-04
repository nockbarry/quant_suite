"""Monte Carlo Permutation Testing (MCPT) for strategy validation.

Based on the approach from neurotrader888/mcpt, this module implements
bar permutation testing to determine if strategy performance is
statistically significant or could have occurred by chance.

Key insight: By shuffling the pairing between overnight gaps and intrabar
moves (while preserving return distributions), we create synthetic price
paths that maintain realistic properties but destroy any exploitable patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Type

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from ...core import Symbol
from ...strategies.base import Strategy
from ..backtest.engine import BacktestConfig, BacktestResult, VectorizedBacktest
from ..metrics.returns import (
    cagr,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    total_return,
)


@dataclass
class MCPTConfig:
    """Configuration for Monte Carlo Permutation Testing."""

    n_permutations: int = 1000
    random_seed: int | None = None
    preserve_correlation: bool = True
    preserve_distribution: bool = True
    test_metrics: list[str] = field(
        default_factory=lambda: ["sharpe_ratio", "profit_factor", "total_return"]
    )
    significance_level: float = 0.05
    n_jobs: int = -1  # Parallel processing (-1 = all cores)


@dataclass
class MCPTResult:
    """Results from MCPT analysis."""

    strategy_name: str
    original_metrics: dict[str, float]
    permutation_metrics: dict[str, list[float]]  # metric -> list of n_perm values
    p_values: dict[str, float]  # metric -> p-value
    percentiles: dict[str, dict[str, float]]  # metric -> {5%, 50%, 95%}
    is_significant: dict[str, bool]  # metric -> True if p < significance_level
    n_permutations: int
    config: MCPTConfig
    runtime_seconds: float

    def to_summary(self) -> dict[str, Any]:
        """Generate a summary dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "n_permutations": self.n_permutations,
            "original_metrics": self.original_metrics,
            "p_values": self.p_values,
            "is_significant": self.is_significant,
            "significance_level": self.config.significance_level,
            "runtime_seconds": self.runtime_seconds,
        }

    def summary_table(self) -> pd.DataFrame:
        """Create a summary DataFrame."""
        records = []
        for metric in self.original_metrics:
            records.append(
                {
                    "metric": metric,
                    "original": self.original_metrics[metric],
                    "p_value": self.p_values.get(metric, np.nan),
                    "5th_percentile": self.percentiles.get(metric, {}).get("5%", np.nan),
                    "50th_percentile": self.percentiles.get(metric, {}).get(
                        "50%", np.nan
                    ),
                    "95th_percentile": self.percentiles.get(metric, {}).get(
                        "95%", np.nan
                    ),
                    "significant": self.is_significant.get(metric, False),
                }
            )
        return pd.DataFrame(records)


class BarPermuter:
    """
    Bar permutation algorithm preserving intrabar structure.

    Key insight from neurotrader888/mcpt: Decompose each bar into:
    - Gap return: (Open_t - Close_{t-1}) / Close_{t-1}
    - Intra-bar return: (Close_t - Open_t) / Open_t

    By shuffling the pairing between gaps and intra-bar moves, we:
    1. Preserve the marginal distribution of returns
    2. Preserve intra-bar OHLC relationships
    3. Destroy any temporal dependencies the strategy exploits

    If strategy still performs well on permuted data, it's likely overfitting.
    """

    def __init__(self, preserve_correlation: bool = True):
        """
        Initialize bar permuter.

        Args:
            preserve_correlation: If True, use same permutation indices
                                 across multiple assets to preserve correlation
        """
        self.preserve_correlation = preserve_correlation

    def decompose_bar(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.DataFrame]:
        """
        Decompose OHLCV bars into gap returns and intra-bar structure.

        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume]

        Returns:
            gap_returns: Series of overnight gap returns
            intrabar_structure: DataFrame with relative H/L/C positions
        """
        df = ohlcv.copy()

        # Calculate gap returns (overnight move)
        # Gap = (Open_t - Close_{t-1}) / Close_{t-1}
        prev_close = df["close"].shift(1)
        gap_returns = (df["open"] - prev_close) / prev_close.replace(0, np.nan)
        gap_returns = gap_returns.fillna(0)

        # Calculate intra-bar structure (relative to open)
        # These are the relative positions within each bar
        intrabar_structure = pd.DataFrame(index=df.index)

        # Intra-bar close return: (Close - Open) / Open
        intrabar_structure["close_rel"] = (
            (df["close"] - df["open"]) / df["open"].replace(0, np.nan)
        ).fillna(0)

        # High relative to open (always >= 0)
        intrabar_structure["high_rel"] = (
            (df["high"] - df["open"]) / df["open"].replace(0, np.nan)
        ).fillna(0)

        # Low relative to open (always <= 0)
        intrabar_structure["low_rel"] = (
            (df["low"] - df["open"]) / df["open"].replace(0, np.nan)
        ).fillna(0)

        # Volume (keep as-is for reconstruction)
        intrabar_structure["volume"] = df["volume"]

        return gap_returns, intrabar_structure

    def permute(
        self,
        data: pd.DataFrame,
        random_state: np.random.Generator,
        permutation_indices: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> tuple[pd.DataFrame, tuple[np.ndarray, np.ndarray]]:
        """
        Generate permuted OHLCV data.

        Algorithm:
        1. Decompose into gap and intra-bar returns
        2. Shuffle the pairing between them (not the values themselves)
        3. Reconstruct OHLCV bars ensuring H >= max(O,C), L <= min(O,C)

        Args:
            data: OHLCV DataFrame
            random_state: NumPy random generator
            permutation_indices: Optional pre-computed indices for correlation preservation

        Returns:
            permuted_data: New OHLCV DataFrame with permuted structure
            indices: The permutation indices used (for correlation preservation)
        """
        n_bars = len(data)
        if n_bars < 10:
            return data.copy(), (np.arange(n_bars), np.arange(n_bars))

        # Decompose bars
        gap_returns, intrabar_structure = self.decompose_bar(data)

        # Generate or use provided permutation indices
        if permutation_indices is None:
            # Shuffle gap assignments (which gap goes with which intrabar)
            perm_gap = random_state.permutation(n_bars - 1)  # Skip first bar (no prev close)
            # Shuffle intrabar assignments
            perm_intrabar = random_state.permutation(n_bars - 1)
        else:
            perm_gap, perm_intrabar = permutation_indices

        # Reconstruct OHLCV
        permuted = pd.DataFrame(index=data.index)
        permuted["volume"] = data["volume"].values

        # Start with first bar's close as reference
        prices = np.zeros(n_bars)
        opens = np.zeros(n_bars)
        highs = np.zeros(n_bars)
        lows = np.zeros(n_bars)

        # First bar uses original values
        opens[0] = data["open"].iloc[0]
        highs[0] = data["high"].iloc[0]
        lows[0] = data["low"].iloc[0]
        prices[0] = data["close"].iloc[0]

        # Get shuffled components
        gap_values = gap_returns.iloc[1:].values
        intrabar_values = intrabar_structure.iloc[1:].values

        shuffled_gaps = gap_values[perm_gap]
        shuffled_intrabar = intrabar_values[perm_intrabar]

        # Reconstruct prices sequentially
        for i in range(1, n_bars):
            prev_close = prices[i - 1]

            # Apply shuffled gap to get open
            gap = shuffled_gaps[i - 1]
            opens[i] = prev_close * (1 + gap)

            # Apply shuffled intrabar structure
            close_rel = shuffled_intrabar[i - 1, 0]
            high_rel = shuffled_intrabar[i - 1, 1]
            low_rel = shuffled_intrabar[i - 1, 2]

            prices[i] = opens[i] * (1 + close_rel)
            highs[i] = opens[i] * (1 + high_rel)
            lows[i] = opens[i] * (1 + low_rel)

            # Ensure OHLC constraints are satisfied
            highs[i] = max(highs[i], opens[i], prices[i])
            lows[i] = min(lows[i], opens[i], prices[i])

        permuted["open"] = opens
        permuted["high"] = highs
        permuted["low"] = lows
        permuted["close"] = prices

        return permuted, (perm_gap, perm_intrabar)

    def permute_multi_asset(
        self,
        data: dict[Symbol, pd.DataFrame],
        random_state: np.random.Generator,
    ) -> dict[Symbol, pd.DataFrame]:
        """
        Permute multiple assets while preserving cross-asset correlation.

        Uses the same permutation indices across all assets so that
        contemporaneous relationships are maintained.

        Args:
            data: Dict mapping symbols to OHLCV DataFrames
            random_state: NumPy random generator

        Returns:
            Dict of permuted DataFrames
        """
        if not data:
            return {}

        # Get minimum length for consistent permutation
        min_len = min(len(df) for df in data.values())

        # Generate shared permutation indices
        perm_gap = random_state.permutation(min_len - 1)
        perm_intrabar = random_state.permutation(min_len - 1)
        shared_indices = (perm_gap, perm_intrabar)

        permuted_data = {}
        for symbol, df in data.items():
            if self.preserve_correlation:
                # Use same indices for all assets
                permuted, _ = self.permute(
                    df.iloc[:min_len], random_state, shared_indices
                )
            else:
                # Independent permutation per asset
                permuted, _ = self.permute(df, random_state)
            permuted_data[symbol] = permuted

        return permuted_data


class MCPTAnalyzer:
    """
    Monte Carlo Permutation Testing analyzer.

    Tests whether strategy performance is statistically significant
    or could have occurred by chance on random data.
    """

    # Mapping of metric names to functions
    METRIC_FUNCTIONS: dict[str, Callable] = {
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "profit_factor": profit_factor,
    }

    # Metrics where higher is better
    HIGHER_IS_BETTER: set[str] = {
        "sharpe_ratio",
        "sortino_ratio",
        "total_return",
        "cagr",
        "profit_factor",
    }

    def __init__(self, config: MCPTConfig | None = None):
        """
        Initialize MCPT analyzer.

        Args:
            config: MCPT configuration
        """
        self.config = config or MCPTConfig()
        self.permuter = BarPermuter(self.config.preserve_correlation)
        self._rng = np.random.default_rng(self.config.random_seed)

    def test(
        self,
        strategy: Strategy,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        backtest_config: BacktestConfig | None = None,
    ) -> MCPTResult:
        """
        Run in-sample MCPT.

        1. Run strategy on original data, record metrics
        2. For each permutation:
           - Permute the data
           - Run strategy on permuted data
           - Record metrics
        3. Calculate p-values

        Args:
            strategy: Strategy to test
            data: OHLCV data (single or multi-asset)
            backtest_config: Optional backtest configuration

        Returns:
            MCPTResult with p-values and significance flags
        """
        start_time = datetime.now()

        # Convert to dict format
        if isinstance(data, pd.DataFrame):
            data = {strategy.universe[0] if strategy.universe else "ASSET": data}

        # Run backtest on original data
        backtest = VectorizedBacktest(backtest_config)
        original_result = backtest.run(strategy, data)
        original_metrics = self._extract_metrics(original_result)

        # Run permutation tests
        if self.config.n_jobs == 1:
            # Sequential execution
            permutation_results = []
            for i in range(self.config.n_permutations):
                result = self._run_single_permutation(
                    strategy, data, backtest, i
                )
                permutation_results.append(result)
        else:
            # Parallel execution
            permutation_results = Parallel(n_jobs=self.config.n_jobs)(
                delayed(self._run_single_permutation)(
                    strategy, data, backtest, i
                )
                for i in range(self.config.n_permutations)
            )

        # Organize results by metric
        permutation_metrics = {
            metric: [] for metric in self.config.test_metrics
        }
        for result in permutation_results:
            if result is not None:
                for metric in self.config.test_metrics:
                    permutation_metrics[metric].append(result.get(metric, np.nan))

        # Calculate p-values and percentiles
        p_values = {}
        percentiles = {}
        is_significant = {}

        for metric in self.config.test_metrics:
            original_value = original_metrics.get(metric, np.nan)
            perm_values = [v for v in permutation_metrics[metric] if not np.isnan(v)]

            if perm_values:
                p_values[metric] = self._calculate_p_value(
                    original_value,
                    perm_values,
                    higher_is_better=metric in self.HIGHER_IS_BETTER,
                )
                percentiles[metric] = {
                    "5%": float(np.percentile(perm_values, 5)),
                    "50%": float(np.percentile(perm_values, 50)),
                    "95%": float(np.percentile(perm_values, 95)),
                }
                is_significant[metric] = p_values[metric] < self.config.significance_level
            else:
                p_values[metric] = np.nan
                percentiles[metric] = {"5%": np.nan, "50%": np.nan, "95%": np.nan}
                is_significant[metric] = False

        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        return MCPTResult(
            strategy_name=strategy.name,
            original_metrics=original_metrics,
            permutation_metrics=permutation_metrics,
            p_values=p_values,
            percentiles=percentiles,
            is_significant=is_significant,
            n_permutations=self.config.n_permutations,
            config=self.config,
            runtime_seconds=runtime,
        )

    def test_walk_forward(
        self,
        strategy_class: Type[Strategy],
        strategy_params: dict[str, Any],
        data: dict[Symbol, pd.DataFrame],
        wf_config: Any,  # WalkForwardConfig
        permute_oos_only: bool = True,
    ) -> MCPTResult:
        """
        Walk-forward MCPT.

        For each permutation:
        - If permute_oos_only: Only permute OOS periods
        - Run full walk-forward optimization
        - Record aggregated OOS metrics

        Args:
            strategy_class: Strategy class to instantiate
            strategy_params: Parameters for strategy
            data: Multi-asset OHLCV data
            wf_config: Walk-forward configuration
            permute_oos_only: Only permute out-of-sample periods

        Returns:
            MCPTResult with p-values from walk-forward analysis
        """
        # Import here to avoid circular imports
        from .walk_forward import WalkForwardOptimizer

        start_time = datetime.now()

        # Run original walk-forward
        optimizer = WalkForwardOptimizer(wf_config)
        original_wf_result = optimizer.run(strategy_class, data, strategy_params)
        original_metrics = original_wf_result.aggregated_metrics

        # Run permutation tests
        permutation_results = []
        for i in range(self.config.n_permutations):
            try:
                # Create permuted data
                seed = self.config.random_seed + i if self.config.random_seed else i
                rng = np.random.default_rng(seed)
                permuted_data = self.permuter.permute_multi_asset(data, rng)

                # Run walk-forward on permuted data
                perm_wf_result = optimizer.run(
                    strategy_class, permuted_data, strategy_params
                )
                permutation_results.append(perm_wf_result.aggregated_metrics)
            except Exception:
                permutation_results.append({})

        # Organize and calculate p-values (same as in test())
        permutation_metrics = {
            metric: [] for metric in self.config.test_metrics
        }
        for result in permutation_results:
            for metric in self.config.test_metrics:
                permutation_metrics[metric].append(result.get(metric, np.nan))

        p_values = {}
        percentiles = {}
        is_significant = {}

        for metric in self.config.test_metrics:
            original_value = original_metrics.get(metric, np.nan)
            perm_values = [v for v in permutation_metrics[metric] if not np.isnan(v)]

            if perm_values:
                p_values[metric] = self._calculate_p_value(
                    original_value,
                    perm_values,
                    higher_is_better=metric in self.HIGHER_IS_BETTER,
                )
                percentiles[metric] = {
                    "5%": float(np.percentile(perm_values, 5)),
                    "50%": float(np.percentile(perm_values, 50)),
                    "95%": float(np.percentile(perm_values, 95)),
                }
                is_significant[metric] = p_values[metric] < self.config.significance_level
            else:
                p_values[metric] = np.nan
                percentiles[metric] = {"5%": np.nan, "50%": np.nan, "95%": np.nan}
                is_significant[metric] = False

        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()

        return MCPTResult(
            strategy_name=strategy_class.name if hasattr(strategy_class, "name") else str(strategy_class),
            original_metrics=original_metrics,
            permutation_metrics=permutation_metrics,
            p_values=p_values,
            percentiles=percentiles,
            is_significant=is_significant,
            n_permutations=self.config.n_permutations,
            config=self.config,
            runtime_seconds=runtime,
        )

    def _run_single_permutation(
        self,
        strategy: Strategy,
        data: dict[Symbol, pd.DataFrame],
        backtest: VectorizedBacktest,
        permutation_idx: int,
    ) -> dict[str, float] | None:
        """Run strategy on a single permutation of data."""
        try:
            # Generate permuted data with unique seed
            seed = self.config.random_seed + permutation_idx if self.config.random_seed else permutation_idx
            rng = np.random.default_rng(seed)
            permuted_data = self.permuter.permute_multi_asset(data, rng)

            # Run backtest on permuted data
            result = backtest.run(strategy, permuted_data)
            return self._extract_metrics(result)
        except Exception:
            return None

    def _extract_metrics(self, result: BacktestResult) -> dict[str, float]:
        """Extract relevant metrics from backtest result."""
        metrics = {}

        # Get returns for calculation
        if len(result.returns) > 1:
            # Calculate period returns from cumulative
            cumulative = result.returns
            period_returns = cumulative.pct_change().dropna()

            for metric_name in self.config.test_metrics:
                if metric_name in self.METRIC_FUNCTIONS:
                    try:
                        func = self.METRIC_FUNCTIONS[metric_name]
                        metrics[metric_name] = float(func(period_returns))
                    except Exception:
                        metrics[metric_name] = np.nan
                elif metric_name in result.metrics:
                    metrics[metric_name] = result.metrics[metric_name]
        else:
            for metric_name in self.config.test_metrics:
                metrics[metric_name] = np.nan

        return metrics

    def _calculate_p_value(
        self,
        original_value: float,
        permuted_values: list[float],
        higher_is_better: bool = True,
    ) -> float:
        """
        Calculate p-value.

        P-value = proportion of permutations where permuted metric
                  is >= original (if higher is better) or
                  <= original (if lower is better)

        Args:
            original_value: Metric value on original data
            permuted_values: List of metric values on permuted data
            higher_is_better: Whether higher values are better

        Returns:
            P-value (0 to 1)
        """
        if np.isnan(original_value) or not permuted_values:
            return np.nan

        n = len(permuted_values)
        if higher_is_better:
            # Count permutations with metric >= original
            count = sum(1 for v in permuted_values if v >= original_value)
        else:
            # Count permutations with metric <= original (e.g., max_drawdown)
            count = sum(1 for v in permuted_values if v <= original_value)

        # Add 1 to numerator and denominator for conservative estimate
        return (count + 1) / (n + 1)


# Convenience functions


def mcpt_test(
    strategy: Strategy,
    data: pd.DataFrame | dict[Symbol, pd.DataFrame],
    n_permutations: int = 1000,
    metrics: list[str] | None = None,
    significance_level: float = 0.05,
    random_seed: int | None = None,
    n_jobs: int = -1,
    backtest_config: BacktestConfig | None = None,
) -> MCPTResult:
    """
    Run Monte Carlo Permutation Test on a strategy.

    This is the main convenience function for MCPT testing.

    Args:
        strategy: Strategy to test
        data: OHLCV data (single or multi-asset)
        n_permutations: Number of permutations to run
        metrics: List of metrics to test (default: sharpe_ratio, profit_factor, total_return)
        significance_level: P-value threshold for significance
        random_seed: Random seed for reproducibility
        n_jobs: Number of parallel jobs (-1 = all cores)
        backtest_config: Optional backtest configuration

    Returns:
        MCPTResult with p-values and significance flags

    Example:
        >>> result = mcpt_test(strategy, data, n_permutations=1000)
        >>> print(f"Sharpe p-value: {result.p_values['sharpe_ratio']:.4f}")
        >>> if result.is_significant['sharpe_ratio']:
        ...     print("Strategy has statistically significant Sharpe ratio!")
    """
    config = MCPTConfig(
        n_permutations=n_permutations,
        random_seed=random_seed,
        test_metrics=metrics or ["sharpe_ratio", "profit_factor", "total_return"],
        significance_level=significance_level,
        n_jobs=n_jobs,
    )
    analyzer = MCPTAnalyzer(config)
    return analyzer.test(strategy, data, backtest_config)


def mcpt_walk_forward(
    strategy_class: Type[Strategy],
    strategy_params: dict[str, Any],
    data: dict[Symbol, pd.DataFrame],
    wf_config: Any,
    n_permutations: int = 500,
    metrics: list[str] | None = None,
    significance_level: float = 0.05,
    random_seed: int | None = None,
    n_jobs: int = -1,
) -> MCPTResult:
    """
    Run Monte Carlo Permutation Test with walk-forward validation.

    More rigorous than in-sample MCPT as it tests out-of-sample performance.

    Args:
        strategy_class: Strategy class to instantiate
        strategy_params: Parameters for strategy
        data: Multi-asset OHLCV data
        wf_config: Walk-forward configuration
        n_permutations: Number of permutations
        metrics: List of metrics to test
        significance_level: P-value threshold
        random_seed: Random seed for reproducibility
        n_jobs: Number of parallel jobs

    Returns:
        MCPTResult with p-values from walk-forward analysis

    Example:
        >>> result = mcpt_walk_forward(
        ...     MovingAverageCrossover,
        ...     {"fast_period": 10, "slow_period": 50},
        ...     data,
        ...     wf_config,
        ...     n_permutations=500
        ... )
        >>> print(f"OOS Sharpe p-value: {result.p_values['sharpe_ratio']:.4f}")
    """
    config = MCPTConfig(
        n_permutations=n_permutations,
        random_seed=random_seed,
        test_metrics=metrics or ["sharpe_ratio", "total_return", "cagr"],
        significance_level=significance_level,
        n_jobs=n_jobs,
    )
    analyzer = MCPTAnalyzer(config)
    return analyzer.test_walk_forward(
        strategy_class, strategy_params, data, wf_config
    )


def verify_permutation_properties(
    original_data: pd.DataFrame,
    permuted_data: pd.DataFrame,
) -> dict[str, Any]:
    """
    Verify that permutation preserves key statistical properties.

    Useful for validating the permutation algorithm.

    Args:
        original_data: Original OHLCV DataFrame
        permuted_data: Permuted OHLCV DataFrame

    Returns:
        Dict with comparison of statistical properties
    """
    original_returns = original_data["close"].pct_change().dropna()
    permuted_returns = permuted_data["close"].pct_change().dropna()

    return {
        "original": {
            "mean": float(original_returns.mean()),
            "std": float(original_returns.std()),
            "skew": float(original_returns.skew()),
            "kurtosis": float(original_returns.kurtosis()),
            "min": float(original_returns.min()),
            "max": float(original_returns.max()),
        },
        "permuted": {
            "mean": float(permuted_returns.mean()),
            "std": float(permuted_returns.std()),
            "skew": float(permuted_returns.skew()),
            "kurtosis": float(permuted_returns.kurtosis()),
            "min": float(permuted_returns.min()),
            "max": float(permuted_returns.max()),
        },
        "preservation_quality": {
            "mean_diff_pct": abs(original_returns.mean() - permuted_returns.mean())
            / (abs(original_returns.mean()) + 1e-10)
            * 100,
            "std_diff_pct": abs(original_returns.std() - permuted_returns.std())
            / (original_returns.std() + 1e-10)
            * 100,
        },
    }
