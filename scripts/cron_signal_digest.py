#!/usr/bin/env python3
"""Signal Digest Pipeline — unified signal processing with quality weighting.

Reads all signal sources, normalizes, applies quality weights + recency decay,
deduplicates, detects convergences, and writes a single digest file for the operator.

Replaces the operator's 5+ stale file reads with one pre-computed digest.

Usage:
    PYTHONPATH=. python3 scripts/cron_signal_digest.py

Output:
    ~/quant_results/scheduler/signal_digest.json
"""

import json
import logging
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [signal-digest] %(message)s")
logger = logging.getLogger(__name__)

RESULTS_DIR = Path.home() / "quant_results"
DIGEST_FILE = RESULTS_DIR / "scheduler" / "signal_digest.json"

# Source quality weights (from thesis_suggester + empirical tuning)
SOURCE_WEIGHTS = {
    "congressional": 1.4,
    "insider": 1.3,
    "statistical": 1.2,
    "agent": 1.1,
    "options_flow": 1.1,
    "news": 1.0,
    "prediction_market": 1.0,
    "wsb": 0.8,
    "stocktwits": 0.7,
    "social_sentiment": 0.7,
    "thesis_suggestion": 0.9,
}

# Recency half-life in hours (strength halves every this many hours)
RECENCY_HALF_LIFE = 12.0


def recency_decay(hours_old: float) -> float:
    """Exponential decay: strength *= 2^(-hours_old / half_life)."""
    return math.pow(2, -hours_old / RECENCY_HALF_LIFE)


def load_social_signals() -> list[dict]:
    """Load signals from latest_scan.json (WSB, Stocktwits, thesis suggestions)."""
    signals = []
    scan_file = RESULTS_DIR / "social" / "latest_scan.json"

    if not scan_file.exists():
        return signals

    try:
        with open(scan_file) as f:
            scan = json.load(f)

        scan_ts = scan.get("timestamp", datetime.now().isoformat())

        # WSB signals
        for sig in scan.get("wsb", {}).get("signals", []):
            symbol = sig.get("symbol", "")
            if not symbol:
                continue
            sentiment = sig.get("sentiment", 0)
            direction = "bullish" if sentiment > 0.1 else ("bearish" if sentiment < -0.1 else "neutral")
            if direction == "neutral":
                continue
            signals.append({
                "symbol": symbol,
                "direction": direction,
                "strength": min(abs(sentiment), 1.0),
                "source": "wsb",
                "timestamp": scan_ts,
                "detail": f"mentions={sig.get('mentions', 0)} phase={sig.get('phase', '')}",
            })

        # Thesis suggestions
        for sug in scan.get("suggestions", {}).get("suggestions", []):
            symbol = sug.get("symbol", "")
            if not symbol:
                continue
            signals.append({
                "symbol": symbol,
                "direction": sug.get("direction", "bullish"),
                "strength": sug.get("confidence", 0.5),
                "source": "thesis_suggestion",
                "timestamp": scan_ts,
                "detail": f"{sug.get('name', '')} ({sug.get('signal_count', 0)} signals)",
            })
    except Exception as e:
        logger.warning(f"Error loading social signals: {e}")

    return signals


def load_statistical_signals() -> list[dict]:
    """Load signals from signals.json (technical/statistical)."""
    signals = []
    sig_file = RESULTS_DIR / "live" / "research" / "signals.json"

    if not sig_file.exists():
        return signals

    try:
        with open(sig_file) as f:
            data = json.load(f)

        for symbol, sigs in data.items():
            ts = sigs.get("timestamp", datetime.now().isoformat())

            # Check key signal fields
            for sig_name in ["swing_signal", "intraday_signal", "ml_signal",
                             "congressional_signal", "insider_signal", "options_flow_signal"]:
                val = sigs.get(sig_name, 0)
                if abs(val) < 0.1:
                    continue

                # Map signal name to source
                if "congressional" in sig_name:
                    source = "congressional"
                elif "insider" in sig_name:
                    source = "insider"
                elif "options" in sig_name:
                    source = "options_flow"
                else:
                    source = "statistical"

                signals.append({
                    "symbol": symbol,
                    "direction": "bullish" if val > 0 else "bearish",
                    "strength": min(abs(val), 1.0),
                    "source": source,
                    "timestamp": ts,
                    "detail": f"{sig_name}={val:.3f}",
                })

            # Technical bias
            bias = sigs.get("technical_bias", "")
            if bias in ("bullish", "bearish"):
                signals.append({
                    "symbol": symbol,
                    "direction": bias,
                    "strength": 0.5,
                    "source": "statistical",
                    "timestamp": ts,
                    "detail": f"technical_bias={bias}",
                })
    except Exception as e:
        logger.warning(f"Error loading statistical signals: {e}")

    return signals


