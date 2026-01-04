# Quant Suite - Claude Code Reference

**Purpose**: Budget-friendly quantitative trading system ($200-$2,000 accounts)
**Last Updated**: 2026-01-04

---

## Quick Start Commands

```bash
# Daily Trading Pipeline
PYTHONPATH=. python scripts/run_daily.py --mode signals      # Generate signals only
PYTHONPATH=. python scripts/run_daily.py --mode paper        # Paper trading execution
PYTHONPATH=. python scripts/run_daily.py --mode live         # Live trading (requires approval)

# Research & Experimentation
PYTHONPATH=. python scripts/full_research_cycle.py           # Full research cycle (all strategies/symbols)
PYTHONPATH=. python scripts/full_research_cycle.py --quick   # Quick research (reduced scope)
PYTHONPATH=. python -m workflows.research.autonomous_loop    # Autonomous research
PYTHONPATH=. python scripts/run_experiments.py               # Run experiments

# Monitoring
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard  # Portfolio dashboard

# Testing
PYTHONPATH=. python -m pytest tests/ -v                      # Run all tests
PYTHONPATH=. python scripts/test_research_system.py          # Test research system

# Validation & Reports
PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM
PYTHONPATH=. python scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM
PYTHONPATH=. python scripts/generate_report.py --type strategy --name bollinger_reversal --symbol QCOM
```

---

## Claude Code Skills

The quant suite includes 7 specialized skills for different workflow stages:

| Skill | Purpose | Trigger |
|-------|---------|---------|
| `/research` | Run research cycles, test strategies | "research strategies", "find alpha" |
| `/critic` | Safety validation, detect artificial performance | "validate strategy", "check for bugs" |
| `/monitor` | Trading performance monitoring | "check portfolio", "monitor trades" |
| `/promote` | Move strategies to production | "promote to paper", "deploy strategy" |
| `/brainstorm` | Feature and strategy ideation | "brainstorm features", "new ideas" |
| `/validate` | Full validation suite | "run validation", "test strategy" |
| `/report` | Generate documentation | "generate report", "create summary" |

### Skill Workflow

```
1. /brainstorm  →  Generate feature/strategy ideas
       ↓
2. /research    →  Test hypotheses, run experiments
       ↓
3. /validate    →  Full validation suite (MCPT, walk-forward, etc.)
       ↓
4. /critic      →  Safety checks (lookahead, overfitting, etc.)
       ↓
5. /promote     →  Move to paper trading
       ↓
6. /monitor     →  Track live performance
       ↓
7. /report      →  Document results
```

### Using Skills

Skills are automatically triggered based on your request, or invoke directly:

```
# Research
"Run a full research cycle across all strategies"
"Test bollinger_reversal on semiconductor stocks"

# Validation
"Validate the bollinger_reversal strategy on QCOM"
"Run critic validation to check for bugs"

# Monitoring
"Check current portfolio status"
"Show trading performance for last 30 days"

# Promotion
"Promote bollinger_reversal/QCOM to paper trading"
"List strategies ready for production"

# Reports
"Generate a strategy report for bollinger_reversal on QCOM"
"Create a research cycle summary"
```

---

## Architecture Overview

```
[Data Layer]          [Feature Layer]        [Strategy Layer]       [Execution Layer]
    |                      |                      |                      |
 yfinance  ─────────► FeatureComputer ────► Strategy.generate() ──► RiskLimits
 SEC filings            (50+ features)           │                      │
 News RSS                  │                     │                      ▼
 Reddit                    ▼                     ▼                 OrderExecutor
    │              enriched DataFrame       Signal objects              │
    │                      │                     │                      ▼
    └──────────────────────┴─────────────────────┴─────────────► Alpaca Broker
```

**Key Design Principles**:
- Look-ahead bias prevention (features computed with proper date boundaries)
- PDT compliance (min 2-day hold, 3 day-trades per 5 days)
- 25% max position size, 5% stop-loss, 10% take-profit defaults
- MCPT validation required (p < 0.05) before production trading

---

## Key File Locations

