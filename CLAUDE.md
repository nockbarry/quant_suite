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
| 9:30 AM+ | `claude "/operator-session"` | Enter persistent monitoring mode |
| When ready | `claude "/trade-decision"` | Adversarial analysis, make decisions |
| When ready | `claude "/execute-trades"` | Execute with your approval |
| 4:30 PM | `claude "/eod-review"` | Extract learnings, update conviction |

### Recommended Starting Prompts

```bash
# Morning - full briefing
claude "/morning-briefing"

# Enter operator mode (monitors every 3 min)
claude "/operator-session"

# Operator mode variants
claude "/operator-session --passive"   # 5 min checks
claude "/operator-session --active"    # 1 min checks

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

### CRITICAL: Read Before Writing Code

Before writing ANY Python code, read the API reference:
```bash
cat docs/API_QUICK_REF.md
```

This prevents common errors like:
- `state.is_fresh()` → doesn't exist
- `calendar.get_events_by_date_range()` → wrong method name
- `signpost.get('description')` → signposts are dataclasses, not dicts

### Morning Setup (Use Scripts, Not Code)

```bash
# One command to set up for trading
./scripts/morning_preflight.sh

# Full context dump for Claude sessions
PYTHONPATH=. python3 scripts/context_dump.py

# Quick summary only
PYTHONPATH=. python3 scripts/context_dump.py --brief
```

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

### Live Signal Layer (NEW)

| Component | Location | Purpose |
|-----------|----------|---------|
| **LiveSignalGenerator** | `src/signals/live_signal_generator.py` | Operationalized validated signals |
| **CandlePatternRecognizer** | `src/data/intraday/candle_analysis.py` | 25+ candle patterns for agents/ML |
| **IntradayFeatureEngine** | `src/data/intraday/feature_engine.py` | VWAP, ORB, volume profile |

Validated signals with MCPT-confirmed metrics:
- **Bollinger Bounce**: IC=0.31, Hit Rate=61.4% (BUY on lower band touch)
- **RSI Extreme**: IC=0.20, Hit Rate=53.8% (BUY <30, SELL >70)
- **Volume Spike FADE**: IC=0.69, CONTRARIAN (fade high volume moves)
- **Channel Breakout FADE**: IC=0.37, CONTRARIAN (fade breakouts)

```python
from src.signals import LiveSignalGenerator, get_signal_summary

# Generate signals for a symbol
generator = LiveSignalGenerator()
signals = await generator.generate_signals("AAPL", lookback_days=60)

# Check for convergences (3+ aligned signals)
convergences = generator.detect_convergence(signals)
for conv in convergences:
    print(f"{conv.symbol}: {conv.signal_count} {conv.direction} signals")
```

### Monitoring Layer (ENHANCED)

| Component | Location | Purpose |
|-----------|----------|---------|
| **ComprehensiveDashboard** | `src/monitoring/comprehensive_dashboard.py` | Full system view with Claude activity |
| **SwarmMonitor** | `src/monitoring/swarm_monitor.py` | Track agent swarms, detect signal convergences |
| **SwarmVisualizer** | `src/monitoring/swarm_visualizer.py` | **NEW** - Timeline + heatmap displays for swarm activity |
| **AgentActivityMonitor** | `src/monitoring/agent_monitor.py` | Track Claude sessions and agents |
| **OperatorLoop** | `src/monitoring/operator_loop.py` | Check cycle logic for operator mode |
| **DataFreshnessTracker** | `src/monitoring/data_freshness_tracker.py` | Data source health |

```python
# Comprehensive dashboard - shows Claude's activity + full system state
from src.monitoring import ComprehensiveDashboard

dashboard = ComprehensiveDashboard()
status = await dashboard.get_comprehensive_status()

# Claude's current activity
print(f"Running agents: {status.claude_activity.agents_running}")
print(f"Decisions today: {status.claude_activity.decisions_today}")

# Market theme
print(f"Theme: {status.current_theme.primary_theme}")

# Or run from command line:
# PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard --watch
```

### Knowledge Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **ThesisTracker** | `src/knowledge/thesis.py` | Investment theses with signposts |
| **ThesisPerformanceTracker** | `src/knowledge/thesis_performance.py` | P&L attribution by thesis |
| **SignalProvenanceTracker** | `src/knowledge/signal_provenance.py` | **NEW** - Track signals from discovery to outcome |
| **ThesisSuggester** | `src/knowledge/thesis_suggester.py` | **NEW** - Auto-suggest theses from converging signals |
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

### Monitoring Layer (NEW)

| Component | Location | Purpose |
|-----------|----------|---------|
| **UnifiedDashboard** | `src/monitoring/unified_dashboard.py` | Full system status + signals |
| **OperatorLoop** | `src/monitoring/operator_loop.py` | Persistent monitoring checks |
| **DataFreshnessTracker** | `src/monitoring/data_freshness_tracker.py` | Track data source status + content |
| **SignalAggregator** | `src/monitoring/signal_summary.py` | Aggregate all signals into actionable items |
| **ImprovementTracker** | `src/monitoring/improvement_tracker.py` | Auto-generated improvement suggestions |
| **SignalQualityTracker** | `src/monitoring/signal_quality_tracker.py` | Track signal hit rates over time |

```python
# Get unified system status with all data sources
from src.monitoring.unified_dashboard import UnifiedDashboard

