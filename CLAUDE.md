# Project Athena - Claude Code Reference

A **fully autonomous** trading system where Claude operates as a **persistent trader** with continuous state awareness, thesis tracking, learning capability, and **autonomous execution authority**. No human in the loop — Claude researches, decides, and executes within quantitative safety rails.

**Parallel Architecture**: Supports 3 identical instances running on separate Alpaca paper accounts with a meta-observer measuring divergence. Decision ensemble (3x evaluation consensus) provides error bars on every trade.

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
./scripts/setup_cron.sh install_all    # One-time cron setup (data + autonomous)
./scripts/athena_scheduler.sh setup    # Create tmux session
./scripts/athena_scheduler.sh sentinel-start  # Start sentinel daemon
```

Runs automatically: 5:55 AM sentinel starts, 6:00 AM data collection, every 5 min state.json updates, 5:10 PM sentinel stops.

### Fully Autonomous Workflow (All Cron-Driven)

| Time (ET) | Command | What Happens |
|-----------|---------|--------------|
| 6:30 AM | `claude "/morning-briefing"` | Read state, search news, review theses |
| 8:30 AM | `claude "/operator-session"` | Persistent monitoring + autonomous execution |
| 10:00/13:00 | `claude "/trade-decision"` | Adversarial analysis → decisions → auto-executed |
| 4:30 PM | `claude "/eod-review"` | Extract learnings, update conviction |

**No human approval needed.** Trade decisions are auto-executed via `cron_auto_execute.py` after each `/trade-decision` session. The operator can also execute stop-losses and thesis invalidation closes directly.

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
/morning-briefing    # Pre-market research and briefing (reads prior session artifacts)
/operator-session    # Persistent monitoring with configurable intervals
/trade-decision      # Generate trade decisions with calibration enforcement + adversarial check
/execute-trades      # Execute with human approval
/eod-review          # End-of-day learning extraction with thesis P&L attribution
/monitor             # Check portfolio and position status

# Analysis & Signals
/analyst             # Event-driven analysis triggered by sentinel (Sonnet, 5min)
/internal-review     # Self-assessment: prediction accuracy, signal drift, thesis health
/signal-scan         # LLM analysis of WSB, Stocktwits social signals
/social-signals      # Check social signal landscape across platforms

# Research & Strategy
/research            # Run research cycles
/research-queue      # Consume research queue — run backtests, validate hypotheses
/hypothesis-gen      # Generate testable hypotheses from accumulated signals
/brainstorm          # Generate feature and strategy ideas
/evening-research    # Post-market web research, news synthesis, macro analysis

# Strategic Planning
/thesis              # Create/review/update investment theses
/theorist            # Weekly scenario planning, blind spots, strategic context
/swarm-operator      # Orchestrate multi-agent swarms

# System Health
/system-review       # Weekly evaluation: instance comparison, thesis health, parameter tuning

# Validation & Production
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
# Broker — MUST connect() before any calls
from src.execution.broker.alpaca import AlpacaBroker
from src.execution.broker.base import AccountInfo, Quote

broker = AlpacaBroker(api_key=..., secret_key=..., paper=True)
await broker.connect()           # REQUIRED before any API call

account = await broker.get_account()  # Returns AccountInfo (NOT raw Alpaca object)
account.portfolio_value          # Decimal — total equity (NOT .equity)
account.cash                     # Decimal
account.buying_power             # Decimal
account.day_trade_count          # int
account.pattern_day_trader       # bool

positions = await broker.get_positions()  # list — each has .symbol, .quantity, etc.
position.quantity                # NOT .qty

quote = await broker.get_quote(symbol)    # Returns Quote
quote.last                       # Decimal — last price

await broker.market_buy(symbol, Decimal(qty))
await broker.market_sell(symbol, Decimal(qty))
await broker.disconnect()        # Clean up when done

# Shortcut: use quick_trade helper (handles connect/disconnect)
from scripts.quick_trade import get_broker
broker = get_broker(paper=True)

# Credentials: config/credentials.yaml → alpaca.api_key, alpaca.secret_key
```

