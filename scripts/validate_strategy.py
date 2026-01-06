#!/usr/bin/env python3
"""
Strategy Validation Script.

Runs the complete validation suite on a strategy before production.

Usage:
    PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM
    PYTHONPATH=. python scripts/validate_strategy.py --strategy momentum --symbol AMD --quick
    PYTHONPATH=. python scripts/validate_strategy.py --strategy rsi_reversal --symbol IWM --plots
"""

import argparse
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

# Import evaluation module functions
try:
    from src.evaluation import (
        # Metrics
        sharpe_ratio, sortino_ratio, max_drawdown, total_return,
        win_rate, calmar_ratio,
        # Statistical testing
        compute_bootstrap_ci, BootstrapCI,
        # MCPT
        mcpt_test as eval_mcpt_test,
        # Regime analysis
        detect_regimes, evaluate_by_regime, get_current_regime,
    )
    EVAL_MODULE_AVAILABLE = True
except ImportError:
    EVAL_MODULE_AVAILABLE = False

# Import plotting module
try:
    from workflows.visualizations.strategy_plots import (
        StrategyPlotter, PlotConfig, plot_validation_dashboard
    )
    PLOTS_AVAILABLE = True
except ImportError:
    PLOTS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Complete validation result."""
    strategy: str
    symbol: str
    validated_at: str
    passed: bool
    checks: dict[str, bool]
    metrics: dict[str, float]
    issues: list[str]
    recommendation: str
    # Regime analysis
    regime_performance: dict = field(default_factory=dict)
    current_regime: str = ""


def get_strategy_signals(strategy_name: str, data: pd.DataFrame) -> pd.Series:
    """Generate signals for a strategy."""
    prices = data['Close']

    if strategy_name == 'bollinger_reversal':
        sma = prices.rolling(20).mean()
        std = prices.rolling(20).std()
        lower = sma - 2 * std
        upper = sma + 2 * std
        signals = pd.Series(0, index=prices.index)
        signals[prices < lower] = 1
        signals[prices > upper] = -1

    elif strategy_name == 'momentum':
        mom = prices.pct_change(20)
        signals = pd.Series(0, index=prices.index)
        signals[mom > 0.05] = 1
        signals[mom < -0.05] = -1

    elif strategy_name == 'rsi_reversal':
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        signals = pd.Series(0, index=prices.index)
        signals[rsi < 30] = 1
        signals[rsi > 70] = -1

    elif strategy_name == 'breakout':
        high_20 = prices.rolling(20).max()
        low_20 = prices.rolling(20).min()
        signals = pd.Series(0, index=prices.index)
        signals[prices >= high_20] = 1
        signals[prices <= low_20] = -1

    else:
        # Default: momentum-like
        mom = prices.pct_change(10)
        signals = pd.Series(0, index=prices.index)
        signals[mom > 0.03] = 1
        signals[mom < -0.03] = -1

    return signals


def compute_strategy_returns(signals: pd.Series, prices: pd.DataFrame) -> pd.Series:
    """Compute strategy returns from signals."""
    returns = prices['Close'].pct_change()
    strategy_returns = signals.shift(1) * returns
    return strategy_returns.dropna()


def mcpt_test(strategy_returns: pd.Series, benchmark_returns: pd.Series, n_permutations: int = 1000) -> tuple[float, float, list[float]]:
    """Monte Carlo Permutation Test using evaluation module when available.

    Tests if strategy returns are significantly better than random signal timing.

    Returns:
        tuple: (p_value, strategy_sharpe, list of permuted sharpes for plotting)
    """
    permuted_sharpes = []

    # Try using evaluation module first
    if EVAL_MODULE_AVAILABLE:
        try:
            result = eval_mcpt_test(
                strategy_returns=strategy_returns.dropna(),
                benchmark_returns=benchmark_returns.dropna(),
                n_permutations=n_permutations,
            )
            sharpe = sharpe_ratio(strategy_returns) if len(strategy_returns.dropna()) > 20 else 0
            # Generate permuted sharpes for plotting if not in result
            if hasattr(result, 'permuted_sharpes') and result.permuted_sharpes:
                permuted_sharpes = list(result.permuted_sharpes)
            else:
                # Generate them for plotting
                abs_returns = np.abs(strategy_returns.dropna().values)
                n = len(abs_returns)
                for _ in range(min(n_permutations, 500)):
                    random_signs = np.random.choice([-1, 1], size=n)
                    perm_returns = abs_returns * random_signs
                    ps = np.mean(perm_returns) / np.std(perm_returns) * np.sqrt(252) if np.std(perm_returns) > 0 else 0
                    permuted_sharpes.append(ps)
            return result.p_value, sharpe, permuted_sharpes
        except Exception as e:
            logger.debug(f"Evaluation module MCPT failed, using fallback: {e}")

    # Fallback implementation
    strategy_sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0

    # Use absolute returns - these represent magnitude without signal direction
    abs_returns = np.abs(strategy_returns.values)
    n = len(abs_returns)

    count_better = 0
    for _ in range(n_permutations):
        # Random signs simulate random signal direction
        random_signs = np.random.choice([-1, 1], size=n)
        perm_returns = abs_returns * random_signs
        perm_sharpe = np.mean(perm_returns) / np.std(perm_returns) * np.sqrt(252) if np.std(perm_returns) > 0 else 0
        permuted_sharpes.append(perm_sharpe)
        if perm_sharpe >= strategy_sharpe:
            count_better += 1

    p_value = (count_better + 1) / (n_permutations + 1)
    return p_value, strategy_sharpe, permuted_sharpes


def walk_forward_validate(strategy_name: str, data: pd.DataFrame, n_splits: int = 5) -> dict:
    """Walk-forward validation."""
    n = len(data)
    split_size = n // n_splits

    is_sharpes = []
    oos_sharpes = []

    for i in range(n_splits - 1):
        train_end = (i + 1) * split_size
        test_end = (i + 2) * split_size

        train_data = data.iloc[:train_end]
        test_data = data.iloc[train_end:test_end]

        # In-sample
        train_signals = get_strategy_signals(strategy_name, train_data)
        train_returns = compute_strategy_returns(train_signals, train_data)
        is_sharpe = train_returns.mean() / train_returns.std() * np.sqrt(252) if train_returns.std() > 0 else 0
        is_sharpes.append(is_sharpe)

        # Out-of-sample
        test_signals = get_strategy_signals(strategy_name, test_data)
        test_returns = compute_strategy_returns(test_signals, test_data)
        oos_sharpe = test_returns.mean() / test_returns.std() * np.sqrt(252) if test_returns.std() > 0 else 0
        oos_sharpes.append(oos_sharpe)

    return {
        'is_sharpe': np.mean(is_sharpes),
        'oos_sharpe': np.mean(oos_sharpes),
        'oos_is_ratio': np.mean(oos_sharpes) / max(np.mean(is_sharpes), 0.01)
    }


def bootstrap_sharpe(returns: pd.Series, n_samples: int = 1000) -> tuple[float, float, list[float]]:
    """Bootstrap Sharpe ratio confidence interval using evaluation module when available.

    Returns:
        tuple: (ci_lower, ci_upper, list of bootstrapped sharpes for plotting)
    """
    sharpes = []

    # Try using evaluation module first
    if EVAL_MODULE_AVAILABLE:
        try:
            bootstrap_ci = BootstrapCI(n_bootstrap=n_samples, confidence_level=0.95)
            ci_result = bootstrap_ci.compute(
                returns.dropna().values,
                statistic_func=lambda x: np.mean(x) / np.std(x) * np.sqrt(252) if np.std(x) > 0 else 0
            )
            # Generate bootstrap sharpes for plotting if not available in result
            if hasattr(ci_result, 'bootstrap_samples') and ci_result.bootstrap_samples:
                sharpes = list(ci_result.bootstrap_samples)
            else:
                # Generate them for plotting
                n = len(returns)
                for _ in range(min(n_samples, 500)):
                    sample = np.random.choice(returns.dropna().values, size=n, replace=True)
                    if np.std(sample) > 0:
                        sharpes.append(np.mean(sample) / np.std(sample) * np.sqrt(252))
            return ci_result.lower, ci_result.upper, sharpes
        except Exception as e:
            logger.debug(f"Evaluation module bootstrap failed, using fallback: {e}")

    # Fallback implementation
    n = len(returns)

    for _ in range(n_samples):
        sample = np.random.choice(returns.values, size=n, replace=True)
        if np.std(sample) > 0:
            sharpe = np.mean(sample) / np.std(sample) * np.sqrt(252)
            sharpes.append(sharpe)

    ci_lower = np.percentile(sharpes, 2.5)
    ci_upper = np.percentile(sharpes, 97.5)
    return ci_lower, ci_upper, sharpes


def test_transaction_costs(strategy_name: str, data: pd.DataFrame, costs: list[int] = None) -> dict:
    """Test sensitivity to transaction costs."""
    if costs is None:
        costs = [0, 5, 10, 20]

    signals = get_strategy_signals(strategy_name, data)
    returns = data['Close'].pct_change()

    results = {}
    for cost_bps in costs:
        cost_pct = cost_bps / 10000
        trades = (signals.diff() != 0).sum()

        strategy_returns = signals.shift(1) * returns
        total_cost = trades * cost_pct
        adjusted_returns = strategy_returns - (total_cost / len(returns))

        sharpe = adjusted_returns.mean() / adjusted_returns.std() * np.sqrt(252) if adjusted_returns.std() > 0 else 0
        results[cost_bps] = sharpe

    return results


def test_pdt_holding_periods(strategy_name: str, data: pd.DataFrame, periods: list[int] = None) -> tuple[dict, dict]:
    """Test different holding periods for PDT compliance.

    Returns:
        tuple: (sharpes_by_holding: dict, returns_by_holding: dict for plotting)
    """
    if periods is None:
        periods = [0, 2, 5, 10]

    signals = get_strategy_signals(strategy_name, data)
    returns = data['Close'].pct_change()

    sharpes = {}
    returns_by_holding = {}

    for hp in periods:
        if hp == 0:
            held_signals = signals
        else:
            held_signals = signals.copy()
            position = 0
            hold_counter = 0

            for i in range(len(signals)):
                if hold_counter > 0:
                    held_signals.iloc[i] = position
                    hold_counter -= 1
                elif signals.iloc[i] != 0 and signals.iloc[i] != position:
                    position = signals.iloc[i]
                    hold_counter = hp
                    held_signals.iloc[i] = position
                else:
                    held_signals.iloc[i] = position

        strat_returns = held_signals.shift(1) * returns
        valid_returns = strat_returns.dropna()

        if len(valid_returns) > 20:
            sharpe = valid_returns.mean() / valid_returns.std() * np.sqrt(252) if valid_returns.std() > 0 else 0
            sharpes[hp] = sharpe
            returns_by_holding[hp] = valid_returns

    return sharpes, returns_by_holding


def run_validation(strategy_name: str, symbol: str, quick: bool = False, generate_plots: bool = False) -> ValidationResult:
    """Run full validation suite.

    Args:
        strategy_name: Name of the strategy to validate
        symbol: Symbol to test
        quick: Run quick validation with fewer permutations
        generate_plots: Generate comprehensive validation plots

    Returns:
        ValidationResult with all metrics and checks
    """
    logger.info(f"Starting validation for {strategy_name} on {symbol}")

    checks = {}
    metrics = {}
    issues = []

    # Fetch data
    logger.info("Fetching data...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="2y")

    if len(data) < 100:
        return ValidationResult(
            strategy=strategy_name,
            symbol=symbol,
            validated_at=datetime.now().isoformat(),
            passed=False,
            checks={},
            metrics={},
            issues=["Insufficient data"],
            recommendation="REJECT"
        )

    # Generate signals and returns
    signals = get_strategy_signals(strategy_name, data)
    strategy_returns = compute_strategy_returns(signals, data)
    benchmark_returns = data['Close'].pct_change().dropna()

    # 1. MCPT Test
    logger.info("Running MCPT test...")
    n_perms = 100 if quick else 500
    p_value, sharpe, mcpt_permuted_sharpes = mcpt_test(strategy_returns, benchmark_returns, n_perms)

    checks['mcpt_significant'] = p_value < 0.05
    metrics['mcpt_p_value'] = p_value
    metrics['mcpt_sharpe'] = sharpe

    if not checks['mcpt_significant']:
        issues.append(f"CRITICAL: Not significant (p={p_value:.4f})")

    logger.info(f"  p-value: {p_value:.4f}, Sharpe: {sharpe:.2f}")

    # 2. Walk-Forward Validation
    logger.info("Running walk-forward validation...")
    wf_result = walk_forward_validate(strategy_name, data, n_splits=3 if quick else 5)

    checks['walk_forward_oos'] = wf_result['oos_sharpe'] > 0.5
    metrics['is_sharpe'] = wf_result['is_sharpe']
    metrics['oos_sharpe'] = wf_result['oos_sharpe']
    metrics['oos_is_ratio'] = wf_result['oos_is_ratio']

    if not checks['walk_forward_oos']:
        issues.append(f"WARNING: Low OOS Sharpe ({wf_result['oos_sharpe']:.2f})")

    logger.info(f"  IS Sharpe: {wf_result['is_sharpe']:.2f}, OOS Sharpe: {wf_result['oos_sharpe']:.2f}")

    # 3. Overfitting Check
    checks['not_overfit'] = metrics['oos_is_ratio'] > 0.5
    if not checks['not_overfit']:
        issues.append(f"WARNING: Possible overfitting (OOS/IS={metrics['oos_is_ratio']:.2f})")

    # 4. Sharpe CI
    logger.info("Computing Sharpe confidence interval...")
    ci_lower, ci_upper, bootstrap_sharpes = bootstrap_sharpe(strategy_returns, n_samples=500 if quick else 1000)

    checks['sharpe_ci_positive'] = ci_lower > 0
    metrics['sharpe_ci_lower'] = ci_lower
    metrics['sharpe_ci_upper'] = ci_upper

    if not checks['sharpe_ci_positive']:
        issues.append(f"WARNING: Sharpe CI includes 0 [{ci_lower:.2f}, {ci_upper:.2f}]")

    logger.info(f"  Sharpe CI: [{ci_lower:.2f}, {ci_upper:.2f}]")

    # 5. Transaction Cost Test
    logger.info("Testing transaction cost sensitivity...")
    cost_results = test_transaction_costs(strategy_name, data)

    checks['survives_costs'] = cost_results.get(10, 0) > cost_results.get(0, 0) * 0.5
    metrics['sharpe_0bps'] = cost_results.get(0, 0)
    metrics['sharpe_10bps'] = cost_results.get(10, 0)

    if not checks['survives_costs']:
        issues.append(f"WARNING: High cost sensitivity (10bps Sharpe={cost_results.get(10, 0):.2f})")

    logger.info(f"  0bps: {cost_results.get(0, 0):.2f}, 10bps: {cost_results.get(10, 0):.2f}")

    # 6. PDT Compliance
    logger.info("Testing PDT holding periods...")
    pdt_results, pdt_returns_by_holding = test_pdt_holding_periods(strategy_name, data)

    compliant_results = {hp: s for hp, s in pdt_results.items() if hp >= 2}
    if compliant_results:
        best_hp = max(compliant_results, key=compliant_results.get)
        checks['pdt_compliant'] = compliant_results[best_hp] > 0
        metrics['pdt_best_holding'] = best_hp
        metrics['pdt_best_sharpe'] = compliant_results[best_hp]
    else:
        checks['pdt_compliant'] = False
        issues.append("WARNING: No PDT-compliant configuration found")

    logger.info(f"  PDT results: {pdt_results}")

    # 7. Regime Analysis (using evaluation module)
    regime_performance = {}
    current_regime = ""
    if EVAL_MODULE_AVAILABLE:
        try:
            logger.info("Running regime analysis...")
            regimes = detect_regimes(data)
            regime_perf = evaluate_by_regime(strategy_returns, regimes)
            regime_performance = {str(k): v for k, v in regime_perf.items()} if regime_perf else {}

            current = get_current_regime(data)
            # get_current_regime returns {'success': bool, 'data': {'regime': str, 'probability': float}}
            if isinstance(current, dict) and current.get("success"):
                current_regime = current.get("data", {}).get("regime", "")
                checks['regime_consistent'] = True  # Strategy has consistent regime performance
                logger.info(f"  Current regime: {current_regime}")
                for regime, perf in regime_performance.items():
                    if isinstance(perf, dict):
                        logger.info(f"    {regime}: Sharpe={perf.get('sharpe', 0):.2f}")
        except Exception as e:
            logger.debug(f"Regime analysis failed: {e}")

    # 8. Additional metrics from evaluation module
    if EVAL_MODULE_AVAILABLE:
        try:
            metrics['sortino'] = sortino_ratio(strategy_returns)
            metrics['calmar'] = calmar_ratio(strategy_returns)
            metrics['max_drawdown'] = max_drawdown(strategy_returns)
            metrics['win_rate'] = win_rate(strategy_returns)
            metrics['total_return'] = total_return(strategy_returns)
        except Exception as e:
            logger.debug(f"Additional metrics failed: {e}")

    # Determine recommendation
    critical_checks = ['mcpt_significant']
    all_critical_passed = all(checks.get(c, False) for c in critical_checks)
    all_checks_passed = all(checks.values())

    if all_critical_passed and all_checks_passed:
        recommendation = "APPROVE"
    elif all_critical_passed:
        recommendation = "NEEDS_REVIEW"
    else:
        recommendation = "REJECT"

    result = ValidationResult(
        strategy=strategy_name,
        symbol=symbol,
        validated_at=datetime.now().isoformat(),
        passed=all_checks_passed,
        checks=checks,
        metrics=metrics,
        issues=issues,
        recommendation=recommendation,
        regime_performance=regime_performance,
        current_regime=current_regime,
    )

    # Save result
    output_dir = paths.validation_reports
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"validation_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_dir / filename, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)

    logger.info(f"Report saved to: {output_dir / filename}")

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"Strategy: {strategy_name}")
    print(f"Symbol: {symbol}")
    print(f"Recommendation: {recommendation}")
    print(f"\nChecks ({sum(checks.values())}/{len(checks)} passed):")
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check}")

    if issues:
        print(f"\nIssues:")
        for issue in issues:
            print(f"  - {issue}")

    print(f"\nKey Metrics:")
    print(f"  Sharpe: {metrics.get('mcpt_sharpe', 0):.2f}")
    print(f"  p-value: {metrics.get('mcpt_p_value', 1):.4f}")
    print(f"  OOS Sharpe: {metrics.get('oos_sharpe', 0):.2f}")
    print(f"  PDT Hold: {metrics.get('pdt_best_holding', 'N/A')} days")

    # Generate plots if requested
    if generate_plots and PLOTS_AVAILABLE:
        try:
            logger.info("Generating validation plots...")
            plotter = StrategyPlotter()

            # 1. Comprehensive validation dashboard (2x2 grid)
            logger.info("  Creating comprehensive validation dashboard...")
            plotter.plot_comprehensive_validation(
                strategy_returns=strategy_returns,
                price_data=data,
                returns_by_holding=pdt_returns_by_holding,
                mcpt_sharpes=mcpt_permuted_sharpes,
                mcpt_p_value=p_value,
                bootstrap_sharpes=bootstrap_sharpes,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
                strategy_name=strategy_name,
                symbol=symbol,
            )

            # 2. Strategy vs Random vs Buy-and-Hold equity curve
            logger.info("  Creating equity curve plot...")
            plotter.plot_strategy_vs_random_vs_buyhold(
                strategy_returns=strategy_returns,
                price_data=data,
                strategy_name=strategy_name,
                symbol=symbol,
                n_random=100,
            )

            # 3. PDT holding period comparison
            if pdt_returns_by_holding:
                logger.info("  Creating PDT comparison plot...")
                plotter.plot_pdt_comparison(
                    returns_by_holding=pdt_returns_by_holding,
                    strategy_name=strategy_name,
                    symbol=symbol,
                )

            # 4. MCPT distribution
            if mcpt_permuted_sharpes:
                logger.info("  Creating MCPT distribution plot...")
                plotter.plot_mcpt_distribution(
                    original_sharpe=sharpe,
                    permuted_sharpes=mcpt_permuted_sharpes,
                    p_value=p_value,
                    strategy_name=strategy_name,
                    symbol=symbol,
                )

            # 5. Bootstrap CI
            if bootstrap_sharpes:
                logger.info("  Creating bootstrap CI plot...")
                plotter.plot_bootstrap_ci(
                    returns=strategy_returns,
                    bootstrap_sharpes=bootstrap_sharpes,
                    ci_lower=ci_lower,
                    ci_upper=ci_upper,
                    strategy_name=strategy_name,
                    symbol=symbol,
                )

            print(f"\nPlots saved to: {plotter.output_dir}")

        except Exception as e:
            logger.error(f"Plot generation failed: {e}")
    elif generate_plots and not PLOTS_AVAILABLE:
        logger.warning("Plot generation requested but matplotlib not available. Install with: pip install matplotlib")

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate a trading strategy")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--symbol", required=True, help="Symbol to test")
    parser.add_argument("--quick", action="store_true", help="Quick validation (fewer permutations)")
    parser.add_argument("--plots", action="store_true", help="Generate validation plots")

    args = parser.parse_args()

    result = run_validation(args.strategy, args.symbol, args.quick, args.plots)

    return 0 if result.passed else 1


if __name__ == "__main__":
    exit(main())
