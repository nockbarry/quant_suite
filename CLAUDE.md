# Quant Suite - Claude Code Reference

**Purpose**: Budget-friendly quantitative trading system ($200-$2,000 accounts)
**Last Updated**: 2026-01-03

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

## Remaining Integration Gaps

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

## Specialized Subagents

The quant suite uses specialized subagents for autonomous operation. Each agent has a specific role:

### Agent Fleet

| Agent | Purpose | Key Files |
|-------|---------|-----------|
| **ResearchAgent** | Strategy discovery and testing | `agents/research.py` |
| **CriticAgent** | Safety validation and bias detection | `agents/critic.py` |
| **MonitorAgent** | Portfolio and trading oversight | `agents/monitor.py` |
| **BrainstormAgent** | Feature and strategy ideation | `agents/brainstorm.py` |
| **OrchestratorAgent** | Multi-agent workflow coordination | `agents/orchestrator.py` |

### Agent Configurations

Located in `/home/nock/projects/quant_suite/agents/`:

```python
from agents import ResearchAgent, CriticAgent, MonitorAgent, BrainstormAgent

# Get agent prompts for spawning
prompt = ResearchAgent.get_quick_research_prompt(
    universes=["tech_mega", "semiconductors"],
    strategies=["bollinger_reversal", "momentum"]
)

# Critic validation
prompt = CriticAgent.get_prompt(
    strategy="bollinger_reversal",
    symbol="QCOM"
)

# Monitor check
prompt = MonitorAgent.get_prompt(focus="health")

# Brainstorm session
prompt = BrainstormAgent.get_prompt(focus="alternative")
```

### Standard Workflows

**Full Research Cycle**:
```
1. BrainstormAgent → Generate feature ideas
2. ResearchAgent → Test strategies with MCPT validation
3. CriticAgent → Validate promising strategies
4. MonitorAgent → Update tracking with results
```

**Daily Operations**:
```
1. MonitorAgent → System health check
2. MonitorAgent → Performance review
3. (Weekly) BrainstormAgent → New ideas
4. ResearchAgent → Follow up on leads
```

### Spawning Agents

Use the Task tool to spawn agents:

```
Task(
    subagent_type="general-purpose",
    prompt=ResearchAgent.get_prompt(),
    description="Run research cycle"
)
```

For parallel execution, spawn multiple agents in a single message.

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
