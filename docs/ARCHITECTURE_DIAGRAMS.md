# Project Athena: Complete Architecture Diagrams

This document maps all modules, functions, data flows, and integrations in the quant_suite package.

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           LAYER 1: SENTINEL (Python, zero Claude tokens)                 │
│                                  scripts/sentinel.py                                     │
│                                                                                         │
│  30s heartbeat │ Market state monitoring │ Convergence detection │ Trigger rules (6)    │
│  Writes: situation_board.json (same-day shared memory, auto-resets daily)                │
│  Triggers: analyst sessions when events need interpretation                             │
└─────────────────────────────────────────────────────────────┬───────────────────────────┘
                                                              │ triggers
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 2: REACTIVE AGENTS (Claude, on-demand, 3-10 min)               │
│                                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │  /analyst   │ │  /trade-    │ │  /execute-  │ │  /signal-   │ │  /operator-  │       │
│  │  (Sonnet)   │ │  decision   │ │  trades     │ │  scan       │ │  session     │       │
│  │  5 min      │ │  (Opus)     │ │  (Opus)     │ │  (Sonnet)   │ │  (Opus)      │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
└─────────────────────────────────────────────────────────────┬───────────────────────────┘
                                                              │ reads/writes
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 3: DEEP AGENTS (Claude, scheduled, 10-20 min)                  │
│                                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │  /morning-  │ │  /internal- │ │  /eod-      │ │  /theorist  │ │  /research   │       │
│  │  briefing   │ │  review     │ │  review     │ │  (Opus)     │ │  (Sonnet)    │       │
│  │  (Opus)     │ │  (Sonnet)   │ │  (Opus)     │ │  Weekly     │ │  On-demand   │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
└─────────────────────────────────────────────────────────────┬───────────────────────────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              SHARED MEMORY (Cross-Session)                               │
│                                                                                         │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐   │
│  │   state.json     │ │ situation_board  │ │ strategic_context│ │  signal_digest   │   │
│  │   (5 min)        │ │  (same-day)     │ │  (multi-day)    │ │  (30 min)        │   │
│  │                  │ │                  │ │                  │ │                  │   │
│  │ Market+Portfolio │ │ Observations     │ │ Thesis momentum │ │ Convergences     │   │
│  │ Signals+Theses  │ │ Alerts, triggers │ │ Patterns, hypos │ │ Signal quality   │   │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘   │
│                                                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │  athena.db (19 tables) — Permanent record: decisions, predictions, theses,       │   │
│  │  documents, insights, experiments, agent_runs, signal_provenance, process_events │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
│   KNOWLEDGE + INTELLIGENCE│ │      DECISION LAYER       │ │     DATA LAYER            │
│                           │ │      src/decision/        │ │     src/data/             │
│ ┌───────────────────────┐ │ │                           │ │                           │
│ │ ThesisTracker         │ │ │ DecisionLogger            │ │ 42 data source modules    │
│ │ + PriceTargets        │ │ │ AdversarialAgent          │ │ 16 RSS feeds              │
│ │ + SignalProvenance    │ │ │ MorningBriefing           │ │ Market mover scanner      │
│ │ + ThesisSuggester     │ │ │ DecisionContextBuilder    │ │ Finviz screens (8)        │
│ │ + BeliefUpdater       │ │ │ SessionContext            │ │ Social (WSB, Stocktwits)  │
│ │ + SetupScorer         │ │ │                           │ │ Geopolitical (5 regions)  │
│ │ + MarketMoverScanner  │ │ │ Predictions → Scoring →   │ │ Legal (SCOTUS, SEC, FTC)  │
│ │ + LearningLog         │ │ │ Belief updates → Better   │ │ Innovation (patents, etc) │
│ └───────────────────────┘ │ │ decisions (feedback loop)  │ │ Prediction markets        │
└───────────────────────────┘ └───────────────────────────┘ └───────────────────────────┘
```

---

## 2. Complete Module Map

### Core Layer (`src/core/`)
```
src/core/
├── __init__.py
├── paths.py           ──► Central path management, QUANT_RESULTS_DIR
├── types.py           ──► Type definitions, enums
├── signal.py          ──► Signal dataclass
├── order.py           ──► Order dataclass
├── position.py        ──► Position dataclass
├── asset.py           ──► Asset dataclass
├── strategy_config.py ──► Strategy configuration
├── strategy_spec.py   ──► Strategy specification
└── universe_manager.py ──► Symbol universe management
```

### Synthesis Layer (`src/synthesis/`) - NEW
```
src/synthesis/
├── __init__.py
├── state.py           ──► UnifiedState, MarketSnapshot, PortfolioSnapshot, etc.
├── signals.py         ──► AggregatedSignal, SignalAggregator
└── daemon.py          ──► LiveDaemon - continuous state updates
```

### Knowledge Layer (`src/knowledge/`) - Updated 2026-03-07
```
src/knowledge/
├── __init__.py
├── thesis.py              ──► Thesis, ThesisTracker, Signpost, PriceTarget (bull/base/bear)
├── thesis_performance.py  ──► ThesisPerformanceTracker, ThesisPerformanceMetrics
├── signal_provenance.py   ──► SignalProvenanceTracker, SignalSource enum, convergence support
├── thesis_suggester.py    ──► ThesisSuggester — auto-suggest from converging signals (2+ sources)
├── learnings.py           ──► Learning, LearningLog
├── base.py                ──► KnowledgeBase, CompanyBrief, SectorContext
└── market_calendar.py     ──► MarketCalendar, CalendarEvent, Prediction
```

### Swarm Layer (`src/swarm/`) - Added 2026-03-06
```
src/swarm/
├── __init__.py
├── situation_board.py     ──► SituationBoard: same-day shared memory, auto-resets daily, 5-min dedup
└── strategic_context.py   ──► StrategicContext: multi-day persistent (thesis momentum, patterns, catalysts)
```

### Context Layer (`src/context/`) - Added 2026-03-03
```
src/context/
├── __init__.py
├── session_context.py     ──► SessionContext: singleton accumulator for session events
└── market_snapshot.py     ──► capture_market_snapshot: SPY, VIX, sectors from state.json
```

### Intelligence Layer (`src/intelligence/`) - Added 2026-03-01, Updated 2026-03-07
```
src/intelligence/
├── __init__.py            ──► Convenience imports
├── context_builder.py     ──► DecisionContextBuilder — assembles track record, calibration, learnings
├── setup_types.py         ──► Canonical setup type taxonomy (11 types, 10 reasoning categories)
├── setup_scorer.py        ──► SetupScorer — performance by setup type from DecisionRecord
├── belief_updater.py      ──► BeliefUpdater — daily signal weight updates, thesis suggestions, calibration
├── market_movers.py       ──► MarketMoverScanner — broad universe scan + context enrichment
└── thesis_keywords.py     ──► Thesis keyword matching + extract_symbols_from_headline()
```

### Decision Layer (`src/decision/`)
```
src/decision/
├── __init__.py
├── decision_logger.py ──► TradingDecision, DecisionLogger
├── adversary.py       ──► AdversarialAgent, AdversarialAnalysis - NEW
├── morning_briefing.py ──► MorningBriefingGenerator
└── morning_open.py    ──► Morning open protocol
```

### Data Layer (`src/data/`)
```
src/data/
├── __init__.py
├── features.py        ──► FeatureEngine (50+ technical features)
│
├── sources/
│   ├── base.py        ──► BaseDataSource
│   ├── yahoo.py       ──► Yahoo Finance integration
│   │
│   ├── alternative/
│   │   ├── congressional_trades.py  ──► Congressional trading signals
│   │   ├── prediction_markets.py    ──► Polymarket, Kalshi
│   │   ├── expert_sentiment.py      ──► Cramer inverse, pundit tracking
│   │   ├── insider.py               ──► SEC Form 4 parsing
│   │   ├── options_flow.py          ──► Unusual options activity
│   │   ├── news.py                  ──► News sentiment
│   │   ├── reddit.py                ──► Reddit/WSB sentiment
│   │   ├── short_interest.py        ──► Short interest data
│   │   ├── institutional_flow.py    ──► 13F filings
│   │   ├── iv_rank.py               ──► IV percentile rank
│   │   ├── etf_flows.py             ──► ETF flow tracking
│   │   ├── weather.py               ──► Weather data (commodities)
│   │   ├── google_trends.py         ──► Google Trends
│   │   │
│   │   │  # Free Data Sources (Added 2026-01-10)
│   │   │  # Reason: Expand signal diversity at zero cost, activate latent knowledge
│   │   ├── vix_structure.py         ──► VIX term structure (CBOE)
│   │   ├── put_call.py              ──► Put/call ratios (CBOE)
│   │   ├── finviz_screens.py        ──► Pre-built stock screens
│   │   ├── aaii_sentiment.py        ──► AAII retail sentiment (weekly)
│   │   ├── newsletter_sentiment.py  ──► Investors Intelligence
│   │   ├── cot_report.py            ──► CFTC Commitment of Traders
│   │   ├── earnings_calendar.py     ──► Earnings with whisper numbers
│   │   ├── economic_calendar.py     ──► BLS, Fed, Treasury releases
│   │   ├── fed_futures.py           ──► CME FedWatch rate expectations
│   │   ├── treasury_calendar.py     ──► Treasury auction schedule
│   │   ├── ipo_calendar.py          ──► NASDAQ IPO calendar
│   │   ├── fda_calendar.py          ──► PDUFA dates, AdCom meetings
│   │   ├── patent_filings.py        ──► USPTO patent activity
│   │   ├── job_postings.py          ──► Job posting growth signals
│   │   ├── app_rankings.py          ──► App Store/Play rankings
│   │   ├── github_activity.py       ──► GitHub org metrics
│   │   │
│   │   │  # Hedge Fund Expansion (Added 2026-01-20)
│   │   │  # Reason: Comprehensive market intelligence and event monitoring
│   │   ├── expanded_news.py         ──► 20+ RSS feeds (WSJ, CNBC, FT, Fed, SEC)
│   │   ├── legal_tracker.py         ──► SCOTUS, SEC, FTC, DOJ tracking
│   │   ├── geopolitical.py          ──► Regional event monitoring (5 regions)
│   │   ├── news_sentiment.py        ──► Keyword sentiment scoring
│   │   │
│   │   │  # Social Signal Tracking (Added 2026-02-01)
│   │   │  # Reason: Catch early alpha from social platforms, track signal provenance
│   │   ├── wsb_tracker.py           ──► NEW: Reddit WSB scanning with signal vintage
│   │   ├── stocktwits.py            ──► NEW: Stocktwits API integration
│   │   └── social_timeseries.py     ──► NEW: SQLite time-series for social mentions
│   │
│   ├── collection_daemon.py         ──► Orchestrates all free data sources (Added 2026-01-10)
│   │
│   ├── realtime/
│   │   ├── news_daemon.py           ──► Continuous news monitoring
│   │   └── social_sentiment.py      ──► Social media tracking
│   │
│   ├── web/
│   │   ├── scraper.py               ──► Web scraping base
│   │   ├── news_scraper.py          ──► News site scraping
│   │   └── sec_filings.py           ──► SEC EDGAR scraping
│   │
│   └── universal/
│       ├── free_api_hub.py          ──► Free API aggregator (FRED, etc.)
│       ├── commodity_scraper.py     ──► Commodity price scraping
│       └── blog_scraper.py          ──► Industry blog scraping
│
├── pipeline/
│   ├── core.py                ──► Core data pipeline
│   ├── market_breadth.py      ──► Market breadth analysis
│   ├── sentiment.py           ──► Sentiment aggregation
│   ├── intraday_technicals.py ──► Real-time technical analysis
│   ├── options_analytics.py   ──► Options Greeks, analytics
│   └── intraday.py            ──► Intraday data processing
│
├── feature_engineering/
│   ├── feature_store.py       ──► DuckDB feature storage
│   ├── feature_registry.py    ──► Feature metadata
│   ├── feature_stability.py   ──► Feature stability analysis
│   ├── feature_interactions.py ──► Feature interaction discovery
│   ├── feature_discovery.py   ──► Automated feature discovery
│   └── text_embeddings.py     ──► Text to embedding features
│
├── calendars/
│   └── calendar_manager.py    ──► Earnings, Fed, economic calendar
│
├── nlp/
│   └── pipeline.py            ──► NLP processing pipeline
│
└── synthesis/
    └── llm_extractor.py       ──► LLM-based data extraction
