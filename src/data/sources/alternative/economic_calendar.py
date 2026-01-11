"""
Economic Release Calendar

Tracks major economic data releases from:
- Bureau of Labor Statistics (BLS): NFP, CPI, PPI, Unemployment
- Federal Reserve: FOMC meetings, Fed speeches
- Treasury: Auction schedules
- Other: GDP, Retail Sales, Housing

Each release includes:
- Date/time
- Prior value and consensus estimate
- Market impact level
- Affected sectors
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

from src.core.paths import paths

logger = logging.getLogger(__name__)


class ReleaseImportance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReleaseCategory(str, Enum):
    EMPLOYMENT = "employment"
    INFLATION = "inflation"
    GROWTH = "growth"
    HOUSING = "housing"
    CONSUMER = "consumer"
    MANUFACTURING = "manufacturing"
    FED = "fed"
    TREASURY = "treasury"
    OTHER = "other"


# Standard economic releases with typical schedule
RELEASE_DEFINITIONS = {
    "nfp": {
        "name": "Nonfarm Payrolls",
        "category": ReleaseCategory.EMPLOYMENT,
        "importance": ReleaseImportance.HIGH,
        "release_time": "08:30",
        "frequency": "monthly",
        "day_pattern": "first_friday",
        "affected_sectors": ["financials", "consumer_discretionary"],
        "typical_impact": "Higher than expected is bullish for stocks, bearish for bonds",
    },
    "cpi": {
        "name": "Consumer Price Index (CPI)",
        "category": ReleaseCategory.INFLATION,
        "importance": ReleaseImportance.HIGH,
        "release_time": "08:30",
        "frequency": "monthly",
        "affected_sectors": ["utilities", "real_estate", "financials"],
        "typical_impact": "Higher than expected is hawkish (bearish for stocks/bonds)",
    },
    "ppi": {
        "name": "Producer Price Index (PPI)",
        "category": ReleaseCategory.INFLATION,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "08:30",
        "frequency": "monthly",
        "affected_sectors": ["materials", "industrials"],
        "typical_impact": "Leading indicator for CPI",
    },
    "fomc": {
        "name": "FOMC Rate Decision",
        "category": ReleaseCategory.FED,
        "importance": ReleaseImportance.HIGH,
        "release_time": "14:00",
        "frequency": "6_weeks",
        "affected_sectors": ["all"],
        "typical_impact": "Rate hike = bearish, cut = bullish, statement language critical",
    },
    "gdp": {
        "name": "GDP Growth Rate",
        "category": ReleaseCategory.GROWTH,
        "importance": ReleaseImportance.HIGH,
        "release_time": "08:30",
        "frequency": "quarterly",
        "affected_sectors": ["all"],
        "typical_impact": "Strong growth = bullish for stocks",
    },
    "retail_sales": {
        "name": "Retail Sales",
        "category": ReleaseCategory.CONSUMER,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "08:30",
        "frequency": "monthly",
        "affected_sectors": ["consumer_discretionary", "consumer_staples"],
        "typical_impact": "Measures consumer spending strength",
    },
    "ism_manufacturing": {
        "name": "ISM Manufacturing PMI",
        "category": ReleaseCategory.MANUFACTURING,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "10:00",
        "frequency": "monthly",
        "day_pattern": "first_business_day",
        "affected_sectors": ["industrials", "materials"],
        "typical_impact": ">50 = expansion, <50 = contraction",
    },
    "ism_services": {
        "name": "ISM Services PMI",
        "category": ReleaseCategory.MANUFACTURING,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "10:00",
        "frequency": "monthly",
        "affected_sectors": ["services", "technology"],
        "typical_impact": ">50 = expansion, <50 = contraction",
    },
    "unemployment_claims": {
        "name": "Initial Jobless Claims",
        "category": ReleaseCategory.EMPLOYMENT,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "08:30",
        "frequency": "weekly",
        "day_pattern": "thursday",
        "affected_sectors": ["consumer_discretionary"],
        "typical_impact": "Lower = stronger labor market",
    },
    "housing_starts": {
        "name": "Housing Starts",
        "category": ReleaseCategory.HOUSING,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "08:30",
        "frequency": "monthly",
        "affected_sectors": ["homebuilders", "materials", "financials"],
        "typical_impact": "Leading indicator for housing sector",
    },
    "existing_home_sales": {
        "name": "Existing Home Sales",
        "category": ReleaseCategory.HOUSING,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "10:00",
        "frequency": "monthly",
        "affected_sectors": ["homebuilders", "financials"],
        "typical_impact": "Measures housing market health",
    },
    "consumer_confidence": {
        "name": "Consumer Confidence",
        "category": ReleaseCategory.CONSUMER,
        "importance": ReleaseImportance.MEDIUM,
        "release_time": "10:00",
        "frequency": "monthly",
        "affected_sectors": ["consumer_discretionary"],
        "typical_impact": "Higher = more consumer spending expected",
    },
    "pce": {
        "name": "PCE Price Index",
        "category": ReleaseCategory.INFLATION,
        "importance": ReleaseImportance.HIGH,
        "release_time": "08:30",
        "frequency": "monthly",
        "affected_sectors": ["all"],
        "typical_impact": "Fed's preferred inflation measure",
    },
}


@dataclass
class EconomicRelease:
    """Single economic data release event."""

    release_id: str  # e.g., "nfp", "cpi"
    name: str
    release_date: datetime
    release_time: str  # "HH:MM" ET
    category: str
    importance: str

    # Values
    prior_value: Optional[float] = None
    consensus: Optional[float] = None
    actual_value: Optional[float] = None  # Filled after release

    # Context
    affected_sectors: list[str] = field(default_factory=list)
    typical_impact: str = ""
    notes: str = ""

    # Metadata
    source: str = "calendar"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "release_id": self.release_id,
            "name": self.name,
            "release_date": self.release_date.isoformat(),
            "release_time": self.release_time,
            "category": self.category,
            "importance": self.importance,
            "prior_value": self.prior_value,
            "consensus": self.consensus,
            "actual_value": self.actual_value,
            "affected_sectors": self.affected_sectors,
            "typical_impact": self.typical_impact,
            "notes": self.notes,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EconomicRelease":
        return cls(
            release_id=d["release_id"],
            name=d["name"],
            release_date=datetime.fromisoformat(d["release_date"]),
            release_time=d["release_time"],
            category=d["category"],
            importance=d["importance"],
            prior_value=d.get("prior_value"),
            consensus=d.get("consensus"),
            actual_value=d.get("actual_value"),
            affected_sectors=d.get("affected_sectors", []),
            typical_impact=d.get("typical_impact", ""),
            notes=d.get("notes", ""),
            source=d.get("source", "calendar"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_today(self) -> bool:
        return self.release_date.date() == datetime.now().date()

    @property
    def is_high_impact(self) -> bool:
        return self.importance == ReleaseImportance.HIGH.value

    @property
    def days_until(self) -> int:
        return (self.release_date.date() - datetime.now().date()).days

    @property
    def surprise(self) -> Optional[float]:
        """Calculate surprise if actual is available."""
        if self.actual_value is not None and self.consensus is not None:
            return self.actual_value - self.consensus
        return None


@dataclass
class EconomicCalendar:
    """Collection of economic release events."""

    timestamp: datetime
    events: list[EconomicRelease] = field(default_factory=list)

    @property
    def today(self) -> list[EconomicRelease]:
        return [e for e in self.events if e.is_today]

    @property
    def this_week(self) -> list[EconomicRelease]:
        return [e for e in self.events if 0 <= e.days_until <= 7]

    @property
    def high_impact(self) -> list[EconomicRelease]:
        return [e for e in self.events if e.is_high_impact]

    @property
    def high_impact_this_week(self) -> list[EconomicRelease]:
        return [e for e in self.this_week if e.is_high_impact]

    def get_by_category(self, category: str) -> list[EconomicRelease]:
        return [e for e in self.events if e.category == category]

    def get_affecting_sector(self, sector: str) -> list[EconomicRelease]:
        return [e for e in self.events if sector in e.affected_sectors or "all" in e.affected_sectors]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EconomicCalendar":
        events = [EconomicRelease.from_dict(e) for e in d.get("events", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            events=events,
        )


class EconomicCalendarSource:
    """
    Generate and manage economic release calendar.

    Uses predefined release schedule plus manual updates.
    In production, would integrate with BLS/Fed APIs.
    """

    name = "economic_calendar"

    # BLS schedule URL (for reference)
    BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/news_release/"
    FED_CALENDAR_URL = "https://www.federalreserve.gov/newsevents/calendar.htm"

    def __init__(
        self,
        cache_ttl_hours: int = 12,
        cache_dir: Optional[Path] = None,
        lookforward_days: int = 30,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "economic")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookforward_days = lookforward_days
        self._cache: Optional[tuple[datetime, EconomicCalendar]] = None

        # Load any manually entered events
        self._manual_events: list[EconomicRelease] = []
        self._load_manual_events()

    def _load_manual_events(self) -> None:
        """Load manually entered events."""
        events_file = self.cache_dir / "manual_events.json"
        if events_file.exists():
            try:
                with open(events_file) as f:
                    data = json.load(f)
                self._manual_events = [EconomicRelease.from_dict(e) for e in data]
            except Exception as e:
                logger.warning(f"Failed to load manual events: {e}")

    def _save_manual_events(self) -> None:
        """Save manually entered events."""
        events_file = self.cache_dir / "manual_events.json"
        try:
            data = [e.to_dict() for e in self._manual_events]
            with open(events_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save manual events: {e}")

    def _check_cache(self) -> Optional[EconomicCalendar]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, calendar = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return calendar

        cache_file = self.cache_dir / "economic_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                calendar = EconomicCalendar.from_dict(data)
                if datetime.now() - calendar.timestamp < self.cache_ttl:
                    self._cache = (calendar.timestamp, calendar)
                    return calendar
            except Exception as e:
                logger.warning(f"Failed to load economic calendar cache: {e}")

        return None

    def _update_cache(self, calendar: EconomicCalendar) -> None:
        """Update cache."""
        self._cache = (datetime.now(), calendar)

        cache_file = self.cache_dir / "economic_calendar.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(calendar.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save economic calendar cache: {e}")

    async def get_calendar(self, force_refresh: bool = False) -> EconomicCalendar:
        """
        Get economic calendar.

        Returns:
            EconomicCalendar with upcoming releases.
        """
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        # Generate calendar from definitions + manual events
        calendar = self._generate_calendar()

        self._update_cache(calendar)
        return calendar

    def _generate_calendar(self) -> EconomicCalendar:
        """Generate calendar from release definitions."""
        calendar = EconomicCalendar(timestamp=datetime.now())

        today = datetime.now().date()
        end_date = today + timedelta(days=self.lookforward_days)

        # Add scheduled releases (simplified - real impl would use actual schedule)
        for release_id, definition in RELEASE_DEFINITIONS.items():
            # For now, just add placeholder events
            # In production, would calculate actual dates based on patterns
            event = EconomicRelease(
                release_id=release_id,
                name=definition["name"],
                release_date=datetime.now() + timedelta(days=7),  # Placeholder
                release_time=definition["release_time"],
                category=definition["category"].value if hasattr(definition["category"], "value") else definition["category"],
                importance=definition["importance"].value if hasattr(definition["importance"], "value") else definition["importance"],
                affected_sectors=definition.get("affected_sectors", []),
                typical_impact=definition.get("typical_impact", ""),
                source="schedule",
            )
            calendar.events.append(event)

        # Add manual events
        for event in self._manual_events:
            if today <= event.release_date.date() <= end_date:
                calendar.events.append(event)

        # Sort by date
        calendar.events.sort(key=lambda e: e.release_date)

        return calendar

    def add_event(
        self,
        release_id: str,
        release_date: datetime,
        prior_value: Optional[float] = None,
        consensus: Optional[float] = None,
        notes: str = "",
    ) -> EconomicRelease:
        """
        Add a manual event to the calendar.

        Args:
            release_id: ID from RELEASE_DEFINITIONS (e.g., "nfp", "cpi")
            release_date: Date/time of release
            prior_value: Previous release value
            consensus: Market consensus estimate
            notes: Additional notes

        Returns:
            The created EconomicRelease
        """
        if release_id not in RELEASE_DEFINITIONS:
            raise ValueError(f"Unknown release_id: {release_id}")

        definition = RELEASE_DEFINITIONS[release_id]

        event = EconomicRelease(
            release_id=release_id,
            name=definition["name"],
            release_date=release_date,
            release_time=definition["release_time"],
            category=definition["category"].value if hasattr(definition["category"], "value") else definition["category"],
            importance=definition["importance"].value if hasattr(definition["importance"], "value") else definition["importance"],
            prior_value=prior_value,
            consensus=consensus,
            affected_sectors=definition.get("affected_sectors", []),
            typical_impact=definition.get("typical_impact", ""),
            notes=notes,
            source="manual",
        )

        self._manual_events.append(event)
        self._save_manual_events()

        # Invalidate cache
        self._cache = None

        return event

    def update_actual(self, release_id: str, release_date: datetime, actual_value: float) -> bool:
        """Update a release with the actual value after it's published."""
        for event in self._manual_events:
            if event.release_id == release_id and event.release_date.date() == release_date.date():
                event.actual_value = actual_value
                event.last_updated = datetime.now()
                self._save_manual_events()
                self._cache = None
                return True
        return False

    def has_high_impact_today(self) -> bool:
        """Check if there are high-impact releases today."""
        cached = self._check_cache()
        if cached:
            return len([e for e in cached.today if e.is_high_impact]) > 0
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_economic_calendar(days: int = 30) -> EconomicCalendar:
    """Get economic calendar for the next N days."""
    source = EconomicCalendarSource(lookforward_days=days)
    try:
        return await source.get_calendar()
    finally:
        await source.close()


async def get_high_impact_releases() -> list[EconomicRelease]:
    """Get upcoming high-impact releases."""
    calendar = await get_economic_calendar()
    return calendar.high_impact


async def has_fomc_this_week() -> bool:
    """Check if there's an FOMC meeting this week."""
    calendar = await get_economic_calendar(days=7)
    return any(e.release_id == "fomc" for e in calendar.events)


if __name__ == "__main__":
    async def main():
        source = EconomicCalendarSource()
        calendar = await source.get_calendar()

        print(f"Economic Calendar - {calendar.timestamp.date()}")
        print(f"Total events: {len(calendar.events)}")
        print(f"High impact: {len(calendar.high_impact)}")

        print("\nHigh Impact Events:")
        for e in calendar.high_impact[:10]:
            print(f"  {e.release_date.strftime('%m/%d')} {e.release_time}: {e.name}")
            if e.consensus:
                print(f"    Prior: {e.prior_value}, Consensus: {e.consensus}")

        await source.close()

    asyncio.run(main())
