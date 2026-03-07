# Project Athena - Claude Code Reference

A hybrid intelligence trading system where Claude operates as a **persistent trader** with continuous state awareness, thesis tracking, and learning capability.

---

## The ONE File Rule

**Start every session by reading the unified state:**

```python
from src.synthesis.state import UnifiedState
from src.core.paths import paths

state = UnifiedState.load(paths.live_state)
print(state.get_summary())
```

This single file contains: market regime, sentiment, portfolio positions, risk, aggregated signals, active theses, pending decisions, recent learnings.

**Key Principle**: The infrastructure IS the memory. Theses persist. Learnings accumulate. No separate SESSION.md needed.

---

## Daily Trading Workflow

### Automated (Background)

```bash
./scripts/setup_cron.sh install    # One-time cron setup
./scripts/trading_day.sh start     # Or manually start each day
```

Runs automatically: 6:00 AM daemons start, every 5 min state.json updates, 5:00 PM stop.

### Your Workflow (Claude Sessions)

| Time (ET) | Command | What Happens |
|-----------|---------|--------------|
| 6:30 AM | `claude "/morning-briefing"` | Read state, search news, review theses |
| 9:30 AM+ | `claude "/operator-session"` | Enter persistent monitoring mode |
| When ready | `claude "/trade-decision"` | Adversarial analysis, make decisions |
| When ready | `claude "/execute-trades"` | Execute with your approval |
| 4:30 PM | `claude "/eod-review"` | Extract learnings, update conviction |

---

## Token Efficiency Rules

**Use existing tools and quick commands instead of writing boilerplate code.**

### CRITICAL: Read Before Writing Code

Before writing ANY Python code, read the API reference:
```bash
cat docs/API_QUICK_REF.md
```

This prevents common errors like:
- `state.is_fresh()` → doesn't exist
- `calendar.get_events_by_date_range()` → wrong method name
- `signpost.get('description')` → signposts are dataclasses, not dicts

### Available Skills
```bash
# Daily Trading Workflow
/morning-briefing    # Pre-market research and briefing
/operator-session    # Persistent monitoring with configurable intervals
/swarm-operator      # Orchestrate multi-agent swarms
/social-signals      # Check WSB, Stocktwits for early alpha signals
/trade-decision      # Generate trade decisions with adversarial check
/execute-trades      # Execute with human approval
/eod-review          # End-of-day learning extraction
/monitor             # Check portfolio and position status
/thesis              # Create/review/update investment theses

# Research & Validation
/research            # Run research cycles
/brainstorm          # Generate feature and strategy ideas
/critic              # Safety validation for strategies
/validate            # Full validation suite (MCPT, walk-forward)
/promote             # Move strategy to production
/report              # Generate documentation and reports
```

### Quick Trade Commands
```bash
PYTHONPATH=. python3 scripts/quick_trade.py buy MU 10
PYTHONPATH=. python3 scripts/quick_trade.py sell SLB 50
PYTHONPATH=. python3 scripts/quick_trade.py quote MU FCX LEN
PYTHONPATH=. python3 scripts/quick_trade.py positions --thesis "Venezuela"
```

### Key Method Signatures
```python
# Broker
AlpacaBroker(api_key=..., secret_key=..., paper=True)
position.quantity  # NOT .qty
await broker.market_buy(symbol, Decimal(qty))
await broker.market_sell(symbol, Decimal(qty))

# Credentials: config/credentials.yaml → alpaca.api_key, alpaca.secret_key
```

---

## Core Architecture

All layers have code examples in `docs/API_QUICK_REF.md`. Component tables below for quick reference.

### Context Preservation Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **SessionContext** | `src/context/session_context.py` | Singleton accumulator for session context events |
| **capture_market_snapshot** | `src/context/market_snapshot.py` | Snapshot SPY, VIX, sectors, portfolio from state.json |

`create_decision()` auto-enriches context. `operator_check()` auto-pushes observations. Web UI shows context at `/decisions/{id}/context/`.

### Synthesis Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **UnifiedState** | `src/synthesis/state.py` | Everything in one dataclass |
| **LiveDaemon** | `src/synthesis/daemon.py` | Writes state.json every 5 min |
| **SignalAggregator** | `src/synthesis/signals.py` | Combines all signal sources |

### Live Signal Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **LiveSignalGenerator** | `src/signals/live_signal_generator.py` | Operationalized validated signals |
| **CandlePatternRecognizer** | `src/data/intraday/candle_analysis.py` | 25+ candle patterns |
| **IntradayFeatureEngine** | `src/data/intraday/feature_engine.py` | VWAP, ORB, volume profile |

