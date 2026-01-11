"""
GitHub Activity

Tracks GitHub organization activity for public tech companies.

GitHub activity can indicate:
- Developer engagement and interest
- Open source strategy and community building
- Technology adoption trends
- Hiring pipeline (contributors often become employees)

Data Source: GitHub API (free, 60 req/hr unauthenticated)
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


# Map stock symbols to GitHub organization names
COMPANY_ORGS = {
    "MSFT": ["microsoft", "Azure", "dotnet"],
    "GOOGL": ["google", "googlecloudplatform", "tensorflow"],
    "META": ["facebook", "facebookresearch", "pytorch"],
    "AMZN": ["aws", "amazon"],
    "AAPL": ["apple"],
    "NVDA": ["NVIDIA", "NVIDIA-AI-IOT"],
    "AMD": ["ROCm", "RadeonOpenCompute"],
    "INTC": ["intel", "oneapi-src"],
    "IBM": ["IBM"],
    "ORCL": ["oracle", "graalvm"],
    "CRM": ["salesforce", "salesforceux"],
    "ADBE": ["adobe"],
    "TSLA": [],  # Limited public repos
    "NFLX": ["Netflix"],
    "UBER": ["uber", "uber-go"],
    "SNAP": ["snapchat"],
    "TWTR": [],  # Now X, limited public
    "SHOP": ["Shopify"],
    "SQ": ["square", "cashapp"],
    "PLTR": ["palantir"],
    "SNOW": ["snowflakedb"],
    "DDOG": ["DataDog"],
    "MDB": ["mongodb"],
    "CRWD": ["CrowdStrike"],
    "ZS": ["zscaler"],
    "OKTA": ["okta"],
    "NET": ["cloudflare"],
    "TWLO": ["twilio"],
    "DOCN": ["digitalocean"],
}


@dataclass
class GitHubRepo:
    """Summary of a GitHub repository."""

    name: str
    full_name: str
    description: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    language: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "stars": self.stars,
            "forks": self.forks,
            "watchers": self.watchers,
            "open_issues": self.open_issues,
            "language": self.language,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GitHubRepo":
        return cls(
            name=d["name"],
            full_name=d["full_name"],
            description=d.get("description", ""),
            stars=d.get("stars", 0),
            forks=d.get("forks", 0),
            watchers=d.get("watchers", 0),
            open_issues=d.get("open_issues", 0),
            language=d.get("language"),
            created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
            updated_at=datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else None,
            pushed_at=datetime.fromisoformat(d["pushed_at"]) if d.get("pushed_at") else None,
        )


@dataclass
class GitHubActivity:
    """GitHub activity summary for a company."""

    symbol: str
    org_names: list[str]
    snapshot_date: datetime

    # Aggregate stats
    public_repos: int = 0
    total_stars: int = 0
    total_forks: int = 0
    total_watchers: int = 0

    # Trends
    stars_30d_ago: Optional[int] = None
    stars_change_30d: Optional[int] = None
    stars_change_pct_30d: Optional[float] = None

    # Activity metrics
    repos_updated_30d: int = 0
    repos_created_30d: int = 0
    contributors_active_30d: int = 0
    commit_velocity: float = 0.0  # Commits per day (estimated)

    # Top repos
    top_repos: list[GitHubRepo] = field(default_factory=list)

    # Top languages
    languages: dict[str, int] = field(default_factory=dict)  # language -> repo count

    # Signals
    developer_interest_signal: float = 0.0  # -1 to +1
    activity_trend: str = "stable"  # "growing", "stable", "declining"

    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "org_names": self.org_names,
            "snapshot_date": self.snapshot_date.isoformat(),
            "public_repos": self.public_repos,
            "total_stars": self.total_stars,
            "total_forks": self.total_forks,
            "total_watchers": self.total_watchers,
            "stars_30d_ago": self.stars_30d_ago,
            "stars_change_30d": self.stars_change_30d,
            "stars_change_pct_30d": self.stars_change_pct_30d,
            "repos_updated_30d": self.repos_updated_30d,
            "repos_created_30d": self.repos_created_30d,
            "contributors_active_30d": self.contributors_active_30d,
            "commit_velocity": self.commit_velocity,
            "top_repos": [r.to_dict() for r in self.top_repos],
            "languages": self.languages,
            "developer_interest_signal": self.developer_interest_signal,
            "activity_trend": self.activity_trend,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GitHubActivity":
        return cls(
            symbol=d["symbol"],
            org_names=d.get("org_names", []),
            snapshot_date=datetime.fromisoformat(d["snapshot_date"]),
            public_repos=d.get("public_repos", 0),
            total_stars=d.get("total_stars", 0),
            total_forks=d.get("total_forks", 0),
            total_watchers=d.get("total_watchers", 0),
            stars_30d_ago=d.get("stars_30d_ago"),
            stars_change_30d=d.get("stars_change_30d"),
            stars_change_pct_30d=d.get("stars_change_pct_30d"),
            repos_updated_30d=d.get("repos_updated_30d", 0),
            repos_created_30d=d.get("repos_created_30d", 0),
            contributors_active_30d=d.get("contributors_active_30d", 0),
            commit_velocity=d.get("commit_velocity", 0.0),
            top_repos=[GitHubRepo.from_dict(r) for r in d.get("top_repos", [])],
            languages=d.get("languages", {}),
            developer_interest_signal=d.get("developer_interest_signal", 0.0),
            activity_trend=d.get("activity_trend", "stable"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_growing(self) -> bool:
        return self.activity_trend == "growing"

    @property
    def is_declining(self) -> bool:
        return self.activity_trend == "declining"

    @property
    def has_significant_presence(self) -> bool:
        """Check if company has meaningful GitHub presence."""
        return self.total_stars >= 1000 or self.public_repos >= 50


@dataclass
class GitHubDatabase:
    """Collection of GitHub activity data."""

    timestamp: datetime
    activities: dict[str, GitHubActivity] = field(default_factory=dict)  # symbol -> activity

    def get_activity(self, symbol: str) -> Optional[GitHubActivity]:
        return self.activities.get(symbol.upper())

    def get_growing(self) -> list[GitHubActivity]:
        """Get companies with growing GitHub presence."""
        return [a for a in self.activities.values() if a.is_growing]

    def get_declining(self) -> list[GitHubActivity]:
        """Get companies with declining GitHub presence."""
        return [a for a in self.activities.values() if a.is_declining]

    def get_top_by_stars(self, n: int = 10) -> list[GitHubActivity]:
        """Get top N companies by total stars."""
        sorted_activities = sorted(
            self.activities.values(),
            key=lambda a: a.total_stars,
            reverse=True,
        )
        return sorted_activities[:n]

    def get_fastest_growing(self, n: int = 10) -> list[GitHubActivity]:
        """Get companies with fastest star growth."""
        with_growth = [a for a in self.activities.values() if a.stars_change_pct_30d is not None]
        sorted_activities = sorted(
            with_growth,
            key=lambda a: a.stars_change_pct_30d or 0,
            reverse=True,
        )
        return sorted_activities[:n]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "activities": {k: v.to_dict() for k, v in self.activities.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GitHubDatabase":
        activities = {k: GitHubActivity.from_dict(v) for k, v in d.get("activities", {}).items()}
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            activities=activities,
        )


class GitHubSource:
    """
    Track GitHub activity for public companies.

    Uses GitHub API (60 requests/hour unauthenticated).
    Can use authenticated token for 5000 req/hour.
    """

    name = "github_activity"

    GITHUB_API = "https://api.github.com"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        cache_dir: Optional[Path] = None,
        api_token: Optional[str] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "github")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_token = api_token
        self._cache: Optional[tuple[datetime, GitHubDatabase]] = None
        self._rate_limit_remaining = 60

    def _check_cache(self) -> Optional[GitHubDatabase]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, database = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return database

        cache_file = self.cache_dir / "github_activity.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                database = GitHubDatabase.from_dict(data)
                if datetime.now() - database.timestamp < self.cache_ttl:
                    self._cache = (database.timestamp, database)
                    return database
            except Exception as e:
                logger.warning(f"Failed to load GitHub cache: {e}")

        return None

    def _update_cache(self, database: GitHubDatabase) -> None:
        """Update cache."""
        self._cache = (datetime.now(), database)

        cache_file = self.cache_dir / "github_activity.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(database.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save GitHub cache: {e}")

    async def get_database(
        self,
        symbols: Optional[list[str]] = None,
        force_refresh: bool = False,
    ) -> GitHubDatabase:
        """Get GitHub activity database."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                if symbols:
                    filtered = GitHubDatabase(timestamp=cached.timestamp)
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
            logger.error(f"Failed to fetch GitHub database: {e}")
            return GitHubDatabase(timestamp=datetime.now())

    async def _fetch_database(self, symbols: Optional[list[str]] = None) -> GitHubDatabase:
        """
        Fetch GitHub activity data.

        In production, would call GitHub API.
        For now, returns cached data.
        """
        cache_file = self.cache_dir / "github_activity.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return GitHubDatabase.from_dict(data)
            except Exception:
                pass

        return GitHubDatabase(timestamp=datetime.now())

    async def fetch_org_activity(self, symbol: str) -> Optional[GitHubActivity]:
        """
        Fetch GitHub activity for a company's organizations.

        Uses GitHub API to get org and repo data.
        """
        org_names = COMPANY_ORGS.get(symbol.upper(), [])
        if not org_names:
            return None

        # In production, would call GitHub API here
        return GitHubActivity(
            symbol=symbol.upper(),
            org_names=org_names,
            snapshot_date=datetime.now(),
        )

    def update_activity(
        self,
        symbol: str,
        total_stars: int,
        total_forks: int,
        public_repos: int,
        stars_30d_ago: Optional[int] = None,
        repos_updated_30d: int = 0,
        top_repos: Optional[list[dict]] = None,
    ) -> GitHubActivity:
        """
        Update GitHub activity for a company.
        """
        cached = self._check_cache() or GitHubDatabase(timestamp=datetime.now())

        org_names = COMPANY_ORGS.get(symbol.upper(), [])

        # Calculate changes
        stars_change_30d = None
        stars_change_pct_30d = None
        if stars_30d_ago is not None:
            stars_change_30d = total_stars - stars_30d_ago
            if stars_30d_ago > 0:
                stars_change_pct_30d = stars_change_30d / stars_30d_ago

        # Determine trend
        activity_trend = "stable"
        developer_interest_signal = 0.0
        if stars_change_pct_30d is not None:
            if stars_change_pct_30d > 0.05:
                activity_trend = "growing"
                developer_interest_signal = min(1.0, stars_change_pct_30d * 5)
            elif stars_change_pct_30d < -0.05:
                activity_trend = "declining"
                developer_interest_signal = max(-1.0, stars_change_pct_30d * 5)

        # Parse top repos
        parsed_repos = []
        if top_repos:
            for repo in top_repos[:5]:
                parsed_repos.append(GitHubRepo(
                    name=repo.get("name", ""),
                    full_name=repo.get("full_name", ""),
                    description=repo.get("description", ""),
                    stars=repo.get("stars", 0),
                    forks=repo.get("forks", 0),
                    watchers=repo.get("watchers", 0),
                    open_issues=repo.get("open_issues", 0),
                    language=repo.get("language"),
                ))

        activity = GitHubActivity(
            symbol=symbol.upper(),
            org_names=org_names,
            snapshot_date=datetime.now(),
            public_repos=public_repos,
            total_stars=total_stars,
            total_forks=total_forks,
            stars_30d_ago=stars_30d_ago,
            stars_change_30d=stars_change_30d,
            stars_change_pct_30d=stars_change_pct_30d,
            repos_updated_30d=repos_updated_30d,
            top_repos=parsed_repos,
            developer_interest_signal=developer_interest_signal,
            activity_trend=activity_trend,
        )

        cached.activities[symbol.upper()] = activity
        self._update_cache(cached)

        return activity

    def get_developer_interest_signal(self, symbol: str) -> Optional[float]:
        """
        Get developer interest signal for a symbol.

        Returns -1 to +1:
        - Positive: Growing developer interest (bullish for tech companies)
        - Negative: Declining interest (bearish)
        - Zero: Stable or no data
        """
        cached = self._check_cache()
        if cached and symbol.upper() in cached.activities:
            return cached.activities[symbol.upper()].developer_interest_signal
        return None

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_github_activity(symbol: str) -> Optional[GitHubActivity]:
    """Get GitHub activity for a symbol."""
    source = GitHubSource()
    try:
        database = await source.get_database([symbol])
        return database.get_activity(symbol)
    finally:
        await source.close()


