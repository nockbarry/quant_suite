"""News and Events Historical Archiver.

Collects and archives news and market events from free sources:
1. RSS feeds (Yahoo Finance, Seeking Alpha, Reuters)
2. Economic calendar events (FRED API)
3. Earnings events (yfinance)
4. Finviz news scraping

This module handles:
- Daily collection and archival of news
- Economic release tracking with actual vs expected
- Earnings calendar maintenance
- Event-return correlation analysis

Usage:
    from src.data.sources.alternative.news_archive import NewsArchiver

    archiver = NewsArchiver()

    # Collect today's news
    await archiver.collect_daily()

    # Get historical events
    events = archiver.load_events(event_type="earnings", days=90)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Single news item."""

    headline: str
    source: str
    url: str
    published: datetime
    symbols: list[str] = field(default_factory=list)
    summary: str = ""
    sentiment: float = 0.0  # -1 to 1
    category: str = ""  # earnings, macro, company, sector

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "source": self.source,
            "url": self.url,
            "published": self.published.isoformat(),
            "symbols": self.symbols,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "category": self.category,
        }


@dataclass
class EconomicEvent:
    """Economic calendar event with actual vs expected."""

    event_id: str
    name: str
    date: datetime
    category: str  # employment, inflation, growth, housing, fed
    importance: str  # high, medium, low

    prior: float | None = None
    consensus: float | None = None
    actual: float | None = None
    surprise: float | None = None  # actual - consensus

    affected_sectors: list[str] = field(default_factory=list)
    market_reaction: dict[str, float] = field(default_factory=dict)  # symbol: return

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "date": self.date.isoformat(),
            "category": self.category,
            "importance": self.importance,
            "prior": self.prior,
            "consensus": self.consensus,
            "actual": self.actual,
            "surprise": self.surprise,
            "affected_sectors": self.affected_sectors,
            "market_reaction": self.market_reaction,
        }


# RSS feed sources
RSS_SOURCES = {
    "yahoo_finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,MSFT,GOOGL,AMZN,META&region=US&lang=en-US",
    "seeking_alpha_market": "https://seekingalpha.com/market_currents.xml",
    "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
}

# Economic events to track
ECONOMIC_EVENTS = {
    "NFP": {
        "name": "Non-Farm Payrolls",
        "category": "employment",
        "importance": "high",
        "frequency": "monthly",
        "day_pattern": "first_friday",
        "affected_sectors": ["financials", "consumer_discretionary"],
        "fred_series": "PAYEMS",
    },
    "CPI": {
        "name": "Consumer Price Index",
        "category": "inflation",
        "importance": "high",
        "frequency": "monthly",
        "affected_sectors": ["utilities", "consumer_staples", "reits"],
        "fred_series": "CPIAUCSL",
    },
    "FOMC": {
        "name": "Federal Reserve Interest Rate Decision",
        "category": "fed",
        "importance": "high",
        "frequency": "8x_yearly",
        "affected_sectors": ["financials", "utilities", "reits", "technology"],
    },
    "GDP": {
        "name": "Gross Domestic Product",
        "category": "growth",
        "importance": "high",
        "frequency": "quarterly",
        "affected_sectors": ["all"],
        "fred_series": "GDP",
    },
    "RETAIL_SALES": {
        "name": "Retail Sales",
        "category": "growth",
        "importance": "medium",
        "frequency": "monthly",
        "affected_sectors": ["consumer_discretionary", "consumer_staples"],
        "fred_series": "RSAFS",
    },
    "JOBLESS_CLAIMS": {
        "name": "Initial Jobless Claims",
        "category": "employment",
        "importance": "medium",
        "frequency": "weekly",
        "affected_sectors": ["consumer_discretionary"],
        "fred_series": "ICSA",
    },
    "ISM_MFG": {
        "name": "ISM Manufacturing PMI",
        "category": "growth",
        "importance": "medium",
        "frequency": "monthly",
        "affected_sectors": ["industrials", "materials"],
        "fred_series": "MANEMP",
    },
    "HOUSING_STARTS": {
        "name": "Housing Starts",
        "category": "housing",
        "importance": "medium",
        "frequency": "monthly",
        "affected_sectors": ["homebuilders", "materials", "financials"],
        "fred_series": "HOUST",
    },
}

