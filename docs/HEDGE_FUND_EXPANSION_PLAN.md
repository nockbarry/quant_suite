# Hedge Fund Expansion Plan

**Created**: 2026-01-20
**Status**: ✅ COMPLETED (2026-01-20)
**Goal**: Transform Project Athena into a comprehensive Claude-managed hedge fund

---

## Implementation Summary

**Completed same day**: 7,074 lines across 22 files

| Category | Modules Built | Lines |
|----------|---------------|-------|
| Data & Intelligence | expanded_news, legal_tracker, geopolitical, news_sentiment | ~1,200 |
| Alerting & Execution | smart_alerter, mobile_bot, rules_engine, drawdown_protection | ~1,600 |
| Analysis & Optimization | portfolio_optimizer, sector_rotation, performance_attribution, earnings_predictor | ~1,700 |
| Real-Time & Tax | websocket_feed, tax_loss_harvester, trade_journal | ~1,400 |
| Operations | collect_all_data, dashboard, setup_cron updates | ~750 |

See `docs/ARCHITECTURE_DIAGRAMS.md` Section 14 for full architecture.

---

## Original Roadmap (Archived Below)

---

## Current State Assessment

### What We Have (35 data sources implemented)

| Category | Sources | Status |
|----------|---------|--------|
| **Congressional Trades** | congressional_trades, congressional_archive | Active |
| **Insider Trading** | insider | Active |
| **Market Regime** | vix_structure, put_call, finviz_screens | Implemented |
| **Sentiment** | aaii_sentiment, newsletter_sentiment, expert_sentiment | Implemented |
| **Positioning** | cot_report, short_interest, options_flow | Implemented |
| **Economic** | earnings_calendar, economic_calendar, fed_futures, treasury_calendar | Implemented |
| **Events** | ipo_calendar, fda_calendar | Implemented |
| **Innovation** | patent_filings, job_postings, app_rankings, github_activity | Implemented |
| **Flow** | etf_flows, institutional_flow | Implemented |
| **Other** | google_trends, prediction_markets, credit_spreads, iv_rank, weather, reddit, news | Implemented |

### What's Actually Running (Cron Jobs)
- LiveDaemon state updates (every 5 min)
- Congressional trades (daily)
- Insider trades (daily)
- Signpost monitoring (hourly)
- News collection (every 4 hours)
- Concentration checks (every 2 hours)

### Key Gaps

1. **Many data sources implemented but not actively collected**
2. **No intraday execution capability** - only manual/scheduled trades
3. **ML models built but not trained/validated**
4. **No real-time alerting system** (only file-based signposts)
5. **Limited news coverage** (3 RSS feeds)
6. **No automated thesis-driven rebalancing**
7. **No multi-timeframe strategy coordination**

---

## Expansion Tiers

### Tier 1: Activate Existing Infrastructure (1-2 days)

**Goal**: Get all 35 data sources actively collecting and feeding into decisions

#### 1.1 Data Collection Activation
```bash
# Add to cron - run collection daemon continuously
*/30 6-17 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 -c "
from src.data.sources.collection_daemon import DataCollectionDaemon
import asyncio
asyncio.run(DataCollectionDaemon().collect_all_now())
" >> ~/quant_results/logs/collection.log 2>&1
```

#### 1.2 Data Source Verification
- [ ] Test each of 35 sources returns valid data
- [ ] Verify data cache population
- [ ] Create monitoring dashboard for source health

#### 1.3 Signal Integration
- [ ] Ensure SignalAggregator uses all available sources
- [ ] Add source weights to unified state
- [ ] Create composite regime score

---

### Tier 2: Enhanced News & Event Monitoring (2-3 days)

**Goal**: Comprehensive real-time awareness of market-moving events

