"""
FDA Calendar

Tracks FDA PDUFA dates, Advisory Committee meetings, and other
regulatory catalysts for biotech/pharma stocks.

Data Sources:
- FDA.gov calendar
- BioPharmCatalyst (free tier)

Provides:
- PDUFA action dates
- AdCom meeting dates
- Phase 3 data readouts
- Approval probability estimates
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    PDUFA = "PDUFA"  # Prescription Drug User Fee Act deadline
    ADCOM = "AdCom"  # Advisory Committee meeting
    PHASE3_DATA = "Phase 3 Data"
    PHASE2_DATA = "Phase 2 Data"
    CRL_RESPONSE = "CRL Response"  # Complete Response Letter resubmission
    BLA = "BLA"  # Biologics License Application
    NDA = "NDA"  # New Drug Application
    SNDDA = "sNDA"  # Supplemental NDA
    APPROVAL = "Approval"


# Historical approval rates by indication category
APPROVAL_RATES = {
    "oncology": 0.33,
    "rare_disease": 0.65,
    "infectious_disease": 0.45,
    "cardiovascular": 0.40,
    "neurology": 0.35,
    "autoimmune": 0.42,
    "metabolic": 0.50,
    "ophthalmology": 0.55,
    "dermatology": 0.48,
    "respiratory": 0.45,
    "general": 0.40,
}


@dataclass
class FDAEvent:
    """Single FDA regulatory event."""

    company: str
    symbol: str
    drug_name: str
    indication: str
    event_type: str  # EventType value
    expected_date: datetime

    # Context
    indication_category: str = "general"
    phase: Optional[str] = None  # "Phase 2", "Phase 3", etc.
    is_priority_review: bool = False
    is_breakthrough: bool = False
    is_accelerated: bool = False
    is_orphan: bool = False

    # Probability
    probability_approval: Optional[float] = None  # Historical rate for indication
    analyst_consensus: Optional[str] = None  # "likely", "uncertain", "unlikely"

    # AdCom specific
    adcom_vote: Optional[str] = None  # e.g., "12-2 favorable"
    adcom_recommendation: Optional[str] = None

    # Market context
    market_cap_billions: Optional[float] = None
    drug_revenue_potential: Optional[float] = None  # Peak sales estimate in billions

    # Metadata
    source: str = "manual"
    notes: str = ""
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "symbol": self.symbol,
            "drug_name": self.drug_name,
            "indication": self.indication,
            "event_type": self.event_type,
            "expected_date": self.expected_date.isoformat(),
            "indication_category": self.indication_category,
            "phase": self.phase,
            "is_priority_review": self.is_priority_review,
            "is_breakthrough": self.is_breakthrough,
            "is_accelerated": self.is_accelerated,
            "is_orphan": self.is_orphan,
            "probability_approval": self.probability_approval,
            "analyst_consensus": self.analyst_consensus,
            "adcom_vote": self.adcom_vote,
            "adcom_recommendation": self.adcom_recommendation,
            "market_cap_billions": self.market_cap_billions,
            "drug_revenue_potential": self.drug_revenue_potential,
            "source": self.source,
            "notes": self.notes,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FDAEvent":
        return cls(
            company=d["company"],
            symbol=d["symbol"],
            drug_name=d["drug_name"],
            indication=d["indication"],
            event_type=d["event_type"],
            expected_date=datetime.fromisoformat(d["expected_date"]),
            indication_category=d.get("indication_category", "general"),
            phase=d.get("phase"),
            is_priority_review=d.get("is_priority_review", False),
            is_breakthrough=d.get("is_breakthrough", False),
            is_accelerated=d.get("is_accelerated", False),
            is_orphan=d.get("is_orphan", False),
            probability_approval=d.get("probability_approval"),
            analyst_consensus=d.get("analyst_consensus"),
            adcom_vote=d.get("adcom_vote"),
            adcom_recommendation=d.get("adcom_recommendation"),
            market_cap_billions=d.get("market_cap_billions"),
            drug_revenue_potential=d.get("drug_revenue_potential"),
            source=d.get("source", "manual"),
            notes=d.get("notes", ""),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_today(self) -> bool:
        return self.expected_date.date() == datetime.now().date()

    @property
    def is_this_week(self) -> bool:
        days = (self.expected_date.date() - datetime.now().date()).days
        return 0 <= days <= 7

    @property
    def days_until(self) -> int:
        return (self.expected_date.date() - datetime.now().date()).days

    @property
    def is_binary_event(self) -> bool:
        """Check if this is a high-impact binary event (PDUFA, AdCom)."""
        return self.event_type in [EventType.PDUFA.value, EventType.ADCOM.value]

    @property
    def has_positive_designations(self) -> bool:
        """Check if drug has any positive FDA designations."""
        return any([self.is_priority_review, self.is_breakthrough, self.is_accelerated, self.is_orphan])

    @property
    def estimated_approval_probability(self) -> float:
        """Estimate approval probability based on various factors."""
        if self.probability_approval is not None:
            return self.probability_approval

        # Start with base rate for indication
        base_rate = APPROVAL_RATES.get(self.indication_category, 0.40)

        # Adjust for positive designations
        if self.is_breakthrough:
            base_rate += 0.15
        if self.is_priority_review:
            base_rate += 0.10
        if self.is_orphan:
            base_rate += 0.10
        if self.is_accelerated:
            base_rate += 0.05

        # Cap at reasonable max
        return min(base_rate, 0.85)


@dataclass
class FDACalendar:
    """Collection of FDA events."""

    timestamp: datetime
    events: list[FDAEvent] = field(default_factory=list)

    @property
    def today(self) -> list[FDAEvent]:
        return [e for e in self.events if e.is_today]

    @property
    def this_week(self) -> list[FDAEvent]:
        return [e for e in self.events if e.is_this_week and e.days_until >= 0]

    @property
    def upcoming(self) -> list[FDAEvent]:
        return [e for e in self.events if e.days_until >= 0]

    @property
    def pdufa_dates(self) -> list[FDAEvent]:
        return [e for e in self.upcoming if e.event_type == EventType.PDUFA.value]

    @property
    def adcom_meetings(self) -> list[FDAEvent]:
        return [e for e in self.upcoming if e.event_type == EventType.ADCOM.value]

    @property
    def binary_events(self) -> list[FDAEvent]:
        """Events that are likely to cause significant stock moves."""
        return [e for e in self.upcoming if e.is_binary_event]

    def get_for_symbol(self, symbol: str) -> list[FDAEvent]:
        return [e for e in self.events if e.symbol.upper() == symbol.upper()]

    def get_high_probability(self, min_prob: float = 0.60) -> list[FDAEvent]:
        """Get events with high approval probability."""
        return [e for e in self.upcoming if e.estimated_approval_probability >= min_prob]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FDACalendar":
        events = [FDAEvent.from_dict(e) for e in d.get("events", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            events=events,
        )


class FDACalendarSource:
    """
    Track FDA regulatory calendar.

    Data sources:
    - FDA.gov (official calendar)
    - BioPharmCatalyst (aggregated biotech calendar)
    """

    name = "fda_calendar"

    FDA_CALENDAR_URL = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"
    BIOPHARM_URL = "https://www.biopharmcatalyst.com/calendars/fda-calendar"

    def __init__(
        self,
        cache_ttl_hours: int = 12,
        cache_dir: Optional[Path] = None,
        lookforward_days: int = 90,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "fda")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookforward_days = lookforward_days
        self._cache: Optional[tuple[datetime, FDACalendar]] = None

    def _check_cache(self) -> Optional[FDACalendar]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, calendar = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return calendar

        cache_file = self.cache_dir / "fda_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                calendar = FDACalendar.from_dict(data)
                if datetime.now() - calendar.timestamp < self.cache_ttl:
                    self._cache = (calendar.timestamp, calendar)
                    return calendar
            except Exception as e:
                logger.warning(f"Failed to load FDA cache: {e}")

        return None

    def _update_cache(self, calendar: FDACalendar) -> None:
        """Update cache."""
        self._cache = (datetime.now(), calendar)

        cache_file = self.cache_dir / "fda_calendar.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(calendar.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save FDA cache: {e}")

    async def get_calendar(self, force_refresh: bool = False) -> FDACalendar:
        """Get FDA calendar."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        try:
            calendar = await self._fetch_calendar()
            self._update_cache(calendar)
            return calendar
        except Exception as e:
            logger.error(f"Failed to fetch FDA calendar: {e}")
            return FDACalendar(timestamp=datetime.now())

    async def _fetch_calendar(self) -> FDACalendar:
        """
        Fetch FDA calendar.

        In production, would scrape FDA.gov or BioPharmCatalyst.
        For now, returns cached data or empty calendar.
        """
        cache_file = self.cache_dir / "fda_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return FDACalendar.from_dict(data)
            except Exception:
                pass

        # Return empty calendar (would be populated by scraping or manual entry)
        return FDACalendar(timestamp=datetime.now())

    def add_event(
        self,
        company: str,
        symbol: str,
        drug_name: str,
        indication: str,
        event_type: str,
        expected_date: datetime,
        indication_category: str = "general",
        is_priority_review: bool = False,
        is_breakthrough: bool = False,
        is_orphan: bool = False,
        notes: str = "",
    ) -> FDAEvent:
        """
        Manually add an FDA event to the calendar.
        """
        # Calculate base probability
        base_prob = APPROVAL_RATES.get(indication_category, 0.40)

        event = FDAEvent(
            company=company,
            symbol=symbol,
            drug_name=drug_name,
            indication=indication,
            event_type=event_type,
            expected_date=expected_date,
            indication_category=indication_category,
            is_priority_review=is_priority_review,
            is_breakthrough=is_breakthrough,
            is_orphan=is_orphan,
            probability_approval=base_prob,
            notes=notes,
            source="manual",
        )

        cached = self._check_cache() or FDACalendar(timestamp=datetime.now())
        cached.events.append(event)
        cached.events.sort(key=lambda e: e.expected_date)
        self._update_cache(cached)

        return event

    def update_event_outcome(
        self,
        symbol: str,
        drug_name: str,
        outcome: str,  # "approved", "crl" (complete response letter), "withdrawn"
        notes: str = "",
    ) -> bool:
        """Update an event with its outcome."""
        cached = self._check_cache()
        if not cached:
            return False

        for event in cached.events:
            if event.symbol.upper() == symbol.upper() and event.drug_name.lower() == drug_name.lower():
                if outcome == "approved":
                    event.event_type = EventType.APPROVAL.value
                event.notes = f"{event.notes}\nOutcome: {outcome}. {notes}".strip()
                event.last_updated = datetime.now()
                self._update_cache(cached)
                return True

        return False

    def get_events_for_symbol(self, symbol: str) -> list[FDAEvent]:
        """Get all FDA events for a specific symbol."""
        cached = self._check_cache()
        if cached:
            return cached.get_for_symbol(symbol)
        return []

    def has_binary_event_soon(self, symbol: str, days: int = 30) -> bool:
        """Check if symbol has a binary FDA event within N days."""
        events = self.get_events_for_symbol(symbol)
        for event in events:
            if event.is_binary_event and 0 <= event.days_until <= days:
                return True
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_fda_calendar(days: int = 90) -> FDACalendar:
    """Get FDA calendar."""
    source = FDACalendarSource(lookforward_days=days)
    try:
        return await source.get_calendar()
    finally:
        await source.close()