### Situation Board (~/quant_results/scheduler/situation_board.json)
```python
# Top-level keys (auto-resets daily):
board["date"]                    # str — "2026-03-24"
board["last_updated"]            # str — ISO timestamp
board["market_snapshot"]         # dict — spy, vix, regime
board["today_observations"]      # list — NOT "observations"
board["active_analyses"]         # list — analyst session results
board["decisions_today"]         # list — {symbol, action, status, reasoning_summary}
board["portfolio_alerts"]        # list — {symbol, type, current_pnl}
board["regime_context"]          # dict — current, vix_trend, interpretation

# Each observation in today_observations:
obs["time"]                      # str — "10:14"
obs["source"]                    # str — "sentinel", "analyst", etc.
obs["type"]                      # str — "signpost", "alert", etc.
obs["text"]                      # str — description
```

---

## Market Opinion System

Continuous LLM-generated market appraisal. Replaces the broken binary prediction system.

### Key Components
| Component | Location | Purpose |
|-----------|----------|---------|
| **OpinionUniverse** | `src/opinions/universe.py` | 50-80 symbol universe (thesis vehicles + watchlist + movers + commodities) |
| **OpinionContextAssembler** | `src/opinions/context_assembler.py` | Compact per-symbol context lines for batched prompts |
| **OpinionCaptureEngine** | `src/opinions/capture.py` | Generate prompt, parse LLM JSON response, save to DB |
| **OpinionScorer** | `src/opinions/scorer.py` | Score opinions at 5d/10d/30d horizons |
| **DecisionQualityTracker** | `src/opinions/decision_quality.py` | Track decision outcomes at 1d/5d/10d/30d |

### Usage (from any session)
```python
from src.opinions.capture import OpinionCaptureEngine

engine = OpinionCaptureEngine()
result = engine.capture(session_type="operator")  # Returns {"prompt": str, "batch_id": str, ...}
# LLM reads result["prompt"], outputs JSON array of opinions
opinions = engine.parse_response(json_text, result["batch_id"], "operator", result["universe"])
saved = engine.save_batch(opinions)
```

### Operator hook (rate-limited to every 15 min)
```python
opinion_result = loop.get_opinion_prompt()  # Returns None if not due
```

### Web Dashboard
`/opinions/` — scorecard, calibration, recent opinions
`/opinions/quality` — decision quality curves per instance
`/opinions/divergence` — cross-instance opinion divergence

### Cron: 5:20 PM opinion scorer, 5:22 PM decision quality

---

## Core Architecture

All layers have code examples in `docs/API_QUICK_REF.md`. Component tables below for quick reference.

### Context Preservation Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **SessionContext** | `src/context/session_context.py` | Singleton accumulator for session context events |
| **capture_market_snapshot** | `src/context/market_snapshot.py` | Snapshot SPY, VIX, sectors, portfolio from state.json |

`create_decision()` auto-enriches context. `operator_check()` auto-pushes observations. Web UI shows context at `/decisions/{id}/context/`.

### Swarm Layer (Cross-Session Memory)
| Component | Location | Purpose |
|-----------|----------|---------|
| **SituationBoard** | `src/swarm/situation_board.py` | Same-day shared memory, auto-resets daily, 5-min dedup |
| **StrategicContext** | `src/swarm/strategic_context.py` | Multi-day persistent (thesis momentum, patterns, catalysts, blind spots) |
| **artifact_log** | `src/swarm/artifact_log.py` | Cross-session artifact provenance (verify information flow) |

All sessions injected with board + context summaries via `--append-system-prompt`. `check_flow_health()` verifies 5 expected cross-session flows.

### Synthesis Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **UnifiedState** | `src/synthesis/state.py` | Everything in one dataclass |
| **LiveDaemon** | `src/synthesis/daemon.py` | Writes state.json every 5 min (auto-links positions to theses) |
| **SignalAggregator** | `src/synthesis/signals.py` | Combines all signal sources |

