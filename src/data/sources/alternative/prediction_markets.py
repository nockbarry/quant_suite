"""Prediction markets data source.

Tracks probability estimates from prediction markets for macro trading signals.
Prediction markets aggregate collective intelligence and often lead news.

Data Sources:
- Polymarket (polymarket.com) - Crypto-based, large liquidity
- Kalshi (kalshi.com) - CFTC-regulated, US events
- Metaculus (metaculus.com) - Community forecasting
- PredictIt (predictit.org) - Political markets (if available)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


class MarketCategory(str, Enum):
    """Category of prediction market."""
    ECONOMICS = "economics"
    FED_POLICY = "fed_policy"
    POLITICS = "politics"
    GEOPOLITICS = "geopolitics"
    CRYPTO = "crypto"
    TECH = "tech"
    EARNINGS = "earnings"
    WEATHER = "weather"
    SPORTS = "sports"
    OTHER = "other"


class MarketSource(str, Enum):
    """Prediction market data source."""
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"
    METACULUS = "metaculus"
    PREDICTIT = "predictit"
    MANIFOLD = "manifold"


# Market categories that affect specific sectors
CATEGORY_TO_SECTORS = {
    MarketCategory.FED_POLICY: ["XLF", "TLT", "GLD", "REIT"],
    MarketCategory.ECONOMICS: ["SPY", "QQQ", "IWM", "XLF"],
    MarketCategory.GEOPOLITICS: ["XLE", "OIH", "GLD", "defense"],
    MarketCategory.CRYPTO: ["COIN", "MSTR", "RIOT", "MARA"],
    MarketCategory.TECH: ["QQQ", "ARKK", "SMH"],
}

# Keywords for categorization
CATEGORY_KEYWORDS = {
    MarketCategory.FED_POLICY: ["fed", "rate", "fomc", "powell", "inflation", "cpi", "pce"],
    MarketCategory.ECONOMICS: ["recession", "gdp", "employment", "jobs", "unemployment"],
    MarketCategory.POLITICS: ["election", "president", "congress", "senate", "house"],
    MarketCategory.GEOPOLITICS: ["war", "russia", "china", "iran", "sanctions", "nato"],
    MarketCategory.CRYPTO: ["bitcoin", "ethereum", "btc", "eth", "crypto"],
    MarketCategory.TECH: ["ai", "apple", "google", "amazon", "microsoft", "meta"],
}


@dataclass
class PredictionMarket:
    """Single prediction market/question."""

    # Core fields
    id: str
    title: str
    description: str
    source: MarketSource
    category: MarketCategory
    url: str

    # Probabilities
    probability: float  # Current probability (0-1)
    probability_change_24h: float  # 24h change
    probability_change_7d: float  # 7d change

    # Market metadata
    volume: float  # Trading volume (USD)
    liquidity: float  # Available liquidity
    created_at: datetime
    end_date: datetime | None
    is_resolved: bool = False
    resolution: str | None = None

    # Derived
    affected_sectors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Compute derived fields."""
        if not self.affected_sectors:
            self.affected_sectors = CATEGORY_TO_SECTORS.get(self.category, [])

    @property
    def is_high_conviction(self) -> bool:
        """Check if market has high conviction (>80% or <20%)."""
        return self.probability >= 0.8 or self.probability <= 0.2

    @property
    def is_trending(self) -> bool:
        """Check if probability moved significantly."""
        return abs(self.probability_change_24h) >= 0.05

    @property
    def signal_strength(self) -> float:
        """
        Calculate signal strength (0-1).

        Factors:
        - Volume/liquidity (market confidence)
        - Probability change (momentum)
        - Distance from 50% (conviction)
        """
        strength = 0.5

        # Volume bonus
        if self.volume >= 1_000_000:
            strength += 0.2
        elif self.volume >= 100_000:
            strength += 0.1

        # Momentum bonus
        if abs(self.probability_change_24h) >= 0.1:
            strength += 0.15
        elif abs(self.probability_change_24h) >= 0.05:
            strength += 0.1

        # Conviction bonus
        conviction = abs(self.probability - 0.5) * 2  # 0 to 1
        strength += conviction * 0.15

        return min(1.0, strength)

    @property
    def direction(self) -> str:
        """Direction of probability movement."""
        if self.probability_change_24h > 0.02:
            return "bullish" if self.probability > 0.5 else "bearish"
        elif self.probability_change_24h < -0.02:
            return "bearish" if self.probability > 0.5 else "bullish"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source.value,
            "category": self.category.value,
            "url": self.url,
            "probability": self.probability,
            "probability_pct": f"{self.probability:.1%}",
            "probability_change_24h": self.probability_change_24h,
            "probability_change_7d": self.probability_change_7d,
            "volume": self.volume,
            "liquidity": self.liquidity,
            "created_at": self.created_at.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_resolved": self.is_resolved,
            "resolution": self.resolution,
            "affected_sectors": self.affected_sectors,
            "is_high_conviction": self.is_high_conviction,
            "is_trending": self.is_trending,
            "signal_strength": self.signal_strength,
            "direction": self.direction,
        }


