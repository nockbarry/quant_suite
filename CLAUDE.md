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

This single file contains:
- Market regime and sentiment
- Portfolio positions and risk
- Aggregated signals for watchlist
- Active investment theses
- Pending decisions
- Recent learnings

---

## System Philosophy

```
┌──────────────────────────────────────────────────────────────────┐
│                       INTELLIGENCE LAYERS                        │
│                                                                  │
│  STATISTICAL      →    LLM (Claude)    →    HUMAN                │
│  Signal Generation     Decision Engine      Oversight            │
│                                                                  │
│  • 50+ features        • Reads state.json   • EOD review         │
│  • Technical signals   • Applies theses     • Approve trades     │
│  • Alternative data    • Adversarial check  • Override           │
│  • Pattern detection   • Pre-mortem         • Set rules          │
│                        • Documents reasoning                     │
└──────────────────────────────────────────────────────────────────┘
```

**Key Principle**: The infrastructure IS the memory. Theses persist. Learnings accumulate. No separate SESSION.md needed.

---

## Daily Trading Workflow

### Automated (Background)

```bash
# One-time setup - installs cron jobs
./scripts/setup_cron.sh install

# Or manually start each day
./scripts/trading_day.sh start
```

This runs automatically:
- **6:00 AM**: Start daemons, pre-market prep
- **Every 5 min**: Update state.json
- **5:00 PM**: Stop daemons

### Your Workflow (Claude Sessions)

| Time (ET) | Command | What Happens |
|-----------|---------|--------------|
| 6:30 AM | `claude "/morning-briefing"` | Read state, search news, review theses |
| 9:30 AM+ | `claude "/trade-decision"` | Adversarial analysis, make decisions |
| When ready | `claude "/execute-trades"` | Execute with your approval |
| 4:30 PM | `claude "/eod-review"` | Extract learnings, update conviction |

### Recommended Starting Prompts

```bash
# Morning - full briefing
claude "/morning-briefing"

# Quick check during day
claude "check positions"

# Make decisions
claude "/trade-decision"

# End of day
claude "/eod-review"
```

See `docs/WORKFLOW.md` for detailed automation guide.

---

## Token Efficiency Rules

**Use existing tools and quick commands instead of writing boilerplate code.**

### Quick Trade Commands
```bash
# Quick trades - NO boilerplate code needed
PYTHONPATH=. python3 scripts/quick_trade.py buy MU 10
PYTHONPATH=. python3 scripts/quick_trade.py sell SLB 50
PYTHONPATH=. python3 scripts/quick_trade.py quote MU FCX LEN
PYTHONPATH=. python3 scripts/quick_trade.py positions --thesis "Venezuela"
PYTHONPATH=. python3 scripts/quick_trade.py close GLD260206C00409000
```

### Available Skills
```bash
# Daily Trading Workflow
/morning-briefing    # Pre-market research and briefing
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

### Quick Reference: Common Patterns

**Broker connection (when truly needed):**
```python
# Use this helper instead of writing boilerplate
from scripts.quick_trade import get_broker
broker = get_broker()
await broker.connect()
```

**Key method signatures:**
```python
# AlpacaBroker - correct parameter names
AlpacaBroker(api_key=..., secret_key=..., paper=True)

# Position attributes
position.quantity  # NOT .qty
position.market_value
position.unrealized_pnl
position.unrealized_pnl_pct

# Order execution
await broker.market_buy(symbol, Decimal(qty))
await broker.market_sell(symbol, Decimal(qty))
await broker.close_position(symbol)
```

**Credentials location:**
```
/home/nock/projects/quant_suite/config/credentials.yaml
  alpaca.api_key
  alpaca.secret_key
```

---

## Core Architecture

### Synthesis Layer (NEW)

| Component | Location | Purpose |
|-----------|----------|---------|
| **UnifiedState** | `src/synthesis/state.py` | Everything in one dataclass |
| **LiveDaemon** | `src/synthesis/daemon.py` | Writes state.json every 5 min |
| **SignalAggregator** | `src/synthesis/signals.py` | Combines all signal sources |

```python
# Update unified state on-demand
from src.synthesis.daemon import LiveDaemon

