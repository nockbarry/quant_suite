#!/usr/bin/env python3
"""Market Mover Scanner — significant price moves across a broad universe.

Runs after close (5:20 PM) and midday (12:30 PM). Pure Python, zero Claude tokens.
Results are picked up by sentinel, daemon, operator, and morning briefing.

Cron entries (installed by setup_cron.sh):
    20 17 * * 1-5 cd /home/nock/projects/quant_suite && \
        PYTHONPATH=. python3 scripts/cron_market_movers.py >> ~/quant_results/logs/market_movers.log 2>&1
    30 12 * * 1-5 cd /home/nock/projects/quant_suite && \
        PYTHONPATH=. python3 scripts/cron_market_movers.py --intraday >> ~/quant_results/logs/market_movers.log 2>&1

Manual:
    PYTHONPATH=. python3 scripts/cron_market_movers.py
    PYTHONPATH=. python3 scripts/cron_market_movers.py --intraday
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [market_movers] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path.home() / "quant_results"
MOVERS_LATEST = RESULTS_DIR / "live" / "market_movers_latest.json"
MOVERS_HISTORY = RESULTS_DIR / "logs" / "market_movers_history.json"


def save_latest(scan_dict: dict) -> None:
    """Save latest scan result for sentinel/daemon to read."""
    MOVERS_LATEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MOVERS_LATEST, "w") as f:
        json.dump(scan_dict, f, indent=2)
    logger.info(f"Saved latest to {MOVERS_LATEST}")


def append_history(scan_dict: dict) -> None:
    """Append to scan history (keep 30 days)."""
    MOVERS_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if MOVERS_HISTORY.exists():
        try:
            with open(MOVERS_HISTORY) as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, ValueError):
            history = []

    # Keep summary only for history (not full enrichment details)
    summary = {
        "timestamp": scan_dict.get("timestamp"),
        "universe_size": scan_dict.get("universe_size", 0),
        "movers_found": scan_dict.get("movers_found", 0),
        "top_gainers": [
            {"symbol": m["symbol"], "change_1d_pct": m["change_1d_pct"]}
            for m in scan_dict.get("gainers", [])[:5]
        ],
        "top_losers": [
            {"symbol": m["symbol"], "change_1d_pct": m["change_1d_pct"]}
            for m in scan_dict.get("losers", [])[:5]
        ],
    }
    history.append(summary)
    history = history[-60:]  # ~30 days at 2 scans/day

    with open(MOVERS_HISTORY, "w") as f:
        json.dump(history, f, indent=2)


def index_documents(scan_dict: dict) -> None:
    """Save significant movers as Documents in athena.db for searchability."""
    try:
        from src.db.write_api import athena_db

        date_str = datetime.now().strftime("%Y%m%d")
        indexed = 0

        # Index movers with meaningful context
        all_movers = scan_dict.get("top_context", [])
        for mover in all_movers:
            if mover.get("context_score", 0) < 0.15:
                continue

            sym = mover["symbol"]
            ctx_parts = []
            if mover.get("news_matches"):
                ctx_parts.append(f"{len(mover['news_matches'])} news")
            if mover.get("finviz_screens"):
                ctx_parts.append(f"screens: {', '.join(mover['finviz_screens'])}")
            if mover.get("wsb_status"):
                ctx_parts.append(f"WSB: {mover['wsb_status'].get('phase', '?')}")
            if mover.get("thesis_alignment"):
                ctx_parts.append(f"thesis: {mover['thesis_alignment'].get('thesis_name', '?')}")

            context_summary = " | ".join(ctx_parts) if ctx_parts else "price move only"

            athena_db.save_document(
                doc_type="market_mover",
                title=f"{sym} {mover['change_1d_pct']:+.1f}% ({mover['trigger']}) — {context_summary}",
                content_inline=json.dumps(mover, indent=2)[:5000],
                symbols=[sym],
                tags=["market_mover", mover.get("trigger", "unknown"),
                      mover.get("sector") or "unknown"],
                source="cron:market_movers",
            )
            indexed += 1

        logger.info(f"Indexed {indexed} mover documents")
    except Exception as e:
        logger.error(f"Document indexing failed: {e}")


def log_process_event(scan_dict: dict) -> None:
    """Log ProcessEvent for audit trail."""
    try:
        from src.db.write_api import athena_db

        movers_found = scan_dict.get("movers_found", 0)
        top = scan_dict.get("gainers", [])[:3]
        top_str = ", ".join(
            f"{m['symbol']} {m['change_1d_pct']:+.1f}%" for m in top
        )

        athena_db.log_event(
            event_type="market_mover_scan",
            source="cron:market_movers",
            title=f"Scanned {scan_dict.get('universe_size', 0)} symbols, "
            f"{movers_found} movers: {top_str}",
            detail=json.dumps({
                "universe_size": scan_dict.get("universe_size", 0),
                "movers_found": movers_found,
                "top_gainers": [m["symbol"] for m in scan_dict.get("gainers", [])[:5]],
                "top_losers": [m["symbol"] for m in scan_dict.get("losers", [])[:5]],
            }),
            severity="info",
        )
    except Exception as e:
        logger.debug(f"ProcessEvent logging failed: {e}")


def register_provenance(scan_dict: dict) -> None:
    """Create SignalProvenance entries for high-context movers.

    This feeds ThesisSuggester convergence detection — market mover signals
    (source=STATISTICAL) combine with WSB/NEWS/INSIDER signals to reach
    the 3+ convergence threshold.
    """
    try:
        from src.knowledge.signal_provenance import get_provenance_tracker, SignalSource

        tracker = get_provenance_tracker()
        registered = 0

        for mover in scan_dict.get("top_context", []):
            if mover.get("context_score", 0) < 0.2:
                continue

            sym = mover["symbol"]
            direction = "bullish" if mover.get("change_1d_pct", 0) > 0 else "bearish"

            ctx_parts = []
            if mover.get("news_matches"):
                ctx_parts.append(f"{len(mover['news_matches'])} news headlines")
            if mover.get("finviz_screens"):
                ctx_parts.append(f"Finviz: {', '.join(mover['finviz_screens'])}")
            if mover.get("wsb_status"):
                ctx_parts.append(f"WSB {mover['wsb_status'].get('phase', '?')}")

            description = (
                f"Market mover: {mover.get('change_1d_pct', 0):+.1f}% day, "
                f"{mover.get('volume_ratio', 0):.1f}x volume. "
                f"Context: {'; '.join(ctx_parts) if ctx_parts else 'price move only'}"
            )

            # Skip if we already have a mover signal for this symbol today
            today = datetime.now().strftime("%Y-%m-%d")
            already_exists = any(
                s.symbol == sym
                and s.detection_method == "market_mover_scan"
                and s.first_detected.strftime("%Y-%m-%d") == today
                for s in tracker._cache.values()
            )
            if not already_exists:
                tracker.create_signal(
                    source=SignalSource.STATISTICAL,
                    symbol=sym,
                    confidence=mover.get("context_score", 0.5),
                    direction=direction,
                    description=description,
                    detection_method="market_mover_scan",
                    metadata={
                        "trigger": mover.get("trigger"),
                        "change_1d": mover.get("change_1d_pct"),
                        "volume_ratio": mover.get("volume_ratio"),
                        "finviz_screens": mover.get("finviz_screens", []),
                    },
                )
                registered += 1

        logger.info(f"Registered {registered} provenance signals")
    except Exception as e:
        logger.error(f"Provenance registration failed: {e}")


def print_summary(scan_dict: dict) -> None:
    """Print human-readable summary to stdout."""
    print(f"\n{'='*60}")
    print(f"Market Movers — {scan_dict.get('timestamp', 'unknown')}")
    print(f"Universe: {scan_dict.get('universe_size', 0)} | Movers: {scan_dict.get('movers_found', 0)}")
    print(f"{'='*60}")

    if scan_dict.get("top_context"):
        print("\nTOP CONTEXT (highest signal convergence):")
        for m in scan_dict["top_context"][:10]:
            ctx = []
            if m.get("news_matches"):
                ctx.append(f"news={len(m['news_matches'])}")
            if m.get("finviz_screens"):
                ctx.append(f"screens={len(m['finviz_screens'])}")
            if m.get("wsb_status"):
                ctx.append(f"wsb={m['wsb_status'].get('phase', '?')}")
            if m.get("thesis_alignment"):
                ctx.append(f"thesis")
            print(
                f"  {m['symbol']:6} {m.get('change_1d_pct', 0):+6.1f}%  "
                f"vol={m.get('volume_ratio', 0):4.1f}x  "
                f"ctx={m.get('context_score', 0):.0%}  "
                f"[{', '.join(ctx)}]"
            )

    if scan_dict.get("gainers"):
        print("\nTOP GAINERS:")
        for m in scan_dict["gainers"][:5]:
            print(f"  {m['symbol']:6} {m.get('change_1d_pct', 0):+6.1f}%  5d={m.get('change_5d_pct', 0):+.1f}%  vol={m.get('volume_ratio', 0):.1f}x")

    if scan_dict.get("losers"):
        print("\nTOP LOSERS:")
        for m in scan_dict["losers"][:5]:
            print(f"  {m['symbol']:6} {m.get('change_1d_pct', 0):+6.1f}%  5d={m.get('change_5d_pct', 0):+.1f}%  vol={m.get('volume_ratio', 0):.1f}x")

    print()


async def main():
    parser = argparse.ArgumentParser(description="Market Mover Scanner")
    parser.add_argument("--intraday", action="store_true", help="Use tighter intraday thresholds")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info(f"Market Movers Scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.intraday:
        logger.info("Mode: INTRADAY (tighter thresholds)")

    from src.intelligence.market_movers import MarketMoverScanner

    scanner = MarketMoverScanner(intraday=args.intraday)
    scan = scanner.scan()
    scan_dict = scan.to_dict()

    save_latest(scan_dict)
    append_history(scan_dict)
    index_documents(scan_dict)
    log_process_event(scan_dict)
    register_provenance(scan_dict)
    print_summary(scan_dict)

    logger.info(f"Scan complete: {scan.movers_found} movers from {scan.universe_size} symbols")


if __name__ == "__main__":
    asyncio.run(main())
