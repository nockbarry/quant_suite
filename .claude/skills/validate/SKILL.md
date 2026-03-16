---
name: validate
description: Run the complete validation suite on a strategy before production. Use when testing strategies, running MCPT, walk-forward validation, checking for bias, or ensuring a strategy meets all quality requirements. This is the gatekeeper before any promotion.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, Edit
---

# Validation Suite Skill

Complete validation pipeline ensuring strategies meet all quality standards.

## Validation Checklist

Every strategy MUST pass ALL checks before production:

| Check | Tool | Threshold | Required |
|-------|------|-----------|----------|
| MCPT Significance | `mcpt_test()` | p < 0.05 | YES |
| Walk-Forward OOS | `WalkForwardValidator` | Sharpe > 0.5 | YES |
| Lookahead Bias | `detect_lookahead()` | None detected | YES |
| Sharpe CI | Bootstrap | Lower bound > 0 | YES |
| Transaction Costs | Backtest | Survives 10bps | YES |
| Overfitting Check | IS/OOS ratio | OOS > 50% of IS | YES |
| PDT Compliance | `PDTAwareBacktest` | Valid for account | YES |
| Regime Robustness | Multi-period | Works in 3+ regimes | RECOMMENDED |

## Quick Start

```bash
# Run full validation suite
PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM

# Individual checks
PYTHONPATH=. python -c "
from src.evaluation.validation.mcpt import mcpt_test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f'p-value: {result.p_value:.4f}')
"
```

## Full Validation Pipeline