#### 2.1 Expanded RSS Feeds
```python
EXPANDED_RSS = {
    # Current
    "yahoo_finance": "...",
    "seeking_alpha": "...",
    "reuters": "...",

    # ADD: Major outlets
    "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "bloomberg_markets": "...",  # Need to find working feed
    "cnbc_top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "ft_markets": "https://www.ft.com/markets?format=rss",

    # ADD: Sector-specific
    "oilprice": "https://oilprice.com/rss/main",
    "mining_weekly": "...",
    "biotech_daily": "...",

    # ADD: Fed/Policy
    "fed_calendar": "https://www.federalreserve.gov/feeds/press_all.xml",
    "treasury_news": "...",

    # ADD: International
    "reuters_asia": "...",
    "reuters_europe": "...",
}
```

#### 2.2 Supreme Court / Legal Tracking
```python
# New source: Legal/Regulatory tracking
class LegalTracker:
    """Track Supreme Court, SEC, regulatory decisions."""

    SOURCES = {
        "scotusblog": "https://www.scotusblog.com/feed/",
        "sec_news": "https://www.sec.gov/news/pressreleases.rss",
        "ftc_news": "...",
    }

    KEYWORDS = ["tariff", "IEEPA", "antitrust", "merger", "regulation"]
```

#### 2.3 Geopolitical Monitoring
```python
class GeopoliticalTracker:
    """Track geopolitical events affecting markets."""

    # Key regions with thesis exposure
    REGIONS = {
        "greenland": ["RTX", "LMT", "NOC", "GD"],  # Defense
        "venezuela": ["SLB", "HAL", "FRO", "STNG"],  # Energy
        "china_taiwan": ["TSM", "NVDA", "AMD"],  # Semis
        "middle_east": ["XLE", "USO", "OIH"],  # Oil
    }

    SOURCES = [
        "https://www.state.gov/press-releases/feed/",
        "https://www.defense.gov/News/",
    ]
```

---

### Tier 3: Intelligent Alerting System (2-3 days)

**Goal**: Real-time notifications that drive action

#### 3.1 Multi-Channel Alerts
```python
class AlertManager:
    """Unified alerting across channels."""

    CHANNELS = {
        "desktop": notify-send,
        "terminal": bell + print,
        "file": JSON log,
        "webhook": Discord/Slack (optional),
    }

    PRIORITY_ROUTING = {
        "critical": ["desktop", "terminal", "file"],
        "high": ["terminal", "file"],
        "medium": ["file"],
    }
```

#### 3.2 Smart Alert Aggregation
```python
class SmartAlerter:
    """Context-aware alerts that reduce noise."""

    def should_alert(self, signal):
        # Don't alert on every tick
        if self.similar_alert_recent(signal, minutes=30):
            return False

        # Require multiple confirmation
        if signal.type == "news":
            return self.has_price_confirmation(signal)

        # Escalate on convergence
        if self.count_aligned_signals() >= 3:
            return True, "CONVERGENCE ALERT"
```

#### 3.3 Signpost Auto-Updates
```python
# Signposts that update based on technicals
class DynamicSignpost:
    """Signposts that track moving levels."""

    def update_spy_support(self):
        # Track 20-day low as rolling support
        spy_20d_low = get_rolling_low("SPY", 20)
        self.update_level("SPY", "support", spy_20d_low * 0.99)

    def update_vix_thresholds(self):
        # Adjust VIX thresholds based on regime
        vix_avg = get_rolling_avg("^VIX", 30)
        self.update_level("^VIX", "elevated", vix_avg * 1.2)
```

---

### Tier 4: Automated Execution Framework (3-5 days)

**Goal**: Rules-based execution with human oversight

#### 4.1 Execution Rules Engine
```python
class ExecutionEngine:
    """Rules-based trade execution."""

    RULES = {
        "signpost_exit": {
            "trigger": "price < signpost.exit_level",
            "action": "sell",
            "size": "full_position",
            "approval": "auto",  # Pre-approved by signpost creation
        },
        "thesis_add": {
            "trigger": "oversold AND thesis.conviction > 60",
            "action": "buy",
            "size": "equal_weight",
            "approval": "queue",  # Needs human confirmation
        },
        "vix_mean_reversion": {
            "trigger": "vix > 30 AND vix_structure == backwardation",
            "action": "buy SPY",
            "size": "5%",
            "approval": "queue",
        },
    }
```

