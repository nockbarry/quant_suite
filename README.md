# Quant Suite

**Autonomous Quantitative Trading System with Claude Code Integration**

A comprehensive quantitative trading platform designed for budget-friendly accounts ($200-$2,000+) with full PDT compliance, Claude Code agents for autonomous research, and text-based alpha discovery.

## Features

- **Triple-Track Research System**: Novel pattern discovery, traditional strategy testing, and text-based alpha research running in parallel
- **PDT Compliance**: Automatic handling of Pattern Day Trader rules for accounts under $25k
- **Claude Code Integration**: 10 specialized agents and 7 skills for autonomous operation
- **Text Research Framework**: Sentiment analysis, embeddings, and backtesting with proper point-in-time methodology
- **50+ Technical Features**: RSI, MACD, Bollinger Bands, and more with proper lookback handling
- **MCPT Validation**: Monte Carlo Permutation Testing to ensure statistical significance
- **Paper/Live Trading**: Alpaca broker integration with risk management

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/quant_suite.git
cd quant_suite

# Install dependencies
pip install -r requirements.txt

# Optional: Install sentence-transformers for real embeddings
pip install sentence-transformers

# Set up Alpaca credentials
cp config/credentials.yaml.example config/credentials.yaml
# Edit config/credentials.yaml with your API keys
```

## Quick Start

```bash
# Run a research cycle
PYTHONPATH=. python3 scripts/full_research_cycle.py --quick

# Paper trading
PYTHONPATH=. python3 scripts/run_daily.py --mode paper