```

### Strategy Layer (`src/strategies/`)
```
src/strategies/
├── __init__.py
├── base.py            ──► BaseStrategy
├── definition.py      ──► Strategy definition utilities
│
├── traditional/
│   ├── trend_following.py     ──► Trend following strategies
│   ├── mean_reversion.py      ──► Mean reversion strategies
│   └── factor_models.py       ──► Factor-based strategies
│
├── ml/
│   ├── classical.py           ──► XGBoost, LightGBM, Random Forest
│   └── deep_learning.py       ──► LSTM, Transformer models
│
├── regime/
│   └── regime_classifier.py   ──► Market regime classification
│
├── intraday/
│   ├── base.py                ──► Intraday base strategy
│   ├── vwap.py                ──► VWAP strategies
│   └── momentum.py            ──► Intraday momentum
│
├── options/
│   ├── iv_crush_detector.py   ──► IV crush detection
│   └── venezuela_options.py   ──► Venezuela thesis options plays
│
├── alternative/
│   ├── sentiment.py           ──► Sentiment-based strategies
│   ├── contrarian.py          ──► Contrarian indicators
│   ├── correlation.py         ──► Correlation-based strategies
│   ├── narrative_momentum.py  ──► News narrative momentum
│   ├── sec_alpha.py           ──► SEC filing alpha
│   ├── renaissance.py         ──► RenTech-style strategies
│   ├── embeddings.py          ──► Embedding-based strategies
│   └── composite_alternative.py ──► Composite alt strategy
│
├── lead_lag/
│   └── lead_lag_strategy.py   ──► Lead-lag relationship strategies
│
└── commodity_mean_rev/
    └── commodity_mean_rev_strategy.py ──► Commodity mean reversion
```

### Evaluation Layer (`src/evaluation/`)
```
src/evaluation/
├── __init__.py
├── reporting.py       ──► Report generation
│
├── backtest/
│   ├── engine.py              ──► Core backtesting engine
│   ├── costs.py               ──► Transaction cost modeling
│   ├── execution_model.py     ──► Execution simulation
│   ├── options_pricer.py      ──► Options pricing (Black-Scholes)
│   └── options_backtest.py    ──► Options strategy backtesting
│
├── validation/
│   ├── mcpt.py                ──► Monte Carlo Permutation Test ***CRITICAL***
│   ├── walk_forward.py        ──► Walk-forward validation
│   ├── purged_cv.py           ──► Purged cross-validation
│   ├── holdout.py             ──► Holdout testing
│   ├── regime.py              ──► Regime-based validation
│   ├── hypothesis_testing.py  ──► Statistical hypothesis tests
│   └── pdt_framework.py       ──► PDT-aware validation
│
├── metrics/
│   ├── returns.py             ──► Return metrics (Sharpe, Sortino, etc.)
│   ├── risk.py                ──► Risk metrics (VaR, max drawdown)
│   └── statistical.py         ──► Statistical metrics
│
├── comparison/                ──► Strategy Comparison (Added 2026-01-11)
│   └── dashboard.py           ──► StrategyDashboard, StrategyComparison
│
└── attribution/
    └── factor_model.py        ──► Performance attribution
```

### Execution Layer (`src/execution/`)
```
src/execution/
├── __init__.py
├── orchestrator.py    ──► Trading orchestrator
├── order_manager.py   ──► Order management
├── pdt_manager.py     ──► PDT rule enforcement + holiday calendar (Updated 2026-01-11)
├── approval.py        ──► Human approval workflow
│
├── broker/
│   ├── base.py                ──► Base broker interface
│   ├── alpaca.py              ──► Alpaca API integration
│   └── paper.py               ──► Paper trading simulation
│
├── pipeline/
│   ├── daily_signals.py       ──► Daily signal generation
│   └── order_executor.py      ──► Order execution pipeline
│
├── promotion/                 ──► Strategy Promotion Pipeline (Added 2026-01-11)
│   └── pipeline.py            ──► PromotionPipeline, PromotionCandidate, PromotionGates
│
└── monitoring/
    ├── dashboard.py           ──► Web dashboard
    └── cli_dashboard.py       ──► CLI monitoring
```

### Risk Layer (`src/risk/`)
```
src/risk/
├── __init__.py
├── position_monitor.py  ──► Real-time position monitoring, VaR
├── position_sizing.py   ──► Kelly criterion, volatility-adjusted sizing
└── limits.py            ──► Risk limits enforcement
```

### Text Research Layer (`src/text_research/`)
```
src/text_research/
├── __init__.py
├── corpus.py            ──► TextCorpus - point-in-time document storage (DuckDB)
├── embedding_engine.py  ──► Multi-model embedding generation
├── signal_generator.py  ──► Text-to-signal conversion
├── feature_extractor.py ──► Text feature extraction
├── backtest.py          ──► Text strategy backtesting
│
└── ingestors/
    ├── sec.py           ──► SEC filing ingestion
    └── news.py          ──► News ingestion
