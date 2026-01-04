"""Multiple hypothesis testing for trading strategy evaluation.

Implements White's Reality Check, Hansen's SPA test, and Stepwise SPA
to prevent data snooping bias when evaluating multiple strategies.

References:
- White (2000) "A Reality Check for Data Snooping" - Econometrica
- Hansen (2005) "A Test for Superior Predictive Ability"
- Romano & Wolf (2005) "Stepwise Multiple Testing as Formalized Data Snooping"
"""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

from ..metrics.returns import sharpe_ratio


@dataclass
class BootstrapConfig:
    """Configuration for block bootstrap methods."""

    n_bootstrap: int = 1000
    block_size: int | None = None  # Auto-calculate if None
    method: str = "stationary"  # "stationary", "circular", "moving"
    random_seed: int | None = None


@dataclass
class RealityCheckResult:
    """Results from White's Reality Check."""

    best_strategy: str
    best_performance: float
    p_value: float  # Null: best strategy is no better than benchmark
    strategy_performances: dict[str, float]
    bootstrap_distribution: np.ndarray
    is_significant: bool
    config: BootstrapConfig
    n_strategies: int

    def to_summary(self) -> dict:
        """Generate summary dictionary."""
        return {
            "best_strategy": self.best_strategy,
            "best_performance": self.best_performance,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "n_strategies": self.n_strategies,
            "n_bootstrap": self.config.n_bootstrap,
        }


@dataclass
class SPAResult:
    """Results from Hansen's SPA Test."""

    consistent_p_value: float  # p^c
    lower_p_value: float  # p^l (most conservative)
    upper_p_value: float  # p^u (least conservative)
    significant_strategies: list[str]  # Strategies with p < alpha
    strategy_t_stats: dict[str, float]
    config: BootstrapConfig
    n_strategies: int

    def to_summary(self) -> dict:
        """Generate summary dictionary."""
        return {
            "consistent_p_value": self.consistent_p_value,
            "lower_p_value": self.lower_p_value,
            "upper_p_value": self.upper_p_value,
            "n_significant": len(self.significant_strategies),
            "significant_strategies": self.significant_strategies,
            "n_strategies": self.n_strategies,
        }


@dataclass
class StepwiseSPAResult:
    """Results from Stepwise SPA."""

    significant_strategies: list[str]
    strategy_rankings: dict[str, int]
    family_wise_p_values: dict[str, float]
    sequential_rejections: list[tuple[str, float]]  # (strategy, p-value at rejection)
    n_strategies: int
    alpha: float

    def to_summary(self) -> dict:
        """Generate summary dictionary."""
        return {
            "significant_strategies": self.significant_strategies,
            "n_significant": len(self.significant_strategies),
            "n_strategies": self.n_strategies,
            "alpha": self.alpha,
            "rejection_sequence": self.sequential_rejections,
        }