```python
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class ValidationResult:
    strategy: str
    symbol: str
    validated_at: str
    passed: bool
    checks: dict[str, bool]
    metrics: dict[str, float]
    issues: list[str]
    recommendation: str  # APPROVE, REJECT, NEEDS_REVIEW

def run_full_validation(strategy, symbol, data) -> ValidationResult:
    """
    Run complete validation suite on a strategy.
    """
    checks = {}
    metrics = {}
    issues = []

    # ===== 1. MCPT Significance Test =====
    print("Running MCPT significance test...")
    from src.evaluation.validation.mcpt import mcpt_test

    strategy_returns = compute_strategy_returns(strategy, data)
    benchmark_returns = data['returns']

    mcpt_result = mcpt_test(
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        n_permutations=1000
    )

    checks['mcpt_significant'] = mcpt_result.p_value < 0.05
    metrics['mcpt_p_value'] = mcpt_result.p_value
    metrics['mcpt_sharpe'] = mcpt_result.strategy_sharpe

    if not checks['mcpt_significant']:
        issues.append(f"CRITICAL: Not significant (p={mcpt_result.p_value:.4f})")

    # ===== 2. Walk-Forward Validation =====
    print("Running walk-forward validation...")
    from src.evaluation.validation.walk_forward import WalkForwardValidator

    wf_validator = WalkForwardValidator(n_splits=5, test_size=0.2)
    wf_result = wf_validator.validate(strategy, data)

    checks['walk_forward_oos'] = wf_result.oos_sharpe > 0.5
    metrics['is_sharpe'] = wf_result.is_sharpe
    metrics['oos_sharpe'] = wf_result.oos_sharpe
    metrics['oos_is_ratio'] = wf_result.oos_sharpe / max(wf_result.is_sharpe, 0.01)

    if not checks['walk_forward_oos']:
        issues.append(f"WARNING: Low OOS Sharpe ({wf_result.oos_sharpe:.2f})")

    # ===== 3. Overfitting Check =====
    print("Checking for overfitting...")
    checks['not_overfit'] = metrics['oos_is_ratio'] > 0.5

    if not checks['not_overfit']:
        issues.append(f"WARNING: Possible overfitting (OOS/IS={metrics['oos_is_ratio']:.2f})")

    # ===== 4. Lookahead Bias Detection =====
    print("Checking for lookahead bias...")
    checks['no_lookahead'] = detect_lookahead_bias(strategy, data)

    if not checks['no_lookahead']:
        issues.append("CRITICAL: Lookahead bias detected")

    # ===== 5. Sharpe Confidence Interval =====
    print("Computing Sharpe confidence interval...")
    import numpy as np

    sharpe_samples = bootstrap_sharpe(strategy_returns, n_samples=1000)
    ci_lower = np.percentile(sharpe_samples, 2.5)
    ci_upper = np.percentile(sharpe_samples, 97.5)

    checks['sharpe_ci_positive'] = ci_lower > 0
    metrics['sharpe_ci_lower'] = ci_lower
    metrics['sharpe_ci_upper'] = ci_upper

    if not checks['sharpe_ci_positive']:
        issues.append(f"WARNING: Sharpe CI includes 0 [{ci_lower:.2f}, {ci_upper:.2f}]")

    # ===== 6. Transaction Cost Sensitivity =====
    print("Testing transaction cost sensitivity...")
    from src.evaluation.backtest.engine import VectorizedBacktest

    sharpes_by_cost = {}
    for cost_bps in [0, 5, 10, 20]:
        backtest = VectorizedBacktest(strategy=strategy, transaction_cost_bps=cost_bps)
        result = backtest.run(data)
        sharpes_by_cost[cost_bps] = result.sharpe_ratio

    checks['survives_costs'] = sharpes_by_cost[10] > sharpes_by_cost[0] * 0.5
    metrics['sharpe_0bps'] = sharpes_by_cost[0]
    metrics['sharpe_10bps'] = sharpes_by_cost[10]

    if not checks['survives_costs']:
        issues.append(f"WARNING: High cost sensitivity (10bps Sharpe={sharpes_by_cost[10]:.2f})")

    # ===== 7. PDT Compliance =====
    print("Checking PDT compliance...")
    from src.evaluation.validation.pdt_framework import PDTAwareBacktest, AccountType

    pdt_backtest = PDTAwareBacktest(account_type=AccountType.BUDGET)
    pdt_results = pdt_backtest.compare_holding_periods(
        strategy.generate_signals(data),
        data['Close'],
        holding_periods=[0, 2, 5, 10]
    )

    # Find best PDT-compliant config
    compliant_results = [r for r in pdt_results if r.holding_period_days >= 2]
    if compliant_results:
        best_pdt = max(compliant_results, key=lambda x: x.sharpe_ratio)
        checks['pdt_compliant'] = best_pdt.sharpe_ratio > 0
        metrics['pdt_best_holding'] = best_pdt.holding_period_days
        metrics['pdt_best_sharpe'] = best_pdt.sharpe_ratio
    else:
        checks['pdt_compliant'] = False
        issues.append("WARNING: No PDT-compliant configuration found")

    # ===== 8. Regime Robustness (Optional) =====
    print("Testing regime robustness...")
    regime_sharpes = test_regime_robustness(strategy, data)
    positive_regimes = sum(1 for s in regime_sharpes.values() if s > 0)

    checks['regime_robust'] = positive_regimes >= 2
    metrics['regimes_positive'] = positive_regimes
    metrics['regime_sharpes'] = regime_sharpes

    # ===== Generate Result =====
    all_critical_passed = all([
        checks['mcpt_significant'],
        checks['no_lookahead'],
        checks['walk_forward_oos'],
    ])

    all_checks_passed = all(checks.values())

    if all_critical_passed and all_checks_passed:
        recommendation = "APPROVE"
    elif all_critical_passed:
        recommendation = "NEEDS_REVIEW"
    else:
        recommendation = "REJECT"

    return ValidationResult(
        strategy=strategy.name,
        symbol=symbol,
        validated_at=datetime.now().isoformat(),
        passed=all_checks_passed,
        checks=checks,
        metrics=metrics,
        issues=issues,
        recommendation=recommendation
    )
```

## Individual Validation Functions

### MCPT Test

```python
from src.evaluation.validation.mcpt import mcpt_test

def validate_significance(strategy_returns, benchmark_returns, n_perms=1000):
    """
    Monte Carlo Permutation Test for statistical significance.
    """
    result = mcpt_test(
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        n_permutations=n_perms
    )

    print(f"Strategy Sharpe: {result.strategy_sharpe:.2f}")
    print(f"p-value: {result.p_value:.4f}")
    print(f"Significant: {result.p_value < 0.05}")

    return result.p_value < 0.05
```

### Walk-Forward Validation