# Sentiment keywords
POSITIVE_KEYWORDS = [
    "surge", "soar", "rally", "jump", "beat", "exceed", "upgrade",
    "bullish", "record", "growth", "profit", "gain", "rise", "strong",
]
NEGATIVE_KEYWORDS = [
    "plunge", "crash", "tumble", "fall", "miss", "cut", "downgrade",
    "bearish", "loss", "decline", "weak", "warning", "concern", "fear",
]


def extract_sentiment(text: str) -> float:
    """Extract simple sentiment from text."""
    text_lower = text.lower()
    positive = sum(1 for word in POSITIVE_KEYWORDS if word in text_lower)
    negative = sum(1 for word in NEGATIVE_KEYWORDS if word in text_lower)

    if positive + negative == 0:
        return 0.0

    return (positive - negative) / (positive + negative)


def extract_symbols(text: str, known_symbols: set[str] | None = None) -> list[str]:
    """Extract stock symbols from text."""
    import re

    # Common false positives to exclude
    FALSE_POSITIVES = {
        "I", "A", "THE", "CEO", "IPO", "ETF", "GDP", "CPI", "NFP", "PMI",
        "USD", "EUR", "GBP", "JPY", "AM", "PM", "IT", "AT", "OR", "AN",
        "BE", "BY", "DO", "GO", "IF", "IN", "IS", "NO", "OF", "ON", "SO",
        "TO", "UP", "US", "WE", "AI", "UK", "EU", "MA", "MD", "ME", "MI",
        "MO", "MS", "MT", "NC", "NE", "NH", "NJ", "NM", "NV", "NY", "OH",
        "OK", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA",
        "WI", "WV", "WY", "DC", "PR", "VI", "ALL", "NEW", "NOW", "OLD",
        "ONE", "TWO", "FOR", "ARE", "BUT", "NOT", "YOU", "CAN", "HAD",
        "HER", "HIS", "HOW", "ITS", "LET", "MAY", "OUR", "OUT", "OWN",
        "SAY", "SHE", "TOO", "USE", "WAY", "WHO", "BOY", "DID", "GET",
        "HAS", "HIM", "MAN", "OLD", "SEE", "WAY", "RSI", "SMA", "EMA",
    }

    # Find potential tickers (1-5 uppercase letters)
    potential = re.findall(r'\b([A-Z]{1,5})\b', text)

    symbols = []
    for ticker in potential:
        if ticker not in FALSE_POSITIVES:
            if known_symbols is None or ticker in known_symbols:
                symbols.append(ticker)

    return list(set(symbols))


