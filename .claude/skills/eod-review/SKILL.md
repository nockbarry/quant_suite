---
name: eod-review
description: End-of-day review and learning loop. Evaluates today's decisions vs outcomes, updates knowledge base with insights, and prepares for tomorrow. Run after market close (4pm+ ET).
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# EOD Review Skill

End-of-day analysis and learning loop for continuous improvement.

## Purpose

This skill:
1. Reviews today's trading decisions and outcomes
2. Compares predictions to actual results
3. **Extracts learnings** and stores them in learning log
4. **Updates thesis conviction** based on signpost checks
5. Updates knowledge base with insights
6. Prepares focus areas for tomorrow

## Quick Start

### Step 1: Get Performance Summary

```bash
PYTHONPATH=. python3 << 'EOF'
from datetime import datetime
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
decisions = logger.get_today_decisions()
summary = logger.get_performance_summary(days=7)

print(f"=== EOD Review - {datetime.now().strftime('%Y-%m-%d')} ===")
print(f"Decisions today: {len(decisions)}")
print(f"7-day win rate: {summary.get('win_rate', 'N/A')}")
print(f"7-day total P&L: ${summary.get('total_pnl', 0):,.2f}")
EOF
```

### Step 2: Check Thesis Signposts

```bash
PYTHONPATH=. python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)

# Check for theses due for review
due = tracker.get_theses_due_for_review()
if due:
    print("=== THESES DUE FOR REVIEW ===")
    for thesis in due:
        print(f"\n{thesis.name}")
        print(f"  Conviction: {thesis.conviction:.0f}%")
        print(f"  Positions: {', '.join(thesis.positions)}")

        # Show conviction trend
        if len(thesis.conviction_history) >= 2:
            recent = thesis.conviction_history[-2:]
            print(f"  Trend: {recent[0].old_value:.0f}% -> {recent[-1].new_value:.0f}%")

# Check all active theses for triggered signposts
print("\n=== SIGNPOST CHECK ===")
for thesis in tracker.get_active_theses():
    pending = thesis.get_pending_signposts()
    for sp in pending:
        print(f"[{thesis.name}] Pending: {sp.description}")
EOF
```

### Step 3: Extract Learnings

```bash
PYTHONPATH=. python3 << 'EOF'
from src.decision.decision_logger import DecisionLogger
from src.knowledge.learnings import LearningLog
from src.core.paths import paths
from datetime import datetime, timedelta

logger = DecisionLogger()
learning_log = LearningLog(paths.learnings)

# Find closed decisions without extracted learnings
for i in range(7):
    date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    filepath = paths.decisions / f"decisions_{date}.json"

    if filepath.exists():
        import json
        with open(filepath) as f:
            data = json.load(f)

        for d in data["decisions"]:
            if d.get("status") == "closed" and not d.get("learning_extracted"):
                print(f"\n=== Unextracted Learning: {d['symbol']} {d['action']} ===")
                print(f"  P&L: {d.get('realized_pnl_pct', 'N/A'):.1f}%")
                print(f"  Reasoning: {d['reasoning'][:100]}...")
                print("  ** NEEDS LEARNING EXTRACTION **")
EOF
```

## Review Process

### Step 1: Portfolio Performance

```python
from alpaca.trading.client import TradingClient
import yaml

with open("config/credentials.yaml") as f:
    creds = yaml.safe_load(f)

client = TradingClient(
    creds["alpaca"]["api_key"],
    creds["alpaca"]["secret_key"],
    paper=True
)

account = client.get_account()
equity = float(account.equity)
last_equity = float(account.last_equity)
day_pnl = equity - last_equity
day_pnl_pct = (day_pnl / last_equity) * 100

print(f"Today's P&L: ${day_pnl:+,.2f} ({day_pnl_pct:+.2f}%)")
```

### Step 1b: Thesis P&L Attribution

**CRITICAL: Break down today's P&L by thesis to understand WHAT drove performance.**

