"""
Job Postings

Tracks job posting activity for public companies as a growth indicator.

Job postings can indicate:
- Company growth trajectory
- Expansion into new areas
- Hiring freezes or layoffs
- Strategic priorities (engineering vs sales)

Data Sources:
- Company career pages (scrape)
- Indeed/LinkedIn public counts
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


# Company career page URLs
CAREER_PAGES = {
    "AAPL": "https://jobs.apple.com",
    "MSFT": "https://careers.microsoft.com",
    "GOOGL": "https://careers.google.com",
    "AMZN": "https://amazon.jobs",
    "META": "https://metacareers.com",
    "NVDA": "https://nvidia.wd5.myworkdayjobs.com",
    "TSLA": "https://tesla.com/careers",
    "NFLX": "https://jobs.netflix.com",
    "CRM": "https://salesforce.wd12.myworkdayjobs.com",
    "ADBE": "https://adobe.wd5.myworkdayjobs.com",
}


@dataclass
class JobPostings:
    """Job posting data for a company."""

    symbol: str
    company: str
    snapshot_date: datetime

    # Total counts
    total_openings: int = 0
    total_openings_previous: Optional[int] = None  # Previous snapshot for comparison

    # By department/function
    engineering_roles: int = 0
    sales_roles: int = 0
    marketing_roles: int = 0
    operations_roles: int = 0
    hr_roles: int = 0
    finance_roles: int = 0
    other_roles: int = 0

    # By level
    entry_level: int = 0
    mid_level: int = 0
    senior_level: int = 0
    executive_roles: int = 0

    # By location
    remote_roles: int = 0
    us_roles: int = 0
    international_roles: int = 0

    # Changes
    change_7d: Optional[int] = None
    change_30d: Optional[int] = None
    change_pct_7d: Optional[float] = None
    change_pct_30d: Optional[float] = None

    # Signals
    growth_signal: str = "stable"  # "expanding", "stable", "contracting"
    growth_score: float = 0.0  # -1 to +1

    # Metadata
    source: str = "manual"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company": self.company,
            "snapshot_date": self.snapshot_date.isoformat(),
            "total_openings": self.total_openings,
            "total_openings_previous": self.total_openings_previous,
            "engineering_roles": self.engineering_roles,
            "sales_roles": self.sales_roles,
            "marketing_roles": self.marketing_roles,
            "operations_roles": self.operations_roles,
            "hr_roles": self.hr_roles,
            "finance_roles": self.finance_roles,
            "other_roles": self.other_roles,
            "entry_level": self.entry_level,
            "mid_level": self.mid_level,
            "senior_level": self.senior_level,
            "executive_roles": self.executive_roles,
            "remote_roles": self.remote_roles,
            "us_roles": self.us_roles,
            "international_roles": self.international_roles,
            "change_7d": self.change_7d,
            "change_30d": self.change_30d,
            "change_pct_7d": self.change_pct_7d,
            "change_pct_30d": self.change_pct_30d,
            "growth_signal": self.growth_signal,
            "growth_score": self.growth_score,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobPostings":
        return cls(
            symbol=d["symbol"],
            company=d["company"],
            snapshot_date=datetime.fromisoformat(d["snapshot_date"]),
            total_openings=d.get("total_openings", 0),
            total_openings_previous=d.get("total_openings_previous"),
            engineering_roles=d.get("engineering_roles", 0),
            sales_roles=d.get("sales_roles", 0),
            marketing_roles=d.get("marketing_roles", 0),
            operations_roles=d.get("operations_roles", 0),
            hr_roles=d.get("hr_roles", 0),
            finance_roles=d.get("finance_roles", 0),
            other_roles=d.get("other_roles", 0),
            entry_level=d.get("entry_level", 0),
            mid_level=d.get("mid_level", 0),
            senior_level=d.get("senior_level", 0),
            executive_roles=d.get("executive_roles", 0),
            remote_roles=d.get("remote_roles", 0),
            us_roles=d.get("us_roles", 0),
            international_roles=d.get("international_roles", 0),
            change_7d=d.get("change_7d"),
            change_30d=d.get("change_30d"),
            change_pct_7d=d.get("change_pct_7d"),
            change_pct_30d=d.get("change_pct_30d"),
            growth_signal=d.get("growth_signal", "stable"),
            growth_score=d.get("growth_score", 0.0),
            source=d.get("source", "manual"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def engineering_ratio(self) -> float:
        """Ratio of engineering to total roles."""
        if self.total_openings == 0:
            return 0.0
        return self.engineering_roles / self.total_openings

    @property
    def sales_engineering_ratio(self) -> float:
        """Ratio of sales to engineering - high = sales focus, low = product focus."""
        if self.engineering_roles == 0:
            return float("inf") if self.sales_roles > 0 else 0.0
        return self.sales_roles / self.engineering_roles

    @property
    def is_expanding(self) -> bool:
        return self.growth_signal == "expanding"

    @property
    def is_contracting(self) -> bool:
        return self.growth_signal == "contracting"


@dataclass
class JobDatabase:
    """Collection of job posting data."""

    timestamp: datetime
    postings: dict[str, JobPostings] = field(default_factory=dict)  # symbol -> postings
    history: dict[str, list[tuple[datetime, int]]] = field(default_factory=dict)  # symbol -> [(date, count)]

    def get_postings(self, symbol: str) -> Optional[JobPostings]:
        return self.postings.get(symbol.upper())

    def get_expanding(self) -> list[JobPostings]:
        """Get companies that are expanding hiring."""
        return [p for p in self.postings.values() if p.is_expanding]

    def get_contracting(self) -> list[JobPostings]:
        """Get companies that are contracting hiring."""
        return [p for p in self.postings.values() if p.is_contracting]

    def get_top_hirers(self, n: int = 10) -> list[JobPostings]:
        """Get top N companies by job openings."""
        sorted_postings = sorted(
            self.postings.values(),
            key=lambda p: p.total_openings,
            reverse=True,
        )
        return sorted_postings[:n]

    def get_fastest_growing(self, n: int = 10) -> list[JobPostings]:
        """Get top N fastest growing hiring."""
        with_growth = [p for p in self.postings.values() if p.change_pct_30d is not None]
        sorted_postings = sorted(
            with_growth,
            key=lambda p: p.change_pct_30d or 0,
            reverse=True,
        )
        return sorted_postings[:n]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "postings": {k: v.to_dict() for k, v in self.postings.items()},
            "history": {k: [(d.isoformat(), c) for d, c in v] for k, v in self.history.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobDatabase":
        postings = {k: JobPostings.from_dict(v) for k, v in d.get("postings", {}).items()}
        history = {
            k: [(datetime.fromisoformat(d), c) for d, c in v]
            for k, v in d.get("history", {}).items()
        }
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            postings=postings,
            history=history,
        )


class JobPostingSource:
    """
    Track job posting data for public companies.

    Data sources:
    - Company career pages
    - Indeed public counts
    - LinkedIn job counts
    """

    name = "job_postings"

    def __init__(
        self,
        cache_ttl_days: int = 3,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(days=cache_ttl_days)
        self.cache_dir = cache_dir or (paths.scraped_data / "jobs")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[tuple[datetime, JobDatabase]] = None

    def _check_cache(self) -> Optional[JobDatabase]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, database = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return database

        cache_file = self.cache_dir / "job_database.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                database = JobDatabase.from_dict(data)
                if datetime.now() - database.timestamp < self.cache_ttl:
                    self._cache = (database.timestamp, database)
                    return database
            except Exception as e:
                logger.warning(f"Failed to load job cache: {e}")

        return None

    def _update_cache(self, database: JobDatabase) -> None:
        """Update cache."""
        self._cache = (datetime.now(), database)

        cache_file = self.cache_dir / "job_database.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(database.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save job cache: {e}")

    async def get_database(
        self,
        symbols: Optional[list[str]] = None,
        force_refresh: bool = False,
    ) -> JobDatabase:
        """Get job posting database."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                if symbols:
                    filtered = JobDatabase(timestamp=cached.timestamp)
                    for sym in symbols:
                        if sym.upper() in cached.postings:
                            filtered.postings[sym.upper()] = cached.postings[sym.upper()]
                    return filtered
                return cached

        try:
            database = await self._fetch_database(symbols)
            self._update_cache(database)
            return database
        except Exception as e:
            logger.error(f"Failed to fetch job database: {e}")
            return JobDatabase(timestamp=datetime.now())

    async def _fetch_database(self, symbols: Optional[list[str]] = None) -> JobDatabase:
        """
        Fetch job posting data.

        In production, would scrape career pages.
        For now, returns cached data.
        """
        cache_file = self.cache_dir / "job_database.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return JobDatabase.from_dict(data)
            except Exception:
                pass

        return JobDatabase(timestamp=datetime.now())

    def update_postings(
        self,
        symbol: str,
        company: str,
        total_openings: int,
        engineering_roles: int = 0,
        sales_roles: int = 0,
        previous_count: Optional[int] = None,
    ) -> JobPostings:
        """
        Update job posting data for a company.

        Args:
            symbol: Stock ticker
            company: Company name
            total_openings: Total job openings
            engineering_roles: Engineering/tech roles
            sales_roles: Sales/BD roles
            previous_count: Previous snapshot for comparison
        """
        cached = self._check_cache() or JobDatabase(timestamp=datetime.now())

        # Get existing or create new
        existing = cached.postings.get(symbol.upper())

        # Compute changes
        change_30d = None
        change_pct_30d = None
        if previous_count is not None:
            change_30d = total_openings - previous_count
            if previous_count > 0:
                change_pct_30d = change_30d / previous_count

        # Determine growth signal
        growth_signal = "stable"
        growth_score = 0.0
        if change_pct_30d is not None:
            if change_pct_30d > 0.10:
                growth_signal = "expanding"
                growth_score = min(1.0, change_pct_30d)
            elif change_pct_30d < -0.10:
                growth_signal = "contracting"
                growth_score = max(-1.0, change_pct_30d)

        postings = JobPostings(
            symbol=symbol.upper(),
            company=company,
            snapshot_date=datetime.now(),
            total_openings=total_openings,
            total_openings_previous=previous_count or (existing.total_openings if existing else None),
            engineering_roles=engineering_roles,
            sales_roles=sales_roles,
            other_roles=total_openings - engineering_roles - sales_roles,
            change_30d=change_30d,
            change_pct_30d=change_pct_30d,
            growth_signal=growth_signal,
            growth_score=growth_score,
            source="manual",
        )

        cached.postings[symbol.upper()] = postings

        # Update history
        if symbol.upper() not in cached.history:
            cached.history[symbol.upper()] = []
        cached.history[symbol.upper()].append((datetime.now(), total_openings))
        # Keep last 90 days of history
        cached.history[symbol.upper()] = [
            (d, c) for d, c in cached.history[symbol.upper()]
            if datetime.now() - d < timedelta(days=90)
        ]

        self._update_cache(cached)
        return postings

    def get_growth_signal(self, symbol: str) -> Optional[float]:
        """
        Get growth signal for a symbol.

        Returns -1 to +1:
        - Positive: Expanding hiring (bullish)
        - Negative: Contracting hiring (bearish)
        - Zero: Stable or no data
        """
        cached = self._check_cache()
        if cached and symbol.upper() in cached.postings:
            return cached.postings[symbol.upper()].growth_score
        return None

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_job_postings(symbol: str) -> Optional[JobPostings]:
    """Get job posting data for a symbol."""
    source = JobPostingSource()
    try:
        database = await source.get_database([symbol])
        return database.get_postings(symbol)
    finally:
        await source.close()


