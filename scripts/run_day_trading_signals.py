#!/usr/bin/env python3
"""
Day Trading Signal Scanner & Paper Trading Deployment

Scans watchlist for validated signals and optionally deploys to paper trading.

Features:
- Scans validated signals (Bollinger, RSI, Stochastic, Volume Fade, etc.)
- Detects signal convergences (3+ aligned = high confidence)
- Generates intraday features (VWAP, ORB, candle patterns)
- Deploys qualifying signals to paper trading
- Archives signals for future validation

Usage:
    # Scan only
    python3 scripts/run_day_trading_signals.py --scan

    # Scan and deploy convergences to paper trading
    python3 scripts/run_day_trading_signals.py --deploy-paper

    # Continuous monitoring mode
    python3 scripts/run_day_trading_signals.py --monitor --interval 5

    # Specific symbols
    python3 scripts/run_day_trading_signals.py --symbols AAPL,NVDA,TSLA
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.live_signal_generator import (
    LiveSignalGenerator,
    LiveSignal,
    SignalConvergence,
    SignalDirection,
    get_signal_summary,
)
from src.data.intraday.candle_analysis import CandleInterpreter, CandlePatternRecognizer
from src.data.intraday.feature_engine import IntradayFeatureEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Default watchlist
DEFAULT_WATCHLIST = [
    # Major indices ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Sector ETFs
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLB", "XLY",
    # Mega caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Financials
    "JPM", "BAC", "GS",
    # Energy
    "XOM", "CVX", "SLB",
    # Commodities
    "GLD", "SLV", "GDX",
]


class DayTradingScanner:
    """
    Scans for day trading signals and manages paper trading deployment.
    """

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.signal_archive_dir = self.results_dir / "signal_archive" / "intraday"
        self.signal_archive_dir.mkdir(parents=True, exist_ok=True)

        self.signal_generator = LiveSignalGenerator()
        self.candle_interpreter = CandleInterpreter()
        self.feature_engine = IntradayFeatureEngine()

    def get_price_data(self, symbol: str, period: str = "3mo") -> Optional[pd.DataFrame]:
        """Fetch price data for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty:
                return None
            # Remove timezone info
            df.index = df.index.tz_localize(None)
            return df
        except Exception as e:
            logger.warning(f"Error fetching {symbol}: {e}")
            return None

    def get_intraday_data(self, symbol: str, period: str = "1d", interval: str = "1m") -> Optional[pd.DataFrame]:
        """Fetch intraday data for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return None
            df.index = df.index.tz_localize(None)
            return df
        except Exception as e:
            logger.warning(f"Error fetching intraday {symbol}: {e}")
            return None

    def scan_symbol(self, symbol: str) -> dict:
        """
        Scan a single symbol for all signals and features.
        """
        result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "signals": [],
            "convergence": None,
            "candle_interpretation": None,
            "intraday_features": None,
            "error": None,
        }

        # Get daily data for swing signals
        daily_df = self.get_price_data(symbol)
        if daily_df is None or len(daily_df) < 25:
            result["error"] = "Insufficient daily data"
            return result

        # Generate validated signals
        signals = self.signal_generator.generate_all_signals(daily_df, symbol)
        result["signals"] = [s.to_dict() for s in signals]

        # Check for convergence
        convergence = self.signal_generator.detect_convergence(signals)
        if convergence:
            result["convergence"] = {
                "direction": convergence.direction.value,
                "score": convergence.convergence_score,
                "confidence": convergence.combined_confidence,
                "summary": convergence.summary,
                "recommendation": convergence.recommendation,
            }

        # Get intraday data for candle analysis
        intraday_df = self.get_intraday_data(symbol)
        if intraday_df is not None and len(intraday_df) > 10:
            # Candle interpretation
            try:
                interp = self.candle_interpreter.interpret_price_action(
                    intraday_df, symbol, "1min"
                )
                result["candle_interpretation"] = {
                    "candle_type": interp.candle_type,
                    "price_action": interp.price_action,
                    "agent_summary": interp.agent_summary,
                    "suggested_bias": interp.suggested_bias.value,
                    "confidence": interp.confidence_level,
                    "patterns": [p.pattern.value for p in interp.patterns_detected],
                }
            except Exception as e:
                logger.debug(f"Candle interpretation error for {symbol}: {e}")

            # Intraday features
            try:
                features = self.feature_engine.calculate_features(
                    intraday_df, symbol, "1min",
                    previous_close=float(daily_df['Close'].iloc[-2]) if len(daily_df) >= 2 else None
                )
                result["intraday_features"] = {
                    "session": features.session.value,
                    "vwap_distance": features.vwap.distance_from_vwap,
                    "vwap_band": features.vwap.band_position,
                    "or_signal": features.opening_range.signal.value,
                    "trading_bias": features.trading_bias,
                    "relative_volume": features.relative_volume,
                    "summary": features.summary,
                }
            except Exception as e:
                logger.debug(f"Intraday features error for {symbol}: {e}")

        return result

    def scan_watchlist(self, symbols: list[str]) -> dict:
        """
        Scan entire watchlist for signals.
        """
        results = {
            "scan_time": datetime.now().isoformat(),
            "symbols_scanned": len(symbols),
            "total_signals": 0,
            "convergences": [],
            "by_symbol": {},
            "summary": {},
        }

        all_signals = []

        for symbol in symbols:
            logger.info(f"Scanning {symbol}...")
            try:
                scan_result = self.scan_symbol(symbol)
                results["by_symbol"][symbol] = scan_result

                # Collect signals
                if scan_result["signals"]:
                    all_signals.extend(scan_result["signals"])
                    results["total_signals"] += len(scan_result["signals"])

                # Collect convergences
                if scan_result["convergence"]:
                    results["convergences"].append({
                        "symbol": symbol,
                        **scan_result["convergence"]
                    })

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                results["by_symbol"][symbol] = {"error": str(e)}

        # Generate summary
        bullish_signals = [s for s in all_signals if s.get("direction") == "bullish"]
        bearish_signals = [s for s in all_signals if s.get("direction") == "bearish"]

        results["summary"] = {
            "total_signals": len(all_signals),
            "bullish_count": len(bullish_signals),
            "bearish_count": len(bearish_signals),
            "convergence_count": len(results["convergences"]),
            "top_bullish": self._get_top_signals(bullish_signals, 5),
            "top_bearish": self._get_top_signals(bearish_signals, 5),
        }

        return results

    def _get_top_signals(self, signals: list[dict], n: int) -> list[dict]:
        """Get top N signals by IC and hit rate."""
        sorted_signals = sorted(
            signals,
            key=lambda s: (s.get("convergence_score", 1), s.get("historical_ic", 0)),
            reverse=True
        )
        return sorted_signals[:n]

    def archive_signals(self, results: dict):
        """Archive scan results for future validation."""
        timestamp = datetime.now()
        archive_file = self.signal_archive_dir / f"signals_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"

        with open(archive_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Signals archived to: {archive_file}")
        return archive_file

    async def deploy_to_paper(self, results: dict, min_convergence: int = 3) -> list[dict]:
        """
        Deploy qualifying signals to paper trading.

        Only deploys:
        - Convergence signals (3+ aligned)
        - Strong individual signals with IC > 0.3
        """
        deployments = []

        # Deploy convergences
        for conv in results.get("convergences", []):
            if conv.get("score", 0) >= min_convergence:
                deployment = await self._create_paper_trade(
                    symbol=conv["symbol"],
                    direction=conv["direction"],
                    reason=conv["summary"],
                    confidence=conv["confidence"],
                    source="convergence"
                )
                if deployment:
                    deployments.append(deployment)

        # Deploy strong individual signals
        for symbol, scan in results.get("by_symbol", {}).items():
            for signal in scan.get("signals", []):
                # Only deploy strong signals without convergence
                if (signal.get("historical_ic", 0) >= 0.3 and
                    signal.get("convergence_score", 1) == 1):  # Not already in convergence
                    deployment = await self._create_paper_trade(
                        symbol=symbol,
                        direction=signal["direction"],
                        reason=signal["description"],
                        confidence=signal["historical_hit_rate"],
                        source=signal["signal_type"]
                    )
                    if deployment:
                        deployments.append(deployment)

        return deployments

    async def _create_paper_trade(
        self,
        symbol: str,
        direction: str,
        reason: str,
        confidence: float,
        source: str
    ) -> Optional[dict]:
        """Create a paper trade from signal."""
        try:
            # Get current price
            df = self.get_price_data(symbol, period="5d")
            if df is None:
                return None

            current_price = float(df['Close'].iloc[-1])

            # Calculate position size based on confidence
            base_size_pct = 5.0  # 5% base
            if confidence > 0.7:
                size_pct = min(10.0, base_size_pct * 1.5)
            elif confidence > 0.6:
                size_pct = base_size_pct
            else:
                size_pct = base_size_pct * 0.7

            # Create paper trade record
            trade = {
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "direction": direction,
                "action": "BUY" if direction == "bullish" else "SELL",
                "price": current_price,
                "size_pct": size_pct,
                "confidence": confidence,
                "source": source,
                "reason": reason,
                "status": "pending",
            }

            # Log the trade
            logger.info(f"Paper trade created: {direction.upper()} {symbol} @ ${current_price:.2f}")

            # Save to paper trades file
            paper_trades_file = self.results_dir / "paper_trades" / "day_trading_signals.jsonl"
            paper_trades_file.parent.mkdir(parents=True, exist_ok=True)

            with open(paper_trades_file, 'a') as f:
                f.write(json.dumps(trade) + "\n")

            return trade

        except Exception as e:
            logger.error(f"Error creating paper trade for {symbol}: {e}")
            return None


def print_scan_results(results: dict):
    """Print formatted scan results."""
    print("\n" + "=" * 70)
    print("DAY TRADING SIGNAL SCAN RESULTS")
    print("=" * 70)
    print(f"\nScan Time: {results['scan_time']}")
    print(f"Symbols Scanned: {results['symbols_scanned']}")
    print(f"Total Signals: {results['total_signals']}")

    summary = results.get("summary", {})

    # Convergences (highest priority)
    if results.get("convergences"):
        print("\n" + "-" * 70)
        print("🎯 HIGH CONFIDENCE CONVERGENCES")
        print("-" * 70)
        for conv in results["convergences"]:
            print(f"\n  {conv['symbol']} - {conv['direction'].upper()}")
            print(f"  Score: {conv['score']} signals aligned")
            print(f"  Confidence: {conv['confidence']:.0%}")
            print(f"  {conv['summary']}")
            print(f"  → {conv['recommendation']}")

    # Summary
    print("\n" + "-" * 70)
    print("SIGNAL SUMMARY")
    print("-" * 70)
    print(f"  Bullish Signals: {summary.get('bullish_count', 0)}")
    print(f"  Bearish Signals: {summary.get('bearish_count', 0)}")
    print(f"  Convergences: {summary.get('convergence_count', 0)}")

    # Top signals
    if summary.get("top_bullish"):
        print("\n  Top Bullish:")
        for s in summary["top_bullish"][:3]:
            print(f"    {s.get('symbol', 'N/A')}: {s.get('signal_type', 'N/A')} (IC={s.get('historical_ic', 0):.2f})")

    if summary.get("top_bearish"):
        print("\n  Top Bearish:")
        for s in summary["top_bearish"][:3]:
            print(f"    {s.get('symbol', 'N/A')}: {s.get('signal_type', 'N/A')} (IC={s.get('historical_ic', 0):.2f})")

    # Individual symbol details (brief)
    print("\n" + "-" * 70)
    print("SYMBOL DETAILS")
    print("-" * 70)

    for symbol, scan in results.get("by_symbol", {}).items():
        if scan.get("error"):
            continue

        signals = scan.get("signals", [])
        if not signals:
            continue

        bullish = [s for s in signals if s.get("direction") == "bullish"]
        bearish = [s for s in signals if s.get("direction") == "bearish"]

        intraday = scan.get("intraday_features", {})
        bias = intraday.get("trading_bias", "neutral")

        signal_str = ""
        if bullish:
            signal_str += f"↑{len(bullish)} "
        if bearish:
            signal_str += f"↓{len(bearish)}"

        print(f"  {symbol}: {signal_str.strip()} | Intraday: {bias}")

    print("\n" + "=" * 70)


async def main():
    parser = argparse.ArgumentParser(description="Day Trading Signal Scanner")
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan watchlist for signals"
    )
    parser.add_argument(
        "--deploy-paper",
        action="store_true",
        help="Deploy qualifying signals to paper trading"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Continuous monitoring mode"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Monitoring interval in minutes (default: 5)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to scan"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    # Default to scan if no action specified
    if not (args.scan or args.deploy_paper or args.monitor):
        args.scan = True

    # Parse symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = DEFAULT_WATCHLIST

    scanner = DayTradingScanner()

    if args.monitor:
        # Continuous monitoring mode
        print(f"Starting continuous monitoring (interval: {args.interval}min)")
        print("Press Ctrl+C to stop\n")

        while True:
            try:
                results = scanner.scan_watchlist(symbols)

                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_scan_results(results)

                # Archive signals
                scanner.archive_signals(results)

                # Deploy if requested
                if args.deploy_paper and results.get("convergences"):
                    deployments = await scanner.deploy_to_paper(results)
                    if deployments:
                        print(f"\n📝 Deployed {len(deployments)} paper trades")

                # Wait for next scan
                print(f"\nNext scan in {args.interval} minutes...")
                await asyncio.sleep(args.interval * 60)

            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
                break

    else:
        # Single scan
        results = scanner.scan_watchlist(symbols)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_scan_results(results)

        # Archive signals
        archive_file = scanner.archive_signals(results)

        # Deploy if requested
        if args.deploy_paper:
            deployments = await scanner.deploy_to_paper(results)
            if deployments:
                print(f"\n📝 Created {len(deployments)} paper trades")
                for d in deployments:
                    print(f"  {d['action']} {d['symbol']} @ ${d['price']:.2f} ({d['source']})")
            else:
                print("\nNo qualifying signals for paper trading")


if __name__ == "__main__":
    asyncio.run(main())