```bash
PYTHONPATH=. python3 << 'EOF'
import json
from pathlib import Path

state_path = Path.home() / "quant_results" / "live" / "state.json"
with open(state_path) as f:
    state = json.load(f)

thesis_perf = state.get("thesis_performance", {})
if thesis_perf:
    print("=== THESIS P&L ATTRIBUTION ===")
    print(f"{'Thesis':<35s} {'Day P&L':>10s} {'Total P&L':>10s} {'Weight':>8s} {'Pos':>4s} {'Best':>8s} {'Worst':>8s}")
    print("─" * 95)

    sorted_theses = sorted(thesis_perf.values(), key=lambda t: t.get("day_pnl", 0), reverse=True)
    total_day = 0
    total_pnl = 0

    for tp in sorted_theses:
        name = tp.get("thesis_name", "?")[:34]
        day = tp.get("day_pnl", 0)
        total = tp.get("total_pnl", 0)
        weight = tp.get("weight_in_portfolio_pct", 0)
        pos_count = tp.get("position_count", 0)
        best = tp.get("best_performer_pnl_pct", 0)
        worst = tp.get("worst_performer_pnl_pct", 0)
        total_day += day
        total_pnl += total
        print(f"  {name:<34s} ${day:>+8,.0f} ${total:>+8,.0f} {weight:>6.1f}% {pos_count:>4d} {best:>+6.1f}% {worst:>+6.1f}%")

    print("─" * 95)
    print(f"  {'TOTAL':<34s} ${total_day:>+8,.0f} ${total_pnl:>+8,.0f}")

    # Flag divergences > 15% within a thesis (equal weight violation)
    print("\n=== DIVERGENCE ALERTS ===")
    for tp in sorted_theses:
        div = tp.get("divergence_pct", 0)
        if div > 15 and tp.get("position_count", 0) >= 2:
            print(f"  WARNING: {tp['thesis_name']}: {div:.0f}% divergence between best/worst")
            print(f"    Best: {tp.get('best_performer', '?')} ({tp.get('best_performer_pnl_pct', 0):+.1f}%)")
            print(f"    Worst: {tp.get('worst_performer', '?')} ({tp.get('worst_performer_pnl_pct', 0):+.1f}%)")
else:
    print("No thesis performance data in state.json. Daemon may need to run.")

# Orphan positions (not in any thesis)
positions = state.get("positions", [])
orphans = [p for p in positions if not p.get("thesis_id")]
if orphans:
    orphan_pnl = sum(p.get("day_pnl", 0) for p in orphans)
    print(f"\n=== ORPHAN POSITIONS ({len(orphans)}) ===")
    print(f"  Day P&L from orphans: ${orphan_pnl:+,.0f}")
    for p in sorted(orphans, key=lambda x: abs(x.get("day_pnl", 0)), reverse=True)[:5]:
        print(f"  {p['symbol']:>6s} ${p.get('day_pnl', 0):>+8,.0f} ({p.get('day_pnl_pct', 0):+.1f}%)")
    print(f"  ... consider assigning these to theses")
EOF
```

Include this thesis breakdown in the EOD report JSON under `thesis_attribution`.

### Step 2: Decision Outcome Analysis

For each decision made today:
- Was the reasoning correct?
- Did key factors play out?
- What was missed?

### Step 3: Learning Extraction

**CRITICAL: Extract a learning from every closed position.**

```python
from src.knowledge.learnings import LearningLog, Learning
from src.core.paths import paths

learning_log = LearningLog(paths.learnings)

# Create learning from closed decision
learning = Learning(
    decision_id="abc12345",
    symbol="HAL",
    action="BUY",
    outcome="win",  # win, loss, scratch
    pnl_pct=4.5,
    what_happened="""
    Bought HAL at $31.97 based on insider_technical signal and
    Venezuela thesis. Stock rallied 4.5% over 3 days as thesis
    played out with Chevron license news.
    """,
    what_i_learned="""
    Insider signal + active thesis creates strong confluence.
    Pre-market strength was key confirmation signal.
    Should have sized larger given high signal agreement.
    """,
    how_this_changes_approach="""
    When insider_technical + thesis align, consider 5% position
    instead of 3%. The confluence is worth the concentration.
    """,
    pattern_name="thesis_insider_confluence",
    pattern_description="Insider buying confirms active investment thesis",
    tags=["insider", "thesis", "energy", "venezuela", "confluence"],
)

learning_log.add_learning(learning)
```

### Step 4: Thesis Conviction Update

```python
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)

# Update conviction based on today's evidence
thesis = tracker.get_thesis("venezuela123")
if thesis:
    # Signpost triggered positively
    thesis.update_conviction(
        new_value=75,
        reason="Chevron license extended 6 months - bullish signpost triggered"
    )
    thesis.trigger_signpost(0, "bullish")
    tracker._save_thesis(thesis)
```

### Step 5: Knowledge Base Update

