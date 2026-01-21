#!/usr/bin/env python3
"""
Daily Signal Archiver

Archives all alternative data signals daily for future backtesting validation.
Run this via cron at 5:30 PM ET after market close.

Creates timestamped archives in:
    ~/quant_results/signal_archive/YYYY/MM/DD/

Each archive contains:
- Market regime signals (VIX, breadth, put/call)
- Sentiment signals (AAII, newsletter, expert)
- Institutional signals (congressional, insider, options flow)
- Technical signals (screen results, squeeze candidates)
- Macro signals (COT, fed futures, economic calendar)

Usage:
    python3 scripts/archive_daily_signals.py
    python3 scripts/archive_daily_signals.py --date 2026-01-15  # Specific date
    python3 scripts/archive_daily_signals.py --dry-run  # Preview without saving
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class DailySignalArchive:
    """Complete daily signal snapshot for backtesting."""
    archive_date: str
    archive_timestamp: str

    # Market regime
    market_regime: dict = field(default_factory=dict)

    # VIX and volatility
    vix_data: dict = field(default_factory=dict)

    # Market breadth
    breadth_data: dict = field(default_factory=dict)

    # Put/call ratio
    put_call_data: dict = field(default_factory=dict)

    # Sentiment
    aaii_sentiment: dict = field(default_factory=dict)
    newsletter_sentiment: dict = field(default_factory=dict)
    expert_sentiment: list = field(default_factory=list)

    # Institutional
    congressional_trades: list = field(default_factory=list)
    insider_trades: list = field(default_factory=list)
    options_flow: list = field(default_factory=list)

    # COT report
    cot_data: dict = field(default_factory=dict)

    # Economic calendar
    economic_events: list = field(default_factory=list)
    fed_expectations: dict = field(default_factory=dict)

    # Screens and candidates
    finviz_screens: dict = field(default_factory=dict)
    squeeze_candidates: list = field(default_factory=list)

    # Technical signals for watchlist
    technical_signals: dict = field(default_factory=dict)

    # Data quality
    collection_stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)


class DailySignalArchiver:
    """Archives daily signals for future backtesting."""

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.archive_dir = self.results_dir / "signal_archive"

    def _get_archive_path(self, archive_date: date) -> Path:
        """Get archive file path for a date."""
        return (
            self.archive_dir
            / str(archive_date.year)
            / f"{archive_date.month:02d}"
            / f"{archive_date.day:02d}"
            / "signals.json"
        )

    async def collect_vix_data(self) -> dict:
        """Collect VIX term structure data."""
        try:
            from src.data.sources.alternative.vix_structure import get_vix_structure, get_vix_signal

            structure = await get_vix_structure()
            signal = get_vix_signal(structure)

            return {
                "vix_spot": structure.vix_spot if structure else None,
                "vix_1m": structure.vix_1m if structure else None,
                "vix_3m": structure.vix_3m if structure else None,
                "slope": structure.slope if structure else None,
                "structure": structure.structure if structure else None,
                "signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting VIX data: {e}")
            return {"error": str(e)}

    async def collect_breadth_data(self) -> dict:
        """Collect market breadth data."""
        try:
            from src.data.pipeline.market_breadth import MarketBreadthAnalyzer

            analyzer = MarketBreadthAnalyzer()
            breadth = await analyzer.get_current_breadth()

            return {
                "advancing": breadth.get("advancing", 0),
                "declining": breadth.get("declining", 0),
                "pct_advancing": breadth.get("pct_advancing", 0),
                "adv_dec_ratio": breadth.get("adv_dec_ratio", 1),
                "pct_above_50ma": breadth.get("pct_above_50ma"),
                "pct_above_200ma": breadth.get("pct_above_200ma"),
                "breadth_thrust": breadth.get("breadth_thrust"),
                "signal": breadth.get("signal", "neutral"),
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting breadth data: {e}")
            return {"error": str(e)}

    async def collect_put_call_data(self) -> dict:
        """Collect put/call ratio data."""
        try:
            from src.data.sources.alternative.put_call import get_put_call_data, get_put_call_signal

            pc_data = await get_put_call_data()
            signal = get_put_call_signal(pc_data)

            return {
                "equity_pc_ratio": pc_data.equity_pc_ratio if pc_data else None,
                "index_pc_ratio": pc_data.index_pc_ratio if pc_data else None,
                "total_pc_ratio": pc_data.total_pc_ratio if pc_data else None,
                "signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting put/call data: {e}")
            return {"error": str(e)}

    async def collect_aaii_sentiment(self) -> dict:
        """Collect AAII sentiment survey data."""
        try:
            from src.data.sources.alternative.aaii_sentiment import get_aaii_sentiment, get_aaii_signal

            sentiment = await get_aaii_sentiment()
            signal = get_aaii_signal(sentiment)

            return {
                "bullish": sentiment.bullish if sentiment else None,
                "neutral": sentiment.neutral if sentiment else None,
                "bearish": sentiment.bearish if sentiment else None,
                "bull_bear_spread": sentiment.bull_bear_spread if sentiment else None,
                "survey_date": sentiment.survey_date.isoformat() if sentiment and sentiment.survey_date else None,
                "signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting AAII sentiment: {e}")
            return {"error": str(e)}

    async def collect_newsletter_sentiment(self) -> dict:
        """Collect newsletter sentiment data."""
        try:
            from src.data.sources.alternative.newsletter_sentiment import get_newsletter_sentiment, get_newsletter_signal

            sentiment = await get_newsletter_sentiment()
            signal = get_newsletter_signal(sentiment)

            return {
                "bulls": sentiment.bulls if sentiment else None,
                "bears": sentiment.bears if sentiment else None,
                "correction": sentiment.correction if sentiment else None,
                "bull_bear_spread": sentiment.bull_bear_spread if sentiment else None,
                "signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting newsletter sentiment: {e}")
            return {"error": str(e)}

    async def collect_expert_sentiment(self) -> list:
        """Collect expert sentiment (Cramer, etc.)."""
        try:
            from src.data.sources.alternative.expert_sentiment import fetch_expert_calls

            calls = await fetch_expert_calls(days_back=7)

            return [
                {
                    "expert": call.expert.value if hasattr(call.expert, 'value') else str(call.expert),
                    "symbol": call.symbol,
                    "action": call.action.value if hasattr(call.action, 'value') else str(call.action),
                    "sentiment": call.sentiment.value if hasattr(call.sentiment, 'value') else str(call.sentiment),
                    "date": call.date.isoformat() if call.date else None,
                    "context": call.context,
                }
                for call in calls[:50]  # Limit to 50 most recent
            ]
        except Exception as e:
            logger.warning(f"Error collecting expert sentiment: {e}")
            return []

    async def collect_congressional_trades(self) -> list:
        """Collect congressional trading data."""
        try:
            from src.data.sources.alternative.congressional_trades import fetch_congressional_trades

            trades = await fetch_congressional_trades(days_back=30)

            return [
                {
                    "politician": trade.politician,
                    "chamber": trade.chamber.value if hasattr(trade.chamber, 'value') else str(trade.chamber),
                    "symbol": trade.symbol,
                    "trade_type": trade.trade_type.value if hasattr(trade.trade_type, 'value') else str(trade.trade_type),
                    "amount_low": trade.amount_low,
                    "amount_high": trade.amount_high,
                    "trade_date": trade.trade_date.isoformat() if trade.trade_date else None,
                    "disclosure_date": trade.disclosure_date.isoformat() if trade.disclosure_date else None,
                }
                for trade in trades[:100]  # Limit to 100 most recent
            ]
        except Exception as e:
            logger.warning(f"Error collecting congressional trades: {e}")
            return []

    async def collect_insider_trades(self) -> list:
        """Collect insider trading (Form 4) data."""
        try:
            from src.data.sources.alternative.insider import fetch_insider_summary

            # Get insider activity for major symbols
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "JNJ"]
            all_trades = []

            for symbol in symbols:
                try:
                    summary = await fetch_insider_summary(symbol, days_back=30)
                    if summary and summary.recent_transactions:
                        for tx in summary.recent_transactions[:5]:
                            all_trades.append({
                                "symbol": symbol,
                                "insider_name": tx.insider_name,
                                "role": tx.role.value if hasattr(tx.role, 'value') else str(tx.role),
                                "transaction_type": tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type),
                                "shares": tx.shares,
                                "price": tx.price,
                                "value": tx.value,
                                "date": tx.date.isoformat() if tx.date else None,
                            })
                except Exception:
                    continue

            return all_trades
        except Exception as e:
            logger.warning(f"Error collecting insider trades: {e}")
            return []

    async def collect_options_flow(self) -> list:
        """Collect unusual options flow data."""
        try:
            from src.data.sources.alternative.options_flow import fetch_unusual_options

            unusual = await fetch_unusual_options()

            return [
                {
                    "symbol": opt.symbol,
                    "contract_type": opt.option_type.value if hasattr(opt.option_type, 'value') else str(opt.option_type),
                    "strike": opt.strike,
                    "expiry": opt.expiry.isoformat() if opt.expiry else None,
                    "volume": opt.volume,
                    "open_interest": opt.open_interest,
                    "premium": opt.premium,
                    "activity_type": opt.activity_type.value if hasattr(opt.activity_type, 'value') else str(opt.activity_type),
                }
                for opt in unusual[:50]  # Limit to 50 most unusual
            ]
        except Exception as e:
            logger.warning(f"Error collecting options flow: {e}")
            return []

    async def collect_cot_data(self) -> dict:
        """Collect Commitment of Traders data."""
        try:
            from src.data.sources.alternative.cot_report import get_cot_report, get_equity_cot_signal

            report = await get_cot_report()
            signal = get_equity_cot_signal(report)

            positions = {}
            if report and report.positions:
                for contract, pos in report.positions.items():
                    positions[contract] = {
                        "commercial_long": pos.commercial_long,
                        "commercial_short": pos.commercial_short,
                        "commercial_net": pos.commercial_net,
                        "non_commercial_long": pos.non_commercial_long,
                        "non_commercial_short": pos.non_commercial_short,
                        "non_commercial_net": pos.non_commercial_net,
                    }

            return {
                "report_date": report.report_date.isoformat() if report and report.report_date else None,
                "positions": positions,
                "equity_signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting COT data: {e}")
            return {"error": str(e)}

    async def collect_economic_events(self) -> list:
        """Collect upcoming economic calendar events."""
        try:
            from src.data.sources.alternative.economic_calendar import get_economic_calendar

            calendar = await get_economic_calendar(days_ahead=7)

            return [
                {
                    "name": event.name,
                    "date": event.date.isoformat() if event.date else None,
                    "time": event.time,
                    "importance": event.importance.value if hasattr(event.importance, 'value') else str(event.importance),
                    "category": event.category.value if hasattr(event.category, 'value') else str(event.category),
                    "previous": event.previous,
                    "forecast": event.forecast,
                }
                for event in (calendar.events if calendar else [])[:50]
            ]
        except Exception as e:
            logger.warning(f"Error collecting economic events: {e}")
            return []

    async def collect_fed_expectations(self) -> dict:
        """Collect Fed rate expectations."""
        try:
            from src.data.sources.alternative.fed_futures import get_fed_expectations, get_rate_path_signal

            expectations = await get_fed_expectations()
            signal = get_rate_path_signal(expectations)

            meetings = []
            if expectations and expectations.meetings:
                for meeting in expectations.meetings[:6]:
                    meetings.append({
                        "date": meeting.date.isoformat() if meeting.date else None,
                        "prob_hike": meeting.prob_hike,
                        "prob_cut": meeting.prob_cut,
                        "prob_hold": meeting.prob_hold,
                        "implied_rate": meeting.implied_rate,
                    })

            return {
                "current_rate": expectations.current_rate if expectations else None,
                "meetings": meetings,
                "signal": signal,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error collecting Fed expectations: {e}")
            return {"error": str(e)}

    async def collect_finviz_screens(self) -> dict:
        """Collect Finviz screen results."""
        try:
            from src.data.sources.alternative.finviz_screens import get_finviz_screens, SCREEN_DEFINITIONS

            screens = await get_finviz_screens()

            result = {}
            if screens:
                for screen_name, screen_result in screens.items():
                    if screen_result and screen_result.symbols:
                        result[screen_name] = {
                            "count": len(screen_result.symbols),
                            "top_symbols": screen_result.symbols[:20],  # Top 20 per screen
                        }

            return result
        except Exception as e:
            logger.warning(f"Error collecting Finviz screens: {e}")
            return {}

    async def collect_squeeze_candidates(self) -> list:
        """Collect short squeeze candidates."""
        try:
            from src.data.sources.alternative.short_interest import create_short_interest_source

            source = create_short_interest_source()
            candidates = await source.get_squeeze_candidates()

            return [
                {
                    "symbol": c.symbol,
                    "short_interest_pct": c.short_interest_pct,
                    "days_to_cover": c.days_to_cover,
                    "squeeze_score": c.squeeze_score,
                }
                for c in candidates[:30]  # Top 30 squeeze candidates
            ]
        except Exception as e:
            logger.warning(f"Error collecting squeeze candidates: {e}")
            return []

    async def collect_technical_signals(self) -> dict:
        """Collect technical signals for watchlist symbols."""
        try:
            import yfinance as yf
            import pandas as pd

            # Standard watchlist
            symbols = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"]
            signals = {}

            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="60d")

                    if len(hist) < 20:
                        continue

                    close = hist['Close']

                    # RSI
                    delta = close.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))

                    # Bollinger Bands
                    ma20 = close.rolling(20).mean()
                    std20 = close.rolling(20).std()
                    bb_position = (close.iloc[-1] - ma20.iloc[-1]) / (2 * std20.iloc[-1])

                    # MACD
                    ema12 = close.ewm(span=12).mean()
                    ema26 = close.ewm(span=26).mean()
                    macd = ema12 - ema26
                    signal_line = macd.ewm(span=9).mean()
                    macd_hist = macd - signal_line

                    # 20-day momentum
                    momentum = (close.iloc[-1] / close.iloc[-20] - 1) * 100

                    signals[symbol] = {
                        "close": float(close.iloc[-1]),
                        "rsi_14": float(rsi.iloc[-1]),
                        "bb_position": float(bb_position),
                        "macd_histogram": float(macd_hist.iloc[-1]),
                        "momentum_20d": float(momentum),
                        "above_50ma": bool(close.iloc[-1] > close.rolling(50).mean().iloc[-1]),
                        "above_200ma": bool(close.iloc[-1] > close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None,
                    }
                except Exception:
                    continue

            return signals
        except Exception as e:
            logger.warning(f"Error collecting technical signals: {e}")
            return {}

    async def collect_market_regime(self) -> dict:
        """Determine current market regime."""
        try:
            from src.data.pipeline.regime_detector import RegimeDetector

            detector = RegimeDetector()
            regime = await detector.detect_regime()

            return {
                "regime": regime.regime if regime else "unknown",
                "confidence": regime.confidence if regime else 0,
                "volatility_regime": regime.volatility_regime if regime else None,
                "trend_regime": regime.trend_regime if regime else None,
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Error detecting market regime: {e}")
            return {"regime": "unknown", "error": str(e)}

    async def archive_daily(self, archive_date: date = None, dry_run: bool = False) -> DailySignalArchive:
        """Archive all signals for a given date."""
        archive_date = archive_date or date.today()
        timestamp = datetime.now()

        logger.info(f"Starting daily signal archive for {archive_date}")

        # Collect all signals concurrently
        results = await asyncio.gather(
            self.collect_vix_data(),
            self.collect_breadth_data(),
            self.collect_put_call_data(),
            self.collect_aaii_sentiment(),
            self.collect_newsletter_sentiment(),
            self.collect_expert_sentiment(),
            self.collect_congressional_trades(),
            self.collect_insider_trades(),
            self.collect_options_flow(),
            self.collect_cot_data(),
            self.collect_economic_events(),
            self.collect_fed_expectations(),
            self.collect_finviz_screens(),
            self.collect_squeeze_candidates(),
            self.collect_technical_signals(),
            self.collect_market_regime(),
            return_exceptions=True
        )

        # Build archive
        archive = DailySignalArchive(
            archive_date=archive_date.isoformat(),
            archive_timestamp=timestamp.isoformat(),
            vix_data=results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
            breadth_data=results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
            put_call_data=results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
            aaii_sentiment=results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
            newsletter_sentiment=results[4] if not isinstance(results[4], Exception) else {"error": str(results[4])},
            expert_sentiment=results[5] if not isinstance(results[5], Exception) else [],
            congressional_trades=results[6] if not isinstance(results[6], Exception) else [],
            insider_trades=results[7] if not isinstance(results[7], Exception) else [],
            options_flow=results[8] if not isinstance(results[8], Exception) else [],
            cot_data=results[9] if not isinstance(results[9], Exception) else {"error": str(results[9])},
            economic_events=results[10] if not isinstance(results[10], Exception) else [],
            fed_expectations=results[11] if not isinstance(results[11], Exception) else {"error": str(results[11])},
            finviz_screens=results[12] if not isinstance(results[12], Exception) else {},
            squeeze_candidates=results[13] if not isinstance(results[13], Exception) else [],
            technical_signals=results[14] if not isinstance(results[14], Exception) else {},
            market_regime=results[15] if not isinstance(results[15], Exception) else {"regime": "unknown"},
        )

        # Collection stats
        archive.collection_stats = {
            "vix_ok": "error" not in archive.vix_data,
            "breadth_ok": "error" not in archive.breadth_data,
            "put_call_ok": "error" not in archive.put_call_data,
            "aaii_ok": "error" not in archive.aaii_sentiment,
            "newsletter_ok": "error" not in archive.newsletter_sentiment,
            "expert_count": len(archive.expert_sentiment),
            "congressional_count": len(archive.congressional_trades),
            "insider_count": len(archive.insider_trades),
            "options_flow_count": len(archive.options_flow),
            "cot_ok": "error" not in archive.cot_data,
            "economic_events_count": len(archive.economic_events),
            "fed_ok": "error" not in archive.fed_expectations,
            "screen_count": len(archive.finviz_screens),
            "squeeze_count": len(archive.squeeze_candidates),
            "technical_symbols": len(archive.technical_signals),
        }

        # Save archive
        if not dry_run:
            archive_path = self._get_archive_path(archive_date)
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            with open(archive_path, 'w') as f:
                json.dump(archive.to_dict(), f, indent=2)

            logger.info(f"Archive saved to: {archive_path}")
        else:
            logger.info("DRY RUN - Archive not saved")

        return archive

    def load_archive(self, archive_date: date) -> DailySignalArchive | None:
        """Load a previously archived signal snapshot."""
        archive_path = self._get_archive_path(archive_date)

        if not archive_path.exists():
            return None

        with open(archive_path) as f:
            data = json.load(f)

        return DailySignalArchive(**data)

    def list_archives(self, days_back: int = 30) -> list[date]:
        """List available archive dates."""
        archives = []

        for days in range(days_back):
            check_date = date.today() - timedelta(days=days)
            archive_path = self._get_archive_path(check_date)
            if archive_path.exists():
                archives.append(check_date)

        return archives


def print_archive_summary(archive: DailySignalArchive):
    """Print a summary of the archived signals."""
    print("\n" + "=" * 70)
    print(f"DAILY SIGNAL ARCHIVE - {archive.archive_date}")
    print("=" * 70)

    stats = archive.collection_stats

    print("\n--- MARKET REGIME ---")
    print(f"  Regime: {archive.market_regime.get('regime', 'unknown')}")
    print(f"  Confidence: {archive.market_regime.get('confidence', 0):.0%}")

    print("\n--- VOLATILITY & BREADTH ---")
    if stats.get("vix_ok"):
        print(f"  VIX Spot: {archive.vix_data.get('vix_spot', 'N/A')}")
        print(f"  Structure: {archive.vix_data.get('structure', 'N/A')}")
    if stats.get("breadth_ok"):
        print(f"  Pct Advancing: {archive.breadth_data.get('pct_advancing', 'N/A')}")
        print(f"  Breadth Signal: {archive.breadth_data.get('signal', 'N/A')}")

    print("\n--- SENTIMENT ---")
    if stats.get("aaii_ok"):
        aaii = archive.aaii_sentiment
        print(f"  AAII: Bull {aaii.get('bullish', 0):.0%} / Bear {aaii.get('bearish', 0):.0%}")
    if stats.get("put_call_ok"):
        print(f"  Put/Call Signal: {archive.put_call_data.get('signal', 'N/A')}")

    print("\n--- INSTITUTIONAL ---")
    print(f"  Congressional trades: {stats.get('congressional_count', 0)}")
    print(f"  Insider trades: {stats.get('insider_count', 0)}")
    print(f"  Unusual options: {stats.get('options_flow_count', 0)}")

    print("\n--- SCREENS & CANDIDATES ---")
    print(f"  Finviz screens: {stats.get('screen_count', 0)}")
    print(f"  Squeeze candidates: {stats.get('squeeze_count', 0)}")

    print("\n--- TECHNICAL SIGNALS ---")
    print(f"  Symbols tracked: {stats.get('technical_symbols', 0)}")

    if archive.technical_signals:
        for symbol in ["SPY", "QQQ"]:
            if symbol in archive.technical_signals:
                sig = archive.technical_signals[symbol]
                print(f"  {symbol}: RSI={sig.get('rsi_14', 0):.1f}, BB={sig.get('bb_position', 0):.2f}, Mom={sig.get('momentum_20d', 0):.1f}%")

    print("\n" + "=" * 70)


async def main():
    parser = argparse.ArgumentParser(description="Archive daily trading signals")
    parser.add_argument(
        "--date",
        type=str,
        help="Archive date (YYYY-MM-DD). Default: today"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available archives"
    )

    args = parser.parse_args()

    archiver = DailySignalArchiver()

    if args.list:
        archives = archiver.list_archives(days_back=60)
        print(f"\nAvailable archives ({len(archives)} days):")
        for d in archives:
            print(f"  {d}")
        return

    archive_date = None
    if args.date:
        archive_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    archive = await archiver.archive_daily(archive_date=archive_date, dry_run=args.dry_run)
    print_archive_summary(archive)


if __name__ == "__main__":
    asyncio.run(main())