### Configuration
| File | Purpose |
|------|---------|
| `config/strategies/validated_strategies.yaml` | **Strategy definitions & schedule** (source of truth) |
| `config/credentials.yaml` | Alpaca API credentials |

### Daily Pipeline
| File | Purpose |
|------|---------|
| `scripts/run_daily.py` | Main daily runner with scheduler |
| `src/execution/pipeline/daily_signals.py` | Signal generation pipeline |
| `src/execution/pipeline/order_executor.py` | Order execution |
| `src/execution/broker/alpaca.py` | Alpaca broker integration |

### Feature System
| File | Purpose |
|------|---------|
| `src/data/feature_engineering/feature_registry.py` | **50+ feature definitions** |
| `src/data/feature_engineering/feature_store.py` | Feature caching |
| `src/data/features.py` | Legacy feature utilities |

### Strategy Framework
| File | Purpose |
|------|---------|
| `src/strategies/base.py` | BaseStrategy class |
| `src/core/strategy_config.py` | Config loader with dataclasses |
| `src/core/signal.py` | Signal object definition |

### Research System
| File | Purpose |
|------|---------|
| `workflows/research/knowledge_base.py` | Experiment tracking & patterns |
| `workflows/research/autonomous_loop.py` | Autonomous research loop |
| `workflows/research/experiment_runner.py` | Experiment execution |
| `workflows/research/hypothesis_generator.py` | Hypothesis generation |

### Validation
| File | Purpose |
|------|---------|
| `src/evaluation/validation/mcpt.py` | Monte Carlo Permutation Test |
| `src/evaluation/validation/walk_forward.py` | Walk-forward validation |
| `src/evaluation/backtest/engine.py` | Vectorized backtesting |

---

## Strategy & Model Testing Framework

The evaluation system (`src/evaluation/`) provides comprehensive testing capabilities:

### Backtesting Engine

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

### Statistical Validation Suite

**MCPT (Monte Carlo Permutation Test):**
```python
from src.evaluation import mcpt_test, mcpt_walk_forward, MCPTAnalyzer

# Basic significance test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {result.p_value:.4f}, Significant: {result.significant}")

# Combined with walk-forward
wf_mcpt = mcpt_walk_forward(strategy, data, n_splits=5, n_permutations=500)
```

**Walk-Forward Validation:**
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

**Hypothesis Testing (Data Snooping Protection):**
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

**Cross-Validation:**
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

**Regime Analysis:**
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

**Multi-Level Holdout:**
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

**PDT Framework:**
```python
from src.evaluation import (
    PDTAwareBacktest, HoldingPeriodOptimizer, PDTTracker,
    AccountType, get_pdt_holding_recommendation,
)

# PDT-compliant backtest
backtest = PDTAwareBacktest(account_type=AccountType.BUDGET, initial_capital=10000)
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10, 20])

# Optimize holding period
optimizer = HoldingPeriodOptimizer()
optimizer.run_full_optimization(signals, prices)
budget_rec = optimizer.get_best_for_budget_account()
print(f"Recommended hold: {budget_rec.holding_period_days} days")
```

### Performance Metrics

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

### Statistical Testing

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

### Performance Attribution

```python
from src.evaluation import (
    FactorModel, FactorExposure, AttributionResult,
    BrinsonAttribution, RollingFactorAnalysis,
)

# Factor model analysis
factor_model = FactorModel(factors=['MKT', 'SMB', 'HML', 'MOM'])
exposures = factor_model.fit(strategy_returns, factor_returns)
print(f"Alpha: {exposures.alpha:.4f}, R²: {exposures.r_squared:.2f}")

# Brinson attribution
brinson = BrinsonAttribution()
attribution = brinson.compute(portfolio_returns, benchmark_returns, weights)
print(f"Allocation: {attribution.allocation:.2%}, Selection: {attribution.selection:.2%}")

# Rolling factor analysis
rolling = RollingFactorAnalysis(window=252)
time_varying = rolling.fit(strategy_returns, factor_returns)
```

### Reporting

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

### Risk Management
| File | Purpose |
|------|---------|
| `src/risk/limits.py` | Risk limit checks |
| `src/risk/position_sizing.py` | Position sizers (FixedFractional, Kelly) |

