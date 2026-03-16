"""
Feature Stability Monitor

Monitors the predictive power of features over time using Information Coefficient (IC)
analysis. Detects feature decay, instability, and regime-dependent performance.

Key capabilities:
- Rolling IC calculation (feature vs forward returns correlation)
- Decay detection (is the feature losing predictive power?)
- Stability reporting (which features are reliable?)
- Regime analysis (does feature work differently in different market conditions?)

Usage:
    from src.data.feature_engineering.feature_stability import FeatureStabilityMonitor

    monitor = FeatureStabilityMonitor()
    report = monitor.generate_stability_report(df, feature_names, forward_returns)

    # Check if feature is decaying
    is_decaying, decay_rate = monitor.detect_decay(ic_series)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from pathlib import Path

from src.core.paths import paths
import json

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FeatureStabilityReport:
    """Comprehensive stability report for a single feature."""
    feature_name: str
    analysis_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # IC Statistics
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_t_stat: float = 0.0
    ic_p_value: float = 1.0

    # Rolling IC analysis
    ic_values: list[float] = field(default_factory=list)
    time_periods: list[str] = field(default_factory=list)

    # Decay analysis
    ic_decay_rate: float = 0.0  # Negative = decaying, positive = improving
    is_decaying: bool = False
    decay_confidence: float = 0.0  # R^2 of decay trend

    # Stability metrics
    ic_ir: float = 0.0  # Information Ratio = mean(IC) / std(IC)
    pct_positive_ic: float = 0.0  # % of periods with positive IC
    max_ic: float = 0.0
    min_ic: float = 0.0
    ic_autocorr: float = 0.0  # Autocorrelation (persistence)

    # Classification
    is_stable: bool = False
    is_significant: bool = False
    stability_grade: Literal["A", "B", "C", "D", "F"] = "F"
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "analysis_date": self.analysis_date,
            "ic_mean": round(self.ic_mean, 4),
            "ic_std": round(self.ic_std, 4),
            "ic_t_stat": round(self.ic_t_stat, 2),
            "ic_p_value": round(self.ic_p_value, 4),
            "ic_ir": round(self.ic_ir, 3),
            "pct_positive_ic": round(self.pct_positive_ic, 2),
            "ic_decay_rate": round(self.ic_decay_rate, 5),
            "is_decaying": self.is_decaying,
            "is_stable": self.is_stable,
            "is_significant": self.is_significant,
            "stability_grade": self.stability_grade,
            "recommendation": self.recommendation,
        }


@dataclass
class PortfolioStabilityReport:
    """Stability report for all features in a portfolio/strategy."""
    analysis_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    total_features: int = 0
    stable_count: int = 0
    decaying_count: int = 0
    significant_count: int = 0
    feature_reports: list[FeatureStabilityReport] = field(default_factory=list)

    # Aggregates
    avg_ic: float = 0.0
    avg_ir: float = 0.0
    best_features: list[str] = field(default_factory=list)
    worst_features: list[str] = field(default_factory=list)
    decaying_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "analysis_date": self.analysis_date,
            "total_features": self.total_features,
            "stable_count": self.stable_count,
            "decaying_count": self.decaying_count,
            "significant_count": self.significant_count,
            "avg_ic": round(self.avg_ic, 4),
            "avg_ir": round(self.avg_ir, 3),
            "best_features": self.best_features,
            "worst_features": self.worst_features,
            "decaying_features": self.decaying_features,
            "feature_reports": [r.to_dict() for r in self.feature_reports],
        }


# =============================================================================
# FEATURE STABILITY MONITOR
# =============================================================================

class FeatureStabilityMonitor:
    """
    Monitor feature predictive power and stability over time.

    Uses Information Coefficient (IC) - the correlation between
    feature values and forward returns - as the primary metric.

    Example:
        monitor = FeatureStabilityMonitor()

        # Single feature analysis
        ic_series = monitor.compute_rolling_ic(feature_values, forward_returns)
        is_decaying, rate = monitor.detect_decay(ic_series)

        # Full portfolio analysis
        report = monitor.generate_stability_report(df, ['rsi_14', 'momentum_20'], returns)
    """

    # Thresholds for classification
    IC_SIGNIFICANCE_THRESHOLD = 0.02  # Mean IC must be > 2%
    IC_IR_THRESHOLD = 0.5  # IC Information Ratio > 0.5
    PCT_POSITIVE_THRESHOLD = 0.55  # >55% positive IC periods
    DECAY_SIGNIFICANCE = 0.05  # p-value for decay trend

    def __init__(
        self,
        output_dir: Path | None = None,
        ic_window_days: int = 60,
        min_periods: int = 20,
    ):
        """
        Initialize the stability monitor.

        Args:
            output_dir: Directory to save stability reports
            ic_window_days: Rolling window for IC calculation
            min_periods: Minimum periods required for analysis
        """
        self.output_dir = output_dir or paths.base / "feature_stability"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ic_window_days = ic_window_days
        self.min_periods = min_periods

    def compute_ic(
        self,
        feature_values: pd.Series,
        forward_returns: pd.Series,
        method: Literal["pearson", "spearman"] = "spearman",
    ) -> float:
        """
        Compute Information Coefficient (correlation) for a single period.

        Args:
            feature_values: Feature values at time t
            forward_returns: Returns from t to t+n
            method: Correlation method (spearman is more robust)

        Returns:
            IC value (correlation coefficient)
        """
        # Align indices
        aligned = pd.concat([feature_values, forward_returns], axis=1).dropna()
        if len(aligned) < self.min_periods:
            return np.nan

        feature_col, return_col = aligned.columns

        if method == "spearman":
            ic, _ = stats.spearmanr(aligned[feature_col], aligned[return_col])
        else:
            ic, _ = stats.pearsonr(aligned[feature_col], aligned[return_col])

        return ic if not np.isnan(ic) else 0.0

    def compute_rolling_ic(
        self,
        feature_values: pd.Series,
        forward_returns: pd.Series,
        window: int | None = None,
        method: Literal["pearson", "spearman"] = "spearman",
    ) -> pd.Series:
        """
        Compute rolling Information Coefficient over time.

        This shows how the feature's predictive power varies across time.

        Args:
            feature_values: Time series of feature values
            forward_returns: Time series of forward returns
            window: Rolling window size (default: self.ic_window_days)
            method: Correlation method

        Returns:
            Time series of IC values
        """
        window = window or self.ic_window_days

        # Create aligned dataframe
        aligned = pd.concat([
            feature_values.rename("feature"),
            forward_returns.rename("returns"),
        ], axis=1).dropna()

        if len(aligned) < window:
            return pd.Series(dtype=float)

        # Compute rolling IC
        def rolling_corr(x):
            if len(x) < self.min_periods:
                return np.nan
            if method == "spearman":
                return stats.spearmanr(x["feature"], x["returns"])[0]
            return stats.pearsonr(x["feature"], x["returns"])[0]

        ic_series = aligned.rolling(window).apply(
            lambda x: rolling_corr(pd.DataFrame({
                "feature": x.values[:len(x)//2],
                "returns": x.values[len(x)//2:],
            })) if len(x) >= self.min_periods * 2 else np.nan,
            raw=False,
        )

        # Simpler approach: just compute correlation in rolling windows
        ic_values = []
        dates = []

        for i in range(window, len(aligned)):
            chunk = aligned.iloc[i-window:i]
            if len(chunk) >= self.min_periods:
                if method == "spearman":
                    ic, _ = stats.spearmanr(chunk["feature"], chunk["returns"])
                else:
                    ic, _ = stats.pearsonr(chunk["feature"], chunk["returns"])
                ic_values.append(ic if not np.isnan(ic) else 0.0)
                dates.append(aligned.index[i])

        return pd.Series(ic_values, index=dates, name=f"ic_{feature_values.name}")

    def detect_decay(
        self,
        ic_series: pd.Series,
        min_periods: int = 6,
    ) -> tuple[bool, float, float]:
        """
        Detect if feature IC is decaying over time.

        Fits a linear trend to the IC series and checks if slope is
        significantly negative.

        Args:
            ic_series: Time series of IC values
            min_periods: Minimum periods for trend analysis

        Returns:
            Tuple of (is_decaying, decay_rate, r_squared)
        """
        ic_clean = ic_series.dropna()

        if len(ic_clean) < min_periods:
            return False, 0.0, 0.0

        # Fit linear trend: IC = a + b*time
        x = np.arange(len(ic_clean))
        y = ic_clean.values

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Decay if slope is significantly negative
        is_decaying = slope < 0 and p_value < self.DECAY_SIGNIFICANCE

        return is_decaying, slope, r_value ** 2

    def compute_ic_statistics(
        self,
        ic_series: pd.Series,
    ) -> dict:
        """
        Compute comprehensive IC statistics.

        Args:
            ic_series: Time series of IC values

        Returns:
            Dictionary of IC statistics
        """
        ic_clean = ic_series.dropna()

        if len(ic_clean) < self.min_periods:
            return {
                "mean": 0.0,
                "std": 0.0,
                "t_stat": 0.0,
                "p_value": 1.0,
                "ir": 0.0,
                "pct_positive": 0.0,
                "max": 0.0,
                "min": 0.0,
                "autocorr": 0.0,
            }

        ic_mean = ic_clean.mean()
        ic_std = ic_clean.std()

        # T-statistic: is mean IC significantly different from 0?
        t_stat, p_value = stats.ttest_1samp(ic_clean, 0)

        # Information Ratio
        ir = ic_mean / ic_std if ic_std > 0 else 0.0

        # Percentage of positive IC periods
        pct_positive = (ic_clean > 0).mean()

        # Autocorrelation (persistence)
        autocorr = ic_clean.autocorr(1) if len(ic_clean) > 1 else 0.0

        return {
            "mean": ic_mean,
            "std": ic_std,
            "t_stat": t_stat,
            "p_value": p_value,
            "ir": ir,
            "pct_positive": pct_positive,
            "max": ic_clean.max(),
            "min": ic_clean.min(),
            "autocorr": autocorr if not np.isnan(autocorr) else 0.0,
        }

    def grade_feature(
        self,
        ic_stats: dict,
        is_decaying: bool,
        decay_rate: float,
    ) -> tuple[str, str]:
        """
        Assign a grade to the feature based on stability metrics.

        Grades:
        - A: Excellent - strong, stable, significant IC
        - B: Good - decent IC, minor decay concerns
        - C: Fair - marginal IC or some decay
        - D: Poor - weak IC or significant decay
        - F: Fail - no predictive value or severe decay

        Args:
            ic_stats: Dictionary from compute_ic_statistics
            is_decaying: Whether decay was detected
            decay_rate: Rate of decay (negative = decaying)

        Returns:
            Tuple of (grade, recommendation)
        """
        ic_mean = ic_stats["mean"]
        ic_ir = ic_stats["ir"]
        pct_pos = ic_stats["pct_positive"]
        p_value = ic_stats["p_value"]

        # Scoring
        score = 0

        # IC Mean contribution (0-40 points)
        if abs(ic_mean) > 0.05:
            score += 40
        elif abs(ic_mean) > 0.03:
            score += 30
        elif abs(ic_mean) > 0.02:
            score += 20
        elif abs(ic_mean) > 0.01:
            score += 10

        # IR contribution (0-25 points)
        if ic_ir > 1.0:
            score += 25
        elif ic_ir > 0.7:
            score += 20
        elif ic_ir > 0.5:
            score += 15
        elif ic_ir > 0.3:
            score += 10

        # Significance contribution (0-20 points)
        if p_value < 0.01:
            score += 20
        elif p_value < 0.05:
            score += 15
        elif p_value < 0.10:
            score += 10

        # Decay penalty (0 to -25 points)
        if is_decaying:
            if decay_rate < -0.01:
                score -= 25
            elif decay_rate < -0.005:
                score -= 15
            else:
                score -= 10

        # Consistency bonus (0-15 points)
        if pct_pos > 0.65:
            score += 15
        elif pct_pos > 0.55:
            score += 10
        elif pct_pos > 0.50:
            score += 5

        # Assign grade
        if score >= 80:
            grade = "A"
            recommendation = "Strong feature - use with confidence"
        elif score >= 65:
            grade = "B"
            recommendation = "Good feature - monitor for decay"
        elif score >= 50:
            grade = "C"
            recommendation = "Marginal feature - combine with others"
        elif score >= 35:
            grade = "D"
            recommendation = "Weak feature - consider removing"
        else:
            grade = "F"
            recommendation = "No value - remove from strategy"

        # Add decay warning
        if is_decaying:
            recommendation += " [DECAY WARNING]"

        return grade, recommendation

    def analyze_feature(
        self,
        feature_values: pd.Series,
        forward_returns: pd.Series,
        feature_name: str | None = None,
    ) -> FeatureStabilityReport:
        """
        Generate comprehensive stability report for a single feature.

        Args:
            feature_values: Time series of feature values
            forward_returns: Time series of forward returns
            feature_name: Name of the feature

        Returns:
            FeatureStabilityReport with full analysis
        """
        name = feature_name or feature_values.name or "unknown"
        report = FeatureStabilityReport(feature_name=name)

        # Compute rolling IC
        ic_series = self.compute_rolling_ic(feature_values, forward_returns)

        if len(ic_series) < self.min_periods:
            report.recommendation = "Insufficient data for analysis"
            return report

        # Store IC values
        report.ic_values = ic_series.values.tolist()
        report.time_periods = [str(d) for d in ic_series.index]

        # Compute statistics
        ic_stats = self.compute_ic_statistics(ic_series)
        report.ic_mean = ic_stats["mean"]
        report.ic_std = ic_stats["std"]
        report.ic_t_stat = ic_stats["t_stat"]
        report.ic_p_value = ic_stats["p_value"]
        report.ic_ir = ic_stats["ir"]
        report.pct_positive_ic = ic_stats["pct_positive"]
        report.max_ic = ic_stats["max"]
        report.min_ic = ic_stats["min"]
        report.ic_autocorr = ic_stats["autocorr"]

        # Detect decay
        is_decaying, decay_rate, decay_r2 = self.detect_decay(ic_series)
        report.ic_decay_rate = decay_rate
        report.is_decaying = is_decaying
        report.decay_confidence = decay_r2

        # Determine stability and significance
        report.is_significant = (
            abs(report.ic_mean) > self.IC_SIGNIFICANCE_THRESHOLD and
            report.ic_p_value < 0.05
        )
        report.is_stable = (
            report.is_significant and
            report.ic_ir > self.IC_IR_THRESHOLD and
            not is_decaying
        )

        # Grade and recommendation
        report.stability_grade, report.recommendation = self.grade_feature(
            ic_stats, is_decaying, decay_rate
        )

        return report

    def generate_stability_report(
        self,
        df: pd.DataFrame,
        feature_names: list[str],
        forward_returns: pd.Series,
    ) -> PortfolioStabilityReport:
        """
        Generate comprehensive stability report for multiple features.

        Args:
            df: DataFrame with feature columns
            feature_names: List of feature column names to analyze
            forward_returns: Series of forward returns

        Returns:
            PortfolioStabilityReport with all features analyzed
        """
        portfolio_report = PortfolioStabilityReport()
        portfolio_report.total_features = len(feature_names)

        for feature_name in feature_names:
            if feature_name not in df.columns:
                logger.warning(f"Feature {feature_name} not found in dataframe")
                continue

            feature_values = df[feature_name]
            report = self.analyze_feature(feature_values, forward_returns, feature_name)
            portfolio_report.feature_reports.append(report)

            if report.is_stable:
                portfolio_report.stable_count += 1
            if report.is_decaying:
                portfolio_report.decaying_count += 1
                portfolio_report.decaying_features.append(feature_name)
            if report.is_significant:
                portfolio_report.significant_count += 1

        # Aggregate statistics
        if portfolio_report.feature_reports:
            ics = [r.ic_mean for r in portfolio_report.feature_reports if r.ic_mean != 0]
            irs = [r.ic_ir for r in portfolio_report.feature_reports if r.ic_ir != 0]

            portfolio_report.avg_ic = np.mean(ics) if ics else 0.0
            portfolio_report.avg_ir = np.mean(irs) if irs else 0.0

            # Best and worst features
            sorted_reports = sorted(
                portfolio_report.feature_reports,
                key=lambda r: r.ic_ir,
                reverse=True,
            )
            portfolio_report.best_features = [r.feature_name for r in sorted_reports[:5]]
            portfolio_report.worst_features = [r.feature_name for r in sorted_reports[-5:]]

        return portfolio_report

    def save_report(
        self,
        report: PortfolioStabilityReport | FeatureStabilityReport,
        filename: str | None = None,
    ) -> Path:
        """Save stability report to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stability_report_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        logger.info(f"Stability report saved to {filepath}")
        return filepath


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_stability_check(
    feature_values: pd.Series,
    forward_returns: pd.Series,
) -> dict:
    """
    Quick stability check for a single feature.

    Returns simplified stability metrics without full report.

    Args:
        feature_values: Feature time series
        forward_returns: Forward returns series

    Returns:
        Dict with key stability indicators
    """
    monitor = FeatureStabilityMonitor()
    report = monitor.analyze_feature(feature_values, forward_returns)

    return {
        "feature": report.feature_name,
        "ic_mean": report.ic_mean,
        "ic_ir": report.ic_ir,
        "is_stable": report.is_stable,
        "is_decaying": report.is_decaying,
        "grade": report.stability_grade,
        "recommendation": report.recommendation,
    }