def load_alt_data_signals() -> list[dict]:
    """Load signals from alt_data.json (congressional, insider, options, sentiment)."""
    signals = []
    alt_file = RESULTS_DIR / "live" / "research" / "alt_data.json"

    if not alt_file.exists():
        return signals

    try:
        with open(alt_file) as f:
            data = json.load(f)

        ts = data.get("timestamp", datetime.now().isoformat())

        # Congressional clusters
        for cluster in data.get("congressional", {}).get("clusters", []):
            symbol = cluster.get("symbol", "")
            if symbol:
                signals.append({
                    "symbol": symbol,
                    "direction": "bullish",  # Congressional buying = bullish
                    "strength": 0.7,
                    "source": "congressional",
                    "timestamp": ts,
                    "detail": f"congressional cluster",
                })

        # Insider buys
        for buy in data.get("insider", {}).get("recent_buys", []):
            symbol = buy.get("symbol", "")
            if symbol:
                signals.append({
                    "symbol": symbol,
                    "direction": "bullish",
                    "strength": 0.6,
                    "source": "insider",
                    "timestamp": ts,
                    "detail": f"insider buying",
                })

        # Social sentiment trending
        for ticker in data.get("social_sentiment", {}).get("trending_tickers", []):
            symbol = ticker.get("symbol", "")
            if not symbol:
                continue
            sentiment = ticker.get("sentiment", "neutral")
            if sentiment in ("bullish", "bearish"):
                signals.append({
                    "symbol": symbol,
                    "direction": sentiment,
                    "strength": min(abs(ticker.get("sentiment_score", 0.5)), 1.0),
                    "source": "social_sentiment",
                    "timestamp": ts,
                    "detail": f"mentions={ticker.get('mentions', 0)}",
                })
    except Exception as e:
        logger.warning(f"Error loading alt data signals: {e}")

    return signals


def load_prediction_market_signals() -> list[dict]:
    """Load signals from prediction_markets.json."""
    signals = []
    pm_file = RESULTS_DIR / "social" / "prediction_markets.json"

    if not pm_file.exists():
        return signals

    try:
        with open(pm_file) as f:
            data = json.load(f)

        ts = data.get("timestamp", datetime.now().isoformat())

        for signal in data.get("signals", []):
            symbol = signal.get("symbol", "")
            if not symbol:
                continue
            signals.append({
                "symbol": symbol,
                "direction": signal.get("direction", "bullish"),
                "strength": signal.get("strength", 0.5),
                "source": "prediction_market",
                "timestamp": ts,
                "detail": signal.get("detail", ""),
            })
    except Exception as e:
        logger.warning(f"Error loading prediction market signals: {e}")

    return signals


def process_signals(raw_signals: list[dict]) -> list[dict]:
    """Apply quality weighting, recency decay, deduplication."""
    now = datetime.now()
    processed = []

    for sig in raw_signals:
        # Parse timestamp
        try:
            ts = datetime.fromisoformat(sig["timestamp"])
        except (ValueError, TypeError, KeyError):
            ts = now

        hours_old = max(0, (now - ts).total_seconds() / 3600)

        # Skip signals older than 48 hours
        if hours_old > 48:
            continue

        # Apply source quality weight
        source_weight = SOURCE_WEIGHTS.get(sig.get("source", ""), 1.0)

        # Apply recency decay
        decay = recency_decay(hours_old)

        # Weighted strength
        weighted = sig["strength"] * source_weight * decay

        processed.append({
            **sig,
            "hours_old": round(hours_old, 1),
            "source_weight": source_weight,
            "recency_decay": round(decay, 3),
            "weighted_strength": round(weighted, 4),
        })

    # Sort by weighted strength descending
    processed.sort(key=lambda s: s["weighted_strength"], reverse=True)

    # Deduplicate: same symbol + direction + source within 4h → keep strongest
    seen = {}
    deduped = []
    for sig in processed:
        key = (sig["symbol"], sig["direction"], sig["source"])
        if key in seen:
            # Keep the one already seen (it's stronger due to sorting)
            continue
        seen[key] = True
        deduped.append(sig)

    return deduped


