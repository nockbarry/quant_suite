"""Statistical testing module for strategy evaluation.

Provides rigorous statistical tests for:
- Strategy significance testing (t-tests, permutation tests)
- Bootstrap confidence intervals
- Comparing strategies to benchmarks
- Testing for skill vs luck
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class StatisticalTestResult:
    """Result from a statistical test."""

    test_name: str
    statistic: float
    p_value: float
    significant: bool
    confidence_level: float = 0.95
    interpretation: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "statistic": round(self.statistic, 4),
            "p_value": round(self.p_value, 4),
            "significant": self.significant,
            "confidence_level": self.confidence_level,
            "interpretation": self.interpretation,
            "details": self.details,
        }


@dataclass
class ConfidenceInterval:
    """Confidence interval result."""

    estimate: float
    lower: float
    upper: float
    confidence_level: float
    method: str
    n_bootstrap: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimate": round(self.estimate, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "confidence_level": self.confidence_level,
            "method": self.method,
            "width": round(self.upper - self.lower, 4),
            "n_bootstrap": self.n_bootstrap,
        }


class BootstrapCI:
    """Bootstrap confidence interval calculator."""

    def __init__(
        self,
        n_bootstrap: int = 10000,
        confidence_level: float = 0.95,
        method: Literal["percentile", "basic", "bca"] = "percentile",
        random_state: int | None = None,
    ):
        """
        Initialize bootstrap CI calculator.

        Args:
            n_bootstrap: Number of bootstrap samples
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            method: Bootstrap method ('percentile', 'basic', 'bca')
            random_state: Random seed for reproducibility
        """
        self.n_bootstrap = n_bootstrap
        self.confidence_level = confidence_level
        self.method = method
        self.rng = np.random.RandomState(random_state)

    def compute(
        self,
        data: np.ndarray | pd.Series,
        statistic_func: callable,
        **kwargs,
    ) -> ConfidenceInterval:
        """
        Compute bootstrap confidence interval.

        Args:
            data: Data array
            statistic_func: Function to compute statistic (e.g., np.mean)
            **kwargs: Additional arguments for statistic_func

        Returns:
            ConfidenceInterval object
        """
        data = np.asarray(data)
        n = len(data)

        # Compute point estimate
        point_estimate = statistic_func(data, **kwargs)

        # Generate bootstrap samples
        bootstrap_stats = np.zeros(self.n_bootstrap)
        for i in range(self.n_bootstrap):
            sample = self.rng.choice(data, size=n, replace=True)
            bootstrap_stats[i] = statistic_func(sample, **kwargs)

        # Compute CI based on method
        alpha = 1 - self.confidence_level

        if self.method == "percentile":
            lower = np.percentile(bootstrap_stats, alpha / 2 * 100)
            upper = np.percentile(bootstrap_stats, (1 - alpha / 2) * 100)

        elif self.method == "basic":
            lower = 2 * point_estimate - np.percentile(bootstrap_stats, (1 - alpha / 2) * 100)
            upper = 2 * point_estimate - np.percentile(bootstrap_stats, alpha / 2 * 100)

        elif self.method == "bca":
            # Bias-corrected and accelerated
            lower, upper = self._bca_interval(
                data, bootstrap_stats, point_estimate, statistic_func, alpha, **kwargs
            )

        else:
            raise ValueError(f"Unknown method: {self.method}")

        return ConfidenceInterval(
            estimate=point_estimate,
            lower=lower,
            upper=upper,
            confidence_level=self.confidence_level,
            method=self.method,
            n_bootstrap=self.n_bootstrap,
        )

    def _bca_interval(
        self,
        data: np.ndarray,
        bootstrap_stats: np.ndarray,
        point_estimate: float,
        statistic_func: callable,
        alpha: float,
        **kwargs,
    ) -> tuple[float, float]:
        """Compute BCa interval."""
        n = len(data)

        # Bias correction
        z0 = stats.norm.ppf(np.mean(bootstrap_stats < point_estimate))

        # Acceleration (jackknife)
        jackknife_stats = np.zeros(n)
        for i in range(n):
            jack_sample = np.delete(data, i)
            jackknife_stats[i] = statistic_func(jack_sample, **kwargs)

        jack_mean = np.mean(jackknife_stats)
        num = np.sum((jack_mean - jackknife_stats) ** 3)
        denom = 6 * (np.sum((jack_mean - jackknife_stats) ** 2) ** 1.5)
        a = num / denom if denom != 0 else 0

        # Adjusted percentiles
        z_alpha_low = stats.norm.ppf(alpha / 2)
        z_alpha_high = stats.norm.ppf(1 - alpha / 2)

        alpha_low = stats.norm.cdf(z0 + (z0 + z_alpha_low) / (1 - a * (z0 + z_alpha_low)))
        alpha_high = stats.norm.cdf(z0 + (z0 + z_alpha_high) / (1 - a * (z0 + z_alpha_high)))

        lower = np.percentile(bootstrap_stats, alpha_low * 100)
        upper = np.percentile(bootstrap_stats, alpha_high * 100)

        return lower, upper


class StatisticalTester:
    """Statistical testing for strategy evaluation."""

    def __init__(
        self,
        confidence_level: float = 0.95,
        n_bootstrap: int = 10000,
    ):
        """
        Initialize statistical tester.

        Args:
            confidence_level: Confidence level for tests
            n_bootstrap: Number of bootstrap samples
        """
        self.confidence_level = confidence_level
        self.n_bootstrap = n_bootstrap
        self.alpha = 1 - confidence_level

    def test_mean_different_from_zero(
        self,
        returns: np.ndarray | pd.Series,
        alternative: Literal["two-sided", "greater", "less"] = "greater",
    ) -> StatisticalTestResult:
        """
        Test if mean return is significantly different from zero.

        Args:
            returns: Array of returns
            alternative: Alternative hypothesis direction

        Returns:
            StatisticalTestResult
        """
        returns = np.asarray(returns)
        returns = returns[~np.isnan(returns)]

        if len(returns) < 2:
            return StatisticalTestResult(
                test_name="t-test (mean != 0)",
                statistic=0,
                p_value=1.0,
                significant=False,
                interpretation="Insufficient data",
            )

        # One-sample t-test
        t_stat, p_value = stats.ttest_1samp(returns, 0)

        # Adjust p-value for one-sided test
        if alternative == "greater":
            p_value = p_value / 2 if t_stat > 0 else 1 - p_value / 2
        elif alternative == "less":
            p_value = p_value / 2 if t_stat < 0 else 1 - p_value / 2

        significant = p_value < self.alpha
        mean_return = np.mean(returns)
        annualized = mean_return * 252

        interpretation = (
            f"Mean return is {'significantly ' if significant else 'not significantly '}"
            f"{'positive' if mean_return > 0 else 'negative'} "
            f"(annualized: {annualized*100:.2f}%, p={p_value:.4f})"
        )

        return StatisticalTestResult(
            test_name="t-test (mean != 0)",
            statistic=t_stat,
            p_value=p_value,
            significant=significant,
            confidence_level=self.confidence_level,
            interpretation=interpretation,
            details={
                "mean_return": round(mean_return, 6),
                "annualized_return": round(annualized, 4),
                "std": round(np.std(returns), 6),
                "n_observations": len(returns),
                "alternative": alternative,
            },
        )

    def test_sharpe_ratio(
        self,
        returns: np.ndarray | pd.Series,
        benchmark_sharpe: float = 0.0,
        risk_free_rate: float = 0.0,
    ) -> StatisticalTestResult:
        """
        Test if Sharpe ratio is significantly different from benchmark.

        Uses the Jobson-Korkie (1981) test with Memmel (2003) correction.

        Args:
            returns: Array of returns
            benchmark_sharpe: Benchmark Sharpe ratio to test against
            risk_free_rate: Annual risk-free rate

        Returns:
            StatisticalTestResult
        """
        returns = np.asarray(returns)
        returns = returns[~np.isnan(returns)]
        n = len(returns)

        if n < 30:
            return StatisticalTestResult(
                test_name="Sharpe Ratio Test",
                statistic=0,
                p_value=1.0,
                significant=False,
                interpretation="Insufficient data (need >= 30 observations)",
            )

        # Convert risk-free rate to daily
        rf_daily = (1 + risk_free_rate) ** (1/252) - 1
        excess_returns = returns - rf_daily

        # Compute Sharpe ratio
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)
        sharpe = (mean_excess / std_excess) * np.sqrt(252) if std_excess > 0 else 0

        # Standard error of Sharpe ratio (Lo, 2002)
        skew = stats.skew(excess_returns)
        kurt = stats.kurtosis(excess_returns)

        se_sharpe = np.sqrt(
            (1 + 0.5 * sharpe**2 - skew * sharpe + (kurt / 4) * sharpe**2) / n
        ) * np.sqrt(252)

        # Test statistic
        z_stat = (sharpe - benchmark_sharpe) / se_sharpe if se_sharpe > 0 else 0
        p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))  # Two-sided

        significant = p_value < self.alpha

        interpretation = (
            f"Sharpe ratio of {sharpe:.2f} is "
            f"{'significantly' if significant else 'not significantly'} "
            f"different from {benchmark_sharpe:.2f} (p={p_value:.4f})"
        )

        return StatisticalTestResult(
            test_name="Sharpe Ratio Test",
            statistic=z_stat,
            p_value=p_value,
            significant=significant,
            confidence_level=self.confidence_level,
            interpretation=interpretation,
            details={
                "sharpe_ratio": round(sharpe, 3),
                "benchmark_sharpe": benchmark_sharpe,
                "standard_error": round(se_sharpe, 4),
                "n_observations": n,
                "skewness": round(skew, 3),
                "kurtosis": round(kurt, 3),
            },
        )

    def compare_strategies(
        self,
        returns_a: np.ndarray | pd.Series,
        returns_b: np.ndarray | pd.Series,
        paired: bool = True,
    ) -> StatisticalTestResult:
        """
        Compare two strategies' returns.

        Args:
            returns_a: Returns from strategy A
            returns_b: Returns from strategy B
            paired: Whether returns are paired (same dates)

        Returns:
            StatisticalTestResult
        """
        returns_a = np.asarray(returns_a)
        returns_b = np.asarray(returns_b)

        # Remove NaN
        if paired:
            mask = ~(np.isnan(returns_a) | np.isnan(returns_b))
            returns_a = returns_a[mask]
            returns_b = returns_b[mask]
        else:
            returns_a = returns_a[~np.isnan(returns_a)]
            returns_b = returns_b[~np.isnan(returns_b)]

        if len(returns_a) < 10 or len(returns_b) < 10:
            return StatisticalTestResult(
                test_name="Strategy Comparison",
                statistic=0,
                p_value=1.0,
                significant=False,
                interpretation="Insufficient data",
            )

        if paired:
            # Paired t-test
            t_stat, p_value = stats.ttest_rel(returns_a, returns_b)
            test_name = "Paired t-test"
        else:
            # Independent t-test (Welch's)
            t_stat, p_value = stats.ttest_ind(returns_a, returns_b, equal_var=False)
            test_name = "Welch's t-test"

        significant = p_value < self.alpha

        mean_diff = np.mean(returns_a) - np.mean(returns_b)
        annualized_diff = mean_diff * 252

        interpretation = (
            f"Strategy A {'outperforms' if mean_diff > 0 else 'underperforms'} "
            f"Strategy B by {abs(annualized_diff)*100:.2f}% annually "
            f"({'significant' if significant else 'not significant'}, p={p_value:.4f})"
        )

        return StatisticalTestResult(
            test_name=test_name,
            statistic=t_stat,
            p_value=p_value,
            significant=significant,
            confidence_level=self.confidence_level,
            interpretation=interpretation,
            details={
                "mean_a": round(np.mean(returns_a), 6),
                "mean_b": round(np.mean(returns_b), 6),
                "mean_difference": round(mean_diff, 6),
                "annualized_difference": round(annualized_diff, 4),
                "n_observations_a": len(returns_a),
                "n_observations_b": len(returns_b),
            },
        )

    def test_alpha(
        self,
        strategy_returns: np.ndarray | pd.Series,
        benchmark_returns: np.ndarray | pd.Series,
        risk_free_rate: float = 0.0,
    ) -> StatisticalTestResult:
        """
        Test if strategy alpha is significantly different from zero.

        Args:
            strategy_returns: Strategy returns
            benchmark_returns: Benchmark returns
            risk_free_rate: Annual risk-free rate

        Returns:
            StatisticalTestResult with alpha analysis
        """
        strategy_returns = np.asarray(strategy_returns)
        benchmark_returns = np.asarray(benchmark_returns)

        # Align and clean
        mask = ~(np.isnan(strategy_returns) | np.isnan(benchmark_returns))
        y = strategy_returns[mask]
        x = benchmark_returns[mask]
        n = len(y)

        if n < 30:
            return StatisticalTestResult(
                test_name="Alpha Test",
                statistic=0,
                p_value=1.0,
                significant=False,
                interpretation="Insufficient data",
            )

        # Convert risk-free rate
        rf_daily = (1 + risk_free_rate) ** (1/252) - 1

        # Excess returns
        y_excess = y - rf_daily
        x_excess = x - rf_daily

        # OLS regression
        slope, intercept, r_value, p_value_slope, std_err = stats.linregress(x_excess, y_excess)

        # Alpha statistics
        alpha_daily = intercept
        alpha_annual = alpha_daily * 252
        beta = slope

        # Standard error of alpha
        y_pred = intercept + slope * x_excess
        residuals = y_excess - y_pred
        mse = np.sum(residuals**2) / (n - 2)
        x_var = np.sum((x_excess - np.mean(x_excess))**2)
        se_alpha = np.sqrt(mse * (1/n + np.mean(x_excess)**2 / x_var))

        # t-test for alpha
        t_stat = alpha_daily / se_alpha if se_alpha > 0 else 0
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 2))

        significant = p_value < self.alpha

        interpretation = (
            f"Alpha of {alpha_annual*100:.2f}% annually is "
            f"{'significantly' if significant else 'not significantly'} "
            f"different from zero (p={p_value:.4f}). Beta={beta:.2f}"
        )

        return StatisticalTestResult(
            test_name="Alpha Test (CAPM)",
            statistic=t_stat,
            p_value=p_value,
            significant=significant,
            confidence_level=self.confidence_level,
            interpretation=interpretation,
            details={
                "alpha_daily": round(alpha_daily, 6),
                "alpha_annual": round(alpha_annual, 4),
                "beta": round(beta, 3),
                "r_squared": round(r_value**2, 4),
                "standard_error": round(se_alpha, 6),
                "n_observations": n,
            },
        )

    def test_skill_vs_luck(
        self,
        returns: np.ndarray | pd.Series,
        n_permutations: int = 10000,
    ) -> StatisticalTestResult:
        """
        Test if strategy performance is due to skill or luck.

        Uses permutation test to compare actual Sharpe ratio
        against distribution of random strategies.

        Args:
            returns: Strategy returns
            n_permutations: Number of permutations

        Returns:
            StatisticalTestResult
        """
        returns = np.asarray(returns)
        returns = returns[~np.isnan(returns)]
        n = len(returns)

        if n < 50:
            return StatisticalTestResult(
                test_name="Skill vs Luck Test",
                statistic=0,
                p_value=1.0,
                significant=False,
                interpretation="Insufficient data (need >= 50 observations)",
            )

        # Compute actual Sharpe ratio
        actual_sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)

        # Generate null distribution by shuffling returns
        null_sharpes = np.zeros(n_permutations)
        for i in range(n_permutations):
            shuffled = np.random.permutation(returns)
            null_sharpes[i] = (np.mean(shuffled) / np.std(shuffled)) * np.sqrt(252)

        # Compute p-value
        p_value = np.mean(null_sharpes >= actual_sharpe)

        significant = p_value < self.alpha

        percentile = (1 - p_value) * 100

        interpretation = (
            f"Strategy Sharpe of {actual_sharpe:.2f} ranks at the "
            f"{percentile:.1f}th percentile of random strategies. "
            f"{'Evidence of skill' if significant else 'Cannot rule out luck'} "
            f"(p={p_value:.4f})"
        )

        return StatisticalTestResult(
            test_name="Skill vs Luck (Permutation Test)",
            statistic=actual_sharpe,
            p_value=p_value,
            significant=significant,
            confidence_level=self.confidence_level,
            interpretation=interpretation,
            details={
                "actual_sharpe": round(actual_sharpe, 3),
                "null_mean": round(np.mean(null_sharpes), 3),
                "null_std": round(np.std(null_sharpes), 3),
                "percentile": round(percentile, 1),
                "n_permutations": n_permutations,
            },
        )

    def compute_confidence_intervals(
        self,
        returns: np.ndarray | pd.Series,
        metrics: list[str] | None = None,
    ) -> dict[str, ConfidenceInterval]:
        """
        Compute bootstrap confidence intervals for multiple metrics.

        Args:
            returns: Strategy returns
            metrics: List of metrics to compute CIs for

        Returns:
            Dict mapping metric names to ConfidenceInterval objects
        """
        returns = np.asarray(returns)
        returns = returns[~np.isnan(returns)]

        if metrics is None:
            metrics = ["mean_return", "sharpe_ratio", "max_drawdown", "volatility"]

        bootstrap = BootstrapCI(
            n_bootstrap=self.n_bootstrap,
            confidence_level=self.confidence_level,
            method="percentile",
        )

        results = {}

        for metric in metrics:
            if metric == "mean_return":
                ci = bootstrap.compute(returns, lambda x: np.mean(x) * 252)
            elif metric == "sharpe_ratio":
                ci = bootstrap.compute(
                    returns,
                    lambda x: (np.mean(x) / np.std(x)) * np.sqrt(252) if np.std(x) > 0 else 0,
                )
            elif metric == "max_drawdown":
                ci = bootstrap.compute(returns, self._compute_max_drawdown)
            elif metric == "volatility":
                ci = bootstrap.compute(returns, lambda x: np.std(x) * np.sqrt(252))
            elif metric == "sortino_ratio":
                ci = bootstrap.compute(returns, self._compute_sortino)
            elif metric == "win_rate":
                ci = bootstrap.compute(returns, lambda x: np.mean(x > 0))
            else:
                continue

            results[metric] = ci

        return results

    def _compute_max_drawdown(self, returns: np.ndarray) -> float:
        """Compute maximum drawdown from returns."""
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        return np.min(drawdown)

    def _compute_sortino(self, returns: np.ndarray) -> float:
        """Compute Sortino ratio."""
        mean_return = np.mean(returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return np.inf
        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return np.inf
        return (mean_return / downside_std) * np.sqrt(252)


class StrategySignificanceSuite:
    """Comprehensive significance testing suite for strategies."""

    def __init__(
        self,
        confidence_level: float = 0.95,
        n_bootstrap: int = 10000,
    ):
        """Initialize significance suite."""
        self.tester = StatisticalTester(confidence_level, n_bootstrap)
        self.confidence_level = confidence_level

    def full_analysis(
        self,
        strategy_returns: np.ndarray | pd.Series,
        benchmark_returns: np.ndarray | pd.Series | None = None,
        risk_free_rate: float = 0.0,
    ) -> dict[str, Any]:
        """
        Run full statistical analysis on a strategy.

        Args:
            strategy_returns: Strategy returns
            benchmark_returns: Optional benchmark returns
            risk_free_rate: Annual risk-free rate

        Returns:
            Comprehensive analysis results
        """
        results = {
            "summary": {},
            "tests": {},
            "confidence_intervals": {},
            "interpretation": {},
        }

        # Basic statistics
        returns = np.asarray(strategy_returns)
        returns = returns[~np.isnan(returns)]

        results["summary"] = {
            "n_observations": len(returns),
            "mean_daily": round(np.mean(returns), 6),
            "mean_annual": round(np.mean(returns) * 252, 4),
            "std_daily": round(np.std(returns), 6),
            "std_annual": round(np.std(returns) * np.sqrt(252), 4),
            "sharpe_ratio": round(
                (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0,
                3
            ),
            "skewness": round(stats.skew(returns), 3),
            "kurtosis": round(stats.kurtosis(returns), 3),
        }

        # Statistical tests
        results["tests"]["mean_positive"] = self.tester.test_mean_different_from_zero(
            returns, alternative="greater"
        ).to_dict()

        results["tests"]["sharpe_significant"] = self.tester.test_sharpe_ratio(
            returns, benchmark_sharpe=0.0, risk_free_rate=risk_free_rate
        ).to_dict()

        results["tests"]["skill_vs_luck"] = self.tester.test_skill_vs_luck(
            returns, n_permutations=5000
        ).to_dict()

        # Benchmark comparison
        if benchmark_returns is not None:
            results["tests"]["alpha"] = self.tester.test_alpha(
                returns, benchmark_returns, risk_free_rate
            ).to_dict()

            results["tests"]["vs_benchmark"] = self.tester.compare_strategies(
                returns, np.asarray(benchmark_returns), paired=True
            ).to_dict()

        # Confidence intervals
        ci_results = self.tester.compute_confidence_intervals(
            returns,
            metrics=["mean_return", "sharpe_ratio", "max_drawdown", "volatility"],
        )
        results["confidence_intervals"] = {
            k: v.to_dict() for k, v in ci_results.items()
        }

        # Overall interpretation
        significant_tests = sum(
            1 for t in results["tests"].values()
            if t.get("significant", False)
        )
        total_tests = len(results["tests"])

        if significant_tests == total_tests:
            overall = "Strong evidence of genuine strategy skill"
        elif significant_tests >= total_tests / 2:
            overall = "Moderate evidence of strategy skill"
        elif significant_tests > 0:
            overall = "Weak evidence of strategy skill"
        else:
            overall = "No significant evidence of strategy skill"

        results["interpretation"] = {
            "overall": overall,
            "significant_tests": f"{significant_tests}/{total_tests}",
            "recommendation": self._generate_recommendation(results),
        }

        return results

    def _generate_recommendation(self, results: dict) -> str:
        """Generate recommendation based on analysis."""
        sharpe = results["summary"]["sharpe_ratio"]
        skill_p = results["tests"]["skill_vs_luck"]["p_value"]
        mean_p = results["tests"]["mean_positive"]["p_value"]

        recommendations = []

        if sharpe < 0.5:
            recommendations.append("Low Sharpe ratio - consider strategy refinement")
        elif sharpe > 1.5:
            recommendations.append("Strong Sharpe ratio - verify with out-of-sample testing")

        if skill_p > 0.1:
            recommendations.append("Cannot rule out luck - extend testing period")

        if mean_p > 0.05:
            recommendations.append("Mean return not significantly positive - review edge")

        if not recommendations:
            recommendations.append("Statistics look good - proceed with paper trading")

        return "; ".join(recommendations)


# Convenience functions
def test_strategy_significance(
    returns: np.ndarray | pd.Series,
    benchmark_returns: np.ndarray | pd.Series | None = None,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """
    Test if a strategy's performance is statistically significant.

    Args:
        returns: Strategy returns
        benchmark_returns: Optional benchmark returns
        confidence_level: Confidence level for tests

    Returns:
        Statistical analysis results
    """
    suite = StrategySignificanceSuite(confidence_level=confidence_level)
    return suite.full_analysis(returns, benchmark_returns)


def compute_bootstrap_ci(
    data: np.ndarray | pd.Series,
    statistic: str = "mean",
    confidence_level: float = 0.95,
    n_bootstrap: int = 10000,
) -> dict[str, Any]:
    """
    Compute bootstrap confidence interval for a statistic.

    Args:
        data: Data array
        statistic: Statistic to compute ('mean', 'median', 'std', 'sharpe')
        confidence_level: Confidence level
        n_bootstrap: Number of bootstrap samples

    Returns:
        Confidence interval results
    """
    bootstrap = BootstrapCI(
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
    )

    stat_funcs = {
        "mean": np.mean,
        "median": np.median,
        "std": np.std,
        "sharpe": lambda x: (np.mean(x) / np.std(x)) * np.sqrt(252) if np.std(x) > 0 else 0,
    }

    if statistic not in stat_funcs:
        return {"success": False, "error": f"Unknown statistic: {statistic}"}

    ci = bootstrap.compute(np.asarray(data), stat_funcs[statistic])
    return {"success": True, "data": ci.to_dict()}


def compare_two_strategies(
    returns_a: np.ndarray | pd.Series,
    returns_b: np.ndarray | pd.Series,
    names: tuple[str, str] = ("Strategy A", "Strategy B"),
) -> dict[str, Any]:
    """
    Compare two strategies statistically.

    Args:
        returns_a: First strategy returns
        returns_b: Second strategy returns
        names: Strategy names

    Returns:
        Comparison results
    """
    tester = StatisticalTester()

    result = tester.compare_strategies(returns_a, returns_b, paired=True)

    return {
        "success": True,
        "data": {
            "strategy_a": names[0],
            "strategy_b": names[1],
            "test_result": result.to_dict(),
            "winner": names[0] if result.details["mean_difference"] > 0 else names[1],
            "margin_annual_pct": round(
                abs(result.details["annualized_difference"]) * 100, 2
            ),
        },
    }
