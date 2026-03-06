# Project Athena

An autonomous trading system where Claude operates as a persistent trader with thesis-driven investing, cross-session memory, and a self-improving intelligence loop. Python handles the mechanical. Claude handles the judgment. Shared memory connects them.

---

## How It Works

Three layers run autonomously during market hours:

```
SENTINEL (Python, every 15-60s, zero Claude tokens)
  Monitors market state, detects convergences, maintains situation board
  Triggers analyst sessions when events need interpretation
       │
       ▼
REACTIVE AGENTS (Claude, on-demand, 3-10 min)
  Analyst ──── Interpret events, assess signals (Sonnet)
  Strategist ─ Make trade decisions with adversarial challenge (Opus)
  Executor ─── Validate orders, submit via Alpaca
       │
       ▼
DEEP AGENTS (Claude, scheduled, 10-20 min)
  Reviewer ─── Quality control, thesis health, update strategic context (Opus)
  Theorist ─── Scenario planning, blind spots, research hypotheses (Opus)
  Researcher ─ Test hypotheses, discover patterns (Sonnet)
```

Sessions share context through two memory files:
- **Situation Board** (`situation_board.json`) — Same-day shared memory. Observations, market state, portfolio alerts, analysis requests. Auto-resets daily.
- **Strategic Context** (`strategic_context.json`) — Multi-day persistent memory. Thesis momentum, developing patterns, signal source trends, upcoming catalysts, research hypotheses.

Every Claude session receives both summaries as injected context. Every session writes back what it learned.

---

## The Trading Day

```
05:55  Sentinel starts (Python daemon, 15-60s heartbeat)
06:00  Data collection begins (35+ sources, every 30 min)
06:30  /morning-briefing — overnight news, thesis review, signal convergences
08:30  Operator session starts (persistent monitoring, writes convergences)
09:31  Scheduled trades execute (from previous day's decisions)
10:00  /trade-decision — adversarial analysis, thesis alignment, pre-mortem
10:30  /signal-scan — LLM analysis of social signals (WSB, Stocktwits)
12:00  /internal-review — prediction accuracy, signal drift, thesis health
13:00  /trade-decision — afternoon pass
14:30  /signal-scan — second social signal pass
15:00  /internal-review — second quality check
16:05  Operator stops
16:30  /eod-review — outcomes vs predictions, extract learnings
17:00  Daemons stop, daily signals archived
17:30  Signal archive for backtesting

Sunday:
18:00  /thesis — weekly thesis review and conviction updates
19:00  /brainstorm — new feature and strategy ideation
20:00  /theorist — scenario planning, blind spot analysis
```

Everything is scheduled via cron and managed through tmux. Install with:

```bash
./scripts/setup_cron.sh install_all
./scripts/athena_scheduler.sh setup
./scripts/athena_scheduler.sh sentinel-start
```

---

## Core Concepts

### Thesis-Driven Investing

Every trade is linked to an investment thesis with signposts and invalidation criteria:

```yaml
name: Venezuela Energy Recovery
conviction: 95%
vehicles: [SLB, HAL, PBF, STNG, EURN, FRO]

signposts:
  - description: "OFAC license renewal scope"
    bullish_if: "Full GL46 renewal with expanded scope"
    bearish_if: "Only cosmetic extension"

invalidation:
  - "Oil below $60 makes Venezuela uneconomic"
```

The system tracks 24 active theses, monitors signposts hourly, auto-invalidates when conviction drops below 40%, and flags anchoring risk above 90%.

### Adversarial Analysis

Every trade decision gets challenged before execution. The adversary examines timing concerns, thesis weaknesses, worst-case scenarios, and recommends position sizing adjustments.

### Compounding Intelligence Loop

Every decision creates testable predictions that are auto-scored:

```
Decision → Prediction → Daily Scorer → Belief Updater → Context Builder
                                            │
                     Signal weights adjusted ─┘
                     Calibration updated
                     Setup type performance tracked
```

At decision time, the system surfaces: symbol track record, setup type performance, confidence calibration ("when you say 70%, you're right 58% of the time"), and prediction history.

### Cross-Session Memory

The swarm architecture solves the context reset problem:

| Memory Layer | Scope | Written By | Read By |
|-------------|-------|------------|---------|
| `state.json` | Current market + portfolio | LiveDaemon (5 min) | All sessions |
| `situation_board.json` | Today's observations | Sentinel + all sessions | All sessions |
| `strategic_context.json` | Multi-day patterns | Reviewer, Theorist | All sessions |
| `signal_digest.json` | Aggregated signals | Signal digest cron | Sentinel, Operator |
| `athena.db` | Permanent record | All sessions | All sessions |

---

## Architecture

