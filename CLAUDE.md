# Quant Suite - Claude Code Reference

**Purpose**: Budget-friendly quantitative trading system ($200-$2,000 accounts)

---

## Project Logs & Documentation

| Document | Purpose |
|----------|---------|
| **DEVLOG.md** | Development progress, decisions, technical debt |
| **RESEARCH_LOG.md** | Validated results, flagged issues, research leads |
| **docs/TRADING_GUIDE.md** | End-user trading guide |
| **docs/EVALUATION_API.md** | Backtesting, validation, metrics API reference |
| **docs/ALPHA_DISCOVERY.md** | Alpha discovery system, alternative data sources |
| **docs/TEXT_RESEARCH.md** | Text research framework, feature engineering |

**Flagged Issues** (see RESEARCH_LOG.md):
- ML strategies (XGBoost, LightGBM) lack MCPT validation
- Mid/small cap feature leakage mentioned but not fully documented

---

## Quick Start Commands

```bash
# Daily Trading
PYTHONPATH=. python scripts/run_daily.py --mode signals      # Generate signals
PYTHONPATH=. python scripts/run_daily.py --mode paper        # Paper trading

# Research
PYTHONPATH=. python scripts/full_research_cycle.py           # Full cycle
PYTHONPATH=. python scripts/full_research_cycle.py --quick   # Quick test

# Validation
PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM --plots
PYTHONPATH=. python scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM

# Monitoring
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard

# Testing
PYTHONPATH=. python -m pytest tests/ -v
```

---

## Claude Code Skills

| Skill | Purpose |
|-------|---------|
| `/research` | Run research cycles, test strategies |
| `/critic` | Safety validation, detect artificial performance |
| `/monitor` | Trading performance monitoring |
| `/promote` | Move strategies to production |
| `/brainstorm` | Feature and strategy ideation |
| `/validate` | Full validation suite |
| `/report` | Generate documentation |

**Workflow**: `/brainstorm` -> `/research` -> `/validate` -> `/critic` -> `/promote` -> `/monitor` -> `/report`

---

## Architecture

```
[Data Layer]          [Feature Layer]        [Strategy Layer]       [Execution Layer]
    |                      |                      |                      |
 yfinance  ---------> FeatureComputer -----> Strategy.generate() --> RiskLimits
 SEC filings           (50+ features)              |                      |
 News RSS                  |                       v                      v
                           v                  Signal objects        OrderExecutor
                    enriched DataFrame              |                      |
                                                    +--------------------> Alpaca
```

**Key Principles**:
- Look-ahead bias prevention (features computed with proper date boundaries)
- PDT compliance (min 2-day hold, 3 day-trades per 5 days)
- 25% max position, 5% stop-loss, 10% take-profit
- MCPT validation required (p < 0.05) before production

---

## Key File Locations

| Category | Files |
|----------|-------|
| **Config** | `config/strategies/validated_strategies.yaml`, `config/credentials.yaml` |
| **Pipeline** | `scripts/run_daily.py`, `src/execution/pipeline/daily_signals.py`, `src/execution/broker/alpaca.py` |
| **Features** | `src/data/feature_engineering/feature_registry.py` (50+ features) |
| **Strategies** | `src/strategies/base.py`, `src/strategies/regime/regime_classifier.py` |
| **Research** | `workflows/research/knowledge_base.py`, `workflows/research/autonomous_loop.py` |
| **Validation** | `src/evaluation/validation/mcpt.py`, `src/evaluation/validation/walk_forward.py` |
| **Visualization** | `workflows/visualizations/strategy_plots.py` |

---

## Validated Strategies

| Strategy | Symbol | Sharpe | p-value |
|----------|--------|--------|---------|
| bollinger_reversal | QCOM | 3.14 | 0.007 |
| bollinger_reversal | MU | 2.93 | 0.007 |
| insider_technical | QQQ | 1.23 | 0.00 |

**Criteria**: MCPT p < 0.05, out-of-sample Sharpe > 0.5

See RESEARCH_LOG.md for full list and research leads.

---

## Common Tasks

### Add a New Strategy
1. Create class inheriting `BaseStrategy`
2. Implement `generate_signals(data) -> list[Signal]`
3. Run backtest with `VectorizedBacktest`
4. Validate with `mcpt_test()` (p < 0.05 required)
5. Add to `config/strategies/validated_strategies.yaml`