async def get_top_github_companies(n: int = 10) -> list[GitHubActivity]:
    """Get top N companies by GitHub stars."""
    source = GitHubSource()
    try:
        database = await source.get_database()
        return database.get_top_by_stars(n)
    finally:
        await source.close()


async def get_growing_github_presence() -> list[GitHubActivity]:
    """Get companies with growing GitHub presence."""
    source = GitHubSource()
    try:
        database = await source.get_database()
        return database.get_growing()
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = GitHubSource()

        # Add example data
        source.update_activity(
            symbol="MSFT",
            total_stars=450000,
            total_forks=180000,
            public_repos=5200,
            stars_30d_ago=440000,
            repos_updated_30d=450,
            top_repos=[
                {"name": "vscode", "full_name": "microsoft/vscode", "stars": 165000, "forks": 29000, "language": "TypeScript"},
                {"name": "TypeScript", "full_name": "microsoft/TypeScript", "stars": 102000, "forks": 12000, "language": "TypeScript"},
                {"name": "terminal", "full_name": "microsoft/terminal", "stars": 95000, "forks": 8500, "language": "C++"},
            ],
        )

        source.update_activity(
            symbol="GOOGL",
            total_stars=380000,
            total_forks=150000,
            public_repos=4800,
            stars_30d_ago=375000,
            repos_updated_30d=380,
            top_repos=[
                {"name": "tensorflow", "full_name": "tensorflow/tensorflow", "stars": 185000, "forks": 74000, "language": "C++"},
                {"name": "material-design-icons", "full_name": "google/material-design-icons", "stars": 51000, "forks": 10500, "language": "CSS"},
            ],
        )

        source.update_activity(
            symbol="META",
            total_stars=320000,
            total_forks=130000,
            public_repos=1800,
            stars_30d_ago=310000,
            repos_updated_30d=250,
            top_repos=[
                {"name": "react", "full_name": "facebook/react", "stars": 225000, "forks": 46000, "language": "JavaScript"},
                {"name": "pytorch", "full_name": "pytorch/pytorch", "stars": 83000, "forks": 22000, "language": "Python"},
            ],
        )

        database = await source.get_database()

        print(f"GitHub Activity Database - {database.timestamp.date()}")
        print(f"Companies tracked: {len(database.activities)}")

        print("\nTop by Stars:")
        for activity in database.get_top_by_stars(5):
            print(f"  {activity.symbol}: {activity.total_stars:,} stars, {activity.public_repos} repos")
            if activity.stars_change_pct_30d:
                print(f"    30d Growth: {activity.stars_change_pct_30d:.1%}")
            if activity.top_repos:
                print(f"    Top Repo: {activity.top_repos[0].name} ({activity.top_repos[0].stars:,} stars)")

        print("\nGrowing Presence:")
        for activity in database.get_growing():
            print(f"  {activity.symbol}: +{activity.stars_change_pct_30d:.1%} stars")

        print("\nDeveloper Interest Signals:")
        for symbol in ["MSFT", "GOOGL", "META"]:
            signal = source.get_developer_interest_signal(symbol)
            print(f"  {symbol}: {signal:.2f}" if signal else f"  {symbol}: N/A")

        await source.close()

    asyncio.run(main())