---

## Validated Strategies (Production Ready)

| Strategy | Primary Symbol | Sharpe | p-value | Class |
|----------|---------------|--------|---------|-------|
| insider_technical | QQQ | **1.23** | 0.00 | `InsiderTechnicalStrategy` |
| volatility_breakout | AMD | 0.73 | 0.02 | `VolatilityBreakoutStrategy` |
| rsi_reversal | IWM | 0.61 | 0.04 | `RSIReversalStrategy` |

**Validation criteria**: MCPT p < 0.05, out-of-sample Sharpe > 0.5

### Strategy Universes
- **insider_technical**: QQQ, MSFT, AAPL, GOOGL, XLK, AMAT, SPY
- **rsi_reversal**: IWM, SPY, QQQ, DIA
- **volatility_breakout**: AMD, NVDA, MRVL, MU, AVGO

---

## Feature Registry Summary

**Total Features**: 50+ registered

| Category | Count | Examples |
|----------|-------|----------|
| TECHNICAL | 11 | rsi, bollinger_bands, macd, atr, volume_features |
| SENTIMENT | 4 | news_sentiment, social_sentiment |
| ALTERNATIVE | 4 | filing_sentiment_10k, mda_tone |
| FLOW | 5 | options_put_call, insider_activity |
| RISK | 4 | beta, drawdown, tail_risk |
| REGIME | 3 | market_regime, volatility_regime |
| EMBEDDING | 4 | narrative_centroid_distance, topic_emergence |

**Feature computation**:
```python
from src.data.feature_engineering.feature_registry import FeatureComputer

computer = FeatureComputer()
features = computer.compute_feature("rsi", df)  # Returns DataFrame with rsi_7, rsi_14, rsi_21
all_tech = computer.compute_all_technical(df)   # All technical features
```

---

## Data Flow: Signal to Execution

```
1. Data Fetch (07:00 ET)
   └── yfinance.download(symbols, period="60d")

2. Feature Computation
   └── FeatureComputer.compute_feature(feature_name, df)
       └── Returns enriched DataFrame with feature columns

3. Signal Generation
   └── strategy.generate_signals(data) -> list[Signal]
       └── Signal(symbol, direction, strength, confidence, strategy_name)

4. Risk Filtering
   └── RiskLimits.check_signal(signal, portfolio)
       ├── Position size check (max 25%)
       ├── PDT compliance (min 2-day hold)
       ├── Drawdown check (max 15%)
       └── Daily loss check (max 5%)

5. Order Execution (09:35 ET)
   └── OrderExecutor.execute(approved_signals)
       └── AlpacaBroker.submit_order(order)

6. EOD Snapshot (16:05 ET)
   └── Record portfolio state, P&L, positions
```

---

## Alpaca Configuration

**Credentials file**: `config/credentials.yaml`
```yaml
alpaca:
  api_key: PK7HVRLPGKWQS7S4FTQKHTZA3C
  secret_key: [REDACTED]
  paper: true
```

**Paper account**: $100,000 balance
**API docs**: https://docs.alpaca.markets/

---

## Schedule Configuration

Defined in `config/strategies/validated_strategies.yaml`:

| Event | Time (ET) | Days |
|-------|-----------|------|
| Signal Generation | 07:00 | Mon-Fri |
| Execution | 09:35 | Mon-Fri |
| EOD Snapshot | 16:05 | Mon-Fri |
| Weekly Review | 18:00 | Sunday |

---

## Common Tasks

### Add a New Strategy
1. Create strategy class inheriting from `BaseStrategy` (or define in `scripts/run_daily.py`)
2. Implement `generate_signals(data: dict[str, pd.DataFrame]) -> list[Signal]`
3. Add `required_features` class attribute
4. Run backtest with `VectorizedBacktest`
5. Validate with `mcpt_test()` (must get p < 0.05)
6. Add to `config/strategies/validated_strategies.yaml`