# Monitor portfolio
PYTHONPATH=. python3 -m src.execution.monitoring.cli_dashboard
```

## Project Structure

```
quant_suite/
├── .claude/                    # Claude Code configuration
│   ├── agents/                 # Agent definitions (10 agents)
│   └── skills/                 # Skill definitions (7 skills)
├── agents/                     # Python agent prompt templates
├── config/                     # Configuration files
│   ├── credentials.yaml        # API credentials
│   ├── orchestration.yaml      # Agent orchestration config
│   └── strategies/             # Strategy pools and validated strategies
├── scripts/                    # CLI scripts for daily operations
├── src/                        # Core source code
│   ├── agents/                 # Runtime agent classes
│   ├── core/                   # Core data types (Signal, Order, Position)
│   ├── data/                   # Data sources and feature engineering
│   ├── evaluation/             # Backtesting and validation
│   ├── execution/              # Order execution and monitoring
│   ├── risk/                   # Risk management
│   ├── strategies/             # Trading strategies
│   └── text_research/          # Text-based alpha framework
├── workflows/                  # High-level workflows
│   ├── orchestration/          # Multi-agent coordination
│   ├── research/               # Research automation
│   ├── review/                 # Daily review dashboard
│   └── pdt/                    # PDT strategy pools
├── tests/                      # Unit and integration tests
└── data/                       # Data storage directories
```

## Core Components

### Data Layer (`src/data/`)

| Module | Description |
|--------|-------------|
| `sources/yahoo.py` | Yahoo Finance price data |
| `sources/alternative/` | News, Google Trends, Short Interest, Reddit |
| `feature_engineering/` | 50+ features with proper lookback handling |
| `storage/` | Parquet and ChromaDB vector storage |

### Strategy Layer (`src/strategies/`)

| Module | Description |
|--------|-------------|
| `traditional/` | Mean reversion, trend following, factor models |
| `alternative/` | Sentiment, embeddings, narrative momentum |
| `regime/` | Market regime classification |
| `ml/` | Classical ML and deep learning strategies |

### Evaluation Layer (`src/evaluation/`)

| Module | Description |
|--------|-------------|
| `backtest/engine.py` | Vectorized backtesting with costs |
| `validation/mcpt.py` | Monte Carlo Permutation Test |
| `validation/walk_forward.py` | Walk-forward validation |
| `validation/pdt_framework.py` | PDT-aware holding period optimization |

## Strategy & Model Testing Framework

The evaluation system provides comprehensive testing capabilities across multiple categories:

### Backtesting Engine (`src/evaluation/backtest/`)

| Class/Function | Description |
|----------------|-------------|
| `VectorizedBacktest` | High-performance vectorized backtesting engine |
| `BacktestConfig` | Configuration for backtest parameters |
| `BacktestResult` | Comprehensive results with metrics |
| `run_backtest()` | Convenience function for quick backtests |
| `BudgetExecutionModel` | Simulates budget account constraints |
| `ExecutionModel` | Realistic fill simulation |

**Cost Models:**
| Model | Description |
|-------|-------------|
| `PercentageCost` | Fixed percentage transaction costs |
| `TieredCost` | Volume-based tiered costs |
| `SpreadCost` | Bid-ask spread modeling |
| `MarketImpactCost` | Price impact from order size |
| `estimate_slippage()` | Slippage estimation utility |

### Statistical Validation (`src/evaluation/validation/`)

**MCPT (Monte Carlo Permutation Test):**
| Class/Function | Description |
|----------------|-------------|
| `mcpt_test()` | Primary significance test for strategies |
| `mcpt_walk_forward()` | Combined MCPT with walk-forward |
| `MCPTAnalyzer` | Detailed permutation analysis |
| `BarPermuter` | Bar-level return permutation |
| `verify_permutation_properties()` | Validates permutation correctness |

**Walk-Forward Validation:**
| Class/Function | Description |
|----------------|-------------|
| `run_walk_forward()` | Out-of-sample walk-forward testing |
| `WalkForwardOptimizer` | Parameter optimization with validation |
| `ParameterOptimizer` | Grid/random search optimization |
| `WalkForwardSplitter` | Time-series aware data splitting |
| `walk_forward_summary()` | Summary statistics for WF results |

**Hypothesis Testing:**
| Class/Function | Description |
|----------------|-------------|
| `WhiteRealityCheck` | White's Reality Check for data snooping |
| `HansenSPA` | Hansen's Superior Predictive Ability test |
| `StepwiseSPA` | Stepwise model confidence set |
| `BlockBootstrap` | Block bootstrap for time series |
| `reality_check()` | Quick reality check function |
| `spa_test()` | SPA test convenience function |
| `stepwise_spa()` | Stepwise SPA convenience function |
| `multiple_testing_summary()` | Summary of multiple testing corrections |

**Cross-Validation:**
| Class/Function | Description |
|----------------|-------------|
| `PurgedKFoldCV` | K-fold with purging for lookahead prevention |
| `CombinatorialPurgedCV` | Combinatorial purged cross-validation |
| `TimeSeriesCV` | Time-series specific CV |
| `purged_cv()` | Purged CV convenience function |
| `combinatorial_purged_cv()` | CPCV convenience function |

**Regime Analysis:**
| Class/Function | Description |
|----------------|-------------|
| `RuleBasedRegimeDetector` | VIX/trend-based regime detection |
| `HMMRegimeDetector` | Hidden Markov Model regime detection |
| `ConditionalEvaluator` | Evaluate strategies by regime |
| `detect_regimes()` | Detect market regimes |
| `evaluate_by_regime()` | Performance breakdown by regime |
| `get_current_regime()` | Current market regime |

**Multi-Level Holdout:**
| Class/Function | Description |
|----------------|-------------|
| `MultiLevelHoldout` | Development/validation/test splits |
| `DevelopmentSplitter` | Train/validation within development |
| `create_holdout_structure()` | Create proper holdout splits |
| `validate_holdout_usage()` | Ensure no data leakage |

**PDT Framework:**
| Class/Function | Description |
|----------------|-------------|
| `PDTAwareBacktest` | Backtest respecting PDT rules |
| `HoldingPeriodOptimizer` | Optimize holding periods |
| `PDTTracker` | Track day trade count |
| `get_pdt_holding_recommendation()` | Recommended hold period |

### Performance Metrics (`src/evaluation/metrics/`)

**Return Metrics:**
| Function | Description |
|----------|-------------|
| `total_return()` | Cumulative return |
| `cagr()` | Compound Annual Growth Rate |
| `sharpe_ratio()` | Risk-adjusted return |
| `sortino_ratio()` | Downside risk-adjusted return |
| `calmar_ratio()` | Return over max drawdown |
| `information_ratio()` | Active return vs tracking error |
| `max_drawdown()` | Maximum peak-to-trough decline |
| `win_rate()` | Percentage of winning trades |
| `profit_factor()` | Gross profits / gross losses |
| `expectancy()` | Expected value per trade |
| `rolling_sharpe()` | Rolling window Sharpe ratio |
| `calculate_alpha()` | Jensen's alpha |
| `calculate_beta()` | Market beta |

**Risk Metrics:**
| Function | Description |
|----------|-------------|
| `value_at_risk()` | VaR at specified confidence |
| `conditional_var()` | Expected Shortfall (CVaR) |
| `max_drawdown_duration()` | Longest drawdown period |
| `downside_deviation()` | Below-target semi-deviation |
| `ulcer_index()` | Ulcer Index (drawdown severity) |
| `omega_ratio()` | Probability-weighted gains/losses |
| `tail_ratio()` | Right tail / left tail ratio |
| `skewness()` | Return distribution skewness |
| `kurtosis()` | Return distribution kurtosis |
| `stability_of_returns()` | R² of cumulative returns |

**Statistical Testing:**
| Class/Function | Description |
|----------------|-------------|
| `StatisticalTester` | Comprehensive statistical tests |
| `test_strategy_significance()` | Full significance test suite |
| `compare_two_strategies()` | Paired comparison of strategies |
| `compute_bootstrap_ci()` | Bootstrap confidence intervals |
| `BootstrapCI` | Bootstrap CI calculator |
| `StrategySignificanceSuite` | Complete significance testing |

### Performance Attribution (`src/evaluation/attribution/`)

| Class | Description |
|-------|-------------|
| `FactorModel` | Multi-factor regression analysis |
| `FactorExposure` | Factor loading analysis |
| `BrinsonAttribution` | Brinson allocation/selection |
| `RollingFactorAnalysis` | Time-varying factor exposures |
| `AttributionResult` | Attribution analysis results |

### Reporting (`src/evaluation/reporting.py`)

| Class/Function | Description |
|----------------|-------------|
| `HTMLReportGenerator` | Interactive HTML reports |
| `ChartGenerator` | Matplotlib/Plotly charts |
| `generate_backtest_report()` | Full backtest report |
| `generate_comparison_report()` | Multi-strategy comparison |
| `generate_json_report()` | Machine-readable JSON output |

### Usage Examples

```python
# Full validation pipeline
from src.evaluation import (
    VectorizedBacktest, mcpt_test, run_walk_forward,
    sharpe_ratio, max_drawdown, StatisticalTester
)

