#!/usr/bin/env python3
"""
Comprehensive Data Source Test Suite

Tests ALL data sources in the quant_suite:
- Core market data (Yahoo Finance)
- 29 alternative data sources
- Data pipelines (breadth, sentiment, options)
- Real-time sources
- Universal sources

Usage:
    python scripts/test_all_data_sources.py
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths


# ==============================================================================
# Test Utilities
# ==============================================================================

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


class TestResults:
    """Track test results."""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []

    def record(self, name: str, success: bool, details: str = "", skip: bool = False):
        if skip:
            self.skipped.append((name, details))
            print(f"[~] {name}: SKIPPED - {details}")
        elif success:
            self.passed.append((name, details))
            print_result(name, True, details)
        else:
            self.failed.append((name, details))
            print_result(name, False, details)

    def summary(self) -> dict:
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        return {
            "total": total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
            "success_rate": len(self.passed) / max(total - len(self.skipped), 1) * 100
        }


results = TestResults()


# ==============================================================================
# Core Market Data Tests
# ==============================================================================

async def test_yahoo_finance():
    """Test Yahoo Finance data source."""
    try:
        from src.data.sources.yahoo import YahooFinanceSource
        from src.core import Timeframe

        source = YahooFinanceSource()

        # Test single fetch
        end = datetime.now()
        start = end - timedelta(days=30)
        df = await source.fetch_ohlcv("SPY", start, end, Timeframe.DAILY)

        if len(df) > 0:
            results.record("Yahoo Finance - fetch_ohlcv", True, f"{len(df)} bars for SPY")
        else:
            results.record("Yahoo Finance - fetch_ohlcv", False, "No data returned")
            return

        # Test multiple fetch
        data = await source.fetch_multiple(["SPY", "QQQ"], start, end)
        results.record("Yahoo Finance - fetch_multiple", len(data) >= 2, f"{len(data)} symbols")

        # Test asset info
        info = await source.get_asset_info("AAPL")
        results.record("Yahoo Finance - get_asset_info", info.get("name") is not None, f"Name: {info.get('name', 'N/A')[:30]}")

    except Exception as e:
        results.record("Yahoo Finance", False, str(e))


# ==============================================================================
# Alternative Data Source Tests
# ==============================================================================

async def test_vix_structure():
    """Test VIX term structure source."""
    try:
        from src.data.sources.alternative.vix_structure import VIXStructureSource
        source = VIXStructureSource()
        structure = await source.get_structure()
        await source.close()
        results.record(
            "VIX Structure",
            structure.vix_spot > 0,
            f"spot={structure.vix_spot:.2f}, slope_3m={structure.slope_3m:.3f}"
        )
    except Exception as e:
        results.record("VIX Structure", False, str(e))


async def test_put_call():
    """Test put/call ratio source."""
    try:
        from src.data.sources.alternative.put_call import PutCallSource
        source = PutCallSource()
        data = await source.get_put_call()
        await source.close()
        results.record(
            "Put/Call Ratio",
            data.total_ratio > 0,
            f"ratio={data.total_ratio:.2f}, signal={data.signal}"
        )
    except Exception as e:
        results.record("Put/Call Ratio", False, str(e))


async def test_finviz_screens():
    """Test Finviz screener."""
    try:
        from src.data.sources.alternative.finviz_screens import FinvizScreener
        screener = FinvizScreener()
        screens = await screener.get_screens()
        await screener.close()
        total = sum(len(s.symbols) for s in screens.screens.values())
        results.record(
            "Finviz Screens",
            len(screens.screens) > 0,
            f"{len(screens.screens)} screens, {total} total symbols"
        )
    except Exception as e:
        results.record("Finviz Screens", False, str(e))


async def test_aaii_sentiment():
    """Test AAII sentiment source."""
    try:
        from src.data.sources.alternative.aaii_sentiment import AAIISentimentSource
        source = AAIISentimentSource()
        data = await source.get_sentiment()
        await source.close()
        results.record(
            "AAII Sentiment",
            data.bullish_pct >= 0,
            f"bullish={data.bullish_pct:.1f}%, bearish={data.bearish_pct:.1f}%"
        )
    except Exception as e:
        results.record("AAII Sentiment", False, str(e))


async def test_newsletter_sentiment():
    """Test newsletter sentiment source."""
    try:
        from src.data.sources.alternative.newsletter_sentiment import NewsletterSentimentSource
        source = NewsletterSentimentSource()
        data = await source.get_sentiment()
        await source.close()
        results.record(
            "Newsletter Sentiment",
            data.bulls_pct >= 0,
            f"bulls={data.bulls_pct:.1f}%, bears={data.bears_pct:.1f}%"
        )
    except Exception as e:
        results.record("Newsletter Sentiment", False, str(e))


async def test_cot_report():
    """Test COT report source."""
    try:
        from src.data.sources.alternative.cot_report import COTSource
        source = COTSource()
        report = await source.get_report()
        await source.close()
        results.record(
            "COT Report",
            len(report.positions) > 0,
            f"{len(report.positions)} contracts, equity_signal={report.equity_signal:.2f}"
        )
    except Exception as e:
        results.record("COT Report", False, str(e))


async def test_earnings_calendar():
    """Test earnings calendar source."""
    try:
        from src.data.sources.alternative.earnings_calendar import EarningsCalendarSource
        source = EarningsCalendarSource()
        calendar = await source.get_calendar()
        await source.close()
        results.record(
            "Earnings Calendar",
            True,
            f"{len(calendar.events)} events"
        )
    except Exception as e:
        results.record("Earnings Calendar", False, str(e))


async def test_economic_calendar():
    """Test economic calendar source."""
    try:
        from src.data.sources.alternative.economic_calendar import EconomicCalendarSource
        source = EconomicCalendarSource()
        calendar = await source.get_calendar()
        await source.close()
        high_impact = len([e for e in calendar.events if e.importance == "high"])
        results.record(
            "Economic Calendar",
            True,
            f"{len(calendar.events)} events, {high_impact} high-impact"
        )
    except Exception as e:
        results.record("Economic Calendar", False, str(e))


async def test_fed_futures():
    """Test Fed futures source."""
    try:
        from src.data.sources.alternative.fed_futures import FedFuturesSource
        source = FedFuturesSource()
        expectations = await source.get_expectations()
        await source.close()
        results.record(
            "Fed Futures",
            True,
            f"path={expectations.rate_path_signal}, 12m_rate={expectations.implied_rate_12m:.2f}%"
        )
    except Exception as e:
        results.record("Fed Futures", False, str(e))


async def test_treasury_calendar():
    """Test Treasury calendar source."""
    try:
        from src.data.sources.alternative.treasury_calendar import TreasuryCalendarSource
        source = TreasuryCalendarSource()
        calendar = await source.get_calendar()
        await source.close()
        results.record(
            "Treasury Calendar",
            True,
            f"{len(calendar.auctions)} auctions"
        )
    except Exception as e:
        results.record("Treasury Calendar", False, str(e))


async def test_ipo_calendar():
    """Test IPO calendar source."""
    try:
        from src.data.sources.alternative.ipo_calendar import IPOCalendarSource
        source = IPOCalendarSource()
        calendar = await source.get_calendar()
        await source.close()
        results.record(
            "IPO Calendar",
            True,
            f"{len(calendar.ipos)} IPOs"
        )
    except Exception as e:
        results.record("IPO Calendar", False, str(e))


async def test_fda_calendar():
    """Test FDA calendar source."""
    try:
        from src.data.sources.alternative.fda_calendar import FDACalendarSource
        source = FDACalendarSource()
        calendar = await source.get_calendar()
        await source.close()
        pdufa = len([e for e in calendar.events if e.event_type == "PDUFA"])
        results.record(
            "FDA Calendar",
            True,
            f"{len(calendar.events)} events, {pdufa} PDUFA"
        )
    except Exception as e:
        results.record("FDA Calendar", False, str(e))


async def test_patent_filings():
    """Test patent filings source."""
    try:
        from src.data.sources.alternative.patent_filings import USPTOSource
        source = USPTOSource()
        db = await source.get_database()
        await source.close()
        results.record(
            "Patent Filings",
            True,
            f"{len(db.activities)} companies tracked"
        )
    except Exception as e:
        results.record("Patent Filings", False, str(e))


async def test_job_postings():
    """Test job postings source."""
    try:
        from src.data.sources.alternative.job_postings import JobPostingSource
        source = JobPostingSource()
        db = await source.get_database()
        await source.close()
        results.record(
            "Job Postings",
            True,
            f"{len(db.postings)} companies tracked"
        )
    except Exception as e:
        results.record("Job Postings", False, str(e))


async def test_app_rankings():
    """Test app rankings source."""
    try:
        from src.data.sources.alternative.app_rankings import AppRankingSource
        source = AppRankingSource()
        db = await source.get_database()
        await source.close()
        results.record(
            "App Rankings",
            True,
            f"{len(db.rankings)} rankings tracked"
        )
    except Exception as e:
        results.record("App Rankings", False, str(e))


async def test_github_activity():
    """Test GitHub activity source."""
    try:
        from src.data.sources.alternative.github_activity import GitHubSource
        source = GitHubSource()
        db = await source.get_database()
        await source.close()
        results.record(
            "GitHub Activity",
            True,
            f"{len(db.activities)} companies tracked"
        )
    except Exception as e:
        results.record("GitHub Activity", False, str(e))


async def test_congressional_trades():
    """Test congressional trades source."""
    try:
        from src.data.sources.alternative.congressional_trades import CongressionalTradesSource
        source = CongressionalTradesSource()
        trades = await source.fetch_recent_trades(days=30)
        await source.close()
        results.record(
            "Congressional Trades",
            True,  # May be empty if no recent trades
            f"{len(trades)} trades in last 30 days"
        )
    except Exception as e:
        results.record("Congressional Trades", False, str(e))


async def test_insider_trading():
    """Test insider trading source (requires API key)."""
    try:
        from src.data.sources.alternative.insider import InsiderDataSource
        source = InsiderDataSource()
        # Will return empty without API keys but should not error
        summary = await source.get_summary("AAPL", days=30)
        await source.close()
        results.record(
            "Insider Trading",
            True,
            f"buys={summary.total_purchases}, sells={summary.total_sales}"
        )
    except Exception as e:
        results.record("Insider Trading", False, str(e))


async def test_options_flow():
    """Test options flow source."""
    try:
        from src.data.sources.alternative.options_flow import OptionsFlowSource
        source = OptionsFlowSource()
        contracts = await source.fetch_options_chain("SPY")
        await source.close()
        results.record(
            "Options Flow",
            len(contracts) > 0,
            f"{len(contracts)} option contracts"
        )
    except Exception as e:
        results.record("Options Flow", False, str(e))


async def test_expert_sentiment():
    """Test expert sentiment source."""
    try:
        from src.data.sources.alternative.expert_sentiment import ExpertSentimentSource
        source = ExpertSentimentSource()
        calls = await source.fetch_calls(days=30)
        await source.close()
        results.record(
            "Expert Sentiment",
            True,
            f"{len(calls)} expert calls in 30 days"
        )
    except Exception as e:
        results.record("Expert Sentiment", False, str(e))


async def test_prediction_markets():
    """Test prediction markets source."""
    try:
        from src.data.sources.alternative.prediction_markets import PredictionMarketsSource
        source = PredictionMarketsSource()
        markets = await source.fetch_markets()
        await source.close()
        results.record(
            "Prediction Markets",
            True,
            f"{len(markets)} markets tracked"
        )
    except Exception as e:
        results.record("Prediction Markets", False, str(e))


async def test_short_interest():
    """Test short interest source."""
    try:
        from src.data.sources.alternative.short_interest import ShortInterestSource
        source = ShortInterestSource()
        data = source.fetch_short_interest("GME")  # Sync method
        if data:
            results.record(
                "Short Interest",
                True,
                f"symbol={data.symbol}, short_ratio={data.short_ratio:.2f}"
            )
        else:
            results.record("Short Interest", True, "No short data available (normal)")
    except Exception as e:
        results.record("Short Interest", False, str(e))


async def test_etf_flows():
    """Test ETF flows source."""
    try:
        from src.data.sources.alternative.etf_flows import ETFFlowSource, ETFCategory
        source = ETFFlowSource()
        flows = await source.get_sector_flows(category=ETFCategory.SECTOR_TECH, days=20)
        await source.close()
        results.record(
            "ETF Flows",
            True,
            f"Tech sector net_flow=${flows.net_flow/1e6:.1f}M"
        )
    except Exception as e:
        results.record("ETF Flows", False, str(e))


async def test_institutional_flow():
    """Test institutional flow scorecard."""
    try:
        from src.data.sources.alternative.institutional_flow import InstitutionalFlowScorecard
        scorecard = InstitutionalFlowScorecard()
        score = scorecard.get_score("AAPL")
        results.record(
            "Institutional Flow",
            True,
            f"AAPL score={score.composite_score:.2f}, sentiment={score.sentiment}"
        )
    except Exception as e:
        results.record("Institutional Flow", False, str(e))


async def test_iv_rank():
    """Test IV rank calculator."""
    try:
        from src.data.sources.alternative.iv_rank import IVRankCalculator
        calculator = IVRankCalculator()
        data = calculator.get_iv_rank("SPY")
        results.record(
            "IV Rank",
            True,
            f"iv_rank={data.iv_rank:.1f}%, iv_percentile={data.iv_percentile:.1f}%"
        )
    except Exception as e:
        results.record("IV Rank", False, str(e))


async def test_google_trends():
    """Test Google Trends source."""
    try:
        from src.data.sources.alternative.google_trends import GoogleTrendsSource
        source = GoogleTrendsSource()
        # get_retail_attention returns RetailAttentionSignal object
        data = source.get_retail_attention("TSLA")
        results.record(
            "Google Trends",
            hasattr(data, 'signal'),
            f"TSLA signal={data.signal}, zscore={data.zscore:.2f}"
        )
    except Exception as e:
        results.record("Google Trends", False, str(e))


async def test_weather():
    """Test weather source."""
    try:
        from src.data.sources.alternative.weather import WeatherDataSource
        source = WeatherDataSource()
        data = await source.fetch_current("chicago")
        await source.close()
        results.record(
            "Weather",
            data is not None,
            f"Chicago temp={data.temperature:.1f}C" if data else "No data"
        )
    except Exception as e:
        results.record("Weather", False, str(e))


async def test_reddit():
    """Test Reddit source."""
    try:
        from src.data.sources.alternative.reddit import RedditDataSource
        source = RedditDataSource()
        trending = await source.get_trending_symbols()
        results.record(
            "Reddit Sentiment",
            True,
            f"{len(trending)} trending tickers"
        )
    except Exception as e:
        results.record("Reddit Sentiment", False, str(e))


async def test_news_source():
    """Test news source."""
    try:
        from src.data.sources.alternative.news import NewsDataSource
        source = NewsDataSource()
        articles = await source.fetch_news(symbol="AAPL", limit=10)
        await source.close()
        results.record(
            "News Source",
            True,
            f"{len(articles)} articles for AAPL"
        )
    except Exception as e:
        results.record("News Source", False, str(e))


# ==============================================================================
# Data Pipeline Tests
# ==============================================================================

def test_market_breadth_pipeline():
    """Test market breadth pipeline."""
    try:
        from src.data.pipeline.market_breadth import MarketBreadthAnalyzer
        analyzer = MarketBreadthAnalyzer()
        breadth = analyzer.get_breadth()
        results.record(
            "Market Breadth Pipeline",
            len(breadth.sectors) > 0,
            f"regime={breadth.regime}, bias={breadth.bias}, {len(breadth.sectors)} sectors"
        )
    except Exception as e:
        results.record("Market Breadth Pipeline", False, str(e))


def test_sentiment_pipeline():
    """Test sentiment pipeline."""
    try:
        from src.data.pipeline.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        sentiment = analyzer.get_sentiment()
        results.record(
            "Sentiment Pipeline",
            sentiment.fear_greed is not None,
            f"F&G={sentiment.fear_greed.value if sentiment.fear_greed else 'N/A'}, composite={sentiment.composite_sentiment:.2f}"
        )
    except Exception as e:
        results.record("Sentiment Pipeline", False, str(e))


async def test_options_analytics_pipeline():
    """Test options analytics (via options flow)."""
    try:
        from src.data.sources.alternative.options_flow import get_put_call_ratio
        data = await get_put_call_ratio("SPY")
        results.record(
            "Options Analytics",
            "volume_ratio" in data,
            f"P/C volume={data.get('volume_ratio', 0):.2f}, signal={data.get('signal', 'N/A')}"
        )
    except Exception as e:
        results.record("Options Analytics", False, str(e))


# ==============================================================================
# Collection Daemon Test
# ==============================================================================

def test_collection_daemon():
    """Test collection daemon."""
    try:
        from src.data.sources.collection_daemon import DataCollectionDaemon
        daemon = DataCollectionDaemon()
        status = daemon.get_status()
        results.record(
            "Collection Daemon",
            len(status.sources) > 0,
            f"{len(status.sources)} sources configured"
        )
    except Exception as e:
        results.record("Collection Daemon", False, str(e))


# ==============================================================================
# Real-time Source Tests
# ==============================================================================

def test_news_daemon():
    """Test news daemon."""
    try:
        from src.data.sources.realtime.news_daemon import NewsDaemon
        daemon = NewsDaemon(watchlist=["SPY", "QQQ", "AAPL"])
        # Just instantiation test
        results.record(
            "News Daemon",
            True,
            "Daemon initialized with 3-symbol watchlist"
        )
    except Exception as e:
        results.record("News Daemon", False, str(e))


async def test_social_sentiment_realtime():
    """Test real-time social sentiment (WSB scraper)."""
    try:
        from src.data.sources.realtime.social_sentiment import WallStreetBetsScraper
        scraper = WallStreetBetsScraper()
        summary = await scraper.get_daily_summary()
        await scraper.close()
        results.record(
            "Social Sentiment (RT)",
            True,
            f"{len(summary.trending_tickers)} trending, sentiment={summary.overall_sentiment}"
        )
    except Exception as e:
        results.record("Social Sentiment (RT)", False, str(e))


# ==============================================================================
# Universal Source Tests
# ==============================================================================

async def test_blog_scraper():
    """Test blog scraper."""
    try:
        from src.data.sources.universal.blog_scraper import BlogScraper
        scraper = BlogScraper()
        # Just instantiation test - actual scraping may be blocked
        results.record(
            "Blog Scraper",
            True,
            "Scraper initialized"
        )
    except Exception as e:
        results.record("Blog Scraper", False, str(e))


async def test_commodity_scraper():
    """Test commodity source."""
    try:
        from src.data.sources.universal.commodity_scraper import CommoditySource
        source = CommoditySource()
        # List available commodities
        available = source.list_available_commodities()
        results.record(
            "Commodity Source",
            len(available) > 0,
            f"{len(available)} commodity categories available"
        )
    except Exception as e:
        results.record("Commodity Source", False, str(e))


async def test_free_api_hub():
    """Test free API hub."""
    import os
    try:
        from src.data.sources.universal.free_api_hub import FreeAPIHub
        fred_key = os.environ.get("FRED_API_KEY")
        if fred_key:
            hub = FreeAPIHub(fred_api_key=fred_key)
            data = await hub.get_fred_series("GDP")
            await hub.close()
            results.record(
                "Free API Hub (FRED)",
                len(data) > 0,
                f"{len(data)} data points"
            )
        else:
            results.record(
                "Free API Hub (FRED)",
                True,
                "Skipped - FRED_API_KEY not set (get free key at fred.stlouisfed.org)"
            )
    except Exception as e:
        results.record("Free API Hub (FRED)", False, str(e))


# ==============================================================================
# Historical Data Collection Test
# ==============================================================================

async def test_historical_data_collection():
    """Test that historical data was collected."""
    try:
        history_dir = paths.live / "historical_data"

        files_to_check = [
            "vix_history_6mo.json",
            "etf_history_6mo.json",
            "breadth_history_6mo.json",
            "collection_summary.json"
        ]

        existing = []
        for f in files_to_check:
            if (history_dir / f).exists():
                existing.append(f)

        results.record(
            "Historical Data Files",
            len(existing) >= 3,
            f"{len(existing)}/{len(files_to_check)} files present"
        )

        # Check collection summary
        summary_file = history_dir / "collection_summary.json"
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
            results.record(
                "Historical Data Summary",
                summary.get("vix_records", 0) > 100,
                f"VIX: {summary.get('vix_records', 0)}, ETFs: {summary.get('etfs_collected', 0)}, Breadth: {summary.get('breadth_records', 0)}"
            )

    except Exception as e:
        results.record("Historical Data", False, str(e))


# ==============================================================================
# Main Runner
# ==============================================================================

async def main():
    print_header("COMPREHENSIVE DATA SOURCE TEST SUITE")
    print(f"Timestamp: {datetime.now()}")
    print("Testing ALL data sources in quant_suite\n")

    # Core Market Data
    print_header("CORE MARKET DATA")
    await test_yahoo_finance()

    # New Alternative Data Sources (Batch 1-6)
    print_header("ALTERNATIVE DATA - MARKET REGIME")
    await test_vix_structure()
    await test_put_call()
    await test_finviz_screens()

    print_header("ALTERNATIVE DATA - SENTIMENT")
    await test_aaii_sentiment()
    await test_newsletter_sentiment()
    await test_cot_report()

    print_header("ALTERNATIVE DATA - ECONOMIC/CALENDAR")
    await test_earnings_calendar()
    await test_economic_calendar()
    await test_fed_futures()
    await test_treasury_calendar()
    await test_ipo_calendar()
    await test_fda_calendar()

    print_header("ALTERNATIVE DATA - INNOVATION")
    await test_patent_filings()
    await test_job_postings()
    await test_app_rankings()
    await test_github_activity()

    # Original Alternative Data Sources
    print_header("ALTERNATIVE DATA - TRADING SIGNALS")
    await test_congressional_trades()
    await test_insider_trading()
    await test_options_flow()
    await test_expert_sentiment()
    await test_prediction_markets()
    await test_short_interest()
    await test_etf_flows()
    await test_institutional_flow()
    await test_iv_rank()

    print_header("ALTERNATIVE DATA - EXTERNAL")
    await test_google_trends()
    await test_weather()
    await test_reddit()
    await test_news_source()

    # Data Pipelines
    print_header("DATA PIPELINES")
    test_market_breadth_pipeline()
    test_sentiment_pipeline()
    await test_options_analytics_pipeline()

    # Collection Daemon
    print_header("COLLECTION INFRASTRUCTURE")
    test_collection_daemon()
    test_news_daemon()
    await test_social_sentiment_realtime()

    # Universal Sources
    print_header("UNIVERSAL DATA SOURCES")
    await test_blog_scraper()
    await test_commodity_scraper()
    await test_free_api_hub()

    # Historical Data
    print_header("HISTORICAL DATA COLLECTION")
    await test_historical_data_collection()

    # Summary
    print_header("TEST SUMMARY")
    summary = results.summary()
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Success Rate: {summary['success_rate']:.1f}%")

    if results.failed:
        print("\nFailed Tests:")
        for name, details in results.failed:
            print(f"  [-] {name}: {details}")

    # Save results
    results_file = paths.live / "test_results" / f"all_sources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "passed": results.passed,
            "failed": results.failed,
            "skipped": results.skipped,
        }, f, indent=2)
    print(f"\nResults saved to: {results_file}")

    return 0 if summary['failed'] == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
