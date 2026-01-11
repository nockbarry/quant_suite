"""
Patent Filings

Tracks patent activity for public companies via USPTO.

Patent activity can indicate:
- R&D investment and innovation pipeline
- Future competitive moats
- Technology direction
- Potential licensing revenue

Data Source: USPTO API (free)
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


# Company to assignee name mappings for USPTO searches
COMPANY_ASSIGNEES = {
    "AAPL": ["Apple Inc.", "Apple Computer"],
    "MSFT": ["Microsoft Corporation", "Microsoft Technology Licensing"],
    "GOOGL": ["Google LLC", "Alphabet Inc.", "Google Inc."],
    "AMZN": ["Amazon Technologies", "Amazon.com"],
    "META": ["Meta Platforms", "Facebook", "Instagram"],
    "NVDA": ["NVIDIA Corporation"],
    "AMD": ["Advanced Micro Devices"],
    "INTC": ["Intel Corporation"],
    "TSLA": ["Tesla", "Tesla Motors"],
    "IBM": ["International Business Machines"],
    "ORCL": ["Oracle"],
    "CRM": ["Salesforce"],
    "ADBE": ["Adobe"],
    "QCOM": ["Qualcomm"],
    "AVGO": ["Broadcom"],
    "TXN": ["Texas Instruments"],
    "MU": ["Micron Technology"],
}


@dataclass
class Patent:
    """Single patent filing."""

    patent_number: str
    title: str
    abstract: str
    filing_date: datetime
    grant_date: Optional[datetime] = None
    assignee: str = ""
    inventors: list[str] = field(default_factory=list)
    classification: str = ""  # CPC/IPC classification
    claims_count: int = 0
    citation_count: int = 0

    def to_dict(self) -> dict:
        return {
            "patent_number": self.patent_number,
            "title": self.title,
            "abstract": self.abstract,
            "filing_date": self.filing_date.isoformat(),
            "grant_date": self.grant_date.isoformat() if self.grant_date else None,
            "assignee": self.assignee,
            "inventors": self.inventors,
            "classification": self.classification,
            "claims_count": self.claims_count,
            "citation_count": self.citation_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Patent":
        return cls(
            patent_number=d["patent_number"],
            title=d["title"],
            abstract=d.get("abstract", ""),
            filing_date=datetime.fromisoformat(d["filing_date"]),
            grant_date=datetime.fromisoformat(d["grant_date"]) if d.get("grant_date") else None,
            assignee=d.get("assignee", ""),
            inventors=d.get("inventors", []),
            classification=d.get("classification", ""),
            claims_count=d.get("claims_count", 0),
            citation_count=d.get("citation_count", 0),
        )


@dataclass
class PatentActivity:
    """Patent activity summary for a company."""

    symbol: str
    company: str
    period_start: datetime
    period_end: datetime

    # Counts
    patents_filed: int = 0
    patents_granted: int = 0
    applications_published: int = 0

    # Trends
    yoy_change_filed: Optional[float] = None  # Year-over-year change in filings
    yoy_change_granted: Optional[float] = None

    # Technology focus
    key_technologies: list[str] = field(default_factory=list)
    top_classifications: dict[str, int] = field(default_factory=dict)

    # Quality indicators
    avg_claims_per_patent: float = 0.0
    avg_citations: float = 0.0

    # Computed signals
    innovation_score: float = 0.0  # Normalized 0-100
    acceleration_signal: float = 0.0  # -1 to +1 (slowing to accelerating)

    # Sample patents
    recent_patents: list[Patent] = field(default_factory=list)

    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company": self.company,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "patents_filed": self.patents_filed,
            "patents_granted": self.patents_granted,
            "applications_published": self.applications_published,
            "yoy_change_filed": self.yoy_change_filed,
            "yoy_change_granted": self.yoy_change_granted,
            "key_technologies": self.key_technologies,
            "top_classifications": self.top_classifications,
            "avg_claims_per_patent": self.avg_claims_per_patent,
            "avg_citations": self.avg_citations,
            "innovation_score": self.innovation_score,
            "acceleration_signal": self.acceleration_signal,
            "recent_patents": [p.to_dict() for p in self.recent_patents],
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatentActivity":
        return cls(
            symbol=d["symbol"],
            company=d["company"],
            period_start=datetime.fromisoformat(d["period_start"]),
            period_end=datetime.fromisoformat(d["period_end"]),
            patents_filed=d.get("patents_filed", 0),
            patents_granted=d.get("patents_granted", 0),
            applications_published=d.get("applications_published", 0),
            yoy_change_filed=d.get("yoy_change_filed"),
            yoy_change_granted=d.get("yoy_change_granted"),
            key_technologies=d.get("key_technologies", []),
            top_classifications=d.get("top_classifications", {}),
            avg_claims_per_patent=d.get("avg_claims_per_patent", 0.0),
            avg_citations=d.get("avg_citations", 0.0),
            innovation_score=d.get("innovation_score", 0.0),
            acceleration_signal=d.get("acceleration_signal", 0.0),
            recent_patents=[Patent.from_dict(p) for p in d.get("recent_patents", [])],
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_accelerating(self) -> bool:
        """Check if patent activity is accelerating."""
        return self.yoy_change_filed is not None and self.yoy_change_filed > 0.10

    @property
    def is_decelerating(self) -> bool:
        """Check if patent activity is slowing."""
        return self.yoy_change_filed is not None and self.yoy_change_filed < -0.10


@dataclass
class PatentDatabase:
    """Collection of patent activity data."""

    timestamp: datetime
    activities: dict[str, PatentActivity] = field(default_factory=dict)  # symbol -> activity

    def get_activity(self, symbol: str) -> Optional[PatentActivity]:
        return self.activities.get(symbol.upper())

    def get_accelerating(self) -> list[PatentActivity]:
        """Get companies with accelerating patent activity."""
        return [a for a in self.activities.values() if a.is_accelerating]

    def get_decelerating(self) -> list[PatentActivity]:
        """Get companies with slowing patent activity."""
        return [a for a in self.activities.values() if a.is_decelerating]

    def get_top_innovators(self, n: int = 10) -> list[PatentActivity]:
        """Get top N companies by innovation score."""
        sorted_activities = sorted(
            self.activities.values(),
            key=lambda a: a.innovation_score,
            reverse=True,
        )
        return sorted_activities[:n]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "activities": {k: v.to_dict() for k, v in self.activities.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatentDatabase":
        activities = {k: PatentActivity.from_dict(v) for k, v in d.get("activities", {}).items()}
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            activities=activities,
        )


class USPTOSource:
    """
    USPTO patent data source.

    Uses USPTO PatentsView API (free, no auth required).
    Rate limited to 45 requests/minute.
    """

    name = "patent_filings"

    USPTO_API = "https://api.patentsview.org/patents/query"

    def __init__(
        self,
        cache_ttl_days: int = 7,
        cache_dir: Optional[Path] = None,
        lookback_days: int = 365,
    ):
        self.cache_ttl = timedelta(days=cache_ttl_days)
        self.cache_dir = cache_dir or (paths.scraped_data / "patents")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookback_days = lookback_days
        self._cache: Optional[tuple[datetime, PatentDatabase]] = None

    def _check_cache(self) -> Optional[PatentDatabase]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, database = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return database

        cache_file = self.cache_dir / "patent_database.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                database = PatentDatabase.from_dict(data)
                if datetime.now() - database.timestamp < self.cache_ttl:
                    self._cache = (database.timestamp, database)
                    return database
            except Exception as e:
                logger.warning(f"Failed to load patent cache: {e}")

        return None

    def _update_cache(self, database: PatentDatabase) -> None:
        """Update cache."""
        self._cache = (datetime.now(), database)

        cache_file = self.cache_dir / "patent_database.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(database.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save patent cache: {e}")

    async def get_database(
        self,
        symbols: Optional[list[str]] = None,
        force_refresh: bool = False,
    ) -> PatentDatabase:
        """Get patent database for tracked companies."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                if symbols:
                    # Return filtered view
                    filtered = PatentDatabase(timestamp=cached.timestamp)
                    for sym in symbols:
                        if sym.upper() in cached.activities:
                            filtered.activities[sym.upper()] = cached.activities[sym.upper()]
                    return filtered
                return cached

        try:
            database = await self._fetch_database(symbols)
            self._update_cache(database)
            return database
        except Exception as e:
            logger.error(f"Failed to fetch patent database: {e}")
            return PatentDatabase(timestamp=datetime.now())

    async def _fetch_database(self, symbols: Optional[list[str]] = None) -> PatentDatabase:
        """
        Fetch patent data from USPTO.

        In production, would use PatentsView API.
        For now, returns cached data or placeholder.
        """
        cache_file = self.cache_dir / "patent_database.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return PatentDatabase.from_dict(data)
            except Exception:
                pass

        # Return empty database
        return PatentDatabase(timestamp=datetime.now())

    async def fetch_company_patents(
        self,
        symbol: str,
        days: int = 365,
    ) -> PatentActivity:
        """
        Fetch patent activity for a specific company.

        Uses USPTO PatentsView API.
        """
        if symbol.upper() not in COMPANY_ASSIGNEES:
            return PatentActivity(
                symbol=symbol.upper(),
                company=symbol,
                period_start=datetime.now() - timedelta(days=days),
                period_end=datetime.now(),
            )

        # In production, would call USPTO API here
        # For now, return placeholder
        return PatentActivity(
            symbol=symbol.upper(),
            company=COMPANY_ASSIGNEES[symbol.upper()][0],
            period_start=datetime.now() - timedelta(days=days),
            period_end=datetime.now(),
        )

    def add_activity(self, activity: PatentActivity) -> None:
        """Manually add patent activity data."""
        cached = self._check_cache() or PatentDatabase(timestamp=datetime.now())
        cached.activities[activity.symbol.upper()] = activity
        self._update_cache(cached)

    def update_activity(
        self,
        symbol: str,
        patents_filed: int,
        patents_granted: int,
        yoy_change: Optional[float] = None,
        key_technologies: Optional[list[str]] = None,
    ) -> bool:
        """Update patent activity for a company."""
        cached = self._check_cache()
        if not cached:
            cached = PatentDatabase(timestamp=datetime.now())

        if symbol.upper() not in cached.activities:
            # Create new entry
            cached.activities[symbol.upper()] = PatentActivity(
                symbol=symbol.upper(),
                company=COMPANY_ASSIGNEES.get(symbol.upper(), [symbol])[0],
                period_start=datetime.now() - timedelta(days=365),
                period_end=datetime.now(),
            )

        activity = cached.activities[symbol.upper()]
        activity.patents_filed = patents_filed
        activity.patents_granted = patents_granted
        activity.yoy_change_filed = yoy_change
        if key_technologies:
            activity.key_technologies = key_technologies
        activity.last_updated = datetime.now()

        # Compute innovation score (simplified)
        # Based on filing rate and trend
        base_score = min(patents_filed / 10, 50)  # Cap base at 50
        if yoy_change:
            trend_bonus = yoy_change * 25  # +/- 25 for growth/decline
            base_score += trend_bonus
        activity.innovation_score = max(0, min(100, base_score))

        # Compute acceleration signal
        if yoy_change is not None:
            activity.acceleration_signal = max(-1, min(1, yoy_change))
        else:
            activity.acceleration_signal = 0.0

        self._update_cache(cached)
        return True

    def get_innovation_signal(self, symbol: str) -> Optional[float]:
        """
        Get innovation signal for a symbol.

        Returns -1 to +1:
        - Positive: Accelerating innovation (bullish for long-term)
        - Negative: Slowing innovation (bearish for long-term)
        - Zero: No data or stable
        """
        cached = self._check_cache()
        if cached and symbol.upper() in cached.activities:
            return cached.activities[symbol.upper()].acceleration_signal
        return None

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_patent_activity(symbol: str) -> Optional[PatentActivity]:
    """Get patent activity for a symbol."""
    source = USPTOSource()
    try:
        database = await source.get_database([symbol])
        return database.get_activity(symbol)
    finally:
        await source.close()