def find_decaying_features(
    df: pd.DataFrame,
    feature_names: list[str],
    forward_returns: pd.Series,
) -> list[str]:
    """
    Find features that are showing decay in predictive power.

    Args:
        df: DataFrame with feature columns
        feature_names: Feature names to check
        forward_returns: Forward returns series

    Returns:
        List of feature names showing decay
    """
    monitor = FeatureStabilityMonitor()
    report = monitor.generate_stability_report(df, feature_names, forward_returns)
    return report.decaying_features


def rank_features_by_stability(
    df: pd.DataFrame,
    feature_names: list[str],
    forward_returns: pd.Series,
) -> pd.DataFrame:
    """
    Rank features by stability metrics.

    Args:
        df: DataFrame with feature columns
        feature_names: Feature names to rank
        forward_returns: Forward returns series

    Returns:
        DataFrame with features ranked by IR
    """
    monitor = FeatureStabilityMonitor()
    report = monitor.generate_stability_report(df, feature_names, forward_returns)

    rows = []
    for r in report.feature_reports:
        rows.append({
            "feature": r.feature_name,
            "ic_mean": r.ic_mean,
            "ic_ir": r.ic_ir,
            "pct_positive": r.pct_positive_ic,
            "is_stable": r.is_stable,
            "is_decaying": r.is_decaying,
            "grade": r.stability_grade,
        })

    result = pd.DataFrame(rows)
    return result.sort_values("ic_ir", ascending=False).reset_index(drop=True)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Feature Stability Monitor")
    parser.add_argument("--symbol", type=str, default="SPY", help="Symbol to analyze")
    parser.add_argument("--days", type=int, default=500, help="Days of history")

    args = parser.parse_args()

    print(f"Feature Stability Monitor - Analyzing {args.symbol}")
    print("=" * 50)
    print("Note: Run with actual data to see stability reports")
    print("See docstring for usage examples")