### Live Signal Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **LiveSignalGenerator** | `src/signals/live_signal_generator.py` | Operationalized validated signals |
| **CandlePatternRecognizer** | `src/data/intraday/candle_analysis.py` | 25+ candle patterns |
| **IntradayFeatureEngine** | `src/data/intraday/feature_engine.py` | VWAP, ORB, volume profile |

Validated signals: Bollinger Bounce (IC=0.31, 61.4%), RSI Extreme (IC=0.20, 53.8%), Volume Spike FADE (IC=0.69), Channel Breakout FADE (IC=0.37).

### Conviction Velocity & Crisis Alpha Signals
| Component | Location | Purpose |
|-----------|----------|---------|
| **ConvictionVelocityEngine** | `src/signals/conviction_velocity.py` | dConviction/dt as position sizing signal. ADD when velocity > +2pp/day, REDUCE when < -3pp/day |
| **CrisisAlphaEngine** | `src/signals/crisis_alpha.py` | VIX>25 mean-reversion in semis. NVDA 93.8% hit rate, MU 78.6%, QCOM 76.9% |

### Commodity Data Pipeline
| Component | Location | Purpose |
|-----------|----------|---------|
| **FertilizerCollector** | `src/data/sources/alternative/fertilizer_prices.py` | CF/MOS/NTR/UNG as urea/potash proxies |
| **ShippingRateCollector** | `src/data/sources/alternative/shipping_rates.py` | BDRY/FRO/DHT as VLCC/BDI proxies |
| **LNGCollector** | `src/data/sources/alternative/lng_prices.py` | UNG/LNG as Henry Hub/TTF proxies |
| **HormuzTracker** | `src/data/sources/alternative/hormuz_tracker.py` | BNO-USO spread + news sentiment for disruption estimate |

### Portfolio Risk Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **PortfolioStressTester** | `src/risk/stress_tester.py` | Monte Carlo VaR, scenario analysis, cross-thesis correlation |
| **DecisionEnsemble** | `src/decision/ensemble.py` | 3x evaluation consensus before execution |

### Parallel Instance Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **InstanceConfig** | `src/core/instance.py` | Instance-aware credentials, paths, tmux sessions |
| **MetaObserver** | `src/parallel/meta_observer.py` | Cross-instance divergence: thesis overlap, conviction distributions |
| **instance_launcher.sh** | `scripts/instance_launcher.sh` | Create/start/stop/status for parallel instances |

### Autonomous Thesis Creation
| Component | Location | Purpose |
|-----------|----------|---------|
| **ThesisSuggester.auto_create_from_suggestions** | `src/knowledge/thesis_suggester.py` | Auto-creates theses when confidence > 0.75, max 2/week |

### Strategic Analysis Layer
| Component | Location | Purpose |
|-----------|----------|---------|
| **SECInsiderMonitor** | `src/data/sources/alternative/sec_insider_monitor.py` | SEC EDGAR Form 4 insider transactions for portfolio symbols |
| **TreasuryMonitor** | `src/data/sources/alternative/treasury_monitor.py` | OFAC/Treasury press releases for sanctions changes |
| **MarketReactionScorer** | `src/intelligence/market_reaction.py` | Detects when market rejects news signal (failed interventions) |
| **CrossReferenceEngine** | `src/intelligence/cross_reference.py` | Cross-references data sources to generate red flags (insider divergence, failed interventions, regulatory ceiling) |
| **run_cross_reference.py** | `scripts/run_cross_reference.py` | Cron wrapper — runs every 30 min, pushes alerts to situation board |

Evening research skill restructured with 5-step investigative checklist: insider check, regulatory check, market reaction analysis, strategic analysis search, cross-reference review. Web dashboard at `/alerts`.