### Run a Backtest
```python
from src.evaluation.backtest.engine import VectorizedBacktest

backtest = VectorizedBacktest(
    strategy=my_strategy,
    initial_capital=10000,
    transaction_cost_bps=10
)
results = backtest.run(data)
print(f"Sharpe: {results.sharpe_ratio:.2f}")
```

### Validate a Strategy (MCPT)
```python
from src.evaluation.validation.mcpt import mcpt_test

result = mcpt_test(
    strategy_returns=strategy_returns,
    benchmark_returns=benchmark_returns,
    n_permutations=1000
)
print(f"p-value: {result.p_value:.4f}")
```

### Check PDT Compliance
```python
from src.risk.limits import check_pdt_compliance

can_trade, remaining = check_pdt_compliance(
    recent_trades=trades_last_5_days,
    max_day_trades=3
)
```

---

## Knowledge Base

**Location**: `workflows/research/knowledge_base.py`

Tracks:
- Successful experiments & strategies
- Failed hypotheses (avoid repeating)
- Detected patterns
- Performance baselines

```python
from workflows.research.knowledge_base import KnowledgeBase

kb = KnowledgeBase()
kb.add_successful_strategy(strategy_name, params, metrics)
kb.add_failed_hypothesis(hypothesis, reason)
patterns = kb.get_detected_patterns()
```

---

## Output Directories

| Path | Contents |
|------|----------|
| `/home/nock/quant_results/` | All trading/research outputs |
| `/home/nock/quant_results/daily_runs/` | Daily signal/execution JSON |
| `/home/nock/quant_results/backtests/` | Backtest results |
| `/home/nock/quant_results/experiments/` | Research experiments |

---

## Testing

```bash
# Unit tests
PYTHONPATH=. python -m pytest tests/unit/ -v

# Integration tests
PYTHONPATH=. python -m pytest tests/integration/ -v

# Specific test files
PYTHONPATH=. python -m pytest tests/unit/test_mcpt.py -v
PYTHONPATH=. python -m pytest tests/unit/test_hypothesis_testing.py -v
```

---

## Error Handling Notes

- **Empty signals**: Check if market is closed or no signals meet thresholds
- **Alpaca connection**: Verify credentials in `config/credentials.yaml`
- **Feature computation**: Some features need sufficient lookback (60+ days)
- **PDT violations**: System enforces 2-day min hold for accounts < $25k

---

## New Integration Components

### Strategy Promoter
**Location**: `workflows/promotion/strategy_promoter.py`

Semi-automatic promotion from research to production:
```bash
# Scan for candidates
PYTHONPATH=. python -m workflows.promotion.strategy_promoter scan

# List pending
PYTHONPATH=. python -m workflows.promotion.strategy_promoter list

# Approve and promote
PYTHONPATH=. python -m workflows.promotion.strategy_promoter approve all
PYTHONPATH=. python -m workflows.promotion.strategy_promoter promote
```

### Knowledge Base Feedback Loop
The daily runner now records to knowledge base:
- Live signals generated
- Execution results (fill price, slippage)
- Daily summaries

### Unified StrategySpec
**Location**: `src/core/strategy_spec.py`

Bridge between research and production:
```python
from src.core.strategy_spec import StrategySpec

# From experiment
spec = StrategySpec.from_experiment(
    strategy_name='my_strategy',
    symbol='AAPL',
    params={'rsi_period': 14},
    train_sharpe=1.5,
    val_sharpe=1.2,
    p_value=0.01,
)

# To YAML config
yaml_str = spec.to_yaml()
```

---

## Research Protocol (Claude Code Workflow)

### Starting a Research Session
```python
from workflows.research.research_protocol import ResearchProtocol, ResearchFocus

protocol = ResearchProtocol()
session = protocol.start_session(focus=ResearchFocus.STRATEGY_DEVELOPMENT)

# Get phase-specific guidance
print(protocol.get_phase_prompt())
print(protocol.get_focus_guidance())
```

### Research Phases
1. **Gap Analysis** - Identify under-explored areas
2. **Hypothesis Generation** - Create testable hypotheses
3. **Experiment Design** - Define experiments
4. **Validation** - Run and validate experiments
5. **Insight Extraction** - Record learnings

