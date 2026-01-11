"""
Treasury Auction Calendar

Tracks Treasury debt auctions which can impact:
- Interest rates
- Bond prices
- Equity markets (through yield competition)

Large auctions can cause market volatility if demand is weak.

Data Source: TreasuryDirect.gov
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


class SecurityType(str, Enum):
    BILL_4W = "4-Week Bill"
    BILL_8W = "8-Week Bill"
    BILL_13W = "13-Week Bill"
    BILL_17W = "17-Week Bill"
    BILL_26W = "26-Week Bill"
    BILL_52W = "52-Week Bill"
    NOTE_2Y = "2-Year Note"
    NOTE_3Y = "3-Year Note"
    NOTE_5Y = "5-Year Note"
    NOTE_7Y = "7-Year Note"
    NOTE_10Y = "10-Year Note"
    BOND_20Y = "20-Year Bond"
    BOND_30Y = "30-Year Bond"
    TIPS_5Y = "5-Year TIPS"
    TIPS_10Y = "10-Year TIPS"
    TIPS_30Y = "30-Year TIPS"
    FRN_2Y = "2-Year FRN"


# Market impact levels for different security types
SECURITY_IMPACT = {
    SecurityType.BILL_4W: "low",
    SecurityType.BILL_8W: "low",
    SecurityType.BILL_13W: "low",
    SecurityType.BILL_17W: "low",
    SecurityType.BILL_26W: "low",
    SecurityType.BILL_52W: "low",
    SecurityType.NOTE_2Y: "medium",
    SecurityType.NOTE_3Y: "medium",
    SecurityType.NOTE_5Y: "medium",
    SecurityType.NOTE_7Y: "medium",
    SecurityType.NOTE_10Y: "high",
    SecurityType.BOND_20Y: "medium",
    SecurityType.BOND_30Y: "high",
    SecurityType.TIPS_5Y: "low",
    SecurityType.TIPS_10Y: "medium",
    SecurityType.TIPS_30Y: "medium",
    SecurityType.FRN_2Y: "low",
}


@dataclass
class TreasuryAuction:
    """Single Treasury auction event."""

    security_type: str
    auction_date: datetime
    settlement_date: Optional[datetime] = None
    announcement_date: Optional[datetime] = None

    # Auction details
    amount_billions: Optional[float] = None  # Offering amount
    previous_yield: Optional[float] = None  # Previous auction yield
    previous_bid_to_cover: Optional[float] = None  # Previous bid-to-cover ratio

    # Results (filled after auction)
    high_yield: Optional[float] = None
    bid_to_cover: Optional[float] = None
    indirect_pct: Optional[float] = None  # Foreign demand indicator
    direct_pct: Optional[float] = None

    # Market impact
    impact_level: str = "medium"  # high, medium, low
    notes: str = ""

    # Metadata
    source: str = "treasury"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "security_type": self.security_type,
            "auction_date": self.auction_date.isoformat(),
            "settlement_date": self.settlement_date.isoformat() if self.settlement_date else None,
            "announcement_date": self.announcement_date.isoformat() if self.announcement_date else None,
            "amount_billions": self.amount_billions,
            "previous_yield": self.previous_yield,
            "previous_bid_to_cover": self.previous_bid_to_cover,
            "high_yield": self.high_yield,
            "bid_to_cover": self.bid_to_cover,
            "indirect_pct": self.indirect_pct,
            "direct_pct": self.direct_pct,
            "impact_level": self.impact_level,
            "notes": self.notes,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TreasuryAuction":
        return cls(
            security_type=d["security_type"],
            auction_date=datetime.fromisoformat(d["auction_date"]),
            settlement_date=datetime.fromisoformat(d["settlement_date"]) if d.get("settlement_date") else None,
            announcement_date=datetime.fromisoformat(d["announcement_date"]) if d.get("announcement_date") else None,
            amount_billions=d.get("amount_billions"),
            previous_yield=d.get("previous_yield"),
            previous_bid_to_cover=d.get("previous_bid_to_cover"),
            high_yield=d.get("high_yield"),
            bid_to_cover=d.get("bid_to_cover"),
            indirect_pct=d.get("indirect_pct"),
            direct_pct=d.get("direct_pct"),
            impact_level=d.get("impact_level", "medium"),
            notes=d.get("notes", ""),
            source=d.get("source", "treasury"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_today(self) -> bool:
        return self.auction_date.date() == datetime.now().date()

    @property
    def is_high_impact(self) -> bool:
        return self.impact_level == "high"

    @property
    def days_until(self) -> int:
        return (self.auction_date.date() - datetime.now().date()).days

    @property
    def is_duration_sensitive(self) -> bool:
        """Check if this is a longer-duration security (more rate sensitive)."""
        return any(x in self.security_type for x in ["10-Year", "20-Year", "30-Year"])


@dataclass
class TreasuryCalendar:
    """Collection of Treasury auction events."""

    timestamp: datetime
    auctions: list[TreasuryAuction] = field(default_factory=list)

    @property
    def today(self) -> list[TreasuryAuction]:
        return [a for a in self.auctions if a.is_today]

    @property
    def this_week(self) -> list[TreasuryAuction]:
        return [a for a in self.auctions if 0 <= a.days_until <= 7]

    @property
    def high_impact(self) -> list[TreasuryAuction]:
        return [a for a in self.auctions if a.is_high_impact]

    @property
    def high_impact_this_week(self) -> list[TreasuryAuction]:
        return [a for a in self.this_week if a.is_high_impact]

    @property
    def duration_sensitive_this_week(self) -> list[TreasuryAuction]:
        return [a for a in self.this_week if a.is_duration_sensitive]

    @property
    def total_issuance_this_week(self) -> float:
        """Total billions being auctioned this week."""
        return sum(a.amount_billions or 0 for a in self.this_week)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "auctions": [a.to_dict() for a in self.auctions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TreasuryCalendar":
        auctions = [TreasuryAuction.from_dict(a) for a in d.get("auctions", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            auctions=auctions,
        )


class TreasuryCalendarSource:
    """
    Track Treasury auction calendar.

    Data source: TreasuryDirect.gov
    """

    name = "treasury_calendar"

    TREASURY_URL = "https://www.treasurydirect.gov/auctions/announcements-data-results/"

    def __init__(
        self,
        cache_ttl_hours: int = 12,
        cache_dir: Optional[Path] = None,
        lookforward_days: int = 14,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "treasury")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookforward_days = lookforward_days
        self._cache: Optional[tuple[datetime, TreasuryCalendar]] = None

    def _check_cache(self) -> Optional[TreasuryCalendar]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, calendar = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return calendar

        cache_file = self.cache_dir / "treasury_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                calendar = TreasuryCalendar.from_dict(data)
                if datetime.now() - calendar.timestamp < self.cache_ttl:
                    self._cache = (calendar.timestamp, calendar)
                    return calendar
            except Exception as e:
                logger.warning(f"Failed to load Treasury cache: {e}")

        return None

    def _update_cache(self, calendar: TreasuryCalendar) -> None:
        """Update cache."""
        self._cache = (datetime.now(), calendar)

        cache_file = self.cache_dir / "treasury_calendar.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(calendar.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save Treasury cache: {e}")

    async def get_calendar(self, force_refresh: bool = False) -> TreasuryCalendar:
        """
        Get Treasury auction calendar.

        Returns:
            TreasuryCalendar with upcoming auctions.
        """
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        try:
            calendar = await self._fetch_calendar()
            self._update_cache(calendar)
            return calendar
        except Exception as e:
            logger.error(f"Failed to fetch Treasury calendar: {e}")
            return self._get_estimated_calendar()

    async def _fetch_calendar(self) -> TreasuryCalendar:
        """
        Fetch Treasury calendar.

        In production, would scrape TreasuryDirect.
        For now, returns estimated schedule.
        """
        cache_file = self.cache_dir / "treasury_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return TreasuryCalendar.from_dict(data)
            except Exception:
                pass

        return self._get_estimated_calendar()

    def _get_estimated_calendar(self) -> TreasuryCalendar:
        """Generate estimated Treasury calendar based on typical schedule."""
        calendar = TreasuryCalendar(timestamp=datetime.now())
        today = datetime.now().date()

        # Typical weekly auction schedule:
        # Monday: 13-week, 26-week bills
        # Tuesday: 52-week bill (some weeks), Notes/Bonds
        # Wednesday: 4-week, 8-week bills
        # Thursday: Various notes/bonds

        # Generate placeholder auctions for next 2 weeks
        for week_offset in range(2):
            week_start = today + timedelta(days=7 * week_offset - today.weekday())

            # Monday - Bills
            monday = week_start
            if monday >= today:
                calendar.auctions.append(TreasuryAuction(
                    security_type=SecurityType.BILL_13W.value,
                    auction_date=datetime.combine(monday, datetime.min.time().replace(hour=11, minute=30)),
                    amount_billions=75.0,
                    impact_level="low",
                ))
                calendar.auctions.append(TreasuryAuction(
                    security_type=SecurityType.BILL_26W.value,
                    auction_date=datetime.combine(monday, datetime.min.time().replace(hour=11, minute=30)),
                    amount_billions=70.0,
                    impact_level="low",
                ))

            # Tuesday - Notes (alternating schedule)
            tuesday = week_start + timedelta(days=1)
            if tuesday >= today:
                # Simplified - would need actual schedule
                if week_offset == 0:
                    calendar.auctions.append(TreasuryAuction(
                        security_type=SecurityType.NOTE_3Y.value,
                        auction_date=datetime.combine(tuesday, datetime.min.time().replace(hour=13)),
                        amount_billions=58.0,
                        impact_level="medium",
                    ))
                else:
                    calendar.auctions.append(TreasuryAuction(
                        security_type=SecurityType.NOTE_10Y.value,
                        auction_date=datetime.combine(tuesday, datetime.min.time().replace(hour=13)),
                        amount_billions=42.0,
                        impact_level="high",
                    ))

            # Wednesday - Short bills
            wednesday = week_start + timedelta(days=2)
            if wednesday >= today:
                calendar.auctions.append(TreasuryAuction(
                    security_type=SecurityType.BILL_4W.value,
                    auction_date=datetime.combine(wednesday, datetime.min.time().replace(hour=11, minute=30)),
                    amount_billions=80.0,
                    impact_level="low",
                ))

            # Thursday - Bonds (some weeks)
            thursday = week_start + timedelta(days=3)
            if thursday >= today and week_offset == 1:
                calendar.auctions.append(TreasuryAuction(
                    security_type=SecurityType.BOND_30Y.value,
                    auction_date=datetime.combine(thursday, datetime.min.time().replace(hour=13)),
                    amount_billions=22.0,
                    impact_level="high",
                ))

        # Sort by date
        calendar.auctions.sort(key=lambda a: a.auction_date)

        return calendar

    def add_auction(
        self,
        security_type: str,
        auction_date: datetime,
        amount_billions: float,
        previous_yield: Optional[float] = None,
        notes: str = "",
    ) -> TreasuryAuction:
        """
        Manually add an auction to the calendar.
        """
        # Determine impact level
        impact = "medium"
        for sec_type, imp in SECURITY_IMPACT.items():
            if sec_type.value == security_type:
                impact = imp
                break

        auction = TreasuryAuction(
            security_type=security_type,
            auction_date=auction_date,
            amount_billions=amount_billions,
            previous_yield=previous_yield,
            impact_level=impact,
            notes=notes,
            source="manual",
        )

        # Get or create calendar
        cached = self._check_cache() or TreasuryCalendar(timestamp=datetime.now())
        cached.auctions.append(auction)
        cached.auctions.sort(key=lambda a: a.auction_date)
        self._update_cache(cached)

        return auction

    def has_high_impact_today(self) -> bool:
        """Check if there are high-impact auctions today."""
        cached = self._check_cache()
        if cached:
            return len([a for a in cached.today if a.is_high_impact]) > 0
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_treasury_calendar(days: int = 14) -> TreasuryCalendar:
    """Get Treasury auction calendar."""
    source = TreasuryCalendarSource(lookforward_days=days)
    try:
        return await source.get_calendar()
    finally:
        await source.close()


async def get_high_impact_auctions() -> list[TreasuryAuction]:
    """Get upcoming high-impact auctions."""
    calendar = await get_treasury_calendar()
    return calendar.high_impact


async def get_weekly_issuance() -> float:
    """Get total Treasury issuance this week in billions."""
    calendar = await get_treasury_calendar(days=7)
    return calendar.total_issuance_this_week


if __name__ == "__main__":
    async def main():
        source = TreasuryCalendarSource()
        calendar = await source.get_calendar()

        print(f"Treasury Calendar - {calendar.timestamp.date()}")
        print(f"Total auctions: {len(calendar.auctions)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"Weekly issuance: ${calendar.total_issuance_this_week:.0f}B")

        print("\nHigh Impact Auctions:")
        for a in calendar.high_impact[:5]:
            print(f"  {a.auction_date.strftime('%m/%d')} {a.security_type}: ${a.amount_billions or 0:.0f}B")

        print("\nAll This Week:")
        for a in calendar.this_week:
            print(f"  {a.auction_date.strftime('%a %m/%d')}: {a.security_type} (${a.amount_billions or 0:.0f}B)")

        await source.close()

    asyncio.run(main())