### Thesis Maintenance (Automated)
| Component | Location | Purpose |
|-----------|----------|---------|
| **ThesisMaintenanceCron** | `scripts/cron_thesis_maintenance.py` | Daily 6:10 AM: auto-suggest theses from signal convergences (≥75% confidence, max 2/week), surface overdue reviews to situation board, enforce 95% conviction ceiling |
| **ThesisSuggester** | `src/knowledge/thesis_suggester.py` | Scan signal convergences → generate suggestions → auto-create theses. Source weights: congressional 1.4, insider 1.3, statistical 1.2, news 1.0 |
| **Belief updater safeguards** | `src/intelligence/belief_updater.py` | Conviction ceiling 95% (prevents anchoring), ±5% per-run velocity cap (prevents whiplash) |
| **Operator overdue check** | `src/monitoring/operator_loop.py` | Every operator check surfaces theses past `next_review` as action items |
| **Sentinel trigger** | `src/intelligence/adaptive_triggers.py` | `thesis_review_overdue`: spawns `/thesis` session when any thesis 7+ days past review (24h cooldown) |

### Self-Improvement Loop
| Component | Location | Purpose |
|-----------|----------|---------|
| **AutoCorrectionEngine** | `scripts/auto_corrections.py` | Mechanical fixes from alerts: conviction +/-, position freeze, thesis invalidation. Every 30 min. |
| **SystemReview skill** | `.claude/skills/system-review/SKILL.md` | Weekly evaluation: instance comparison, thesis health, parameter tuning, bug triage. Sunday 4:30 PM. |
| **AutoUpgrader** | `src/upgrades/auto_upgrader.py` | Branch-test-merge code changes. Tier 1 (whitelist), Tier 2 (new files), Tier 3 (propose). |
| **BugMonitor** | `src/intelligence/bug_monitor.py` | Scans logs for tracebacks, categorizes, proposes fixes. Every 2h. Dashboard at `/bugs`. |
| **AdaptiveTriggerEngine** | `src/intelligence/adaptive_triggers.py` | Event-driven session spawning: portfolio drawdown, VIX spike, position stop, red flag cluster, crash loop, thesis invalidation, thesis review overdue. Integrated into sentinel. |

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
| **DecisionContextBuilder** | `src/intelligence/context_builder.py` | Track record + calibration + price targets + learnings at decision time |
| **SetupScorer** | `src/intelligence/setup_scorer.py` | Performance analytics by setup type |
| **BeliefUpdater** | `src/intelligence/belief_updater.py` | Daily signal weight updates, calibration, auto-applies ALL conviction changes |
| **PredictionRecord** | `src/db/models.py` | Testable predictions linked to decisions |

Feedback loop: decisions → predictions → scored → belief updater adjusts weights (auto-applies ALL conviction changes) → context builder surfaces at decision time. Calibration enforcement caps confidence in `/trade-decision`. Web dashboard at `/intelligence`.

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
| **UsageMonitor** | `src/monitoring/usage_monitor.py` | Token usage, cost-per-session-type, capacity tracking |
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

## Trade Decision Framework (Fully Autonomous)

When making trading decisions, systematically consider:

1. **Thesis Alignment** — Is symbol linked to an active thesis? Conviction level? Signpost triggers?
2. **Statistical Signal Quality** — Confidence, historical performance, regime alignment
3. **Knowledge Base Context** — Company/sector understanding from `src/knowledge/base.py`
4. **Adversarial Challenge** — Every trade gets challenged via `AdversarialAgent`
5. **Pre-Mortem** — "It's 30 days later and I lost money. What happened?"
6. **Decision Logging** — Use `create_decision()` with thesis_id, pre_mortem, adversarial_notes
7. **Auto-Execution** — Decisions with status PENDING are auto-executed by `cron_auto_execute.py` after session

**Execution authority: FULL.** No human approval needed. Safety rails (position sizing, daily loss limits, PDT) are enforced automatically.

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

No exceptions in autonomous mode.

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

### Autonomous Execution Rules

**The system is fully autonomous. No human approval required.**

| Trigger | Action | Executor |
|---------|--------|----------|
| Trade decision PENDING | Auto-execute on paper | `cron_auto_execute.py` (after trade-decision session) |
| Position at -15% stop | Auto-close | Operator session or rules engine |
| Thesis conviction < 40% | Auto-close all thesis positions | Belief updater → rules engine |
| Position > 20% portfolio | Auto-trim to 15% | Rules engine (concentration_trim) |
| Portfolio down 10%+ | Auto-reduce largest position | Rules engine (drawdown_protection) |
| VIX > 30 in backwardation | Auto-buy SPY 5% | Rules engine (vix_mean_reversion) |
| Thesis stock RSI < 30 | Auto-add 2% | Rules engine (thesis_oversold_add) |
| Conviction change any size | Auto-applied | Belief updater (no cap) |

