---
name: morning-briefing
description: Generate pre-market research briefing with overnight news, market data, and alternative signals. Run this before market open (6-8am ET) to inform trading decisions. Outputs structured JSON and markdown summary.
allowed-tools: Read, Bash(PYTHONPATH=*), Bash(curl:*), Glob, Grep, Write, WebSearch, WebFetch
---

# Morning Briefing Skill

Pre-market research and intelligence gathering for informed trading decisions.

## Purpose

This skill gathers and synthesizes:
1. **Overnight news** - Market-moving events while you slept
2. **Pre-market data** - Futures, gap direction, volume
3. **Alternative signals** - Congressional trades, prediction markets, options flow
4. **Portfolio context** - Current positions and risk exposure
5. **Active theses** - Investment theses with pending signposts
6. **Pending decisions** - Decisions awaiting outcomes

## Quick Start

### Option 1: Read From Unified State (Preferred)

If the LiveDaemon is running, just read the state file:

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.synthesis.state import UnifiedState
from src.core.paths import paths

# Load unified state
state = UnifiedState.load(paths.live_state)
if state:
    print(state.get_summary())
else:
    print("No unified state available. Run daemon or generate briefing directly.")
EOF
```

### Option 2: Generate Fresh Briefing

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
import asyncio
from datetime import datetime
from src.decision.morning_briefing import MorningBriefingGenerator

async def main():
    generator = MorningBriefingGenerator()
    briefing = await generator.generate()
    briefing.save()
    print(briefing.to_markdown())

asyncio.run(main())
EOF
```

### Option 3: Update Unified State Now

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
import asyncio
from src.synthesis.daemon import LiveDaemon

async def main():
    daemon = LiveDaemon()
    state = await daemon.update_now()
    print(state.get_summary())

asyncio.run(main())
EOF
```

## What's in Unified State

When you read `~/quant_results/live/state.json`, you get:

| Section | Contents |
|---------|----------|
| `market` | Market breadth, futures, VIX, regime |
| `sentiment` | Fear/greed, put/call ratio, retail sentiment |
| `portfolio` | Equity, cash, buying power, day P&L |
| `positions` | Current holdings with unrealized P&L |
| `risk` | Portfolio beta, VaR, sector exposure |
| `watchlist_signals` | Aggregated signals for watchlist |
| `theses` | Active investment theses with conviction |
| `pending_decisions` | Decisions awaiting outcomes |
| `recent_learnings` | Recent trade lessons |
| `alerts` | Active alerts |
| `upcoming_events` | Earnings, Fed, etc. |
| `research_available` | Paths to pre-computed research files |
| `alternative_signals` | **NEW**: Weather→energy, FDA calendar, squeeze candidates, research insights |

## Research Files Available

Pre-computed research (run `scripts/research_prep.py` before market):

```bash
# Features for watchlist
cat ~/quant_results/live/research/features.json

# Strategy signals
cat ~/quant_results/live/research/signals.json

# Alternative data summary
cat ~/quant_results/live/research/alt_data.json

# Stock screens
cat ~/quant_results/live/research/screens.json
```

## Active Theses Review

Check active investment theses:

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
theses = tracker.get_active_theses()

for thesis in theses:
    print(f"\n=== {thesis.name} ===")
    print(f"Conviction: {thesis.conviction:.0f}%")
    print(f"Positions: {', '.join(thesis.positions)}")

    pending = thesis.get_pending_signposts()
    if pending:
        print(f"Next signpost: {pending[0].description}")

    if thesis.check_review_due():
        print("** REVIEW DUE **")
EOF
```

## Pending Decisions

Check decisions awaiting outcomes:

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
pending = logger.get_pending_decisions()

if pending:
    print(f"{len(pending)} pending decisions:")
    for d in pending:
        print(f"  {d.action.value} {d.symbol} @ {d.timestamp.strftime('%Y-%m-%d %H:%M')}")
else:
    print("No pending decisions")