```

### Alerts Layer (`src/alerts/`)
```
src/alerts/
├── __init__.py
├── alert_manager.py   ──► Alert monitoring and notification
├── alert_types.py     ──► Alert type definitions
├── smart_alerter.py   ──► Signal convergence detection (Added 2026-01-20)
└── mobile_bot.py      ──► Telegram/Discord mobile alerts (Added 2026-01-20)
```

### Real-Time Data Layer (`src/data/realtime/`)
```
src/data/realtime/
├── __init__.py
├── websocket_feed.py  ──► WebSocket price feeds: Alpaca, Finnhub, polling (Added 2026-01-20)
└── news_daemon.py     ──► Continuous news monitoring
```

### Risk Layer (`src/risk/`)
```
src/risk/
├── __init__.py
├── position_monitor.py   ──► Real-time position monitoring, VaR
├── position_sizing.py    ──► Kelly criterion, volatility-adjusted sizing
├── limits.py             ──► Risk limits enforcement
└── portfolio_optimizer.py ──► Risk parity, mean-variance, Kelly (Added 2026-01-20)
```

### Execution Layer Extended (`src/execution/`)
```
src/execution/
├── rules_engine.py        ──► Automated execution rules (Added 2026-01-20)
└── drawdown_protection.py ──► 5-level drawdown protection (Added 2026-01-20)
```

### Tax Layer (`src/tax/`)
```
src/tax/
├── __init__.py
└── tax_loss_harvester.py  ──► Tax-loss harvesting, wash sale tracking (Added 2026-01-20)
```

### Analysis Layer (`src/analysis/`)
```
src/analysis/
├── __init__.py
└── earnings_predictor.py  ──► 7-signal earnings surprise predictor (Added 2026-01-20)
```

### Knowledge Layer Extended (`src/knowledge/`)
```
src/knowledge/
├── trade_journal.py           ──► Automated trade journal with context (Added 2026-01-20)
├── performance_attribution.py ──► Performance attribution by thesis/signal (Added 2026-01-20)
└── ... (existing files)
```

### Synthesis Layer Extended (`src/synthesis/`)
```
src/synthesis/
├── sector_rotation.py     ──► Sector leadership & cycle tracking (Added 2026-01-20)
└── ... (existing files)
```

### Database Layer (`src/db/`) - Added 2026-03-01, Updated 2026-03-07
```
src/db/
├── __init__.py
├── database.py        ──► SQLAlchemy engine, session management, get_db()
├── models.py          ──► All ORM models (19 tables):
│                          ├── ThesisRecord, SignpostRecord, thesis_position_links
│                          ├── DecisionRecord, PredictionRecord
│                          ├── LearningRecord, learning_tags
│                          ├── AgentRun, LLMInteraction
│                          ├── Document, Insight, Experiment
│                          ├── ProcessEvent, SignalProvenanceRecord
│                          ├── Company, Sector
│                          ├── decision_signal_links, decision_convergences
│                          └── autonomy_checks
├── write_api.py       ──► AthenaWriteAPI singleton (athena_db):
│                          ├── save_document(), search_documents()
│                          ├── get_documents_for_symbol()
│                          ├── save_thesis(), save_decision()
│                          └── update_price_targets()
├── sync.py            ──► File sync (signal provenance, JSONL append)
└── migrate.py         ──► Backfill script: scans ~/quant_results/ and indexes all files
```

### Monitoring Layer (`src/monitoring/`) - Updated 2026-02-01
```
src/monitoring/
├── __init__.py
├── unified_dashboard.py       ──► Full system status + signals + convergences
├── swarm_monitor.py           ──► NEW: Track agent swarms, detect signal convergences
├── swarm_visualizer.py        ──► NEW: Timeline + heatmap displays for swarm activity
├── operator_loop.py           ──► Persistent monitoring check cycles
├── data_freshness_tracker.py  ──► Track data source status WITH content summaries
├── signal_summary.py          ──► Aggregate all signals into actionable items
├── improvement_tracker.py     ──► Auto-generated improvement suggestions
└── signal_quality_tracker.py  ──► Track signal hit rates over time
```

### Web Layer (`src/web/`) - Added 2026-03-01, Updated 2026-03-07
```
src/web/
├── __init__.py
├── app.py                ──► FastAPI app, 26 routers, CORS, Jinja2 templates
│
├── routes/ (26 modules)
│   ├── dashboard.py      ──► / (main dashboard with portfolio, activity feed)
│   ├── portfolio.py      ──► /portfolio (positions, allocation, P&L)
│   ├── decisions.py      ──► /decisions (list + detail + context panels)
│   ├── theses.py         ──► /theses (CRUD, conviction, signposts, price targets)
│   ├── signals.py        ──► /signals (live signals, convergences)
│   ├── movers.py         ──► /movers (market mover scanner: gainers, losers, volume)
│   ├── swarm.py          ──► /swarm (situation board, strategic context, sentinel)
│   ├── sessions.py       ──► /sessions (autonomous session timeline)
│   ├── intelligence.py   ──► /intelligence (predictions, calibration, setup perf)
│   ├── reviews.py        ──► /reviews (EOD reviews, internal reviews, briefings)
│   ├── documents.py      ──► /documents (universal browser + insights + experiments)
│   ├── agents.py         ──► /agents (agent runs, ops center)
│   ├── research.py       ──► /research (experiments, insights)
│   ├── data_sources.py   ──► /data (data source freshness grid)
│   ├── knowledge.py      ──► /knowledge (company + sector briefs)
│   ├── learnings.py      ──► /learnings (trade learnings)
│   ├── usage.py          ──► /usage (LLM token tracking)
│   ├── system.py         ──► /system (health, autonomy status)
│   ├── flows.py          ──► /flows (process events activity feed)
│   ├── reports.py        ──► /reports
│   ├── upload.py         ──► /upload
│   ├── llm.py            ──► /llm
│   ├── tasks.py          ──► /tasks (background task management)
│   ├── api.py            ──► /api (JSON endpoints)
│   └── websocket.py      ──► WebSocket for live feed
│
├── services/
│   ├── state_service.py       ──► Read unified state, portfolio summary
│   ├── document_service.py    ──► Document queries (list, filter, search)
│   ├── thesis_service.py      ──► Thesis CRUD with dual-write (YAML + DB)
│   ├── decision_service.py    ──► Decision queries + context panels
│   ├── mover_service.py       ──► Market mover scan data for web UI
│   ├── swarm_service.py       ──► Situation board + strategic context for web UI
│   ├── review_service.py      ──► EOD reviews, briefings, internal reviews
│   ├── intelligence_service.py ──► Predictions, calibration, setup type performance
│   ├── portfolio_service.py   ──► Portfolio data from Alpaca
│   ├── flow_service.py        ──► Process events for activity feed
│   ├── system_service.py      ──► System health, autonomy status
│   └── task_manager.py        ──► Background task lifecycle
│
└── templates/ (21 template directories, Tailwind + HTMX, dark theme)
```

---

## 3. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  EXTERNAL DATA SOURCES                                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
         │              │              │              │              │
    Yahoo Finance   Alpaca API    Web Scraping   Free APIs     SEC EDGAR
         │              │              │              │              │
         ▼              ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   DATA INGESTION                                        │
│                                                                                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ yahoo.py     │ │ alpaca.py    │ │ news_daemon  │ │ free_api_hub │ │ sec_filings  │   │
│  │              │ │              │ │              │ │              │ │              │   │
│  │ • OHLCV      │ │ • Account    │ │ • Real-time  │ │ • FRED       │ │ • 10-K/10-Q  │   │
│  │ • Splits     │ │ • Positions  │ │   news       │ │ • Weather    │ │ • 8-K        │   │
│  │ • Dividends  │ │ • Orders     │ │ • Sentiment  │ │ • Commodities│ │ • Form 4     │   │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘   │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────┼───────────┘
          │                │                │                │                │
          ▼                ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FEATURE ENGINEERING                                     │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                           features.py - FeatureEngine                           │    │
│  │                                                                                 │    │
│  │  Technical (50+)         Alternative Data          Text Features                │    │
│  │  • RSI, MACD, BB         • Congressional signals   • Embeddings                 │    │
│  │  • Momentum (5/10/20d)   • Insider signals         • Sentiment scores           │    │
│  │  • Volume patterns       • Options flow            • Named entities             │    │
│  │  • Support/Resistance    • Social sentiment        • Topic clusters             │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                         │                                               │
│                                         ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                      feature_store.py - DuckDB Storage                          │    │
│  │                                                                                 │    │
│  │  • Versioned features    • Point-in-time safety    • Fast retrieval             │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  SIGNAL GENERATION                                      │
│                                                                                         │
│  ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌─────────────────┐  │
│  │  Traditional      │ │  ML Strategies    │ │  Alternative      │ │  Regime         │  │
│  │                   │ │                   │ │                   │ │                 │  │
│  │ • Trend following │ │ • XGBoost         │ │ • Sentiment       │ │ • Risk-on/off   │  │
│  │ • Mean reversion  │ │ • LightGBM        │ │ • Congressional   │ │ • Transitioning │  │
│  │ • Factor models   │ │ • LSTM            │ │ • Contrarian      │ │                 │  │
│  └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘ └────────┬────────┘  │
│            │                     │                     │                    │           │
│            └─────────────────────┼─────────────────────┼────────────────────┘           │
│                                  ▼                     ▼                                │
│                    ┌─────────────────────────────────────────────────┐                  │
│                    │         SignalAggregator (signals.py)           │                  │
│                    │                                                 │                  │
│                    │  • Composite score (weighted)                   │                  │
│                    │  • Signal agreement (0-1)                       │                  │
│                    │  • Confidence calculation                       │                  │
│                    └─────────────────────┬───────────────────────────┘                  │
└──────────────────────────────────────────┼──────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   UNIFIED STATE                                         │
│                                                                                         │
│                          ~/quant_results/live/state.json                                │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │  {                                                                              │    │
│  │    "timestamp": "...",                                                          │    │
│  │    "market_open": true,                                                         │    │
│  │    "market": { spy_price, vix, regime, ... },                                   │    │
│  │    "sentiment": { fear_greed, put_call, ... },                                  │    │
│  │    "portfolio": { equity, cash, positions, ... },                               │    │
│  │    "risk": { var, correlation_risk, ... },                                      │    │
│  │    "watchlist_signals": { "SLB": {...}, "HAL": {...} },                         │    │
│  │    "theses": [ { name, conviction, signposts, ... } ],                          │    │
│  │    "pending_decisions": [ ... ],                                                │    │
│  │    "recent_learnings": [ ... ],                                                 │    │
│  │    "alerts": [ ... ],                                                           │    │
│  │    "research": { features_file, signals_file, ... }                             │    │
│  │  }                                                                              │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│     DECISION MAKING    │   │    KNOWLEDGE BASE      │   │     EXECUTION          │
│                        │   │                        │   │                        │
│ /trade-decision        │   │  ~/quant_results/      │   │ /execute-trades        │
│                        │   │                        │   │                        │
│ ┌────────────────────┐ │   │ ├── theses/            │   │ ┌────────────────────┐ │
│ │ AdversarialAgent   │ │   │ │   └── *.yaml         │   │ │ PDT Manager        │ │
│ │                    │ │   │ │                      │   │ │                    │ │
│ │ • Challenge trade  │ │   │ ├── learnings/         │   │ │ • Day trade count  │ │
│ │ • Timing concerns  │ │   │ │   └── 2026-01.json   │   │ │ • Hold enforcement │ │
│ │ • Adjust confidence│ │   │ │                      │   │ └────────────────────┘ │
│ └────────────────────┘ │   │ ├── knowledge/         │   │                        │
│                        │   │ │   ├── companies/     │   │ ┌────────────────────┐ │
│ ┌────────────────────┐ │   │ │   │   └── SLB.yaml   │   │ │ Risk Limits        │ │
│ │ DecisionLogger     │ │   │ │   └── sectors/       │   │ │                    │ │
│ │                    │ │   │ │       └── energy.yaml│   │ │ • Position max 25% │ │
│ │ • Log decision     │ │   │ │                      │   │ │ • Sector max 40%   │ │
│ │ • Link to thesis   │ │   │ └── decisions/         │   │ │ • Daily loss 5%    │ │
│ │ • Pre-mortem       │ │   │     └── decisions_*.json│  │ └────────────────────┘ │
│ └────────────────────┘ │   │                        │   │                        │
└────────────────────────┘   └────────────────────────┘   │ ┌────────────────────┐ │
                                                          │ │ Alpaca Broker      │ │
                                                          │ │                    │ │
                                                          │ │ • Submit orders    │ │
                                                          │ │ • Monitor fills    │ │
                                                          │ └────────────────────┘ │
                                                          └────────────────────────┘
```

