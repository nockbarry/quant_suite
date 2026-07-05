"""Benchmark comparison: account vs SPY, QQQ, and a frozen thesis basket.

Fix #2 from the 2026-06-09 fresh evaluation. The frozen basket is the
kill-shot metric: an equal-weight buy-and-hold of the system's OWN thesis
vehicles, frozen at first run. If the account doesn't beat its own frozen
basket, the daily activity machinery is subtracting value (the realized-P&L
data already suggests this: short-hold trades were net negative).

Two basket measurements:
  * frozen_forward  — clean: frozen at first run, tracked forward only.
  * retrospective   — equal-weight of CURRENT vehicles from a past anchor
                      date. Survivorship-biased (it holds today's winners),
                      flagged as such; useful context, not proof.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RETRO_ANCHOR = "2026-01-05"   # account's first trade date


def _bench_dir() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    p = base / "benchmarks"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _closes(symbols: list[str], period: str = "7mo"):
    """Daily close series per symbol via yfinance. Returns {sym: pandas.Series}."""
    import yfinance as yf

    out = {}
    for s in symbols:
        try:
            h = yf.Ticker(s).history(period=period)["Close"].dropna()
            if len(h) > 0:
                h.index = h.index.tz_localize(None)
                out[s] = h
        except Exception as e:
            logger.warning(f"price history failed for {s}: {e}")
    return out


def ensure_frozen_basket(symbols: list[str]) -> dict:
    """Freeze an equal-weight basket of `symbols` at today's prices (first run only)."""
    path = _bench_dir() / "frozen_basket.json"
    if path.exists():
        return json.loads(path.read_text())
    closes = _closes(sorted(set(symbols)), period="5d")
    # Guard against NaN closes — a NaN start_price silently kills the frozen basket
    # benchmark forever (p0 > 0 is False for NaN), so only freeze valid prices.
    valid = {s: float(c.dropna().iloc[-1]) for s, c in closes.items()
             if len(c.dropna()) > 0 and float(c.dropna().iloc[-1]) > 0}
    basket = {
        "frozen_at": datetime.now().strftime("%Y-%m-%d"),
        "symbols": sorted(valid.keys()),
        "start_prices": {s: round(p, 4) for s, p in valid.items()},
        "note": "Equal-weight buy-and-hold of own thesis vehicles at freeze date. "
                "The does-activity-add-value benchmark — do not edit.",
    }
    path.write_text(json.dumps(basket, indent=2))
    logger.info(f"Frozen basket created: {len(basket['symbols'])} symbols @ {basket['frozen_at']}")
    return basket


def _basket_return(symbols: list[str], closes: dict, start: datetime,
                   start_prices: Optional[dict] = None) -> Optional[float]:
    """Equal-weight buy-and-hold return from `start` (or explicit start prices)."""
    rets = []
    for s in symbols:
        c = closes.get(s)
        if c is None or len(c) == 0:
            continue
        if start_prices and s in start_prices:
            p0 = start_prices[s]
        else:
            window = c[c.index >= start]
            if len(window) == 0:
                continue
            p0 = float(window.iloc[0])
        if p0 > 0:
            rets.append(float(c.iloc[-1]) / p0 - 1.0)
    return sum(rets) / len(rets) if rets else None


def compute_report(thesis_symbols: list[str],
                   account_equity: dict[str, float],
                   account_label: str = "main") -> dict:
    """Build the benchmark report.

    Args:
        thesis_symbols: current active thesis vehicles.
        account_equity: {YYYY-MM-DD: equity} daily history (from Alpaca).
    """
    basket = ensure_frozen_basket(thesis_symbols)
    frozen_start = datetime.strptime(basket["frozen_at"], "%Y-%m-%d")
    retro_start = datetime.strptime(RETRO_ANCHOR, "%Y-%m-%d")
    now = datetime.now()

    universe = sorted(set(basket["symbols"]) | set(thesis_symbols) | {"SPY", "QQQ"})
    closes = _closes(universe)

    dates = sorted(account_equity.keys())

    def acct_return(since: datetime) -> Optional[float]:
        s = since.strftime("%Y-%m-%d")
        eligible = [d for d in dates if d >= s]
        if not eligible or not dates:
            return None
        first, last = account_equity[eligible[0]], account_equity[dates[-1]]
        return last / first - 1.0 if first else None

    windows = {
        "since_frozen": frozen_start,
        "trailing_30d": now - timedelta(days=30),
        "since_jan": retro_start,
    }
    report: dict = {
        "generated_at": now.isoformat(),
        "account": account_label,
        "frozen_at": basket["frozen_at"],
        "windows": {},
    }
    for name, start in windows.items():
        row = {
            "account": acct_return(start),
            "spy": _basket_return(["SPY"], closes, start),
            "qqq": _basket_return(["QQQ"], closes, start),
        }
        if name == "since_frozen":
            row["frozen_basket"] = _basket_return(
                basket["symbols"], closes, start, start_prices=basket["start_prices"])
        else:
            row["own_basket_retrospective"] = _basket_return(
                sorted(set(thesis_symbols)), closes, start)
        report["windows"][name] = {
            k: (round(v * 100, 2) if v is not None else None) for k, v in row.items()
        }

    report["caveat"] = ("own_basket_retrospective holds TODAY'S vehicles over a past window "
                        "(survivorship-biased). frozen_basket (forward from frozen_at) is the "
                        "clean does-activity-add-value benchmark.")

    out = _bench_dir() / "benchmark_latest.json"
    out.write_text(json.dumps(report, indent=2))
    (_bench_dir() / f"benchmark_{now.strftime('%Y%m%d')}.json").write_text(
        json.dumps(report, indent=2))
    return report