daemon = LiveDaemon()
state = await daemon.update_now()
```

### Knowledge Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **ThesisTracker** | `src/knowledge/thesis.py` | Investment theses with signposts |
| **ThesisPerformanceTracker** | `src/knowledge/thesis_performance.py` | P&L attribution by thesis |
| **LearningLog** | `src/knowledge/learnings.py` | Extracted trade learnings |
| **KnowledgeBase** | `src/knowledge/base.py` | Company/sector understanding |

```python
# Create a thesis
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
thesis = tracker.create_thesis(
    name="Venezuela Energy Recovery",
    summary="Sanctions relief drives oilfield services rally",
    conviction=65,
    signposts=[{"description": "Chevron license extended", ...}],
    positions=["SLB", "HAL"],
)

# Get thesis performance
from src.knowledge.thesis_performance import ThesisPerformanceTracker
perf_tracker = ThesisPerformanceTracker()
metrics = perf_tracker.get_performance("thesis_id")
print(f"Total P&L: ${metrics.total_pnl:.2f}, Win Rate: {metrics.win_rate:.0%}")
print(perf_tracker.get_thesis_leaderboard())
```

### Decision Layer (ENHANCED)

| Component | Location | Purpose |
|-----------|----------|---------|
| **DecisionLogger** | `src/decision/decision_logger.py` | Full records with thesis linking |
| **AdversarialAgent** | `src/decision/adversary.py` | Challenge every trade |
| **MorningBriefing** | `src/decision/morning_briefing.py` | Pre-market context |

```python
# Run adversarial analysis
from src.decision.adversary import AdversarialAgent

adversary = AdversarialAgent()
analysis = adversary.challenge(
    symbol="SLB",
    proposed_action="BUY",
    reasoning="Venezuela thesis + pre-market strength",
    confidence=0.75,
    context={"sector_exposure": 0.45}
)

print(f"Concern Level: {analysis.overall_concern_level}")
print(f"Proceed: {analysis.proceed_recommendation}")
```

### Evaluation Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **StrategyDashboard** | `src/evaluation/comparison/dashboard.py` | Compare validated strategies |
| **MCPTAnalyzer** | `src/evaluation/validation/mcpt.py` | Monte Carlo permutation testing |
| **WalkForwardOptimizer** | `src/evaluation/validation/walk_forward.py` | Walk-forward validation |

```python
# Compare strategies
from src.evaluation.comparison import StrategyDashboard, get_strategy_leaderboard

dashboard = StrategyDashboard()
top_strategies = dashboard.get_top_performers(n=10, validated_only=True)
print(dashboard.generate_report())

# Quick leaderboard
print(get_strategy_leaderboard(top_n=5))
```

### Promotion Pipeline

| Component | Location | Purpose |
|-----------|----------|---------|
| **PromotionPipeline** | `src/execution/promotion/pipeline.py` | Backtest → Paper → Live lifecycle |
| **PromotionCandidate** | `src/execution/promotion/pipeline.py` | Strategy being promoted |
| **PromotionGates** | `src/execution/promotion/pipeline.py` | Requirements for advancement |

```python
# Manage strategy promotion
from src.execution.promotion import PromotionPipeline, PromotionStage

pipeline = PromotionPipeline()

# Add candidate from backtest
candidate = pipeline.add_candidate("momentum_breakout", "AAPL", backtest_metrics={
    "sharpe": 2.5, "max_drawdown": 12.0, "num_trades": 50
})

# Update after MCPT validation
pipeline.update_mcpt_results("momentum_breakout", "AAPL", p_value=0.02)

# Try to advance to paper trading
success, reason = pipeline.advance_stage("momentum_breakout", "AAPL")