---

## 4. Daily Workflow Diagram (Updated 2026-03-08)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS TRADING DAY (Swarm Architecture)                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

Architecture: cron → athena_scheduler.sh (tmux) → session_wrapper.sh → claude
Coordination: ~/quant_results/scheduler/ (state, triggers, completions, locks)

 TIME (ET)     LAYER        SESSION                 MODEL    PURPOSE
─────────────────────────────────────────────────────────────────────────────────────────

 05:55         Sentinel     sentinel-start           Python   Start monitoring daemon
                            │  30s heartbeat, zero Claude tokens
                            │  Maintains situation_board.json
                            │  6 trigger rules, regime-adaptive intervals
                            │

 06:00         Background   collect_all_data.py      cron     Data collection begins
                            │  42 sources, every 30 min (--quick) / 2h (full)
                            │  cron_signal_digest.py every 30 min
                            │  signpost_monitor.py every 10 min (9am-3pm)
                            │

 06:30         Deep Agent   /morning-briefing        Opus     Overnight news, thesis review
                            │  Reads: state.json + situation_board + strategic_context
                            │  Searches: overnight news, sector developments
                            │  Reviews: active theses, signpost triggers, belief updates
                            │  Checks: market movers, signal convergences, price targets
                            │  Output: ~/quant_results/briefings/briefing_YYYYMMDD.json
                            │

 08:30         Reactive     /operator-session        Opus     Persistent monitoring
                            │  Reads situation board every check cycle
                            │  Pushes observations to SessionContext
                            │  Writes convergences to situation_board.json
                            │  Runs until 16:05
                            │

 09:31         Execution    Scheduled trades                  From previous day's decisions
                            │

 10:00         Deep Agent   /trade-decision          Opus     Morning trade pass
                            │  Step 0: Context builder (track record, calibration)
                            │  Step 0b: Situation board + strategic context
                            │  Step 1-3: Thesis alignment, signals, adversarial challenge
                            │  Step 4: Decision + pre-mortem + price targets
                            │  Step 4b: Write to situation board
                            │  Step 7: Auto-create predictions
                            │  Output: ~/quant_results/decisions/
                            │

 10:30         Reactive     /signal-scan             Sonnet   Social signal analysis
                            │  WSB, Stocktwits, prediction markets
                            │  LLM analysis of emerging themes
                            │

 12:00         Deep Agent   /internal-review         Sonnet   Self-assessment #1
                            │  Prediction accuracy, signal drift, thesis health
                            │  Updates strategic_context.json (thesis momentum, patterns)
                            │

 12:30         Background   cron_market_movers.py    cron     Midday mover scan (--intraday)
                            │  ~400 symbols, tighter thresholds (2% day move)
                            │  Enriches with news, Finviz, WSB, thesis alignment
                            │  Registers SignalProvenance (source=STATISTICAL)
                            │

 13:00         Deep Agent   /trade-decision          Opus     Afternoon trade pass
                            │

 14:30         Reactive     /signal-scan             Sonnet   Second social signal pass
                            │

 15:00         Deep Agent   /internal-review         Sonnet   Self-assessment #2
                            │

 16:05                      Operator stops
                            │

 16:30         Deep Agent   /eod-review              Opus     End-of-day analysis
                            │  Portfolio performance vs SPY, sector benchmarks
                            │  Decision outcome analysis
                            │  Learning extraction → ~/quant_results/learnings/
                            │  Thesis conviction updates
                            │  Tomorrow's focus areas
                            │  Output: ~/quant_results/reviews/eod_review_YYYYMMDD.json
                            │

 17:10                      Sentinel stops
 17:15         Background   cron_prediction_scorer   cron     Score predictions
 17:20         Background   cron_market_movers.py    cron     After-close mover scan (broad)
 17:30         Background   cron_belief_update       cron     Update signal weights


 SUNDAY (Weekly Deep Sessions)
─────────────────────────────────────────────────────────────────────────────────────────
 18:00         Deep Agent   /thesis                  Opus     Weekly thesis review
 19:00         Deep Agent   /brainstorm              Sonnet   Strategy and feature ideation
 20:00         Deep Agent   /theorist                Opus     Scenario planning, blind spots


 CONTINUOUS (Background Daemons)
─────────────────────────────────────────────────────────────────────────────────────────

 LiveDaemon    every 5 min    Write state.json (market + portfolio + signals)
 Sentinel      10-60s         Monitor for trigger events, maintain situation board
 Data cron     every 30 min   collect_all_data.py --quick (news + thesis matching)
 Data cron     every 2h       collect_all_data.py (full 13-source collection)
 Digest cron   every 30 min   cron_signal_digest.py (aggregation + convergences)
 Signpost      every 10 min   signpost_monitor.py (thesis price signpost checks)


 EVENT-DRIVEN (Sentinel Triggers)
─────────────────────────────────────────────────────────────────────────────────────────

 Sentinel detects:             Spawns:
   convergence (3+ signals)  →  /analyst (Sonnet, 5 min)
   signpost_hit              →  /analyst
   position_alert (±5%)      →  /analyst
   vix_spike (VIX > 30)      →  /analyst
   regime_change              →  /analyst
   urgent_news                →  /analyst
```

---

## 5. Research & Validation Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            RESEARCH & VALIDATION PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  IDEA GENERATION                                                                        │
│                                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ /brainstorm      │  │ Alpha Discovery  │  │ Hypothesis Gen   │  │ Macro Research   │ │
│  │                  │  │ Agent            │  │ Agent            │  │ Agent            │ │
│  │ • Feature ideas  │  │                  │  │                  │  │                  │ │
│  │ • Strategy vars  │  │ • Market scans   │  │ • Text → signal  │  │ • Geopolitical   │ │
│  │ • Gap analysis   │  │ • Anomalies      │  │ • Correlations   │  │ • Economic       │ │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘ │
│           └─────────────────────┴─────────────────────┴─────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  STRATEGY DEVELOPMENT                                                                   │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │  /research - Research Agent                                                     │    │
│  │                                                                                 │    │
│  │  1. Define strategy parameters                                                  │    │
│  │     └─► strategy_spec.py                                                        │    │
│  │                                                                                 │    │
│  │  2. Compute features                                                            │    │
│  │     └─► FeatureEngine.compute(symbols, start, end)                              │    │
│  │                                                                                 │    │
│  │  3. Generate signals                                                            │    │
│  │     └─► Strategy.generate_signals(features)                                     │    │
│  │                                                                                 │    │
│  │  4. Initial backtest                                                            │    │
│  │     └─► BacktestEngine.run(strategy, data)                                      │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  VALIDATION SUITE                                                                       │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │  /validate - Full Validation                                                    │    │
│  │                                                                                 │    │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐ │    │
│  │  │  1. MCPT (Monte Carlo Permutation Test)  ***CRITICAL***                    │ │    │
│  │  │     └─► mcpt.py                                                            │ │    │
│  │  │     └─► Shuffle returns 1000x, compute p-value                             │ │    │
│  │  │     └─► REQUIRED: p < 0.05                                                 │ │    │
│  │  └────────────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                                 │    │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐ │    │
│  │  │  2. Walk-Forward Validation                                                │ │    │
│  │  │     └─► walk_forward.py                                                    │ │    │
│  │  │     └─► Train on window, test on next period, roll forward                 │ │    │
│  │  │     └─► Check OOS Sharpe > 0.5                                             │ │    │
│  │  └────────────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                                 │    │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐ │    │
│  │  │  3. Regime Validation                                                      │ │    │
│  │  │     └─► regime.py                                                          │ │    │
│  │  │     └─► Test across risk-on, risk-off, transitioning                       │ │    │
│  │  └────────────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                                 │    │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐ │    │
│  │  │  4. Purged Cross-Validation                                                │ │    │
│  │  │     └─► purged_cv.py                                                       │ │    │
│  │  │     └─► Prevents lookahead bias in time series                             │ │    │
│  │  └────────────────────────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  SAFETY CHECK                                                                           │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │  /critic - Critic Agent                                                         │    │
│  │                                                                                 │    │
│  │  Checks for:                                                                    │    │
│  │  • Lookahead bias (using future data)                                           │    │
│  │  • Overfitting (too many parameters)                                            │    │
│  │  • Data leakage (train/test contamination)                                      │    │
│  │  • Survivorship bias                                                            │    │
│  │  • Unrealistic assumptions                                                      │    │
│  │  • Implementation bugs                                                          │    │
│  │                                                                                 │    │
│  │  REQUIRED: Pass all checks before promotion                                     │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  PROMOTION                                                                              │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │  /promote - Strategy Promoter                                                   │    │
│  │                                                                                 │    │
│  │  Requirements:                                                                  │    │
│  │  ✓ MCPT p-value < 0.05                                                          │    │
│  │  ✓ OOS Sharpe > 0.5                                                             │    │
│  │  ✓ Critic validation passed                                                     │    │
│  │  ✓ Walk-forward consistent                                                      │    │
│  │                                                                                 │    │
│  │  Promotion path:                                                                │    │
│  │  Research → Paper Trading → Live Trading                                        │    │
│  │                                                                                 │    │
│  │  OUTPUT: config/production/strategies/{strategy}.yaml                           │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Claude Agent Network

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               CLAUDE AGENT NETWORK                                      │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────────┐
                              │  orchestrator-agent │
                              │                     │
                              │  Coordinates multi- │
                              │  agent workflows    │
                              └──────────┬──────────┘
                                         │
           ┌─────────────────────────────┼─────────────────────────────┐
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   RESEARCH TRACK    │    │  INTELLIGENCE TRACK │    │   OPERATIONS TRACK  │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   research-agent    │    │ macro-research-agent│    │    critic-agent     │
│                     │    │                     │    │                     │
│ • Full research     │    │ • Geopolitical      │    │ • Safety validation │
│ • Strategy testing  │    │ • Economic factors  │    │ • Bias detection    │
│ • MCPT validation   │    │ • Fed policy        │    │ • Overfitting check │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│research-worker-agent│    │  news-analyst-agent │    │   monitor-agent     │
│                     │    │                     │    │                     │
│ • Parallel testing  │    │ • Event analysis    │    │ • Portfolio health  │
│ • Sector research   │    │ • Earnings impact   │    │ • Performance track │
│                     │    │ • News sentiment    │    │ • Anomaly detection │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│alpha-discovery-agent│    │regime-detector-agent│    │data-acquisition-agt │
│                     │    │                     │    │                     │
│ • Market scans      │    │ • Regime classify   │    │ • Free API data     │
│ • Anomaly detection │    │ • Strategy adjust   │    │ • Web scraping      │
│ • Momentum/reversal │    │ • Risk assessment   │    │ • Novel sources     │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
           │
           ▼
┌─────────────────────┐    ┌─────────────────────┐
│hypothesis-gen-agent │    │  brainstorm-agent   │
│                     │    │                     │
│ • Text → signals    │    │ • Feature ideas     │
│ • Correlation mining│    │ • Strategy variants │
│ • Testable hypotheses│   │ • Gap analysis      │
└─────────────────────┘    └─────────────────────┘
```

