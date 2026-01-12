#!/usr/bin/env python3
"""
Full Data Collection Pipeline Test

Tests all data sources and attempts historical backfill where feasible.
Generates a comprehensive report on data availability.

Usage:
    PYTHONPATH=. python scripts/test_full_data_pipeline.py
    PYTHONPATH=. python scripts/test_full_data_pipeline.py --backfill --months 3
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Ensure proper path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SourceTestResult:
    """Result of testing a data source."""
    name: str
    success: bool
    current_data: bool = False
    historical_data: bool = False
    records_current: int = 0
    records_historical: int = 0
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    error: Optional[str] = None
    notes: str = ""
    sample_data: Optional[dict] = None


@dataclass
class PipelineTestReport:
    """Full pipeline test report."""
    timestamp: datetime = field(default_factory=datetime.now)
    sources_tested: int = 0
    sources_passed: int = 0
    sources_with_history: int = 0
    total_current_records: int = 0
    total_historical_records: int = 0
    results: list[SourceTestResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "sources_tested": self.sources_tested,
            "sources_passed": self.sources_passed,
            "sources_with_history": self.sources_with_history,
            "total_current_records": self.total_current_records,
            "total_historical_records": self.total_historical_records,
            "results": [
                {
                    "name": r.name,
                    "success": r.success,
                    "current_data": r.current_data,
                    "historical_data": r.historical_data,
                    "records_current": r.records_current,
                    "records_historical": r.records_historical,
                    "date_range_start": r.date_range_start.isoformat() if r.date_range_start else None,
                    "date_range_end": r.date_range_end.isoformat() if r.date_range_end else None,
                    "error": r.error,
                    "notes": r.notes,
                }
                for r in self.results
            ]
        }


class DataPipelineTester:
    """Test and backfill data pipeline."""

    def __init__(self, backfill_months: int = 3):
        self.backfill_months = backfill_months
        self.start_date = datetime.now() - timedelta(days=backfill_months * 30)
        self.end_date = datetime.now()
        self.results: list[SourceTestResult] = []

        # Ensure cache directories exist
        self.cache_dir = paths.live / "data_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir = paths.live / "historical_data"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    async def run_full_test(self) -> PipelineTestReport:
        """Run comprehensive test of all data sources."""
        logger.info("=" * 60)
        logger.info("DATA COLLECTION PIPELINE TEST")
        logger.info(f"Testing period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info("=" * 60)

        # Test each category
        await self._test_market_regime_sources()
        await self._test_sentiment_sources()
        await self._test_economic_sources()
        await self._test_event_sources()
        await self._test_innovation_sources()
        await self._test_collection_daemon()

        # Generate report
        report = self._generate_report()

        # Save report
        self._save_report(report)

        return report

    async def _test_market_regime_sources(self):
        """Test market regime data sources."""
        logger.info("\n--- MARKET REGIME SOURCES ---")

        # 1. VIX Term Structure
        await self._test_vix_structure()

        # 2. Put/Call Ratio
        await self._test_put_call()

        # 3. Finviz Screens
        await self._test_finviz_screens()

    async def _test_vix_structure(self):
        """Test VIX term structure source."""
        try:
            from src.data.sources.alternative.vix_structure import (
                VIXStructureSource, get_vix_structure
            )

            source = VIXStructureSource()
            structure = await source.get_structure()

            result = SourceTestResult(
                name="VIX Term Structure",
                success=True,
                current_data=True,
                records_current=1,
                date_range_end=structure.timestamp,
                sample_data={
                    "vix_spot": structure.vix_spot,
                    "slope_3m": structure.slope_3m,
                    "structure": structure.structure,
                    "signal": structure.mean_reversion_signal,
                },
                notes="Real-time VIX data from Yahoo Finance"
            )

            # Attempt historical backfill using yfinance
            historical = await self._backfill_vix_history()
            if historical:
                result.historical_data = True
                result.records_historical = len(historical)
                result.date_range_start = historical[0]["date"] if historical else None

            logger.info(f"  VIX Structure: PASS (slope={structure.slope:.3f}, structure={structure.structure})")

        except Exception as e:
            result = SourceTestResult(
                name="VIX Term Structure",
                success=False,
                error=str(e)
            )
            logger.error(f"  VIX Structure: FAIL - {e}")

        self.results.append(result)

    async def _backfill_vix_history(self) -> list[dict]:
        """Backfill VIX historical data."""
        try:
            import yfinance as yf

            # Get VIX spot history
            vix = yf.Ticker("^VIX")
            hist = vix.history(period=f"{self.backfill_months}mo")

            if hist.empty:
                return []

            history = []
            for date, row in hist.iterrows():
                history.append({
                    "date": date.to_pydatetime(),
                    "vix_spot": row["Close"],
                    "high": row["High"],
                    "low": row["Low"],
                })

            # Save to history file
            history_file = self.history_dir / "vix_history.json"
            with open(history_file, "w") as f:
                json.dump([
                    {**h, "date": h["date"].isoformat()}
                    for h in history
                ], f, indent=2)

            logger.info(f"    Backfilled {len(history)} VIX records")
            return history

        except Exception as e:
            logger.warning(f"    VIX backfill failed: {e}")
            return []

    async def _test_put_call(self):
        """Test put/call ratio source."""
        try:
            from src.data.sources.alternative.put_call import (
                PutCallSource, get_put_call_data
            )

            source = PutCallSource()
            data = await source.get_put_call()

            result = SourceTestResult(
                name="Put/Call Ratio",
                success=True,
                current_data=True,
                records_current=1,
                date_range_end=data.timestamp,
                sample_data={
                    "total_ratio": data.total_ratio,
                    "equity_ratio": data.equity_ratio,
                    "signal": data.signal,
                    "contrarian_signal": data.contrarian_signal,
                },
                notes="CBOE put/call ratio data"
            )

            eq_ratio = data.equity_ratio or data.total_ratio
            logger.info(f"  Put/Call Ratio: PASS (ratio={eq_ratio:.2f}, signal={data.signal})")

        except Exception as e:
            result = SourceTestResult(
                name="Put/Call Ratio",
                success=False,
                error=str(e)
            )
            logger.error(f"  Put/Call Ratio: FAIL - {e}")

        self.results.append(result)

    async def _test_finviz_screens(self):
        """Test Finviz screener source."""
        try:
            from src.data.sources.alternative.finviz_screens import (
                FinvizScreener, get_finviz_screens
            )

            screener = FinvizScreener()
            screens = await screener.get_screens()

            total_symbols = sum(len(s.symbols) for s in screens.screens.values())

            result = SourceTestResult(
                name="Finviz Screens",
                success=True,
                current_data=True,
                records_current=total_symbols,
                date_range_end=screens.timestamp,
                sample_data={
                    "screens_run": len(screens.screens),
                    "total_symbols": total_symbols,
                    "screens": list(screens.screens.keys()),
                },
                notes="Pre-built stock screener results"
            )

            logger.info(f"  Finviz Screens: PASS ({len(screens.screens)} screens, {total_symbols} total symbols)")

        except Exception as e:
            result = SourceTestResult(
                name="Finviz Screens",
                success=False,
                error=str(e)
            )
            logger.error(f"  Finviz Screens: FAIL - {e}")

        self.results.append(result)

    async def _test_sentiment_sources(self):
        """Test sentiment data sources."""
        logger.info("\n--- SENTIMENT SOURCES ---")

        # 1. AAII Sentiment
        await self._test_aaii_sentiment()

        # 2. Newsletter Sentiment
        await self._test_newsletter_sentiment()

        # 3. COT Report
        await self._test_cot_report()

    async def _test_aaii_sentiment(self):
        """Test AAII sentiment source."""
        try:
            from src.data.sources.alternative.aaii_sentiment import (
                AAIISentimentSource, get_aaii_sentiment
            )

            source = AAIISentimentSource()
            data = await source.get_sentiment()

            result = SourceTestResult(
                name="AAII Sentiment",
                success=True,
                current_data=True,
                records_current=1,
                date_range_end=data.survey_date,
                sample_data={
                    "bullish_pct": data.bullish_pct,
                    "bearish_pct": data.bearish_pct,
                    "bull_bear_spread": data.bull_bear_spread,
                    "contrarian_signal": data.contrarian_signal,
                },
                notes="Weekly retail investor sentiment survey"
            )

            # Check for historical data
            if source._history:
                result.historical_data = True
                result.records_historical = len(source._history)
                result.date_range_start = source._history[0][0] if source._history else None

            logger.info(f"  AAII Sentiment: PASS (bullish={data.bullish_pct:.1f}%, bearish={data.bearish_pct:.1f}%)")

        except Exception as e:
            result = SourceTestResult(
                name="AAII Sentiment",
                success=False,
                error=str(e)
            )
            logger.error(f"  AAII Sentiment: FAIL - {e}")

        self.results.append(result)

    async def _test_newsletter_sentiment(self):
        """Test newsletter sentiment source."""
        try:
            from src.data.sources.alternative.newsletter_sentiment import (
                NewsletterSentimentSource, get_newsletter_sentiment
            )

            source = NewsletterSentimentSource()
            data = await source.get_sentiment()

            result = SourceTestResult(
                name="Newsletter Sentiment",
                success=True,
                current_data=True,
                records_current=1,
                date_range_end=data.survey_date,
                sample_data={
                    "bulls_pct": data.bulls_pct,
                    "bears_pct": data.bears_pct,
                    "bull_bear_spread": data.bull_bear_spread,
                    "contrarian_signal": data.contrarian_signal,
                },
                notes="Investors Intelligence advisor sentiment"
            )

            logger.info(f"  Newsletter Sentiment: PASS (bulls={data.bulls_pct:.1f}%)")

        except Exception as e:
            result = SourceTestResult(
                name="Newsletter Sentiment",
                success=False,
                error=str(e)
            )
            logger.error(f"  Newsletter Sentiment: FAIL - {e}")

        self.results.append(result)

    async def _test_cot_report(self):
        """Test COT report source."""
        try:
            from src.data.sources.alternative.cot_report import (
                COTSource, get_cot_report
            )

            source = COTSource()
            report = await source.get_report()

            result = SourceTestResult(
                name="COT Report",
                success=True,
                current_data=True,
                records_current=len(report.positions),
                date_range_end=report.report_date,
                sample_data={
                    "contracts_tracked": list(report.positions.keys()),
                    "equity_signal": report.equity_signal,
                    "commodity_signal": report.commodity_signal,
                    "risk_appetite": report.overall_risk_appetite,
                },
                notes="CFTC Commitment of Traders data"
            )

            # Check for historical data
            if source._history:
                total_history = sum(len(h) for h in source._history.values())
                result.historical_data = total_history > 0
                result.records_historical = total_history

            logger.info(f"  COT Report: PASS ({len(report.positions)} contracts, equity_signal={report.equity_signal:.2f})")

        except Exception as e:
            result = SourceTestResult(
                name="COT Report",
                success=False,
                error=str(e)
            )
            logger.error(f"  COT Report: FAIL - {e}")

        self.results.append(result)

    async def _test_economic_sources(self):
        """Test economic calendar sources."""
        logger.info("\n--- ECONOMIC SOURCES ---")

        # 1. Earnings Calendar
        await self._test_earnings_calendar()

        # 2. Economic Calendar
        await self._test_economic_calendar()

        # 3. Fed Futures
        await self._test_fed_futures()

        # 4. Treasury Calendar
        await self._test_treasury_calendar()

    async def _test_earnings_calendar(self):
        """Test earnings calendar source."""
        try:
            from src.data.sources.alternative.earnings_calendar import (
                EarningsCalendarSource, get_earnings_calendar
            )

            source = EarningsCalendarSource()
            calendar = await source.get_calendar()

            upcoming = [e for e in calendar.events if e.report_date > datetime.now()]

            result = SourceTestResult(
                name="Earnings Calendar",
                success=True,
                current_data=True,
                records_current=len(calendar.events),
                date_range_end=calendar.end_date,
                date_range_start=calendar.start_date,
                sample_data={
                    "total_events": len(calendar.events),
                    "upcoming_events": len(upcoming),
                    "next_earnings": [
                        {"symbol": e.symbol, "date": e.report_date.isoformat()}
                        for e in upcoming[:5]
                    ] if upcoming else [],
                },
                notes="Earnings dates with whisper numbers"
            )

            logger.info(f"  Earnings Calendar: PASS ({len(calendar.events)} events, {len(upcoming)} upcoming)")

        except Exception as e:
            result = SourceTestResult(
                name="Earnings Calendar",
                success=False,
                error=str(e)
            )
            logger.error(f"  Earnings Calendar: FAIL - {e}")

        self.results.append(result)

    async def _test_economic_calendar(self):
        """Test economic calendar source."""
        try:
            from src.data.sources.alternative.economic_calendar import (
                EconomicCalendarSource, get_economic_calendar
            )

            source = EconomicCalendarSource()
            calendar = await source.get_calendar()

            high_impact = [r for r in calendar.releases if r.importance == "high"]

            result = SourceTestResult(
                name="Economic Calendar",
                success=True,
                current_data=True,
                records_current=len(calendar.releases),
                date_range_end=calendar.end_date,
                date_range_start=calendar.start_date,
                sample_data={
                    "total_releases": len(calendar.releases),
                    "high_impact": len(high_impact),
                    "next_high_impact": [
                        {"name": r.name, "date": r.release_date.isoformat()}
                        for r in high_impact[:5]
                    ] if high_impact else [],
                },
                notes="BLS, Fed, Treasury release schedule"
            )

            logger.info(f"  Economic Calendar: PASS ({len(calendar.releases)} releases, {len(high_impact)} high-impact)")

        except Exception as e:
            result = SourceTestResult(
                name="Economic Calendar",
                success=False,
                error=str(e)
            )
            logger.error(f"  Economic Calendar: FAIL - {e}")

        self.results.append(result)

    async def _test_fed_futures(self):
        """Test Fed futures source."""
        try:
            from src.data.sources.alternative.fed_futures import (
                FedFuturesSource, get_fed_expectations
            )

            source = FedFuturesSource()
            expectations = await source.get_expectations()

            result = SourceTestResult(
                name="Fed Futures",
                success=True,
                current_data=True,
                records_current=len(expectations.meetings),
                date_range_end=expectations.timestamp,
                sample_data={
                    "current_rate": expectations.current_rate,
                    "next_meeting": expectations.next_meeting.meeting_date.isoformat(),
                    "prob_cut": expectations.prob_cut,
                    "prob_hold": expectations.prob_hold,
                    "prob_hike": expectations.prob_hike,
                    "rate_path_signal": expectations.rate_path_signal,
                    "implied_rate_12m": expectations.implied_rate_12m,
                },
                notes="CME FedWatch rate expectations"
            )

            logger.info(f"  Fed Futures: PASS (path={expectations.rate_path_signal}, 12m_rate={expectations.implied_rate_12m:.2f}%)")

        except Exception as e:
            result = SourceTestResult(
                name="Fed Futures",
                success=False,
                error=str(e)
            )
            logger.error(f"  Fed Futures: FAIL - {e}")

        self.results.append(result)

    async def _test_treasury_calendar(self):
        """Test Treasury calendar source."""
        try:
            from src.data.sources.alternative.treasury_calendar import (
                TreasuryCalendarSource, get_treasury_calendar
            )

            source = TreasuryCalendarSource()
            calendar = await source.get_calendar()

            high_impact = [a for a in calendar.auctions if a.security_type in ("10-Year", "30-Year")]

            result = SourceTestResult(
                name="Treasury Calendar",
                success=True,
                current_data=True,
                records_current=len(calendar.auctions),
                date_range_end=calendar.end_date,
                date_range_start=calendar.start_date,
                sample_data={
                    "total_auctions": len(calendar.auctions),
                    "high_impact": len(high_impact),
                    "total_issuance": sum(a.amount for a in calendar.auctions),
                },
                notes="Treasury auction schedule"
            )

            logger.info(f"  Treasury Calendar: PASS ({len(calendar.auctions)} auctions)")

        except Exception as e:
            result = SourceTestResult(
                name="Treasury Calendar",
                success=False,
                error=str(e)
            )
            logger.error(f"  Treasury Calendar: FAIL - {e}")

        self.results.append(result)

    async def _test_event_sources(self):
        """Test event catalyst sources."""
        logger.info("\n--- EVENT CATALYST SOURCES ---")

        # 1. IPO Calendar
        await self._test_ipo_calendar()

        # 2. FDA Calendar
        await self._test_fda_calendar()

    async def _test_ipo_calendar(self):
        """Test IPO calendar source."""
        try:
            from src.data.sources.alternative.ipo_calendar import (
                IPOCalendarSource, get_ipo_calendar
            )

            source = IPOCalendarSource()
            calendar = await source.get_calendar()

            result = SourceTestResult(
                name="IPO Calendar",
                success=True,
                current_data=True,
                records_current=len(calendar.events),
                date_range_end=calendar.end_date,
                date_range_start=calendar.start_date,
                sample_data={
                    "total_ipos": len(calendar.events),
                    "upcoming": [
                        {"company": e.company_name, "date": e.expected_date.isoformat()}
                        for e in calendar.events[:5]
                    ] if calendar.events else [],
                },
                notes="NASDAQ IPO calendar"
            )

            logger.info(f"  IPO Calendar: PASS ({len(calendar.events)} IPOs)")

        except Exception as e:
            result = SourceTestResult(
                name="IPO Calendar",
                success=False,
                error=str(e)
            )
            logger.error(f"  IPO Calendar: FAIL - {e}")

        self.results.append(result)

    async def _test_fda_calendar(self):
        """Test FDA calendar source."""
        try:
            from src.data.sources.alternative.fda_calendar import (
                FDACalendarSource, get_fda_calendar
            )

            source = FDACalendarSource()
            calendar = await source.get_calendar()

            pdufa_events = [e for e in calendar.events if e.event_type == "PDUFA"]

            result = SourceTestResult(
                name="FDA Calendar",
                success=True,
                current_data=True,
                records_current=len(calendar.events),
                date_range_end=calendar.end_date,
                date_range_start=calendar.start_date,
                sample_data={
                    "total_events": len(calendar.events),
                    "pdufa_dates": len(pdufa_events),
                    "upcoming_pdufa": [
                        {"symbol": e.symbol, "drug": e.drug_name, "date": e.expected_date.isoformat()}
                        for e in pdufa_events[:5]
                    ] if pdufa_events else [],
                },
                notes="FDA PDUFA dates and AdCom meetings"
            )

            logger.info(f"  FDA Calendar: PASS ({len(calendar.events)} events, {len(pdufa_events)} PDUFA)")

        except Exception as e:
            result = SourceTestResult(
                name="FDA Calendar",
                success=False,
                error=str(e)
            )
            logger.error(f"  FDA Calendar: FAIL - {e}")

        self.results.append(result)

    async def _test_innovation_sources(self):
        """Test innovation signal sources."""
        logger.info("\n--- INNOVATION SOURCES ---")

        # 1. Patent Filings
        await self._test_patents()

        # 2. Job Postings
        await self._test_job_postings()

        # 3. App Rankings
        await self._test_app_rankings()

        # 4. GitHub Activity
        await self._test_github()

    async def _test_patents(self):
        """Test USPTO patent source."""
        try:
            from src.data.sources.alternative.patent_filings import (
                USPTOSource, get_patent_activity
            )

            source = USPTOSource()
            activity = await source.get_activity(["AAPL", "MSFT", "GOOGL"])

            result = SourceTestResult(
                name="Patent Filings",
                success=True,
                current_data=True,
                records_current=len(activity),
                date_range_end=datetime.now(),
                sample_data={
                    "companies_tracked": list(activity.keys()),
                    "sample": {k: v.patents_filed for k, v in list(activity.items())[:3]} if activity else {},
                },
                notes="USPTO patent activity by company"
            )

            logger.info(f"  Patent Filings: PASS ({len(activity)} companies)")

        except Exception as e:
            result = SourceTestResult(
                name="Patent Filings",
                success=False,
                error=str(e)
            )
            logger.error(f"  Patent Filings: FAIL - {e}")

        self.results.append(result)

    async def _test_job_postings(self):
        """Test job postings source."""
        try:
            from src.data.sources.alternative.job_postings import (
                JobPostingSource, get_job_postings
            )

            source = JobPostingSource()
            postings = await source.get_postings(["AAPL", "MSFT", "GOOGL"])

            result = SourceTestResult(
                name="Job Postings",
                success=True,
                current_data=True,
                records_current=len(postings),
                date_range_end=datetime.now(),
                sample_data={
                    "companies_tracked": list(postings.keys()),
                    "sample": {k: v.total_openings for k, v in list(postings.items())[:3]} if postings else {},
                },
                notes="Job posting growth signals"
            )

            logger.info(f"  Job Postings: PASS ({len(postings)} companies)")

        except Exception as e:
            result = SourceTestResult(
                name="Job Postings",
                success=False,
                error=str(e)
            )
            logger.error(f"  Job Postings: FAIL - {e}")

        self.results.append(result)

    async def _test_app_rankings(self):
        """Test app rankings source."""
        try:
            from src.data.sources.alternative.app_rankings import (
                AppRankingSource, get_app_rankings
            )

            source = AppRankingSource()
            rankings = await source.get_rankings()

            result = SourceTestResult(
                name="App Rankings",
                success=True,
                current_data=True,
                records_current=len(rankings),
                date_range_end=datetime.now(),
                sample_data={
                    "companies_tracked": list(rankings.keys()),
                    "sample": {
                        k: {
                            "avg_rank": v.average_rank,
                            "momentum": v.momentum_signal
                        }
                        for k, v in list(rankings.items())[:3]
                    } if rankings else {},
                },
                notes="App Store/Play rankings"
            )

            logger.info(f"  App Rankings: PASS ({len(rankings)} companies)")

        except Exception as e:
            result = SourceTestResult(
                name="App Rankings",
                success=False,
                error=str(e)
            )
            logger.error(f"  App Rankings: FAIL - {e}")

        self.results.append(result)

    async def _test_github(self):
        """Test GitHub activity source."""
        try:
            from src.data.sources.alternative.github_activity import (
                GitHubSource, get_github_activity
            )

            source = GitHubSource()
            activity = await source.get_activity(["MSFT", "GOOGL", "META"])

            result = SourceTestResult(
                name="GitHub Activity",
                success=True,
                current_data=True,
                records_current=len(activity),
                date_range_end=datetime.now(),
                sample_data={
                    "companies_tracked": list(activity.keys()),
                    "sample": {
                        k: {
                            "stars": v.total_stars,
                            "repos": v.public_repos,
                            "signal": v.developer_interest_signal
                        }
                        for k, v in list(activity.items())[:3]
                    } if activity else {},
                },
                notes="GitHub organization metrics"
            )

            logger.info(f"  GitHub Activity: PASS ({len(activity)} companies)")

        except Exception as e:
            result = SourceTestResult(
                name="GitHub Activity",
                success=False,
                error=str(e)
            )
            logger.error(f"  GitHub Activity: FAIL - {e}")

        self.results.append(result)

    async def _test_collection_daemon(self):
        """Test the collection daemon."""
        logger.info("\n--- COLLECTION DAEMON ---")

        try:
            from src.data.sources.collection_daemon import DataCollectionDaemon

            daemon = DataCollectionDaemon()

            # Get status
            status = await daemon.get_collection_status()

            # Run one collection cycle
            logger.info("  Running full collection cycle...")
            results = await daemon.collect_all_now()

            passed = sum(1 for v in results.values() if v.get("success", False))
            failed = len(results) - passed

            result = SourceTestResult(
                name="Collection Daemon",
                success=passed > 0,
                current_data=True,
                records_current=passed,
                sample_data={
                    "sources_configured": len(daemon.SCHEDULES),
                    "collection_results": {k: v.get("success", False) for k, v in results.items()},
                    "passed": passed,
                    "failed": failed,
                },
                notes=f"Orchestrated {passed}/{len(results)} sources successfully"
            )

            logger.info(f"  Collection Daemon: PASS ({passed}/{len(results)} sources collected)")

            # Show any failures
            for source_name, source_result in results.items():
                if not source_result.get("success", False):
                    logger.warning(f"    {source_name}: {source_result.get('error', 'Unknown error')}")

        except Exception as e:
            result = SourceTestResult(
                name="Collection Daemon",
                success=False,
                error=str(e)
            )
            logger.error(f"  Collection Daemon: FAIL - {e}")

        self.results.append(result)

    def _generate_report(self) -> PipelineTestReport:
        """Generate summary report."""
        passed = sum(1 for r in self.results if r.success)
        with_history = sum(1 for r in self.results if r.historical_data)
        current_records = sum(r.records_current for r in self.results)
        historical_records = sum(r.records_historical for r in self.results)

        report = PipelineTestReport(
            sources_tested=len(self.results),
            sources_passed=passed,
            sources_with_history=with_history,
            total_current_records=current_records,
            total_historical_records=historical_records,
            results=self.results,
        )

        return report

    def _save_report(self, report: PipelineTestReport):
        """Save report to file."""
        report_file = self.cache_dir / "pipeline_test_report.json"
        with open(report_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"\nReport saved to: {report_file}")

    def print_summary(self, report: PipelineTestReport):
        """Print summary to console."""
        print("\n" + "=" * 60)
        print("DATA PIPELINE TEST SUMMARY")
        print("=" * 60)
        print(f"Timestamp: {report.timestamp}")
        print(f"Sources Tested: {report.sources_tested}")
        print(f"Sources Passed: {report.sources_passed}/{report.sources_tested}")
        print(f"Sources with History: {report.sources_with_history}")
        print(f"Current Records: {report.total_current_records}")
        print(f"Historical Records: {report.total_historical_records}")
        print()

        # Show results table
        print("RESULTS:")
        print("-" * 60)
        print(f"{'Source':<25} {'Status':<8} {'Current':<10} {'Historical':<10}")
        print("-" * 60)

        for r in report.results:
            status = "PASS" if r.success else "FAIL"
            current = str(r.records_current) if r.current_data else "-"
            historical = str(r.records_historical) if r.historical_data else "-"
            print(f"{r.name:<25} {status:<8} {current:<10} {historical:<10}")

        print("-" * 60)

        # Show failures
        failures = [r for r in report.results if not r.success]
        if failures:
            print("\nFAILURES:")
            for r in failures:
                print(f"  {r.name}: {r.error}")

        print()


async def main():
    parser = argparse.ArgumentParser(description="Test data collection pipeline")
    parser.add_argument("--backfill", action="store_true", help="Attempt historical backfill")
    parser.add_argument("--months", type=int, default=3, help="Months of history to backfill")
    args = parser.parse_args()

    tester = DataPipelineTester(backfill_months=args.months)
    report = await tester.run_full_test()
    tester.print_summary(report)

    # Return exit code based on results
    if report.sources_passed == report.sources_tested:
        print("All tests passed!")
        return 0
    else:
        print(f"{report.sources_tested - report.sources_passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
