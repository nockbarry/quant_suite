"""
App Rankings

Tracks App Store and Google Play rankings for public company apps.

App rankings can indicate:
- Consumer demand trends
- Competitive positioning
- Growth/decline in user acquisition
- Market sentiment for consumer tech

Data Sources:
- App Store (scrape)
- Google Play (scrape)
- App Annie free tier
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


class AppStore(str, Enum):
    IOS = "iOS"
    ANDROID = "Android"


class AppCategory(str, Enum):
    OVERALL = "Overall"
    SOCIAL = "Social"
    FINANCE = "Finance"
    ENTERTAINMENT = "Entertainment"
    PRODUCTIVITY = "Productivity"
    SHOPPING = "Shopping"
    GAMES = "Games"
    HEALTH = "Health"
    NEWS = "News"
    MUSIC = "Music"
    PHOTO_VIDEO = "Photo & Video"


# Map apps to companies
APP_COMPANY_MAP = {
    # Meta
    "Facebook": "META",
    "Instagram": "META",
    "WhatsApp": "META",
    "Messenger": "META",
    "Threads": "META",
    # Google
    "YouTube": "GOOGL",
    "Google Maps": "GOOGL",
    "Gmail": "GOOGL",
    "Google": "GOOGL",
    "Google Photos": "GOOGL",
    "Chrome": "GOOGL",
    # Apple
    "Apple Music": "AAPL",
    "Apple TV": "AAPL",
    "Apple Podcasts": "AAPL",
    # Amazon
    "Amazon": "AMZN",
    "Amazon Prime Video": "AMZN",
    "Kindle": "AMZN",
    "Audible": "AMZN",
    # Microsoft
    "Microsoft Teams": "MSFT",
    "Outlook": "MSFT",
    "LinkedIn": "MSFT",
    "OneDrive": "MSFT",
    # Netflix
    "Netflix": "NFLX",
    # Spotify
    "Spotify": "SPOT",
    # Disney
    "Disney+": "DIS",
    "Hulu": "DIS",
    "ESPN": "DIS",
    # Snap
    "Snapchat": "SNAP",
    # Pinterest
    "Pinterest": "PINS",
    # Block (Square)
    "Cash App": "SQ",
    # PayPal
    "PayPal": "PYPL",
    "Venmo": "PYPL",
    # Uber
    "Uber": "UBER",
    "Uber Eats": "UBER",
    # DoorDash
    "DoorDash": "DASH",
    # Airbnb
    "Airbnb": "ABNB",
    # Shopify
    "Shop": "SHOP",
}


@dataclass
class AppRanking:
    """Single app ranking snapshot."""

    app_name: str
    company: str
    symbol: str
    store: str  # AppStore value
    category: str  # AppCategory value

    current_rank: int
    previous_rank: Optional[int] = None
    rank_7d_ago: Optional[int] = None
    rank_30d_ago: Optional[int] = None

    # Changes
    rank_change_1d: Optional[int] = None  # Positive = improved (moved up)
    rank_change_7d: Optional[int] = None
    rank_change_30d: Optional[int] = None

    # Rating
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    recent_reviews_sentiment: Optional[str] = None  # "positive", "neutral", "negative"

    # Metadata
    snapshot_date: datetime = field(default_factory=datetime.now)
    source: str = "manual"

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "company": self.company,
            "symbol": self.symbol,
            "store": self.store,
            "category": self.category,
            "current_rank": self.current_rank,
            "previous_rank": self.previous_rank,
            "rank_7d_ago": self.rank_7d_ago,
            "rank_30d_ago": self.rank_30d_ago,
            "rank_change_1d": self.rank_change_1d,
            "rank_change_7d": self.rank_change_7d,
            "rank_change_30d": self.rank_change_30d,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "recent_reviews_sentiment": self.recent_reviews_sentiment,
            "snapshot_date": self.snapshot_date.isoformat(),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppRanking":
        return cls(
            app_name=d["app_name"],
            company=d["company"],
            symbol=d["symbol"],
            store=d["store"],
            category=d["category"],
            current_rank=d["current_rank"],
            previous_rank=d.get("previous_rank"),
            rank_7d_ago=d.get("rank_7d_ago"),
            rank_30d_ago=d.get("rank_30d_ago"),
            rank_change_1d=d.get("rank_change_1d"),
            rank_change_7d=d.get("rank_change_7d"),
            rank_change_30d=d.get("rank_change_30d"),
            rating=d.get("rating"),
            rating_count=d.get("rating_count"),
            recent_reviews_sentiment=d.get("recent_reviews_sentiment"),
            snapshot_date=datetime.fromisoformat(d["snapshot_date"]) if "snapshot_date" in d else datetime.now(),
            source=d.get("source", "manual"),
        )

    @property
    def is_top_10(self) -> bool:
        return self.current_rank <= 10

    @property
    def is_top_50(self) -> bool:
        return self.current_rank <= 50

    @property
    def is_rising(self) -> bool:
        """Check if app is rising in rankings (rank going down = rising)."""
        if self.rank_change_7d is not None:
            return self.rank_change_7d > 0  # Positive change means improved rank
        return False

    @property
    def is_falling(self) -> bool:
        """Check if app is falling in rankings."""
        if self.rank_change_7d is not None:
            return self.rank_change_7d < -10  # Significant drop
        return False

    @property
    def momentum_signal(self) -> float:
        """
        Get momentum signal from -1 to +1.
        Based on rank changes (higher rank = better, so rank decreasing = improving).
        """
        if self.rank_change_7d is None:
            return 0.0

        # Normalize rank change
        # Rising by 10 spots = +0.5, rising by 20 = +1.0
        # Falling by 10 spots = -0.5, falling by 20 = -1.0
        signal = self.rank_change_7d / 20.0
        return max(-1.0, min(1.0, signal))


@dataclass
class CompanyAppSummary:
    """Summary of app rankings for a company."""

    symbol: str
    company: str
    apps: list[AppRanking] = field(default_factory=list)

    @property
    def top_app(self) -> Optional[AppRanking]:
        """Get the highest-ranked app."""
        if not self.apps:
            return None
        return min(self.apps, key=lambda a: a.current_rank)

    @property
    def avg_rank(self) -> float:
        """Average rank across all apps."""
        if not self.apps:
            return 0.0
        return sum(a.current_rank for a in self.apps) / len(self.apps)

    @property
    def avg_momentum(self) -> float:
        """Average momentum across all apps."""
        if not self.apps:
            return 0.0
        return sum(a.momentum_signal for a in self.apps) / len(self.apps)

    @property
    def rising_apps(self) -> list[AppRanking]:
        return [a for a in self.apps if a.is_rising]

    @property
    def falling_apps(self) -> list[AppRanking]:
        return [a for a in self.apps if a.is_falling]


@dataclass
class AppRankingDatabase:
    """Collection of app rankings."""

    timestamp: datetime
    rankings: list[AppRanking] = field(default_factory=list)

    def get_for_symbol(self, symbol: str) -> list[AppRanking]:
        return [r for r in self.rankings if r.symbol.upper() == symbol.upper()]

    def get_company_summary(self, symbol: str) -> CompanyAppSummary:
        apps = self.get_for_symbol(symbol)
        if not apps:
            return CompanyAppSummary(symbol=symbol.upper(), company=symbol)
        return CompanyAppSummary(
            symbol=symbol.upper(),
            company=apps[0].company,
            apps=apps,
        )

    def get_top_apps(self, n: int = 20, category: str = "Overall") -> list[AppRanking]:
        """Get top N apps in a category."""
        category_apps = [r for r in self.rankings if r.category == category]
        sorted_apps = sorted(category_apps, key=lambda r: r.current_rank)
        return sorted_apps[:n]

    def get_biggest_movers(self, n: int = 10) -> list[AppRanking]:
        """Get apps with biggest rank changes (up or down)."""
        with_changes = [r for r in self.rankings if r.rank_change_7d is not None]
        sorted_apps = sorted(with_changes, key=lambda r: abs(r.rank_change_7d or 0), reverse=True)
        return sorted_apps[:n]

    def get_rising(self) -> list[AppRanking]:
        """Get apps that are rising in rankings."""
        return [r for r in self.rankings if r.is_rising]

    def get_falling(self) -> list[AppRanking]:
        """Get apps that are falling in rankings."""
        return [r for r in self.rankings if r.is_falling]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "rankings": [r.to_dict() for r in self.rankings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppRankingDatabase":
        rankings = [AppRanking.from_dict(r) for r in d.get("rankings", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            rankings=rankings,
        )


class AppRankingSource:
    """
    Track app store rankings.

    Data sources:
    - App Store (scrape top charts)
    - Google Play (scrape top charts)
    - Manual entry from App Annie/SensorTower
    """

    name = "app_rankings"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "apps")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[tuple[datetime, AppRankingDatabase]] = None

    def _check_cache(self) -> Optional[AppRankingDatabase]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, database = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return database

        cache_file = self.cache_dir / "app_rankings.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                database = AppRankingDatabase.from_dict(data)
                if datetime.now() - database.timestamp < self.cache_ttl:
                    self._cache = (database.timestamp, database)
                    return database
            except Exception as e:
                logger.warning(f"Failed to load app ranking cache: {e}")

        return None

    def _update_cache(self, database: AppRankingDatabase) -> None:
        """Update cache."""
        self._cache = (datetime.now(), database)

        cache_file = self.cache_dir / "app_rankings.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(database.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save app ranking cache: {e}")

    async def get_database(self, force_refresh: bool = False) -> AppRankingDatabase:
        """Get app ranking database."""
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        try:
            database = await self._fetch_database()
            self._update_cache(database)
            return database
        except Exception as e:
            logger.error(f"Failed to fetch app rankings: {e}")
            return AppRankingDatabase(timestamp=datetime.now())

    async def _fetch_database(self) -> AppRankingDatabase:
        """
        Fetch app rankings.

        In production, would scrape app stores.
        For now, returns cached data.
        """
        cache_file = self.cache_dir / "app_rankings.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return AppRankingDatabase.from_dict(data)
            except Exception:
                pass

        return AppRankingDatabase(timestamp=datetime.now())

    def update_ranking(
        self,
        app_name: str,
        current_rank: int,
        store: str = AppStore.IOS.value,
        category: str = AppCategory.OVERALL.value,
        previous_rank: Optional[int] = None,
        rank_7d_ago: Optional[int] = None,
        rating: Optional[float] = None,
    ) -> AppRanking:
        """
        Update app ranking.
        """
        # Look up company from app name
        symbol = APP_COMPANY_MAP.get(app_name, "UNKNOWN")
        company = app_name

        # Calculate changes
        rank_change_1d = None
        if previous_rank is not None:
            rank_change_1d = previous_rank - current_rank  # Positive = improved

        rank_change_7d = None
        if rank_7d_ago is not None:
            rank_change_7d = rank_7d_ago - current_rank

        ranking = AppRanking(
            app_name=app_name,
            company=company,
            symbol=symbol,
            store=store,
            category=category,
            current_rank=current_rank,
            previous_rank=previous_rank,
            rank_7d_ago=rank_7d_ago,
            rank_change_1d=rank_change_1d,
            rank_change_7d=rank_change_7d,
            rating=rating,
            source="manual",
        )

        # Update database
        cached = self._check_cache() or AppRankingDatabase(timestamp=datetime.now())

        # Remove existing ranking for same app/store/category
        cached.rankings = [
            r for r in cached.rankings
            if not (r.app_name == app_name and r.store == store and r.category == category)
        ]
        cached.rankings.append(ranking)

        self._update_cache(cached)
        return ranking

    def get_momentum_signal(self, symbol: str) -> Optional[float]:
        """
        Get app momentum signal for a symbol.

        Returns -1 to +1:
        - Positive: Apps rising in rankings (bullish for consumer engagement)
        - Negative: Apps falling in rankings (bearish)
        - Zero: No data or stable
        """
        cached = self._check_cache()
        if not cached:
            return None

        summary = cached.get_company_summary(symbol)
        if not summary.apps:
            return None

        return summary.avg_momentum

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_app_rankings(symbol: str) -> list[AppRanking]:
    """Get app rankings for a symbol."""
    source = AppRankingSource()
    try:
        database = await source.get_database()
        return database.get_for_symbol(symbol)
    finally:
        await source.close()


async def get_top_apps(n: int = 20) -> list[AppRanking]:
    """Get top N apps overall."""
    source = AppRankingSource()
    try:
        database = await source.get_database()
        return database.get_top_apps(n)
    finally:
        await source.close()


async def get_rising_apps() -> list[AppRanking]:
    """Get apps rising in rankings."""
    source = AppRankingSource()
    try:
        database = await source.get_database()
        return database.get_rising()
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = AppRankingSource()

        # Add example data
        source.update_ranking("Instagram", 1, store=AppStore.IOS.value, previous_rank=1, rank_7d_ago=2, rating=4.7)
        source.update_ranking("TikTok", 2, store=AppStore.IOS.value, previous_rank=3, rank_7d_ago=5, rating=4.8)
        source.update_ranking("YouTube", 3, store=AppStore.IOS.value, previous_rank=2, rank_7d_ago=3, rating=4.7)
        source.update_ranking("Facebook", 5, store=AppStore.IOS.value, previous_rank=4, rank_7d_ago=4, rating=4.0)
        source.update_ranking("Snapchat", 8, store=AppStore.IOS.value, previous_rank=6, rank_7d_ago=6, rating=4.2)
        source.update_ranking("Netflix", 15, store=AppStore.IOS.value, previous_rank=12, rank_7d_ago=10, rating=4.3)
        source.update_ranking("Cash App", 4, store=AppStore.IOS.value, previous_rank=5, rank_7d_ago=8, rating=4.8)

        database = await source.get_database()

        print(f"App Rankings - {database.timestamp.date()}")
        print(f"Total apps tracked: {len(database.rankings)}")

        print("\nTop 10 Apps:")
        for r in database.get_top_apps(10):
            change = ""
            if r.rank_change_7d:
                change = f" ({r.rank_change_7d:+d} 7d)"
            print(f"  #{r.current_rank} {r.app_name} ({r.symbol}){change}")

        print("\nBiggest Movers:")
        for r in database.get_biggest_movers(5):
            print(f"  {r.app_name}: {r.rank_change_7d:+d} spots (now #{r.current_rank})")

        print("\nCompany Summary - META:")
        summary = database.get_company_summary("META")
        print(f"  Apps: {len(summary.apps)}")
        print(f"  Top App: {summary.top_app.app_name if summary.top_app else 'N/A'}")
        print(f"  Avg Momentum: {summary.avg_momentum:.2f}")

        # Check signal
        signal = source.get_momentum_signal("META")
        print(f"\n  Momentum Signal: {signal:.2f}" if signal else "\n  Momentum Signal: N/A")

        await source.close()

    asyncio.run(main())