EOF
```

## CRITICAL: Load Trading Patterns First

Before generating briefing, review accumulated trading wisdom:

```bash
cat /home/nock/projects/quant_suite/docs/TRADING_PATTERNS.md
```

Key patterns to check every morning:
- **Pattern 2**: Converging Signals - look for 3+ signals aligned
- **Pattern 3**: Data Source Check - check ALL alt-data sources
- **Pattern 5**: Binary Events - review upcoming catalysts
- **Pattern 6**: Weather → Commodities - check HDD/CDD anomalies
- **Pattern 9**: Social Spikes - check for mention surges

## Research Process

When this skill runs, Claude should:

### Step 0: Load Trading Patterns
```bash
# Read the patterns file to ensure all checks are performed
cat /home/nock/projects/quant_suite/docs/TRADING_PATTERNS.md | head -200
```

### Step 1: Check Unified State
```python
from src.synthesis.state import UnifiedState
from src.core.paths import paths

state = UnifiedState.load(paths.live_state)
if state and state.is_fresh(max_age_minutes=30):
    # Use existing state
    summary = state.get_summary()
else:
    # State stale - update it
    from src.synthesis.daemon import LiveDaemon
    daemon = LiveDaemon()
    state = await daemon.update_now()
```

### Step 1.5: Check Alternative Signals (NEW - Added 2026-01-19)

The unified state now includes `alternative_signals` from previously disconnected data sources:

```python
# Alternative signals are in state.alternative_signals
if state.alternative_signals:
    alt = state.alternative_signals

    # Weather → Energy signals
    if alt.get("weather_signals"):
        print("=== WEATHER ALERTS ===")
        for sig in alt["weather_signals"]:
            print(f"  {sig['signal_type']}: {sig['description']}")
            print(f"  Affected: {', '.join(sig['affected_symbols'])}")

    # FDA Binary Events (upcoming PDUFA dates, AdCom meetings)
    if alt.get("fda_signals"):
        print("=== FDA CALENDAR ===")
        for sig in alt["fda_signals"]:
            print(f"  {sig['symbol']}: {sig['drug_name']} {sig['event_type']}")
            print(f"  {sig['days_until']} days until event")
            print(f"  Est. approval: {sig['approval_probability']:.0%}")

    # Squeeze Candidates (high short interest + social mentions)
    if alt.get("squeeze_candidates"):
        print("=== SQUEEZE WATCH ===")
        for c in alt["squeeze_candidates"][:5]:
            print(f"  {c['symbol']}: Score {c['squeeze_score']:.2f}")
            print(f"    Short: {c['short_percent_of_float']:.1%}, Days to cover: {c['days_to_cover']:.1f}")

    # Research Insights (unimplemented strategies, patterns)
    if alt.get("research_insights"):
        ri = alt["research_insights"]
        if ri["actionable_unimplemented"] > 0:
            print(f"=== RESEARCH INSIGHTS ({ri['actionable_unimplemented']} actionable) ===")
            for insight in ri["top_insights"][:3]:
                print(f"  [{insight['category']}] {insight['title']}")
                print(f"    Confidence: {insight['confidence']:.0%}")
```

Or generate fresh alternative signals:
```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 -m src.synthesis.alternative_signals --all
```

### Step 1.6: Check Market Calendar (NEW - Added 2026-01-20)

Review upcoming events and predictions:

```python
from src.knowledge.market_calendar import MarketCalendar
from datetime import date, timedelta

calendar = MarketCalendar()

# Get upcoming week events
print("=== UPCOMING EVENTS (7 days) ===")
for event in calendar.get_upcoming_events(days=7, min_impact=EventImpact.MEDIUM):
    impact_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(event.impact.value, "⚪")
    print(f"{impact_emoji} {event.date}: {event.title}")
    print(f"   {event.description[:80]}...")
    if event.symbols_affected:
        print(f"   Symbols: {', '.join(event.symbols_affected[:5])}")