```python
from src.knowledge.base import KnowledgeBase, CompanyBrief
from src.core.paths import paths

kb = KnowledgeBase(paths.knowledge)

# Update or create company knowledge
company = kb.get_company("HAL") or CompanyBrief(
    symbol="HAL",
    name="Halliburton",
    business_model="Oilfield services",
    moat="",
    earnings_quality="",
    key_risks=[],
    key_catalysts=[],
    best_setups="",
)

# Update based on what we learned
company.best_setups = "insider_technical + thesis alignment; pre-market strength entry"
company.key_catalysts = ["Venezuela contracts", "OPEC+ cuts", "Capex cycle upturn"]

kb.save_company(company)
```

## Learning Log Format

Learnings are stored in monthly JSON files:

```json
{
  "month": "2026-01",
  "learnings": [
    {
      "id": "learn_abc123",
      "created": "2026-01-06T16:30:00",
      "decision_id": "abc12345",
      "symbol": "HAL",
      "action": "BUY",
      "outcome": "win",
      "pnl_pct": 4.5,
      "what_happened": "...",
      "what_i_learned": "...",
      "how_this_changes_approach": "...",
      "pattern_name": "thesis_insider_confluence",
      "pattern_description": "Insider buying confirms thesis",
      "tags": ["insider", "thesis", "energy"]
    }
  ]
}
```

## EOD Report Format

Save to: `~/quant_results/eod_reviews/review_YYYYMMDD.json`

```json
{
  "date": "2026-01-06",
  "account": {
    "equity": 96500,
    "day_pnl": 612,
    "day_pnl_pct": 0.64
  },
  "decisions_made": 3,
  "decisions_executed": 1,
  "outcomes": {
    "wins": 1,
    "losses": 0,
    "pending": 0
  },
  "learnings_extracted": [
    {
      "symbol": "HAL",
      "pattern": "thesis_insider_confluence",
      "summary": "Insider + thesis alignment is high-conviction setup"
    }
  ],
  "thesis_updates": [
    {
      "thesis": "Venezuela Energy Recovery",
      "old_conviction": 65,
      "new_conviction": 75,
      "reason": "Chevron license extended - bullish signpost"
    }
  ],
  "tomorrow_focus": [
    "Monitor HAL for continuation",
    "Review Feb options expiring Friday",
    "Check Venezuela news"
  ]
}
```

## Example Session

```
User: /eod-review

Claude: Running end-of-day review for January 6, 2026.

## Portfolio Summary

| Metric | Value |
|--------|-------|
| Equity | $96,500.45 |
| Day P&L | +$611.54 (+0.64%) |

### vs Benchmarks
- SPY: +0.45% (outperformed by +0.19%)
- XLE: +1.2% (underperformed by -0.56%)

---

## Decision Analysis

### Decision 1: HAL BUY (EXECUTED)
- **Entry:** $31.97
- **Current:** $33.41
- **P&L:** +$129.96 (+4.5%)
- **Confidence was:** 65%
- **Status:** WINNING

**Analysis:**
- Reasoning was correct - HAL followed thesis
- Pre-market strength was good entry signal
- Insider_technical signal was predictive

---

## Learning Extracted

**Pattern:** thesis_insider_confluence

**What happened:**
Bought HAL based on insider_technical signal and Venezuela thesis.
Stock rallied 4.5% as Chevron license news confirmed thesis.

**What I learned:**
Insider signal + active thesis creates strong confluence.
Pre-market strength was key confirmation.

**How this changes approach:**
When insider_technical + thesis align, size 5% instead of 3%.

**Tags:** insider, thesis, energy, confluence

---

## Thesis Updates

### Venezuela Energy Recovery
- **Previous conviction:** 65%
- **New conviction:** 75%
- **Reason:** Chevron license extended 6 months - bullish signpost triggered

**Signpost triggered:**
[+] Chevron license extended beyond 6 months - BULLISH

---

## Knowledge Base Updates

- Updated HAL company brief with best_setups
- Logged insider_technical signal performance

---

## Tomorrow's Focus

1. **Monitor:** HAL position for continuation or profit-taking
2. **Review:** Feb options (VLO, GLD) for potential exit
3. **Watch:** Energy sector breadth
4. **Research:** Any further Venezuela/Cuba news
5. **Thesis:** SLB signpost pending - contract announcements

---

Review saved to: ~/quant_results/eod_reviews/review_20260106.json
Learning saved to: ~/quant_results/learnings/2026-01.json
```