# 1. Run backtest
backtest = VectorizedBacktest(strategy, transaction_cost_bps=10)
result = backtest.run(data)

# 2. MCPT significance test
mcpt = mcpt_test(result.returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {mcpt.p_value:.4f}")

# 3. Walk-forward validation
wf_result = run_walk_forward(strategy, data, n_splits=5)
print(f"OOS Sharpe: {wf_result.oos_sharpe:.2f}")

# 4. Statistical testing suite
tester = StatisticalTester()
sig_result = tester.test_sharpe_ratio(result.returns)
print(f"Sharpe significant: {sig_result.significant}")

# 5. Reality check for data snooping
from src.evaluation import reality_check
rc_result = reality_check(strategy_returns_list, benchmark_returns)
print(f"Best strategy survives: {rc_result.best_survives}")
```

### Execution Layer (`src/execution/`)

| Module | Description |
|--------|-------------|
| `broker/alpaca.py` | Alpaca trading integration |
| `pipeline/` | Daily signal and order execution |
| `monitoring/` | Portfolio dashboard |

### Text Research (`src/text_research/`)

| Module | Description |
|--------|-------------|
| `corpus.py` | Point-in-time safe text storage |
| `embedding_engine.py` | Multi-model embeddings |
| `feature_extractor.py` | 7 text features |
| `signal_generator.py` | 5 signal strategies |
| `backtest.py` | Text-aware backtesting |
| `ingestors/` | News and SEC filing ingestion |

## Claude Code Agents

The system includes 10 specialized agents in `.claude/agents/`:

### Research Track (Track 1 & 2)

| Agent | Purpose |
|-------|---------|
| `research-agent` | Comprehensive strategy research and testing |
| `research-worker-agent` | Parallelizable sector-specific research |
| `macro-research-agent` | Geopolitical and macro factor analysis |
| `news-analyst-agent` | Event-driven news analysis |
| `regime-detector-agent` | Market regime classification |

### Text Research Track (Track 3)

| Agent | Purpose |
|-------|---------|
| `text-research-agent` | Text-based alpha discovery |

### Support Agents

| Agent | Purpose |
|-------|---------|
| `critic-agent` | Safety validation and bias detection |
| `monitor-agent` | Portfolio and trading oversight |
| `brainstorm-agent` | Feature and strategy ideation |
| `orchestrator-agent` | Multi-agent workflow coordination |

### Running Agents

```bash
# Via Claude Code - spawn agents in conversation
"Run a dual-track research cycle on semiconductors"

# The orchestrator spawns parallel agents:
# Track 1: macro-research, news-analyst, regime-detector
# Track 2: research-workers (by sector)
# Track 3: text-research-agent
```

## Claude Code Skills

7 skills available in `.claude/skills/`:

| Skill | Command | Purpose |
|-------|---------|---------|
| `/research` | Research strategies | Run research cycles, test hypotheses |
| `/validate` | Validate strategy | Full validation suite (MCPT, walk-forward) |
| `/critic` | Check for bugs | Safety checks, lookahead detection |
| `/promote` | Promote to paper | Move strategies to production |
| `/monitor` | Check portfolio | Trading performance monitoring |
| `/brainstorm` | Generate ideas | Feature and strategy ideation |
| `/report` | Generate report | Create documentation |

### Skill Workflow

```
/brainstorm -> /research -> /validate -> /critic -> /promote -> /monitor -> /report
```

## Configuration

### Strategy Pools (`config/strategies/strategy_pools.yaml`)

```yaml
budget_pool:
  constraints:
    min_hold_days: 2          # PDT compliance
    max_day_trades_per_5_days: 3
    max_position_pct: 0.20
    stop_loss_pct: 0.05
  strategies: []              # Populated by promotion

full_pool:
  constraints:
    min_hold_days: 0          # No restrictions
    max_position_pct: 0.25
  strategies: []
```

### Validated Strategies (`config/strategies/validated_strategies.yaml`)

Strategies that passed MCPT validation (p < 0.05) with production-ready status.

## Usage Examples

### Research Cycle

```python
from workflows.research.comprehensive_researcher import ComprehensiveResearcher

researcher = ComprehensiveResearcher()
results = researcher.run_cycle(
    universes=['semiconductors', 'tech_mega'],
    strategies=['bollinger_reversal', 'momentum']
)
```

### Text Research

```python
from src.text_research import (
    TextCorpus, EmbeddingEngine, TextFeatureExtractor,
    TextSignalGenerator, TextBacktester
)

corpus = TextCorpus()
embeddings = EmbeddingEngine()
features = TextFeatureExtractor(corpus, embeddings)
signals = TextSignalGenerator()
backtester = TextBacktester(corpus, embeddings, features)

result = backtester.run_walk_forward(
    signal_generator=signals.create_signal_generator_fn("combined"),
    symbols=["NVDA", "AMD"],
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31)
)
```

### Strategy Validation

```python
from src.evaluation.validation.mcpt import mcpt_test