Validated signals: Bollinger Bounce (IC=0.31, 61.4%), RSI Extreme (IC=0.20, 53.8%), Volume Spike FADE (IC=0.69), Channel Breakout FADE (IC=0.37).

### Knowledge Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **ThesisTracker** | `src/knowledge/thesis.py` | Investment theses with signposts |
| **ThesisPerformanceTracker** | `src/knowledge/thesis_performance.py` | P&L attribution by thesis |
| **SignalProvenanceTracker** | `src/knowledge/signal_provenance.py` | Track signals from discovery to outcome |
| **ThesisSuggester** | `src/knowledge/thesis_suggester.py` | Auto-suggest theses from converging signals |
| **LearningLog** | `src/knowledge/learnings.py` | Extracted trade learnings |
| **KnowledgeBase** | `src/knowledge/base.py` | Company/sector understanding |

### Intelligence Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **DecisionContextBuilder** | `src/intelligence/context_builder.py` | Track record + calibration + learnings at decision time |
| **SetupScorer** | `src/intelligence/setup_scorer.py` | Performance analytics by setup type |
| **BeliefUpdater** | `src/intelligence/belief_updater.py` | Daily signal weight updates, calibration |
| **PredictionRecord** | `src/db/models.py` | Testable predictions linked to decisions |

Feedback loop: decisions → predictions → scored → belief updater adjusts weights → context builder surfaces at decision time. Web dashboard at `/intelligence`.

### Decision Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **DecisionLogger** | `src/decision/decision_logger.py` | Full records with thesis linking |
| **AdversarialAgent** | `src/decision/adversary.py` | Challenge every trade |
| **MorningBriefing** | `src/decision/morning_briefing.py` | Pre-market context |

### Document Index Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **Document/Insight/Experiment** | `src/db/models.py` | Universal content index |
| **document_service** | `src/web/services/document_service.py` | Query layer for web UI |
| **context_for_symbol** | `scripts/context_for_symbol.py` | Full context dump for agents |

Web UI: `/documents`, `/documents/insights/list`, `/documents/experiments/list`

### Market Analysis Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **MarketMoverScanner** | `src/intelligence/market_movers.py` | Broad universe scan + context enrichment |
| **extract_symbols_from_headline** | `src/intelligence/thesis_keywords.py` | Ticker extraction from news headlines |
| **mover_service** | `src/web/services/mover_service.py` | Web service for mover dashboard |

### Monitoring Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **ComprehensiveDashboard** | `src/monitoring/comprehensive_dashboard.py` | Full system view with Claude activity |
| **OperatorLoop** | `src/monitoring/operator_loop.py` | Persistent monitoring checks |
| **DataFreshnessTracker** | `src/monitoring/data_freshness_tracker.py` | Data source health |
| **SignalQualityTracker** | `src/monitoring/signal_quality_tracker.py` | Track signal hit rates over time |

### Evaluation & Promotion
| Component | Location | Purpose |
|-----------|----------|---------|
| **StrategyDashboard** | `src/evaluation/comparison/dashboard.py` | Compare validated strategies |
| **MCPTAnalyzer** | `src/evaluation/validation/mcpt.py` | Monte Carlo permutation testing |
| **PromotionPipeline** | `src/execution/promotion/pipeline.py` | Backtest → Paper → Live lifecycle |

Pipeline: BACKTEST → MCPT_VALIDATION (p<0.05) → PAPER_TRADING (20+ days) → PAPER_REVIEW (Sharpe>0.5) → LIVE_PENDING → LIVE_TRADING

---

## Trade Decision Framework

When making trading decisions, systematically consider:

1. **Thesis Alignment** — Is symbol linked to an active thesis? Conviction level? Signpost triggers?
2. **Statistical Signal Quality** — Confidence, historical performance, regime alignment
3. **Knowledge Base Context** — Company/sector understanding from `src/knowledge/base.py`
4. **Adversarial Challenge** — CRITICAL: Every trade gets challenged via `AdversarialAgent`
5. **Pre-Mortem** — "It's 30 days later and I lost money. What happened?"
6. **Decision Logging** — Use `create_decision()` with thesis_id, pre_mortem, adversarial_notes

---

## Trading Rules

### CRITICAL: Performance-Based Rules (Updated 2026-01-21)

Based on analysis of 82 trades from Jan 5-21, 2026:

| Category | # Trades | Avg Return | Verdict |
|----------|----------|------------|---------|
| Current stock holdings | 51 | **+7.75%** | ✅ Excellent |
| Closed stocks | 7 | **-6.66%** | ❌ Exited too early |
| Options | 24 | **-14.25%** | ❌ AVOID |

