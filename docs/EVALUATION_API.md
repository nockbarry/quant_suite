# Evaluation API Reference

Comprehensive testing and validation framework for quantitative strategies.

**Module Location**: `src/evaluation/`

---

## Table of Contents

1. [Backtesting Engine](#backtesting-engine)
2. [Statistical Validation](#statistical-validation)
3. [Cross-Validation](#cross-validation)
4. [Regime Analysis](#regime-analysis)
5. [PDT Framework](#pdt-framework)
6. [Performance Metrics](#performance-metrics)
7. [Statistical Testing](#statistical-testing)
8. [Performance Attribution](#performance-attribution)
9. [Reporting](#reporting)

---

## Backtesting Engine

```python
from src.evaluation import (
    VectorizedBacktest, BacktestConfig, BacktestResult, run_backtest,
    PercentageCost, TieredCost, SpreadCost, MarketImpactCost,
    BudgetExecutionModel, ExecutionModel,
)

# Quick backtest
backtest = VectorizedBacktest(strategy, transaction_cost_bps=10)
result = backtest.run(data)

# With cost model
from src.evaluation.backtest import MarketImpactCost
cost_model = MarketImpactCost(impact_coefficient=0.1)
backtest = VectorizedBacktest(strategy, cost_model=cost_model)
```

---

## Statistical Validation

### MCPT (Monte Carlo Permutation Test)

```python
from src.evaluation import mcpt_test, mcpt_walk_forward, MCPTAnalyzer

# Basic significance test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {result.p_value:.4f}, Significant: {result.significant}")

# Combined with walk-forward
wf_mcpt = mcpt_walk_forward(strategy, data, n_splits=5, n_permutations=500)
```

### Walk-Forward Validation

```python
from src.evaluation import (
    run_walk_forward, WalkForwardOptimizer, ParameterOptimizer,
    WalkForwardSplitter, walk_forward_summary,
)

# Out-of-sample validation
result = run_walk_forward(strategy, data, n_splits=5)
print(walk_forward_summary(result))

# Parameter optimization
optimizer = WalkForwardOptimizer(strategy_class, param_grid)
best_params = optimizer.optimize(data)
```

### Hypothesis Testing (Data Snooping Protection)

```python
from src.evaluation import (
    WhiteRealityCheck, HansenSPA, StepwiseSPA,
    reality_check, spa_test, stepwise_spa,
    BlockBootstrap, multiple_testing_summary,
)

# White's Reality Check - tests if best strategy beats benchmark after snooping
rc_result = reality_check(strategy_returns_list, benchmark_returns)
print(f"Best survives: {rc_result.best_survives}")

# Hansen's SPA - more powerful test
spa_result = spa_test(strategy_returns_list, benchmark_returns)

# Stepwise SPA - identify all significant strategies
stepwise = stepwise_spa(strategy_returns_list, benchmark_returns)
print(f"Significant strategies: {stepwise.significant_indices}")
```

### Multi-Level Holdout

```python
from src.evaluation import (
    MultiLevelHoldout, DevelopmentSplitter,
    create_holdout_structure, validate_holdout_usage,
)

# Proper dev/val/test splits
holdout = create_holdout_structure(
    data,
    dev_pct=0.6,
    val_pct=0.2,
    test_pct=0.2,
)

# Validate no leakage
issues = validate_holdout_usage(holdout)
if issues:
    print(f"Leakage detected: {issues}")
```

---

## Cross-Validation

```python
from src.evaluation import (
    PurgedKFoldCV, CombinatorialPurgedCV, TimeSeriesCV,
    purged_cv, combinatorial_purged_cv, cv_summary,
)

# Purged K-Fold (prevents lookahead)
cv = PurgedKFoldCV(n_splits=5, embargo_pct=0.01)
results = purged_cv(strategy, data, cv)
print(cv_summary(results))

# Combinatorial Purged CV (de Prado method)
cpcv_results = combinatorial_purged_cv(strategy, data, n_splits=10, n_test_splits=2)
```

---

## Regime Analysis

### Standard Regime Detection

```python
from src.evaluation import (
    RuleBasedRegimeDetector, HMMRegimeDetector,
    detect_regimes, evaluate_by_regime, get_current_regime,
    ConditionalEvaluator, RegimeType,
)

# Detect market regimes
regimes = detect_regimes(market_data, method='hmm')
current = get_current_regime(market_data)
print(f"Current regime: {current.regime_type}, Confidence: {current.confidence:.2f}")

# Evaluate strategy by regime
regime_perf = evaluate_by_regime(strategy_returns, regimes)
for regime, metrics in regime_perf.items():
    print(f"{regime}: Sharpe={metrics['sharpe']:.2f}")
```

### Empirical Regime Classifier

Based on analysis of 470+ strategy/symbol combinations:

```python
from src.strategies.regime import (
    EmpiricalRegimeClassifier,
    EmpiricalRegimeState,
    VolatilityTrendRegime,
    get_symbols_for_regime,
    EMPIRICAL_REGIME_PERFORMANCE,
    MIDCAP_ALPHA_UNIVERSE,
)

# Detect regime from price data
classifier = EmpiricalRegimeClassifier()
regime = classifier.detect_regime(prices)  # pd.Series of prices

print(f"Regime: {regime.combined.value}")
print(f"Volatility: {'HIGH' if regime.volatility_high else 'LOW'} ({regime.vol_percentile:.0f}%ile)")
print(f"Trend: {'UP' if regime.uptrend else 'DOWN'} ({regime.trend_strength:+.2%})")

# Get strategy recommendations (sorted by expected Sharpe)
recommendations = classifier.get_strategy_recommendations(regime)
for rec in recommendations:
    print(f"{rec.strategy}: Sharpe={rec.expected_sharpe:.2f}, "
          f"Confidence={rec.confidence}, Size={rec.position_size_multiplier:.2f}x")

# Get strategies to avoid in current regime
avoid = classifier.get_avoid_strategies(regime)
print(f"Avoid: {avoid}")

# Get symbol universe for regime
symbols = get_symbols_for_regime(regime)
```

### Regime-Strategy Performance Matrix

| Strategy | High Vol + Up | High Vol + Down | Low Vol + Up | Low Vol + Down |
|----------|--------------|-----------------|--------------|----------------|
| rsi_14_30 | **1.54** | 0.70 | 1.05 | -0.18 |
| rsi_14_25 | **1.37** | 0.90 | 0.64 | 0.13 |
| mean_rev_20_2.0 | **1.08** | 0.84 | 0.38 | 0.62 |
| momentum_20 | 0.31 | AVOID (-1.90) | **2.48** | 1.67 |
| momentum_50 | 0.79 | AVOID (-2.41) | **2.19** | 0.32 |
| breakout_10 | **1.79** | AVOID (-0.60) | 0.88 | 0.90 |
| breakout_20 | **1.47** | AVOID (-1.03) | 0.65 | 0.73 |

**Key Findings:**
- Mid/small caps: 70/470 strategies beat B&H (14.9% win rate)
- Large caps: Only 20/520 beat B&H (3.8% win rate) - too efficient
- RSI/Mean-Rev: Best in HIGH VOL (bigger bounce opportunities)
- Momentum: Best in UPTREND (2.48 Sharpe), FAILS in downtrend (-1.90)
- Breakout: Best in UPTREND, AVOID in downtrend (false breakouts)

**Action by Regime:**
- HIGH_VOL_UPTREND: RSI, Breakout, Mean-Rev (position size 0.8x)
- HIGH_VOL_DOWNTREND: RSI, Mean-Rev ONLY; AVOID Momentum/Breakout (0.56x)
- LOW_VOL_UPTREND: Momentum strategies (1.0x)
- LOW_VOL_DOWNTREND: REDUCE EXPOSURE; Mean-Rev only (0.7x)

---

## PDT Framework

### Account Types
- **Budget** (< $25k): Min 2-day hold, max 3 day trades per 5 days
- **Margin** (>= $25k): No restrictions
- **Cash**: T+1 settlement

### PDT-Aware Backtesting

```python
from src.evaluation.validation import PDTAwareBacktest, AccountType

backtest = PDTAwareBacktest(
    account_type=AccountType.BUDGET,
    initial_capital=10000
)

# Compare holding periods
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10, 20])

for r in results:
    status = "OK" if r.pdt_compliant else "X"
    print(f"{status} {r.holding_period_days}d: Sharpe={r.sharpe_ratio:.2f}")
```

### Holding Period Optimization

```python
from src.evaluation.validation import HoldingPeriodOptimizer

optimizer = HoldingPeriodOptimizer()
optimizer.run_full_optimization(strategy_signals, strategy_prices)

# Best for budget account (PDT compliant)
budget_best = optimizer.get_best_for_budget_account()

# Best for full account (unrestricted)
full_best = optimizer.get_best_for_full_account()

# Export recommendations
df = optimizer.export_recommendations()
```

---

## Performance Metrics

```python
from src.evaluation import (
    # Return metrics
    total_return, cagr, sharpe_ratio, sortino_ratio, calmar_ratio,
    information_ratio, max_drawdown, win_rate, profit_factor,
    expectancy, rolling_sharpe, calculate_alpha, calculate_beta,
    performance_summary,
    # Risk metrics
    value_at_risk, conditional_var, max_drawdown_duration,
    downside_deviation, ulcer_index, omega_ratio, tail_ratio,
    skewness, kurtosis, stability_of_returns, risk_summary,
)

# Quick performance summary
perf = performance_summary(returns)
print(f"Sharpe: {perf['sharpe']:.2f}, Max DD: {perf['max_drawdown']:.1%}")

# Risk summary
risk = risk_summary(returns)
print(f"VaR 95%: {risk['var_95']:.1%}, CVaR: {risk['cvar_95']:.1%}")
```

---

## Statistical Testing

```python
from src.evaluation import (
    StatisticalTester, test_strategy_significance,
    compare_two_strategies, compute_bootstrap_ci,
    BootstrapCI, StrategySignificanceSuite,
)

# Comprehensive significance testing
tester = StatisticalTester()

# Test if Sharpe is significantly > 0
result = tester.test_sharpe_ratio(returns, null_sharpe=0)
print(f"Sharpe significant: {result.significant}, p={result.p_value:.4f}")

# Test alpha significance
alpha_test = tester.test_alpha(strategy_returns, benchmark_returns)

# Compare two strategies
comparison = compare_two_strategies(strat1_returns, strat2_returns)
print(f"Strategy 1 better: {comparison.first_better}, p={comparison.p_value:.4f}")

# Bootstrap confidence interval
ci = compute_bootstrap_ci(returns, statistic_func=sharpe_ratio)
print(f"Sharpe 95% CI: [{ci.lower:.2f}, {ci.upper:.2f}]")
```

---

## Performance Attribution

```python
from src.evaluation import (
    FactorModel, FactorExposure, AttributionResult,
    BrinsonAttribution, RollingFactorAnalysis,
)

# Factor model analysis
factor_model = FactorModel(factors=['MKT', 'SMB', 'HML', 'MOM'])
exposures = factor_model.fit(strategy_returns, factor_returns)
print(f"Alpha: {exposures.alpha:.4f}, R-squared: {exposures.r_squared:.2f}")

# Brinson attribution
brinson = BrinsonAttribution()
attribution = brinson.compute(portfolio_returns, benchmark_returns, weights)
print(f"Allocation: {attribution.allocation:.2%}, Selection: {attribution.selection:.2%}")

# Rolling factor analysis
rolling = RollingFactorAnalysis(window=252)
time_varying = rolling.fit(strategy_returns, factor_returns)
```

---

## Reporting

```python
from src.evaluation import (
    HTMLReportGenerator, ChartGenerator,
    generate_backtest_report, generate_comparison_report,
    generate_json_report, ReportConfig,
)

# Generate HTML report
report = generate_backtest_report(backtest_result, output_path="report.html")

# Compare multiple strategies
comparison = generate_comparison_report(
    results=[result1, result2, result3],
    names=["Strategy A", "Strategy B", "Strategy C"],
)

# JSON for programmatic use
json_report = generate_json_report(backtest_result)
```

---

## Workflow Integration Examples

### ComprehensiveResearcher

```python
# Bootstrap CI using evaluation module
from src.evaluation import BootstrapCI
bootstrap_ci = BootstrapCI(n_bootstrap=1000, confidence_level=0.95)
ci_result = bootstrap_ci.compute(returns.values, statistic_func=lambda x: sharpe_ratio(pd.Series(x)))

# Reality check for data snooping protection (runs when 5+ significant strategies)
from src.evaluation import reality_check
strategy_dict = {f"{r.strategy_name}/{r.symbol}": r.returns for r in significant}
rc_result = reality_check(strategy_dict, benchmark)

# Regime detection
from src.evaluation import detect_regimes, get_current_regime
regimes = detect_regimes(price_data)
current = get_current_regime(price_data)  # Returns {'success': True, 'data': {'regime': 'sideways', ...}}
```

### validate_strategy.py

```python
# Additional metrics from evaluation module
from src.evaluation import sortino_ratio, calmar_ratio, max_drawdown, win_rate
metrics['sortino'] = sortino_ratio(strategy_returns)
metrics['calmar'] = calmar_ratio(strategy_returns)
metrics['max_drawdown'] = max_drawdown(strategy_returns)
metrics['win_rate'] = win_rate(strategy_returns)

# Regime analysis
from src.evaluation import detect_regimes, evaluate_by_regime
regimes = detect_regimes(data)
regime_perf = evaluate_by_regime(strategy_returns, regimes)
```

### research_cycle.py

```python
# Reality check method available on ResearchCycleManager
manager.run_reality_check(strategy_returns_list, benchmark_returns)

# Regime detection method
manager.detect_current_regime(market_data)
```

---

*Last updated: 2026-01-05*
