# Project Athena: Hybrid Intelligence Trading System

A trading platform that fuses **statistical alpha generation**, **LLM reasoning**, and **human oversight** into a persistent intelligence that learns from every trade.

---

## The Core Insight

Within algorithmic trading, there exists a largely unexplored middle ground:

| Approach | Strength | Weakness |
|----------|----------|----------|
| **Pure Quantitative** | Rigorous, systematic | Blind to context |
| **Pure Discretionary** | Flexible, contextual | Prone to emotion |
| **Hybrid Intelligence** | Both + learning | What we're building |

**Project Athena** creates something genuinely new: a system where Claude operates as a **persistent trader** with continuous state awareness, investment thesis tracking, and learning capability. The infrastructure itself becomes the memory.

---

## Architecture: One File to Rule Them All

The key insight: **centralize state**. One file to read, one place to look.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ~/quant_results/live/state.json                 │
│  Market + Portfolio + Signals + Theses + Decisions + Learnings      │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │ writes continuously
┌─────────────────────────────────────────────────────────────────────┐
│                      LIVE DAEMON (background)                       │
│  Pulls from all components, synthesizes, writes unified state       │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
        ┌─────────────┬───────────┼───────────┬─────────────┐
        │             │           │           │             │
   ┌────┴────┐  ┌─────┴─────┐ ┌───┴───┐ ┌─────┴─────┐ ┌─────┴─────┐
   │ Signals │  │ Portfolio │ │ News  │ │ Theses    │ │ Decisions │
   │ Engine  │  │ Monitor   │ │ Daemon│ │ Tracker   │ │ Logger    │
   └─────────┘  └───────────┘ └───────┘ └───────────┘ └───────────┘
```

When Claude starts a session, it reads ONE file and knows:
- Market regime and sentiment
- Portfolio positions and risk
- Aggregated signals for the watchlist
- Active investment theses with conviction levels
- Pending decisions awaiting outcomes
- Recent learnings from past trades

---

## What Makes This Different

### 1. Investment Theses with Signposts

Every trade is linked to a thesis - a belief about what the market is missing:

```yaml
name: Venezuela Energy Recovery
conviction: 65%
positions: [SLB, HAL]

signposts:
  - description: "Chevron license extended"
    bullish_if: "Full renewal with expanded scope"
    bearish_if: "Only cosmetic extension"
    status: pending

invalidation_triggers:
  - "Oil below $60 makes Venezuela uneconomic"
  - "Policy reversal forces exit"
```

The system tracks signposts, updates conviction, and knows when to exit.

### 2. Adversarial Analysis

Every trade gets challenged before execution:

```
Proposed: BUY SLB at $45

Adversarial Analysis:
- Concern Level: MEDIUM
- Timing Concerns: Already up 15% this month
- Thesis Weaknesses: Geopolitical reversal risk
- Worst Case: Policy change forces -20% exit
- Recommendation: Proceed with reduced size
- Confidence Adjustment: -5%
```

### 3. Learning Loop

Learnings are extracted from every closed position:

```
Pattern: thesis_insider_confluence
What happened: Bought HAL on insider signal + Venezuela thesis. Rallied 4.5%.
What I learned: Insider + thesis alignment is high-conviction setup.
How this changes approach: Size 5% instead of 3% on this pattern.
Tags: [insider, thesis, energy, confluence]
```

These learnings persist and inform future decisions.

### 4. Pre-Mortem Thinking

Before every trade: "It's 30 days later and I lost money. What happened?"

This forces identification of failure modes before entering.

---

## Daily Workflow

```
6:00 AM  ─── scripts/research_prep.py ───► Pre-compute features, signals, screens
           │
6:30 AM  ─── /morning-briefing ───────────► Read unified state + web search
           │                                 Review active theses
           │                                 Check signal convergences (3+ aligned)
           │                                 Check improvement suggestions
           │
7:00 AM  ─── /trade-decision ─────────────► Synthesize signals + thesis alignment
           │                                 Run adversarial analysis
           │                                 Write pre-mortem
           │                                 Log decision with thesis link
           │
9:30 AM  ─── /operator-session ───────────► Enter persistent monitoring mode
           │                                 Check every 3 min (configurable)
           │                                 Surface alerts, convergences, catalysts
           │                                 Spawn research agents when needed
           │
Intraday ─── LiveDaemon ──────────────────► Update state.json every 5 min
           │
4:00 PM  ─── Exit operator session ───────► Market close
           │
4:30 PM  ─── /eod-review ─────────────────► Analyze outcomes vs predictions
           │                                 Extract learnings, log signal outcomes
           │                                 Update thesis conviction
           │
