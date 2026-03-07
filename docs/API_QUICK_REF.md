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

# Price targets (bull/base/bear per vehicle)
thesis.price_targets    # dict[str, PriceTarget]
pt = thesis.get_price_target("SLB")  # Optional[PriceTarget]
pt.bull_target          # float
pt.base_target          # float
pt.bear_target          # float
pt.entry_price          # float
pt.progress_pct(50.0)   # float (0-100+)

# Set price targets (auto-creates predictions)
tracker.set_price_targets(thesis.id, {
    "SLB": {
        "bull_target": 62.0, "base_target": 55.0, "bear_target": 42.0,
        "entry_price": 47.5, "timeframe_days": 90,
        "notes": "Venezuela contracts + oil recovery",
    },
})
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

## AthenaWriteAPI — Document Index (src/db/write_api.py)

```python
from src.db.write_api import athena_db

# Save/index a document
athena_db.save_document(
    doc_type="research_result",      # briefing, eod_review, decision, critic_report, etc.
    title="Bollinger Reversal: Semiconductors",
    file_path="/home/nock/quant_results/research_results/research_123.json",  # optional
    content_inline="...",            # optional, for small content (<10KB)
    source="skill:research",         # who created it
    agent_run_id="abc123",           # optional FK
    thesis_id="thesis_456",          # optional FK
    decision_id="dec_789",           # optional FK
    symbols=["NVDA", "AMD"],         # optional list
    tags=["research", "bollinger"],   # optional list
)

# Get recent documents
docs = athena_db.get_recent_documents(limit=10)
# Returns: list of Document objects
# Attributes: .id, .doc_type, .title, .summary, .file_path, .source, .symbols, .tags, .created

# Get documents for a symbol
docs = athena_db.get_documents_for_symbol("NVDA", limit=15)

# Search documents by text
docs = athena_db.search_documents(query="bollinger semiconductor", doc_type="research_result", limit=20)

# Search research insights
insights = athena_db.search_insights("momentum reversal")
# Returns: list of Insight objects
# Attributes: .id, .title, .description, .category, .confidence, .validated, .tags
```

### Symbol Context Script

```bash
# Full context for a symbol: documents, insights, theses, decisions
PYTHONPATH=. python3 scripts/context_for_symbol.py NVDA
PYTHONPATH=. python3 scripts/context_for_symbol.py NVDA AMD --json
```

---

## Market Mover Scanner (src/intelligence/market_movers.py)

```python
from src.intelligence.market_movers import MarketMoverScanner

scanner = MarketMoverScanner()

# Full scan: build universe → fetch prices → identify movers → enrich → rank
scan = scanner.scan()  # Returns MarketMoverScan dataclass

# MarketMoverScan attributes
scan.timestamp          # datetime
scan.universe_size      # int (~231 symbols)
scan.movers_found       # int
scan.gainers            # list[dict] sorted by change_1d_pct desc
scan.losers             # list[dict] sorted by change_1d_pct asc
scan.volume_spikes      # list[dict] sorted by volume_ratio desc
scan.top_context        # list[dict] sorted by context_score desc

# Each mover dict contains:
# symbol, name, sector, price, change_1d_pct, change_5d_pct, change_1m_pct,
# volume, avg_volume, volume_ratio, trigger, move_magnitude,
# news_matches, finviz_screens, wsb_status, thesis_alignment,
# context_score, rank, timestamp

# Intraday scan (tighter thresholds: 2% day, 8% week)
scan = scanner.scan(intraday=True)

# Cron script (writes JSON + indexes documents + creates provenance)
# PYTHONPATH=. python3 scripts/cron_market_movers.py
# PYTHONPATH=. python3 scripts/cron_market_movers.py --intraday

# Web service (reads latest JSON)
from src.web.services.mover_service import get_latest_scan, get_mover_detail
scan = get_latest_scan()     # dict with _fresh, _age_display computed fields
mover = get_mover_detail("MRVL")  # dict or None
```

---

## Signal Provenance (src/knowledge/signal_provenance.py)

```python
from src.knowledge.signal_provenance import get_provenance_tracker, SignalSource

tracker = get_provenance_tracker()

# Create a signal
tracker.create_signal(
    source=SignalSource.STATISTICAL,  # WSB, NEWS, INSIDER, CONGRESSIONAL, OPTIONS, etc.
    symbol="MRVL",
    detection_method="market_mover_scan",
    initial_confidence=0.75,
    initial_direction="bullish",
    initial_description="MRVL +18.4% with 5.1x volume ratio",
    metadata={"context_score": 0.36, "trigger": "day_move"},
)

# Get all signals (loaded from ~/quant_results/signal_provenance/*.json)
signals = list(tracker._cache.values())  # list[SignalProvenance]
```

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