# Get predictions due for review
print("\n=== PREDICTIONS DUE FOR REVIEW ===")
for pred in calendar.get_predictions_due_for_review():
    print(f"📊 {pred.title} ({pred.source})")
    print(f"   {pred.prediction[:80]}...")
    print(f"   ID: {pred.id}")
```

Or use CLI:
```bash
# View this week's events
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py events --week

# View predictions due for review
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py predictions --due
```

**Key Calendar Items to Check:**
- **Fed/FOMC dates** - Position before, vol crush after
- **CPI/Jobs days** - Major volatility expected
- **Earnings** - Binary events for portfolio holdings
- **OpEx/Witching** - Pin risk, gamma exposure
- **Political events** - Election effects, policy deadlines

### Step 1.7: Check Improvement Suggestions (NEW - Added 2026-01-20)

Review pending improvements from the continuous improvement loop:

```python
from src.monitoring.improvement_tracker import get_improvement_tracker

tracker = get_improvement_tracker()

# Get high-priority pending improvements
pending = tracker.get_pending()
high_priority = [s for s in pending if s.priority == "high"]

if high_priority:
    print("=== HIGH PRIORITY IMPROVEMENTS ===")
    for suggestion in high_priority:
        print(f"  [{suggestion.category}] {suggestion.title}")
        print(f"    Action: {suggestion.suggested_action}")

# Get summary
summary = tracker.get_summary()
print(f"\nTotal pending: {summary['by_status'].get('pending', 0)}")
print(f"High priority: {summary['pending_high_priority']}")
```

### Step 1.8: Check Signal Convergences (NEW - Added 2026-01-20)

Look for symbols with 3+ aligned signals:

```python
from src.monitoring.signal_summary import get_signal_summary

summary = get_signal_summary()

print(f"=== MARKET REGIME: {summary.regime.upper()} ===")
for sig in summary.regime_signals:
    print(f"  - {sig}")

if summary.convergences:
    print("\n=== SIGNAL CONVERGENCES ===")
    for conv in summary.convergences:
        direction_emoji = "📈" if conv.direction == "bullish" else "📉"
        print(f"  {direction_emoji} {conv.symbol}: {len(conv.signals)} signals ({conv.convergence_score:.0%} strength)")
        print(f"    Types: {', '.join(set(s.type for s in conv.signals))}")

print("\n=== TOP SIGNALS ===")
for sig in summary.top_signals[:5]:
    print(f"  [{sig.type}] {sig.symbol or 'MARKET'}: {sig.description[:50]}")
```

### Step 1.9: Check Data Freshness (NEW - Added 2026-01-20)

Verify all data sources are fresh:

```python
from src.monitoring.data_freshness_tracker import get_data_freshness

freshness = get_data_freshness()

print(f"=== DATA SOURCES ({freshness.healthy_sources}/{freshness.total_sources} healthy) ===")

# Show stale sources first
stale = [name for name, s in freshness.sources.items() if s.status == "stale"]
if stale:
    print(f"  ⚠️ STALE: {', '.join(stale)}")

# Show top signals from each source
print("\nTop signals by source:")
for name, status in freshness.sources.items():
    if status.top_signal and status.signal_count > 0:
        print(f"  [{status.status[:3]}] {name}: {status.top_signal[:50]}")
```

### Step 2: Web Search for Overnight News
```
Search: "stock market news today [current date]"
Search: "fed interest rates news"
Search: "[sectors in portfolio] sector news"
```

### Step 3: Review Active Theses
- Are any signposts about to trigger?
- Any overnight news affecting thesis positions?
- Any theses due for review?

### Step 4: Check Pre-Computed Research
```python
import json
research_dir = paths.live / "research"

# Load signals
with open(research_dir / "signals.json") as f:
    signals = json.load(f)

# Load screens
with open(research_dir / "screens.json") as f:
    screens = json.load(f)
