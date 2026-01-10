#!/usr/bin/env python3
"""Research Prep Script - Pre-compute everything Claude needs.

Runs before market open to generate files Claude can read directly
instead of executing pipelines.

Output: ~/quant_results/live/research/
- features.json: Feature matrix for universe
- signals.json: Strategy signals for all symbols
- alt_data.json: Alternative data summary
- screens.json: Pre-computed stock screens

Usage:
    PYTHONPATH=. python scripts/research_prep.py
    PYTHONPATH=. python scripts/research_prep.py --watchlist SPY,QQQ,AAPL
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Default watchlist
DEFAULT_WATCHLIST = [
    # Indices
    "SPY", "QQQ", "IWM", "DIA",
    # Tech
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "AMZN", "TSLA",
    # Energy
    "XLE", "SLB", "HAL", "OXY", "XOM", "CVX",
    # Financials
    "XLF", "JPM", "BAC", "GS",
    # Other sectors
    "XLK", "XLV", "XLI", "XLY", "XLP", "XLU",
]


def compute_features_for_universe(
    symbols: list[str],
) -> dict[str, dict]:
    """
    Compute features for all symbols.

    Args:
        symbols: List of symbols

    Returns:
        Dict mapping symbol to feature dict.
    """
    results = {}

    try:
        from src.data.features import FeatureEngine
        import yfinance as yf

        for symbol in symbols:
            try:
                # Get historical data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="3mo")

                if hist.empty:
                    logger.warning(f"No data for {symbol}")
                    continue

                # Compute features
                features = FeatureEngine.compute_all_features(hist)

                # Get latest values
                if not features.empty:
                    latest = features.iloc[-1].to_dict()
                    results[symbol] = {
                        "timestamp": datetime.now().isoformat(),
                        "features": {k: float(v) if not isinstance(v, str) else v
                                    for k, v in latest.items() if v == v}  # Filter NaN
                    }

            except Exception as e:
                logger.warning(f"Failed to compute features for {symbol}: {e}")

    except ImportError as e:
        logger.error(f"Feature engine not available: {e}")

    return results


def run_all_strategies(symbols: list[str]) -> dict[str, dict]:
    """
    Run all strategies on symbols.

    Args:
        symbols: List of symbols

    Returns:
        Dict mapping symbol to signals dict.
    """
    results = {}

    # Try to import strategy modules
    try:
        # Placeholder - would integrate with actual strategies
        # from src.strategies.swing.bollinger_reversal import BollingerReversalStrategy

        for symbol in symbols:
            results[symbol] = {
                "timestamp": datetime.now().isoformat(),
                "swing_signal": 0.0,  # -1 to 1
                "intraday_signal": 0.0,
                "ml_signal": 0.0,
                "notes": "Strategy signals not yet implemented",
            }

    except ImportError as e:
        logger.warning(f"Strategy modules not available: {e}")

    return results


async def aggregate_alt_data(symbols: list[str]) -> dict:
    """
    Aggregate alternative data for symbols.

    Args:
        symbols: List of symbols

    Returns:
        Dict with alt data summary.
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "congressional": {},
        "insider": {},
        "options_flow": {},
        "social_sentiment": {},
    }

    # Congressional trading
    try:
        from src.data.sources.alternative.congressional_trades import (
            find_congressional_clusters,
        )
        clusters = await find_congressional_clusters(min_traders=2)
        result["congressional"] = {
            "clusters": [c.__dict__ if hasattr(c, '__dict__') else str(c) for c in clusters[:10]],
            "symbols_with_activity": [c.symbol for c in clusters if hasattr(c, 'symbol')][:20],
        }
    except Exception as e:
        logger.debug(f"Congressional data unavailable: {e}")

    # Insider trading
    try:
        from src.data.sources.alternative.insider import get_recent_insider_buys
        insider_buys = await get_recent_insider_buys(days=7)
        result["insider"] = {
            "recent_buys": insider_buys[:20] if insider_buys else [],
            "symbols_with_buying": list(set(b.get("symbol") for b in insider_buys if b.get("symbol")))[:20],
        }
    except Exception as e:
        logger.debug(f"Insider data unavailable: {e}")

    # Options flow
    try:
        from src.data.sources.alternative.options_flow import get_unusual_activity
        unusual = await get_unusual_activity()
        result["options_flow"] = {
            "unusual_activity": unusual[:20] if unusual else [],
            "bullish_flow": [u for u in (unusual or []) if u.get("direction") == "bullish"][:10],
            "bearish_flow": [u for u in (unusual or []) if u.get("direction") == "bearish"][:10],
        }
    except Exception as e:
        logger.debug(f"Options flow unavailable: {e}")

    # Social sentiment
    try:
        from src.data.sources.realtime.social_sentiment import WallStreetBetsScraper
        scraper = WallStreetBetsScraper()
        trending = await scraper.get_trending_tickers()
        result["social_sentiment"] = {
            "trending_tickers": [t.to_dict() for t in trending[:15]],
            "overall_sentiment": "bullish" if trending and sum(t.sentiment_score for t in trending[:10]) > 0 else "neutral",
        }
        await scraper.close()
    except Exception as e:
        logger.debug(f"Social sentiment unavailable: {e}")

    return result