```
~/quant_results/
├── live/state.json              ← THE source of truth (market + portfolio + signals)
├── athena.db                    ← SQLite (19 tables: decisions, predictions, theses, etc.)
├── scheduler/
│   ├── situation_board.json     ← Same-day shared memory (sentinel → all)
│   ├── strategic_context.json   ← Multi-day persistent memory (reviewer → all)
│   ├── signal_digest.json       ← Aggregated signals with convergences
│   ├── scheduler_state.json     ← Session lifecycle tracking
│   ├── completions/             ← Session completion records with findings
│   ├── locks/                   ← Session mutex locks
│   └── trade_triggers.json      ← Convergences awaiting trade decisions
├── theses/                      ← Investment theses (YAML, dual-write to DB)
├── learnings/                   ← Monthly trade learnings
├── intelligence/                ← Calibration, metrics, daily belief updates
├── briefings/                   ← Morning briefing archives
├── decisions/                   ← Full decision records with context
├── reviews/                     ← Internal review + theorist reports
├── knowledge/                   ← Company and sector briefs
├── social/                      ← WSB, Stocktwits signal databases
└── logs/                        ← Operator, sentinel, session logs
```

### Source Code

```
src/
├── swarm/                       ← Cross-session shared memory
│   ├── situation_board.py       ← SituationBoard: same-day observations
│   └── strategic_context.py     ← StrategicContext: multi-day patterns
├── synthesis/                   ← Unified state (state.py, daemon.py, signals.py)
├── knowledge/                   ← Theses, learnings, knowledge base
├── intelligence/                ← Belief updater, context builder, setup scorer
├── decision/                    ← Decision logger, adversary, morning briefing
├── context/                     ← Session context preservation
├── monitoring/                  ← Operator loop, dashboards, signal quality
├── signals/                     ← Live signal generator, candle patterns
├── data/                        ← 40+ data sources, intraday features
├── execution/                   ← Broker, PDT manager, promotion pipeline
├── evaluation/                  ← MCPT, walk-forward, strategy comparison
├── web/                         ← FastAPI dashboard (24 routes)
│   ├── routes/swarm.py          ← Situation board + strategic context UI
│   ├── routes/sessions.py       ← Autonomous session timeline
│   ├── routes/intelligence.py   ← Prediction tracking + calibration
│   └── routes/theses.py         ← Thesis management
└── db/                          ← SQLite models, write API

scripts/
├── sentinel.py                  ← Python monitoring daemon (replaces health_monitor)
├── athena_scheduler.sh          ← tmux session manager
├── session_wrapper.sh           ← Per-session wrapper (timeout, model, skill, context)
├── setup_cron.sh                ← Install data + autonomous cron schedules
├── collect_all_data.py          ← Master data collection (35+ sources)
└── cron_signal_digest.py        ← Signal aggregation + convergence detection

.claude/
├── skills/                      ← 18 Claude Code skills
│   ├── analyst/                 ← Event-driven analysis (Sonnet, 5 min)
│   ├── theorist/                ← Strategic thinking (Opus, 15 min)
│   ├── trade-decision/          ← Trade decisions with adversarial check
│   ├── internal-review/         ← Self-assessment + strategic context update
│   ├── morning-briefing/        ← Pre-market research
│   ├── eod-review/              ← End-of-day learning extraction
│   ├── operator-session/        ← Persistent monitoring
│   └── ...                      ← 11 more (research, brainstorm, thesis, etc.)
└── agents/                      ← 13 specialized Claude Code agents
```

---

## Skills and Agents

### Skills (18)

| Skill | Model | Duration | Trigger |
|-------|-------|----------|---------|
| `/morning-briefing` | Opus | 10 min | Cron 6:30 AM |
| `/trade-decision` | Opus | 10 min | Cron 10:00/13:00 + sentinel trigger |
| `/analyst` | Sonnet | 5 min | Sentinel event trigger |
| `/operator-session` | Opus | 8 hours | Cron 8:30 AM |
| `/eod-review` | Opus | 10 min | Cron 4:30 PM |
| `/internal-review` | Opus | 10 min | Cron 12:00/15:00 |
| `/theorist` | Opus | 15 min | Cron Sunday 8 PM |
| `/signal-scan` | Sonnet | 5 min | Cron 10:30/14:30 |
| `/thesis` | Opus | 10 min | Cron Sunday 6 PM |
| `/research` | Sonnet | 15 min | On-demand + triggered |
| `/brainstorm` | Sonnet | 10 min | Cron Sunday 7 PM |
| `/execute-trades` | Opus | 5 min | After trade-decision |
| `/social-signals` | Sonnet | 5 min | On-demand |
| `/monitor` | Sonnet | 5 min | On-demand |
| `/critic` | Sonnet | 10 min | Before promotion |
| `/validate` | Sonnet | 15 min | Before promotion |
| `/promote` | Opus | 10 min | After validation |
| `/report` | Sonnet | 10 min | On-demand |

### Agents (13)