```

### Step 5: Run Morning Checklist (NEW - Added 2026-01-08)

For each active thesis position, systematically check:

```
MORNING CHECKLIST
═══════════════════════════════════════════════════════════

THESIS: [Name]
Conviction: [X]%

□ VALIDITY CHECK
  - Any invalidation triggers hit? [Y/N]
  - If Y, what action needed?

□ OVERSOLD SCAN
  - Any thesis positions down >2% yesterday on valid thesis? [Y/N]
  - If Y, flag as potential ADD opportunity

□ NEWS REINFORCEMENT
  - Does overnight news SUPPORT or CONTRADICT thesis?
  - News impact score: [calculate below]

□ SECTOR ROTATION
  - Is sector rotating IN or OUT?
  - Tailwind or headwind?

□ REGIME CHECK
  - VIX level: [X] (calm <15, elevated 15-25, fear >25)
  - Risk-on or risk-off?

DECISION PER POSITION:
  [SYMBOL]: ADD / HOLD / TRIM
  Reasoning: [brief]

═══════════════════════════════════════════════════════════
```

### Step 5b: Score News Impact (NEW)

For each significant news item, calculate impact score:

```
NEWS IMPACT SCORE
─────────────────────────────────────────────────────────
Headline: [headline]

Relevance (1-5):  How related to active thesis?        [X]
Sentiment (1-5):  Bullish=5, Neutral=3, Bearish=1      [X]
Magnitude (1-5):  Market-moving potential              [X]
Surprise (1-5):   Expected=1, Total surprise=5         [X]

SCORE = (R × S × M × Su) / 625 = [X.XX]

Interpretation:
  > 0.50 = STRONG signal - consider action
  0.20-0.50 = MODERATE signal - monitor closely
  < 0.20 = WEAK signal - note but no action
─────────────────────────────────────────────────────────
```

### Step 5c: Check Sold Position Tracker (NEW)

```bash
# Check if any recently sold positions have moved significantly
cat ~/quant_results/tracking/sold_positions.json
```

Flag any sold positions up >5% since sale for learning review.

### Step 6: Synthesize and Recommend
Based on research:
- Overall market sentiment
- Thesis-driven opportunities
- Specific opportunities or risks
- Recommended focus for today
- **ADD opportunities** (oversold thesis positions)
- **Regret check** (sold positions that moved)

## Output Format

Save briefings to: `/home/nock/quant_results/briefings/briefing_YYYYMMDD.json`

```json
{
  "date": "2026-01-06",
  "generated_at": "2026-01-06T07:00:00",
  "market_sentiment": "neutral_to_bullish",

  "overnight_news": [
    {
      "headline": "Fed signals patience on rate cuts",
      "source": "Reuters",
      "symbols_affected": ["SPY", "QQQ", "TLT"],
      "sentiment": "neutral",
      "importance": "high"
    }
  ],

  "pre_market": {
    "sp500_futures": "+0.3%",
    "nasdaq_futures": "+0.4%",
    "vix": 14.5
  },

  "active_theses": [
    {
      "name": "Venezuela Energy Recovery",
      "conviction": 65,
      "positions": ["SLB", "HAL"],
      "status": "Active - monitoring",
      "next_signpost": "Chevron license extension"
    }
  ],

  "pending_decisions": [
    {
      "symbol": "HAL",
      "action": "BUY",
      "status": "pending",
      "created": "2026-01-05T14:00:00"
    }
  ],

  "portfolio_exposure": {
    "total_equity": 95888,
    "sector_breakdown": {"energy": 45, "tech": 20, "other": 35}
  },

  "alternative_signals": {
    "congressional_trades": [],
    "options_flow": [],
    "social_sentiment": {}
  },

  "focus_areas": [
    "Venezuela thesis still playing out - monitor SLB, HAL",
    "Fed commentary tomorrow - position accordingly"
  ],

  "risk_warnings": [
    "Heavy energy concentration (45%)"
  ]
}
```

## Register Output as Document

After saving the briefing, index it so it appears in `/documents` and cross-references work:

```python
from src.db.write_api import athena_db