async def get_top_innovators(n: int = 10) -> list[PatentActivity]:
    """Get top innovating companies."""
    source = USPTOSource()
    try:
        database = await source.get_database()
        return database.get_top_innovators(n)
    finally:
        await source.close()


async def get_accelerating_innovation() -> list[PatentActivity]:
    """Get companies with accelerating patent activity."""
    source = USPTOSource()
    try:
        database = await source.get_database()
        return database.get_accelerating()
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = USPTOSource()

        # Add some example data
        source.update_activity(
            symbol="AAPL",
            patents_filed=2500,
            patents_granted=1800,
            yoy_change=0.15,
            key_technologies=["Neural Engine", "AR/VR", "Battery", "Display"],
        )

        source.update_activity(
            symbol="MSFT",
            patents_filed=3200,
            patents_granted=2400,
            yoy_change=0.22,
            key_technologies=["AI/ML", "Cloud", "Security", "Gaming"],
        )

        source.update_activity(
            symbol="GOOGL",
            patents_filed=2800,
            patents_granted=2100,
            yoy_change=0.08,
            key_technologies=["AI/ML", "Search", "Autonomous Vehicles", "Cloud"],
        )

        database = await source.get_database()

        print(f"Patent Database - {database.timestamp.date()}")
        print(f"Companies tracked: {len(database.activities)}")

        print("\nTop Innovators:")
        for activity in database.get_top_innovators(5):
            print(f"  {activity.symbol}: {activity.patents_filed} filed, score={activity.innovation_score:.0f}")
            print(f"    YoY Change: {activity.yoy_change_filed or 0:.1%}")
            print(f"    Focus: {', '.join(activity.key_technologies[:3])}")

        if database.get_accelerating():
            print("\nAccelerating Innovation:")
            for activity in database.get_accelerating():
                print(f"  {activity.symbol}: +{activity.yoy_change_filed:.1%} YoY")

        await source.close()

    asyncio.run(main())
