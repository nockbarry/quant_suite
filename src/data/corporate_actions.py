"""Corporate-action (split) awareness.

The CRWD 4:1 split on 2026-07-02 corrupted day-P&L (reported -4.67% vs real
~-0.7%), fired 8 false stop-loss/drawdown triggers, and drove a bug-driven
rebalance on the beta instance — because nothing in the system knew splits
exist. This module provides:

- fetch_recent_splits(): query Alpaca's corporate-actions API for forward/
  reverse splits around today (cron_corporate_actions.py caches this at
  5:45 AM into ~/quant_results/live/corporate_actions.json)
- todays_splits(): read the cache; symbols with an ex-date of today
- detect_share_discontinuity(): defense-in-depth — a qty ratio jump between
  consecutive position snapshots that looks like a simple split ratio, in
  case the API misses one

Consumers: synthesis daemon (sanitize intraday P&L at source), adaptive
triggers (suppress drawdown stops on split days), reconciler (freeze
splitting symbols for the day). All gated by ATHENA_CA_GUARD (default on).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_FILE = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))) / "live" / "corporate_actions.json"

# Ratios we treat as "looks like a split" in discontinuity detection
_SPLIT_LIKE_RATIOS = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 20.0,
                      1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 20)
_RATIO_TOLERANCE = 0.02


def guard_enabled() -> bool:
    return os.environ.get("ATHENA_CA_GUARD", "1") != "0"


@dataclass
class SplitEvent:
    symbol: str
    ratio: float          # new_rate / old_rate (4.0 for a 4:1 forward split)
    ex_date: str          # ISO date
    action_type: str      # forward_split / reverse_split / detected_discontinuity

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_recent_splits(symbols: list[str], lookback_days: int = 3,
                        lookahead_days: int = 3) -> list[SplitEvent]:
    """Query Alpaca corporate-actions API for splits with ex-dates near today."""
    if not symbols:
        return []
    import yaml
    from alpaca.data.enums import CorporateActionsType
    from alpaca.data.historical.corporate_actions import CorporateActionsClient
    from alpaca.data.requests import CorporateActionsRequest

    creds_path = Path(__file__).resolve().parents[2] / "config" / "credentials.yaml"
    creds = yaml.safe_load(creds_path.read_text())["alpaca"]
    client = CorporateActionsClient(creds["api_key"], creds["secret_key"])

    today = date.today()
    req = CorporateActionsRequest(
        symbols=sorted(set(symbols)),
        types=[CorporateActionsType.FORWARD_SPLIT, CorporateActionsType.REVERSE_SPLIT],
        start=today - timedelta(days=lookback_days),
        end=today + timedelta(days=lookahead_days),
    )
    result = client.get_corporate_actions(req)
    data = result.data if hasattr(result, "data") else result

    events: list[SplitEvent] = []
    for key in ("forward_splits", "reverse_splits"):
        for item in (data.get(key) or []):
            get = item.get if isinstance(item, dict) else lambda k, _i=item: getattr(_i, k, None)
            old_rate = float(get("old_rate") or 1.0) or 1.0
            new_rate = float(get("new_rate") or 1.0)
            ex = get("ex_date")
            events.append(SplitEvent(
                symbol=str(get("symbol")),
                ratio=new_rate / old_rate,
                ex_date=ex.isoformat() if hasattr(ex, "isoformat") else str(ex),
                action_type=key.rstrip("s"),
            ))
    return events


def write_cache(events: list[SplitEvent]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "fetched_at": datetime.now().isoformat(),
        "events": [e.to_dict() for e in events],
    }, indent=2))


def _load_cache() -> list[SplitEvent]:
    if not CACHE_FILE.exists():
        return []
    try:
        raw = json.loads(CACHE_FILE.read_text())
        return [SplitEvent(**e) for e in raw.get("events", [])]
    except Exception as e:
        logger.warning(f"corporate_actions cache unreadable: {e}")
        return []


def todays_splits() -> dict[str, SplitEvent]:
    """Symbols with a split ex-date of today, from the daily cache.

    Missing/stale cache degrades to {} — current (pre-guard) behavior.
    """
    if not guard_enabled():
        return {}
    today = date.today().isoformat()
    return {e.symbol: e for e in _load_cache() if e.ex_date == today}


def detect_share_discontinuity(prev_qty: dict[str, float],
                               curr_qty: dict[str, float]) -> dict[str, float]:
    """Detect split-like quantity jumps between consecutive position snapshots.

    Returns {symbol: ratio} for symbols whose share count changed by a clean
    split-like multiple. Catches splits the API missed (the CRWD failure
    mode: qty 7 -> 28 overnight with no order).
    """
    hits: dict[str, float] = {}
    for sym, prev in prev_qty.items():
        curr = curr_qty.get(sym)
        if not prev or not curr or prev <= 0 or curr <= 0:
            continue
        ratio = curr / prev
        for candidate in _SPLIT_LIKE_RATIOS:
            if abs(ratio - candidate) / candidate <= _RATIO_TOLERANCE:
                hits[sym] = candidate
                break
    return hits