#### 4.2 Trade Queue System
```python
class TradeQueue:
    """Queue trades for human review or auto-execution."""

    def queue_trade(self, trade, reason, approval_type):
        if approval_type == "auto":
            # Pre-approved rules (signpost exits)
            self.execute_immediately(trade)
        elif approval_type == "queue":
            # Save for human review
            self.pending_trades.append({
                "trade": trade,
                "reason": reason,
                "timestamp": now(),
                "expires": now() + timedelta(hours=4),
            })
            self.notify_human(trade)
```

#### 4.3 Scheduled Trade System
```python
# Enhance existing scheduled_trades.py
class ScheduledTradeManager:
    """Manage time-based trade execution."""

    SCHEDULES = {
        "open_orders": "9:31",  # Execute at open
        "close_orders": "15:55",  # Execute before close
        "rebalance": "first_monday",  # Monthly rebalance
    }

    def add_scheduled_trade(self, trade, schedule_type, conditions=None):
        """Schedule a trade with optional conditions."""
        pass
```

---

### Tier 5: ML Signal Integration (5-7 days)

**Goal**: Train and deploy ML models for enhanced signals

#### 5.1 Model Training Pipeline
```python
# From existing ML infrastructure
PRIORITY_MODELS = [
    # High value, quick to train
    ("xgboost", "direction_5d", ["technical", "sentiment"]),
    ("lightgbm", "direction_5d", ["technical", "congressional"]),

    # Alternative data focus
    ("xgboost", "direction_20d", ["congressional", "insider", "options"]),
]

# Training schedule
# 1. Train on 2 years of data
# 2. Validate with MCPT (1000 permutations)
# 3. Walk-forward test (5 periods)
# 4. Deploy if p < 0.05 and Sharpe > 0.5
```

#### 5.2 Ensemble Signal
```python
class MLEnsemble:
    """Combine multiple ML models into single signal."""

    def get_signal(self, symbol):
        signals = []
        for model in self.validated_models:
            pred = model.predict(symbol)
            signals.append(pred * model.weight)

        return sum(signals) / sum(model.weight for model in self.validated_models)
```

---

### Tier 6: Multi-Timeframe Coordination (3-5 days)

**Goal**: Coordinate intraday, swing, and position trading

#### 6.1 Timeframe Framework
```python
class TimeframeCoordinator:
    """Coordinate strategies across timeframes."""

    TIMEFRAMES = {
        "position": {
            "horizon": "weeks to months",
            "signals": ["thesis", "macro", "congressional"],
            "sizing": "10-20%",
        },
        "swing": {
            "horizon": "days to weeks",
            "signals": ["technical", "sentiment", "flow"],
            "sizing": "5-10%",
        },
        "tactical": {
            "horizon": "intraday to days",
            "signals": ["signpost", "news", "vix_spike"],
            "sizing": "2-5%",
        },
    }

    def check_alignment(self, symbol):
        """Check if all timeframes agree."""
        position_signal = self.get_position_signal(symbol)
        swing_signal = self.get_swing_signal(symbol)
        tactical_signal = self.get_tactical_signal(symbol)

        return {
            "aligned": all same direction,
            "strength": average magnitude,
            "recommended_size": based on alignment,
        }
```

#### 6.2 Position Lifecycle Tracking
```python
class PositionLifecycle:
    """Track position from entry to exit."""

    STAGES = [
        "thesis_identified",
        "entry_signal",
        "position_built",
        "thesis_playing_out",
        "profit_target_approaching",
        "exit_signal",
        "position_closed",
        "outcome_logged",
    ]

    def get_position_stage(self, symbol):
        """Where is this position in its lifecycle?"""
        pass
```

---

