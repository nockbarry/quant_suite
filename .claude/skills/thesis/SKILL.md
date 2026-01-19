---
name: thesis
description: Manage investment theses with signposts, conviction tracking, and review schedules. Use to create new theses, review active ones, update conviction, or check signpost triggers.
allowed-tools: Read, Write, Bash(PYTHONPATH=*), Glob, Grep
---

# Thesis Management Skill

Track and manage investment theses with structured signposts, conviction history, and review schedules.

## Purpose

Investment theses provide the "why" behind trades:
- **What do I believe** that the market doesn't?
- **What signposts** will validate or invalidate this belief?
- **What positions** are linked to this thesis?

## Quick Commands

### List Active Theses

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
for thesis in tracker.get_active_theses():
    print(f"\n=== {thesis.name} ===")
    print(f"ID: {thesis.id}")
    print(f"Status: {thesis.status}")
    print(f"Conviction: {thesis.conviction:.0f}%")
    print(f"Positions: {', '.join(thesis.positions) or 'None'}")
    pending = thesis.get_pending_signposts()
    if pending:
        print(f"Next Signpost: {pending[0].description}")
    print(f"Review Due: {'YES' if thesis.check_review_due() else 'No'}")
EOF
```

### Create New Thesis

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker, Signpost
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)

thesis = tracker.create_thesis(
    name="Venezuela Energy Recovery",
    summary="Sanctions relief drives oilfield services rally as majors resume operations",
    bull_case="Chevron license extension + potential broader relief → SLB/HAL contracts",
    bear_case="Political reversal, oil price collapse, execution delays",
    conviction=65,
    signposts=[
        {
            "description": "Chevron license extended beyond 6 months",
            "bullish_if": "Full license renewal with expanded scope",
            "bearish_if": "Only cosmetic extension or further restrictions",
        },
        {
            "description": "Major oilfield services contract announced",
            "bullish_if": "SLB or HAL wins material contract",
            "bearish_if": "Contracts go to non-US players",
        },
    ],
    invalidation_triggers=[
        "Maduro regime action forces Biden to reverse",
        "Oil below $60 makes Venezuela uneconomic",
        "Gap fade >70% on announcement day",
    ],
    positions=["SLB", "HAL"],
    review_interval_days=7,
)

print(f"Created thesis: {thesis.name} (ID: {thesis.id})")
print(f"Saved to: {paths.theses / f'{thesis.id}.yaml'}")
EOF
```

### Update Conviction

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

THESIS_ID = "abc12345"  # Replace with actual ID
NEW_CONVICTION = 55
REASON = "Gap faded 70% on announcement - market skeptical"

tracker = ThesisTracker(paths.theses)
thesis = tracker.get_thesis(THESIS_ID)

if thesis:
    thesis.update_conviction(NEW_CONVICTION, REASON)
    tracker._save_thesis(thesis)
    print(f"Updated {thesis.name} conviction: {NEW_CONVICTION}%")
    print(f"Reason: {REASON}")
else:
    print(f"Thesis {THESIS_ID} not found")
EOF
```

### Trigger Signpost

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

THESIS_ID = "abc12345"  # Replace with actual ID
SIGNPOST_INDEX = 0  # First signpost
OUTCOME = "bullish"  # bullish, bearish, or neutral

tracker = ThesisTracker(paths.theses)
thesis = tracker.get_thesis(THESIS_ID)

if thesis:
    thesis.trigger_signpost(SIGNPOST_INDEX, OUTCOME)
    tracker._save_thesis(thesis)
    signpost = thesis.signposts[SIGNPOST_INDEX]
    print(f"Triggered: {signpost.description}")
    print(f"Outcome: {OUTCOME}")
else:
    print(f"Thesis {THESIS_ID} not found")
EOF
```

### Add Position to Thesis

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

THESIS_ID = "abc12345"  # Replace with actual ID
SYMBOL = "OXY"

tracker = ThesisTracker(paths.theses)
if tracker.add_position(THESIS_ID, SYMBOL):
    print(f"Added {SYMBOL} to thesis {THESIS_ID}")