## Step 5b: Propagate Learnings to Strategic Context & Situation Board

**CRITICAL: Push today's learnings to shared memory so downstream sessions benefit.**

After extracting learnings in Steps 3-5, propagate key findings:

```bash
PYTHONPATH=. python3 << 'EOF'
from src.swarm.strategic_context import StrategicContext
from src.swarm.situation_board import SituationBoard

ctx = StrategicContext.load()
board = SituationBoard.load_or_create()

# 1. Push significant learnings as developing patterns
# (Fill these in from learnings extracted in Step 3)
# For each learning with a pattern_name, add to strategic context:
#
# ctx.add_developing_pattern(
#     name="<pattern_name from learning>",
#     evidence="<what_happened summary>",
#     interpretation="<how_this_changes_approach>",
#     affected_theses=["<thesis names>"],
# )

# 2. Push today's P&L and key observations to situation board
# board.add_observation(
#     source="eod-review",
#     obs_type="daily_summary",
#     text=f"Day P&L: ${day_pnl:+,.0f} ({day_pnl_pct:+.2f}%). <key insight>",
#     symbols=["<symbols discussed>"],
# )

# 3. Push thesis conviction changes to strategic context momentum
# (These were already tracked in Step 4 via ThesisTracker, but
#  also update strategic context for cross-session awareness)
# ctx.update_thesis_momentum("<thesis_name>", <new_conviction>)

# 4. Push tomorrow's focus items as upcoming catalysts
# for item in tomorrow_focus:
#     if it references a specific date/event:
#         ctx.add_catalyst(
#             date="<date>",
#             event=item,
#             affected=["<symbols>"],
#         )

ctx.save()
board.save()
print("Learnings propagated to strategic context and situation board")
EOF
```

**What this enables:**
- Morning briefing reads yesterday's learnings from strategic context (not just learning log files)
- Trade decisions see developing patterns from accumulated EOD insights
- Internal reviews track pattern evolution over multiple days
- Theorist sees real performance outcomes, not just predictions

## Step 6: Score Predictions & Run Belief Update (Intelligence Loop)

**CRITICAL: This closes the feedback loop.** Score today's predictions and update beliefs.

```bash
# Score any predictions that have reached their resolve_by date
PYTHONPATH=. python3 scripts/cron_prediction_scorer.py
```

```bash
# Run belief update — updates signal weights, suggests thesis conviction changes
PYTHONPATH=. python3 scripts/cron_belief_update.py
```

```bash
# Review the belief update report
PYTHONPATH=. python3 << 'EOF'
import json
from pathlib import Path
from datetime import datetime

# Read today's belief update
date_str = datetime.now().strftime("%Y%m%d")
report_path = Path.home() / "quant_results" / "intelligence" / f"daily_update_{date_str}.json"

if report_path.exists():
    report = json.loads(report_path.read_text())
    print(report.get("learning_summary", "No update available"))

    # Show any thesis conviction suggestions
    for s in report.get("thesis_suggestions", []):
        print(f"\n  SUGGESTION: {s['thesis_name']}")
        print(f"    Current: {s['current_conviction']}%, Change: {s['suggested_change']:+}%")
        print(f"    Reason: {s['reason']}")
else:
    print("No belief update for today. Run the scorer and updater first.")
EOF
```

Review the suggestions. Apply thesis conviction changes if they make sense:

```python
from src.db.write_api import athena_db

# If belief update suggests increasing conviction:
athena_db.update_conviction(
    thesis_id="...",
    value=80.0,
    reason="Belief update: 78% prediction accuracy over 12 predictions"
)
```

## Learning Loop Integration

The EOD review feeds back into tomorrow's decisions:

```
/morning-briefing → reads yesterday's EOD review + recent learnings
/trade-decision → applies learned patterns + thesis context
/execute-trades → validates against risk rules
/eod-review → generates new learnings → cycle continues
```

## Retrieving Past Learnings

```bash
PYTHONPATH=. python3 << 'EOF'
from src.knowledge.learnings import LearningLog
from src.core.paths import paths

log = LearningLog(paths.learnings)

# Get recent learnings
recent = log.get_recent(days=30)
print(f"Last 30 days: {len(recent)} learnings\n")

# Get learnings by pattern
confluence = log.get_by_tag("confluence")
print(f"Confluence patterns: {len(confluence)}")

# Get learnings for a symbol
hal_learnings = log.get_by_symbol("HAL")
for l in hal_learnings:
    print(f"  {l.created.strftime('%Y-%m-%d')}: {l.outcome} ({l.pnl_pct:+.1f}%)")
    print(f"    Pattern: {l.pattern_name}")
EOF
```