Sunday   ─── cron_weekly_improvement_review ► Generate improvement suggestions
```

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

# Pre-compute research (before market)
PYTHONPATH=. python scripts/research_prep.py

# Run daily workflow with Claude Code
claude /morning-briefing
claude /trade-decision
claude /execute-trades
claude /eod-review
```

---

## Output Directory Structure

```
~/quant_results/
├── live/                       # THE source of truth
│   ├── state.json             # Unified state (READ THIS FIRST)
│   └── research/              # Pre-computed research files
│       ├── features.json
│       ├── signals.json
│       ├── alt_data.json
│       └── screens.json
│
├── theses/                     # Investment theses (YAML)
│   └── venezuela_energy.yaml
│
├── learnings/                  # Trade learnings (monthly JSON)
│   └── 2026-01.json
│
├── knowledge/                  # Persistent knowledge
│   ├── companies/
│   │   └── SLB.yaml
│   └── sectors/
│       └── energy.yaml
│
├── improvements/               # Auto-generated improvement suggestions
│   └── suggestions.json
│
├── signal_quality/             # Signal quality metrics
│   ├── quality.json
│   └── outcomes.jsonl
│
├── logs/                       # Operator and system logs
│   └── operator_log.jsonl
│
├── decisions/                  # Trading decisions with reasoning
├── briefings/                  # Morning briefings
├── eod_reviews/               # End-of-day reviews
├── social/                     # Social signal tracking
│   ├── wsb.db                 # WSB mention database
│   ├── wsb_signals.json       # Processed WSB signals
│   └── social_timeseries.db   # Cross-platform time-series
├── signal_provenance/         # Signal tracking from discovery to outcome
└── suggestions/               # Auto-generated thesis suggestions
```

---

## Swarm Intelligence

Project Athena implements **swarm intelligence** principles where specialized agents collaborate via shared state:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SWARM ARCHITECTURE                               │
│                                                                      │
│  Trading Swarm        Research Swarm       Modeling Swarm           │
│  ├─ critic-agent      ├─ research-agent    ├─ regime-detector       │
│  ├─ monitor-agent     ├─ alpha-discovery   ├─ hypothesis-gen        │
│  └─ news-analyst      └─ brainstorm        └─ text-research         │
│                                                                      │
│         ▼                    ▼                    ▼                  │
│    ┌───────────────────────────────────────────────────────┐        │
│    │           ~/quant_results/live/signals/               │        │
│    │              (stigmergic communication)               │        │
│    └───────────────────────────────────────────────────────┘        │
│                           ▼                                          │
│    ┌───────────────────────────────────────────────────────┐        │
│    │              CONVERGENCE DETECTION                     │        │
│    │         3+ agents agree → high confidence signal       │        │
│    └───────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

**Swarm Execution Patterns:**
- **Morning Swarm**: Parallel spawn of regime-detector, news-analyst, monitor
- **Research Swarm**: Sequential pipeline from brainstorm → hypothesis → research
- **Crisis Swarm**: All agents converge on risk assessment

**Swarm Visualizer:**
```bash
python -m src.monitoring.swarm_visualizer --watch
```

---

## Core Components

### Synthesis Layer
| Component | Purpose |
|-----------|---------|
| `UnifiedState` | Everything in one dataclass |
| `LiveDaemon` | Writes state.json continuously |
| `SignalAggregator` | Combines all signal sources |

### Knowledge Layer
| Component | Purpose |
|-----------|---------|
| `ThesisTracker` | Investment theses with signposts |
| `ThesisPerformanceTracker` | P&L attribution by thesis |
| `SignalProvenanceTracker` | Track signals from discovery to outcome |
| `ThesisSuggester` | Auto-suggest theses from converging signals |
| `PaperPositionTracker` | Track thesis performance without investing |
| `LearningLog` | Extracted trade learnings |
| `KnowledgeBase` | Company/sector understanding |

### Execution Layer
| Component | Purpose |
|-----------|---------|
| `AccountManager` | Multi-account support (live/paper/tracking) |
| `AlpacaBroker` | Broker integration for paper and live trading |
| `PDTManager` | Pattern day trading compliance |

### Decision Layer
| Component | Purpose |
|-----------|---------|
| `DecisionLogger` | Full decision records with setup type tracking |
| `AdversarialAgent` | Challenge every trade |
| `MorningBriefing` | Pre-market context |

### Evaluation Layer
| Component | Purpose |
|-----------|---------|
| `StrategyDashboard` | Compare validated strategies by Sharpe, p-value |
| `MCPTAnalyzer` | Monte Carlo permutation testing |
| `WalkForwardOptimizer` | Walk-forward validation |

### Promotion Pipeline
| Component | Purpose |
|-----------|---------|
| `PromotionPipeline` | Manage backtest → paper → live lifecycle |
| `PromotionGates` | Automated quality gates for advancement |