### Quick Research Commands
```bash
# Comprehensive strategy research
PYTHONPATH=. python -c "
from workflows.research.comprehensive_researcher import ComprehensiveResearcher
researcher = ComprehensiveResearcher()
results = researcher.run_cycle(universes=['tech_mega', 'semiconductors'], strategies=['bollinger_reversal', 'momentum'])
"

# Feature discovery
PYTHONPATH=. python -c "
from src.data.feature_engineering import FeatureDiscoveryEngine
engine = FeatureDiscoveryEngine()
report = engine.generate_discovery_report()
print(f'Total ideas: {report[\"total_ideas\"]}')"
```

### Session Tracker (Cross-Session Insights)
```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()

# Log an insight
tracker.log_insight(
    title="Bollinger reversal works on semiconductors",
    description="QCOM, MU, MRVL all show Sharpe > 2.0",
    category="strategy",
    evidence={"sharpe": 2.5, "p_value": 0.01},
    tags=["bollinger", "semiconductors"]
)

# Log an experiment
tracker.log_experiment(
    strategy="bollinger_reversal",
    symbol="AVGO",
    params={"period": 20, "num_std": 2.0},
    result="success",
    sharpe=1.8,
    p_value=0.02
)

# Search past insights
insights = tracker.search_insights(category="strategy", min_confidence=0.6)
```

---

## Alternative Data Sources

### Google Trends (Retail Attention)
```python
from src.data.sources.alternative import GoogleTrendsSource

trends = GoogleTrendsSource()
attention = trends.get_retail_attention('TSLA')

print(f"Z-score: {attention.zscore:.2f}")
print(f"Signal: {attention.signal}")  # 'high_attention', 'low_attention', 'normal'
print(f"Contrarian buy: {attention.is_contrarian_buy()}")
```

### Short Interest (Squeeze Detection)
```python
from src.data.sources.alternative import ShortInterestSource

shorts = ShortInterestSource()
data = shorts.fetch_short_interest('GME')

print(f"Short % of float: {data.short_percent_of_float:.1%}")
print(f"Days to cover: {data.short_ratio:.1f}")
print(f"Squeeze candidate: {data.is_squeeze_candidate()}")

# Find squeeze candidates
candidates = shorts.find_squeeze_candidates(['AMC', 'GME', 'BBBY'], min_short_pct=0.15)
```

### FinBERT Sentiment
```python
from src.strategies.alternative.sentiment import SentimentAnalyzer

# Force transformer mode (no lexicon fallback)
analyzer = SentimentAnalyzer(model_name='finbert', force_transformer=True)
score, confidence = analyzer.analyze("Stock surged on strong earnings")
print(f"Sentiment: {score:.2f}, Confidence: {confidence:.2f}")
```

---

## PDT Framework (Budget Accounts)

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
    status = "✓" if r.pdt_compliant else "✗"
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

## Feature Engineering System

### Feature Discovery
```python
from src.data.feature_engineering import FeatureDiscoveryEngine, FeatureDomain

engine = FeatureDiscoveryEngine(existing_features=['rsi', 'macd'])

# Get domain-specific ideas
ideas = engine.discover_from_domain(FeatureDomain.SENTIMENT)

# Get literature-inspired ideas
lit_ideas = engine.discover_from_literature()

# Full discovery report
report = engine.generate_discovery_report()
```

### Feature Interactions
```python
from src.data.feature_engineering import FeatureInteractionGenerator

generator = FeatureInteractionGenerator()

# Generate all interactions
result = generator.generate_interactions(df, feature_columns=['rsi', 'momentum', 'volatility'])

# Auto-discover best interactions by IC
top_interactions = generator.auto_discover_interactions(df, forward_returns, top_n=20)
```

### Feature Stability Monitoring
```python
from src.data.feature_engineering import FeatureStabilityMonitor

monitor = FeatureStabilityMonitor()

# Analyze single feature
report = monitor.analyze_feature(df, 'rsi_14', forward_returns)
print(f"IC: {report.ic_mean:.3f}, Grade: {report.grade}, Stable: {report.is_stable}")

# Full portfolio report
portfolio = monitor.generate_stability_report(df, ['rsi_14', 'macd', 'momentum'], forward_returns)
```