**Safety rails (always enforced, cannot be overridden):**
- Max 5% single trade size
- Max 10 trades per day
- Max 15% single position
- Max 40% sector concentration
- No buying if portfolio down 3%+ today
- Trading hours 9 AM - 4 PM ET only
- PDT compliance (<$25k accounts)

### Adaptive Triggers (Event-Driven Sessions)

The `AdaptiveTriggerEngine` (`src/intelligence/adaptive_triggers.py`) runs inside the sentinel every 30s and spawns unscheduled sessions when conditions warrant. Each trigger has a cooldown to prevent spam.

| Trigger | Threshold | Level | Session Spawned | Cooldown |
|---------|-----------|-------|-----------------|----------|
| Portfolio drawdown | -3% day | elevated | trade-decision | 4h |
| Portfolio drawdown | -5% day | critical | system-review | 8h |
| Position stop hit | -15% unrealized | elevated | trade-decision | 1h |
| VIX spike | +10% session | elevated | trade-decision | 4h |
| VIX extreme | >35 absolute | critical | trade-decision | 8h |
| Oil crash (BNO/USO) | -10% day | critical | system-review | 8h |
| Red flag cluster | 3+ in 4h | elevated | trade-decision | 4h |
| Insider selling cluster | 3+ portfolio stocks in 24h | elevated | trade-decision | 8h |
| Thesis invalidated | conviction <25% | elevated | trade-decision | 4h |
| Conviction velocity | >5pp/day | alert | analyst | 8h |
| Thesis review overdue | 7+ days past review | alert | thesis | 24h |
| Crash loop | 5+ same error/1h | critical | system-review | 12h |
| Ensemble rejections | 3+ consecutive | elevated | system-review | 24h |
| Instance divergence | >15% equity spread | critical | system-review | 24h |

Trigger history visible on web dashboard at `/alerts`. Log at `~/quant_results/logs/adaptive_triggers.jsonl`.

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
| macro-research-agent | Geopolitical & macro analysis |
| news-analyst-agent | Event-driven analysis |
| regime-detector-agent | Market regime classification |
| critic-agent | Safety validation, bias detection |
| monitor-agent | Portfolio oversight |
| data-acquisition-agent | Free data acquisition |
| orchestrator-agent | Multi-agent coordination |
| text-research-agent | Text analysis and embeddings |

---

## Key File Locations

