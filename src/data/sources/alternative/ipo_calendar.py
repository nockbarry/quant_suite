"""
IPO Calendar

Tracks upcoming Initial Public Offerings from:
- NASDAQ IPO calendar
- NYSE listings

Provides:
- IPO dates and price ranges
- Deal sizes and valuations
- Underwriters
- Sector classification
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class IPOEvent:
    """Single IPO event."""

    company_name: str
    symbol: str
    expected_date: datetime
    status: str  # "expected", "priced", "withdrawn", "postponed"

    # Deal details
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    price_final: Optional[float] = None  # Actual IPO price if priced
    shares_offered: Optional[int] = None  # In millions
    deal_size: Optional[float] = None  # In millions USD

    # Valuation
    valuation: Optional[float] = None  # Pre-money valuation in billions
    market_cap_at_ipo: Optional[float] = None  # In billions

    # Context
    sector: str = "unknown"
    industry: str = "unknown"
    exchange: str = "NASDAQ"  # NASDAQ or NYSE
    lead_underwriters: list[str] = field(default_factory=list)

    # Performance (post-IPO)
    first_day_return: Optional[float] = None
    current_price: Optional[float] = None

    # Metadata
    source: str = "nasdaq"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "symbol": self.symbol,
            "expected_date": self.expected_date.isoformat(),
            "status": self.status,
            "price_low": self.price_low,
            "price_high": self.price_high,
            "price_final": self.price_final,
            "shares_offered": self.shares_offered,
            "deal_size": self.deal_size,
            "valuation": self.valuation,
            "market_cap_at_ipo": self.market_cap_at_ipo,
            "sector": self.sector,
            "industry": self.industry,
            "exchange": self.exchange,
            "lead_underwriters": self.lead_underwriters,
            "first_day_return": self.first_day_return,
            "current_price": self.current_price,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IPOEvent":
        return cls(
            company_name=d["company_name"],
            symbol=d["symbol"],
            expected_date=datetime.fromisoformat(d["expected_date"]),
            status=d["status"],
            price_low=d.get("price_low"),
            price_high=d.get("price_high"),
            price_final=d.get("price_final"),
            shares_offered=d.get("shares_offered"),
            deal_size=d.get("deal_size"),
            valuation=d.get("valuation"),
            market_cap_at_ipo=d.get("market_cap_at_ipo"),
            sector=d.get("sector", "unknown"),
            industry=d.get("industry", "unknown"),
            exchange=d.get("exchange", "NASDAQ"),
            lead_underwriters=d.get("lead_underwriters", []),
            first_day_return=d.get("first_day_return"),
            current_price=d.get("current_price"),
            source=d.get("source", "nasdaq"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def price_range(self) -> str:
        """Format price range as string."""
        if self.price_final:
            return f"${self.price_final:.2f}"
        if self.price_low and self.price_high:
            return f"${self.price_low:.2f}-${self.price_high:.2f}"
        return "TBD"

    @property
    def midpoint_price(self) -> Optional[float]:
        """Get midpoint of price range."""
        if self.price_final:
            return self.price_final
        if self.price_low and self.price_high:
            return (self.price_low + self.price_high) / 2
        return None

    @property
    def is_this_week(self) -> bool:
        days = (self.expected_date.date() - datetime.now().date()).days
        return 0 <= days <= 7

    @property
    def is_large_deal(self) -> bool:
        """Check if this is a large deal (>$500M)."""
        return self.deal_size and self.deal_size >= 500

    @property
    def days_until(self) -> int:
        return (self.expected_date.date() - datetime.now().date()).days


@dataclass
class IPOCalendar:
    """Collection of IPO events."""

    timestamp: datetime
    ipos: list[IPOEvent] = field(default_factory=list)

    @property
    def this_week(self) -> list[IPOEvent]:
        return [i for i in self.ipos if i.is_this_week and i.status == "expected"]

    @property
    def upcoming(self) -> list[IPOEvent]:
        return [i for i in self.ipos if i.status == "expected" and i.days_until >= 0]

    @property
    def priced_recently(self) -> list[IPOEvent]:
        """IPOs priced in last 5 days."""
        cutoff = datetime.now() - timedelta(days=5)
        return [i for i in self.ipos if i.status == "priced" and i.expected_date >= cutoff]

    @property
    def large_deals(self) -> list[IPOEvent]:
        return [i for i in self.upcoming if i.is_large_deal]

    def get_by_sector(self, sector: str) -> list[IPOEvent]:
        return [i for i in self.ipos if i.sector.lower() == sector.lower()]

    @property
    def total_deal_volume_this_week(self) -> float:
        """Total deal volume this week in millions."""
        return sum(i.deal_size or 0 for i in self.this_week)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "ipos": [i.to_dict() for i in self.ipos],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IPOCalendar":
        ipos = [IPOEvent.from_dict(i) for i in d.get("ipos", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            ipos=ipos,
        )


class IPOCalendarSource:
    """
    Track upcoming IPOs.

    Data source: NASDAQ IPO calendar
    """

    name = "ipo_calendar"

    NASDAQ_URL = "https://www.nasdaq.com/market-activity/ipos"

    def __init__(
        self,
        cache_ttl_hours: int = 12,
        cache_dir: Optional[Path] = None,
        lookforward_days: int = 30,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "ipo")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookforward_days = lookforward_days
        self._cache: Optional[tuple[datetime, IPOCalendar]] = None

    def _check_cache(self) -> Optional[IPOCalendar]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, calendar = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return calendar

        cache_file = self.cache_dir / "ipo_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                calendar = IPOCalendar.from_dict(data)
                if datetime.now() - calendar.timestamp < self.cache_ttl:
                    self._cache = (calendar.timestamp, calendar)
                    return calendar
            except Exception as e:
                logger.warning(f"Failed to load IPO cache: {e}")

        return None

    def _update_cache(self, calendar: IPOCalendar) -> None:
        """Update cache."""
        self._cache = (datetime.now(), calendar)

        cache_file = self.cache_dir / "ipo_calendar.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(calendar.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save IPO cache: {e}")

    async def get_calendar(self, force_refresh: bool = False) -> IPOCalendar:
        """Get IPO calendar."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        try:
            calendar = await self._fetch_calendar()
            self._update_cache(calendar)
            return calendar
        except Exception as e:
            logger.error(f"Failed to fetch IPO calendar: {e}")
            return IPOCalendar(timestamp=datetime.now())

    async def _fetch_calendar(self) -> IPOCalendar:
        """
        Fetch IPO calendar.

        In production, would scrape NASDAQ or use a data provider.
        """
        cache_file = self.cache_dir / "ipo_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return IPOCalendar.from_dict(data)
            except Exception:
                pass

        # Return empty calendar (would be populated by scraping or manual entry)
        return IPOCalendar(timestamp=datetime.now())

    def add_ipo(
        self,
        company_name: str,
        symbol: str,
        expected_date: datetime,
        price_low: Optional[float] = None,
        price_high: Optional[float] = None,
        shares_offered: Optional[int] = None,
        sector: str = "unknown",
        exchange: str = "NASDAQ",
        underwriters: Optional[list[str]] = None,
    ) -> IPOEvent:
        """
        Manually add an IPO to the calendar.
        """
        deal_size = None
        if price_low and price_high and shares_offered:
            midpoint = (price_low + price_high) / 2
            deal_size = (midpoint * shares_offered) / 1e6  # In millions

        ipo = IPOEvent(
            company_name=company_name,
            symbol=symbol,
            expected_date=expected_date,
            status="expected",
            price_low=price_low,
            price_high=price_high,
            shares_offered=shares_offered,
            deal_size=deal_size,
            sector=sector,
            exchange=exchange,
            lead_underwriters=underwriters or [],
            source="manual",
        )

        cached = self._check_cache() or IPOCalendar(timestamp=datetime.now())
        cached.ipos.append(ipo)
        cached.ipos.sort(key=lambda i: i.expected_date)
        self._update_cache(cached)

        return ipo

    def update_ipo_priced(
        self,
        symbol: str,
        price_final: float,
        first_day_return: Optional[float] = None,
    ) -> bool:
        """Update an IPO as priced."""
        cached = self._check_cache()
        if not cached:
            return False

        for ipo in cached.ipos:
            if ipo.symbol.upper() == symbol.upper():
                ipo.status = "priced"
                ipo.price_final = price_final
                ipo.first_day_return = first_day_return
                ipo.last_updated = datetime.now()
                self._update_cache(cached)
                return True
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_ipo_calendar(days: int = 30) -> IPOCalendar:
    """Get IPO calendar."""
    source = IPOCalendarSource(lookforward_days=days)
    try:
        return await source.get_calendar()
    finally:
        await source.close()


async def get_upcoming_ipos() -> list[IPOEvent]:
    """Get upcoming IPOs."""
    calendar = await get_ipo_calendar()
    return calendar.upcoming


async def get_large_ipos() -> list[IPOEvent]:
    """Get large upcoming IPOs (>$500M)."""
    calendar = await get_ipo_calendar()
    return calendar.large_deals


if __name__ == "__main__":
    async def main():
        source = IPOCalendarSource()
        calendar = await source.get_calendar()

        print(f"IPO Calendar - {calendar.timestamp.date()}")
        print(f"Total IPOs: {len(calendar.ipos)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"Deal volume this week: ${calendar.total_deal_volume_this_week:.0f}M")

        if calendar.upcoming:
            print("\nUpcoming IPOs:")
            for ipo in calendar.upcoming[:10]:
                print(f"  {ipo.expected_date.strftime('%m/%d')} {ipo.symbol}: {ipo.company_name}")
                print(f"    Price: {ipo.price_range}, Deal: ${ipo.deal_size or 0:.0f}M")

        await source.close()

    asyncio.run(main())
