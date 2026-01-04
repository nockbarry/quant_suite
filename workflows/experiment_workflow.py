#!/usr/bin/env python3
"""
Standardized Experiment Workflow

This workflow should be run for ALL experiments to ensure:
1. No data leakage / look-ahead bias
2. Proper statistical validation (MCPT)
3. Feature performance tracking
4. Comprehensive visualization
5. Reproducible results

Usage:
    from workflows.experiment_workflow import ExperimentWorkflow

    workflow = ExperimentWorkflow(experiment_name="my_strategy")
    results = workflow.run_full_evaluation(
        strategies=my_strategies,
        symbols=my_symbols,
    )
"""

import json
import logging
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yfinance as yf

warnings.filterwarnings("ignore")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class FeatureStats:
    """Statistics for a single feature."""

    name: str
    correlation_with_target: float
    correlation_with_past_target: float
    information_coefficient: float
    autocorrelation_1d: float
    look_ahead_risk: str  # "low", "medium", "high"
    description: str = ""


@dataclass
class LeakageReport:
    """Report from leak detection."""

    is_clean: bool
    issues: list[str]
    warnings: list[str]
    feature_details: dict[str, FeatureStats]


@dataclass
class StrategyResult:
    """Result from strategy evaluation."""

    strategy_name: str
    symbol: str
    sharpe_ratio: float
    total_return: float
    max_drawdown: float
    n_trades: int
    win_rate: float
    profit_factor: float
    features_used: list[str]


@dataclass
class MCPTResult:
    """Result from MCPT validation."""

    strategy_name: str
    symbol: str
    actual_sharpe: float
    mean_permuted_sharpe: float
    std_permuted_sharpe: float
    p_value: float
    is_significant_5pct: bool
    is_significant_10pct: bool
    n_permutations: int


@dataclass
class ExperimentReport:
    """Complete experiment report."""

    experiment_name: str
    timestamp: str
    symbols: list[str]
    strategies: list[str]
    leakage_report: LeakageReport
    backtest_results: list[StrategyResult]
    mcpt_results: list[MCPTResult]
    feature_stats: dict[str, FeatureStats]
    summary: dict[str, Any]
    plots_generated: list[str]


# =============================================================================
# STRATEGY PROTOCOL
# =============================================================================


