# Quant Suite

**Hybrid Human-AI-Statistical Trading System**

A trading platform that combines **statistical signal generation**, **LLM decision synthesis**, and **human oversight** for budget-friendly accounts ($200-$25,000+).

---

## The Hybrid Approach

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYERS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   STATISTICAL          LLM (Claude)           HUMAN            │
│   ────────────         ────────────           ─────            │
│   • 50+ features       • Synthesizes          • EOD review     │
│   • Technical            all inputs           • Approve trades │
│   • Alternative data   • Latent knowledge     • Override       │
│   • ML models          • Documents why        • Set rules      │
│                                                                 │
│   "What patterns       "Does this make        "Do I trust      │
│    exist in data?"      sense?"                this?"          │
└─────────────────────────────────────────────────────────────────┘
```

**Why hybrid?**
- Statistics find patterns humans miss
- LLMs provide context and reasoning humans would apply
- Human oversight catches errors both might make
- Full audit trail of every decision

---

## Daily Trading Workflow

```
6:30 AM   /morning-briefing    Gather news, portfolio state, alternative data
7:00 AM   /trade-decision      Claude makes BUY/SELL/HOLD decisions with reasoning
7:30 AM   /execute-trades      Execute approved trades (human approval required)
4:30 PM   /eod-review          Analyze outcomes, update learnings
```

**Key Innovation**: Claude Code IS the decision engine. Statistical models generate signals, but Claude synthesizes research context and applies latent market knowledge to make final trading decisions with documented reasoning.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/quant_suite.git
cd quant_suite
pip install -r requirements.txt

# Configure credentials
cp config/credentials.yaml.example config/credentials.yaml
# Edit with your Alpaca API keys

# Run daily workflow (Claude Code)
claude /morning-briefing
claude /trade-decision
claude /execute-trades

# Or run statistical pipeline directly
PYTHONPATH=. python scripts/run_daily.py --mode paper
```

---

## Features

### Three Intelligence Layers

| Layer | Components | Purpose |
|-------|------------|---------|
| **Statistical** | 50+ features, ML models, technical indicators | Find patterns in data |
| **LLM** | Claude Code with market knowledge | Synthesize and reason |
| **Human** | EOD review, trade approval | Judgment and accountability |

### Alternative Data Sources

| Source | Signals |
|--------|---------|
| Congressional Trades | Cluster buying (Pelosi, committee members) |
| Prediction Markets | Fed policy, recession odds, macro events |
| Expert Sentiment | Inverse Cramer, follow/fade pundits |
| Insider Trading | SEC Form 4 cluster buying |
| Options Flow | Unusual activity, institutional positioning |
| News/Reddit | Sentiment, trending tickers |

### PDT Compliance

For accounts under $25,000:
- Tracks 3 day trades per 5 rolling days
- Enforces 2-day minimum hold for swings
- PDTManager for real-time capacity tracking

### Intraday Trading

- VWAP bounce strategy
- Momentum continuation
- ATR-based stops and targets
- Session phase awareness (opening, power hour)

### Research Framework

- 13 specialized Claude Code agents
- MCPT validation (p < 0.05 required)
- Walk-forward testing
- Critic validation for bias detection

---

## Architecture