### Rule 1: NO OPTIONS TRADING

**Options averaged -14.25% return. Do not trade options.**

Exceptions (require explicit user approval): Deep ITM calls (delta > 0.80), protective puts, covered calls for exit.

### Rule 2: HOLD POSITIONS - Don't Exit Early

**Exit ONLY when:** signpost invalidates thesis, -15% stop loss, conviction < 40%, concentration rebalancing.

**Do NOT exit because:** slightly negative, "taking profits" on small gains, nervous, "feels" wrong.

### Rule 3: Equal Weight Within Theses

1. **START EQUAL WEIGHT** across ALL vehicles
2. **CONCENTRATE ONLY AFTER** 10%+ outperformance
3. **SEPARATE IMMEDIATE vs FUTURE** beneficiaries

### Rule 4: Stock Picking Works

90% hit rate, +7.75% average. Keep: thesis-based investing, diversified vehicles, holding winners.

### Position Sizing & Risk Limits
| Confidence | Max Size | | Limit | Value |
|------------|----------|-|-------|-------|
| 90%+ | 10% | | Single position | **10% max** |
| 75-90% | 7% | | Single thesis | **40% max** |
| 60-75% | 5% | | Sector exposure | 45% max |
| <60% | 3% | | Stop loss | 15% |

### Exit Checklist (ALL must be checked before selling)

- [ ] Bearish signpost triggered?
- [ ] Thesis conviction < 40%?
- [ ] Position at -15% stop?
- [ ] Concentration requires rebalancing?

If NONE checked → **DO NOT SELL**

### PDT Compliance (<$25k)
Max 3 day trades per 5 rolling business days. 2-day minimum hold. Use `PDTManager` from `src/execution/pdt_manager.py`.

### Trading Patterns Reference

Read `docs/TRADING_PATTERNS.md` for accumulated wisdom: vehicle enumeration, converging signals (3+), squeeze mechanics, binary events, NO OPTIONS.

---

## Claude Code Agents (13)

| Agent | Purpose |
|-------|---------|
| research-agent | Comprehensive strategy research |
| research-worker-agent | Parallelizable sector research |
| alpha-discovery-agent | Market inefficiency scanning |
| hypothesis-generator-agent | Insight to strategy |
| brainstorm-agent | Feature ideation |
| text-research-agent | Text analysis and embeddings |
| macro-research-agent | Geopolitical & macro analysis |
| news-analyst-agent | Event-driven analysis |
| regime-detector-agent | Market regime classification |
| critic-agent | Safety validation, bias detection |
| monitor-agent | Portfolio oversight |
| data-acquisition-agent | Free data acquisition |
| orchestrator-agent | Multi-agent coordination |

---

## Key File Locations

| Category | Path |
|----------|------|
| **Unified State** | `~/quant_results/live/state.json` |
| **Database** | `~/quant_results/athena.db` (19 tables) |
| **Theses** | `~/quant_results/theses/` (YAML) + DB |
| **Learnings** | `~/quant_results/learnings/` |
| **Knowledge** | `~/quant_results/knowledge/` |
| **Decisions** | `~/quant_results/decisions/` |
| **Briefings** | `~/quant_results/briefings/` |
| **Intelligence** | `~/quant_results/intelligence/` |
| **Research** | `~/quant_results/live/research/` |
| **News** | `~/quant_results/live/news/` + `live/news_cache.json` |
| **Social** | `~/quant_results/social/` (wsb.db, stocktwits_cache.json) |
| **Market Movers** | `~/quant_results/live/market_movers_latest.json` |
| **Finviz** | `~/quant_results/scraped_data/finviz/screens_latest.json` |
| **Operator Logs** | `~/quant_results/logs/operator_log.jsonl` |
| **Credentials** | `config/credentials.yaml` |
| **Skills** | `.claude/skills/*/SKILL.md` |
| **Agents** | `.claude/agents/*.md` |

---

## Data Sources

### Statistical Signals
Technical (50+ features), ML models (XGBoost/LightGBM, require MCPT), regime detection.

### Alternative Data (40+ Sources)

| Category | Key Sources |
|----------|-------------|
| **Core** | Congressional trades, Insider trading, Options flow, Social sentiment |
| **Social** | WSB Tracker (Reddit), Stocktwits, Social Time-Series DB |
| **Market Regime** | VIX structure, Put/call ratios, Finviz screens (8), Breadth |
| **Sentiment** | AAII survey, Newsletter, COT report, Expert sentiment |
| **Economic** | Earnings calendar, Economic releases, Fed futures |
| **Events** | IPO calendar, FDA calendar (PDUFA dates) |
| **Innovation** | Patents, Job postings, App rankings, GitHub activity |
| **News** | 16 RSS feeds (WSJ, CNBC, Bloomberg, Fed, SEC, sector-specific) |
| **Geopolitical** | 5-region tracking (Greenland, Venezuela, China, ME, Russia) |
| **Legal** | SCOTUS cases, SEC enforcement, FTC, DOJ tracking |
| **Prediction Markets** | Polymarket, Kalshi, Metaculus, PredictIt |