# Check what's ready for live
ready = pipeline.get_ready_for_live()
print(pipeline.generate_report())
```

**Pipeline Stages:**
1. `BACKTEST` → Initial development
2. `MCPT_VALIDATION` → Statistical validation (p < 0.05)
3. `PAPER_TRADING` → Live paper trading (20+ days)
4. `PAPER_REVIEW` → Evaluate paper results (Sharpe > 0.5)
5. `LIVE_PENDING` → Awaiting human approval
6. `LIVE_TRADING` → Active in production

---

## Quick Commands

```bash
# Daily Trading
PYTHONPATH=. python scripts/research_prep.py              # Pre-compute research
PYTHONPATH=. python scripts/run_daily.py --mode signals   # Generate signals
PYTHONPATH=. python scripts/run_daily.py --mode paper     # Paper trading

# Research
PYTHONPATH=. python scripts/full_research_cycle.py        # Full research
PYTHONPATH=. python scripts/full_research_cycle.py --quick # Quick test

# Validation
PYTHONPATH=. python scripts/validate_strategy.py --strategy bollinger_reversal --symbol QCOM --plots
PYTHONPATH=. python scripts/critic_validate.py --strategy bollinger_reversal --symbol QCOM

# Monitoring
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard
```

---

## Trade Decision Framework

When making trading decisions, I should systematically consider:

### 1. Thesis Alignment

```python
from src.knowledge.thesis import ThesisTracker
tracker = ThesisTracker(paths.theses)
theses = tracker.get_theses_for_symbol("SLB")
```

- Is this symbol linked to an active thesis?
- What is the current conviction level?
- Have any signposts triggered recently?

### 2. Statistical Signal Quality

- Signal confidence and confirming indicators
- Historical performance of signal type
- Alignment with current market regime

### 3. Knowledge Base Context

```python
from src.knowledge.base import KnowledgeBase
kb = KnowledgeBase(paths.knowledge)
company = kb.get_company("SLB")
sector = kb.get_sector("energy")
```

### 4. Adversarial Challenge

**CRITICAL: Every trade gets challenged.**

```python
from src.decision.adversary import AdversarialAgent
adversary = AdversarialAgent()
analysis = adversary.challenge(symbol, action, reasoning, confidence, context)
```

### 5. Pre-Mortem

Before every BUY: "It's 30 days later and I lost money. What happened?"

### 6. Decision Logging

```python
from src.decision.decision_logger import create_decision, Action