result = mcpt_test(
    strategy_returns=returns,
    benchmark_returns=benchmark,
    n_permutations=1000
)
print(f"p-value: {result.p_value:.4f}")
```

### PDT-Aware Backtesting

```python
from src.evaluation.validation import PDTAwareBacktest, AccountType

backtest = PDTAwareBacktest(
    account_type=AccountType.BUDGET,
    initial_capital=10000
)
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10])
```

## CLI Commands

```bash
# Daily Operations
PYTHONPATH=. python3 scripts/run_daily.py --mode signals
PYTHONPATH=. python3 scripts/run_daily.py --mode paper
PYTHONPATH=. python3 scripts/run_daily.py --mode live

# Research
PYTHONPATH=. python3 scripts/full_research_cycle.py
PYTHONPATH=. python3 scripts/full_research_cycle.py --quick

# Validation
PYTHONPATH=. python3 scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM
PYTHONPATH=. python3 scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM

# Reports
PYTHONPATH=. python3 scripts/generate_report.py --type strategy --name bollinger_reversal --symbol QCOM

# Testing
PYTHONPATH=. python3 -m pytest tests/ -v
```

## Feature Registry

50+ registered features across categories:

| Category | Count | Examples |
|----------|-------|----------|
| Technical | 11 | rsi, macd, bollinger_bands, atr |
| Sentiment | 4 | news_sentiment, social_sentiment |
| Alternative | 4 | filing_sentiment, mda_tone |
| Flow | 5 | options_put_call, insider_activity |
| Risk | 4 | beta, drawdown, tail_risk |
| Regime | 3 | market_regime, volatility_regime |
| Embedding | 4 | narrative_centroid, topic_emergence |
| Text | 7 | sentiment_mean, narrative_shift |

## Output Directories

Results are stored in `/home/nock/quant_results/`:

| Directory | Contents |
|-----------|----------|
| `daily_runs/` | Daily signal and execution JSON |
| `daily_reviews/` | Human review dashboards |
| `backtests/` | Backtest results |
| `experiments/` | Research experiments |
| `validation_reports/` | Strategy validation JSON |
| `text_corpus/` | Text research documents |
| `embeddings_cache/` | Cached embeddings |

## Development

### Running Tests

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
PYTHONPATH=. python3 -m pytest tests/unit/ -v
PYTHONPATH=. python3 -m pytest tests/integration/ -v
```