dashboard = UnifiedDashboard()
status = await dashboard.get_unified_status()
print(f"Market Regime: {status.market_regime}")
print(f"Top Signals: {len(status.top_signals)}")
print(f"Convergences: {len(status.convergences)}")

# Run operator check cycle
from src.monitoring.operator_loop import OperatorLoop

loop = OperatorLoop()
observation = loop.operator_check(check_num=1)
print(loop.format_observation(observation))

# Track signal quality
from src.monitoring.signal_quality_tracker import log_signal_outcome

log_signal_outcome(
    signal_type="congressional",
    symbol="NVDA",
    direction="bullish",
    signal_strength=0.85,
    acted_on=True,
    pnl=250.0,
    pnl_pct=2.5,
)
```

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

# Monitoring - COMPREHENSIVE DASHBOARD (recommended)
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard        # Full view with Claude activity
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard --watch # Auto-refresh every 60s
PYTHONPATH=. python -m src.monitoring.unified_dashboard              # Simpler unified view
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard        # Portfolio only

# Day Trading Signals
PYTHONPATH=. python scripts/run_day_trading_signals.py --scan        # Scan for signals
PYTHONPATH=. python scripts/run_day_trading_signals.py --deploy-paper # Deploy to paper trading
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

### CRITICAL: Performance-Based Rules (Updated 2026-01-21)

Based on analysis of 82 trades from Jan 5-21, 2026:

| Category | # Trades | Avg Return | Verdict |
|----------|----------|------------|---------|
| Current stock holdings | 51 | **+7.75%** | ✅ Excellent |
| Closed stocks | 7 | **-6.66%** | ❌ Exited too early |
| Options | 24 | **-14.25%** | ❌ AVOID |

**See**: `~/quant_results/reports/performance_analysis_20260121.md`

---

### Rule 1: NO OPTIONS TRADING

**Options averaged -14.25% return. Do not trade options.**

Exceptions (require explicit user approval):
- Deep ITM calls as stock replacement (delta > 0.80)
- Protective puts for existing large positions
- Covered calls on positions we want to exit

Evidence: 24 options trades, only 6 profitable, average loss -14.25%

---

### Rule 2: HOLD POSITIONS - Don't Exit Early

**Closed stocks averaged -6.66%. Current holdings average +7.75%.**

Our exits were consistently wrong:
- VLO: Sold at $178, now $185 (left $534 on table)
- JPM: Sold at $310, now $288 (saved $137)
- CEG: Sold at $299, now $289 (saved $60)
- Net: Lost money by exiting

**Exit ONLY when:**
1. Signpost invalidates thesis (bearish trigger)
2. Position hits -15% stop loss
3. Thesis conviction drops below 40%
4. Concentration limits require rebalancing

**Do NOT exit because:**
- Position is slightly negative
- "Taking profits" on small gains
- Nervous about market conditions
- Position "feels" wrong without data

---

### Rule 3: Equal Weight Within Theses

When a thesis has multiple vehicles:

1. **START EQUAL WEIGHT**: Allocate thesis capital equally across ALL vehicles
   - Example: 25 Venezuela positions = ~2% each, not 14% SLB + 7% HAL

2. **LET WINNERS PROVE THEMSELVES**: Only concentrate AFTER 10%+ outperformance
   - Our top 3 positions (SLB, HAL, XLE) returned 7.6% average
   - Our smaller positions returned 10.2% average
   - Equal weight would have added ~$235 to returns

3. **SEPARATE IMMEDIATE vs FUTURE BENEFICIARIES**:
   - Immediate: Tankers (FRO +24.6%, INSW +21.5%) moved first
   - Future: Services (SLB +12.1%, HAL +5.7%) moved later
   - Equal weight captures the right timing

---

### Rule 4: Stock Picking Works - Keep Doing It

Our stock selection is excellent:
- 90% hit rate (44 of 49 positions profitable)
- Venezuela thesis: +9.9% average across 25 stocks
- Gold thesis: +13.2% average across 6 stocks
- Current holdings: +7.75% average

**Keep doing:**
- Thesis-based investing with clear signposts
- Diversifying across multiple vehicles per thesis
- Holding winners and letting them compound

---

### Position Sizing by Confidence
| Confidence | Max Size |
|------------|----------|
| 90%+ | 10% (reduced from 15%) |
| 75-90% | 7% |
| 60-75% | 5% |
| <60% | 3% or HOLD |

### Risk Limits
| Limit | Value |
|-------|-------|
| Single position | **10% max** (reduced from 15%) |
| Single thesis total | **40% max** |
| Sector exposure | 45% max |
| Daily loss | 5% max |
| Stop loss | 15% (only exit trigger) |

### Exit Checklist (ALL must be checked before selling)

Before ANY sell order, answer:
- [ ] Is a bearish signpost triggered?
- [ ] Has thesis conviction dropped below 40%?
- [ ] Is position at -15% stop loss?
- [ ] Does concentration require rebalancing?

If NONE checked → **DO NOT SELL**

---

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
- **NO OPTIONS**: Options lost -14.25% on average - avoid them

---

## Claude Code Skills (15)

### Daily Trading
| Skill | Purpose |
|-------|---------|
| `/morning-briefing` | Read unified state, research overnight news |
| `/operator-session` | Persistent monitoring with configurable intervals |
| `/swarm-operator` | Orchestrate multi-agent swarms (trading, research, modeling) |
| `/social-signals` | **NEW** - Check WSB, Stocktwits for early alpha signals |
| `/trade-decision` | Synthesize + adversarial + thesis linking |
| `/execute-trades` | Execute with human approval |
| `/eod-review` | Extract learnings, update thesis |
| `/thesis` | Create/review/update theses |

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

### Agent Activity Logging

**Log agent activity for monitoring and improvement tracking:**

```python
from src.monitoring import log_agent_start, log_agent_complete

