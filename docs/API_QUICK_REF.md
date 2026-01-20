# API Quick Reference

Read this BEFORE writing any Python code to avoid API errors.

---

## UnifiedState (src/synthesis/state.py)

```python
from src.synthesis.state import UnifiedState
from src.core.paths import paths

# Load state
state = UnifiedState.load(paths.live_state)  # Returns Optional[UnifiedState]

# Get summary (THE method to use)
print(state.get_summary())  # Returns formatted string

# Key attributes (dataclass fields, NOT methods)
state.timestamp          # datetime
state.market_open        # bool
state.market             # MarketSnapshot
state.sentiment          # SentimentSnapshot
state.portfolio          # PortfolioSnapshot
state.positions          # list[PositionSnapshot]
state.theses             # list[ThesisSummary]
state.alerts             # list[AlertSnapshot]
state.upcoming_events    # list[CalendarEvent]

# Check freshness (NO is_fresh method - calculate manually)
from datetime import datetime, timedelta
age = datetime.now() - state.timestamp
is_fresh = age < timedelta(minutes=30)
```

---

## LiveDaemon (src/synthesis/daemon.py)

```python
from src.synthesis.daemon import LiveDaemon

daemon = LiveDaemon()

# Update state NOW (async)
state = await daemon.update_now()  # Returns UnifiedState
```

---

## MarketCalendar (src/knowledge/market_calendar.py)

```python
from src.knowledge.market_calendar import MarketCalendar
from datetime import date, timedelta

calendar = MarketCalendar()

# Get events in date range
events = calendar.get_events_in_range(start_date, end_date)  # list[CalendarEvent]

# Get upcoming events
events = calendar.get_upcoming_events(days=7)  # list[CalendarEvent]

# Get predictions due for review
predictions = calendar.get_predictions_due_for_review()  # list[Prediction]

# CalendarEvent attributes
event.id                # str
event.date              # date
event.title             # str
event.description       # str
event.impact            # EventImpact enum (critical, high, medium, low)
event.symbols_affected  # list[str]

# Access impact value
impact_str = event.impact.value  # "critical", "high", "medium", "low"
```

---

## ThesisTracker (src/knowledge/thesis.py)

```python
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)

# Get active theses
theses = tracker.get_active_theses()  # list[Thesis]

# Get theses for symbol
theses = tracker.get_theses_for_symbol("SLB")  # list[Thesis]

# Thesis attributes
thesis.id               # str
thesis.name             # str
thesis.conviction       # float (0-100)
thesis.positions        # list[str]
thesis.signposts        # list[Signpost] - NOT dicts!

# Thesis methods
pending = thesis.get_pending_signposts()  # list[Signpost]
due = thesis.check_review_due()           # bool

# Signpost attributes (dataclass, NOT dict)
signpost.description    # str
signpost.status         # str ("pending", "triggered", "invalidated")
signpost.trigger_date   # Optional[datetime]
```

---

## Paths (src/core/paths.py)

```python
from src.core.paths import paths

paths.live_state    # Path to state.json
paths.theses        # Path to theses directory
paths.knowledge     # Path to knowledge directory
paths.live          # Path to live directory

# NO paths.results - use Path.home() / "quant_results" instead
results_dir = Path.home() / "quant_results"
```

---

## Quick Trade CLI (scripts/quick_trade.py)

```bash
# Use CLI instead of writing broker code
PYTHONPATH=. python scripts/quick_trade.py buy MU 10
PYTHONPATH=. python scripts/quick_trade.py sell SLB 50
PYTHONPATH=. python scripts/quick_trade.py positions
PYTHONPATH=. python scripts/quick_trade.py quote AAPL MSFT
```

---

## Common Mistakes to Avoid

| Wrong | Right |
|-------|-------|
| `state.is_fresh()` | `(datetime.now() - state.timestamp) < timedelta(minutes=30)` |
| `calendar.get_events_by_date_range()` | `calendar.get_events_in_range()` |
| `signpost.get('description')` | `signpost.description` |
| `paths.results` | `Path.home() / "quant_results"` |
| `event.impact` (raw) | `event.impact.value` (string) |

---

## Scripts to Use Instead of Writing Code

```bash
# Morning setup
./scripts/morning_preflight.sh

# Full context dump
PYTHONPATH=. python scripts/context_dump.py

# Quick API reference
PYTHONPATH=. python scripts/context_dump.py --api

# Update state only
PYTHONPATH=. python -c "
import asyncio
from src.synthesis.daemon import LiveDaemon
asyncio.run(LiveDaemon().update_now())
"
```