class BlockBootstrap:
    """
    Block bootstrap for time series with autocorrelation.

    Implements:
    - Stationary bootstrap (random block lengths from geometric distribution)
    - Circular block bootstrap (fixed length, wrap-around)
    - Moving block bootstrap (fixed length, no wrap)
    """

    def __init__(self, config: BootstrapConfig | None = None):
        """
        Initialize block bootstrap.

        Args:
            config: Bootstrap configuration
        """
        self.config = config or BootstrapConfig()
        self._rng = np.random.default_rng(self.config.random_seed)

    def auto_block_size(self, returns: pd.Series) -> int:
        """
        Estimate optimal block size using Politis & White (2004) method.

        Based on autocorrelation structure of the series.

        Args:
            returns: Return series

        Returns:
            Optimal block size
        """
        n = len(returns)
        if n < 10:
            return max(1, n // 2)

        # Calculate autocorrelations up to lag n^(1/3)
        max_lag = int(np.ceil(n ** (1 / 3)))
        max_lag = min(max_lag, n // 2)

        acf_values = self._calculate_acf(returns, max_lag)

        # Find first insignificant lag using Bartlett's formula
        threshold = 1.96 / np.sqrt(n)
        significant_lag = 1

        for lag in range(1, len(acf_values)):
            if abs(acf_values[lag]) < threshold:
                break
            significant_lag = lag

        # Optimal block size is approximately 2 * significant lag
        optimal_size = max(1, min(2 * significant_lag + 1, n // 4))

        return optimal_size

    def _calculate_acf(self, series: pd.Series, max_lag: int) -> np.ndarray:
        """Calculate autocorrelation function."""
        n = len(series)
        mean = series.mean()
        var = series.var()

        if var == 0:
            return np.zeros(max_lag + 1)

        acf = np.zeros(max_lag + 1)
        acf[0] = 1.0

        for lag in range(1, max_lag + 1):
            cov = np.sum((series.iloc[lag:] - mean) * (series.iloc[:-lag] - mean)) / n
            acf[lag] = cov / var

        return acf

    def generate_indices(
        self,
        n_samples: int,
        random_state: np.random.Generator | None = None,
    ) -> np.ndarray:
        """
        Generate bootstrap sample indices.

        Args:
            n_samples: Number of samples in original data
            random_state: Optional random generator

        Returns:
            Array of bootstrap indices
        """
        rng = random_state or self._rng
        block_size = self.config.block_size or self.auto_block_size(
            pd.Series(np.zeros(n_samples))  # Placeholder
        )

        if self.config.method == "stationary":
            return self._stationary_bootstrap(n_samples, block_size, rng)
        elif self.config.method == "circular":
            return self._circular_bootstrap(n_samples, block_size, rng)
        else:  # moving
            return self._moving_bootstrap(n_samples, block_size, rng)

    def _stationary_bootstrap(
        self,
        n: int,
        avg_block_size: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """
        Stationary bootstrap with random block lengths.

        Block lengths follow geometric distribution with mean = avg_block_size.
        """
        p = 1 / avg_block_size  # Probability of starting new block
        indices = []
        pos = rng.integers(0, n)

        while len(indices) < n:
            # Add current position
            indices.append(pos)

            # Decide whether to continue block or start new one
            if rng.random() < p:
                # Start new block at random position
                pos = rng.integers(0, n)
            else:
                # Continue block, wrap around if necessary
                pos = (pos + 1) % n

        return np.array(indices[:n])

    def _circular_bootstrap(
        self,
        n: int,
        block_size: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Circular block bootstrap with wrap-around."""
        n_blocks = int(np.ceil(n / block_size))
        indices = []

        for _ in range(n_blocks):
            start = rng.integers(0, n)
            block = [(start + i) % n for i in range(block_size)]
            indices.extend(block)

        return np.array(indices[:n])

    def _moving_bootstrap(
        self,
        n: int,
        block_size: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Moving block bootstrap without wrap-around."""
        n_blocks = int(np.ceil(n / block_size))
        max_start = n - block_size
        indices = []

        for _ in range(n_blocks):
            start = rng.integers(0, max(1, max_start + 1))
            block = list(range(start, min(start + block_size, n)))
            indices.extend(block)

        return np.array(indices[:n])

    def resample(
        self,
        data: pd.Series | pd.DataFrame,
        random_state: np.random.Generator | None = None,
    ) -> pd.Series | pd.DataFrame:
        """
        Resample data using block bootstrap.

        Args:
            data: Series or DataFrame to resample
            random_state: Optional random generator

        Returns:
            Resampled data
        """
        n = len(data)

        # Auto-calculate block size if needed
        if self.config.block_size is None:
            if isinstance(data, pd.Series):
                self.config.block_size = self.auto_block_size(data)
            else:
                self.config.block_size = self.auto_block_size(data.iloc[:, 0])

        indices = self.generate_indices(n, random_state)

        if isinstance(data, pd.Series):
            return data.iloc[indices].reset_index(drop=True)
        else:
            return data.iloc[indices].reset_index(drop=True)


class WhiteRealityCheck:
    """
    White's Reality Check (2000).

    Tests the null hypothesis that the best strategy from a family
    is no better than a benchmark (typically buy-and-hold).

    Accounts for data snooping bias when many strategies are tested.

    Limitations:
    - Conservative (can reject good strategies when many bad ones included)
    - Type II error prone
    """

    def __init__(self, config: BootstrapConfig | None = None):
        """
        Initialize Reality Check.

        Args:
            config: Bootstrap configuration
        """
        self.config = config or BootstrapConfig()
        self.bootstrap = BlockBootstrap(self.config)

    def test(
        self,
        strategy_returns: dict[str, pd.Series],
        benchmark_returns: pd.Series | None = None,
        performance_metric: Callable = sharpe_ratio,
        alpha: float = 0.05,
    ) -> RealityCheckResult:
        """
        Run Reality Check.

        H0: max_k E[f_k] <= 0 (best strategy has non-positive expected performance)
        H1: max_k E[f_k] > 0 (at least one strategy has positive expected performance)

        Where f_k = (strategy_k_performance - benchmark_performance)

        Args:
            strategy_returns: Dict mapping strategy names to return series
            benchmark_returns: Benchmark return series (default: zero returns)
            performance_metric: Function to calculate performance (default: Sharpe)
            alpha: Significance level

        Returns:
            RealityCheckResult with p-value and significance
        """
        if not strategy_returns:
            raise ValueError("No strategies provided")

        # Align all series to common index
        strategy_names = list(strategy_returns.keys())
        aligned_returns = self._align_series(strategy_returns)

        if benchmark_returns is not None:
            benchmark_aligned = benchmark_returns.reindex(aligned_returns.index).fillna(0)
        else:
            benchmark_aligned = pd.Series(0, index=aligned_returns.index)

        n = len(aligned_returns)

        # Calculate original performance differences
        strategy_performances = {}
        performance_diffs = {}

        for name in strategy_names:
            strat_perf = performance_metric(aligned_returns[name])
            bench_perf = performance_metric(benchmark_aligned)
            strategy_performances[name] = strat_perf
            performance_diffs[name] = strat_perf - bench_perf

        # Original test statistic: maximum performance difference
        original_max = max(performance_diffs.values())
        best_strategy = max(performance_diffs, key=performance_diffs.get)

        # Bootstrap distribution of max performance difference
        rng = np.random.default_rng(self.config.random_seed)
        bootstrap_max = []

        for b in range(self.config.n_bootstrap):
            # Generate bootstrap indices
            indices = self.bootstrap.generate_indices(n, rng)

            # Calculate performance for each strategy on bootstrap sample
            boot_max = -np.inf
            for name in strategy_names:
                boot_returns = aligned_returns[name].iloc[indices].reset_index(drop=True)
                boot_perf = performance_metric(boot_returns)

                # Center around original performance (for null distribution)
                boot_diff = boot_perf - performance_diffs[name]
                boot_max = max(boot_max, boot_diff)

            bootstrap_max.append(boot_max)

        bootstrap_max = np.array(bootstrap_max)

        # P-value: proportion of bootstrap samples where max >= original
        p_value = np.mean(bootstrap_max >= original_max)

        return RealityCheckResult(
            best_strategy=best_strategy,
            best_performance=strategy_performances[best_strategy],
            p_value=p_value,
            strategy_performances=strategy_performances,
            bootstrap_distribution=bootstrap_max,
            is_significant=p_value < alpha,
            config=self.config,
            n_strategies=len(strategy_names),
        )

    def _align_series(
        self, strategy_returns: dict[str, pd.Series]
    ) -> pd.DataFrame:
        """Align all return series to common index."""
        df = pd.DataFrame(strategy_returns)
        df = df.dropna()
        return df


class HansenSPA:
    """
    Hansen's Superior Predictive Ability Test (2005).

    More powerful than White's RC by avoiding the "least favorable
    configuration" problem - doesn't assume all bad strategies
    have exactly zero expected performance.

    Returns three p-values:
    - p^l (lower): Most conservative
    - p^c (consistent): Consistent estimator
    - p^u (upper): Least conservative
    """

    def __init__(self, config: BootstrapConfig | None = None):
        """
        Initialize SPA test.

        Args:
            config: Bootstrap configuration
        """
        self.config = config or BootstrapConfig()
        self.bootstrap = BlockBootstrap(self.config)

    def test(
        self,
        strategy_returns: dict[str, pd.Series],
        benchmark_returns: pd.Series | None = None,
        performance_metric: Callable = sharpe_ratio,
        alpha: float = 0.05,
    ) -> SPAResult:
        """
        Run SPA test.

        Args:
            strategy_returns: Dict mapping strategy names to return series
            benchmark_returns: Benchmark return series
            performance_metric: Function to calculate performance
            alpha: Significance level

        Returns:
            SPAResult with three p-values
        """
        if not strategy_returns:
            raise ValueError("No strategies provided")

        strategy_names = list(strategy_returns.keys())
        aligned_returns = self._align_series(strategy_returns)

        if benchmark_returns is not None:
            benchmark_aligned = benchmark_returns.reindex(aligned_returns.index).fillna(0)
        else:
            benchmark_aligned = pd.Series(0, index=aligned_returns.index)

        n = len(aligned_returns)
        k = len(strategy_names)

        # Calculate performance differences and standard errors
        perf_diffs = {}
        std_errors = {}
        t_stats = {}

        for name in strategy_names:
            # Calculate rolling performance difference
            diff_series = aligned_returns[name] - benchmark_aligned

            # Use mean difference as performance measure
            mean_diff = diff_series.mean()
            std_err = diff_series.std() / np.sqrt(n)

            perf_diffs[name] = mean_diff
            std_errors[name] = std_err if std_err > 0 else 1e-10
            t_stats[name] = mean_diff / std_errors[name]

        # Original SPA statistic
        max_t = max(t_stats.values())

        # Bootstrap for three p-values
        rng = np.random.default_rng(self.config.random_seed)

        boot_stats_c = []  # Consistent
        boot_stats_l = []  # Lower
        boot_stats_u = []  # Upper

        for b in range(self.config.n_bootstrap):
            indices = self.bootstrap.generate_indices(n, rng)

            boot_t_stats = {}
            for name in strategy_names:
                boot_diff = (
                    aligned_returns[name].iloc[indices] -
                    benchmark_aligned.iloc[indices]
                ).reset_index(drop=True)

                boot_mean = boot_diff.mean()
                boot_std = boot_diff.std() / np.sqrt(n)

                # Center for null distribution
                centered_mean = boot_mean - perf_diffs[name]

                if boot_std > 0:
                    boot_t_stats[name] = centered_mean / boot_std
                else:
                    boot_t_stats[name] = 0

            # Calculate three versions of max statistic
            # p^c: Use all strategies
            boot_stats_c.append(max(boot_t_stats.values()))

            # p^l: Only strategies with positive sample mean
            positive_stats = [
                boot_t_stats[name] for name in strategy_names
                if perf_diffs[name] > 0
            ]
            boot_stats_l.append(max(positive_stats) if positive_stats else 0)

            # p^u: Set negative means to zero
            adjusted_stats = [
                max(0, boot_t_stats[name]) for name in strategy_names
            ]
            boot_stats_u.append(max(adjusted_stats))

        # Calculate p-values
        p_consistent = np.mean(np.array(boot_stats_c) >= max_t)
        p_lower = np.mean(np.array(boot_stats_l) >= max_t)
        p_upper = np.mean(np.array(boot_stats_u) >= max_t)

        # Identify significant strategies
        significant = [
            name for name, t in t_stats.items()
            if t > np.percentile(boot_stats_c, 100 * (1 - alpha))
        ]

        return SPAResult(
            consistent_p_value=p_consistent,
            lower_p_value=p_lower,
            upper_p_value=p_upper,
            significant_strategies=significant,
            strategy_t_stats=t_stats,
            config=self.config,
            n_strategies=k,
        )

    def _align_series(
        self, strategy_returns: dict[str, pd.Series]
    ) -> pd.DataFrame:
        """Align all return series to common index."""
        df = pd.DataFrame(strategy_returns)
        df = df.dropna()
        return df


class StepwiseSPA:
    """
    Romano-Wolf Stepwise SPA procedure.

    Identifies which specific strategies have significant predictive ability,
    not just whether any strategy is significant.

    Controls familywise error rate (FWER) - probability of making any
    false rejections.
    """

    def __init__(self, alpha: float = 0.05, config: BootstrapConfig | None = None):
        """
        Initialize Stepwise SPA.

        Args:
            alpha: Familywise error rate to control
            config: Bootstrap configuration
        """
        self.alpha = alpha
        self.config = config or BootstrapConfig()
        self.bootstrap = BlockBootstrap(self.config)

    def test(
        self,
        strategy_returns: dict[str, pd.Series],
        benchmark_returns: pd.Series | None = None,
        performance_metric: Callable = sharpe_ratio,
    ) -> StepwiseSPAResult:
        """
        Run stepwise procedure.

        Algorithm:
        1. Test all strategies jointly using SPA
        2. If rejected, identify most significant strategy, remove from set
        3. Repeat until no rejections

        Args:
            strategy_returns: Dict mapping strategy names to return series
            benchmark_returns: Benchmark return series
            performance_metric: Function to calculate performance

        Returns:
            StepwiseSPAResult with list of significant strategies
        """
        if not strategy_returns:
            raise ValueError("No strategies provided")

        strategy_names = list(strategy_returns.keys())
        aligned_returns = self._align_series(strategy_returns)

        if benchmark_returns is not None:
            benchmark_aligned = benchmark_returns.reindex(aligned_returns.index).fillna(0)
        else:
            benchmark_aligned = pd.Series(0, index=aligned_returns.index)

        n = len(aligned_returns)

        # Calculate t-statistics for all strategies
        perf_diffs = {}
        std_errors = {}
        t_stats = {}

        for name in strategy_names:
            diff_series = aligned_returns[name] - benchmark_aligned
            mean_diff = diff_series.mean()
            std_err = diff_series.std() / np.sqrt(n)

            perf_diffs[name] = mean_diff
            std_errors[name] = std_err if std_err > 0 else 1e-10
            t_stats[name] = mean_diff / std_errors[name]

        # Rank strategies by t-statistic
        rankings = {
            name: rank for rank, name in enumerate(
                sorted(t_stats, key=t_stats.get, reverse=True), 1
            )
        }

        # Stepwise procedure
        remaining_strategies = set(strategy_names)
        significant_strategies = []
        sequential_rejections = []
        family_wise_p_values = {}
        rng = np.random.default_rng(self.config.random_seed)

        while remaining_strategies:
            # Find strategy with maximum t-stat among remaining
            max_name = max(remaining_strategies, key=lambda x: t_stats[x])
            max_t = t_stats[max_name]

            if max_t <= 0:
                # No positive t-stats remaining
                break

            # Bootstrap test for current maximum
            boot_max = []
            for b in range(self.config.n_bootstrap):
                indices = self.bootstrap.generate_indices(n, rng)

                boot_max_t = -np.inf
                for name in remaining_strategies:
                    boot_diff = (
                        aligned_returns[name].iloc[indices] -
                        benchmark_aligned.iloc[indices]
                    ).reset_index(drop=True)

                    boot_mean = boot_diff.mean()
                    boot_std = boot_diff.std() / np.sqrt(n)

                    # Center for null
                    centered = boot_mean - perf_diffs[name]
                    if boot_std > 0:
                        boot_t = centered / boot_std
                    else:
                        boot_t = 0

                    boot_max_t = max(boot_max_t, boot_t)

                boot_max.append(boot_max_t)

            # Calculate stepwise p-value
            p_value = np.mean(np.array(boot_max) >= max_t)
            family_wise_p_values[max_name] = p_value

            if p_value < self.alpha:
                # Reject: this strategy is significant
                significant_strategies.append(max_name)
                sequential_rejections.append((max_name, p_value))
                remaining_strategies.remove(max_name)
            else:
                # Accept null: stop procedure
                # Remaining strategies are not significant
                for name in remaining_strategies:
                    family_wise_p_values[name] = p_value
                break

        return StepwiseSPAResult(
            significant_strategies=significant_strategies,
            strategy_rankings=rankings,
            family_wise_p_values=family_wise_p_values,
            sequential_rejections=sequential_rejections,
            n_strategies=len(strategy_names),
            alpha=self.alpha,
        )

    def _align_series(
        self, strategy_returns: dict[str, pd.Series]
    ) -> pd.DataFrame:
        """Align all return series to common index."""
        df = pd.DataFrame(strategy_returns)
        df = df.dropna()
        return df


# Convenience functions


def reality_check(
    strategies: dict[str, pd.Series] | list,
    benchmark: pd.Series | None = None,
    n_bootstrap: int = 1000,
    block_size: int | None = None,
    alpha: float = 0.05,
    random_seed: int | None = None,
) -> RealityCheckResult:
    """
    Run White's Reality Check on strategy returns.

    Tests whether the best strategy is significantly better than benchmark.

    Args:
        strategies: Dict of strategy returns or list of BacktestResults
        benchmark: Benchmark returns (default: zero)
        n_bootstrap: Number of bootstrap samples
        block_size: Block size for bootstrap (auto if None)
        alpha: Significance level
        random_seed: Random seed

    Returns:
        RealityCheckResult

    Example:
        >>> result = reality_check(
        ...     {"ma_10_50": returns1, "ma_20_100": returns2},
        ...     benchmark=spy_returns
        ... )
        >>> print(f"Best: {result.best_strategy}, p={result.p_value:.4f}")
    """
    # Convert BacktestResults to returns if needed
    if isinstance(strategies, list):
        strategies = {
            r.strategy_name: r.returns.pct_change().dropna()
            for r in strategies
        }

    config = BootstrapConfig(
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        random_seed=random_seed,
    )
    test = WhiteRealityCheck(config)
    return test.test(strategies, benchmark, alpha=alpha)


def spa_test(
    strategies: dict[str, pd.Series] | list,
    benchmark: pd.Series | None = None,
    n_bootstrap: int = 1000,
    block_size: int | None = None,
    alpha: float = 0.05,
    random_seed: int | None = None,
) -> SPAResult:
    """
    Run Hansen's SPA test on strategy returns.

    More powerful than Reality Check, returns three p-values:
    - consistent: Standard estimate
    - lower: Most conservative
    - upper: Least conservative

    Args:
        strategies: Dict of strategy returns or list of BacktestResults
        benchmark: Benchmark returns
        n_bootstrap: Number of bootstrap samples
        block_size: Block size for bootstrap
        alpha: Significance level
        random_seed: Random seed

    Returns:
        SPAResult

    Example:
        >>> result = spa_test(strategies, benchmark=spy_returns)
        >>> print(f"SPA p-value: {result.consistent_p_value:.4f}")
    """
    if isinstance(strategies, list):
        strategies = {
            r.strategy_name: r.returns.pct_change().dropna()
            for r in strategies
        }

    config = BootstrapConfig(
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        random_seed=random_seed,
    )
    test = HansenSPA(config)
    return test.test(strategies, benchmark, alpha=alpha)


def stepwise_spa(
    strategies: dict[str, pd.Series] | list,
    benchmark: pd.Series | None = None,
    alpha: float = 0.05,
    n_bootstrap: int = 1000,
    block_size: int | None = None,
    random_seed: int | None = None,
) -> StepwiseSPAResult:
    """
    Run Stepwise SPA to identify which specific strategies are significant.

    Controls familywise error rate while identifying all significant strategies.

    Args:
        strategies: Dict of strategy returns or list of BacktestResults
        benchmark: Benchmark returns
        alpha: Familywise error rate to control
        n_bootstrap: Number of bootstrap samples
        block_size: Block size for bootstrap
        random_seed: Random seed

    Returns:
        StepwiseSPAResult with list of significant strategies

    Example:
        >>> result = stepwise_spa(strategies, benchmark=spy_returns, alpha=0.05)
        >>> print(f"Significant strategies: {result.significant_strategies}")
    """
    if isinstance(strategies, list):
        strategies = {
            r.strategy_name: r.returns.pct_change().dropna()
            for r in strategies
        }

    config = BootstrapConfig(
        n_bootstrap=n_bootstrap,
        block_size=block_size,
        random_seed=random_seed,
    )
    test = StepwiseSPA(alpha, config)
    return test.test(strategies, benchmark)


def multiple_testing_summary(
    strategies: dict[str, pd.Series],
    benchmark: pd.Series | None = None,
    alpha: float = 0.05,
    n_bootstrap: int = 1000,
    random_seed: int | None = None,
) -> dict:
    """
    Run all multiple testing procedures and return comprehensive summary.

    Args:
        strategies: Dict of strategy returns
        benchmark: Benchmark returns
        alpha: Significance level
        n_bootstrap: Number of bootstrap samples
        random_seed: Random seed

    Returns:
        Dict with results from all tests

    Example:
        >>> summary = multiple_testing_summary(strategies)
        >>> print(f"Reality Check p-value: {summary['reality_check']['p_value']:.4f}")
        >>> print(f"SPA p-value: {summary['spa']['consistent_p_value']:.4f}")
        >>> print(f"Significant strategies: {summary['stepwise_spa']['significant']}")
    """
    config = BootstrapConfig(n_bootstrap=n_bootstrap, random_seed=random_seed)

    # Run all tests
    rc_result = WhiteRealityCheck(config).test(strategies, benchmark, alpha=alpha)
    spa_result = HansenSPA(config).test(strategies, benchmark, alpha=alpha)
    stepwise_result = StepwiseSPA(alpha, config).test(strategies, benchmark)

    return {
        "n_strategies": len(strategies),
        "alpha": alpha,
        "reality_check": {
            "p_value": rc_result.p_value,
            "is_significant": rc_result.is_significant,
            "best_strategy": rc_result.best_strategy,
        },
        "spa": {
            "consistent_p_value": spa_result.consistent_p_value,
            "lower_p_value": spa_result.lower_p_value,
            "upper_p_value": spa_result.upper_p_value,
        },
        "stepwise_spa": {
            "significant": stepwise_result.significant_strategies,
            "n_significant": len(stepwise_result.significant_strategies),
            "rankings": stepwise_result.strategy_rankings,
        },
    }
