#!/usr/bin/env python3
"""Cache corporate actions (splits) for held + universe symbols.

Cron: 5:45 AM ET Mon-Fri — before the synthesis daemon's first P&L snapshot,
the 10:15 reconcile, and any adaptive-trigger evaluation. Downstream readers
use src.data.corporate_actions.todays_splits().
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [corp-actions] %(message)s")
logger = logging.getLogger("corp-actions")


def gather_symbols() -> list[str]:
    """Held positions + thesis vehicles + opinion universe (best effort)."""
    symbols: set[str] = set()
    try:
        import json

        from src.core.paths import paths

        state = json.loads(Path(paths.live_state).read_text())
        for pos in (state.get("portfolio", {}) or {}).get("positions", []) or []:
            if pos.get("symbol"):
                symbols.add(pos["symbol"])
    except Exception as e:
        logger.warning(f"state.json positions unavailable: {e}")

    try:
        from src.knowledge.thesis import ThesisTracker

        for th in ThesisTracker().get_active_theses():
            symbols.update(th.positions or [])
    except Exception as e:
        logger.warning(f"thesis vehicles unavailable: {e}")

    try:
        from src.opinions.universe import OpinionUniverse

        symbols.update(e["symbol"] for e in OpinionUniverse().get_universe() if e.get("symbol"))
    except Exception as e:
        logger.warning(f"opinion universe unavailable: {e}")

    return sorted(symbols)


def main() -> int:
    from src.data.corporate_actions import CACHE_FILE, fetch_recent_splits, write_cache

    symbols = gather_symbols()
    if not symbols:
        logger.error("No symbols gathered — writing empty cache so readers see a fresh file")
        write_cache([])
        return 1

    try:
        events = fetch_recent_splits(symbols)
    except Exception as e:
        logger.error(f"Corporate-actions fetch failed: {e}")
        # Do NOT overwrite an existing cache with nothing on API failure —
        # yesterday's lookahead window may still cover today's ex-dates.
        if not CACHE_FILE.exists():
            write_cache([])
        return 1

    write_cache(events)
    if events:
        for e in events:
            logger.info(f"SPLIT: {e.symbol} {e.ratio:g}x ex={e.ex_date} ({e.action_type})")
    else:
        logger.info(f"No splits in window for {len(symbols)} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