def get_screens() -> dict[str, list[str]]:
    """
    Generate pre-computed stock screens.

    Returns:
        Dict mapping screen name to list of symbols.
    """
    screens = {
        "momentum_leaders": [],
        "value_stocks": [],
        "unusual_volume": [],
        "insider_buying": [],
        "oversold": [],
        "overbought": [],
        "near_52w_high": [],
        "near_52w_low": [],
    }

    try:
        import yfinance as yf

        # Sample universe for screening
        universe = DEFAULT_WATCHLIST[:20]

        for symbol in universe:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1mo")

                if hist.empty:
                    continue

                # Calculate metrics
                current = hist["Close"].iloc[-1]
                high_52w = hist["Close"].max()
                low_52w = hist["Close"].min()
                avg_vol = hist["Volume"].mean()
                recent_vol = hist["Volume"].iloc[-1]

                # Calculate RSI (simplified)
                delta = hist["Close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 50

                # Apply screens
                if rsi > 70:
                    screens["overbought"].append(symbol)
                if rsi < 30:
                    screens["oversold"].append(symbol)
                if current > high_52w * 0.95:
                    screens["near_52w_high"].append(symbol)
                if current < low_52w * 1.05:
                    screens["near_52w_low"].append(symbol)
                if recent_vol > avg_vol * 1.5:
                    screens["unusual_volume"].append(symbol)

                # Momentum: up >5% in last 5 days
                if len(hist) >= 5:
                    five_day_return = (current / hist["Close"].iloc[-5] - 1) * 100
                    if five_day_return > 5:
                        screens["momentum_leaders"].append(symbol)

            except Exception as e:
                logger.debug(f"Screening failed for {symbol}: {e}")

    except ImportError:
        logger.warning("yfinance not available for screening")

    # Add metadata
    return {
        "timestamp": datetime.now().isoformat(),
        "screens": screens,
    }


async def generate_research_files(
    watchlist: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Generate all pre-computed research files.

    Args:
        watchlist: Symbols to compute for
        output_dir: Output directory

    Returns:
        Summary of generated files.
    """
    watchlist = watchlist or DEFAULT_WATCHLIST
    output_dir = output_dir or paths.live_research
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "watchlist": watchlist,
        "files_generated": [],
    }

    # 1. Features
    logger.info("Computing features...")
    features = compute_features_for_universe(watchlist)
    features_file = output_dir / "features.json"
    with open(features_file, "w") as f:
        json.dump(features, f, indent=2)
    summary["files_generated"].append(str(features_file))
    logger.info(f"  Wrote {features_file} ({len(features)} symbols)")

    # 2. Signals
    logger.info("Computing signals...")
    signals = run_all_strategies(watchlist)
    signals_file = output_dir / "signals.json"
    with open(signals_file, "w") as f:
        json.dump(signals, f, indent=2)
    summary["files_generated"].append(str(signals_file))
    logger.info(f"  Wrote {signals_file} ({len(signals)} symbols)")

    # 3. Alt data
    logger.info("Aggregating alternative data...")
    alt_data = await aggregate_alt_data(watchlist)
    alt_data_file = output_dir / "alt_data.json"
    with open(alt_data_file, "w") as f:
        json.dump(alt_data, f, indent=2)
    summary["files_generated"].append(str(alt_data_file))
    logger.info(f"  Wrote {alt_data_file}")

    # 4. Screens
    logger.info("Running screens...")
    screens = get_screens()
    screens_file = output_dir / "screens.json"
    with open(screens_file, "w") as f:
        json.dump(screens, f, indent=2)
    summary["files_generated"].append(str(screens_file))
    logger.info(f"  Wrote {screens_file}")

    # Save summary
    summary_file = output_dir / "prep_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Research Prep - Pre-compute data for Claude")
    parser.add_argument(
        "--watchlist",
        type=str,
        help="Comma-separated list of symbols",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    watchlist = args.watchlist.split(",") if args.watchlist else None
    output_dir = Path(args.output) if args.output else None

    logger.info("=" * 50)
    logger.info("Research Prep - Pre-computing data for Claude")
    logger.info("=" * 50)

    summary = await generate_research_files(watchlist, output_dir)

    logger.info("")
    logger.info("=" * 50)
    logger.info("COMPLETE")
    logger.info(f"Generated {len(summary['files_generated'])} files")
    logger.info(f"Output: {paths.live_research}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
