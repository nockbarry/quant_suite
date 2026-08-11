"""
Wire monthly revenue reports (TSMC, etc.) into the document signal pipeline.

Milestone v5. The TSMCRevenueCollector already fetches monthly TWSE revenue
and computes YoY growth. This script converts those numbers into structured
SignalProvenance entries so they flow through ThesisSuggester convergence
detection — closing the v0 blind spot where TSM was excluded because it
files 6-K not 8-K.

This is a STRUCTURED signal (no LLM needed) — TSMC's monthly revenue is a
hard number with a clear directional interpretation.

Schedule: ~12:00 UTC on the 10th-12th of each month (TSMC publishes ~10th).
Idempotent — uses a date-stamped cache to avoid duplicate signals per
calendar month per symbol.

Usage:
    PYTHONPATH=. python3 scripts/cron_monthly_revenue_signals.py
    PYTHONPATH=. python3 scripts/cron_monthly_revenue_signals.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.data.sources.alternative.tsmc_revenue import TSMCRevenueCollector
from src.knowledge.signal_provenance import SignalSource, get_provenance_tracker

logger = logging.getLogger(__name__)

# YoY thresholds → (direction, magnitude, confidence)
def _classify(yoy_pct: float) -> Optional[tuple[str, str, float]]:
    if yoy_pct >= 30:
        return ("bullish", "strong", 0.85)
    if yoy_pct >= 15:
        return ("bullish", "moderate", 0.70)
    if yoy_pct >= 8:
        return ("bullish", "mild", 0.55)
    if yoy_pct <= -15:
        return ("bearish", "strong", 0.80)
    if yoy_pct <= -8:
        return ("bearish", "moderate", 0.65)
    if yoy_pct <= -3:
        return ("bearish", "mild", 0.50)
    # ±3% range = no actionable signal
    return None


def _cache_path() -> Path:
    return paths.scheduler / "processed_monthly_revenue.json"


def _load_cache() -> dict:
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict) -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2, sort_keys=True))


async def process_tsmc(dry_run: bool, cache: dict) -> dict:
    """Returns {action, key, yoy} or {action: 'skip', reason}."""
    collector = TSMCRevenueCollector()
    snapshot = await collector.collect()

    # Cache key: (symbol, latest_month) — one signal per reported month.
    cache_key = f"TSM_{snapshot.latest_month}"
    if cache_key in cache:
        return {"action": "skip", "reason": "already_processed", "key": cache_key}

    # Source quality gate: don't write signals from "reference" (hardcoded historical) data
    if snapshot.source not in ("tsmc_ir", "tsmc_ir_html"):
        return {
            "action": "skip",
            "reason": f"source_not_live({snapshot.source})",
            "key": cache_key,
        }

    classification = _classify(snapshot.yoy_growth_pct)
    if classification is None:
        return {
            "action": "skip",
            "reason": f"yoy_in_neutral_zone({snapshot.yoy_growth_pct:+.1f}%)",
            "key": cache_key,
        }

    direction, magnitude, confidence = classification
    description = (
        f"TSMC {snapshot.latest_month} revenue YoY {snapshot.yoy_growth_pct:+.1f}% "
        f"({snapshot.revenue_trend}). MoM {snapshot.mom_growth_pct:+.1f}%."
    )

    if dry_run:
        logger.info(
            f"[DRY] would write {direction}/{magnitude} TSM signal: {description}"
        )
        return {
            "action": "would_write",
            "key": cache_key,
            "direction": direction,
            "magnitude": magnitude,
            "yoy": snapshot.yoy_growth_pct,
        }

    tracker = get_provenance_tracker()
    provenance = tracker.create_signal(
        source=SignalSource.MONTHLY_REVENUE,
        symbol="TSM",
        confidence=confidence,
        direction=direction,
        description=description,
        detection_method="tsmc_monthly_revenue_yoy",
        metadata={
            "signal_type": "monthly_revenue_yoy",
            "magnitude": magnitude,
            "latest_month": snapshot.latest_month,
            "latest_revenue_twd_b": snapshot.latest_revenue_twd_b,
            "yoy_growth_pct": snapshot.yoy_growth_pct,
            "mom_growth_pct": snapshot.mom_growth_pct,
            "revenue_trend": snapshot.revenue_trend,
            "semi_cycle_signal": snapshot.semi_cycle_signal,
            "source_quality": snapshot.data_quality,
        },
    )
    cache[cache_key] = {
        "symbol": "TSM",
        "latest_month": snapshot.latest_month,
        "yoy_growth_pct": snapshot.yoy_growth_pct,
        "direction": direction,
        "magnitude": magnitude,
        "signal_id": provenance.signal_id,
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {
        "action": "wrote_signal",
        "key": cache_key,
        "signal_id": provenance.signal_id,
        "direction": direction,
        "magnitude": magnitude,
        "yoy": snapshot.yoy_growth_pct,
    }


async def run(dry_run: bool = False) -> dict:
    cache = _load_cache()
    results = {}
    try:
        results["tsmc"] = await process_tsmc(dry_run, cache)
    except Exception as e:
        logger.exception(f"TSMC processing failed: {e}")
        results["tsmc"] = {"action": "error", "error": str(e)}

    if not dry_run:
        _save_cache(cache)

    return {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "results": results,
        "cache_size": len(cache),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monthly revenue signal cron (v5)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    summary = asyncio.run(run(dry_run=args.dry_run))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