else:
    print(f"Failed to add position")
EOF
```

### Review Theses Due

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
due = tracker.get_theses_due_for_review()

if not due:
    print("No theses due for review")
else:
    for thesis in due:
        print(f"\n=== REVIEW DUE: {thesis.name} ===")
        print(f"Conviction: {thesis.conviction:.0f}%")
        print(f"Days active: {(datetime.now() - thesis.created).days}")
        print(f"Positions: {', '.join(thesis.positions)}")
        print("\nSignposts:")
        for i, s in enumerate(thesis.signposts):
            status_icon = "+" if s.status == "triggered" else "?" if s.status == "pending" else "x"
            print(f"  [{status_icon}] {s.description}")
        print("\nConviction History:")
        for h in thesis.conviction_history[-3:]:
            print(f"  {h.timestamp.strftime('%Y-%m-%d')}: {h.old_value:.0f}% -> {h.new_value:.0f}% ({h.reason})")
EOF
```

### Invalidate Thesis

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

THESIS_ID = "abc12345"  # Replace with actual ID
REASON = "Oil price collapse below $55 makes Venezuela uneconomic"

tracker = ThesisTracker(paths.theses)
if tracker.invalidate_thesis(THESIS_ID, REASON):
    print(f"Thesis {THESIS_ID} invalidated")
    print(f"Reason: {REASON}")
else:
    print(f"Failed to invalidate thesis")
EOF
```

## CRITICAL: Load Trading Patterns First

Before creating or reviewing any thesis, read the accumulated trading wisdom:

```bash
cat /home/nock/projects/quant_suite/docs/TRADING_PATTERNS.md
```

Key patterns to apply:
- **Pattern 1**: Vehicle Enumeration - enumerate ALL beneficiaries
- **Pattern 2**: Converging Signals - need 3+ signals aligned
- **Pattern 3**: Data Source Check - what alt-data supports this?
- **Pattern 8**: Derivative Plays - are there better vehicles?

## Workflow

### Creating a New Thesis

1. **Identify the belief**: What do you believe that consensus doesn't?
2. **Define signposts**: What events will prove/disprove the thesis?
3. **Set invalidation triggers**: What would force you to abandon it?
4. **ENUMERATE ALL VEHICLES** (Pattern 1 - CRITICAL):
   - Direct beneficiaries
   - Suppliers
   - Customers
   - ETFs
   - Adjacent sectors
   - Options plays
   - International exposure
   - Short candidates (losers)
5. **Check for signal convergence** (Pattern 2)
6. **Set conviction**: How confident are you? (0-100%)

### Reviewing a Thesis

1. Check if any signposts have been triggered
2. Review conviction history - has it been declining?
3. Check if invalidation triggers have occurred
4. Update conviction based on new information
5. Schedule next review

### Integration with Trading

When making a trade decision:
1. Check if symbol is linked to an active thesis
2. Ensure thesis conviction supports the trade
3. Record thesis_id in the TradingDecision
4. After trade closes, update thesis if outcome is informative

## File Location

Theses are stored as YAML files in:
```
~/quant_results/theses/{thesis_id}.yaml
```

## Thesis Structure

```yaml
id: abc12345
name: Venezuela Energy Recovery
created: 2026-01-06T08:00:00
status: active  # active, validated, invalidated, expired

summary: Sanctions relief drives oilfield services rally
bull_case: Chevron license + broader relief → contracts
bear_case: Political reversal, oil collapse, delays

conviction: 65

signposts:
  - description: Chevron license extended
    status: pending
    bullish_if: Full renewal
    bearish_if: Only cosmetic

invalidation_triggers:
  - Maduro action forces reversal
  - Oil below $60

positions:
  - SLB
  - HAL

last_review: 2026-01-06T08:00:00
next_review: 2026-01-13T08:00:00
review_interval_days: 7

conviction_history:
  - timestamp: 2026-01-06T08:00:00
    old_value: 50
    new_value: 65
    reason: Initial thesis creation

notes:
  - "[2026-01-06 08:00] Created thesis based on Venezuela sanctions news"
```
