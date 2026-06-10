"""Event-driven cash reserves (Fix #4, 2026-06-09 eval).

The A/B test showed the operator's regime-aware de-risking is real alpha
(main beat fully-deployed beta by ~3.8pp in the FOMC-scare week). This makes
that judgment declarative: hold a cash reserve into known binary macro events,
auto-deploy the day after. The reconciler honors it mechanically.

Config: <results>/live/event_reserves.json — maintained by LLM sessions
(evening-research / theorist add CPI dates, adjust percentages). Seeded with
the published 2026 FOMC schedule. Manual reserves (scripts/reserve.py) always
take precedence on name collision.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from src.portfolio.target import CashPolicy, Reserve

logger = logging.getLogger(__name__)

# Published FOMC decision days (second meeting day), 2026.
SEED_EVENTS = [
    {"name": "FOMC-Jun", "date": "2026-06-17", "reserve_pct": 0.20, "days_before": 5},
    {"name": "FOMC-Jul", "date": "2026-07-29", "reserve_pct": 0.20, "days_before": 5},
    {"name": "FOMC-Sep", "date": "2026-09-16", "reserve_pct": 0.20, "days_before": 5},
    {"name": "FOMC-Oct", "date": "2026-10-28", "reserve_pct": 0.20, "days_before": 5},
    {"name": "FOMC-Dec", "date": "2026-12-09", "reserve_pct": 0.20, "days_before": 5},
]


def _config_path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "live" / "event_reserves.json"


def load_events() -> list[dict]:
    """Load the event config, seeding it on first use."""
    p = _config_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "note": "Binary macro events that hold back cash. Maintained by LLM "
                    "sessions (add CPI/earnings clusters, tune pcts). Reserve is "
                    "active from (date - days_before) through date; deploys after.",
            "events": SEED_EVENTS,
        }, indent=2))
        logger.info(f"Seeded event reserves config with {len(SEED_EVENTS)} FOMC dates")
    try:
        return json.loads(p.read_text()).get("events", [])
    except Exception as e:
        logger.warning(f"event_reserves.json unreadable ({e}); no event reserves")
        return []


def compute_event_reserves(today: Optional[date] = None) -> list[Reserve]:
    """Reserves for events whose pre-event window contains `today`."""
    today = today or date.today()
    out = []
    for ev in load_events():
        try:
            ev_date = date.fromisoformat(ev["date"])
            window_start = ev_date - timedelta(days=int(ev.get("days_before", 5)))
            if window_start <= today <= ev_date:
                out.append(Reserve(
                    name=f"event:{ev['name']}",
                    target_pct=float(ev.get("reserve_pct", 0.20)),
                    catalyst=f"binary event {ev['name']} on {ev['date']}",
                    expiry=ev_date,  # active through decision day, deploys next
                ))
        except (KeyError, ValueError) as e:
            logger.warning(f"bad event entry {ev}: {e}")
    return out


def merge_event_reserves(cash_policy: CashPolicy, today: Optional[date] = None) -> CashPolicy:
    """Add active event reserves to a CashPolicy in place (manual names win)."""
    existing = {r.name for r in cash_policy.reserves}
    added = []
    for r in compute_event_reserves(today):
        if r.name not in existing:
            cash_policy.reserves.append(r)
            added.append(f"{r.name}({r.target_pct:.0%} thru {r.expiry})")
    if added:
        logger.info(f"Event reserves active: {added}")
    return cash_policy