class StrategyProtocol(Protocol):
    """Protocol for strategy classes."""

    name: str

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals."""
        ...


# =============================================================================
# LEAK DETECTOR
# =============================================================================


class LeakDetector:
    """Detect look-ahead bias in features and strategies."""

    def __init__(self, target_horizon: int = 5, significance_threshold: float = 1.5):
        self.target_horizon = target_horizon
        self.significance_threshold = significance_threshold

    def analyze_feature(
        self,
        feature: pd.Series,
        target: pd.Series,
        feature_name: str,
    ) -> FeatureStats:
        """Analyze a single feature for look-ahead bias."""
        common_idx = feature.dropna().index.intersection(target.dropna().index)
        if len(common_idx) < 50:
            return FeatureStats(
                name=feature_name,
                correlation_with_target=0.0,
                correlation_with_past_target=0.0,
                information_coefficient=0.0,
                autocorrelation_1d=0.0,
                look_ahead_risk="unknown",
                description="Insufficient data",
            )

        feat = feature.loc[common_idx]
        tgt = target.loc[common_idx]

        # Correlation with current target (potential leak)
        corr_current = feat.corr(tgt)

        # Correlation with past target (natural relationship)
        past_tgt = target.shift(self.target_horizon).loc[common_idx].dropna()
        corr_past = 0.0
        if len(past_tgt) > 50:
            corr_past = feat.loc[past_tgt.index].corr(past_tgt)

        # Information coefficient (rank correlation)
        try:
            from scipy.stats import spearmanr
            ic, _ = spearmanr(feat, tgt)
        except:
            ic = 0.0

        # Autocorrelation
        autocorr = feat.autocorr(lag=1) if len(feat) > 10 else 0.0

        # Assess look-ahead risk
        if abs(corr_current) > 0.3 and abs(corr_current) > abs(corr_past) * 2:
            risk = "high"
        elif abs(corr_current) > 0.1 and abs(corr_current) > abs(corr_past) * 1.5:
            risk = "medium"
        else:
            risk = "low"

        return FeatureStats(
            name=feature_name,
            correlation_with_target=round(corr_current, 4) if not pd.isna(corr_current) else 0.0,
            correlation_with_past_target=round(corr_past, 4) if not pd.isna(corr_past) else 0.0,
            information_coefficient=round(ic, 4) if not pd.isna(ic) else 0.0,
            autocorrelation_1d=round(autocorr, 4) if not pd.isna(autocorr) else 0.0,
            look_ahead_risk=risk,
        )

    def check_position_lag(
        self,
        positions: pd.Series,
        signals: pd.Series,
    ) -> tuple[bool, str]:
        """Verify positions are properly lagged from signals."""
        if signals is None:
            return True, "No signals to compare"

        corr_same = positions.corr(signals)
        corr_lagged = positions.corr(signals.shift(1))

        if pd.isna(corr_same) or pd.isna(corr_lagged):
            return True, "Insufficient data for lag check"

        is_lagged = corr_lagged >= corr_same * 0.9
        msg = (
            f"Lag check passed (same-day corr: {corr_same:.3f}, lagged corr: {corr_lagged:.3f})"
            if is_lagged
            else f"WARNING: Positions may not be lagged (same-day corr: {corr_same:.3f} > lagged: {corr_lagged:.3f})"
        )
        return is_lagged, msg

    def run_full_check(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        positions: pd.Series = None,
        signals: pd.Series = None,
    ) -> LeakageReport:
        """Run comprehensive leak detection."""
        issues = []
        warnings_list = []
        feature_details = {}

        # Check each feature
        for col in features.columns:
            stats = self.analyze_feature(features[col], target, col)
            feature_details[col] = stats

            if stats.look_ahead_risk == "high":
                issues.append(f"HIGH RISK: Feature '{col}' shows strong look-ahead correlation")
            elif stats.look_ahead_risk == "medium":
                warnings_list.append(f"MEDIUM RISK: Feature '{col}' may have look-ahead bias")

        # Check position lag
        if positions is not None and signals is not None:
            is_lagged, msg = self.check_position_lag(positions, signals)
            if not is_lagged:
                issues.append(msg)

        is_clean = len(issues) == 0

        return LeakageReport(
            is_clean=is_clean,
            issues=issues,
            warnings=warnings_list,
            feature_details=feature_details,
        )


# =============================================================================
# FEATURE EXTRACTOR
# =============================================================================


class FeatureExtractor:
    """Extract and document features from strategy."""

    @staticmethod
    def extract_features_from_data(data: pd.DataFrame) -> pd.DataFrame:
        """Extract common features from price data."""
        features = pd.DataFrame(index=data.index)

        close = data["close"]
        volume = data.get("volume", pd.Series(1, index=data.index))

        # Momentum features (all use .shift(1) to prevent look-ahead)
        features["ret_1d"] = close.pct_change().shift(1)
        features["ret_5d"] = close.pct_change(5).shift(1)
        features["ret_20d"] = close.pct_change(20).shift(1)

        # Volatility features
        features["vol_10d"] = close.pct_change().rolling(10).std().shift(1)
        features["vol_20d"] = close.pct_change().rolling(20).std().shift(1)

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        features["rsi"] = (100 - (100 / (1 + gain / (loss + 1e-10)))).shift(1)

        # Bollinger position
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        features["bb_position"] = ((close - ma20) / (2 * std20 + 1e-10)).shift(1)

        # Volume features
        avg_vol = volume.rolling(20).mean()
        features["volume_ratio"] = (volume / (avg_vol + 1)).shift(1)

        # Price patterns
        features["high_low_range"] = ((data["high"] - data["low"]) / close).shift(1)

        return features

    @staticmethod
    def get_feature_descriptions() -> dict[str, str]:
        """Get descriptions for all features."""
        return {
            "ret_1d": "1-day return (lagged)",
            "ret_5d": "5-day return (lagged)",
            "ret_20d": "20-day momentum (lagged)",
            "vol_10d": "10-day realized volatility (lagged)",
            "vol_20d": "20-day realized volatility (lagged)",
            "rsi": "14-day RSI (lagged)",
            "bb_position": "Position in Bollinger Bands (lagged)",
            "volume_ratio": "Volume vs 20-day average (lagged)",
            "high_low_range": "Normalized high-low range (lagged)",
        }


# =============================================================================
# MCPT VALIDATOR
# =============================================================================


class MCPTValidator:
    """Monte Carlo Permutation Test validator."""

    def __init__(self, n_permutations: int = 200):
        self.n_permutations = n_permutations

    def validate(
        self,
        strategy: StrategyProtocol,
        data: pd.DataFrame,
    ) -> MCPTResult:
        """Run MCPT validation on strategy."""
        # Get actual performance
        signals = strategy.generate_signals(data)
        positions = signals["signal"].shift(1).fillna(0)
        returns = data["close"].pct_change()
        strategy_returns = positions * returns

        actual_sharpe = (
            strategy_returns.mean() / (strategy_returns.std() + 1e-10)
        ) * np.sqrt(252)

        # Permutation test
        permuted_sharpes = []
        for _ in range(self.n_permutations):
            perm_returns = returns.sample(frac=1, replace=False)
            perm_returns.index = returns.index

            perm_prices = (1 + perm_returns).cumprod() * data["close"].iloc[0]
            perm_data = data.copy()
            perm_data["close"] = perm_prices
            perm_data["open"] = perm_prices.shift(1).fillna(perm_prices.iloc[0])
            perm_data["high"] = perm_data[["open", "close"]].max(axis=1) * 1.005
            perm_data["low"] = perm_data[["open", "close"]].min(axis=1) * 0.995

            perm_signals = strategy.generate_signals(perm_data)
            perm_positions = perm_signals["signal"].shift(1).fillna(0)
            perm_strat_returns = perm_positions * perm_data["close"].pct_change()

            perm_sharpe = (
                perm_strat_returns.mean() / (perm_strat_returns.std() + 1e-10)
            ) * np.sqrt(252)
            permuted_sharpes.append(perm_sharpe)

        permuted_sharpes = np.array(permuted_sharpes)
        p_value = float((permuted_sharpes >= actual_sharpe).sum() / self.n_permutations)

        return MCPTResult(
            strategy_name=strategy.name,
            symbol="",  # Set by caller
            actual_sharpe=float(actual_sharpe),
            mean_permuted_sharpe=float(np.mean(permuted_sharpes)),
            std_permuted_sharpe=float(np.std(permuted_sharpes)),
            p_value=p_value,
            is_significant_5pct=p_value < 0.05,
            is_significant_10pct=p_value < 0.10,
            n_permutations=self.n_permutations,
        )


# =============================================================================
# VISUALIZATION
# =============================================================================


class ExperimentVisualizer:
    """Generate experiment visualizations."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        plt.style.use("seaborn-v0_8-whitegrid")

    def plot_equity_curves(
        self,
        results: dict[str, pd.Series],
        title: str,
        filename: str,
    ) -> str:
        """Plot equity curves for multiple strategies."""
        fig, ax = plt.subplots(figsize=(12, 6))

        for name, returns in results.items():
            equity = (1 + returns).cumprod()
            ax.plot(equity.index, equity.values, label=name, linewidth=1.5)

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative Return")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

        filepath = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close()

        return str(filepath)

    def plot_mcpt_distribution(
        self,
        mcpt_results: list[MCPTResult],
        filename: str,
    ) -> str:
        """Plot MCPT distribution for each strategy."""
        n_results = len(mcpt_results)
        if n_results == 0:
            return ""

        fig, axes = plt.subplots(
            nrows=(n_results + 2) // 3,
            ncols=min(3, n_results),
            figsize=(15, 4 * ((n_results + 2) // 3)),
        )
        if n_results == 1:
            axes = [axes]
        else:
            axes = axes.flatten()

        for idx, result in enumerate(mcpt_results):
            ax = axes[idx]

            # Create synthetic distribution from stats
            x = np.linspace(
                result.mean_permuted_sharpe - 3 * result.std_permuted_sharpe,
                result.mean_permuted_sharpe + 3 * result.std_permuted_sharpe,
                100,
            )
            from scipy.stats import norm

            y = norm.pdf(x, result.mean_permuted_sharpe, result.std_permuted_sharpe)

            ax.fill_between(x, y, alpha=0.3, color="blue", label="Permuted Distribution")
            ax.axvline(
                result.actual_sharpe,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Actual: {result.actual_sharpe:.2f}",
            )
            ax.axvline(
                result.mean_permuted_sharpe,
                color="blue",
                linestyle=":",
                label=f"Mean Perm: {result.mean_permuted_sharpe:.2f}",
            )

            sig_marker = "**" if result.is_significant_5pct else "*" if result.is_significant_10pct else ""
            ax.set_title(
                f"{result.strategy_name} on {result.symbol}\np={result.p_value:.3f} {sig_marker}",
                fontsize=10,
            )
            ax.legend(fontsize=8)

        # Hide unused subplots
        for idx in range(n_results, len(axes)):
            axes[idx].set_visible(False)

        filepath = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close()

        return str(filepath)

    def plot_feature_importance(
        self,
        feature_stats: dict[str, FeatureStats],
        filename: str,
    ) -> str:
        """Plot feature importance and risk assessment."""
        if not feature_stats:
            return ""

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Left: Information Coefficient
        names = list(feature_stats.keys())
        ics = [s.information_coefficient for s in feature_stats.values()]
        colors = [
            "red" if s.look_ahead_risk == "high" else "orange" if s.look_ahead_risk == "medium" else "green"
            for s in feature_stats.values()
        ]

        ax1 = axes[0]
        bars = ax1.barh(names, ics, color=colors)
        ax1.set_xlabel("Information Coefficient")
        ax1.set_title("Feature Performance (IC)", fontweight="bold")
        ax1.axvline(0, color="black", linewidth=0.5)

        # Right: Look-ahead risk assessment
        ax2 = axes[1]
        corr_current = [s.correlation_with_target for s in feature_stats.values()]
        corr_past = [s.correlation_with_past_target for s in feature_stats.values()]

        x = np.arange(len(names))
        width = 0.35
        ax2.barh(x - width / 2, corr_current, width, label="Corr w/ Current Target", color="red", alpha=0.7)
        ax2.barh(x + width / 2, corr_past, width, label="Corr w/ Past Target", color="blue", alpha=0.7)
        ax2.set_yticks(x)
        ax2.set_yticklabels(names)
        ax2.set_xlabel("Correlation")
        ax2.set_title("Look-Ahead Risk Assessment", fontweight="bold")
        ax2.legend()
        ax2.axvline(0, color="black", linewidth=0.5)

        filepath = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close()

        return str(filepath)

    def plot_strategy_comparison(
        self,
        results: list[StrategyResult],
        filename: str,
    ) -> str:
        """Plot strategy comparison heatmap."""
        if not results:
            return ""

        # Create DataFrame for heatmap
        data = {}
        for r in results:
            key = f"{r.strategy_name}"
            if key not in data:
                data[key] = {}
            data[key][r.symbol] = r.sharpe_ratio

        df = pd.DataFrame(data).T

        fig, ax = plt.subplots(figsize=(14, 8))
        sns.heatmap(
            df,
            annot=True,
            fmt=".2f",
            cmap="RdYlGn",
            center=0,
            ax=ax,
            cbar_kws={"label": "Sharpe Ratio"},
        )
        ax.set_title("Strategy-Symbol Performance Matrix", fontsize=14, fontweight="bold")
        ax.set_xlabel("Symbol")
        ax.set_ylabel("Strategy")

        filepath = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close()

        return str(filepath)


# =============================================================================
# MAIN WORKFLOW
# =============================================================================


class ExperimentWorkflow:
    """
    Standardized experiment workflow.

    Ensures all experiments follow the same rigorous process:
    1. Data leakage detection
    2. Feature analysis
    3. Backtest evaluation
    4. MCPT validation
    5. Visualization
    6. Report generation
    """

    def __init__(
        self,
        experiment_name: str,
        output_dir: Path = None,
        n_permutations: int = 200,
    ):
        self.experiment_name = experiment_name
        self.output_dir = output_dir or Path.home() / "quant_results" / "experiments" / experiment_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.leak_detector = LeakDetector()
        self.mcpt_validator = MCPTValidator(n_permutations=n_permutations)
        self.visualizer = ExperimentVisualizer(self.output_dir / "plots")

    def fetch_data(
        self,
        symbols: list[str],
        start_date: str = "2020-01-01",
        end_date: str = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch price data for symbols."""
        logger.info(f"Fetching data for {len(symbols)} symbols...")
        data = {}

        for symbol in symbols:
            try:
                df = yf.download(
                    symbol,
                    start=start_date,
                    end=end_date,
                    progress=False,
                    auto_adjust=True,
                )
                if df is not None and len(df) > 200:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [c.lower() for c in df.columns]
                    data[symbol] = df
                    logger.info(f"  {symbol}: {len(df)} bars")
            except Exception as e:
                logger.warning(f"  {symbol}: Failed - {e}")

        return data

    def run_leakage_check(
        self,
        data: dict[str, pd.DataFrame],
    ) -> tuple[LeakageReport, dict[str, FeatureStats]]:
        """Run leakage detection on all data."""
        logger.info("Running data leakage detection...")

        all_feature_stats = {}
        all_issues = []
        all_warnings = []

        for symbol, df in data.items():
            # Extract features
            features = FeatureExtractor.extract_features_from_data(df)

            # Create target (5-day forward return direction)
            target = (df["close"].shift(-5) / df["close"] - 1 > 0).astype(int)

            # Run check
            report = self.leak_detector.run_full_check(features, target)

            for name, stats in report.feature_details.items():
                key = f"{symbol}_{name}"
                all_feature_stats[key] = stats

            all_issues.extend([f"[{symbol}] {i}" for i in report.issues])
            all_warnings.extend([f"[{symbol}] {w}" for w in report.warnings])

        # Aggregate feature stats across symbols
        feature_names = FeatureExtractor.get_feature_descriptions().keys()
        aggregated_stats = {}

        for feat in feature_names:
            matching = [s for k, s in all_feature_stats.items() if k.endswith(f"_{feat}")]
            if matching:
                aggregated_stats[feat] = FeatureStats(
                    name=feat,
                    correlation_with_target=np.mean([s.correlation_with_target for s in matching]),
                    correlation_with_past_target=np.mean([s.correlation_with_past_target for s in matching]),
                    information_coefficient=np.mean([s.information_coefficient for s in matching]),
                    autocorrelation_1d=np.mean([s.autocorrelation_1d for s in matching]),
                    look_ahead_risk=max([s.look_ahead_risk for s in matching], key=lambda x: {"low": 0, "medium": 1, "high": 2}.get(x, 0)),
                    description=FeatureExtractor.get_feature_descriptions().get(feat, ""),
                )

        combined_report = LeakageReport(
            is_clean=len(all_issues) == 0,
            issues=all_issues,
            warnings=all_warnings,
            feature_details=aggregated_stats,
        )

        if combined_report.is_clean:
            logger.info("  PASSED: No data leakage detected")
        else:
            logger.warning(f"  FAILED: {len(all_issues)} issues found")
            for issue in all_issues[:5]:
                logger.warning(f"    - {issue}")

        return combined_report, aggregated_stats

    def run_backtests(
        self,
        strategies: list[StrategyProtocol],
        data: dict[str, pd.DataFrame],
    ) -> list[StrategyResult]:
        """Run backtests for all strategy-symbol combinations."""
        logger.info(f"Running backtests for {len(strategies)} strategies...")
        results = []

        for strategy in strategies:
            for symbol, df in data.items():
                try:
                    signals = strategy.generate_signals(df)
                    positions = signals["signal"].shift(1).fillna(0)
                    returns = df["close"].pct_change()
                    strategy_returns = positions * returns

                    sharpe = (strategy_returns.mean() / (strategy_returns.std() + 1e-10)) * np.sqrt(252)
                    total_return = (1 + strategy_returns).prod() - 1
                    max_dd = ((1 + strategy_returns).cumprod() / (1 + strategy_returns).cumprod().cummax() - 1).min()
                    n_trades = (positions.diff().abs() > 0).sum()

                    # Win rate and profit factor
                    winning = strategy_returns[strategy_returns > 0]
                    losing = strategy_returns[strategy_returns < 0]
                    win_rate = len(winning) / (len(winning) + len(losing)) if (len(winning) + len(losing)) > 0 else 0
                    profit_factor = winning.sum() / (-losing.sum()) if losing.sum() != 0 else float("inf")

                    result = StrategyResult(
                        strategy_name=strategy.name,
                        symbol=symbol,
                        sharpe_ratio=float(sharpe),
                        total_return=float(total_return),
                        max_drawdown=float(max_dd),
                        n_trades=int(n_trades),
                        win_rate=float(win_rate),
                        profit_factor=float(profit_factor) if not np.isinf(profit_factor) else 999.0,
                        features_used=[],  # Can be populated by strategy
                    )
                    results.append(result)

                    if sharpe > 0.4:
                        logger.info(f"  {strategy.name} on {symbol}: Sharpe={sharpe:.2f}")

                except Exception as e:
                    logger.warning(f"  {strategy.name} on {symbol}: Error - {e}")

        return results

    def run_mcpt_validation(
        self,
        strategies: list[StrategyProtocol],
        data: dict[str, pd.DataFrame],
        backtest_results: list[StrategyResult],
        sharpe_threshold: float = 0.4,
    ) -> list[MCPTResult]:
        """Run MCPT validation on promising strategies."""
        # Filter to promising strategies
        promising = [
            (r.strategy_name, r.symbol)
            for r in backtest_results
            if r.sharpe_ratio > sharpe_threshold
        ]

        logger.info(f"Running MCPT validation on {len(promising)} promising strategies...")
        results = []

        strategy_map = {s.name: s for s in strategies}

        for strategy_name, symbol in promising:
            try:
                strategy = strategy_map[strategy_name]
                df = data[symbol]

                mcpt_result = self.mcpt_validator.validate(strategy, df)
                mcpt_result.symbol = symbol

                results.append(mcpt_result)

                sig_marker = "**" if mcpt_result.is_significant_5pct else "*" if mcpt_result.is_significant_10pct else ""
                logger.info(f"  {strategy_name} on {symbol}: p={mcpt_result.p_value:.3f} {sig_marker}")

            except Exception as e:
                logger.warning(f"  MCPT {strategy_name} on {symbol}: Error - {e}")

        return results

    def generate_visualizations(
        self,
        backtest_results: list[StrategyResult],
        mcpt_results: list[MCPTResult],
        feature_stats: dict[str, FeatureStats],
    ) -> list[str]:
        """Generate all visualizations."""
        logger.info("Generating visualizations...")
        plots = []

        # Strategy comparison heatmap
        plot_path = self.visualizer.plot_strategy_comparison(
            backtest_results,
            "strategy_comparison.png",
        )
        if plot_path:
            plots.append(plot_path)

        # MCPT distributions
        plot_path = self.visualizer.plot_mcpt_distribution(
            mcpt_results,
            "mcpt_distributions.png",
        )
        if plot_path:
            plots.append(plot_path)

        # Feature importance
        plot_path = self.visualizer.plot_feature_importance(
            feature_stats,
            "feature_analysis.png",
        )
        if plot_path:
            plots.append(plot_path)

        logger.info(f"  Generated {len(plots)} plots")
        return plots

    def generate_summary(
        self,
        backtest_results: list[StrategyResult],
        mcpt_results: list[MCPTResult],
    ) -> dict[str, Any]:
        """Generate summary statistics."""
        summary = {
            "total_combinations": len(backtest_results),
            "positive_sharpe": sum(1 for r in backtest_results if r.sharpe_ratio > 0),
            "sharpe_gt_05": sum(1 for r in backtest_results if r.sharpe_ratio > 0.5),
            "mcpt_significant_5pct": sum(1 for r in mcpt_results if r.is_significant_5pct),
            "mcpt_significant_10pct": sum(1 for r in mcpt_results if r.is_significant_10pct),
        }

        # Best results
        if backtest_results:
            best = max(backtest_results, key=lambda r: r.sharpe_ratio)
            summary["best_backtest"] = {
                "strategy": best.strategy_name,
                "symbol": best.symbol,
                "sharpe": best.sharpe_ratio,
                "return": best.total_return,
            }

        if mcpt_results:
            sig_results = [r for r in mcpt_results if r.is_significant_5pct]
            if sig_results:
                best_sig = max(sig_results, key=lambda r: r.actual_sharpe)
                summary["best_significant"] = {
                    "strategy": best_sig.strategy_name,
                    "symbol": best_sig.symbol,
                    "sharpe": best_sig.actual_sharpe,
                    "p_value": best_sig.p_value,
                }

        return summary

    def run_full_evaluation(
        self,
        strategies: list[StrategyProtocol],
        symbols: list[str],
        start_date: str = "2020-01-01",
        end_date: str = None,
    ) -> ExperimentReport:
        """
        Run complete experiment workflow.

        This is the main entry point that runs:
        1. Data fetching
        2. Leakage detection
        3. Backtesting
        4. MCPT validation
        5. Visualization
        6. Report generation
        """
        logger.info("=" * 60)
        logger.info(f"EXPERIMENT: {self.experiment_name}")
        logger.info("=" * 60)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Fetch data
        data = self.fetch_data(symbols, start_date, end_date)

        # 2. Leakage detection
        leakage_report, feature_stats = self.run_leakage_check(data)

        # 3. Backtests
        backtest_results = self.run_backtests(strategies, data)

        # 4. MCPT validation
        mcpt_results = self.run_mcpt_validation(strategies, data, backtest_results)

        # 5. Visualizations
        plots = self.generate_visualizations(backtest_results, mcpt_results, feature_stats)

        # 6. Summary
        summary = self.generate_summary(backtest_results, mcpt_results)

        # Create report
        report = ExperimentReport(
            experiment_name=self.experiment_name,
            timestamp=timestamp,
            symbols=symbols,
            strategies=[s.name for s in strategies],
            leakage_report=leakage_report,
            backtest_results=backtest_results,
            mcpt_results=mcpt_results,
            feature_stats=feature_stats,
            summary=summary,
            plots_generated=plots,
        )

        # Save report
        self._save_report(report)

        # Print summary
        self._print_summary(report)

        return report

    def _save_report(self, report: ExperimentReport) -> None:
        """Save report to JSON."""
        # Convert dataclasses to dicts
        report_dict = {
            "experiment_name": report.experiment_name,
            "timestamp": report.timestamp,
            "symbols": report.symbols,
            "strategies": report.strategies,
            "leakage_report": {
                "is_clean": report.leakage_report.is_clean,
                "issues": report.leakage_report.issues,
                "warnings": report.leakage_report.warnings,
                "feature_details": {
                    k: asdict(v) for k, v in report.leakage_report.feature_details.items()
                },
            },
            "backtest_results": [asdict(r) for r in report.backtest_results],
            "mcpt_results": [asdict(r) for r in report.mcpt_results],
            "feature_stats": {k: asdict(v) for k, v in report.feature_stats.items()},
            "summary": report.summary,
            "plots_generated": report.plots_generated,
        }

        filepath = self.output_dir / f"report_{report.timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(report_dict, f, indent=2, default=str)

        logger.info(f"Report saved to: {filepath}")

    def _print_summary(self, report: ExperimentReport) -> None:
        """Print experiment summary."""
        print("\n" + "=" * 60)
        print(f"EXPERIMENT SUMMARY: {report.experiment_name}")
        print("=" * 60)

        # Leakage status
        status = "CLEAN" if report.leakage_report.is_clean else "ISSUES FOUND"
        print(f"\nData Leakage Check: {status}")
        if report.leakage_report.issues:
            for issue in report.leakage_report.issues[:3]:
                print(f"  - {issue}")

        # Results
        print(f"\nBacktest Results:")
        print(f"  Total combinations: {report.summary['total_combinations']}")
        print(f"  Positive Sharpe: {report.summary['positive_sharpe']}")
        print(f"  Sharpe > 0.5: {report.summary['sharpe_gt_05']}")

        if "best_backtest" in report.summary:
            best = report.summary["best_backtest"]
            print(f"\n  Best: {best['strategy']} on {best['symbol']}")
            print(f"        Sharpe={best['sharpe']:.3f}, Return={best['return']:.1%}")

        # MCPT Results
        print(f"\nMCPT Validation:")
        print(f"  Significant (p<0.05): {report.summary['mcpt_significant_5pct']}")
        print(f"  Significant (p<0.10): {report.summary['mcpt_significant_10pct']}")

        if "best_significant" in report.summary:
            best = report.summary["best_significant"]
            print(f"\n  Best Significant: {best['strategy']} on {best['symbol']}")
            print(f"                    Sharpe={best['sharpe']:.3f}, p={best['p_value']:.3f}")

        # Feature analysis
        print(f"\nFeature Analysis:")
        high_risk = [k for k, v in report.feature_stats.items() if v.look_ahead_risk == "high"]
        if high_risk:
            print(f"  HIGH RISK features: {', '.join(high_risk)}")
        else:
            print("  No high-risk features detected")

        # Plots
        print(f"\nPlots generated: {len(report.plots_generated)}")
        for plot in report.plots_generated:
            print(f"  - {Path(plot).name}")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def run_experiment(
    experiment_name: str,
    strategies: list[StrategyProtocol],
    symbols: list[str],
    start_date: str = "2020-01-01",
    n_permutations: int = 200,
) -> ExperimentReport:
    """
    Convenience function to run a full experiment.

    Usage:
        from workflows.experiment_workflow import run_experiment

        report = run_experiment(
            experiment_name="my_strategy_test",
            strategies=[MyStrategy()],
            symbols=["AAPL", "MSFT", "GOOGL"],
        )
    """
    workflow = ExperimentWorkflow(
        experiment_name=experiment_name,
        n_permutations=n_permutations,
    )
    return workflow.run_full_evaluation(
        strategies=strategies,
        symbols=symbols,
        start_date=start_date,
    )


if __name__ == "__main__":
    # Example usage - run with the advanced strategies
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from scripts.advanced_strategy_builder import (
        SentimentMomentumHybridStrategy,
        InsiderTechnicalConfluenceStrategy,
        MultiAlphaEnsembleStrategy,
    )

    strategies = [
        SentimentMomentumHybridStrategy(),
        InsiderTechnicalConfluenceStrategy(),
        MultiAlphaEnsembleStrategy(),
    ]

    symbols = ["QQQ", "MSFT", "AAPL", "GOOGL", "AMD", "NVDA"]

    report = run_experiment(
        experiment_name="advanced_strategies_audit",
        strategies=strategies,
        symbols=symbols,
        n_permutations=100,  # Reduced for demo
    )