```python
from src.evaluation.validation.walk_forward import WalkForwardValidator

def validate_walk_forward(strategy, data, n_splits=5):
    """
    Walk-forward out-of-sample validation.
    """
    validator = WalkForwardValidator(n_splits=n_splits, test_size=0.2)
    result = validator.validate(strategy, data)

    print(f"In-Sample Sharpe: {result.is_sharpe:.2f}")
    print(f"Out-of-Sample Sharpe: {result.oos_sharpe:.2f}")
    print(f"OOS/IS Ratio: {result.oos_sharpe/result.is_sharpe:.2%}")

    return result.oos_sharpe > 0.5
```

### Lookahead Bias Detection

```python
def detect_lookahead_bias(strategy, data):
    """
    Detect if strategy uses future information.
    """
    import numpy as np

    # Test 1: Shuffle future returns
    original_signals = strategy.generate_signals(data)

    shuffled_data = data.copy()
    shuffled_data['returns'] = np.random.permutation(data['returns'].values)
    shuffled_signals = strategy.generate_signals(shuffled_data)

    # Signals should be identical if no lookahead
    signals_match = np.allclose(
        original_signals.fillna(0).values,
        shuffled_signals.fillna(0).values
    )

    if not signals_match:
        print("WARNING: Signals changed when future returns shuffled")
        return False

    # Test 2: Progressive data test
    for t in range(50, len(data), 50):
        partial_data = data.iloc[:t]
        full_signal = strategy.generate_signals(data).iloc[t-1]
        partial_signal = strategy.generate_signals(partial_data).iloc[-1]

        if full_signal != partial_signal:
            print(f"WARNING: Signal at t={t} differs with restricted data")
            return False

    return True
```

### Bootstrap Sharpe CI

```python
import numpy as np

def bootstrap_sharpe(returns, n_samples=1000):
    """
    Bootstrap Sharpe ratio confidence interval.
    """
    sharpes = []
    n = len(returns)

    for _ in range(n_samples):
        sample = np.random.choice(returns, size=n, replace=True)
        if np.std(sample) > 0:
            sharpe = np.mean(sample) / np.std(sample) * np.sqrt(252)
            sharpes.append(sharpe)

    return sharpes
```

### Regime Robustness

```python
def test_regime_robustness(strategy, data):
    """
    Test strategy across different market regimes.
    """
    from src.evaluation.backtest.engine import VectorizedBacktest

    # Define regimes by volatility
    vol = data['returns'].rolling(20).std()
    vol_median = vol.median()

    regimes = {
        'low_vol': data[vol < vol_median * 0.8],
        'normal_vol': data[(vol >= vol_median * 0.8) & (vol <= vol_median * 1.2)],
        'high_vol': data[vol > vol_median * 1.2],
    }

    sharpes = {}
    for regime_name, regime_data in regimes.items():
        if len(regime_data) > 50:
            backtest = VectorizedBacktest(strategy=strategy)
            result = backtest.run(regime_data)
            sharpes[regime_name] = result.sharpe_ratio
            print(f"  {regime_name}: Sharpe={result.sharpe_ratio:.2f}")

    return sharpes
```

## Validation Report

```python
def save_validation_report(result: ValidationResult):
    """
    Save validation report to disk.
    """
    output_dir = paths.base / "validation_reports"
    output_dir.mkdir(exist_ok=True)

    filename = f"validation_{result.strategy}_{result.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_dir / filename, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)

    # Also log to tracker
    from workflows.research.session_tracker import get_tracker
    tracker = get_tracker()

    tracker.log_insight(
        title=f"Validation: {result.strategy}/{result.symbol} - {result.recommendation}",
        description=f"Passed {sum(result.checks.values())}/{len(result.checks)} checks",
        category="strategy",
        evidence=asdict(result),
        tags=["validation", result.recommendation.lower()]
    )

    return output_dir / filename
```

## Output Locations

| Output | Path |
|--------|------|
| Validation reports | `~/quant_results/validation_reports/` |
| MCPT results | Embedded in validation report |
| Walk-forward results | Embedded in validation report |

## Integration with Other Skills

- After `/research`: Run validation on discovered strategies
- Before `/promote`: Validation must pass
- With `/critic`: Validation + critic = full safety check
- For `/report`: Include validation metrics in reports
