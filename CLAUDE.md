# Quant Suite - Hybrid Human-AI-Statistical Trading System

A trading system that combines **statistical signal generation**, **LLM decision synthesis**, and **human oversight** for budget-friendly accounts.

---

## System Philosophy

```
                    INTELLIGENCE LAYERS
┌──────────────────────────────────────────────────────┐
│                                                      │
│  STATISTICAL LAYER    →   LLM LAYER    →   HUMAN    │
│  (Signal Generation)      (Decision)       (Review)  │
│                                                      │
│  • 50+ features           • Synthesizes          • EOD review    │
│  • Technical signals        signals + research   • Approve trades│
│  • Alternative data       • Applies latent       • Override      │
│  • Pattern detection        market knowledge     • Set rules     │
│                           • Documents reasoning                  │
└──────────────────────────────────────────────────────┘
```

**Key Principle**: Each layer adds value. Statistics find patterns. Claude adds context and reasoning. Humans provide judgment and accountability.

---

## Daily Trading Workflow

| Time (ET) | Skill | What Happens |
|-----------|-------|--------------|
| 6:30 AM | `/morning-briefing` | Gather news, portfolio state, alternative data |
| 7:00 AM | `/trade-decision` | Claude synthesizes signals + research → decisions with reasoning |
| 7:30 AM | `/execute-trades` | Execute approved decisions (human approval required) |
| 4:30 PM | `/eod-review` | Analyze outcomes, update learnings, prepare tomorrow |

```bash
# Run the workflow
claude /morning-briefing
claude /trade-decision
claude /execute-trades
claude /eod-review
```

---

## Quick Commands

```bash
# Daily Trading
PYTHONPATH=. python scripts/run_daily.py --mode signals      # Generate signals
PYTHONPATH=. python scripts/run_daily.py --mode paper        # Paper trading

# Research
PYTHONPATH=. python scripts/full_research_cycle.py           # Full research
PYTHONPATH=. python scripts/full_research_cycle.py --quick   # Quick test

# Validation
PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM --plots
PYTHONPATH=. python scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM

# Monitoring
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard
```

---

## Architecture Overview

```
PRE-MARKET (6:00-8:00 AM ET)
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Alternative  │  │ Statistical  │  │   Morning    │               │
│  │    Data      │  │   Signals    │  │   Research   │               │
│  │              │  │              │  │              │               │
│  │ Congressional│  │ Swing (daily)│  │ Overnight    │               │
│  │ Pred Markets │  │ Intraday (5m)│  │ news         │               │
│  │ Expert Sent. │  │ Technical    │  │ Pre-market   │               │
│  │ Insider      │  │ ML models    │  │ Portfolio    │               │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                 │                  │                      │
│         └─────────────────┼──────────────────┘                      │
│                           ▼                                         │
│              ┌────────────────────────┐                             │
│              │    MORNING BRIEFING    │                             │
│              │   (Structured context) │                             │
│              └───────────┬────────────┘                             │
│                          ▼                                          │
│              ┌────────────────────────┐                             │
│              │  LLM DECISION ENGINE   │                             │
│              │                        │                             │
│              │  • Consume all signals │                             │
│              │  • Apply latent knowledge                            │
│              │  • BUY/SELL/HOLD + why │                             │
│              └───────────┬────────────┘                             │
│                          ▼                                          │
│              ┌────────────────────────┐                             │
│              │   EXECUTION (9:30)     │                             │
│              │                        │                             │
│              │  • Risk validation     │                             │
│              │  • PDT compliance      │                             │
│              │  • Human approval      │                             │
│              │  • Alpaca orders       │                             │
│              └───────────┬────────────┘                             │
│                          ▼                                          │
│              ┌────────────────────────┐                             │
│              │   LEARNING LOOP (4PM)  │                             │
│              │                        │                             │
│              │  • Track outcomes      │                             │
│              │  • Update knowledge    │                             │
│              │  • What worked/failed  │                             │
│              └────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Sources

### Statistical Signals
- **Technical**: RSI, MACD, Bollinger Bands, momentum (50+ features)
- **ML Models**: XGBoost, LightGBM (require MCPT validation)
- **Regime**: Volatility regime, trend detection

### Alternative Data
| Source | File | Signal Type |
|--------|------|-------------|
| **Congressional Trades** | `congressional_trades.py` | Cluster buying, Pelosi trades |
| **Prediction Markets** | `prediction_markets.py` | Fed policy, recession odds, macro |
| **Expert Sentiment** | `expert_sentiment.py` | Inverse Cramer, follow/fade pundits |
| **Insider Trading** | `insider.py` | SEC Form 4 cluster buying |
| **Options Flow** | `options_flow.py` | Unusual activity, put/call ratio |
| **News/Reddit** | `news.py`, `reddit.py` | Sentiment, trending tickers |

### Alternative Data Usage
```python
# Congressional cluster buying (multiple members buying same stock)
from src.data.sources.alternative import find_congressional_clusters
clusters = await find_congressional_clusters(min_traders=2)

# Inverse Cramer (signal auto-inverted)
from src.data.sources.alternative import get_inverse_cramer
cramer_calls = await get_inverse_cramer(days=7)