| Category | Path |
|----------|------|
| **Unified State** | `~/quant_results/live/state.json` |
| **Database** | `~/quant_results/athena.db` (19 tables: decisions, predictions, theses, signals, etc.) |
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
| **Signal Provenance** | `~/quant_results/signal_provenance/*.json` |
| **Scheduler** | `~/quant_results/scheduler/` (board, context, state, triggers, completions) |
| **Artifact Flow Log** | `~/quant_results/scheduler/artifact_reads.jsonl` |
| **Calibration** | `~/quant_results/intelligence/calibration.json` |
| **Research Queue** | `~/quant_results/scheduler/research_queue.json` |
| **Credentials** | `config/credentials.yaml` (or `credentials_{instance}.yaml` for multi-instance) |
| **Skills** | `.claude/skills/*/SKILL.md` (20 skills) |
| **Agents** | `.claude/agents/*.md` (13 agents) |
| **Commodity Data** | `~/quant_results/live/fertilizer_prices.json`, `shipping_rates.json`, `lng_prices.json`, `hormuz_status.json` |
| **Risk Reports** | `~/quant_results/risk_reports/stress_test_*.json` |
| **Ensemble Logs** | `~/quant_results/decisions/ensemble/ensemble_*.json` |
| **Meta Reports** | `~/quant_results/parallel/meta_report_*.json` |
| **War Dashboard** | `~/quant_results/war/` |
| **Cross-Reference Alerts** | `~/quant_results/live/cross_reference_alerts.json` |
| **Bug Reports** | `~/quant_results/logs/bug_reports.json` |
| **Stress Test** | `~/quant_results/risk_reports/stress_test_latest.json` |
| **Meta Reports** | `~/quant_results/parallel/meta_report_latest.json` |
| **Upgrade Log** | `~/quant_results/logs/upgrade_log.jsonl` |
| **Auto-Corrections Log** | `~/quant_results/logs/auto_corrections.jsonl` |
| **Thesis Maintenance Log** | `~/quant_results/logs/thesis_maintenance.jsonl` |
| **Auto-Thesis Creation Log** | `~/quant_results/logs/auto_thesis_creation.jsonl` |
| **Signal Engines** | `~/quant_results/live/signal_engines.json` |
| **SEC Insider Alerts** | `~/quant_results/live/sec_insider_alerts.json` |

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
| `run_cross_reference.py` | Every 30 min (9-4pm) | Cross-reference red flags |
| `auto_corrections.py` | Every 30 min (9-4pm) | Mechanical conviction/position fixes |
| `cron_thesis_maintenance.py` | 6:10 AM Mon-Fri | Auto-suggest theses, surface overdue reviews, conviction ceiling enforcement |
| `run_market_reaction.py` | Every 30 min (9-4pm) | News reaction scoring |
| `run_signal_engines.py` | Every 30 min (9-4pm) | Conviction velocity + crisis alpha signals |
| `run_stress_test.py` | 5:35 PM Mon-Fri | Portfolio VaR and scenario analysis |
| `run_meta_observer.py` | 5:40 PM Mon-Fri | Cross-instance divergence |
| `run_bug_monitor.py` | Every 2h Mon-Fri | Log scanning and bug detection |
| `run_ensemble.py` | After trade-decision | 3x consensus before execution |

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
| 17:30 | `/evening-research` | opus |
| Sun 16:30 | `/system-review` | opus |
| Sun 18:00 | `/thesis` | sonnet |
| Sun 19:00 | `/brainstorm` | opus |
| Sun 20:00 | `/theorist` | opus |

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

# Monitoring & Health
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard --watch
PYTHONPATH=. python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8000
python3 scripts/readiness_check.py                # Full system readiness check (11 categories)
python3 scripts/readiness_check.py --fix           # Auto-fix known issues
python3 scripts/readiness_check.py --category flow # Check cross-session flow only

# Data Collection
PYTHONPATH=. python scripts/collect_all_data.py --quick

# Signal Pipeline
PYTHONPATH=. python scripts/cron_signal_digest.py  # Aggregate all signals + convergences
PYTHONPATH=. python scripts/cron_market_movers.py           # After-close scan
PYTHONPATH=. python scripts/cron_market_movers.py --intraday # Midday (tighter thresholds)

# Conviction Velocity & Crisis Alpha Signals
PYTHONPATH=. python -c "from src.signals.conviction_velocity import ConvictionVelocityEngine; e = ConvictionVelocityEngine(); [print(f'{s.thesis_name}: {s.signal_direction} v={s.velocity_3d:+.1f}pp/d') for s in e.scan_all_theses()]"
PYTHONPATH=. python -c "from src.signals.crisis_alpha import CrisisAlphaEngine; e = CrisisAlphaEngine(); [print(s) for s in e.generate_signals()]"

# Portfolio Risk
PYTHONPATH=. python scripts/run_stress_test.py              # Full stress test report

# Multi-Instance Management
./scripts/instance_launcher.sh list                          # List all instances
./scripts/instance_launcher.sh create alpha API_KEY SECRET   # Create new instance
./scripts/instance_launcher.sh start alpha                   # Start instance
./scripts/instance_launcher.sh status all                    # Status of all instances

# Meta-Observer (cross-instance analysis)
PYTHONPATH=. python scripts/run_meta_observer.py             # Cross-instance divergence report

# Decision Ensemble
PYTHONPATH=. python scripts/run_ensemble.py                  # Run ensemble on pending decisions
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
