#!/usr/bin/env python3
"""Periodic signal scan — WSB, Stocktwits, thesis suggestions.

Runs every 2 hours via cron. Pure Python, no Claude needed.
Results are picked up by operator_check() and surfaced in the web UI.

Cron entry (installed by setup_cron.sh):
    0 6,8,10,12,14,16 * * 1-5 cd /home/nock/projects/quant_suite && \
        PYTHONPATH=. python3 scripts/cron_signal_scan.py >> ~/quant_results/logs/signal_scan.log 2>&1
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [signal_scan] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path.home() / "quant_results"
SCAN_HISTORY = RESULTS_DIR / "logs" / "signal_scan_history.json"
SCAN_LATEST = RESULTS_DIR / "social" / "latest_scan.json"


async def scan_wsb() -> dict:
    """Scan WSB and related subreddits for mentions."""
    try:
        from src.data.sources.alternative.wsb_tracker import get_wsb_tracker

        tracker = get_wsb_tracker()
        mentions = await tracker.scan_recent_posts(limit=100)
        tracker._update_daily_stats()
        early_signals = tracker.get_early_signals()
        tracker.save_signals()

        result = {
            "mentions_found": len(mentions),
            "early_signals": len(early_signals),
            "signals": [
                {
                    "symbol": s.symbol,
                    "phase": s.current_phase.value,
                    "mentions": s.mention_count,
                    "growth_rate": round(s.growth_rate, 2),
                    "sentiment": round(s.avg_sentiment, 2),
                    "vintage_days": s.signal_vintage,
                    "dd_count": s.dd_count,
                }
                for s in early_signals[:15]
            ],
        }
        logger.info(f"WSB: {len(mentions)} mentions, {len(early_signals)} early signals")
        return result
    except Exception as e:
        logger.error(f"WSB scan failed: {e}")
        return {"error": str(e), "mentions_found": 0, "early_signals": 0, "signals": []}


def scan_thesis_suggestions() -> dict:
    """Check for thesis suggestions from converging signals."""
    try:
        from src.knowledge.thesis_suggester import get_thesis_suggester

        suggester = get_thesis_suggester()
        suggestions = suggester.generate_suggestions()

        result = {
            "count": len(suggestions),
            "suggestions": [
                {
                    "symbol": s.symbol,
                    "name": s.suggested_name,
                    "direction": s.direction,
                    "confidence": round(s.confidence_score, 2),
                    "signal_count": s.signal_count,
                    "sources": s.signal_sources[:5],
                }
                for s in suggestions
            ],
        }
        if suggestions:
            logger.info(f"Thesis suggestions: {len(suggestions)} new")
            for s in suggestions[:3]:
                logger.info(f"  -> {s.symbol}: {s.suggested_name} ({s.direction}, {s.signal_count} signals)")
        return result
    except Exception as e:
        logger.error(f"Thesis suggestion scan failed: {e}")
        return {"error": str(e), "count": 0, "suggestions": []}


def check_news_freshness() -> dict:
    """Check that news collection is running and report latest."""
    try:
        cache_file = RESULTS_DIR / "live" / "news_cache.json"
        if not cache_file.exists():
            return {"status": "missing", "count": 0}

        with open(cache_file) as f:
            news = json.load(f)

        items = news if isinstance(news, list) else news.get("items", [])
        age_hours = 0
        if items:
            latest_ts = max(
                (i.get("timestamp", i.get("published", "")) for i in items),
                default="",
            )
            if latest_ts:
                try:
                    latest = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
                    age_hours = (datetime.now() - latest.replace(tzinfo=None)).total_seconds() / 3600
                except (ValueError, TypeError):
                    pass

        thesis_matched = [i for i in items if i.get("thesis_matches")]

        return {
            "status": "ok" if age_hours < 6 else "stale",
            "count": len(items),
            "thesis_matched": len(thesis_matched),
            "age_hours": round(age_hours, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0}


def log_to_process_events(results: dict):
    """Log scan results as a ProcessEvent for operator visibility."""
    try:
        from src.autonomy.provenance import log_event

        signals = results.get("wsb", {}).get("signals", [])
        suggestions = results.get("suggestions", {}).get("suggestions", [])

        summary_parts = []
        if signals:
            top = ", ".join(s["symbol"] for s in signals[:5])
            summary_parts.append(f"WSB early: {top}")
        if suggestions:
            top = ", ".join(s["symbol"] for s in suggestions[:3])
            summary_parts.append(f"Thesis suggestions: {top}")

        summary = "; ".join(summary_parts) if summary_parts else "No notable signals"

        log_event(
            "signal_scan",
            source="cron:signal_scan",
            title=f"Signal scan: {summary}",
            severity="info",
        )
    except Exception:
        pass


async def main():
    logger.info("=" * 50)
    logger.info(f"Signal Scan Starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    results = {"timestamp": datetime.now().isoformat()}

    # Run scans
    results["wsb"] = await scan_wsb()
    results["suggestions"] = scan_thesis_suggestions()
    results["news"] = check_news_freshness()

    # Save latest scan result (operator reads this)
    SCAN_LATEST.parent.mkdir(parents=True, exist_ok=True)
    with open(SCAN_LATEST, "w") as f:
        json.dump(results, f, indent=2)

    # Append to history
    SCAN_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if SCAN_HISTORY.exists():
        try:
            with open(SCAN_HISTORY) as f:
                history = json.load(f)
        except (json.JSONDecodeError, ValueError):
            history = []

    history.append(results)
    history = history[-360:]  # ~30 days at 2-hour intervals

    with open(SCAN_HISTORY, "w") as f:
        json.dump(history, f, indent=2)

    # Log to ProcessEvent for operator
    log_to_process_events(results)

    # Summary
    wsb = results["wsb"]
    sug = results["suggestions"]
    news = results["news"]
    logger.info(f"Results: WSB {wsb.get('early_signals', 0)} early signals, "
                f"{sug.get('count', 0)} thesis suggestions, "
                f"news {'ok' if news.get('status') == 'ok' else 'STALE'}")
    logger.info("Scan complete")

    return results


if __name__ == "__main__":
    asyncio.run(main())