async def get_expanding_companies() -> list[JobPostings]:
    """Get companies with expanding hiring."""
    source = JobPostingSource()
    try:
        database = await source.get_database()
        return database.get_expanding()
    finally:
        await source.close()


async def get_contracting_companies() -> list[JobPostings]:
    """Get companies with contracting hiring."""
    source = JobPostingSource()
    try:
        database = await source.get_database()
        return database.get_contracting()
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = JobPostingSource()

        # Add example data
        source.update_postings(
            symbol="AAPL",
            company="Apple",
            total_openings=5200,
            engineering_roles=2800,
            sales_roles=800,
            previous_count=4800,
        )

        source.update_postings(
            symbol="MSFT",
            company="Microsoft",
            total_openings=8500,
            engineering_roles=4500,
            sales_roles=1500,
            previous_count=8200,
        )

        source.update_postings(
            symbol="META",
            company="Meta Platforms",
            total_openings=2100,
            engineering_roles=1400,
            sales_roles=200,
            previous_count=3500,
        )

        database = await source.get_database()

        print(f"Job Postings Database - {database.timestamp.date()}")
        print(f"Companies tracked: {len(database.postings)}")

        print("\nTop Hirers:")
        for p in database.get_top_hirers(5):
            print(f"  {p.symbol}: {p.total_openings} openings")
            print(f"    Engineering: {p.engineering_roles} ({p.engineering_ratio:.0%})")
            if p.change_pct_30d:
                print(f"    30d Change: {p.change_pct_30d:+.1%}")

        print("\nExpanding:")
        for p in database.get_expanding():
            print(f"  {p.symbol}: +{p.change_pct_30d:.1%} ({p.total_openings} openings)")

        print("\nContracting:")
        for p in database.get_contracting():
            print(f"  {p.symbol}: {p.change_pct_30d:.1%} ({p.total_openings} openings)")

        await source.close()

    asyncio.run(main())