## Signal Quality Tracking

**IMPORTANT:** Log which signals influenced each decision for quality tracking.

### Log Signal Outcomes

```python
from src.monitoring.signal_quality_tracker import log_signal_outcome

# Log each signal that influenced a decision
# When the decision closes, this lets us track signal quality

# Example: Insider signal led to a winning trade
log_signal_outcome(
    signal_type="insider",
    symbol="HAL",
    direction="bullish",
    signal_strength=0.75,
    acted_on=True,
    pnl=129.96,
    pnl_pct=4.5,
    hold_days=3,
)

# Example: Technical signal we didn't act on
log_signal_outcome(
    signal_type="technical",
    symbol="AAPL",
    direction="bullish",
    signal_strength=0.5,
    acted_on=False,  # Signal generated but not traded
)
```

### Review Signal Quality

```bash
PYTHONPATH=. python3 << 'EOF'
from src.monitoring.signal_quality_tracker import get_signal_quality_tracker

tracker = get_signal_quality_tracker()
summary = tracker.get_summary()

print("=== SIGNAL QUALITY SUMMARY ===")
print(f"Signal types tracked: {summary['total_types']}")
print(f"Average hit rate: {summary['avg_hit_rate']:.0%}")

if summary.get('best_signal'):
    print(f"Best: {summary['best_signal']} ({summary['best_hit_rate']:.0%})")
if summary.get('worst_signal'):
    print(f"Worst: {summary['worst_signal']} ({summary['worst_hit_rate']:.0%})")

if summary.get('degrading'):
    print(f"DEGRADING: {', '.join(summary['degrading'])}")
if summary.get('improving'):
    print(f"Improving: {', '.join(summary['improving'])}")
EOF
```

### Generate Improvement Suggestions

```bash
PYTHONPATH=. python3 << 'EOF'
from src.monitoring.improvement_tracker import get_improvement_tracker

tracker = get_improvement_tracker()

# Get pending improvements
pending = tracker.get_pending()
if pending:
    print("=== PENDING IMPROVEMENTS ===")
    for imp in pending[:5]:
        print(f"[{imp.priority.upper()}] {imp.title}")
        print(f"  Action: {imp.suggested_action}")
        print()

# Get summary
summary = tracker.get_summary()
print(f"Total suggestions: {summary['total_suggestions']}")
print(f"High priority pending: {summary['pending_high_priority']}")
EOF
```

## Register Output as Document

After saving the EOD review, index it in the documents table:

```python
from src.db.write_api import athena_db

athena_db.save_document(
    doc_type="eod_review",
    title=f"EOD Review — {date}",
    file_path=str(filepath),
    source="skill:eod-review",
    symbols=symbols_discussed,
    tags=["eod_review", "daily"],
)
```

## Query Historical Context

Before running the review, check previous reviews and learnings:

```python
from src.db.write_api import athena_db

# Recent EOD reviews for comparison
reviews = athena_db.get_recent_documents(limit=5)
eod_reviews = [d for d in reviews if d.doc_type == "eod_review"]

# Search insights related to today's positions
insights = athena_db.search_insights("momentum")

# Get documents for a specific symbol being reviewed
docs = athena_db.get_documents_for_symbol("HAL", limit=10)
```

Or use the convenience script:
```bash
PYTHONPATH=. python3 scripts/context_for_symbol.py HAL
```

## Key Files

| File | Purpose |
|------|---------|
| `~/quant_results/decisions/` | Today's decisions |
| `~/quant_results/learnings/` | Learning log (monthly files) |
| `~/quant_results/theses/` | Investment theses |
| `~/quant_results/knowledge/` | Company/sector knowledge |
| `~/quant_results/eod_reviews/` | EOD review outputs |
| `~/quant_results/signal_quality/` | Signal quality tracking |
| `~/quant_results/improvements/` | Improvement suggestions |
| `src/knowledge/learnings.py` | LearningLog class |
| `src/knowledge/thesis.py` | ThesisTracker class |
| `src/monitoring/signal_quality_tracker.py` | Signal quality tracking |
| `src/monitoring/improvement_tracker.py` | Improvement tracking |
