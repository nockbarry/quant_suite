#!/usr/bin/env python3
"""
Historical Data Backfill Script

Attempts to backfill historical alternative data from free sources for backtesting.

Available backfill sources:
1. VIX Historical - Yahoo Finance (^VIX)
2. Market Breadth - Calculated from sector ETFs
3. Put/Call Ratio - CBOE historical (limited)
4. AAII Sentiment - Public archives
5. COT Report - CFTC public archives
6. Congressional Trades - Quiver Quantitative
7. Insider Trading - SEC EDGAR / OpenInsider archives

Usage:
    python3 scripts/backfill_historical_data.py --source vix --days 365
    python3 scripts/backfill_historical_data.py --source all --days 180
    python3 scripts/backfill_historical_data.py --list
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HistoricalBackfiller:
    """Backfills historical alternative data for backtesting."""

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or paths.base
        self.backfill_dir = self.results_dir / "backfill"
        self.backfill_dir.mkdir(parents=True, exist_ok=True)

    def backfill_vix_history(self, days: int = 365) -> dict:
        """
        Backfill VIX historical data from Yahoo Finance.

        Provides: VIX spot price, high, low, and estimated term structure.
        """
        logger.info(f"Backfilling VIX history for {days} days...")

        # Get VIX data
        vix = yf.Ticker("^VIX")
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        hist = vix.history(start=start_date.isoformat(), end=end_date.isoformat())

        if hist.empty:
            logger.warning("No VIX data received from Yahoo Finance")
            return {"error": "No data", "records": []}

        # Also get VIX3M for term structure estimation
        vix3m = yf.Ticker("^VIX3M")
        hist3m = vix3m.history(start=start_date.isoformat(), end=end_date.isoformat())

        records = []
        for dt in hist.index:
            date_str = dt.strftime("%Y-%m-%d")
            vix_spot = float(hist.loc[dt, 'Close'])
            vix_high = float(hist.loc[dt, 'High'])
            vix_low = float(hist.loc[dt, 'Low'])

            # Estimate term structure slope
            slope = 0.05  # Default contango assumption
            structure = "contango"
            if dt in hist3m.index:
                vix3m_val = float(hist3m.loc[dt, 'Close'])
                slope = (vix3m_val - vix_spot) / vix_spot
                structure = "contango" if slope > 0 else "backwardation"

            # Generate signal
            signal = -0.4 if vix_spot < 20 else (-0.2 if vix_spot < 25 else 0.2 if vix_spot < 30 else 0.4)
            if structure == "backwardation":
                signal += 0.3  # Backwardation is more bearish

            records.append({
                "date": date_str,
                "vix_spot": vix_spot,
                "high": vix_high,
                "low": vix_low,
                "vix_3m": float(hist3m.loc[dt, 'Close']) if dt in hist3m.index else None,
                "slope_estimate": round(slope, 4),
                "structure": structure,
                "signal": round(signal, 2),
            })

        # Save to file
        output_file = self.backfill_dir / f"vix_history_{days}d.json"
        with open(output_file, 'w') as f:
            json.dump({"vix": records, "backfilled_at": datetime.now().isoformat()}, f, indent=2)

        logger.info(f"Saved {len(records)} VIX records to {output_file}")
        return {"records": len(records), "file": str(output_file)}

    def backfill_breadth_history(self, days: int = 365) -> dict:
        """
        Backfill market breadth by calculating from sector ETFs.

        Uses: XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY (S&P 500 sectors)
        """
        logger.info(f"Backfilling market breadth for {days} days...")

        sector_etfs = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Fetch all sector ETF data
        sector_data = {}
        for etf in sector_etfs:
            try:
                ticker = yf.Ticker(etf)
                hist = ticker.history(start=start_date.isoformat(), end=end_date.isoformat())
                if not hist.empty:
                    sector_data[etf] = hist
            except Exception as e:
                logger.warning(f"Failed to fetch {etf}: {e}")

        if len(sector_data) < 6:
            logger.warning("Not enough sector data for breadth calculation")
            return {"error": "Insufficient data", "records": []}

        # Combine all dates
        all_dates = set()
        for hist in sector_data.values():
            all_dates.update(hist.index)
        all_dates = sorted(all_dates)

        records = []
        for dt in all_dates:
            advancing = 0
            total = 0

            for etf, hist in sector_data.items():
                if dt in hist.index and dt - timedelta(days=1) in hist.index:
                    today_close = hist.loc[dt, 'Close']
                    prev_close = hist.loc[dt - timedelta(days=1), 'Close']
                    if today_close > prev_close:
                        advancing += 1
                    total += 1

            if total > 0:
                pct_advancing = advancing / total
                signal = "strong" if pct_advancing > 0.7 else "healthy" if pct_advancing > 0.5 else "weak" if pct_advancing > 0.3 else "very_weak"
                breadth_signal = 0.8 if pct_advancing > 0.7 else 0.4 if pct_advancing > 0.5 else -0.4 if pct_advancing > 0.3 else -0.8

                records.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "pct_advancing": round(pct_advancing, 2),
                    "advancing": advancing,
                    "total": total,
                    "signal": signal,
                    "breadth_signal": breadth_signal,
                })

        # Save to file
        output_file = self.backfill_dir / f"breadth_history_{days}d.json"
        with open(output_file, 'w') as f:
            json.dump({"breadth": records, "backfilled_at": datetime.now().isoformat()}, f, indent=2)

        logger.info(f"Saved {len(records)} breadth records to {output_file}")
        return {"records": len(records), "file": str(output_file)}

    def backfill_aaii_history(self, years: int = 2) -> dict:
        """
        Backfill AAII sentiment from public sources.

        AAII publishes weekly sentiment data.
        Historical data available at: https://www.aaii.com/sentimentsurvey
        """
        logger.info(f"Backfilling AAII sentiment history...")

        # AAII historical data URL (they provide CSV downloads)
        # Note: This may require manual download as they don't have a public API
        url = "https://www.aaii.com/files/surveys/sentiment.xls"

        try:
            # Try to fetch historical data
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"AAII data not available via direct download: {response.status_code}")
                return self._create_synthetic_aaii_history(years)

            # Parse Excel file
            df = pd.read_excel(response.content, sheet_name=0)
            records = []

            for _, row in df.iterrows():
                if pd.notna(row.get('Date')):
                    records.append({
                        "date": row['Date'].strftime("%Y-%m-%d") if hasattr(row['Date'], 'strftime') else str(row['Date']),
                        "bullish": float(row.get('Bullish', 0)) / 100,
                        "neutral": float(row.get('Neutral', 0)) / 100,
                        "bearish": float(row.get('Bearish', 0)) / 100,
                        "bull_bear_spread": (float(row.get('Bullish', 0)) - float(row.get('Bearish', 0))) / 100,
                    })

            output_file = self.backfill_dir / f"aaii_history_{years}y.json"
            with open(output_file, 'w') as f:
                json.dump({"aaii": records, "backfilled_at": datetime.now().isoformat()}, f, indent=2)

            logger.info(f"Saved {len(records)} AAII records to {output_file}")
            return {"records": len(records), "file": str(output_file)}

        except Exception as e:
            logger.warning(f"Error fetching AAII data: {e}")
            return self._create_synthetic_aaii_history(years)

    def _create_synthetic_aaii_history(self, years: int) -> dict:
        """Create synthetic AAII history based on market behavior."""
        logger.info("Creating synthetic AAII history based on SPY price action...")

        spy = yf.Ticker("SPY")
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)
        hist = spy.history(start=start_date.isoformat(), end=end_date.isoformat())

        # Calculate 20-day returns for sentiment proxy
        hist['return_20d'] = hist['Close'].pct_change(20)

        records = []
        # Weekly samples (Thursdays like AAII)
        for i in range(0, len(hist), 5):
            if i + 20 >= len(hist):
                continue

            dt = hist.index[i]
            ret = hist.iloc[i]['return_20d']

            if pd.isna(ret):
                continue

            # Map returns to sentiment (contrarian indicator)
            # Strong positive returns -> high bullish (eventual contrarian sell)
            bullish = 0.35 + ret * 2  # Base 35%, moves with returns
            bullish = max(0.20, min(0.60, bullish))  # Clamp to realistic range

            bearish = 0.30 - ret * 2
            bearish = max(0.15, min(0.50, bearish))

            neutral = 1 - bullish - bearish

            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "bullish": round(bullish, 3),
                "neutral": round(neutral, 3),
                "bearish": round(bearish, 3),
                "bull_bear_spread": round(bullish - bearish, 3),
                "synthetic": True,  # Mark as synthetic
            })

        output_file = self.backfill_dir / f"aaii_history_synthetic_{years}y.json"
        with open(output_file, 'w') as f:
            json.dump({"aaii": records, "backfilled_at": datetime.now().isoformat(), "synthetic": True}, f, indent=2)

        logger.info(f"Saved {len(records)} synthetic AAII records to {output_file}")
        return {"records": len(records), "file": str(output_file), "synthetic": True}

    def backfill_put_call_history(self, days: int = 365) -> dict:
        """
        Backfill put/call ratio from proxy data.

        Uses CBOE total put/call ratio data if available, otherwise estimates
        from option volume on major ETFs.
        """
        logger.info(f"Backfilling put/call ratio for {days} days...")

        # Try to fetch from CBOE data
        # Note: CBOE provides delayed data, may need alternative sources
        try:
            # Use market proxy: VIX correlation with put/call
            vix = yf.Ticker("^VIX")
            spy = yf.Ticker("SPY")

            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            vix_hist = vix.history(start=start_date.isoformat(), end=end_date.isoformat())
            spy_hist = spy.history(start=start_date.isoformat(), end=end_date.isoformat())

            records = []
            for dt in vix_hist.index:
                if dt not in spy_hist.index:
                    continue

                vix_val = float(vix_hist.loc[dt, 'Close'])
                spy_ret = float(spy_hist.loc[dt, 'Close'] / spy_hist.loc[dt, 'Open'] - 1)

                # Estimate P/C ratio from VIX and daily return
                # Higher VIX and down days = higher put/call
                base_pc = 0.85  # Average historical P/C
                pc_adjustment = (vix_val - 20) / 100  # VIX effect
                ret_adjustment = -spy_ret * 0.5  # Down days increase puts
                estimated_pc = base_pc + pc_adjustment + ret_adjustment
                estimated_pc = max(0.4, min(1.5, estimated_pc))

                # Signal: high P/C (>1.0) is contrarian bullish
                signal = 1 if estimated_pc > 1.1 else 0.5 if estimated_pc > 1.0 else 0 if estimated_pc > 0.8 else -0.5 if estimated_pc > 0.6 else -1

                records.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "estimated_pc_ratio": round(estimated_pc, 3),
                    "vix_reference": round(vix_val, 2),
                    "signal": signal,
                    "synthetic": True,
                })

            output_file = self.backfill_dir / f"put_call_history_{days}d.json"
            with open(output_file, 'w') as f:
                json.dump({"put_call": records, "backfilled_at": datetime.now().isoformat(), "synthetic": True}, f, indent=2)

            logger.info(f"Saved {len(records)} put/call records to {output_file}")
            return {"records": len(records), "file": str(output_file), "synthetic": True}

        except Exception as e:
            logger.error(f"Error backfilling put/call: {e}")
            return {"error": str(e), "records": []}

    async def backfill_congressional_history(self, days: int = 365) -> dict:
        """
        Backfill congressional trading data from Quiver Quantitative.

        Quiver provides historical congressional trading data.
        API: https://api.quiverquant.com/beta/historical/congresstrading
        """
        logger.info(f"Attempting to backfill congressional trading history...")

        # Quiver Quant free tier may have limitations
        # Alternative: House Stock Watcher / Senate Stock Watcher
        try:
            # Try House Stock Watcher API
            url = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                all_trades = response.json()

                # Filter to recent trades
                cutoff = date.today() - timedelta(days=days)
                records = []

                for trade in all_trades:
                    trade_date_str = trade.get('transaction_date', '')
                    if not trade_date_str:
                        continue

                    try:
                        trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()
                    except:
                        continue

                    if trade_date < cutoff:
                        continue

                    records.append({
                        "date": trade_date_str,
                        "politician": trade.get('representative', ''),
                        "chamber": "house",
                        "symbol": trade.get('ticker', ''),
                        "trade_type": trade.get('type', ''),
                        "amount": trade.get('amount', ''),
                        "disclosure_date": trade.get('disclosure_date', ''),
                    })

                output_file = self.backfill_dir / f"congressional_history_{days}d.json"
                with open(output_file, 'w') as f:
                    json.dump({"trades": records, "backfilled_at": datetime.now().isoformat(), "source": "house_stock_watcher"}, f, indent=2)

                logger.info(f"Saved {len(records)} congressional records to {output_file}")
                return {"records": len(records), "file": str(output_file)}
            else:
                logger.warning(f"House Stock Watcher unavailable: {response.status_code}")
                return {"error": f"HTTP {response.status_code}", "records": []}

        except Exception as e:
            logger.error(f"Error backfilling congressional data: {e}")
            return {"error": str(e), "records": []}

    async def backfill_insider_history(self, days: int = 365, symbols: list = None) -> dict:
        """
        Backfill insider trading from OpenInsider.

        OpenInsider provides historical Form 4 data.
        """
        logger.info(f"Attempting to backfill insider trading history...")

        symbols = symbols or ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

        try:
            # OpenInsider scraping (public data)
            base_url = "http://openinsider.com/screener"
            all_trades = []

            # Note: OpenInsider may have rate limits
            # For production, consider SEC EDGAR API

            for symbol in symbols[:5]:  # Limit to avoid rate limits
                try:
                    url = f"http://openinsider.com/screener?s={symbol}&o=&pl=&ph=&ll=&lh=&fd=730&fdr=&td=0&tdr=&fdlyl=&fdlyh=&dtefrom=&dteto=&xp=1&xs=1&vl=&vh=&ocl=&och=&session=&sort=FSORT&sortextra=&cnt=100"
                    response = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})

                    if response.status_code == 200:
                        # Parse HTML for insider data
                        # This is a simplified version - full implementation would use BeautifulSoup
                        logger.info(f"Fetched insider data page for {symbol}")
                        # Note: Actual parsing would extract trade details from HTML
                except Exception as e:
                    logger.warning(f"Error fetching insider data for {symbol}: {e}")
                    continue

                await asyncio.sleep(1)  # Rate limit

            # For now, return empty result with note about manual data
            output_file = self.backfill_dir / f"insider_history_{days}d.json"
            with open(output_file, 'w') as f:
                json.dump({
                    "trades": all_trades,
                    "backfilled_at": datetime.now().isoformat(),
                    "note": "Full insider backfill requires SEC EDGAR API integration",
                    "symbols_attempted": symbols[:5]
                }, f, indent=2)

            return {"records": len(all_trades), "file": str(output_file), "note": "Limited data - full backfill requires SEC EDGAR"}

        except Exception as e:
            logger.error(f"Error backfilling insider data: {e}")
            return {"error": str(e), "records": []}

    def backfill_cot_history(self, weeks: int = 52) -> dict:
        """
        Backfill COT report from CFTC archives.

        CFTC provides historical COT data in downloadable format.
        https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm
        """
        logger.info(f"Attempting to backfill COT history for {weeks} weeks...")

        try:
            # CFTC provides annual files
            year = date.today().year
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"

            # Note: This would require downloading and parsing the CFTC zip files
            # For now, return info about manual process

            output_file = self.backfill_dir / f"cot_history_{weeks}w.json"
            with open(output_file, 'w') as f:
                json.dump({
                    "reports": [],
                    "backfilled_at": datetime.now().isoformat(),
                    "note": f"COT data available from CFTC: {url}",
                    "manual_steps": [
                        "1. Download CFTC annual files from the URL",
                        "2. Extract and parse the text/CSV files",
                        "3. Filter for relevant contracts (ES, NQ, SPY equivalents)",
                        "4. Calculate commercial vs speculative positioning"
                    ]
                }, f, indent=2)

            logger.info(f"COT backfill info saved to {output_file}")
            return {"records": 0, "file": str(output_file), "note": "Manual download required from CFTC"}

        except Exception as e:
            logger.error(f"Error backfilling COT data: {e}")
            return {"error": str(e), "records": []}

    async def backfill_all(self, days: int = 365) -> dict:
        """Run all backfill operations."""
        results = {}

        # Synchronous backfills
        results["vix"] = self.backfill_vix_history(days)
        results["breadth"] = self.backfill_breadth_history(days)
        results["put_call"] = self.backfill_put_call_history(days)
        results["aaii"] = self.backfill_aaii_history(days // 365 + 1)
        results["cot"] = self.backfill_cot_history(days // 7)

        # Async backfills
        results["congressional"] = await self.backfill_congressional_history(days)
        results["insider"] = await self.backfill_insider_history(days)

        # Summary
        total_records = sum(r.get("records", 0) for r in results.values())
        logger.info(f"Backfill complete: {total_records} total records across {len(results)} sources")

        # Save summary
        summary_file = self.backfill_dir / "backfill_summary.json"
        with open(summary_file, 'w') as f:
            json.dump({
                "backfill_date": datetime.now().isoformat(),
                "days_requested": days,
                "results": results
            }, f, indent=2)

        return results


def list_available_sources():
    """List available backfill sources."""
    print("\nAvailable Backfill Sources:")
    print("-" * 60)
    sources = [
        ("vix", "VIX spot and term structure from Yahoo Finance"),
        ("breadth", "Market breadth calculated from sector ETFs"),
        ("put_call", "Put/Call ratio estimated from VIX correlation"),
        ("aaii", "AAII sentiment (may be synthetic proxy)"),
        ("cot", "COT report (requires manual CFTC download)"),
        ("congressional", "Congressional trades from House Stock Watcher"),
        ("insider", "Insider trading (limited, needs SEC EDGAR)"),
        ("all", "Run all backfill operations"),
    ]

    for name, desc in sources:
        print(f"  {name:<15} - {desc}")

    print("\nUsage Examples:")
    print("  python3 scripts/backfill_historical_data.py --source vix --days 365")
    print("  python3 scripts/backfill_historical_data.py --source all --days 180")


async def main():
    parser = argparse.ArgumentParser(description="Backfill Historical Alternative Data")
    parser.add_argument(
        "--source",
        type=str,
        choices=["vix", "breadth", "put_call", "aaii", "cot", "congressional", "insider", "all"],
        help="Data source to backfill"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to backfill (default: 365)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available backfill sources"
    )

    args = parser.parse_args()

    if args.list or not args.source:
        list_available_sources()
        return

    backfiller = HistoricalBackfiller()

    if args.source == "all":
        results = await backfiller.backfill_all(args.days)
        print(f"\nBackfill complete. Results saved to: {backfiller.backfill_dir}")
        for source, result in results.items():
            records = result.get("records", 0)
            synthetic = " (synthetic)" if result.get("synthetic") else ""
            print(f"  {source}: {records} records{synthetic}")

    elif args.source == "vix":
        result = backfiller.backfill_vix_history(args.days)
        print(f"VIX backfill: {result.get('records', 0)} records saved to {result.get('file', 'N/A')}")

    elif args.source == "breadth":
        result = backfiller.backfill_breadth_history(args.days)
        print(f"Breadth backfill: {result.get('records', 0)} records saved to {result.get('file', 'N/A')}")

    elif args.source == "put_call":
        result = backfiller.backfill_put_call_history(args.days)
        print(f"Put/Call backfill: {result.get('records', 0)} records saved to {result.get('file', 'N/A')}")

    elif args.source == "aaii":
        result = backfiller.backfill_aaii_history(max(1, args.days // 365))
        print(f"AAII backfill: {result.get('records', 0)} records saved to {result.get('file', 'N/A')}")

    elif args.source == "cot":
        result = backfiller.backfill_cot_history(args.days // 7)
        print(f"COT backfill: {result.get('note', 'Check output file for manual steps')}")

    elif args.source == "congressional":
        result = await backfiller.backfill_congressional_history(args.days)
        print(f"Congressional backfill: {result.get('records', 0)} records saved to {result.get('file', 'N/A')}")

    elif args.source == "insider":
        result = await backfiller.backfill_insider_history(args.days)
        print(f"Insider backfill: {result.get('note', 'Check output file')}")


if __name__ == "__main__":
    asyncio.run(main())
