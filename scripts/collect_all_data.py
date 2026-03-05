#!/usr/bin/env python3
"""Master Data Collection Script - Collects from ALL data sources.

Run this to activate all data sources and log results.

Usage:
    PYTHONPATH=. python scripts/collect_all_data.py
    PYTHONPATH=. python scripts/collect_all_data.py --quick  # Essential only
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Collector Functions ---

async def collect_expanded_news():
    """Collect from 15+ RSS feeds."""
    try:
        from src.data.sources.alternative.expanded_news import ExpandedNewsCollector
        collector = ExpandedNewsCollector()
        result = await collector.collect_and_save()
        await collector.close()
        return {"expanded_news": result}
    except Exception as e:
        logger.error(f"Expanded news collection failed: {e}")
        return {"expanded_news": {"error": str(e)}}


async def collect_legal():
    """Collect legal/regulatory events."""
    try:
        from src.data.sources.alternative.legal_tracker import LegalTracker
        tracker = LegalTracker()
        result = await tracker.collect_all()
        await tracker.close()
        return {"legal": result}
    except Exception as e:
        logger.error(f"Legal collection failed: {e}")
        return {"legal": {"error": str(e)}}


async def collect_geopolitical():
    """Collect geopolitical events."""
    try:
        from src.data.sources.alternative.geopolitical import GeopoliticalMonitor
        monitor = GeopoliticalMonitor()
        result = await monitor.collect_all()
        await monitor.close()
        return {"geopolitical": result}
    except Exception as e:
        logger.error(f"Geopolitical collection failed: {e}")
        return {"geopolitical": {"error": str(e)}}


async def collect_sector_rotation():
    """Analyze sector rotation."""
    try:
        from src.synthesis.sector_rotation import SectorRotationDetector
        detector = SectorRotationDetector()
        strengths = await detector.analyze_sectors()
        signal = detector.detect_rotation(strengths)
        return {
            "sector_rotation": {
                "sectors_analyzed": len(strengths),
                "rotation_signal": signal.to_dict() if signal else None,
            }
        }
    except Exception as e:
        logger.error(f"Sector rotation failed: {e}")
        return {"sector_rotation": {"error": str(e)}}


async def collect_from_daemon():
    """Run the data collection daemon for all sources."""
    try:
        from src.data.sources.collection_daemon import DataCollectionDaemon
        daemon = DataCollectionDaemon()
        await daemon.collect_all_now()
        status = daemon.get_status()
        return {"daemon": {"sources_collected": len(status.sources)}}
    except Exception as e:
        logger.error(f"Daemon collection failed: {e}")
        return {"daemon": {"error": str(e)}}


async def collect_wsb():
    """Collect WSB and Reddit social signals."""
    try:
        from src.data.sources.alternative.wsb_tracker import get_wsb_tracker
        tracker = get_wsb_tracker()
        mentions = await tracker.scan_recent_posts(limit=100)
        early_signals = tracker.get_early_signals()
        return {"wsb": {
            "mentions": len(mentions),
            "early_signals": len(early_signals),
            "top_signals": [
                {"symbol": s.symbol, "phase": s.current_phase.value, "mentions": s.mention_count}
                for s in early_signals[:5]
            ],
        }}
    except Exception as e:
        logger.error(f"WSB collection failed: {e}")
        return {"wsb": {"error": str(e)}}


async def collect_finviz():
    """Collect Finviz screen results."""
    try:
        from src.data.sources.alternative.finviz_screens import FinvizScreener
        screener = FinvizScreener()
        screens = await screener.get_screens(force_refresh=True)
        await screener.close()
        return {"finviz": {
            "screens": len(screens.screens),
            "total_symbols": sum(s.symbol_count for s in screens.screens.values()),
        }}
    except Exception as e:
        logger.error(f"Finviz collection failed: {e}")
        return {"finviz": {"error": str(e)}}


async def collect_stocktwits():
    """Collect Stocktwits trending data."""
    try:
        from src.data.sources.alternative.stocktwits import get_stocktwits_client
        client = get_stocktwits_client()
        trending = client.get_trending()
        return {"stocktwits": {
            "trending_count": len(trending),
            "top_trending": [t.get("symbol", t.get("title", "?")) for t in trending[:10]],
        }}
    except Exception as e:
        logger.error(f"Stocktwits collection failed: {e}")
        return {"stocktwits": {"error": str(e)}}


async def collect_congressional():
    """Collect congressional trading data and persist to disk."""
    try:
        from src.core.paths import paths
        from src.data.sources.alternative.congressional_trades import CongressionalTradesSource
        source = CongressionalTradesSource()
        trades = await source.fetch_recent_trades(days=7)
        notable = [t for t in trades if t.signal_strength >= 0.5]

        # Persist to disk for daemon.py, data_freshness_tracker, and web UI
        log_dir = paths.base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "congressional_collection_history.json"

        history = []
        if log_file.exists():
            try:
                with open(log_file) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, ValueError):
                history = []

        history.append({
            "timestamp": datetime.now().isoformat(),
            "trades_found": len(trades),
            "notable_trades": [t.to_dict() for t in notable[:20]],
        })
        history = history[-90:]

        with open(log_file, "w") as f:
            json.dump(history, f, indent=2, default=str)

        return {"congressional": {
            "total_trades": len(trades),
            "notable_trades": len(notable),
            "top_trades": [
                {"politician": t.politician, "symbol": t.symbol, "type": t.trade_type, "amount": t.amount_estimate}
                for t in notable[:5]
            ],
        }}
    except Exception as e:
        logger.error(f"Congressional collection failed: {e}")
        return {"congressional": {"error": str(e)}}


async def collect_prediction_markets():
    """Collect prediction market data and persist to disk."""
    try:
        from src.core.paths import paths
        from src.data.sources.alternative.prediction_markets import PredictionMarketsSource
        source = PredictionMarketsSource()
        signals = await source.get_macro_signals()

        # Persist to disk for web UI data_sources.py
        pm_dir = paths.live / "research" / "prediction_markets"
        pm_dir.mkdir(parents=True, exist_ok=True)
        latest_file = pm_dir / "latest.json"

        with open(latest_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "macro_signals": [s.to_dict() for s in signals],
            }, f, indent=2, default=str)

        return {"prediction_markets": {
            "macro_signals": len(signals),
            "top_signals": [
                {"category": s.category.value, "direction": s.consensus_direction, "avg_probability": s.avg_probability}
                for s in signals[:5]
            ],
        }}
    except Exception as e:
        logger.error(f"Prediction markets collection failed: {e}")
        return {"prediction_markets": {"error": str(e)}}


async def collect_insider():
    """Collect insider trading data and persist to disk."""
    try:
        from src.core.paths import paths
        from src.data.sources.alternative.insider import InsiderDataSource

        source = InsiderDataSource()
        # Scan a default set of symbols for recent insider activity
        watchlist = [
            "SLB", "HAL", "NVDA", "MSFT", "AAPL", "GOOGL", "META",
            "AMD", "AMZN", "XOM", "CVX", "JPM", "GS", "SPY",
        ]

        all_transactions = []
        for symbol in watchlist:
            try:
                end = datetime.now()
                start = end - timedelta(days=30)
                transactions = await source.fetch_transactions(symbol, start, end, limit=50)
                for t in transactions:
                    all_transactions.append(t.to_dict())
            except Exception:
                pass

        await source.close()

        purchases = [t for t in all_transactions if t.get("is_purchase")]
        notable = [t for t in all_transactions if t.get("value", 0) >= 100_000]

        # Persist to disk for data_freshness_tracker and web UI
        log_dir = paths.base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "insider_collection_history.json"

        history = []
        if log_file.exists():
            try:
                with open(log_file) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, ValueError):
                history = []

        history.append({
            "timestamp": datetime.now().isoformat(),
            "result": {
                "status": "success",
                "transactions_collected": len(all_transactions),
                "purchases": len(purchases),
                "notable_transactions": len(notable),
                "top_notable": notable[:20],
            },
        })
        history = history[-90:]

        with open(log_file, "w") as f:
            json.dump(history, f, indent=2, default=str)

        return {"insider": {
            "transactions": len(all_transactions),
            "purchases": len(purchases),
            "notable": len(notable),
        }}
    except Exception as e:
        logger.error(f"Insider collection failed: {e}")
        return {"insider": {"error": str(e)}}


async def update_unified_state():
    """Update the unified state file."""
    try:
        from src.synthesis.daemon import LiveDaemon
        daemon = LiveDaemon()
        state = await daemon.update_now()
        return {"unified_state": "updated", "timestamp": state.timestamp.isoformat()}
    except Exception as e:
        logger.error(f"State update failed: {e}")
        return {"unified_state": {"error": str(e)}}


async def run_signpost_check():
    """Check signposts for triggered alerts."""
    try:
        from scripts.signpost_monitor import load_signposts, check_signposts, save_alerts
        signposts = load_signposts()
        triggered = check_signposts(signposts, alerts_only=True)
        if triggered:
            save_alerts(triggered)
        return {"signposts": {"checked": len(signposts), "triggered": len(triggered)}}
    except Exception as e:
        logger.error(f"Signpost check failed: {e}")
        return {"signposts": {"error": str(e)}}


# --- ProcessEvent Logging ---

def log_collection_event(name: str, result: dict):
    """Log a data collection event to ProcessEvent for provenance."""
    try:
        from src.autonomy.provenance import log_event
        has_error = "error" in result.get(name, result)
        log_event(
            event_type="data_collected" if not has_error else "data_collection_failed",
            source=f"collector:{name}",
            title=f"{'Collected' if not has_error else 'Failed'}: {name}",
            detail=result,
        )
    except Exception:
        pass  # Don't fail collection over logging


# --- Main Collection ---

async def collect_all(quick: bool = False):
    """Collect from all data sources in parallel."""
    logger.info("=" * 60)
    logger.info(f"Master Data Collection - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    start_time = datetime.now()

    # Essential collections (always run)
    essential = {
        "expanded_news": collect_expanded_news(),
        "unified_state": update_unified_state(),
        "signposts": run_signpost_check(),
    }

    # Extended collections (skip if --quick)
    extended = {
        "legal": collect_legal(),
        "geopolitical": collect_geopolitical(),
        "sector_rotation": collect_sector_rotation(),
        "wsb": collect_wsb(),
        "finviz": collect_finviz(),
        "stocktwits": collect_stocktwits(),
        "congressional": collect_congressional(),
        "prediction_markets": collect_prediction_markets(),
        "insider": collect_insider(),
        "daemon": collect_from_daemon(),
    }

    tasks = essential if quick else {**essential, **extended}

    logger.info(f"Running {len(tasks)} collection tasks in parallel...")

    # Run all tasks concurrently with asyncio.gather
    names = list(tasks.keys())
    coros = list(tasks.values())
    gather_results = await asyncio.gather(*coros, return_exceptions=True)

    results = {}
    for name, result in zip(names, gather_results):
        if isinstance(result, Exception):
            logger.error(f"  Failed: {name} - {result}")
            results[name] = {"error": str(result)}
        elif isinstance(result, dict):
            results.update(result)
            logger.info(f"  Completed: {name}")
        else:
            results[name] = {"error": f"Unexpected result type: {type(result)}"}

    # Log each result as ProcessEvent
    for name in names:
        if name in results:
            log_collection_event(name, {name: results[name]})

    duration = (datetime.now() - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info(f"Collection completed in {duration:.1f} seconds")
    logger.info("=" * 60)

    successes = sum(1 for v in results.values() if not isinstance(v, dict) or "error" not in v)
    failures = len(results) - successes

    logger.info(f"Results: {successes} succeeded, {failures} failed")

    # Save collection log
    log_dir = Path.home() / "quant_results" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "collection_log.json"
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration,
        "quick_mode": quick,
        "task_count": len(tasks),
        "successes": successes,
        "failures": failures,
        "results": results,
    }

    existing_log = []
    if log_file.exists():
        try:
            with open(log_file) as f:
                existing_log = json.load(f)
        except (json.JSONDecodeError, ValueError):
            existing_log = []

    existing_log.append(log_entry)
    existing_log = existing_log[-100:]  # Keep last 100

    with open(log_file, "w") as f:
        json.dump(existing_log, f, indent=2, default=str)

    return results


def main():
    parser = argparse.ArgumentParser(description="Master data collection")
    parser.add_argument("--quick", action="store_true", help="Run essential collections only")
    args = parser.parse_args()

    results = asyncio.run(collect_all(quick=args.quick))

    # Print summary
    print(f"\nCollection Summary ({len(results)} sources):")
    print("-" * 40)
    for source, result in sorted(results.items()):
        if isinstance(result, dict) and "error" in result:
            print(f"  ✗ {source}: {result['error'][:60]}")
        else:
            print(f"  ✓ {source}")

    errors = {k: v["error"] for k, v in results.items() if isinstance(v, dict) and "error" in v}
    if errors:
        print(f"\n{len(errors)} errors encountered (see logs for details)")


if __name__ == "__main__":
    main()
