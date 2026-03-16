---
name: critic
description: Safety check for trading strategies to detect artificial performance inflation. Use when validating strategies, checking for bugs, lookahead bias, overfitting, data leakage, or other issues that make backtest results unreliable. Critical before promoting any strategy to production.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, Edit
---

# Critic Agent Skill

Safety validation to detect issues that artificially inflate strategy performance.

## Purpose

Before any strategy goes to production, the Critic Agent must verify:
1. No lookahead bias (future data leaking into signals)
2. No overfitting (strategy only works on training data)
3. No data leakage (information from test period in training)
4. No survivorship bias (only testing stocks that exist today)
5. No implementation bugs (signal timing, execution assumptions)

## Quick Start

```bash
# Run full critic validation on a strategy
PYTHONPATH=. python scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM

# Check for lookahead bias
PYTHONPATH=. python -c "
from src.evaluation.validation.bias_detection import detect_lookahead_bias
result = detect_lookahead_bias(strategy, data)
print(f'Lookahead bias: {result.has_bias}')
"
```

## Validation Checks

### 1. Lookahead Bias Detection

```python
from src.evaluation.validation.mcpt import MCPTValidator

validator = MCPTValidator()

# Check if strategy uses future information
def check_lookahead(strategy, data):
    """
    Test: Shuffle future returns, strategy performance should not change
    if it's not using future information.
    """
    import numpy as np

    original_signals = strategy.generate_signals(data)

    # Shuffle future returns
    shuffled_data = data.copy()
    shuffled_data['returns'] = np.random.permutation(data['returns'].values)

    shuffled_signals = strategy.generate_signals(shuffled_data)

    # Signals should be identical if no lookahead
    return np.allclose(original_signals, shuffled_signals)
```

### 2. Overfitting Detection

```python
from src.evaluation.validation.walk_forward import WalkForwardValidator

def check_overfitting(strategy, data, n_splits=5):
    """
    Walk-forward validation to detect overfitting.
    Red flag: Large gap between in-sample and out-of-sample performance.
    """
    validator = WalkForwardValidator(n_splits=n_splits)
    results = validator.validate(strategy, data)

    is_gap = results.is_sharpe_gap  # IS Sharpe >> OOS Sharpe
    oos_ratio = results.oos_sharpe / results.is_sharpe

    print(f"IS Sharpe: {results.is_sharpe:.2f}")
    print(f"OOS Sharpe: {results.oos_sharpe:.2f}")
    print(f"OOS/IS Ratio: {oos_ratio:.2%}")

    # Red flag if OOS is less than 50% of IS
    return oos_ratio < 0.5
```

### 3. Data Leakage Check

```python
def check_data_leakage(strategy, train_data, test_data):
    """
    Verify no information from test period leaked into training.
    """
    # Check 1: Feature computation dates
    feature_dates = strategy.get_feature_dates()
    test_start = test_data.index[0]

    leaked_features = [f for f in feature_dates if feature_dates[f] >= test_start]

    if leaked_features:
        print(f"LEAKAGE DETECTED: Features computed with test data: {leaked_features}")
        return True

    # Check 2: Model training dates
    if hasattr(strategy, 'model'):
        if strategy.model.training_end >= test_start:
            print("LEAKAGE: Model trained on test period data")
            return True

    return False
```

### 4. Signal Timing Validation

```python
def check_signal_timing(strategy, data):
    """
    Verify signals are generated BEFORE the bar they trade on.
    Common bug: Using close price to generate signal, then buying at close.
    """
    signals = strategy.generate_signals(data)

    # Check: Signal at time T should only use data up to T-1
    for t in range(1, len(signals)):
        # Get data available at signal time
        available_data = data.iloc[:t]

        # Regenerate signal with only available data
        single_signal = strategy.generate_signals(available_data)

        if signals.iloc[t-1] != single_signal.iloc[-1]:
            print(f"TIMING BUG at {data.index[t]}: Signal differs with restricted data")
            return True

    return False
```