async def get_upcoming_pdufa() -> list[FDAEvent]:
    """Get upcoming PDUFA dates."""
    calendar = await get_fda_calendar()
    return calendar.pdufa_dates


async def get_binary_events() -> list[FDAEvent]:
    """Get upcoming binary FDA events (PDUFA, AdCom)."""
    calendar = await get_fda_calendar()
    return calendar.binary_events


async def check_fda_catalyst(symbol: str, days: int = 30) -> Optional[FDAEvent]:
    """Check if a symbol has an upcoming FDA catalyst."""
    source = FDACalendarSource()
    try:
        events = source.get_events_for_symbol(symbol)
        for event in events:
            if 0 <= event.days_until <= days:
                return event
        return None
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = FDACalendarSource()

        # Add some example events for testing
        source.add_event(
            company="Moderna",
            symbol="MRNA",
            drug_name="mRNA-4157",
            indication="Melanoma",
            event_type=EventType.PHASE3_DATA.value,
            expected_date=datetime.now() + timedelta(days=45),
            indication_category="oncology",
            is_breakthrough=True,
            notes="KEYNOTE-942 trial",
        )

        source.add_event(
            company="Vertex Pharmaceuticals",
            symbol="VRTX",
            drug_name="VX-548",
            indication="Acute Pain",
            event_type=EventType.PDUFA.value,
            expected_date=datetime.now() + timedelta(days=20),
            indication_category="neurology",
            is_priority_review=True,
            notes="Non-opioid pain drug",
        )

        calendar = await source.get_calendar()

        print(f"FDA Calendar - {calendar.timestamp.date()}")
        print(f"Total events: {len(calendar.events)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"Upcoming PDUFA: {len(calendar.pdufa_dates)}")

        if calendar.upcoming:
            print("\nUpcoming Events:")
            for event in calendar.upcoming[:10]:
                print(f"  {event.expected_date.strftime('%m/%d')} {event.symbol}: {event.drug_name}")
                print(f"    {event.event_type} - {event.indication}")
                print(f"    Est. approval prob: {event.estimated_approval_probability:.0%}")
                if event.has_positive_designations:
                    designations = []
                    if event.is_breakthrough:
                        designations.append("BTD")
                    if event.is_priority_review:
                        designations.append("Priority")
                    if event.is_orphan:
                        designations.append("Orphan")
                    print(f"    Designations: {', '.join(designations)}")

        await source.close()

    asyncio.run(main())