# This happens automatically in MorningBriefing.save(), but if you
# write a custom briefing file (e.g. markdown), register it manually:
athena_db.save_document(
    doc_type="briefing",
    title=f"Morning Briefing — {date}",
    file_path=str(filepath),
    source="skill:morning-briefing",
    symbols=["SLB", "HAL", "GLD"],  # symbols discussed
    tags=["briefing", "pre-market"],
)
```

## Query Historical Context

Before generating the briefing, check what documents and insights exist for relevant symbols:

```python
from src.db.write_api import athena_db

# Get recent documents for a symbol
recent = athena_db.get_recent_documents(limit=5)
for doc in recent:
    print(f"  [{doc.doc_type}] {doc.title}")

# Search for relevant insights
insights = athena_db.search_insights("energy sector")
for ins in insights:
    print(f"  [{ins.category}] {ins.title} (confidence: {ins.confidence})")

# Get full context for a symbol (documents + decisions + theses)
symbol_docs = athena_db.get_documents_for_symbol("SLB", limit=10)
```

Or use the convenience script:
```bash
PYTHONPATH=. python3 scripts/context_for_symbol.py SLB
```

## Integration with Trade Decisions

The briefing (or unified state) is consumed by `/trade-decision`:

```python
# In trade-decision skill
from src.synthesis.state import UnifiedState
from src.core.paths import paths

state = UnifiedState.load(paths.live_state)
# Use state.market, state.portfolio, state.theses, etc.
```

## Schedule

| Time (ET) | Action |
|-----------|--------|
| 6:00 AM | Run research_prep.py to pre-compute data |
| 6:30 AM | Run morning briefing / update daemon |
| 7:00 AM | Review briefing output |
| 7:30 AM | Feed to /trade-decision |

## Key Files

| File | Purpose |
|------|---------|
| `~/quant_results/live/state.json` | Unified state (ONE file to read) |
| `~/quant_results/live/research/` | Pre-computed research files |
| `~/quant_results/briefings/` | Saved briefings |
| `~/quant_results/theses/` | Investment theses |
| `~/quant_results/decisions/` | Trading decisions |
| `~/quant_results/knowledge/calendar/` | Market calendar, predictions, learnings |

## Adding Learnings from Briefing

When you discover something important during the briefing, add it to the calendar:

```bash
# Add a learning linked to an upcoming event
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py learn \
    "Fed more hawkish than expected, markets priced in 2 cuts but only 1 likely" \
    --source briefing \
    --event fomc_2026_01 \
    --tags fed,rates,hawkish

# Add a learning about a prediction
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py learn \
    "Goldman's rate cut prediction looking less likely given strong jobs data" \
    --source briefing \
    --prediction pred_fed_cuts_2026_gs \
    --tags fed,prediction

# Add a general market learning
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py learn \
    "Tech earnings beat but sold off - market rotating to value" \
    --source briefing \
    --symbol MSFT \
    --tags earnings,rotation,tech
```

Or in Python:
```python
from src.knowledge.market_calendar import MarketCalendar

calendar = MarketCalendar()
calendar.add_learning(
    content="CPI came in hot, Fed likely to delay cuts",
    source="briefing",
    event_id="cpi_2026-01-14",
    tags=["cpi", "inflation", "fed"],
)
```

## Resolving Predictions

When a prediction's target date arrives, resolve it:

```bash
# Mark a prediction as correct
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py resolve \
    claude_midterm_pattern_2026 \
    --status correct \
    --outcome "SPY rallied 10% from October low to year-end as predicted" \
    --accuracy 0.85

# Mark a prediction as incorrect
PYTHONPATH=/home/nock/projects/quant_suite python scripts/calendar_cli.py resolve \
    pred_fed_cuts_2026_gs \
    --status incorrect \
    --outcome "Fed only cut once, not twice as predicted" \
    --notes "Inflation stickier than expected"
```
