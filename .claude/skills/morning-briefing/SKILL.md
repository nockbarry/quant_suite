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