---

## Text Research Framework (`src/text_research/`)

Point-in-time safe text-based alpha research system:

### Core Components

| Module | Description |
|--------|-------------|
| `corpus.py` | `TextCorpus` - PIT-safe document storage |
| `embedding_engine.py` | `EmbeddingEngine` - Multi-model embeddings |
| `feature_extractor.py` | `TextFeatureExtractor` - 7 text features |
| `signal_generator.py` | `TextSignalGenerator` - 6 signal strategies |
| `backtest.py` | `TextBacktester` - Walk-forward with proper temporal alignment |
| `ingestors/news.py` | `NewsIngestor` - RSS and API news |
| `ingestors/sec.py` | `SECIngestor` - 10-K, 10-Q, 8-K filings |

### Text Features

| Feature | Description | Lookback |
|---------|-------------|----------|
| `text_sentiment_mean` | Average sentiment score | 7 days |
| `text_sentiment_momentum` | Change in sentiment | 14 days |
| `text_sentiment_volatility` | Sentiment std dev | 14 days |
| `text_mention_velocity` | Document count change | 7 days |
| `text_narrative_shift` | Centroid distance | 30 days |
| `text_semantic_novelty` | Novelty score | 30 days |
| `text_topic_concentration` | Embedding dispersion | 30 days |

### Signal Strategies

| Strategy | Description |
|----------|-------------|
| `sentiment_mean` | Long positive, short negative sentiment |
| `sentiment_momentum` | Long improving, short deteriorating |
| `narrative_shift` | Trade on narrative changes |
| `attention_velocity` | Trade on attention spikes |
| `contrarian_sentiment` | Bet against extreme sentiment |
| `combined` | Multi-factor weighted |

### Usage

```python
from src.text_research import (
    TextCorpus, EmbeddingEngine, TextFeatureExtractor,
    TextSignalGenerator, TextBacktester
)
from src.text_research.ingestors import NewsIngestor, SECIngestor
from datetime import date

# Initialize components
corpus = TextCorpus()
embeddings = EmbeddingEngine()
features = TextFeatureExtractor(corpus, embeddings)
signals = TextSignalGenerator()
backtester = TextBacktester(corpus, embeddings, features)

# Ingest text data
news_ingestor = NewsIngestor(corpus)
news_ingestor.ingest_rss_feeds(symbols=["NVDA", "AMD", "QCOM"])

sec_ingestor = SECIngestor(corpus)
sec_ingestor.ingest_10k(symbols=["NVDA", "AMD"])

# Run walk-forward backtest
result = backtester.run_walk_forward(
    signal_generator=signals.create_signal_generator_fn("combined"),
    symbols=["NVDA", "AMD", "QCOM"],
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31),
    train_window=252,
    test_window=63
)

# Check for lookahead bias
is_clean = backtester.validate_no_lookahead()
print(f"Lookahead-free: {is_clean}")

# Print results
for fold in result:
    print(f"Train Sharpe: {fold.train_sharpe:.2f}, Test Sharpe: {fold.test_sharpe:.2f}")
```

### Key Design Principles

- **signal_delay=1**: Same-day text generates next-day signals (no lookahead)
- **Point-in-time safe**: All queries respect document timestamps
- **Walk-forward validation**: Proper temporal splits
- **Online learning**: Daily embedding updates without full recompute

---

## Latest Validated Strategies (2026-01-03)

From comprehensive research cycle:

| Strategy | Symbol | Sharpe | p-value | Status |
|----------|--------|--------|---------|--------|
| bollinger_reversal | QCOM | 3.14 | 0.007 | **Production Ready** |
| bollinger_reversal | MU | 2.93 | 0.007 | **Production Ready** |
| bollinger_reversal | MRVL | 2.71 | 0.017 | **Production Ready** |
| bollinger_reversal | IWM | 2.34 | 0.040 | **Production Ready** |
| momentum | AMD | 2.11 | 0.047 | **Production Ready** |