```
PRE-MARKET
┌────────────────────────────────────────────────────────┐
│                                                        │
│  Alternative Data     Statistical         Research     │
│  ─────────────────    ──────────         ────────     │
│  Congressional        Swing signals      Overnight     │
│  Prediction mkts      Intraday (5m)      news         │
│  Expert sentiment     Technical          Pre-market   │
│  Insider trading      ML models          Portfolio    │
│                                                        │
│                    ↓                                   │
│           ┌─────────────────┐                         │
│           │ MORNING BRIEFING │                        │
│           │ (Structured)     │                        │
│           └────────┬────────┘                         │
│                    ↓                                  │
│           ┌─────────────────┐                         │
│           │  LLM DECISION   │                         │
│           │  • Synthesize   │                         │
│           │  • Reason       │                         │
│           │  • Decide + why │                         │
│           └────────┬────────┘                         │
│                    ↓                                  │
│           ┌─────────────────┐                         │
│           │   EXECUTION     │                         │
│           │  • Risk check   │                         │
│           │  • PDT check    │                         │
│           │  • Approval     │                         │
│           │  • Submit       │                         │
│           └────────┬────────┘                         │
│                    ↓                                  │
│           ┌─────────────────┐                         │
│           │  LEARNING LOOP  │                         │
│           │  • Track P&L    │                         │
│           │  • What worked  │                         │
│           │  • Update KB    │                         │
│           └─────────────────┘                         │
└────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
quant_suite/
├── .claude/
│   ├── skills/              # 11 Claude Code skills
│   │   ├── morning-briefing/
│   │   ├── trade-decision/
│   │   ├── execute-trades/
│   │   └── eod-review/
│   └── agents/              # 13 specialized agents
├── src/
│   ├── decision/            # LLM decision engine
│   │   ├── morning_briefing.py
│   │   └── decision_logger.py
│   ├── strategies/
│   │   ├── intraday/        # VWAP, momentum
│   │   ├── traditional/     # Mean reversion, trend
│   │   └── regime/          # Regime classification
│   ├── data/
│   │   ├── sources/alternative/  # Congressional, prediction mkts, etc.
│   │   └── pipeline/intraday.py  # Real-time data
│   ├── execution/
│   │   ├── pdt_manager.py   # PDT compliance
│   │   └── broker/alpaca.py
│   └── evaluation/
│       └── validation/      # MCPT, walk-forward
├── scripts/
│   ├── run_daily.py
│   └── full_research_cycle.py
└── config/
    ├── credentials.yaml
    └── strategies/validated_strategies.yaml
```

---

## Claude Code Integration

### Skills (11)

**Daily Trading:**
- `/morning-briefing` - Pre-market research
- `/trade-decision` - LLM decision engine
- `/execute-trades` - Execute with approval
- `/eod-review` - Daily analysis

**Research:**
- `/research`, `/validate`, `/critic`, `/brainstorm`, `/promote`, `/monitor`, `/report`

### Agents (13)

**Research:** research-agent, research-worker-agent, alpha-discovery-agent, hypothesis-generator-agent, brainstorm-agent

**Market Intelligence:** macro-research-agent, news-analyst-agent, regime-detector-agent

**Operations:** critic-agent, monitor-agent, data-acquisition-agent, orchestrator-agent

---

## Alternative Data Usage

```python
# Congressional cluster buying
from src.data.sources.alternative import find_congressional_clusters
clusters = await find_congressional_clusters(min_traders=2)
for c in clusters:
    print(f"{c.symbol}: {c.unique_traders} politicians, {c.signal}")

# Inverse Cramer (signal automatically inverted)
from src.data.sources.alternative import get_inverse_cramer
cramer = await get_inverse_cramer(days=7)
for call in cramer:
    print(f"{call.symbol}: {call.signal}")  # His BUY → our SELL

# Prediction markets
from src.data.sources.alternative import get_macro_signals
macro = await get_macro_signals()
for signal in macro:
    print(f"{signal.category}: {signal.consensus_direction}")
```

---

## PDT Manager

For accounts under $25,000:

```python
from src.execution.pdt_manager import create_pdt_manager

pdt = create_pdt_manager(account_equity=10000)

# Check capacity
can_trade, reason = pdt.can_day_trade("AAPL")
print(f"Can day trade: {can_trade} - {reason}")

# Record trades
pdt.record_entry("AAPL", price=150.0, quantity=10)
trade_type, record = pdt.record_exit("AAPL", price=152.0)

# Status
print(pdt.get_summary())
# {'day_trade_count': 1, 'day_trades_remaining': 2, ...}
```

---

## Validation Requirements

Before production:
- **MCPT p-value < 0.05** (Monte Carlo Permutation Test)
- **Out-of-sample Sharpe > 0.5**
- **Critic validation** (no lookahead bias, overfitting)

```python
from src.evaluation.validation.mcpt import mcpt_test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {result.p_value:.4f}")
```

---

## Trading Rules

| Rule | Value |
|------|-------|
| Max single position | 25% |
| Max sector exposure | 40% |
| Max daily loss | 5% |
| Stop loss | 5-15% |
| PDT day trades | 3 per 5 days |
| Min swing hold | 2 days |

---

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code reference |
| `docs/EVALUATION_API.md` | Backtesting, validation |
| `docs/ALPHA_DISCOVERY.md` | Alternative data |
| `docs/TRADING_GUIDE.md` | User guide |
| `DEVLOG.md` | Development log |
| `RESEARCH_LOG.md` | Research findings |

---

## License

MIT