---

## 7. Storage Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              ~/quant_results/ DIRECTORY                                 │
└─────────────────────────────────────────────────────────────────────────────────────────┘

~/quant_results/
│
├── live/                          *** THE SOURCE OF TRUTH ***
│   ├── state.json                 ◄── Read this first! (market + portfolio + signals)
│   ├── market_movers_latest.json  ◄── Latest mover scan (50 movers, 231 universe)
│   ├── news_cache.json            ◄── Cached news with thesis keyword matches
│   ├── data_cache/                ◄── VIX, put/call, AAII, COT, Fed, earnings cache
│   └── research/                  ◄── Pre-computed features, signals, screens
│
├── athena.db                      *** SQLITE DATABASE (19 tables) ***
│                                  ◄── decisions, predictions, theses, signposts
│                                  ◄── documents, insights, experiments
│                                  ◄── signal_provenance, process_events
│                                  ◄── agent_runs, llm_interactions
│
├── scheduler/                     *** SWARM COORDINATION (Added 2026-03-06) ***
│   ├── situation_board.json       ◄── Same-day shared memory (sentinel → all)
│   ├── strategic_context.json     ◄── Multi-day persistent memory (reviewer → all)
│   ├── signal_digest.json         ◄── Aggregated signals with convergences
│   ├── scheduler_state.json       ◄── Session lifecycle tracking
│   ├── trade_triggers.json        ◄── Convergences awaiting trade decisions
│   ├── completions/               ◄── Session completion records
│   └── locks/                     ◄── Session mutex locks
│
├── theses/                        *** INVESTMENT THESES (YAML, dual-write to DB) ***
│
├── intelligence/                  *** COMPOUNDING INTELLIGENCE (Added 2026-03-01) ***
│   ├── calibration.json           ◄── Confidence calibration bins
│   ├── metrics_history.jsonl      ◄── Daily performance metrics
│   └── daily_update_*.json        ◄── Belief update reports
│
├── signal_provenance/             *** SIGNAL TRACKING (22 active signals) ***
│
├── decisions/                     *** TRADING DECISIONS (JSON per day) ***
├── briefings/                     *** MORNING BRIEFINGS ***
├── reviews/                       *** Internal + EOD reviews ***
├── learnings/                     *** MONTHLY TRADE LEARNINGS ***
├── knowledge/                     *** COMPANY/SECTOR BRIEFS ***
│
├── social/                        *** SOCIAL SIGNAL TRACKING ***
│   ├── wsb.db                     ◄── WSB mention database
│   ├── wsb_signals.json           ◄── Latest WSB signals
│   └── social_timeseries.db       ◄── Social mention time series
│
├── scraped_data/finviz/           *** FINVIZ SCREEN CACHE ***
│   └── screens_latest.json        ◄── 8 screens, sorted by relevance
│
├── logs/                          *** OPERATIONAL LOGS ***
│   ├── operator_log.jsonl
│   ├── sentinel.log
│   └── market_movers.log
│
└── research_results/              *** AUTO-INDEXED RESEARCH OUTPUT ***
```

---

## 8. Integration Matrix

This shows which modules use which other modules:

```
                          CONSUMER (reads from)
                    ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
                    │state│sigag│thetr│learn│knowb│decis│adver│featr│backT│