@dataclass
class MacroSignal:
    """Aggregated macro signal from prediction markets."""

    category: MarketCategory
    markets: list[PredictionMarket]
    timestamp: datetime

    @property
    def avg_probability(self) -> float:
        """Average probability across markets."""
        if not self.markets:
            return 0.5
        return sum(m.probability for m in self.markets) / len(self.markets)

    @property
    def consensus_direction(self) -> str:
        """Consensus direction based on market movements."""
        if not self.markets:
            return "neutral"

        bullish = sum(1 for m in self.markets if m.direction == "bullish")
        bearish = sum(1 for m in self.markets if m.direction == "bearish")

        if bullish > bearish:
            return "bullish"
        elif bearish > bullish:
            return "bearish"
        return "mixed"

    @property
    def total_volume(self) -> float:
        """Total volume across markets."""
        return sum(m.volume for m in self.markets)

    @property
    def trending_markets(self) -> list[PredictionMarket]:
        """Markets with significant probability changes."""
        return [m for m in self.markets if m.is_trending]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "market_count": len(self.markets),
            "avg_probability": self.avg_probability,
            "consensus_direction": self.consensus_direction,
            "total_volume": self.total_volume,
            "trending_count": len(self.trending_markets),
            "timestamp": self.timestamp.isoformat(),
            "affected_sectors": CATEGORY_TO_SECTORS.get(self.category, []),
        }


def categorize_market(title: str, description: str = "") -> MarketCategory:
    """Categorize a market based on title and description."""
    text = (title + " " + description).lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category

    return MarketCategory.OTHER