| Agent | Purpose |
|-------|---------|
| research-agent | Strategy research and backtesting |
| research-worker-agent | Parallelizable sector research |
| alpha-discovery-agent | Market inefficiency scanning |
| hypothesis-generator-agent | Turn insights into testable strategies |
| brainstorm-agent | Feature and strategy ideation |
| macro-research-agent | Geopolitical and macro analysis |
| news-analyst-agent | Event-driven analysis |
| regime-detector-agent | Market regime classification |
| critic-agent | Safety validation, bias detection |
| monitor-agent | Portfolio oversight |
| data-acquisition-agent | Free data source acquisition |
| orchestrator-agent | Multi-agent coordination |

---

## Data Sources (40+)

| Category | Sources |
|----------|---------|
| **Market** | SPY, VIX, sector ETFs, put/call ratios, NYSE breadth, Finviz screens (8) |
| **Alternative** | Congressional trades, insider trading (Form 4), options flow |
| **Social** | WSB (Reddit), Stocktwits, social time-series DB |
| **Sentiment** | AAII survey, newsletter sentiment, COT report, prediction markets |
| **News** | 16 RSS feeds (WSJ, CNBC, Bloomberg, Fed, SEC, sector-specific) |
| **Economic** | Earnings calendar, economic releases, Fed futures |
| **Events** | IPO calendar, FDA calendar (PDUFA dates) |
| **Geopolitical** | 5-region tracking (Greenland, Venezuela, China, Middle East, Russia) |
| **Legal** | SCOTUS, SEC enforcement, FTC, DOJ |
| **Innovation** | Patents, job postings, app rankings, GitHub activity |

Collected every 30 minutes via `collect_all_data.py`. Signal digest built every 30 minutes with quality-weighted deduplication.

---

## Web Dashboard

FastAPI dashboard at `http://localhost:8000` with 24 routes:

| Page | What It Shows |
|------|--------------|
| `/` | Portfolio summary, activity feed, system health |
| `/swarm` | Situation board, strategic context, sentinel status, thesis momentum |
| `/sessions` | Autonomous session timeline, live status, thesis-matched news |
| `/intelligence` | Prediction tracking, calibration chart, setup type performance |
| `/theses` | Thesis management (create, edit, conviction history, signposts) |
| `/portfolio` | Positions, P&L, thesis attribution |
| `/decisions` | Decision records with full context panels |
| `/signals` | Live signals, convergence detection |
| `/data` | Data source freshness grid (40+ sources) |
| `/agents` | Agent run metrics and ops center |
| `/research` | Research experiments and insights |

HTMX for dynamic updates. Dark theme. Auto-refresh on live data.

---

## Trading Rules

Based on analysis of 82+ trades:

| Rule | Rationale |
|------|-----------|
| **No options** | Averaged -14.25% across 24 trades |
| **Hold positions** | Exits averaged -6.66%, holdings +7.75% |
| **Equal weight within theses** | Don't concentrate until 10%+ outperformance |
| **Max 10% single position** | Risk management |
| **Max 40% single thesis** | Diversification |
| **15% stop loss** | Exit only on: signpost invalidation, stop hit, conviction <40% |

### Validation Requirements

Before production: MCPT p-value < 0.05, out-of-sample Sharpe > 0.5, critic validation pass.

---

## Quick Start

```bash
# Install
git clone <repo-url>
cd quant_suite
pip install -r requirements.txt

# Configure
cp config/credentials.yaml.example config/credentials.yaml
# Edit with Alpaca API keys (paper trading)

# Manual daily workflow
claude /morning-briefing
claude /trade-decision
claude /execute-trades
claude /eod-review

# Autonomous mode (recommended)
./scripts/setup_cron.sh install_all     # Install all cron jobs
./scripts/athena_scheduler.sh setup     # Create tmux session
./scripts/athena_scheduler.sh sentinel-start  # Start sentinel daemon
./scripts/athena_scheduler.sh status    # Verify everything running

# Web dashboard
PYTHONPATH=. uvicorn src.web.app:app --host 0.0.0.0 --port 8000

# Manual control
./scripts/athena_scheduler.sh kill-all  # Emergency stop
./scripts/athena_scheduler.sh wsl-info  # WSL setup for autonomous trading
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code reference (skills, agents, API, rules) |
| `docs/SWARM_ARCHITECTURE.md` | Three-layer swarm design |
| `docs/SWARM_IMPLEMENTATION_PLAN.md` | Implementation details for all 4 phases |
| `docs/SYSTEM_REVIEW.md` | System audit findings |
| `docs/AUTONOMOUS_TRADING_ARCHITECTURE.md` | Scheduler, session wrapper, health monitoring |
| `docs/TRADING_PATTERNS.md` | Accumulated trading wisdom |
| `docs/API_QUICK_REF.md` | Method signatures and usage |
| `docs/ARCHITECTURE_DIAGRAMS.md` | Complete system architecture |
| `docs/FREE_DATA_SOURCES.md` | Data source implementation |
| `docs/EVALUATION_API.md` | Backtesting and validation |
| `docs/README_LEGACY.md` | Previous README for reference |

---

## License

MIT