PROVIDER (used by)  │.py  │.py  │.py  │.py  │.py  │log  │.py  │.py  │eng  │
┌───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ paths.py          │  ✓  │  ✓  │  ✓  │  ✓  │  ✓  │  ✓  │     │  ✓  │  ✓  │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ yahoo.py          │     │     │     │     │     │     │     │  ✓  │  ✓  │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ alpaca.py         │  ✓  │     │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ features.py       │     │  ✓  │     │     │     │     │     │     │  ✓  │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ market_breadth.py │  ✓  │  ✓  │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ sentiment.py      │  ✓  │  ✓  │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ intraday_tech.py  │     │  ✓  │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ position_monitor  │  ✓  │     │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ thesis.py         │  ✓  │     │     │     │     │  ✓  │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ learnings.py      │  ✓  │     │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ base.py (kb)      │     │     │     │     │     │  ✓  │  ✓  │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ decision_logger   │  ✓  │     │     │  ✓  │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ adversary.py      │     │     │     │     │     │  ✓  │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ strategies/*      │     │  ✓  │     │     │     │     │     │  ✓  │  ✓  │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ alternative/*     │     │  ✓  │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ text_corpus.py    │     │     │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ embedding_engine  │     │     │     │     │     │     │     │     │     │
└───────────────────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘

Legend:
  state.py     = UnifiedState (synthesis)
  sigag.py     = SignalAggregator (synthesis)
  thetr.py     = ThesisTracker (knowledge)
  learn.py     = LearningLog (knowledge)
  knowb.py     = KnowledgeBase (knowledge)
  decis.py     = DecisionLogger (decision)
  adver.py     = AdversarialAgent (decision)
  featr.py     = FeatureEngine (data)
  backT.py     = BacktestEngine (evaluation)
```

---

## 9. Potentially Underutilized Modules

Based on the integration analysis, these modules may need better integration:

### Fully Integrated
- `UnifiedState` - Central to everything
- `ThesisTracker` - Linked to decisions
- `DecisionLogger` - Connected to learnings and theses
- `SignalAggregator` - Pulls from all signal sources
- `FeatureEngine` - Used by strategies and backtests

### Needs Integration Review
| Module | Current Status | Recommended Integration |
|--------|---------------|------------------------|
| `text_corpus.py` | Standalone DuckDB | Feed into SignalAggregator sentiment |
| `embedding_engine.py` | Standalone | Use for thesis similarity search |
| `feature_store.py` | DuckDB storage | Use for historical feature retrieval |
| `feature_discovery.py` | Research tool | Connect to brainstorm-agent |
| `llm_extractor.py` | Standalone | Use in morning briefing |
| `lead_lag_strategy.py` | Validated | Add to signal aggregator |
| `commodity_mean_rev.py` | Validated | Add to signal aggregator |
| `renaissance.py` | Experimental | Needs validation |
| `social_sentiment.py` | Stub | Implement and connect |

### Scripts Needing Entry Points
| Script | Purpose | Status |
|--------|---------|--------|
| `research_prep.py` | Pre-market data prep | Should run at 6AM |
| `run_daily.py` | Daily signal generation | Integrated |
| `full_research_cycle.py` | Complete research | Used by /research |
| `validate_strategy.py` | Strategy validation | Used by /validate |
| `critic_validate.py` | Safety validation | Used by /critic |

---

## 10. Recommended Improvements

### High Priority
1. **Implement `social_sentiment.py`** - Currently a stub, needed for SignalAggregator
2. **Connect `text_corpus.py` to signals** - Rich sentiment data not being used
3. **Integrate `feature_store.py`** - Use versioned features in backtests

### Medium Priority
4. **Connect `lead_lag_strategy.py`** - Validated but not in aggregator
5. **Add `commodity_mean_rev`** - Validated but not in aggregator
6. **Implement `llm_extractor.py` usage** - Use for briefing enhancement

### Lower Priority
7. **Validate `renaissance.py`** - Promising but needs MCPT
8. **Connect `embedding_engine.py`** - For thesis similarity search
9. **Implement `feature_discovery.py` loop** - Automated feature generation

---

## 11. Data Collection Daemon Architecture

**Added**: 2026-01-10
**Reason**: Orchestrate 20+ free data sources with configurable schedules, proper caching, and rate limiting to expand signal diversity at zero API cost.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            DATA COLLECTION DAEMON                                        │
│                         src/data/sources/collection_daemon.py                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         │                                │                                │
         ▼                                ▼                                ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   REAL-TIME (5-15m) │    │     HOURLY          │    │      DAILY          │
│   Market hours only │    │                     │    │                     │
├─────────────────────┤    ├─────────────────────┤    ├─────────────────────┤
│ vix_structure   15m │    │ fed_futures     60m │    │ finviz_screens  4hr │
│ put_call        60m │    │                     │    │ earnings_cal    6hr │
│ breadth          5m │    │                     │    │ economic_cal   12hr │
└─────────────────────┘    └─────────────────────┘    │ ipo_calendar   12hr │
                                                       │ fda_calendar   12hr │
         ┌────────────────────────────────┐            │ app_rankings   24hr │
         │                                │            │ github_activity24hr │
         ▼                                ▼            │ short_interest 24hr │
┌─────────────────────┐    ┌─────────────────────┐    └─────────────────────┘
│      WEEKLY         │    │     PERIODIC        │
├─────────────────────┤    ├─────────────────────┤
│ aaii_sentiment      │    │ job_postings    3d  │
│ newsletter_sentiment│    │                     │
│ cot_report          │    │                     │
│ patents             │    │                     │
└─────────────────────┘    └─────────────────────┘
         │                                │
         └────────────────┬───────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              CACHING & STORAGE                                           │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │  ~/quant_results/live/data_cache/                                                │   │
│  │                                                                                  │   │
│  │  vix_structure.json    ─► {"timestamp": "...", "slope": 0.15, "signal": 0.3}    │   │
│  │  put_call.json         ─► {"timestamp": "...", "equity_ratio": 0.68, ...}       │   │
│  │  aaii_sentiment.json   ─► {"survey_date": "...", "bullish_pct": 42.5, ...}      │   │
│  │  cot_report.json       ─► {"report_date": "...", "ES": {...}, "NQ": {...}}      │   │
│  │  fed_expectations.json ─► {"timestamp": "...", "prob_cut": 0.65, ...}           │   │
│  │  earnings_calendar.json ─► {"events": [...], "timestamp": "..."}                │   │
│  │  fda_calendar.json     ─► {"events": [...], "timestamp": "..."}                 │   │
│  │  ... etc                                                                         │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  All files include timestamps for point-in-time backtesting safety                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              SIGNAL AGGREGATOR                                           │
│                              src/synthesis/signals.py                                    │
│                                                                                          │
│  New signal fields (Added 2026-01-10):                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │  vix_structure_signal: float   # -1 to +1 (contango/backwardation)               │   │
│  │  breadth_signal: float         # -1 to +1 (weak/strong breadth)                  │   │
│  │  aaii_signal: float            # -1 to +1 (contrarian: high bull = sell)         │   │
│  │  cot_signal: float             # -1 to +1 (follow commercials)                   │   │
│  │  put_call_signal: float        # -1 to +1 (contrarian at extremes)               │   │
│  │  short_squeeze_score: float    # 0 to 1 (squeeze potential)                      │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Free Data Source Categories

| Category | Sources | Update Frequency | Use Case |
|----------|---------|-----------------|----------|
| **Market Regime** | VIX structure, Put/call, NYSE breadth, Finviz screens | 5-60 min | Core market context |
| **Sentiment Extremes** | AAII survey, Newsletter sentiment, COT report | Weekly | Contrarian signals |
| **Economic Calendar** | Earnings, Economic releases, Fed futures, Treasury auctions | 1-12 hr | Event preparation |
| **Event Catalysts** | IPO calendar, FDA calendar | 12 hr | Binary event awareness |
| **Innovation Signals** | Patents, Job postings, App rankings, GitHub activity | 1-7 days | Growth/momentum proxy |

### Key Design Decisions (2026-01-10)

1. **Variable Update Frequencies**: Different data sources have different freshness requirements
2. **Market Hours Awareness**: Real-time sources only poll during market hours to save resources
3. **Graceful Failure Handling**: Exponential backoff on source failures, continue with other sources
4. **Point-in-Time Safety**: All cached data includes timestamps for accurate backtesting
5. **Rate Limiting**: Respects source-specific rate limits to avoid being blocked
6. **Zero Cost**: All sources are free (CBOE, CFTC, SEC, USPTO, etc.)

---

## 12. Strategy Promotion Pipeline

**Added**: 2026-01-11
**Reason**: Automate the lifecycle of strategies from research through paper trading to live trading with quality gates at each stage.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            STRATEGY PROMOTION PIPELINE                                   │
│                         src/execution/promotion/pipeline.py                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   BACKTEST    │───►│    MCPT       │───►│    PAPER      │───►│    PAPER      │
│               │    │  VALIDATION   │    │   TRADING     │    │   REVIEW      │
└───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘
       │                    │                    │                    │
       │                    │                    │                    │
   GATE: Basic          GATE: p<0.05         GATE: 20+ days      GATE: Sharpe>0.5
   backtest results     Sharpe>1.0           min 10 trades       max DD<15%
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              PromotionCandidate                                        │
│  {                                                                                     │
│    strategy_name: "momentum_breakout",                                                 │
│    symbol: "AAPL",                                                                     │
│    current_stage: "paper_trading",                                                     │
│    backtest_sharpe: 2.5,                                                               │
│    mcpt_p_value: 0.02,                                                                 │
│    paper_days: 15,                                                                     │
│    paper_sharpe: 1.2,                                                                  │
│    notes: ["[2026-01-05] Added to pipeline", "..."]                                    │
│  }                                                                                     │
└───────────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌───────────────┐    ┌───────────────┐
│ LIVE_PENDING  │───►│    LIVE       │
│               │    │   TRADING     │
└───────────────┘    └───────────────┘
       │                    │
   GATE: Human          Status: Active
   approval required    in production
```

### Pipeline Stages

| Stage | Requirements to Advance | Automated? |
|-------|------------------------|------------|
| BACKTEST | Sharpe computed, 30+ trades | Yes |
| MCPT_VALIDATION | p-value < 0.05, Sharpe > 1.0 | Yes |
| PAPER_TRADING | 20+ trading days, 10+ trades | Yes |
| PAPER_REVIEW | Paper Sharpe > 0.5, DD < 15% | Yes |
| LIVE_PENDING | Await human approval | **No** |
| LIVE_TRADING | - | Final |

### Integration with Cron Jobs

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              CRON JOB INTEGRATION                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘

cron_paper_trading_review.py (Daily 5:30 PM ET)
    │
    ├─► Load PromotionPipeline
    │
    ├─► For each PAPER_TRADING candidate:
    │   ├─► Update metrics from paper broker
    │   └─► Try to advance to PAPER_REVIEW
    │
    ├─► For each PAPER_REVIEW candidate:
    │   └─► Try to advance to LIVE_PENDING
    │
    └─► Alert if candidates ready for approval

cron_thesis_signpost_check.py (Hourly 6 AM - 5 PM ET)
    │
    ├─► Check active theses for signpost triggers
    │
    ├─► Calculate trigger likelihood from:
    │   ├─► Target date proximity
    │   ├─► News relevance
    │   └─► Price action
    │
    └─► Save alerts to ~/quant_results/alerts/
```

---

## 13. Thesis Performance Attribution

**Added**: 2026-01-11
**Reason**: Answer "Which theses are profitable?" by tracking P&L and performance metrics per investment thesis.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          THESIS PERFORMANCE ATTRIBUTION                                  │
│                        src/knowledge/thesis_performance.py                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
│    ThesisTracker      │     │    DecisionLogger     │     │     LearningLog       │
│                       │     │                       │     │                       │
│ • Thesis definitions  │     │ • Trading decisions   │     │ • Extracted learnings │
│ • Signpost tracking   │     │ • thesis_id links     │     │ • Patterns identified │
│ • Conviction history  │     │ • Realized P&L        │     │                       │
└───────────┬───────────┘     └───────────┬───────────┘     └───────────┬───────────┘
            │                             │                             │
            └─────────────────────────────┼─────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────────┐
                        │     ThesisPerformanceTracker        │
                        │                                     │
                        │  get_performance(thesis_id)         │
                        │  get_all_performance()              │
                        │  get_thesis_leaderboard()           │
                        │  compare_theses([id1, id2])         │
                        └─────────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────────┐
                        │     ThesisPerformanceMetrics        │
                        │                                     │
                        │  thesis_id: "venezuela123"          │
                        │  thesis_name: "Venezuela Energy"    │
                        │  total_realized_pnl: $2,340.00      │
                        │  num_trades: 15                     │
                        │  wins: 10, losses: 4, scratches: 1  │
                        │  win_rate: 71%                      │
                        │  avg_hold_days: 5.2                 │
                        │  position_performance: {...}        │
                        │  key_patterns: ["insider_confluence"]│
                        └─────────────────────────────────────┘

USAGE:
    from src.knowledge.thesis_performance import ThesisPerformanceTracker

    tracker = ThesisPerformanceTracker()
    print(tracker.get_thesis_leaderboard())

    # Output:
    # | Rank | Thesis            | P&L     | Win Rate | Trades |
    # |------|-------------------|---------|----------|--------|
    # | 1    | Venezuela Energy  | +$2,340 | 71%      | 15     |
    # | 2    | AI Infrastructure | +$1,120 | 65%      | 8      |
```

---

---

## 14. Hedge Fund Expansion Architecture (Added 2026-01-20)

**Reason**: Transform Project Athena into a comprehensive Claude-managed hedge fund with real-time capabilities.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           HEDGE FUND EXPANSION MODULES                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              DATA & INTELLIGENCE                                       │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ expanded_news   │  │ legal_tracker   │  │ geopolitical    │  │ news_sentiment  │   │
│  │                 │  │                 │  │                 │  │                 │   │
│  │ • 20+ RSS feeds │  │ • SCOTUS cases  │  │ • 5 regions     │  │ • Keyword scoring│  │
│  │ • WSJ, CNBC, FT │  │ • SEC enforce   │  │ • Greenland     │  │ • Sector mapping │  │
│  │ • Fed, SEC feeds│  │ • FTC, DOJ      │  │ • Venezuela     │  │ • Bull/bear terms│  │
│  │ • Sector news   │  │ • IEEPA tariffs │  │ • China/Taiwan  │  │ • Confidence calc│  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              ALERTING & EXECUTION                                      │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ smart_alerter   │  │ mobile_bot      │  │ rules_engine    │  │ drawdown_protect│   │
│  │                 │  │                 │  │                 │  │                 │   │
│  │ • Signal converg│  │ • Telegram      │  │ • AUTO/QUEUE/   │  │ • 5 levels      │   │
│  │ • Multi-source  │  │ • Discord       │  │   NOTIFY        │  │ • normal→emerge │   │
│  │ • Alert levels  │  │ • Rate limiting │  │ • Pre-defined   │  │ • 5-15% triggers│   │
│  │ • Callbacks     │  │ • Quiet hours   │  │   rules         │  │ • Auto reduce   │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              ANALYSIS & OPTIMIZATION                                   │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │portfolio_optim  │  │ sector_rotation │  │ perform_attrib  │  │earnings_predictor│  │
│  │                 │  │                 │  │                 │  │                 │   │
│  │ • Risk parity   │  │ • Sector leader │  │ • P&L by thesis │  │ • 7 signals     │   │
│  │ • Mean-variance │  │ • Cycle phases  │  │ • P&L by signal │  │ • Momentum      │   │
│  │ • Kelly criterion│ │ • Transition    │  │ • Attribution   │  │ • Analyst revs  │   │
│  │ • Rebalance calc│  │   detection     │  │   analysis      │  │ • Options skew  │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              REAL-TIME & TAX                                           │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                        │
│  │ websocket_feed  │  │ tax_loss_harvest│  │ trade_journal   │                        │
│  │                 │  │                 │  │                 │                        │
│  │ • Alpaca WS     │  │ • Wash sale     │  │ • Full context  │                        │
│  │ • Finnhub WS    │  │   tracking      │  │ • Market state  │                        │
│  │ • Polling backup│  │ • Substitute    │  │ • Thesis link   │                        │
│  │ • Price alerts  │  │   securities    │  │ • Learnings     │                        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                        │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Module Summary Table

| Module | Lines | Location | Purpose |
|--------|-------|----------|---------|
| `expanded_news.py` | 331 | `src/data/sources/alternative/` | 20+ RSS feeds aggregation |
| `legal_tracker.py` | 325 | `src/data/sources/alternative/` | Legal case monitoring |
| `geopolitical.py` | 300 | `src/data/sources/alternative/` | Regional event tracking |
| `news_sentiment.py` | 273 | `src/data/sources/alternative/` | Keyword sentiment scoring |
| `smart_alerter.py` | 369 | `src/alerts/` | Signal convergence detection |
| `mobile_bot.py` | 373 | `src/alerts/` | Telegram/Discord integration |
| `rules_engine.py` | 536 | `src/execution/` | Automated execution rules |
| `drawdown_protection.py` | 301 | `src/execution/` | 5-level portfolio protection |
| `portfolio_optimizer.py` | 411 | `src/risk/` | Risk parity, MPT, Kelly |
| `sector_rotation.py` | 369 | `src/synthesis/` | Sector cycle tracking |
| `performance_attribution.py` | 309 | `src/knowledge/` | P&L attribution analysis |
| `earnings_predictor.py` | 609 | `src/analysis/` | 7-signal earnings prediction |
| `websocket_feed.py` | 348 | `src/data/realtime/` | Real-time price feeds |
| `tax_loss_harvester.py` | 446 | `src/tax/` | Tax optimization |
| `trade_journal.py` | 629 | `src/knowledge/` | Automated trade journal |

**Total**: ~5,700 lines of production code

### Integration Points

```
                            ┌─────────────────────┐
                            │   UnifiedState      │
                            │   (state.json)      │
                            └─────────┬───────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│  DATA SOURCES     │     │   ALERTING        │     │   ANALYSIS        │
│                   │     │                   │     │                   │
│ • expanded_news   │────►│ • smart_alerter   │────►│ • earnings_predict│
│ • legal_tracker   │     │ • mobile_bot      │     │ • portfolio_optim │
│ • geopolitical    │     │                   │     │ • sector_rotation │
│ • news_sentiment  │     │                   │     │ • perform_attrib  │
└───────────────────┘     └───────────────────┘     └───────────────────┘
        │                             │                             │
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│  SignalAggregator │     │   ExecutionEngine │     │   TradeJournal    │
│  (signals.py)     │     │                   │     │                   │
│                   │     │ • rules_engine    │     │ • Full context    │
│ • Sentiment scores│     │ • drawdown_protect│     │ • Thesis linking  │
│ • Convergence     │     │                   │     │ • Tax tracking    │
└───────────────────┘     └───────────────────┘     └───────────────────┘
```

---

## 15. Monitoring & Operator Layer (Added 2026-01-20)

**Reason**: Transform Claude Code into a persistent trading operator with continuous monitoring, improvement tracking, and signal convergence detection.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           MONITORING & OPERATOR LAYER                                    │
│                               src/monitoring/                                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              UNIFIED DASHBOARD                                         │
│                           unified_dashboard.py                                         │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  get_unified_status() returns:                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │  UnifiedSystemStatus:                                                            │  │
│  │    • timestamp, market_open, market_hours                                        │  │
│  │    • market_regime: "risk_on" | "risk_off" | "neutral" | "volatile"              │  │
│  │    • regime_signals: [VIX, put/call, breadth indicators]                         │  │
│  │    • data_sources: {source: {fresh, last_update, top_signal, signal_count}}      │  │
│  │    • top_signals: [Signal(type, symbol, strength, direction, detail)]            │  │
│  │    • convergences: [ConvergenceSignal(symbol, 3+ aligned signals)]               │  │
│  │    • thesis_exposure: {thesis_name: {value, pct, day_pnl, positions}}            │  │
│  │    • upcoming_catalysts: [Catalyst(date, type, symbol, detail)]                  │  │
│  │    • portfolio, risk, agents, alerts, research                                   │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              OPERATOR SESSION                                          │
│                           operator_loop.py + /operator-session skill                   │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Claude enters persistent monitoring loop:                                             │
│                                                                                        │
│  /operator-session              # Default: 3 min checks                               │
│  /operator-session --passive    # 5 min checks (quiet days)                           │
│  /operator-session --active     # 1 min checks (volatile)                             │
│                                                                                        │
│  Each check cycle:                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │  1. Read state.json                                                              │  │
│  │  2. Check for triggered alerts                                                   │  │
│  │  3. Check signpost triggers                                                      │  │
│  │  4. Review agent completions (from agent_activity.jsonl)                         │  │
│  │  5. Check data freshness (stale sources)                                         │  │
│  │  6. Detect signal convergence (3+ signals aligned)                               │  │
│  │  7. Generate action items                                                        │  │
│  │  8. Log observation → ~/quant_results/logs/operator_log.jsonl                    │  │
│  │  9. Wait configured interval                                                     │  │
│  │  10. Repeat until exit or market close                                           │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  OperatorObservation:                                                                  │
│    alerts: [Alert(level, type, symbol, message, timestamp)]                           │
│    signposts: [SignpostTrigger(thesis_id, description, likelihood)]                   │
│    agent_completions: [AgentCompletion(agent_type, task_id, result_summary)]          │
│    stale_sources: [str]  # Sources needing refresh                                    │
│    convergences: [ConvergenceSignal]  # 3+ aligned signals                            │
│    action_items: [ActionItem(priority, action, symbol, detail)]                       │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              DATA FRESHNESS TRACKER                                    │
│                           data_freshness_tracker.py                                    │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Tracks WHAT each source returned, not just WHEN:                                      │
│                                                                                        │
│  ┌─────────────────┬────────────────────────────────────────────────────────────────┐ │
│  │ Source          │ Content Tracked                                                │ │
│  ├─────────────────┼────────────────────────────────────────────────────────────────┤ │
│  │ congressional   │ Top cluster signals, recent politician trades                  │ │
│  │ insider         │ Recent Form 4 buys > $100k                                     │ │
│  │ vix_structure   │ Contango/backwardation state, slope                            │ │
│  │ put_call        │ Extreme readings, contrarian signals                           │ │
│  │ aaii_sentiment  │ Bull/bear readings, extreme flags                              │ │
│  │ earnings_cal    │ This week's earnings for portfolio holdings                    │ │
│  │ economic_cal    │ Upcoming FOMC, CPI, jobs reports                               │ │
│  │ fda_calendar    │ PDUFA dates in next 30 days                                    │ │
│  │ finviz_screens  │ Oversold bounces, new highs, volume leaders                    │ │
│  │ geopolitical    │ Regional risk scores, recent events                            │ │
│  │ market_breadth  │ Advance/decline, new highs/lows                                │ │
│  └─────────────────┴────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              SIGNAL AGGREGATION                                        │
│                           signal_summary.py                                            │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Aggregates ALL collected data sources into actionable signals:                        │
│                                                                                        │
│  Signal(type, symbol, strength, direction, timestamp, source, detail, confidence)      │
│                                                                                        │
│  Convergence Detection:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │  For each symbol in watchlist:                                                   │  │
│  │    1. Check insider buying (Form 4)                                              │  │
│  │    2. Check congressional activity                                               │  │
│  │    3. Check technical signals (RSI, MACD)                                        │  │
│  │    4. Check options flow (unusual activity)                                      │  │
│  │    5. Check social sentiment                                                     │  │
│  │                                                                                   │  │
│  │    If 3+ aligned → ConvergenceSignal                                             │  │
│  │    Strength = average of component signal strengths                              │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  Market Regime Detection:                                                              │
│    • risk_on: Low VIX + bullish breadth + contrarian sentiment                        │
│    • risk_off: High VIX + bearish breadth + fear indicators                           │
│    • volatile: VIX > 25 or extreme readings                                           │
│    • neutral: Mixed signals                                                           │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              IMPROVEMENT TRACKER                                       │
│                           improvement_tracker.py + signal_quality_tracker.py           │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ImprovementSuggestion:                                                                │
│    id, category, priority, title, description, evidence, suggested_action, status      │
│                                                                                        │
│  Categories: "agent", "signal", "thesis", "sizing", "process"                          │
│  Priorities: "high", "medium", "low"                                                   │
│  Status: "pending", "in_progress", "completed", "rejected"                             │
│                                                                                        │
│  SignalQuality:                                                                        │
│    signal_type, total_signals, acted_on, profitable, hit_rate, avg_pnl, ic, trend      │
│                                                                                        │
│  Weekly Review (Sunday 6 PM):                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │  1. Analyze agent performance (completion rate, token efficiency)                │  │
│  │  2. Calculate signal quality (hit rate, IC, trends)                              │  │
│  │  3. Compare to 30-day baseline                                                   │  │
│  │  4. Generate improvement suggestions                                             │  │
│  │  5. Save to ~/quant_results/improvements/                                        │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Module Summary Table

| Module | Lines | Location | Purpose |
|--------|-------|----------|---------|
| `unified_dashboard.py` | ~400 | `src/monitoring/` | Full system status with all data |
| `operator_loop.py` | ~500 | `src/monitoring/` | Persistent monitoring check cycles |
| `data_freshness_tracker.py` | ~800 | `src/monitoring/` | Track data status + content |
| `signal_summary.py` | ~650 | `src/monitoring/` | Signal aggregation + convergence |
| `improvement_tracker.py` | ~450 | `src/monitoring/` | Auto-generated improvements |
| `signal_quality_tracker.py` | ~360 | `src/monitoring/` | Signal hit rate tracking |

**Total**: ~3,100+ lines of monitoring infrastructure

### Daily Workflow with Operator Session

```
6:30 AM ─── /morning-briefing ───────────────────────────────────────────────────
              │
              ▼
         Check improvements, convergences, data freshness

9:30 AM ─── /operator-session ───────────────────────────────────────────────────
              │
              ▼
         ┌────────────────────────────────────────────────────────────────────┐
         │  PERSISTENT MONITORING LOOP                                        │
         │                                                                    │
         │  Every 3 min (configurable):                                       │
         │    • Check alerts, signposts, agent completions                    │
         │    • Detect signal convergences                                    │
         │    • Surface action items                                          │
         │    • Spawn research agents if needed                               │
         │                                                                    │
         │  Can spawn:                                                        │
         │    • macro-research-agent (on geopolitical events)                 │
         │    • research-agent (on signal convergence)                        │
         │    • critic-agent (before trade decisions)                         │
         └────────────────────────────────────────────────────────────────────┘
              │
              ▼
4:00 PM ─── Market Close ─── /eod-review ────────────────────────────────────────
              │
              ▼
         Log signal outcomes, update quality metrics

Sunday ──── cron_weekly_improvement_review.py ───────────────────────────────────
              │
              ▼
         Generate improvement suggestions for next week
```

---

## 16. Compounding Intelligence Layer (Added 2026-03-01)

**Reason**: Close the feedback loop so the system gets measurably smarter over time. Predictions are made explicit, scored automatically, and learnings flow back into future decisions.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        COMPOUNDING INTELLIGENCE LOOP                                     │
│                            src/intelligence/                                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │  /trade-     │────►│  DecisionContext  │────►│  Better Decision │
    │  decision    │     │  Builder          │     │  (calibrated)    │
    └──────────────┘     └──────────────────┘     └────────┬─────────┘
                              ▲                            │
                              │                            ▼
                    ┌─────────┴──────────┐     ┌──────────────────┐
                    │   Belief Updater   │     │  Log Predictions │
                    │   (5:30 PM daily)  │     │  (explicit,      │
                    │                    │     │   testable)      │
                    │ • Signal weights   │     └────────┬─────────┘
                    │ • Thesis suggestions│             │
                    │ • Calibration      │             ▼
                    │ • Learning summary │  ┌──────────────────┐
                    └────────────────────┘  │  Auto-Score      │
                              ▲            │  (5:15 PM daily)  │
                              │            │                    │
                              └────────────┤ • Direction check  │
                                           │ • Price comparison │
                                           │ • Brier score      │
                                           └──────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           PREDICTION TRACKING                                          │
│                        DB: predictions table (PredictionRecord)                        │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Prediction Types:                                                                     │
│    direction | price_target | relative_perf | timeframe_move | event_outcome           │
│    thesis_validation                                                                   │
│                                                                                        │
│  Reasoning Categories:                                                                 │
│    thesis_driven | technical | geopolitical | earnings | momentum | mean_reversion     │
│    event_driven | sentiment | insider_following | congressional                        │
│                                                                                        │
│  Setup Types (11 canonical):                                                           │
│    thesis_driven | signal_convergence | technical_breakout | mean_reversion            │
│    momentum | event_driven | insider_following | congressional | squeeze               │
│    sector_rotation | rebalance                                                         │
│                                                                                        │
│  Lifecycle: open → hit | miss | expired | cancelled                                   │
│  Scoring: Brier = (confidence - outcome)²                                             │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           DECISION CONTEXT BUILDER                                     │
│                        context_builder.py                                               │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  build_context(symbol, setup_type, thesis_id, scenario) → DecisionContext              │
│                                                                                        │
│  Scenarios:                                                                            │
│  ┌──────────────────┬───────────────────────────────────────────────────────────────┐  │
│  │ trade_decision   │ Full: track record + learnings + signals + calibration        │  │
│  │ morning_briefing │ Light: thesis status + overnight predictions + belief updates │  │
│  │ eod_review       │ Outcome: prediction scores + learning extraction prompts     │  │
│  │ thesis_review    │ Thesis: conviction history + linked predictions + signposts   │  │
│  └──────────────────┴───────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  DecisionContext contains:                                                             │
│    symbol_track_record  ─── from DecisionRecord WHERE symbol=X                        │
│    setup_type_track_record ─── from DecisionRecord WHERE setup_type=X                 │
│    relevant_learnings   ─── from LearningRecord by symbol/tags                        │
│    signal_quality       ─── from signal_quality/quality.json                          │
│    prediction_history   ─── from PredictionRecord                                     │
│    calibration          ─── from resolved PredictionRecord by confidence bin           │
│    thesis_context       ─── from ThesisRecord + linked decisions                      │
│    summary              ─── Pre-formatted text for Claude to read                     │
│                                                                                        │
│  Example output:                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │  === DECISION CONTEXT: SLB ===                                                  │   │
│  │  SYMBOL TRACK RECORD: 12 decisions, 75% win rate, avg +3.2%                     │   │
│  │  SETUP TYPE (thesis_driven): 81% win rate — YOUR BEST SETUP TYPE                │   │
│  │  CONFIDENCE CALIBRATION: When you say 70%, you're right 58% of the time         │   │
│  │  PREDICTION HISTORY: 8 predictions, 63% accurate, timing 2.3 days late          │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           BELIEF UPDATE SYSTEM                                         │
│                        belief_updater.py + cron scripts                                │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  Daily automated pipeline (weekdays):                                                  │
│                                                                                        │
│  5:15 PM ─── cron_prediction_scorer.py ─────────────────────────────────────────────  │
│    1. Query open predictions past resolve_by                                           │
│    2. Fetch current prices (yfinance)                                                  │
│    3. Score by type (direction, price_target, timeframe_move)                          │
│    4. Calculate Brier score: (confidence - outcome)²                                  │
│    5. Expire predictions >5 days past deadline                                        │
│                                                                                        │
│  5:30 PM ─── cron_belief_update.py ─────────────────────────────────────────────────  │
│    1. Update signal weights (hit_rate × IC)                                            │
│    2. Suggest thesis conviction changes from prediction accuracy                       │
│    3. Compute calibration bins and error                                               │
│    4. Generate learning summary (natural language)                                     │
│    5. Persist report → intelligence/daily_update_YYYYMMDD.json                        │
│    6. Append metrics → intelligence/metrics_history.jsonl                              │
│                                                                                        │
│  "Getting Smarter" Metrics (tracked daily):                                            │
│    • Prediction accuracy (rolling 30d)                                                 │
│    • Average Brier score (rolling 30d)                                                 │
│    • Calibration error                                                                 │
│    • Decision win rate (rolling 30d)                                                   │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           WEB DASHBOARD                                                │
│                        /intelligence routes + templates                                │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  GET /intelligence/            ─── Main dashboard (scorecard, calibration, setup perf) │
│  GET /intelligence/predictions ─── Prediction list with filters                        │
│  GET /intelligence/predictions/{id} ─── Prediction detail with resolution timeline    │
│  GET /intelligence/context/{symbol}  ─── Decision context (page + HTMX partial)       │
│  GET /intelligence/calibration ─── JSON calibration data for Chart.js                 │
│  GET /intelligence/setup-types ─── JSON setup type performance                        │
│                                                                                        │
│  HTMX Integration:                                                                    │
│    decisions/detail.html ─── loads /intelligence/context/{symbol} partial              │
│    theses/detail.html ─── shows linked prediction history table                       │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Module Summary Table

| Module | Location | Purpose |
|--------|----------|---------|
| `context_builder.py` | `src/intelligence/` | Assemble decision context from DB tables |
| `setup_types.py` | `src/intelligence/` | Canonical setup type and reasoning taxonomies |
| `setup_scorer.py` | `src/intelligence/` | Setup type performance from DecisionRecord |
| `belief_updater.py` | `src/intelligence/` | Daily signal weights, calibration, thesis suggestions |
| `intelligence_service.py` | `src/web/services/` | DB queries for intelligence dashboard |
| `intelligence.py` | `src/web/routes/` | 6 FastAPI routes for intelligence UI |
| `cron_prediction_scorer.py` | `scripts/` | Automated prediction scoring (5:15 PM) |
| `cron_belief_update.py` | `scripts/` | Automated belief updates (5:30 PM) |
| `backfill_predictions.py` | `scripts/` | One-time backfill from existing decisions |

### Skill Integration

| Skill | Change |
|-------|--------|
| `/trade-decision` | Step 0: Get decision context before deciding. Step 7: Log explicit predictions. |
| `/eod-review` | Step 6: Score predictions and run belief update. |
| `/morning-briefing` | Read yesterday's belief update report and calibration data. |

---

*Generated: 2026-01-07*
*Updated: 2026-01-10 - Added Data Collection Daemon and 20+ free data sources*
*Updated: 2026-01-11 - Added Promotion Pipeline, Thesis Performance, Strategy Dashboard, Holiday Calendar*
*Updated: 2026-01-20 - Added Hedge Fund Expansion (15 modules, 5,700 lines)*
*Updated: 2026-01-20 - Added Monitoring & Operator Layer (6 modules, 3,100+ lines)*
*Updated: 2026-03-01 - Added Compounding Intelligence Layer (predictions, context builder, belief updater)*
*Updated: 2026-03-08 - Rewrote high-level architecture (swarm), daily workflow, module map, storage layout, web layer*
*This document should be updated when major architectural changes are made.*