class PredictionMarketsSource:
    """
    Prediction markets data source.

    Aggregates probability estimates from multiple markets.
    """

    name = "prediction_markets"

    # API endpoints
    POLYMARKET_API = "https://clob.polymarket.com"
    KALSHI_API = "https://trading-api.kalshi.com/v2"
    METACULUS_API = "https://www.metaculus.com/api2"
    MANIFOLD_API = "https://api.manifold.markets/v0"

    def __init__(
        self,
        kalshi_api_key: str | None = None,
        cache_ttl_minutes: int = 15,
    ):
        """
        Initialize prediction markets source.

        Args:
            kalshi_api_key: Kalshi API key (optional)
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.kalshi_api_key = kalshi_api_key
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "QuantSuite/1.0 (research@example.com)",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_cache(self, key: str) -> Any | None:
        """Check if cached data is valid."""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache."""
        self._cache[key] = (datetime.now(), data)

    async def fetch_markets(
        self,
        category: MarketCategory | None = None,
        min_volume: float = 10_000,
        active_only: bool = True,
    ) -> list[PredictionMarket]:
        """
        Fetch prediction markets.

        Args:
            category: Filter by category
            min_volume: Minimum volume filter
            active_only: Only return active (unresolved) markets

        Returns:
            List of PredictionMarket objects
        """
        cache_key = f"markets:{category}:{min_volume}:{active_only}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        markets = []

        # Fetch from multiple sources
        polymarket = await self._fetch_polymarket()
        markets.extend(polymarket)

        manifold = await self._fetch_manifold()
        markets.extend(manifold)

        if self.kalshi_api_key:
            kalshi = await self._fetch_kalshi()
            markets.extend(kalshi)

        # Filter
        if category:
            markets = [m for m in markets if m.category == category]

        if min_volume > 0:
            markets = [m for m in markets if m.volume >= min_volume]

        if active_only:
            markets = [m for m in markets if not m.is_resolved]

        # Sort by volume
        markets.sort(key=lambda x: x.volume, reverse=True)

        if markets:
            self._update_cache(cache_key, markets)

        return markets

    async def _fetch_polymarket(self) -> list[PredictionMarket]:
        """Fetch from Polymarket API."""
        client = await self._get_client()
        markets = []

        try:
            # Polymarket CLOB API for active markets
            url = f"{self.POLYMARKET_API}/markets"
            params = {"active": True, "limit": 100}

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data:
                try:
                    # Parse probabilities from outcomes
                    outcomes = item.get("outcomes", [])
                    probability = 0.5
                    if outcomes:
                        # Find "Yes" outcome probability
                        for outcome in outcomes:
                            if outcome.get("name", "").lower() == "yes":
                                probability = float(outcome.get("price", 0.5))
                                break

                    title = item.get("question", item.get("title", ""))
                    description = item.get("description", "")
                    category = categorize_market(title, description)

                    markets.append(PredictionMarket(
                        id=f"poly_{item.get('id', '')}",
                        title=title,
                        description=description,
                        source=MarketSource.POLYMARKET,
                        category=category,
                        url=f"https://polymarket.com/event/{item.get('slug', '')}",
                        probability=probability,
                        probability_change_24h=0.0,  # Would need historical data
                        probability_change_7d=0.0,
                        volume=float(item.get("volume", 0)),
                        liquidity=float(item.get("liquidity", 0)),
                        created_at=datetime.fromisoformat(
                            item.get("createdAt", datetime.now().isoformat()).replace("Z", "+00:00")
                        ) if item.get("createdAt") else datetime.now(),
                        end_date=datetime.fromisoformat(
                            item.get("endDate", "").replace("Z", "+00:00")
                        ) if item.get("endDate") else None,
                        is_resolved=item.get("resolved", False),
                    ))

                except Exception as e:
                    logger.debug(f"Error parsing Polymarket item: {e}")

        except Exception as e:
            logger.warning(f"Error fetching Polymarket: {e}")

        return markets

    async def _fetch_kalshi(self) -> list[PredictionMarket]:
        """Fetch from Kalshi API."""
        if not self.kalshi_api_key:
            return []

        client = await self._get_client()
        markets = []

        try:
            url = f"{self.KALSHI_API}/markets"
            headers = {"Authorization": f"Bearer {self.kalshi_api_key}"}

            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("markets", []):
                try:
                    title = item.get("title", "")
                    subtitle = item.get("subtitle", "")
                    category = categorize_market(title, subtitle)

                    # Kalshi probability from yes_price
                    probability = float(item.get("yes_price", 0.5))

                    markets.append(PredictionMarket(
                        id=f"kalshi_{item.get('ticker', '')}",
                        title=title,
                        description=subtitle,
                        source=MarketSource.KALSHI,
                        category=category,
                        url=f"https://kalshi.com/markets/{item.get('ticker', '')}",
                        probability=probability,
                        probability_change_24h=float(item.get("price_change_24h", 0)),
                        probability_change_7d=0.0,
                        volume=float(item.get("volume_24h", 0)),
                        liquidity=float(item.get("open_interest", 0)),
                        created_at=datetime.fromisoformat(
                            item.get("open_time", datetime.now().isoformat())
                        ) if item.get("open_time") else datetime.now(),
                        end_date=datetime.fromisoformat(
                            item.get("close_time", "")
                        ) if item.get("close_time") else None,
                        is_resolved=item.get("status") == "settled",
                        resolution=item.get("result"),
                    ))

                except Exception as e:
                    logger.debug(f"Error parsing Kalshi item: {e}")

        except Exception as e:
            logger.warning(f"Error fetching Kalshi: {e}")

        return markets

    async def _fetch_manifold(self) -> list[PredictionMarket]:
        """Fetch from Manifold Markets API (free, no auth)."""
        client = await self._get_client()
        markets = []

        try:
            # Manifold search endpoint for high-volume markets
            url = f"{self.MANIFOLD_API}/search-markets"
            params = {
                "term": "",
                "sort": "liquidity",
                "limit": 50,
            }

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data:
                try:
                    title = item.get("question", "")
                    description = item.get("textDescription", "")
                    category = categorize_market(title, description)

                    # Manifold probability
                    probability = float(item.get("probability", 0.5))

                    markets.append(PredictionMarket(
                        id=f"manifold_{item.get('id', '')}",
                        title=title,
                        description=description,
                        source=MarketSource.MANIFOLD,
                        category=category,
                        url=item.get("url", ""),
                        probability=probability,
                        probability_change_24h=float(item.get("prob24HoursAgo", probability)) - probability if item.get("prob24HoursAgo") else 0.0,
                        probability_change_7d=0.0,
                        volume=float(item.get("volume", 0)),
                        liquidity=float(item.get("totalLiquidity", 0)),
                        created_at=datetime.fromtimestamp(
                            item.get("createdTime", 0) / 1000
                        ) if item.get("createdTime") else datetime.now(),
                        end_date=datetime.fromtimestamp(
                            item.get("closeTime", 0) / 1000
                        ) if item.get("closeTime") else None,
                        is_resolved=item.get("isResolved", False),
                        resolution=str(item.get("resolution")) if item.get("resolution") else None,
                    ))

                except Exception as e:
                    logger.debug(f"Error parsing Manifold item: {e}")

        except Exception as e:
            logger.warning(f"Error fetching Manifold: {e}")

        return markets

    async def get_fed_markets(self) -> list[PredictionMarket]:
        """
        Get Fed policy related markets.

        Useful for rate-sensitive trades (financials, bonds, REITs).

        Returns:
            List of Fed-related markets
        """
        markets = await self.fetch_markets(category=MarketCategory.FED_POLICY)
        return markets

    async def get_recession_probability(self) -> float | None:
        """
        Get aggregate recession probability.

        Returns:
            Average recession probability or None if unavailable
        """
        markets = await self.fetch_markets(category=MarketCategory.ECONOMICS)

        recession_markets = [
            m for m in markets
            if "recession" in m.title.lower()
        ]

        if not recession_markets:
            return None

        return sum(m.probability for m in recession_markets) / len(recession_markets)

    async def get_macro_signals(self) -> list[MacroSignal]:
        """
        Get aggregated macro signals by category.

        Returns:
            List of MacroSignal objects
        """
        all_markets = await self.fetch_markets()

        # Group by category
        by_category: dict[MarketCategory, list[PredictionMarket]] = {}
        for market in all_markets:
            if market.category not in by_category:
                by_category[market.category] = []
            by_category[market.category].append(market)

        # Build signals
        signals = []
        now = datetime.now()

        for category, markets in by_category.items():
            if markets:  # Only include categories with markets
                signals.append(MacroSignal(
                    category=category,
                    markets=markets,
                    timestamp=now,
                ))

        # Sort by volume
        signals.sort(key=lambda x: x.total_volume, reverse=True)

        return signals

    async def get_trending_markets(
        self,
        min_change: float = 0.05,
    ) -> list[PredictionMarket]:
        """
        Get markets with significant probability changes.

        Large probability moves often precede news.

        Args:
            min_change: Minimum 24h probability change

        Returns:
            List of trending markets
        """
        markets = await self.fetch_markets()
        trending = [m for m in markets if abs(m.probability_change_24h) >= min_change]
        trending.sort(key=lambda x: abs(x.probability_change_24h), reverse=True)
        return trending

    def to_dataframe(
        self,
        markets: list[PredictionMarket],
    ) -> pd.DataFrame:
        """Convert markets to DataFrame."""
        if not markets:
            return pd.DataFrame()

        records = [m.to_dict() for m in markets]
        df = pd.DataFrame(records)

        return df


async def fetch_prediction_markets(
    category: MarketCategory | None = None,
    min_volume: float = 10_000,
    kalshi_api_key: str | None = None,
) -> list[PredictionMarket]:
    """
    Convenience function to fetch prediction markets.

    Args:
        category: Filter by category
        min_volume: Minimum volume
        kalshi_api_key: Kalshi API key

    Returns:
        List of PredictionMarket objects
    """
    source = PredictionMarketsSource(kalshi_api_key=kalshi_api_key)

    try:
        return await source.fetch_markets(category=category, min_volume=min_volume)
    finally:
        await source.close()


async def get_macro_signals(
    kalshi_api_key: str | None = None,
) -> list[MacroSignal]:
    """
    Get aggregated macro signals from prediction markets.

    Args:
        kalshi_api_key: Kalshi API key

    Returns:
        List of MacroSignal objects
    """
    source = PredictionMarketsSource(kalshi_api_key=kalshi_api_key)

    try:
        return await source.get_macro_signals()
    finally:
        await source.close()