**Key Finding**: Bollinger band reversal shows consistent edge on high-beta semiconductor stocks.

---

## Workflow Integration Status

The evaluation module functions are now integrated into the main workflows:

### Completed Integrations ✓

| Workflow | Functions Integrated | Status |
|----------|---------------------|--------|
| **ComprehensiveResearcher** | `BootstrapCI`, `reality_check`, `detect_regimes`, `evaluate_by_regime`, `get_current_regime`, all metrics | ✓ Complete |
| **validate_strategy.py** | `BootstrapCI`, `detect_regimes`, `evaluate_by_regime`, `get_current_regime`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `max_drawdown`, `win_rate` | ✓ Complete |
| **research_cycle.py** | `reality_check`, `stepwise_spa`, `detect_regimes`, `get_current_regime` | ✓ Complete |

### Usage Examples

**ComprehensiveResearcher** (`workflows/research/comprehensive_researcher.py`):
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

**validate_strategy.py** (`scripts/validate_strategy.py`):
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

**research_cycle.py** (`workflows/orchestration/research_cycle.py`):
```python
# Reality check method available on ResearchCycleManager
manager.run_reality_check(strategy_returns_list, benchmark_returns)

# Regime detection method
manager.detect_current_regime(market_data)
```

### Remaining Integration Opportunities

| Function | Module | Use Case | Priority |
|----------|--------|----------|----------|
| `combinatorial_purged_cv()` | purged_cv | More robust cross-validation | Medium |
| `FactorModel` | attribution | Factor exposure analysis | Low |
| `generate_backtest_report()` | reporting | Automated HTML reports | Low |

### Other Planned Features

1. **Features computed fresh each run**: No persistent feature cache (DuckDB planned)
2. **Earnings calls NLP**: Transcript fetching and analysis (planned)
3. **Additional alt data**: Job postings, web traffic, patents, dark pool (lower priority)

**Full plan**: See `/home/nock/.claude/plans/curried-dazzling-hopcroft.md`

---

## Claude Code Research Workflow Commands

Use these prompts to trigger research workflows:

### Full Research Cycle
```
Run a full research cycle across all strategies and features
```
This will:
- Inventory all 11 strategies, 45 symbols, 36 features
- Collect alternative data (Google Trends, Short Interest)
- Test all strategy-symbol combinations with MCPT validation
- Optimize PDT holding periods for budget accounts
- Generate insights and next research leads
- Save reports to `/home/nock/quant_results/full_research/`

### Quick Research
```
Run a quick research cycle on tech and semiconductor stocks
```
This runs a reduced scope (3 strategies, 2 universes) for faster iteration.

### Follow-Up Research
```
Follow up on the research leads from the last cycle and test the top 5 recommendations
```

### Sector Expansion
```
Expand research to financials and healthcare sectors using mean reversion and volatility breakout strategies
```

### Strategy Promotion
```
Promote bollinger_reversal on QCOM to paper trading with 10-day hold period
```

---

## Latest Research Results (2026-01-03)

**Experiments**: 39 run, 4 significant (p<0.05), 4 production-ready
**Best Strategy**: bollinger_reversal on semiconductors (QCOM, MU, MRVL)
**Key Insight**: Mean reversion works on high-beta cyclical stocks

**Top Research Leads**:
1. Extend bollinger_reversal to DIA (priority: 0.8)
2. Test mean reversion on high-vol stocks: AMZN, META, NVDA (priority: 0.7)
3. Explore financials: JPM, GS, V, MA (priority: 0.6)

**Alternative Data Signals**:
- GME: Squeeze candidate (16.6% short, 10.2 days to cover)
- All tech: Below-average retail attention (contrarian positive)

---

## Claude Code Agents (10 Total)

The quant suite uses 10 specialized Claude Code agents for autonomous operation, organized into three tracks:

### Track 1: Novel Pattern Discovery

| Agent | Purpose | Config |
|-------|---------|--------|
| **macro-research-agent** | Geopolitical & macro factor analysis | `.claude/agents/macro-research-agent.md` |
| **news-analyst-agent** | Event-driven news analysis | `.claude/agents/news-analyst-agent.md` |
| **regime-detector-agent** | Market regime classification | `.claude/agents/regime-detector-agent.md` |

