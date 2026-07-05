"""
Empirical calibration of SupplyChainGraph decay factors (Milestone v4).

For each edge (root → target) in SUPPLY_CHAIN_V0, runs an event study around
the root's historical earnings announcement dates (SEC 8-K item 2.02 filings,
fetched via EarningsTranscriptCollector). Computes the information coefficient
(IC) between root's earnings-window return and target's post-event return.

Drops edges whose |IC| < 0.15 (noise floor). For surviving edges, sets the
decay factor as a function of IC and directional consistency, clipped to
[0.4, 0.9].

Output: ~/quant_results/calibration/supply_chain_v1.json
SupplyChainGraph loads this file at instantiation if present, falling back
to v0 priors otherwise.

Usage:
    PYTHONPATH=. python3 scripts/calibrate_supply_chain.py
    PYTHONPATH=. python3 scripts/calibrate_supply_chain.py --years 5 --window 30
    PYTHONPATH=. python3 scripts/calibrate_supply_chain.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.data.sources.alternative.earnings_transcripts import (
    EarningsTranscriptCollector,
)
from src.intelligence.supply_chain_graph import SUPPLY_CHAIN_V0, Edge

logger = logging.getLogger(__name__)

# Calibration thresholds
MIN_IC = 0.15           # below this, edge is dropped
MIN_EVENTS = 8          # minimum earnings events per root to attempt calibration
DECAY_FLOOR = 0.40      # min decay (matches SupplyChainGraph.MIN_INFERRED_CONFIDENCE)
DECAY_CEILING = 0.90    # max decay — never trust an edge fully
DEFAULT_WINDOW_DAYS = 30  # post-event return horizon


@dataclass
class EdgeCalibration:
    """Calibration result for a single edge."""
    source: str
    target: str
    relation: str
    n_events: int
    ic: float                     # Pearson correlation of root vs target windowed returns
    directional_consistency: float  # fraction of events where signs agree
    median_target_return: float    # median target return after root events (sanity check)
    decay: Optional[float]         # None if dropped
    dropped: bool
    drop_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Data helpers
# ----------------------------------------------------------------------------

def _fetch_prices(symbol: str, years: int) -> Optional["pd.DataFrame"]:
    """Daily close prices for the past N years. Returns None on failure."""
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period=f"{years}y", interval="1d")
        if df.empty or "Close" not in df.columns:
            return None
        # Strip timezone for clean date arithmetic
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        return df[["Close"]]
    except Exception as e:
        logger.warning(f"price fetch failed for {symbol}: {e}")
        return None


async def _fetch_earnings_dates(symbol: str, years: int) -> list[str]:
    """Historical 8-K item 2.02 filing dates (ISO YYYY-MM-DD)."""
    collector = EarningsTranscriptCollector()
    cik = collector.EXTRA_CIKS.get(symbol.upper()) or await collector.scraper.cik_lookup.get_cik(symbol)
    if not cik:
        await collector.close()
        return []
    # We want a wide history — use a generous limit and filter by date below.
    try:
        candidates = await collector._list_earnings_filings(cik, limit=80)
    except Exception as e:
        logger.warning(f"earnings dates fetch failed for {symbol}: {e}")
        await collector.close()
        return []
    finally:
        await collector.close()
    cutoff = datetime.now() - timedelta(days=years * 365)
    out = []
    for c in candidates:
        try:
            dt = datetime.strptime(c["filed_date"], "%Y-%m-%d")
        except (ValueError, KeyError):
            continue
        if dt >= cutoff:
            out.append(c["filed_date"])
    return sorted(out)


def _window_return(prices: "pd.DataFrame", as_of_date: str, days: int) -> Optional[float]:
    """Return ((P[t+days] - P[t]) / P[t])."""
    import pandas as pd
    target = pd.Timestamp(as_of_date)
    # Find first trading day on/after target
    after = prices.index[prices.index >= target]
    if len(after) == 0:
        return None
    start_idx = after[0]
    end_target = start_idx + pd.Timedelta(days=days)
    after_end = prices.index[prices.index >= end_target]
    if len(after_end) == 0:
        return None
    end_idx = after_end[0]
    p0 = prices.loc[start_idx, "Close"]
    p1 = prices.loc[end_idx, "Close"]
    if p0 == 0 or pd.isna(p0) or pd.isna(p1):
        return None
    return float((p1 - p0) / p0)


def _earnings_window_return(prices: "pd.DataFrame", as_of_date: str) -> Optional[float]:
    """Return for the trading day of the earnings event (close vs prior close).
    A proxy for the market's reaction to the earnings news."""
    import pandas as pd
    target = pd.Timestamp(as_of_date)
    on_or_after = prices.index[prices.index >= target]
    if len(on_or_after) == 0:
        return None
    today = on_or_after[0]
    earlier = prices.index[prices.index < today]
    if len(earlier) == 0:
        return None
    yesterday = earlier[-1]
    p0 = prices.loc[yesterday, "Close"]
    p1 = prices.loc[today, "Close"]
    if p0 == 0 or pd.isna(p0) or pd.isna(p1):
        return None
    return float((p1 - p0) / p0)


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation; 0.0 on degenerate input. No numpy dependency."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _directional_consistency(xs: list[float], ys: list[float]) -> float:
    """Fraction of (x, y) pairs where signs agree (excluding zeros)."""
    matches = 0
    n = 0
    for x, y in zip(xs, ys):
        if x == 0 or y == 0:
            continue
        n += 1
        if (x > 0) == (y > 0):
            matches += 1
    return matches / n if n > 0 else 0.0