# When starting agent work
agent_id = log_agent_start("research", "Strategy testing: NVDA bollinger_reversal")

# When completing
log_agent_complete(agent_id,
    summary="Tested 15 strategies, 2 significant (Sharpe > 1.5)",
    success=True
)
```

View logged activity:
```bash
tail -20 ~/quant_results/logs/agent_activity.jsonl
```

---

## Key File Locations

| Category | Path |
|----------|------|
| **Unified State** | `~/quant_results/live/state.json` |
| **Pre-computed Research** | `~/quant_results/live/research/` |
| **Theses** | `~/quant_results/theses/` |
| **Learnings** | `~/quant_results/learnings/` |
| **Knowledge** | `~/quant_results/knowledge/` |
| **Improvements** | `~/quant_results/improvements/` |
| **Signal Quality** | `~/quant_results/signal_quality/` |
| **Operator Logs** | `~/quant_results/logs/operator_log.jsonl` |
| **Skills** | `.claude/skills/*/SKILL.md` |
| **Agents** | `.claude/agents/*.md` |
| **Synthesis Layer** | `src/synthesis/` |
| **Knowledge Layer** | `src/knowledge/` |
| **Decision Engine** | `src/decision/` |
| **Monitoring Layer** | `src/monitoring/` |
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
| `improvements/` | Auto-generated improvement suggestions |
| `signal_quality/` | Signal quality metrics and outcomes |
| `logs/operator_log.jsonl` | Operator session observations |

---

## Data Sources

### Statistical Signals
- **Technical**: RSI, MACD, Bollinger Bands, momentum (50+ features)
- **ML Models**: XGBoost, LightGBM (require MCPT validation)
- **Regime**: Volatility regime, trend detection

### Alternative Data (40+ Sources)

| Category | Key Sources |
|----------|-------------|
| **Core** | Congressional trades, Insider trading, Options flow, Social sentiment |
| **Social (NEW)** | WSB Tracker (Reddit), Stocktwits, Social Time-Series DB |
| **Market Regime** | VIX structure, Put/call ratios, Finviz screens, Breadth |
| **Sentiment** | AAII survey, Newsletter sentiment, COT report, Expert sentiment |
| **Economic** | Earnings calendar, Economic releases, Fed futures, Treasury |
| **Events** | IPO calendar, FDA calendar (PDUFA dates) |
| **Innovation** | Patents, Job postings, App rankings, GitHub activity |
| **News** | 20+ RSS feeds (WSJ, CNBC, FT, Fed, SEC, sector-specific) |
| **Geopolitical** | 5-region tracking (Greenland, Venezuela, China, ME, Russia) |
| **Legal** | SCOTUS cases, SEC enforcement, FTC, DOJ tracking |

All sources in `src/data/sources/alternative/`

### Social Signal Tracking (NEW)

```python
# Scan WSB for early signals
from src.data.sources.alternative.wsb_tracker import get_wsb_tracker
import asyncio

tracker = get_wsb_tracker()
mentions = asyncio.run(tracker.scan_recent_posts())
early_signals = tracker.get_early_signals()  # < 7 days, growing momentum

# Track signal provenance
from src.knowledge.signal_provenance import create_signal_provenance
signal = create_signal_provenance(
    source="wsb",
    symbol="WDC",
    confidence=0.7,
    direction="bullish",
    description="SanDisk spin-off DD gaining traction",
)

# Auto-suggest theses from converging signals
from src.knowledge.thesis_suggester import get_thesis_suggester
suggester = get_thesis_suggester()
suggestions = suggester.generate_suggestions()  # 3+ signals = suggestion
```

---

## Hedge Fund Capabilities

### Alerting & Execution
| Module | Purpose |
|--------|---------|
| `smart_alerter.py` | Signal convergence detection across sources |
| `mobile_bot.py` | Telegram/Discord alerts with rate limiting |
| `rules_engine.py` | Auto-execution rules (AUTO/QUEUE/NOTIFY) |
| `drawdown_protection.py` | 5-level protection (5%→15% triggers) |

### Analysis & Optimization
| Module | Purpose |
|--------|---------|
| `portfolio_optimizer.py` | Risk parity, mean-variance, Kelly criterion |
| `sector_rotation.py` | Sector leadership tracking & cycle phases |
| `performance_attribution.py` | P&L attribution by thesis/signal |
| `earnings_predictor.py` | 7-signal earnings surprise prediction |

### Real-Time & Tax
| Module | Purpose |
|--------|---------|
| `websocket_feed.py` | Alpaca/Finnhub WebSocket + polling fallback |
| `tax_loss_harvester.py` | Wash sale tracking, substitute securities |
| `trade_journal.py` | Full trade tracking with context/learnings |

---

## Real-Time Infrastructure

| Component | Module | Update Interval |
|-----------|--------|-----------------|
| **LiveDaemon** | `src/synthesis/daemon.py` | 5 min |
| **DataCollectionDaemon** | `src/data/sources/collection_daemon.py` | Variable |
| **WebSocket Feed** | `src/data/realtime/websocket_feed.py` | Real-time |
| **News Daemon** | `src/data/sources/realtime/news_daemon.py` | 30 min |
| **Market Breadth** | `src/data/pipeline/market_breadth.py` | 5 min |
| **Sentiment** | `src/data/pipeline/sentiment.py` | 1 hour |
| **Smart Alerter** | `src/alerts/smart_alerter.py` | On signal |
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
| `cron_weekly_improvement_review.py` | Sunday 6 PM | Weekly improvement analysis |

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

## Documentation Guide

### Start Here (By Task)

| If You Need To... | Read This |
|-------------------|-----------|
| **Trade daily** | `docs/WORKFLOW.md` - Daily trading workflow |
| **Create a thesis** | `docs/TRADING_PATTERNS.md` - Meta-learnings & vehicle enumeration |
| **Understand the system** | `docs/ARCHITECTURE_DIAGRAMS.md` - Full system architecture |
| **Run autonomous trading** | `docs/AUTONOMOUS_TRADING_ARCHITECTURE.md` - Swarm intelligence & agent frameworks |
| **Find data sources** | `docs/FREE_DATA_SOURCES.md` - 40+ implemented sources |
| **See hedge fund features** | `docs/ARCHITECTURE_DIAGRAMS.md` Section 14 - HF expansion modules |
| **Identify opportunities** | `docs/ALTERNATIVE_DATA_OPPORTUNITIES.md` - Missed opportunities analysis |

### Reference Documentation

| Document | Purpose |
|----------|---------|
| `docs/AUTONOMOUS_TRADING_ARCHITECTURE.md` | Swarm intelligence, agent frameworks, cost analysis |
| `docs/EVALUATION_API.md` | Backtesting, validation, metrics |
| `docs/ALPHA_DISCOVERY.md` | Alternative data, market scanning |
| `docs/TEXT_RESEARCH.md` | Text research, embeddings |
| `docs/TRADING_GUIDE.md` | End-user trading guide |
| `docs/REALTIME_DATA_SPEC.md` | Real-time infrastructure |
| `docs/API_QUICK_REF.md` | API method signatures |

### Development History

| Document | Purpose |
|----------|---------|
| `DEVLOG.md` | Development progress log |
| `RESEARCH_LOG.md` | Research findings and experiments |
| `docs/HEDGE_FUND_EXPANSION_PLAN.md` | Completed expansion roadmap (archive) |