### Track 2: Strategy Testing

| Agent | Purpose | Config |
|-------|---------|--------|
| **research-agent** | Comprehensive strategy research | `.claude/agents/research-agent.md` |
| **research-worker-agent** | Parallelizable sector research | `.claude/agents/research-worker-agent.md` |

### Track 3: Text-Based Alpha

| Agent | Purpose | Config |
|-------|---------|--------|
| **text-research-agent** | Text-based alpha discovery | `.claude/agents/text-research-agent.md` |

### Support Agents

| Agent | Purpose | Config |
|-------|---------|--------|
| **critic-agent** | Safety validation and bias detection | `.claude/agents/critic-agent.md` |
| **monitor-agent** | Portfolio and trading oversight | `.claude/agents/monitor-agent.md` |
| **brainstorm-agent** | Feature and strategy ideation | `.claude/agents/brainstorm-agent.md` |
| **orchestrator-agent** | Multi-agent workflow coordination | `.claude/agents/orchestrator-agent.md` |

### Agent Python Templates

Located in `/home/nock/projects/quant_suite/agents/`:

```python
from agents import ResearchAgent, CriticAgent, MonitorAgent, BrainstormAgent, OrchestratorAgent

# Research agent
prompt = ResearchAgent.get_quick_research_prompt(
    universes=["tech_mega", "semiconductors"],
    strategies=["bollinger_reversal", "momentum"]
)

# Critic validation
prompt = CriticAgent.get_prompt(strategy="bollinger_reversal", symbol="QCOM")

# Monitor check
prompt = MonitorAgent.get_prompt(focus="health")

# Brainstorm session
prompt = BrainstormAgent.get_prompt(focus="alternative")

# Orchestrator for multi-agent coordination
prompt = OrchestratorAgent.get_dual_track_prompt(sector="semiconductors")
```

### Standard Workflows

**Full Triple-Track Research Cycle**:
```
1. [PARALLEL] Track 1: macro-research, news-analyst, regime-detector
2. [PARALLEL] Track 2: research-workers (by sector)
3. [PARALLEL] Track 3: text-research-agent
4. [SEQUENTIAL] Aggregate results
5. [SEQUENTIAL] critic-agent validates top strategies
6. [SEQUENTIAL] Generate daily review
```

**Dual-Track Research** (simpler):
```
1. regime-detector-agent → Get regime and recommendations
2. [PARALLEL] 2-3x research-worker-agents
3. critic-agent → Validate significant findings
```

**Daily Operations**:
```
1. monitor-agent → System health check
2. monitor-agent → Performance review
3. (Weekly) brainstorm-agent → New ideas
4. research-agent → Follow up on leads
```

### Spawning Agents via Task Tool

```python
# Single agent
Task(
    subagent_type="general-purpose",
    prompt="Use research-agent to test bollinger_reversal on semiconductors",
    description="Research cycle"
)

# Parallel agents (all in one message)
Task(prompt="Use macro-research-agent for semiconductors", description="Macro: semis")
Task(prompt="Use news-analyst-agent for semiconductors", description="News: semis")
Task(prompt="Use regime-detector-agent", description="Regime detection")
Task(prompt="Use research-worker-agent for semiconductors", description="Research: semis")
```

---

## Output Directories

| Path | Contents |
|------|----------|
| `/home/nock/quant_results/comprehensive_research/` | Research cycle results |
| `/home/nock/quant_results/validation_reports/` | Strategy validation JSON |
| `/home/nock/quant_results/critic_reports/` | Critic validation JSON |
| `/home/nock/quant_results/strategy_reports/` | Strategy documentation (Markdown) |
| `/home/nock/quant_results/research_reports/` | Research summaries |
| `/home/nock/quant_results/performance_reports/` | Trading performance |
| `/home/nock/quant_results/promotions/` | Promotion records |
| `/home/nock/quant_results/research_tracker/` | Session tracker data |
| `/home/nock/quant_results/agent_runs/` | Agent execution logs |