# ----------------------------------------------------------------------------
# Calibration core
# ----------------------------------------------------------------------------

async def calibrate_edge(
    source: str,
    target: str,
    relation: str,
    years: int,
    window_days: int,
) -> EdgeCalibration:
    """Run the event study for a single edge."""
    earnings_dates = await _fetch_earnings_dates(source, years)
    if len(earnings_dates) < MIN_EVENTS:
        return EdgeCalibration(
            source=source, target=target, relation=relation,
            n_events=len(earnings_dates),
            ic=0.0, directional_consistency=0.0, median_target_return=0.0,
            decay=None, dropped=True,
            drop_reason=f"insufficient_events({len(earnings_dates)}<{MIN_EVENTS})",
        )

    src_prices = _fetch_prices(source, years)
    tgt_prices = _fetch_prices(target, years)
    if src_prices is None or tgt_prices is None:
        return EdgeCalibration(
            source=source, target=target, relation=relation,
            n_events=len(earnings_dates),
            ic=0.0, directional_consistency=0.0, median_target_return=0.0,
            decay=None, dropped=True,
            drop_reason="price_fetch_failed",
        )

    src_earnings_returns: list[float] = []
    tgt_post_returns: list[float] = []
    for ed in earnings_dates:
        sr = _earnings_window_return(src_prices, ed)
        tr = _window_return(tgt_prices, ed, window_days)
        if sr is None or tr is None:
            continue
        src_earnings_returns.append(sr)
        tgt_post_returns.append(tr)

    if len(src_earnings_returns) < MIN_EVENTS:
        return EdgeCalibration(
            source=source, target=target, relation=relation,
            n_events=len(src_earnings_returns),
            ic=0.0, directional_consistency=0.0, median_target_return=0.0,
            decay=None, dropped=True,
            drop_reason=f"insufficient_paired_events({len(src_earnings_returns)})",
        )

    ic = _pearson(src_earnings_returns, tgt_post_returns)
    consistency = _directional_consistency(src_earnings_returns, tgt_post_returns)
    median_tr = sorted(tgt_post_returns)[len(tgt_post_returns) // 2]

    if abs(ic) < MIN_IC:
        return EdgeCalibration(
            source=source, target=target, relation=relation,
            n_events=len(src_earnings_returns),
            ic=ic, directional_consistency=consistency,
            median_target_return=median_tr,
            decay=None, dropped=True,
            drop_reason=f"ic_below_threshold({abs(ic):.3f}<{MIN_IC})",
        )

    # Drop edges with NEGATIVE IC: this means the v0 directional prior
    # ("when source rises, target rises") is empirically wrong. The honest
    # response is to remove the edge entirely — propagation in the wrong
    # direction is worse than no propagation. Direction-flipping (positive
    # signal on source → negative inferred on target) would require extending
    # the InferredSignal data model and is deferred to a later milestone.
    if ic < 0:
        return EdgeCalibration(
            source=source, target=target, relation=relation,
            n_events=len(src_earnings_returns),
            ic=ic, directional_consistency=consistency,
            median_target_return=median_tr,
            decay=None, dropped=True,
            drop_reason=f"negative_ic({ic:+.3f}_v0_direction_wrong)",
        )

    # Decay: scale IC by directional consistency, clip to [floor, ceiling].
    # IC=0.5, consistency=0.7 -> 0.5 * 0.7 * 1.5 = 0.525
    decay_raw = ic * consistency * 1.5
    decay = max(DECAY_FLOOR, min(DECAY_CEILING, decay_raw))

    return EdgeCalibration(
        source=source, target=target, relation=relation,
        n_events=len(src_earnings_returns),
        ic=ic, directional_consistency=consistency,
        median_target_return=median_tr,
        decay=decay, dropped=False,
    )


async def calibrate_all(years: int, window_days: int) -> list[EdgeCalibration]:
    results: list[EdgeCalibration] = []
    for source, edges in SUPPLY_CHAIN_V0.items():
        # Skip the synthetic "TSM_litho" key which isn't a real symbol
        if not source.isalpha():
            logger.info(f"skipping non-symbol key {source!r}")
            continue
        for edge in edges:
            logger.info(f"calibrating {source} -> {edge.target} ({edge.relation})")
            cal = await calibrate_edge(
                source=source,
                target=edge.target,
                relation=edge.relation,
                years=years,
                window_days=window_days,
            )
            results.append(cal)
            if cal.dropped:
                logger.warning(
                    f"  DROPPED: {cal.drop_reason} "
                    f"(IC={cal.ic:.3f}, consistency={cal.directional_consistency:.2f}, n={cal.n_events})"
                )
            else:
                logger.info(
                    f"  IC={cal.ic:+.3f}, consistency={cal.directional_consistency:.2f}, "
                    f"n={cal.n_events}, decay={cal.decay:.3f}"
                )
    return results


def write_calibrated_graph(results: list[EdgeCalibration], output_path: Path) -> None:
    """Write the surviving edges in the SupplyChainGraph format."""
    graph: dict[str, list[dict]] = {}
    for cal in results:
        if cal.dropped:
            continue
        graph.setdefault(cal.source, []).append({
            "target": cal.target,
            "relation": cal.relation,
            "decay": round(cal.decay, 4),
            "notes": (
                f"calibrated v1 (IC={cal.ic:+.3f}, "
                f"consistency={cal.directional_consistency:.2f}, n={cal.n_events})"
            ),
        })

    payload = {
        "version": "v1",
        "calibrated_at": datetime.now().isoformat(timespec="seconds"),
        "min_ic": MIN_IC,
        "min_events": MIN_EVENTS,
        "decay_floor": DECAY_FLOOR,
        "decay_ceiling": DECAY_CEILING,
        "graph": graph,
        "all_results": [r.to_dict() for r in results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"wrote {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate SupplyChainGraph decay factors")
    parser.add_argument("--years", type=int, default=5, help="Lookback years for events (default 5)")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_DAYS,
                        help="Post-event return window days (default 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output file")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    output_path = paths.base / "calibration" / "supply_chain_v1.json"

    results = asyncio.run(calibrate_all(args.years, args.window))

    surviving = sum(1 for r in results if not r.dropped)
    dropped = sum(1 for r in results if r.dropped)
    logger.info(f"\nSummary: {surviving} surviving / {dropped} dropped of {len(results)} edges")

    if args.dry_run:
        logger.info("dry-run, not writing")
        for r in results:
            logger.info(f"  {r.to_dict()}")
        return 0

    write_calibrated_graph(results, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