decision = create_decision(
    symbol="SLB",
    action=Action.BUY,
    confidence=0.70,
    size_pct=10.0,
    reasoning="...",
    key_factors=["..."],
    risks=["..."],
    context={...},
    thesis_id="venezuela123",  # Link to thesis
    pre_mortem="Policy reversal forces exit",
    adversarial_notes="Concern: sector concentration",
)
```

---

## Trading Rules

### CRITICAL: Thesis Position Sizing (Learned 2026-01-07)

**HIGH CONVICTION ≠ HIGH CONCENTRATION**

When a thesis has multiple vehicles:

1. **START EQUAL WEIGHT**: Allocate thesis capital equally across ALL vehicles
   - Example: 6 Venezuela positions = ~6% each, not 22% SLB + 17% XLE

2. **LET WINNERS PROVE THEMSELVES**: Only concentrate AFTER 10%+ outperformance
   - The market knows timing better than you
   - Winners naturally grow; don't force it

3. **SEPARATE IMMEDIATE vs FUTURE BENEFICIARIES**:
   - Immediate: Benefit NOW (tankers shipping oil)
   - Future: Benefit LATER (services for reconstruction)
   - Equal weight captures the right timing

**Evidence (Venezuela thesis, 2026-01-07):**
- Concentrated allocation: +0.55% ROI
- Equal weight allocation: +1.92% ROI
- Difference: **~$1,000 left on the table**
- Tankers (1-9% each): +10-13%
- SLB+XLE (39% combined): -2 to -3%

See: `~/quant_results/knowledge/position_sizing.yaml`

### Position Sizing by Confidence
| Confidence | Max Size |
|------------|----------|
| 90%+ | 15% (not 20%) |
| 75-90% | 10% |
| 60-75% | 7% |
| <60% | 5% or HOLD |

### Risk Limits
| Limit | Value |
|-------|-------|
| Single position | **15% max** (reduced from 25%) |
| Single thesis total | **35% max** |
| Sector exposure | 40% max |
| Daily loss | 5% max |
| Stop loss | 5-15% based on conviction |

### PDT Compliance (<$25k)
- Max 3 day trades per 5 rolling business days
- 2-day minimum hold for swing trades
- Holiday calendar included (2024-2027) for accurate day counting
- Use `PDTManager` from `src/execution/pdt_manager.py`

### Trading Patterns Reference

**IMPORTANT**: When creating theses or making decisions, review accumulated wisdom:

```bash
cat docs/TRADING_PATTERNS.md
```

Key patterns (see file for full details):
- **Vehicle Enumeration**: Enumerate ALL thesis beneficiaries, not just obvious plays
- **Converging Signals**: Require 3+ independent signals aligned before high-conviction trades
- **Use Existing Data**: Check the 32+ alt-data sources we already have
- **Squeeze Mechanics**: High short interest + social spike = potential squeeze
- **Binary Events**: Position BEFORE known catalysts (FDA, earnings)

---

## Claude Code Skills (12)

### Daily Trading
| Skill | Purpose |
|-------|---------|
| `/morning-briefing` | Read unified state, research overnight news |
| `/trade-decision` | Synthesize + adversarial + thesis linking |
| `/execute-trades` | Execute with human approval |
| `/eod-review` | Extract learnings, update thesis |
| `/thesis` | **NEW** - Create/review/update theses |

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
| hypothesis-generator-agent | Insight to strategy |
| brainstorm-agent | Feature ideation |
| text-research-agent | Text analysis and embeddings research |

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
| **Unified State** | `~/quant_results/live/state.json` |
| **Pre-computed Research** | `~/quant_results/live/research/` |
| **Theses** | `~/quant_results/theses/` |
| **Learnings** | `~/quant_results/learnings/` |
| **Knowledge** | `~/quant_results/knowledge/` |
| **Skills** | `.claude/skills/*/SKILL.md` |
| **Agents** | `.claude/agents/*.md` |
| **Synthesis Layer** | `src/synthesis/` |
| **Knowledge Layer** | `src/knowledge/` |
| **Decision Engine** | `src/decision/` |
| **Strategies** | `src/strategies/` |
| **Alternative Data** | `src/data/sources/alternative/` |

---

## Output Directories

All outputs in configurable results directory (default: `~/quant_results`):

| Directory | Contents |
|-----------|----------|
| `live/state.json` | **THE source of truth** |
| `live/research/` | Pre-computed features, signals, screens |
| `theses/` | Investment thesis YAML files |
| `learnings/` | Monthly learning JSON files |
| `knowledge/companies/` | Company briefs |
| `knowledge/sectors/` | Sector context |
| `decisions/` | Trading decisions with reasoning |
| `briefings/` | Morning briefings |
| `eod_reviews/` | End-of-day reviews |

---

## Data Sources

### Statistical Signals
- **Technical**: RSI, MACD, Bollinger Bands, momentum (50+ features)
- **ML Models**: XGBoost, LightGBM (require MCPT validation)
- **Regime**: Volatility regime, trend detection

### Alternative Data (Core)
| Source | File | Signal Type |
|--------|------|-------------|
| **Congressional Trades** | `congressional_trades.py` | Cluster buying |
| **Prediction Markets** | `prediction_markets.py` | Fed policy, macro |
| **Expert Sentiment** | `expert_sentiment.py` | Inverse Cramer |
| **Insider Trading** | `insider.py` | Form 4 clusters |
| **Options Flow** | `options_flow.py` | Unusual activity |
| **Social Sentiment** | `social_sentiment.py` | Reddit/Twitter |

### Free Data Sources (20+)
| Category | Sources | Files |
|----------|---------|-------|
| **Market Regime** | VIX term structure, Put/call ratios, Finviz screens | `vix_structure.py`, `put_call.py`, `finviz_screens.py` |
| **Sentiment** | AAII survey, Newsletter sentiment, COT report | `aaii_sentiment.py`, `newsletter_sentiment.py`, `cot_report.py` |
| **Economic** | Earnings calendar, Economic releases, Fed futures, Treasury auctions | `earnings_calendar.py`, `economic_calendar.py`, `fed_futures.py`, `treasury_calendar.py` |
| **Events** | IPO calendar, FDA calendar | `ipo_calendar.py`, `fda_calendar.py` |
| **Innovation** | USPTO patents, Job postings, App rankings, GitHub activity | `patent_filings.py`, `job_postings.py`, `app_rankings.py`, `github_activity.py` |

All sources in `src/data/sources/alternative/`

---

## Real-Time Infrastructure

| Component | Module | Update Interval |
|-----------|--------|-----------------|
| **LiveDaemon** | `src/synthesis/daemon.py` | 5 min |
| **DataCollectionDaemon** | `src/data/sources/collection_daemon.py` | Variable |
| **News Daemon** | `src/data/sources/realtime/news_daemon.py` | 30 min |
| **Market Breadth** | `src/data/pipeline/market_breadth.py` | 5 min |
| **Sentiment** | `src/data/pipeline/sentiment.py` | 1 hour |
| **Alert Manager** | `src/alerts/alert_manager.py` | 1 min |
| **Position Risk** | `src/risk/position_monitor.py` | 15 min |

### Data Collection Daemon Schedules

```python
# Real-time (market hours only)
vix_structure: 15 min, put_call: 60 min, breadth: 5 min

# Hourly
fed_futures: 60 min

# Daily
finviz_screens: 4 hr, earnings_calendar: 6 hr, economic_calendar: 12 hr
ipo_calendar: 12 hr, fda_calendar: 12 hr, app_rankings: 24 hr, github_activity: 24 hr

# Weekly
aaii_sentiment: weekly, newsletter_sentiment: weekly, cot_report: weekly, patents: weekly

# Periodic
job_postings: 3 days
```

### Cron Jobs

| Script | Schedule | Purpose |
|--------|----------|---------|
| `research_prep.py` | 6:00 AM Mon-Fri | Pre-market research preparation |
| `cron_news_collect.py` | Every 4 hours | Collect market news and events |
| `cron_congressional_collect.py` | 6:30 AM daily | Collect congressional trades |
| `cron_insider_collect.py` | 7:00 AM daily | Collect insider trading (Form 4) |
| `LiveDaemon.update_now()` | Every 5 min Mon-Fri | Update unified state.json |
| `eod_snapshot.py` | 5:00 PM Mon-Fri | End-of-day data snapshot |
| `cron_thesis_signpost_check.py` | Hourly 6am-5pm Mon-Fri | Check thesis signposts for triggers |
| `cron_paper_trading_review.py` | 5:30 PM Mon-Fri | Review paper trading, advance pipeline |
| `cron_concentration_check.py` | Every 2 hours Mon-Fri | Monitor portfolio concentration |
| `cron_trade_wrapper.sh` | 9:31 AM Mon-Fri | Execute scheduled trades at market open |

```bash
# Install cron jobs
./scripts/setup_cron.sh install

# Check installed jobs
crontab -l | grep QUANT_SUITE_CRON
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

## Detailed Documentation

| Document | Purpose |
|----------|---------|
| `docs/EVALUATION_API.md` | Backtesting, validation, metrics |
| `docs/ALPHA_DISCOVERY.md` | Alternative data, market scanning |
| `docs/TEXT_RESEARCH.md` | Text research, embeddings |
| `docs/TRADING_GUIDE.md` | End-user trading guide |
| `docs/FREE_DATA_SOURCES.md` | Free data sources (20+) implementation guide |
| `docs/ARCHITECTURE_DIAGRAMS.md` | Complete system architecture |
| `DEVLOG.md` | Development progress |
| `RESEARCH_LOG.md` | Research findings |