### Quick Backtest
```python
from src.evaluation.backtest.engine import VectorizedBacktest
backtest = VectorizedBacktest(strategy, initial_capital=10000, transaction_cost_bps=10)
results = backtest.run(data)
```

### MCPT Validation
```python
from src.evaluation.validation.mcpt import mcpt_test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {result.p_value:.4f}")
```

### Regime Detection
```python
from src.strategies.regime import EmpiricalRegimeClassifier
classifier = EmpiricalRegimeClassifier()
regime = classifier.detect_regime(prices)
recommendations = classifier.get_strategy_recommendations(regime)
```

See `docs/EVALUATION_API.md` for comprehensive API reference.

---

## Claude Code Agents (13 Total)

### Track 1: Novel Pattern Discovery
| Agent | Purpose |
|-------|---------|
| macro-research-agent | Geopolitical & macro analysis |
| news-analyst-agent | Event-driven news analysis |
| regime-detector-agent | Market regime classification |

### Track 2: Strategy Testing
| Agent | Purpose |
|-------|---------|
| research-agent | Comprehensive strategy research |
| research-worker-agent | Parallelizable sector research |

### Track 3: Text-Based Alpha
| Agent | Purpose |
|-------|---------|
| text-research-agent | Text-based alpha discovery |

### Track 4: Alpha Discovery
| Agent | Purpose |
|-------|---------|
| alpha-discovery-agent | Market inefficiency scanning |
| data-acquisition-agent | Free data source acquisition |
| hypothesis-generator-agent | Insight to strategy conversion |

### Support Agents
| Agent | Purpose |
|-------|---------|
| critic-agent | Safety validation, bias detection |
| monitor-agent | Portfolio and trading oversight |
| brainstorm-agent | Feature and strategy ideation |
| orchestrator-agent | Multi-agent workflow coordination |

**Configs**: `.claude/agents/<agent-name>.md`

### Standard Workflows

**Dual-Track Research**:
```
1. regime-detector-agent -> Get regime recommendations
2. [PARALLEL] 2-3x research-worker-agents
3. critic-agent -> Validate findings
```

**Alpha Discovery Pipeline**:
```
1. alpha-discovery-agent -> Scan for inefficiencies
2. data-acquisition-agent -> Scrape blogs, fetch data
3. hypothesis-generator-agent -> Create hypotheses
4. research-agent -> Test hypotheses
5. critic-agent -> Validate findings
```

**Daily Operations**:
```
1. monitor-agent -> Health check
2. monitor-agent -> Performance review
3. research-agent -> Follow up leads
```

---

## Output Directories

| Path | Contents |
|------|----------|
| `/home/nock/quant_results/` | All outputs |
| `.../comprehensive_research/` | Research cycle results |
| `.../validation_reports/` | Strategy validation JSON |
| `.../critic_reports/` | Critic validation JSON |
| `.../plots/` | Strategy validation plots |
| `.../promotions/` | Promotion records |

---

## Feature Registry Summary

**50+ features** in categories: TECHNICAL (11), SENTIMENT (4), ALTERNATIVE (4), FLOW (5), RISK (4), REGIME (3), EMBEDDING (4)

```python
from src.data.feature_engineering.feature_registry import FeatureComputer
computer = FeatureComputer()
features = computer.compute_feature("rsi", df)
```

---

## Schedule (ET)

| Event | Time | Days |
|-------|------|------|
| Signal Generation | 07:00 | Mon-Fri |
| Execution | 09:35 | Mon-Fri |
| EOD Snapshot | 16:05 | Mon-Fri |

---

## Error Handling

- **Empty signals**: Market closed or no signals meet thresholds
- **Alpaca connection**: Verify `config/credentials.yaml`
- **Feature computation**: Needs 60+ days lookback
- **PDT violations**: System enforces 2-day min hold for <$25k accounts

---

## Detailed Documentation

For comprehensive API documentation, see:
- `docs/EVALUATION_API.md` - Backtesting, validation, metrics, regime analysis
- `docs/ALPHA_DISCOVERY.md` - Alpha discovery, alternative data, market scanning
- `docs/TEXT_RESEARCH.md` - Text research, feature engineering, session tracking
- `docs/TRADING_GUIDE.md` - End-user trading guide