**Pipeline Stages**: BACKTEST → MCPT_VALIDATION → PAPER_TRADING → PAPER_REVIEW → LIVE_PENDING → LIVE_TRADING

### Monitoring Layer
| Component | Purpose |
|-----------|---------|
| `UnifiedDashboard` | Full system status with all data sources |
| `SwarmMonitor` | Track agent swarms, detect signal convergences |
| `SwarmVisualizer` | Timeline + heatmap displays for swarm activity |
| `OperatorLoop` | Persistent monitoring check cycles |
| `DataFreshnessTracker` | Track data source status + content summaries |
| `SignalAggregator` | Aggregate signals + detect convergences |
| `ImprovementTracker` | Auto-generated improvement suggestions |
| `SignalQualityTracker` | Track signal hit rates over time |

---

## Claude Code Skills (15)

### Daily Trading
| Skill | Purpose |
|-------|---------|
| `/morning-briefing` | Read unified state, research overnight news |
| `/operator-session` | Persistent monitoring mode with configurable intervals |
| `/swarm-operator` | Orchestrate multi-agent swarms (trading, research, modeling) |
| `/social-signals` | Check WSB, Stocktwits for early alpha signals |
| `/trade-decision` | Synthesize + adversarial analysis + thesis linking |
| `/execute-trades` | Execute with human approval |
| `/eod-review` | Extract learnings, update thesis conviction |
| `/thesis` | Create/review/update investment theses |

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
research-agent, research-worker-agent, alpha-discovery-agent, hypothesis-generator-agent, brainstorm-agent

### Market Intelligence
macro-research-agent, news-analyst-agent, regime-detector-agent

### Operations
critic-agent, monitor-agent, data-acquisition-agent, orchestrator-agent

---

## Key Principles

### Token Efficiency
- Pre-compute everything possible (`research_prep.py`)
- Claude reads files, doesn't run pipelines
- ONE unified state file instead of scattered queries

### Session Continuity
- The infrastructure IS the memory
- Theses persist across sessions
- Learnings accumulate over time
- No separate SESSION.md needed

### Latent Knowledge Access
- Externalize knowledge (company/sector briefs)
- Structured decision frameworks
- Adversarial challenge before every trade

---

## Validation Requirements

Before production:
- **MCPT p-value < 0.05** (Monte Carlo Permutation Test)
- **Out-of-sample Sharpe > 0.5**
- **Critic validation** (no lookahead bias, overfitting)

---

## Trading Rules

| Rule | Value |
|------|-------|
| Max single position | **15%** (reduced from 25%) |
| Max thesis total | 35% |
| Max sector exposure | 40% |
| Max daily loss | 5% |
| Stop loss | 5-15% (based on conviction) |
| PDT day trades | 3 per 5 business days (<$25k) |
| Min swing hold | 2 business days |

**Key Learning**: High conviction ≠ high concentration. Start equal weight across thesis vehicles.

---

## Data Sources

### Statistical Signals
- 50+ technical features (RSI, MACD, Bollinger, momentum)
- ML models (require MCPT validation)
- Regime detection

### Alternative Data
| Category | Sources |
|----------|---------|
| **Core Alternative** | Congressional Trades, Insider Trading, Options Flow, Expert Sentiment, Prediction Markets, Social Sentiment |
| **Social Signals** | WSB Tracker (Reddit), Stocktwits, Social Time-Series DB with signal "vintage" tracking |
| **Market Regime** | VIX Term Structure, Put/Call Ratios, NYSE Breadth, Finviz Screens |
| **Sentiment Extremes** | AAII Survey, Newsletter Sentiment, Commitment of Traders (COT) |
| **Economic Calendar** | Earnings Calendar, Economic Releases, Fed Futures, Treasury Auctions |
| **Event Catalysts** | IPO Calendar, FDA Calendar (PDUFA/AdCom) |
| **Innovation Signals** | USPTO Patents, Job Postings, App Rankings, GitHub Activity |

### Data Collection Daemon
Orchestrates collection of 20+ free data sources with configurable schedules:
- **Real-time** (5-15 min): VIX structure, market breadth
- **Hourly**: Put/call ratios, Fed futures
- **Daily**: Earnings calendar, IPO calendar, app rankings
- **Weekly**: COT report, AAII sentiment, patents

All data is cached with proper TTLs and timestamps for point-in-time backtesting.

---

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code reference |
| `docs/EVALUATION_API.md` | Backtesting, validation |
| `docs/ALPHA_DISCOVERY.md` | Alternative data |
| `docs/TEXT_RESEARCH.md` | Text research, embeddings |
| `docs/TRADING_GUIDE.md` | User guide |
| `docs/FREE_DATA_SOURCES.md` | Free data sources implementation |
| `docs/ARCHITECTURE_DIAGRAMS.md` | Complete system architecture |

---

## License

MIT