class NewsArchiver:
    """Archive and manage news and events data."""

    def __init__(self, archive_dir: Path | None = None):
        """Initialize archiver."""
        self.archive_dir = archive_dir or paths.base / "news_archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.news_dir = self.archive_dir / "news"
        self.events_dir = self.archive_dir / "events"
        self.earnings_dir = self.archive_dir / "earnings"

        for d in [self.news_dir, self.events_dir, self.earnings_dir]:
            d.mkdir(exist_ok=True)

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "QuantSuite/1.0 News Research",
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_rss_news(self) -> list[NewsItem]:
        """Fetch news from RSS feeds."""
        client = await self._get_client()
        all_news = []

        for source_name, url in RSS_SOURCES.items():
            try:
                resp = await client.get(url)
                resp.raise_for_status()

                # Parse RSS XML
                root = ElementTree.fromstring(resp.content)

                for item in root.findall(".//item"):
                    try:
                        title = item.find("title")
                        link = item.find("link")
                        description = item.find("description")
                        pub_date = item.find("pubDate")

                        if title is None:
                            continue

                        headline = title.text or ""
                        url_str = link.text if link is not None else ""
                        summary = description.text if description is not None else ""

                        # Parse date
                        published = datetime.now()
                        if pub_date is not None and pub_date.text:
                            try:
                                # Try common RSS date formats
                                for fmt in [
                                    "%a, %d %b %Y %H:%M:%S %z",
                                    "%a, %d %b %Y %H:%M:%S %Z",
                                    "%Y-%m-%dT%H:%M:%S%z",
                                ]:
                                    try:
                                        published = datetime.strptime(pub_date.text.strip(), fmt)
                                        break
                                    except ValueError:
                                        continue
                            except Exception:
                                pass

                        # Extract symbols and sentiment
                        full_text = f"{headline} {summary}"
                        symbols = extract_symbols(full_text)
                        sentiment = extract_sentiment(full_text)

                        news_item = NewsItem(
                            headline=headline,
                            source=source_name,
                            url=url_str,
                            published=published.replace(tzinfo=None) if hasattr(published, 'replace') else published,
                            symbols=symbols,
                            summary=summary[:500] if summary else "",
                            sentiment=sentiment,
                        )
                        all_news.append(news_item)

                    except Exception as e:
                        logger.debug(f"Error parsing RSS item: {e}")

            except Exception as e:
                logger.warning(f"Error fetching RSS from {source_name}: {e}")

        return all_news

    async def collect_daily(self) -> dict[str, Any]:
        """Collect and archive today's news."""
        logger.info("Collecting daily news...")

        # Fetch RSS news
        news_items = await self.fetch_rss_news()
        logger.info(f"Fetched {len(news_items)} news items from RSS")

        if not news_items:
            return {"status": "no_news", "message": "No news items found"}

        # Save to dated file
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.news_dir / f"news_{date_str}.json"

        # Load existing if present
        existing = []
        if daily_file.exists():
            with open(daily_file) as f:
                existing = json.load(f)

        # Merge and deduplicate by URL
        existing_urls = {item.get("url") for item in existing}
        new_items = [n.to_dict() for n in news_items if n.url not in existing_urls]

        all_items = existing + new_items

        with open(daily_file, "w") as f:
            json.dump(all_items, f, indent=2)

        logger.info(f"Saved {len(new_items)} new items to {daily_file}")

        return {
            "status": "success",
            "new_items": len(new_items),
            "total_items": len(all_items),
            "path": str(daily_file),
        }

    def load_news(self, days: int = 30) -> pd.DataFrame:
        """Load archived news from the last N days."""
        all_news = []
        cutoff = datetime.now() - timedelta(days=days)

        for file in sorted(self.news_dir.glob("news_*.json"), reverse=True):
            try:
                # Parse date from filename
                date_str = file.stem.replace("news_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")

                if file_date < cutoff:
                    continue

                with open(file) as f:
                    items = json.load(f)
                    all_news.extend(items)

            except Exception as e:
                logger.debug(f"Error loading {file}: {e}")

        return pd.DataFrame(all_news)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of archived data."""
        news_files = list(self.news_dir.glob("news_*.json"))
        earnings_files = list(self.earnings_dir.glob("*.parquet"))
        events_files = list(self.events_dir.glob("*.json"))

        total_news = 0
        for f in news_files:
            try:
                with open(f) as fp:
                    total_news += len(json.load(fp))
            except Exception:
                pass

        return {
            "news_files": len(news_files),
            "total_news_items": total_news,
            "earnings_files": len(earnings_files),
            "events_files": len(events_files),
            "archive_dir": str(self.archive_dir),
        }


async def run_collection():
    """Run news collection."""
    archiver = NewsArchiver()
    try:
        result = await archiver.collect_daily()
        print("\nCollection Results:")
        print(json.dumps(result, indent=2))

        print("\nArchive Summary:")
        summary = archiver.get_summary()
        print(json.dumps(summary, indent=2))
    finally:
        await archiver.close()


if __name__ == "__main__":
    asyncio.run(run_collection())