### 5. Transaction Cost Sensitivity

```python
def check_transaction_sensitivity(strategy, data, costs=[0, 5, 10, 20, 50]):
    """
    Test if strategy survives realistic transaction costs.
    Red flag: Strategy only profitable with 0 costs.
    """
    from src.evaluation.backtest.engine import VectorizedBacktest

    results = {}
    for cost_bps in costs:
        backtest = VectorizedBacktest(
            strategy=strategy,
            transaction_cost_bps=cost_bps
        )
        result = backtest.run(data)
        results[cost_bps] = result.sharpe_ratio
        print(f"  {cost_bps}bps: Sharpe={result.sharpe_ratio:.2f}")

    # Red flag: Sharpe drops >50% from 0 to 10bps
    if results[10] < results[0] * 0.5:
        print("WARNING: Strategy very sensitive to transaction costs")
        return True

    return False
```

### 6. Statistical Significance

```python
from src.evaluation.validation.mcpt import mcpt_test

def check_statistical_significance(strategy_returns, benchmark_returns, n_perms=1000):
    """
    Monte Carlo Permutation Test for significance.
    """
    result = mcpt_test(
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        n_permutations=n_perms
    )

    print(f"p-value: {result.p_value:.4f}")
    print(f"Significant (p<0.05): {result.p_value < 0.05}")

    return result.p_value >= 0.05  # Returns True if NOT significant (a problem)
```

## Full Critic Validation Pipeline

```python
def run_critic_validation(strategy, symbol, data):
    """
    Run all critic checks on a strategy.
    """
    issues = []

    # 1. Lookahead bias
    if check_lookahead(strategy, data):
        issues.append("CRITICAL: Lookahead bias detected")

    # 2. Overfitting
    if check_overfitting(strategy, data):
        issues.append("WARNING: Possible overfitting (OOS << IS)")

    # 3. Signal timing
    if check_signal_timing(strategy, data):
        issues.append("CRITICAL: Signal timing bug")

    # 4. Transaction costs
    if check_transaction_sensitivity(strategy, data):
        issues.append("WARNING: High transaction cost sensitivity")

    # 5. Statistical significance
    if check_statistical_significance(strategy.returns, data['returns']):
        issues.append("CRITICAL: Not statistically significant (p>=0.05)")

    # Report
    print("\n" + "="*50)
    print("CRITIC VALIDATION REPORT")
    print("="*50)
    print(f"Strategy: {strategy.name}")
    print(f"Symbol: {symbol}")
    print(f"Issues found: {len(issues)}")

    for issue in issues:
        print(f"  - {issue}")

    if not issues:
        print("  ALL CHECKS PASSED")

    return len(issues) == 0
```

## Red Flags to Watch For

| Red Flag | Severity | Action |
|----------|----------|--------|
| OOS Sharpe < 50% of IS Sharpe | High | Reduce complexity, regularize |
| p-value > 0.05 | Critical | Do not promote |
| Sharpe drops >50% with 10bps costs | Medium | Reduce trade frequency |
| Signal uses same-bar close price | Critical | Fix signal timing |
| Feature uses future data | Critical | Fix feature computation |
| Only works on specific date range | High | Test multiple periods |

## Critic Report Output

After validation, generate a critic report:

```python
critic_report = {
    "strategy": strategy.name,
    "symbol": symbol,
    "validation_date": datetime.now().isoformat(),
    "checks": {
        "lookahead_bias": False,
        "overfitting": False,
        "signal_timing": True,
        "transaction_sensitivity": False,
        "statistical_significance": True
    },
    "metrics": {
        "is_sharpe": 2.5,
        "oos_sharpe": 1.8,
        "oos_is_ratio": 0.72,
        "p_value": 0.008,
        "sharpe_at_10bps": 2.1
    },
    "recommendation": "APPROVE" | "REJECT" | "NEEDS_REVIEW",
    "issues": [],
    "notes": ""
}
```

Save to: `~/quant_results/critic_reports/`
