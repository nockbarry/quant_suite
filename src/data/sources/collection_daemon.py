"""
Data Collection Daemon

Orchestrates collection of all free data sources with appropriate schedules.
Runs alongside LiveDaemon to keep alternative data fresh.

Different sources have different update frequencies:
- Real-time (5-15 min): VIX structure, breadth, put/call
- Hourly: Fed futures
- Daily: Finviz screens, earnings calendar, sentiment surveys
- Weekly: COT report, patent data

Each source has its own rate limiting and caching to avoid
overloading free data providers.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any

from src.core.paths import paths

logger = logging.getLogger(__name__)


class UpdateFrequency(str, Enum):
    """How often to update each data source."""
    REALTIME = "realtime"  # Every 5-15 minutes
    HOURLY = "hourly"
    FOUR_HOURS = "4h"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class SourceConfig:
    """Configuration for a data source."""

    name: str
    frequency: UpdateFrequency
    interval_minutes: int
    market_hours_only: bool = True
    enabled: bool = True
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0


@dataclass
class CollectionStatus:
    """Status of all data collection."""

    timestamp: datetime
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    is_market_hours: bool = False
    total_collections_today: int = 0
    errors_today: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "sources": {
                name: {
                    "frequency": cfg.frequency.value,
                    "interval_minutes": cfg.interval_minutes,
                    "market_hours_only": cfg.market_hours_only,
                    "enabled": cfg.enabled,
                    "last_success": cfg.last_success.isoformat() if cfg.last_success else None,
                    "last_error": cfg.last_error,
                    "consecutive_failures": cfg.consecutive_failures,
                }
                for name, cfg in self.sources.items()
            },
            "is_market_hours": self.is_market_hours,
            "total_collections_today": self.total_collections_today,
            "errors_today": self.errors_today,
        }


class DataCollectionDaemon:
    """
    Orchestrates collection of all free data sources.

    Runs as a background service, collecting data at appropriate intervals.
    Respects rate limits and market hours for each source.
    """

    # Source schedules
    SCHEDULES: dict[str, SourceConfig] = {
        # Batch 1: Market Regime (Real-time during market hours)
        "vix_structure": SourceConfig(
            name="vix_structure",
            frequency=UpdateFrequency.REALTIME,
            interval_minutes=15,
            market_hours_only=True,
        ),
        "put_call": SourceConfig(
            name="put_call",
            frequency=UpdateFrequency.HOURLY,
            interval_minutes=60,
            market_hours_only=True,
        ),
        "market_breadth": SourceConfig(
            name="market_breadth",
            frequency=UpdateFrequency.REALTIME,
            interval_minutes=5,
            market_hours_only=True,
        ),
        "finviz_screens": SourceConfig(
            name="finviz_screens",
            frequency=UpdateFrequency.FOUR_HOURS,
            interval_minutes=240,
            market_hours_only=False,
        ),

        # Batch 2: Sentiment (Daily/Weekly)
        "aaii_sentiment": SourceConfig(
            name="aaii_sentiment",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=1440,
            market_hours_only=False,
        ),
        "newsletter_sentiment": SourceConfig(
            name="newsletter_sentiment",
            frequency=UpdateFrequency.WEEKLY,
            interval_minutes=10080,
            market_hours_only=False,
        ),
        "cot_report": SourceConfig(
            name="cot_report",
            frequency=UpdateFrequency.WEEKLY,
            interval_minutes=10080,
            market_hours_only=False,
        ),

        # Batch 3: Economic Calendar (Various)
        "earnings_calendar": SourceConfig(
            name="earnings_calendar",
            frequency=UpdateFrequency.FOUR_HOURS,
            interval_minutes=360,
            market_hours_only=False,
        ),
        "economic_calendar": SourceConfig(
            name="economic_calendar",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=720,
            market_hours_only=False,
        ),
        "fed_futures": SourceConfig(
            name="fed_futures",
            frequency=UpdateFrequency.HOURLY,
            interval_minutes=60,
            market_hours_only=True,
        ),
        "treasury_calendar": SourceConfig(
            name="treasury_calendar",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=720,
            market_hours_only=False,
        ),

        # Batch 4: Alternative Data (Various)
        "ipo_calendar": SourceConfig(
            name="ipo_calendar",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=720,
            market_hours_only=False,
        ),
        "fda_calendar": SourceConfig(
            name="fda_calendar",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=720,
            market_hours_only=False,
        ),

        # Batch 5: Innovation Signals (Less frequent)
        "patents": SourceConfig(
            name="patents",
            frequency=UpdateFrequency.WEEKLY,
            interval_minutes=10080,
            market_hours_only=False,
        ),
        "job_postings": SourceConfig(
            name="job_postings",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=4320,  # Every 3 days
            market_hours_only=False,
        ),
        "app_rankings": SourceConfig(
            name="app_rankings",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=1440,
            market_hours_only=False,
        ),
        "github_activity": SourceConfig(
            name="github_activity",
            frequency=UpdateFrequency.DAILY,
            interval_minutes=1440,
            market_hours_only=False,
        ),
    }

    def __init__(
        self,
        status_dir: Optional[Path] = None,
    ):
        self.status_dir = status_dir or paths.live
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._status = CollectionStatus(
            timestamp=datetime.now(),
            sources=dict(self.SCHEDULES),
        )
        self._collectors: dict[str, Callable] = {}
        self._setup_collectors()

    def _setup_collectors(self) -> None:
        """Set up collector functions for each source."""
        # Map source names to their collector functions
        # These would import and call the actual source classes
        self._collectors = {
            "vix_structure": self._collect_vix_structure,
            "put_call": self._collect_put_call,
            "market_breadth": self._collect_market_breadth,
            "finviz_screens": self._collect_finviz_screens,
            "aaii_sentiment": self._collect_aaii_sentiment,
            "newsletter_sentiment": self._collect_newsletter_sentiment,
            "cot_report": self._collect_cot_report,
            "earnings_calendar": self._collect_earnings_calendar,
            "economic_calendar": self._collect_economic_calendar,
            "fed_futures": self._collect_fed_futures,
            "treasury_calendar": self._collect_treasury_calendar,
            "ipo_calendar": self._collect_ipo_calendar,
            "fda_calendar": self._collect_fda_calendar,
            "patents": self._collect_patents,
            "job_postings": self._collect_job_postings,
            "app_rankings": self._collect_app_rankings,
            "github_activity": self._collect_github_activity,
        }

    def _is_market_hours(self) -> bool:
        """Check if we're in US market hours (9:30 AM - 4:00 PM ET)."""
        now = datetime.now()
        # Simplified check - would use proper timezone handling in production
        # Assuming system is in ET timezone
        weekday = now.weekday()
        if weekday >= 5:  # Saturday or Sunday
            return False

        hour = now.hour
        minute = now.minute

        # Market hours: 9:30 AM - 4:00 PM ET
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False

        return True

    def _should_collect(self, source_name: str) -> bool:
        """Check if a source should be collected now."""
        config = self._status.sources.get(source_name)
        if not config or not config.enabled:
            return False

        # Check market hours requirement
        if config.market_hours_only and not self._is_market_hours():
            return False

        # Check if enough time has passed since last collection
        if config.last_success:
            elapsed = datetime.now() - config.last_success
            if elapsed.total_seconds() < config.interval_minutes * 60:
                return False

        # Back off on consecutive failures
        if config.consecutive_failures >= 3:
            # Exponential backoff: wait 2^failures * interval
            backoff_multiplier = min(2 ** config.consecutive_failures, 16)
            if config.last_success:
                elapsed = datetime.now() - config.last_success
                if elapsed.total_seconds() < config.interval_minutes * 60 * backoff_multiplier:
                    return False

        return True

    async def _collect_source(self, source_name: str) -> bool:
        """Collect data from a single source."""
        collector = self._collectors.get(source_name)
        if not collector:
            logger.warning(f"No collector for source: {source_name}")
            return False

        config = self._status.sources.get(source_name)
        if not config:
            return False

        try:
            await collector()
            config.last_success = datetime.now()
            config.last_error = None
            config.consecutive_failures = 0
            self._status.total_collections_today += 1
            logger.info(f"Successfully collected: {source_name}")
            return True
        except Exception as e:
            config.last_error = str(e)
            config.consecutive_failures += 1
            self._status.errors_today += 1
            logger.error(f"Failed to collect {source_name}: {e}")
            return False

    # Individual collectors - these call the actual source classes
    async def _collect_vix_structure(self) -> None:
        """Collect VIX term structure data."""
        from src.data.sources.alternative.vix_structure import VIXStructureSource
        source = VIXStructureSource()
        try:
            await source.get_structure(force_refresh=True)
        finally:
            await source.close()

    async def _collect_put_call(self) -> None:
        """Collect put/call ratio data."""
        from src.data.sources.alternative.put_call import PutCallSource
        source = PutCallSource()
        try:
            await source.get_data(force_refresh=True)
        finally:
            await source.close()

    async def _collect_market_breadth(self) -> None:
        """Collect market breadth data."""
        # Uses existing market_breadth.py infrastructure
        from src.data.pipeline.market_breadth import MarketBreadthCalculator
        calc = MarketBreadthCalculator()
        await calc.calculate()

    async def _collect_finviz_screens(self) -> None:
        """Collect Finviz screen results."""
        from src.data.sources.alternative.finviz_screens import FinvizScreener
        screener = FinvizScreener()
        try:
            await screener.run_all_screens(force_refresh=True)
        finally:
            await screener.close()

    async def _collect_aaii_sentiment(self) -> None:
        """Collect AAII sentiment data."""
        from src.data.sources.alternative.aaii_sentiment import AAIISentimentSource
        source = AAIISentimentSource()
        try:
            await source.get_sentiment(force_refresh=True)
        finally:
            await source.close()

    async def _collect_newsletter_sentiment(self) -> None:
        """Collect newsletter sentiment data."""
        from src.data.sources.alternative.newsletter_sentiment import NewsletterSentimentSource
        source = NewsletterSentimentSource()
        try:
            await source.get_sentiment(force_refresh=True)
        finally:
            await source.close()

    async def _collect_cot_report(self) -> None:
        """Collect COT report data."""
        from src.data.sources.alternative.cot_report import COTSource
        source = COTSource()
        try:
            await source.get_report(force_refresh=True)
        finally:
            await source.close()

    async def _collect_earnings_calendar(self) -> None:
        """Collect earnings calendar data."""
        from src.data.sources.alternative.earnings_calendar import EarningsCalendarSource
        source = EarningsCalendarSource()
        try:
            await source.get_calendar(force_refresh=True)
        finally:
            await source.close()

    async def _collect_economic_calendar(self) -> None:
        """Collect economic calendar data."""
        from src.data.sources.alternative.economic_calendar import EconomicCalendarSource
        source = EconomicCalendarSource()
        try:
            await source.get_calendar(force_refresh=True)
        finally:
            await source.close()

    async def _collect_fed_futures(self) -> None:
        """Collect Fed futures data."""
        from src.data.sources.alternative.fed_futures import FedFuturesSource
        source = FedFuturesSource()
        try:
            await source.get_expectations(force_refresh=True)
        finally:
            await source.close()

    async def _collect_treasury_calendar(self) -> None:
        """Collect Treasury calendar data."""
        from src.data.sources.alternative.treasury_calendar import TreasuryCalendarSource
        source = TreasuryCalendarSource()
        try:
            await source.get_calendar(force_refresh=True)
        finally:
            await source.close()

    async def _collect_ipo_calendar(self) -> None:
        """Collect IPO calendar data."""
        from src.data.sources.alternative.ipo_calendar import IPOCalendarSource
        source = IPOCalendarSource()
        try:
            await source.get_calendar(force_refresh=True)
        finally:
            await source.close()

    async def _collect_fda_calendar(self) -> None:
        """Collect FDA calendar data."""
        from src.data.sources.alternative.fda_calendar import FDACalendarSource
        source = FDACalendarSource()
        try:
            await source.get_calendar(force_refresh=True)
        finally:
            await source.close()

    async def _collect_patents(self) -> None:
        """Collect patent data."""
        from src.data.sources.alternative.patent_filings import USPTOSource
        source = USPTOSource()
        try:
            await source.get_database(force_refresh=True)
        finally:
            await source.close()

    async def _collect_job_postings(self) -> None:
        """Collect job posting data."""
        from src.data.sources.alternative.job_postings import JobPostingSource
        source = JobPostingSource()
        try:
            await source.get_database(force_refresh=True)
        finally:
            await source.close()

    async def _collect_app_rankings(self) -> None:
        """Collect app ranking data."""
        from src.data.sources.alternative.app_rankings import AppRankingSource
        source = AppRankingSource()
        try:
            await source.get_database(force_refresh=True)
        finally:
            await source.close()

    async def _collect_github_activity(self) -> None:
        """Collect GitHub activity data."""
        from src.data.sources.alternative.github_activity import GitHubSource
        source = GitHubSource()
        try:
            await source.get_database(force_refresh=True)
        finally:
            await source.close()

    async def collect_all_now(self) -> CollectionStatus:
        """
        Force collection of all sources immediately.

        Useful for initial data population or debugging.
        """
        logger.info("Starting forced collection of all sources...")

        for source_name in self._collectors.keys():
            config = self._status.sources.get(source_name)
            if config and config.enabled:
                await self._collect_source(source_name)

        self._status.timestamp = datetime.now()
        self._save_status()
        return self._status

    async def collect_due(self) -> list[str]:
        """
        Collect all sources that are due for update.

        Returns list of sources that were collected.
        """
        self._status.is_market_hours = self._is_market_hours()
        collected = []

        for source_name in self._collectors.keys():
            if self._should_collect(source_name):
                success = await self._collect_source(source_name)
                if success:
                    collected.append(source_name)

        if collected:
            self._status.timestamp = datetime.now()
            self._save_status()

        return collected

    async def start(self, interval_seconds: int = 60) -> None:
        """
        Start the collection daemon.

        Runs continuously, checking for due collections every interval.
        """
        self._running = True
        logger.info(f"Starting data collection daemon (interval: {interval_seconds}s)")

        while self._running:
            try:
                collected = await self.collect_due()
                if collected:
                    logger.info(f"Collected {len(collected)} sources: {', '.join(collected)}")
            except Exception as e:
                logger.error(f"Collection cycle error: {e}")

            await asyncio.sleep(interval_seconds)

    async def stop(self) -> None:
        """Stop the collection daemon."""
        self._running = False
        logger.info("Stopping data collection daemon")

    def get_status(self) -> CollectionStatus:
        """Get current collection status."""
        self._status.timestamp = datetime.now()
        self._status.is_market_hours = self._is_market_hours()
        return self._status

    def _save_status(self) -> None:
        """Save status to disk."""
        import json
        status_file = self.status_dir / "collection_status.json"
        try:
            with open(status_file, "w") as f:
                json.dump(self._status.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save collection status: {e}")

    def enable_source(self, source_name: str) -> bool:
        """Enable a data source."""
        if source_name in self._status.sources:
            self._status.sources[source_name].enabled = True
            return True
        return False

    def disable_source(self, source_name: str) -> bool:
        """Disable a data source."""
        if source_name in self._status.sources:
            self._status.sources[source_name].enabled = False
            return True
        return False


# Convenience functions
async def collect_all_data() -> CollectionStatus:
    """Force collection of all data sources."""
    daemon = DataCollectionDaemon()
    return await daemon.collect_all_now()


async def collect_due_data() -> list[str]:
    """Collect data sources that are due."""
    daemon = DataCollectionDaemon()
    return await daemon.collect_due()


def get_collection_status() -> CollectionStatus:
    """Get current collection status."""
    daemon = DataCollectionDaemon()
    return daemon.get_status()


if __name__ == "__main__":
    async def main():
        daemon = DataCollectionDaemon()

        print("Data Collection Daemon")
        print("=" * 50)

        status = daemon.get_status()
        print(f"\nMarket Hours: {status.is_market_hours}")
        print(f"Collections Today: {status.total_collections_today}")
        print(f"Errors Today: {status.errors_today}")

        print("\nSource Schedules:")
        for name, config in status.sources.items():
            status_str = "ENABLED" if config.enabled else "DISABLED"
            last = config.last_success.strftime("%H:%M") if config.last_success else "Never"
            print(f"  {name}: {config.frequency.value} ({config.interval_minutes}min) - {status_str}")
            print(f"    Last: {last}, Failures: {config.consecutive_failures}")

        print("\n" + "=" * 50)
        print("To start daemon: await daemon.start()")
        print("To collect now: await daemon.collect_all_now()")

    asyncio.run(main())
