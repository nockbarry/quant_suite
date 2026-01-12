#!/usr/bin/env python3
"""
Simplified Data Collection Pipeline Test

Tests all data sources with correct API calls.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_result(name: str, success: bool, details: str = ""):
    status = "PASS" if success else "FAIL"
    icon = "[+]" if success else "[-]"
    print(f"{icon} {name}: {status}")
    if details:
        print(f"    {details}")


async def test_vix_structure():
    """Test VIX term structure."""
    try:
        from src.data.sources.alternative.vix_structure import VIXStructureSource
        source = VIXStructureSource()
        structure = await source.get_structure()
        await source.close()

        print_result(
            "VIX Structure",
            True,
            f"spot={structure.vix_spot:.2f}, structure={structure.structure}, signal={structure.mean_reversion_signal:.2f}"
        )
        return True
    except Exception as e:
        print_result("VIX Structure", False, str(e))
        return False


async def test_put_call():
    """Test put/call ratio."""
    try:
        from src.data.sources.alternative.put_call import PutCallSource
        source = PutCallSource()
        data = await source.get_put_call()
        await source.close()

        print_result(
            "Put/Call Ratio",
            True,
            f"ratio={data.total_ratio:.2f}, signal={data.signal}"
        )
        return True
    except Exception as e:
        print_result("Put/Call Ratio", False, str(e))
        return False


async def test_finviz_screens():
    """Test Finviz screener."""
    try:
        from src.data.sources.alternative.finviz_screens import FinvizScreener
        screener = FinvizScreener()
        screens = await screener.get_screens()
        await screener.close()

        total = sum(len(s.symbols) for s in screens.screens.values())
        print_result(
            "Finviz Screens",
            True,
            f"{len(screens.screens)} screens, {total} total symbols"
        )
        return True
    except Exception as e:
        print_result("Finviz Screens", False, str(e))
        return False


async def test_aaii_sentiment():
    """Test AAII sentiment."""
    try:
        from src.data.sources.alternative.aaii_sentiment import AAIISentimentSource
        source = AAIISentimentSource()
        data = await source.get_sentiment()
        await source.close()

        print_result(
            "AAII Sentiment",
            True,
            f"bullish={data.bullish_pct:.1f}%, bearish={data.bearish_pct:.1f}%"
        )
        return True
    except Exception as e:
        print_result("AAII Sentiment", False, str(e))
        return False


async def test_newsletter_sentiment():
    """Test newsletter sentiment."""
    try:
        from src.data.sources.alternative.newsletter_sentiment import NewsletterSentimentSource
        source = NewsletterSentimentSource()
        data = await source.get_sentiment()
        await source.close()

        print_result(
            "Newsletter Sentiment",
            True,
            f"bulls={data.bulls_pct:.1f}%, bears={data.bears_pct:.1f}%"
        )
        return True
    except Exception as e:
        print_result("Newsletter Sentiment", False, str(e))
        return False


async def test_cot_report():
    """Test COT report."""
    try:
        from src.data.sources.alternative.cot_report import COTSource
        source = COTSource()
        report = await source.get_report()
        await source.close()

        print_result(
            "COT Report",
            True,
            f"{len(report.positions)} contracts, equity_signal={report.equity_signal:.2f}"
        )
        return True
    except Exception as e:
        print_result("COT Report", False, str(e))
        return False


async def test_earnings_calendar():
    """Test earnings calendar."""
    try:
        from src.data.sources.alternative.earnings_calendar import EarningsCalendarSource
        source = EarningsCalendarSource()
        calendar = await source.get_calendar()
        await source.close()

        print_result(
            "Earnings Calendar",
            True,
            f"{len(calendar.events)} events"
        )
        return True
    except Exception as e:
        print_result("Earnings Calendar", False, str(e))
        return False


async def test_economic_calendar():
    """Test economic calendar."""
    try:
        from src.data.sources.alternative.economic_calendar import EconomicCalendarSource
        source = EconomicCalendarSource()
        calendar = await source.get_calendar()
        await source.close()

        high_impact = len([e for e in calendar.events if e.importance == "high"])
        print_result(
            "Economic Calendar",
            True,
            f"{len(calendar.events)} events, {high_impact} high-impact"
        )
        return True
    except Exception as e:
        print_result("Economic Calendar", False, str(e))
        return False


async def test_fed_futures():
    """Test Fed futures."""
    try:
        from src.data.sources.alternative.fed_futures import FedFuturesSource
        source = FedFuturesSource()
        expectations = await source.get_expectations()
        await source.close()

        print_result(
            "Fed Futures",
            True,
            f"path={expectations.rate_path_signal}, 12m_rate={expectations.implied_rate_12m:.2f}%"
        )
        return True
    except Exception as e:
        print_result("Fed Futures", False, str(e))
        return False


async def test_treasury_calendar():
    """Test Treasury calendar."""
    try:
        from src.data.sources.alternative.treasury_calendar import TreasuryCalendarSource
        source = TreasuryCalendarSource()
        calendar = await source.get_calendar()
        await source.close()

        print_result(
            "Treasury Calendar",
            True,
            f"{len(calendar.auctions)} auctions"
        )
        return True
    except Exception as e:
        print_result("Treasury Calendar", False, str(e))
        return False


async def test_ipo_calendar():
    """Test IPO calendar."""
    try:
        from src.data.sources.alternative.ipo_calendar import IPOCalendarSource
        source = IPOCalendarSource()
        calendar = await source.get_calendar()
        await source.close()

        print_result(
            "IPO Calendar",
            True,
            f"{len(calendar.ipos)} IPOs"
        )
        return True
    except Exception as e:
        print_result("IPO Calendar", False, str(e))
        return False


async def test_fda_calendar():
    """Test FDA calendar."""
    try:
        from src.data.sources.alternative.fda_calendar import FDACalendarSource
        source = FDACalendarSource()
        calendar = await source.get_calendar()
        await source.close()

        pdufa = len([e for e in calendar.events if e.event_type == "PDUFA"])
        print_result(
            "FDA Calendar",
            True,
            f"{len(calendar.events)} events, {pdufa} PDUFA"
        )
        return True
    except Exception as e:
        print_result("FDA Calendar", False, str(e))
        return False


async def test_patents():
    """Test patent filings."""
    try:
        from src.data.sources.alternative.patent_filings import USPTOSource
        source = USPTOSource()
        db = await source.get_database()
        await source.close()

        print_result(
            "Patent Filings",
            True,
            f"{len(db.activities)} companies tracked"
        )
        return True
    except Exception as e:
        print_result("Patent Filings", False, str(e))
        return False


async def test_job_postings():
    """Test job postings."""
    try:
        from src.data.sources.alternative.job_postings import JobPostingSource
        source = JobPostingSource()
        db = await source.get_database()
        await source.close()

        print_result(
            "Job Postings",
            True,
            f"{len(db.postings)} companies tracked"
        )
        return True
    except Exception as e:
        print_result("Job Postings", False, str(e))
        return False


async def test_app_rankings():
    """Test app rankings."""
    try:
        from src.data.sources.alternative.app_rankings import AppRankingSource
        source = AppRankingSource()
        db = await source.get_database()
        await source.close()

        print_result(
            "App Rankings",
            True,
            f"{len(db.rankings)} app rankings tracked"
        )
        return True
    except Exception as e:
        print_result("App Rankings", False, str(e))
        return False


async def test_github():
    """Test GitHub activity."""
    try:
        from src.data.sources.alternative.github_activity import GitHubSource
        source = GitHubSource()
        db = await source.get_database()
        await source.close()

        print_result(
            "GitHub Activity",
            True,
            f"{len(db.activities)} companies tracked"
        )
        return True
    except Exception as e:
        print_result("GitHub Activity", False, str(e))
        return False


async def test_collection_daemon():
    """Test collection daemon."""
    try:
        from src.data.sources.collection_daemon import DataCollectionDaemon
        daemon = DataCollectionDaemon()
        status = daemon.get_status()

        print_result(
            "Collection Daemon",
            True,
            f"{len(status.sources)} sources configured"
        )
        return True
    except Exception as e:
        print_result("Collection Daemon", False, str(e))
        return False


async def test_historical_vix():
    """Test historical VIX data collection."""
    try:
        import yfinance as yf

        # Get 3 months of VIX history
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="3mo")

        if hist.empty:
            print_result("VIX History", False, "No historical data returned")
            return False

        # Save to history file
        history_dir = paths.live / "historical_data"
        history_dir.mkdir(parents=True, exist_ok=True)

        history = []
        for date, row in hist.iterrows():
            history.append({
                "date": date.isoformat(),
                "close": float(row["Close"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
            })

        history_file = history_dir / "vix_history.json"
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

        print_result(
            "VIX History",
            True,
            f"{len(history)} days of data saved to {history_file}"
        )
        return True
    except Exception as e:
        print_result("VIX History", False, str(e))
        return False


async def main():
    print_header("DATA COLLECTION PIPELINE TEST")
    print(f"Timestamp: {datetime.now()}")

    results = []

    # Market Regime Sources
    print_header("MARKET REGIME SOURCES")
    results.append(await test_vix_structure())
    results.append(await test_put_call())
    results.append(await test_finviz_screens())

    # Sentiment Sources
    print_header("SENTIMENT SOURCES")
    results.append(await test_aaii_sentiment())
    results.append(await test_newsletter_sentiment())
    results.append(await test_cot_report())

    # Economic Sources
    print_header("ECONOMIC SOURCES")
    results.append(await test_earnings_calendar())
    results.append(await test_economic_calendar())
    results.append(await test_fed_futures())
    results.append(await test_treasury_calendar())

    # Event Sources
    print_header("EVENT CATALYST SOURCES")
    results.append(await test_ipo_calendar())
    results.append(await test_fda_calendar())

    # Innovation Sources
    print_header("INNOVATION SOURCES")
    results.append(await test_patents())
    results.append(await test_job_postings())
    results.append(await test_app_rankings())
    results.append(await test_github())

    # Collection Daemon
    print_header("COLLECTION DAEMON")
    results.append(await test_collection_daemon())

    # Historical Data
    print_header("HISTORICAL DATA BACKFILL")
    results.append(await test_historical_vix())

    # Summary
    print_header("SUMMARY")
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")
    print(f"Success Rate: {100*passed/total:.0f}%")

    if passed == total:
        print("\nAll tests passed!")
        return 0
    else:
        print(f"\n{total - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