### Tier 7: Autonomous Research Cycles (5-7 days)

**Goal**: Claude proactively researches and proposes new opportunities

#### 7.1 Scheduled Research
```python
# Weekly research cycle
RESEARCH_SCHEDULE = {
    "monday": "sector_rotation_analysis",
    "tuesday": "thesis_health_check",
    "wednesday": "new_opportunity_scan",
    "thursday": "risk_assessment",
    "friday": "week_review_and_learning",
}
```

#### 7.2 Opportunity Pipeline
```python
class OpportunityPipeline:
    """Track opportunities from discovery to position."""

    STAGES = [
        "signal_detected",
        "research_initiated",
        "thesis_drafted",
        "validation_passed",
        "position_recommended",
        "human_approved",
        "position_opened",
    ]
```

#### 7.3 Automated Thesis Updates
```python
class ThesisAutoUpdater:
    """Automatically update thesis conviction based on evidence."""

    def daily_update(self, thesis):
        # Positive evidence
        if thesis_positions_outperforming(thesis):
            thesis.conviction += 2

        if signpost_triggered_positive(thesis):
            thesis.conviction += 5

        # Negative evidence
        if thesis_positions_underperforming(thesis):
            thesis.conviction -= 2

        if invalidation_trigger_hit(thesis):
            thesis.conviction = 0  # Exit
```

---

## Implementation Priority

### Phase 1: Foundation (This Week)
1. **Activate all data collection** - Get 35 sources running
2. **Expand news sources** - Add 10+ RSS feeds
3. **Enhanced signpost system** - Dynamic levels, multi-channel alerts

### Phase 2: Intelligence (Next Week)
4. **Smart alerting** - Context-aware, convergence detection
5. **Execution rules engine** - Auto-execute pre-approved actions
6. **Geopolitical tracking** - Monitor regions affecting theses

### Phase 3: Learning (Week 3)
7. **ML model training** - Train and validate priority models
8. **Research automation** - Scheduled research cycles
9. **Thesis auto-updates** - Evidence-based conviction tracking

### Phase 4: Coordination (Week 4)
10. **Multi-timeframe coordination** - Align signals across horizons
11. **Position lifecycle** - Track from entry to exit
12. **Opportunity pipeline** - Systematic idea flow

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Data sources active | ~5 | 35 |
| RSS feeds | 3 | 15+ |
| Signpost symbols | 16 | 50+ |
| Alert latency | Manual | <1 min |
| ML models validated | 0 | 5+ |
| Auto-executable rules | 0 | 10+ |
| Research frequency | Ad-hoc | Daily |

---

## Files to Create/Modify

### New Files
```
src/alerts/
├── alert_manager.py        # Multi-channel alerting
├── smart_alerter.py        # Context-aware alerts
└── dynamic_signposts.py    # Self-updating levels

src/execution/
├── rules_engine.py         # Rules-based execution
├── trade_queue.py          # Pending trade management
└── scheduled_manager.py    # Time-based trades

src/research/
├── opportunity_pipeline.py # Idea tracking
├── auto_research.py        # Scheduled research
└── thesis_updater.py       # Auto conviction updates

src/data/sources/alternative/
├── legal_tracker.py        # SCOTUS, SEC, regulatory
├── geopolitical.py         # Regional event tracking
└── expanded_news.py        # Additional RSS sources
```

### Modified Files
```
scripts/setup_cron.sh       # Add collection daemon, research cycles
src/synthesis/signals.py    # Integrate all 35 sources
CLAUDE.md                   # Document new capabilities
```

---

## Immediate Actions

1. **Run data source audit** - Test all 35 sources
2. **Activate collection daemon** - Add to cron
3. **Expand signpost coverage** - Add more symbols/levels
4. **Add RSS feeds** - At least 5 more major sources
5. **Create alert manager** - Multi-channel notifications

---

*This document serves as the master roadmap for expanding Project Athena into a comprehensive Claude-managed hedge fund.*