# Prediction markets for macro
from src.data.sources.alternative import get_macro_signals
macro = await get_macro_signals()
```

---

## LLM Decision Framework

When making trading decisions, Claude explicitly considers:

### 1. Statistical Signal Quality
- Signal confidence and confirming indicators
- Historical performance of signal type
- Alignment with current market regime

### 2. Latent Market Knowledge
- **Company**: Business model, moat, earnings quality, management
- **Sector**: Cycle position, catalysts, relative valuations
- **Macro**: Fed policy, economic cycle, geopolitical risks
- **Behavioral**: Sentiment extremes, crowded trades, positioning

### 3. Portfolio Context
- Current exposure to symbol/sector
- Correlation with existing positions
- PDT constraints (<$25k accounts)

### 4. Risk Assessment
- What could go wrong?
- Max loss scenario
- Exit liquidity

---

## Trading Rules

### Position Sizing by Confidence
| Confidence | Max Size |
|------------|----------|
| 90%+ | 20% |
| 75-90% | 15% |
| 60-75% | 10% |
| <60% | 5% or HOLD |

### Risk Limits
| Limit | Value |
|-------|-------|
| Single position | 25% max |
| Sector exposure | 40% max |
| Daily loss | 5% max |
| Stop loss | 5-15% based on conviction |
| Take profit | 10-30% |

### PDT Compliance (<$25k)
- Max 3 day trades per 5 rolling days
- 2-day minimum hold for swing trades
- Use `PDTManager` to track capacity

```python
from src.execution.pdt_manager import create_pdt_manager
pdt = create_pdt_manager(account_equity=10000)
can_trade, reason = pdt.can_day_trade("AAPL")
```

---

## Claude Code Skills (11)

### Daily Trading
| Skill | Purpose |
|-------|---------|
| `/morning-briefing` | Pre-market research aggregation |
| `/trade-decision` | LLM decision engine |
| `/execute-trades` | Execution with approval |
| `/eod-review` | Daily analysis and learning |

### Research & Validation
| Skill | Purpose |
|-------|---------|
| `/research` | Run research cycles |
| `/critic` | Safety validation |
| `/validate` | Full validation suite |
| `/brainstorm` | Feature and strategy ideation |
| `/promote` | Move to production |
| `/monitor` | Portfolio oversight |
| `/report` | Generate documentation |

---

## Claude Code Agents (13)

### Research Track
| Agent | Purpose |
|-------|---------|
| research-agent | Comprehensive strategy research |
| research-worker-agent | Parallelizable sector research |
| alpha-discovery-agent | Market inefficiency scanning |
| hypothesis-generator-agent | Insight → strategy |
| brainstorm-agent | Feature ideation |

### Market Intelligence
| Agent | Purpose |
|-------|---------|
| macro-research-agent | Geopolitical & macro analysis |
| news-analyst-agent | Event-driven analysis |
| regime-detector-agent | Market regime classification |

### Operations
| Agent | Purpose |
|-------|---------|
| critic-agent | Safety validation, bias detection |
| monitor-agent | Portfolio oversight |
| data-acquisition-agent | Free data acquisition |
| orchestrator-agent | Multi-agent coordination |

---

## Key File Locations

| Category | Path |
|----------|------|
| **Skills** | `.claude/skills/*/SKILL.md` |
| **Agents** | `.claude/agents/*.md` |
| **Strategies** | `src/strategies/` |
| **Alternative Data** | `src/data/sources/alternative/` |
| **Decision Engine** | `src/decision/` |
| **Intraday** | `src/strategies/intraday/`, `src/data/pipeline/intraday.py` |
| **PDT Manager** | `src/execution/pdt_manager.py` |
| **Validation** | `src/evaluation/validation/` |

---

## Output Directories

| Path | Contents |
|------|----------|
| `/home/nock/quant_results/briefings/` | Morning briefings |
| `/home/nock/quant_results/decisions/` | Trading decisions with reasoning |
| `/home/nock/quant_results/eod_reviews/` | EOD analysis |
| `/home/nock/quant_results/pdt/` | PDT state tracking |
| `/home/nock/quant_results/trading_logs/` | Session logs |
| `/home/nock/quant_results/comprehensive_research/` | Research results |
| `/home/nock/quant_results/validation_reports/` | Strategy validation |

---

## Validated Strategies

| Strategy | Symbol | Sharpe | p-value |
|----------|--------|--------|---------|
| bollinger_reversal | QCOM | 3.14 | 0.007 |
| bollinger_reversal | MU | 2.93 | 0.007 |
| insider_technical | QQQ | 1.23 | 0.00 |

**Validation Criteria**: MCPT p < 0.05, out-of-sample Sharpe > 0.5

---

## Error Handling

| Issue | Solution |
|-------|----------|
| Empty signals | Market closed or thresholds not met |
| Alpaca connection | Check `config/credentials.yaml` |
| Feature computation | Needs 60+ days lookback |
| PDT violations | System enforces 2-day hold for <$25k |

---

## Detailed Documentation

| Document | Purpose |
|----------|---------|
| `docs/EVALUATION_API.md` | Backtesting, validation, metrics |
| `docs/ALPHA_DISCOVERY.md` | Alternative data, market scanning |
| `docs/TEXT_RESEARCH.md` | Text research, embeddings |
| `docs/TRADING_GUIDE.md` | End-user trading guide |
| `DEVLOG.md` | Development progress |
| `RESEARCH_LOG.md` | Research findings |