All sources in `src/data/sources/alternative/`. See `docs/FREE_DATA_SOURCES.md` for full list.

---

## Infrastructure

### Hedge Fund Modules
Alerting (`smart_alerter.py`, `mobile_bot.py`), execution rules (`rules_engine.py`), drawdown protection, portfolio optimization (risk parity, Kelly), sector rotation, performance attribution, earnings prediction, WebSocket feeds, tax-loss harvesting, trade journal. See `docs/ARCHITECTURE_DIAGRAMS.md` Section 14.

### Cron Jobs
| Script | Schedule | Purpose |
|--------|----------|---------|
| `collect_all_data.py --quick` | Every 30 min Mon-Fri | Fast news + thesis matching |
| `collect_all_data.py` | Every 2h Mon-Fri | Full data collection (13 sources) |
| LiveDaemon | Every 5 min Mon-Fri | Update state.json |
| `cron_signal_scan.py` | Every 2h Mon-Fri | WSB, Stocktwits, prediction markets |
| `cron_signal_digest.py` | Every 30 min | Signal aggregation + convergences |
| `cron_market_movers.py` | 12:30 + 5:20 PM | Broad universe mover scan |
| `signpost_monitor.py` | Every 10 min (9-3pm) | Thesis signpost price checks |
| `cron_prediction_scorer.py` | 5:15 PM Mon-Fri | Score predictions |
| `cron_belief_update.py` | 5:30 PM Mon-Fri | Update signal weights |

```bash
./scripts/setup_cron.sh install       # Data collection cron
./scripts/setup_cron.sh install_auto  # Autonomous trading sessions
./scripts/setup_cron.sh install_all   # Both
```

### Autonomous Trading Day

Architecture: `cron → athena_scheduler.sh (tmux) → session_wrapper.sh → claude`

| Time (ET) | Session | Model |
|-----------|---------|-------|
| 05:55 | sentinel-start (Python daemon) | - |
| 06:30 | `/morning-briefing` | opus |
| 08:30 | `/operator-session` | opus |
| 10:00, 13:00 | `/trade-decision` | opus |
| 10:30, 14:30 | `/signal-scan` | sonnet |
| 12:00, 15:00 | `/internal-review` | sonnet |
| 16:30 | `/eod-review` | opus |
| 17:10 | sentinel-stop | - |

```bash
./scripts/athena_scheduler.sh setup           # Create tmux session
./scripts/athena_scheduler.sh sentinel-start  # Start Python monitoring daemon
./scripts/athena_scheduler.sh operator-start  # Launch operator
./scripts/athena_scheduler.sh status          # Show all sessions
```

Session coordination via `~/quant_results/scheduler/` (state, triggers, completions, locks, handoff).

---

## Quick Commands

```bash
# Research & Signals
PYTHONPATH=. python scripts/full_research_cycle.py --quick
PYTHONPATH=. python scripts/run_daily.py --mode signals
PYTHONPATH=. python scripts/context_for_symbol.py SLB

# Monitoring
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard --watch
PYTHONPATH=. python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8000

# Data Collection
PYTHONPATH=. python scripts/collect_all_data.py --quick

# Market Movers (broad universe scan)
PYTHONPATH=. python scripts/cron_market_movers.py           # After-close scan
PYTHONPATH=. python scripts/cron_market_movers.py --intraday # Midday (tighter thresholds)
```

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
| No unified state | Run `LiveDaemon().update_now()` |
| PDT violations | System enforces 2-day hold for <$25k |

---

## Documentation Guide

| If You Need To... | Read This |
|-------------------|-----------|
| Trade daily | `docs/WORKFLOW.md` |
| Create a thesis | `docs/TRADING_PATTERNS.md` |
| Understand the system | `docs/ARCHITECTURE_DIAGRAMS.md` |
| API method signatures | `docs/API_QUICK_REF.md` |
| Data sources | `docs/FREE_DATA_SOURCES.md` |
| Autonomous trading | `docs/AUTONOMOUS_TRADING_ARCHITECTURE.md` |
| Backtesting/validation | `docs/EVALUATION_API.md` |
| Alternative data | `docs/ALPHA_DISCOVERY.md` |