def detect_convergences(signals: list[dict]) -> list[dict]:
    """Find symbols with 3+ sources aligned in same direction."""
    from collections import defaultdict

    # Group by symbol + direction
    groups = defaultdict(list)
    for sig in signals:
        key = (sig["symbol"], sig["direction"])
        groups[key].append(sig)

    convergences = []
    for (symbol, direction), sigs in groups.items():
        sources = list({s["source"] for s in sigs})
        if len(sources) >= 3:
            avg_strength = sum(s["weighted_strength"] for s in sigs) / len(sigs)
            convergences.append({
                "symbol": symbol,
                "direction": direction,
                "source_count": len(sources),
                "sources": sources,
                "avg_weighted_strength": round(avg_strength, 4),
                "signals": [
                    {"source": s["source"], "strength": s["weighted_strength"], "detail": s.get("detail", "")}
                    for s in sigs
                ],
            })

    # Sort by source count then avg strength
    convergences.sort(key=lambda c: (c["source_count"], c["avg_weighted_strength"]), reverse=True)
    return convergences


def get_market_regime() -> str:
    """Read current market regime from state.json."""
    state_file = RESULTS_DIR / "live" / "state.json"
    try:
        with open(state_file) as f:
            state = json.load(f)
        return state.get("market_regime", {}).get("regime", "unknown")
    except Exception:
        return "unknown"


def get_source_freshness(sources: dict[str, str]) -> dict:
    """Check how fresh each data source is."""
    now = datetime.now()
    freshness = {}

    files = {
        "social_scan": RESULTS_DIR / "social" / "latest_scan.json",
        "signals": RESULTS_DIR / "live" / "research" / "signals.json",
        "alt_data": RESULTS_DIR / "live" / "research" / "alt_data.json",
        "prediction_markets": RESULTS_DIR / "social" / "prediction_markets.json",
        "state": RESULTS_DIR / "live" / "state.json",
    }

    for name, path in files.items():
        if path.exists():
            age_hours = (now.timestamp() - path.stat().st_mtime) / 3600
            freshness[name] = {
                "exists": True,
                "age_hours": round(age_hours, 1),
                "status": "fresh" if age_hours < 1 else ("ok" if age_hours < 4 else "stale"),
            }
        else:
            freshness[name] = {"exists": False, "status": "missing"}

    return freshness


def main():
    logger.info("Building signal digest...")

    # Load from all sources
    social = load_social_signals()
    statistical = load_statistical_signals()
    alt_data = load_alt_data_signals()
    prediction = load_prediction_market_signals()

    raw_total = len(social) + len(statistical) + len(alt_data) + len(prediction)
    logger.info(
        f"Raw signals: {len(social)} social, {len(statistical)} statistical, "
        f"{len(alt_data)} alt-data, {len(prediction)} prediction = {raw_total} total"
    )

    # Process: weight, decay, deduplicate
    all_signals = social + statistical + alt_data + prediction
    processed = process_signals(all_signals)
    logger.info(f"After processing: {len(processed)} signals (from {raw_total} raw)")

    # Detect convergences
    convergences = detect_convergences(processed)
    logger.info(f"Convergences detected: {len(convergences)}")

    # Get context
    regime = get_market_regime()
    freshness = get_source_freshness({})

    # Write digest
    digest = {
        "timestamp": datetime.now().isoformat(),
        "signal_count": len(processed),
        "convergence_count": len(convergences),
        "regime": regime,
        "signals": processed[:50],  # Top 50 by weighted strength
        "convergences": convergences,
        "source_counts": {
            source: len([s for s in processed if s["source"] == source])
            for source in set(s["source"] for s in processed)
        },
        "digest_sources": freshness,
    }

    DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DIGEST_FILE, "w") as f:
        json.dump(digest, f, indent=2)

    logger.info(f"Wrote digest: {DIGEST_FILE} ({len(processed)} signals, {len(convergences)} convergences)")

    # Log to ProcessEvent
    try:
        from src.autonomy.provenance import log_event

        log_event(
            "signal_digest_updated",
            source="cron:signal_digest",
            title=f"Signal digest: {len(processed)} signals, {len(convergences)} convergences, regime={regime}",
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