### Adding a New Strategy

1. Create strategy class in `src/strategies/`
2. Implement `generate_signals(data) -> list[Signal]`
3. Add `required_features` class attribute
4. Run backtest and validate with MCPT
5. Add to `config/strategies/validated_strategies.yaml`

### Adding a New Feature

1. Add to `src/data/feature_engineering/feature_registry.py`
2. Implement compute function with proper lookback
3. Register with category and lookback_days

## Architecture Diagram

```
+-------------------------------------------------------------------------+
|                         ORCHESTRATOR AGENT                               |
+-------------------------------------------------------------------------+
|                                                                          |
|   TRACK 1: Novel Patterns          TRACK 2: Strategy Testing             |
|   +- macro-research-agent          +- research-worker (tech)             |
|   +- news-analyst-agent            +- research-worker (semis)            |
|   +- regime-detector-agent         +- research-worker (etfs)             |
|                                                                          |
|   TRACK 3: Text-Based Alpha                                              |
|   +- text-research-agent                                                 |
|                                                                          |
+-------------------------------------------------------------------------+
|   AGGREGATION -> VALIDATION (critic-agent) -> DAILY REVIEW -> PROMOTION |
+-------------------------------------------------------------------------+
```

## See Also

- **CLAUDE.md**: Detailed Claude Code reference for agents and skills
- **docs/TRADING_GUIDE.md**: Trading operations guide

## License

MIT License

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request
