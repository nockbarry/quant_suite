"""News data source for financial news and headlines.

Fetches news from multiple sources for sentiment analysis and NLP strategies.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Represents a single news article."""

    title: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None
    content: str | None = None
    symbols: list[Symbol] = field(default_factory=list)
    sentiment: float | None = None  # -1 to 1 if pre-computed
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def article_id(self) -> str:
        """Generate unique ID for article."""
        return hashlib.md5(f"{self.url}{self.title}".encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "summary": self.summary,
            "content": self.content,
            "symbols": self.symbols,
            "sentiment": self.sentiment,
            **self.metadata,
        }


@dataclass
class NewsSourceConfig:
    """Configuration for a news source."""

    name: str
    base_url: str
    api_key: str | None = None
    rate_limit: float = 1.0  # requests per second
    enabled: bool = True


class NewsDataSource:
    """
    Aggregated news data source.

    Fetches news from multiple providers and aggregates them.
    Supports:
    - Alpha Vantage News API
    - Finnhub News
    - NewsAPI (general news)
    - RSS feeds
    """

    name = "news_aggregator"

    def __init__(
        self,
        alpha_vantage_key: str | None = None,
        finnhub_key: str | None = None,
        newsapi_key: str | None = None,
        cache_ttl_minutes: int = 15,
    ):
        """
        Initialize news data source.

        Args:
            alpha_vantage_key: Alpha Vantage API key
            finnhub_key: Finnhub API key
            newsapi_key: NewsAPI key
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.alpha_vantage_key = alpha_vantage_key
        self.finnhub_key = finnhub_key
        self.newsapi_key = newsapi_key
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        self._cache: dict[str, tuple[datetime, list[NewsArticle]]] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _cache_key(self, source: str, symbol: str | None, query: str | None) -> str:
        """Generate cache key."""
        return f"{source}:{symbol or 'all'}:{query or 'none'}"

    def _check_cache(self, key: str) -> list[NewsArticle] | None:
        """Check if cached data is still valid."""
        if key in self._cache:
            timestamp, articles = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                return articles
        return None

    def _update_cache(self, key: str, articles: list[NewsArticle]) -> None:
        """Update cache with new data."""
        self._cache[key] = (datetime.now(), articles)

    async def fetch_news(
        self,
        symbol: Symbol | None = None,
        query: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
        sources: list[str] | None = None,
    ) -> list[NewsArticle]:
        """
        Fetch news articles.

        Args:
            symbol: Filter by stock symbol
            query: Search query
            start: Start datetime
            end: End datetime
            limit: Maximum articles to return
            sources: Specific sources to use

        Returns:
            List of NewsArticle objects
        """
        articles = []

        # Determine which sources to use
        use_sources = sources or ["alpha_vantage", "finnhub", "newsapi"]

        # Fetch from each source
        tasks = []

        if "alpha_vantage" in use_sources and self.alpha_vantage_key:
            tasks.append(self._fetch_alpha_vantage(symbol, query, limit))

        if "finnhub" in use_sources and self.finnhub_key:
            tasks.append(self._fetch_finnhub(symbol, start, end))

        if "newsapi" in use_sources and self.newsapi_key:
            tasks.append(self._fetch_newsapi(query or symbol, start, end, limit))

        # Gather results
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    articles.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"News fetch error: {result}")

        # Filter by date range
        if start:
            articles = [a for a in articles if a.published_at >= start]
        if end:
            articles = [a for a in articles if a.published_at <= end]

        # Sort by date (newest first)
        articles.sort(key=lambda x: x.published_at, reverse=True)

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        return unique_articles[:limit]

    async def _fetch_alpha_vantage(
        self,
        symbol: Symbol | None,
        query: str | None,
        limit: int,
    ) -> list[NewsArticle]:
        """Fetch from Alpha Vantage News API."""
        if not self.alpha_vantage_key:
            return []

        cache_key = self._cache_key("alpha_vantage", symbol, query)
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        client = await self._get_client()
        articles = []

        try:
            params = {
                "function": "NEWS_SENTIMENT",
                "apikey": self.alpha_vantage_key,
                "limit": min(limit, 200),
            }

            if symbol:
                params["tickers"] = symbol

            if query:
                params["topics"] = query

            response = await client.get(
                "https://www.alphavantage.co/query",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("feed", []):
                try:
                    published = datetime.strptime(
                        item["time_published"],
                        "%Y%m%dT%H%M%S",
                    )

                    # Extract sentiment
                    sentiment = None
                    if "overall_sentiment_score" in item:
                        sentiment = float(item["overall_sentiment_score"])

                    # Extract tickers
                    tickers = []
                    for ticker_data in item.get("ticker_sentiment", []):
                        tickers.append(ticker_data.get("ticker", ""))

                    articles.append(NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", "Alpha Vantage"),
                        published_at=published,
                        summary=item.get("summary", ""),
                        symbols=tickers,
                        sentiment=sentiment,
                        metadata={
                            "relevance_score": item.get("overall_sentiment_label"),
                            "banner_image": item.get("banner_image"),
                        },
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Alpha Vantage article: {e}")

            self._update_cache(cache_key, articles)

        except Exception as e:
            logger.error(f"Alpha Vantage news fetch error: {e}")

        return articles

    async def _fetch_finnhub(
        self,
        symbol: Symbol | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[NewsArticle]:
        """Fetch from Finnhub News API."""
        if not self.finnhub_key:
            return []

        cache_key = self._cache_key("finnhub", symbol, None)
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        client = await self._get_client()
        articles = []

        try:
            # Finnhub requires start/end dates
            end = end or datetime.now()
            start = start or (end - timedelta(days=7))

            params = {
                "token": self.finnhub_key,
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            }

            if symbol:
                # Company news endpoint
                url = f"https://finnhub.io/api/v1/company-news"
                params["symbol"] = symbol
            else:
                # General news endpoint
                url = "https://finnhub.io/api/v1/news"
                params["category"] = "general"

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            for item in data:
                try:
                    published = datetime.fromtimestamp(item.get("datetime", 0))

                    articles.append(NewsArticle(
                        title=item.get("headline", ""),
                        url=item.get("url", ""),
                        source=item.get("source", "Finnhub"),
                        published_at=published,
                        summary=item.get("summary", ""),
                        symbols=[item.get("related", "")] if item.get("related") else [],
                        metadata={
                            "category": item.get("category"),
                            "image": item.get("image"),
                        },
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Finnhub article: {e}")

            self._update_cache(cache_key, articles)

        except Exception as e:
            logger.error(f"Finnhub news fetch error: {e}")

        return articles

    async def _fetch_newsapi(
        self,
        query: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[NewsArticle]:
        """Fetch from NewsAPI."""
        if not self.newsapi_key:
            return []

        cache_key = self._cache_key("newsapi", None, query)
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        client = await self._get_client()
        articles = []

        try:
            end = end or datetime.now()
            start = start or (end - timedelta(days=7))

            params = {
                "apiKey": self.newsapi_key,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": min(limit, 100),
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            }

            # Use everything endpoint for queries, top-headlines for general
            if query:
                url = "https://newsapi.org/v2/everything"
                params["q"] = query
                params["domains"] = "bloomberg.com,cnbc.com,reuters.com,wsj.com,ft.com"
            else:
                url = "https://newsapi.org/v2/top-headlines"
                params["category"] = "business"
                params["country"] = "us"

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            for item in data.get("articles", []):
                try:
                    published_str = item.get("publishedAt", "")
                    if published_str:
                        published = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    else:
                        published = datetime.now()

                    articles.append(NewsArticle(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", {}).get("name", "NewsAPI"),
                        published_at=published,
                        summary=item.get("description", ""),
                        content=item.get("content", ""),
                        metadata={
                            "author": item.get("author"),
                            "image": item.get("urlToImage"),
                        },
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing NewsAPI article: {e}")

            self._update_cache(cache_key, articles)

        except Exception as e:
            logger.error(f"NewsAPI fetch error: {e}")

        return articles

    async def fetch_for_symbols(
        self,
        symbols: list[Symbol],
        start: datetime | None = None,
        end: datetime | None = None,
        limit_per_symbol: int = 20,
    ) -> dict[Symbol, list[NewsArticle]]:
        """
        Fetch news for multiple symbols.

        Args:
            symbols: List of symbols
            start: Start datetime
            end: End datetime
            limit_per_symbol: Max articles per symbol

        Returns:
            Dict mapping symbols to their news articles
        """
        results = {}

        # Fetch in parallel with rate limiting
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests

        async def fetch_with_semaphore(symbol: Symbol) -> tuple[Symbol, list[NewsArticle]]:
            async with semaphore:
                articles = await self.fetch_news(
                    symbol=symbol,
                    start=start,
                    end=end,
                    limit=limit_per_symbol,
                )
                await asyncio.sleep(0.5)  # Rate limiting
                return symbol, articles

        tasks = [fetch_with_semaphore(s) for s in symbols]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in task_results:
            if isinstance(result, tuple):
                symbol, articles = result
                results[symbol] = articles
            elif isinstance(result, Exception):
                logger.warning(f"Error fetching news: {result}")

        return results

    def to_dataframe(self, articles: list[NewsArticle]) -> pd.DataFrame:
        """
        Convert articles to DataFrame.

        Args:
            articles: List of NewsArticle objects

        Returns:
            DataFrame with article data
        """
        if not articles:
            return pd.DataFrame()

        records = [article.to_dict() for article in articles]
        df = pd.DataFrame(records)

        if "published_at" in df.columns:
            df["published_at"] = pd.to_datetime(df["published_at"])
            df = df.set_index("published_at").sort_index()

        return df


class RSSNewsSource:
    """
    RSS feed news source for financial news.

    Supports common financial news RSS feeds.
    """

    DEFAULT_FEEDS = {
        "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
        "cnbc": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
        "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
    }

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        include_defaults: bool = True,
    ):
        """
        Initialize RSS news source.

        Args:
            feeds: Dict of feed_name -> feed_url
            include_defaults: Include default financial feeds
        """
        self.feeds = {}

        if include_defaults:
            self.feeds.update(self.DEFAULT_FEEDS)

        if feeds:
            self.feeds.update(feeds)

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_feed(
        self,
        feed_name: str,
        limit: int = 50,
    ) -> list[NewsArticle]:
        """
        Fetch articles from a specific RSS feed.

        Args:
            feed_name: Name of the feed
            limit: Max articles to return

        Returns:
            List of NewsArticle objects
        """
        if feed_name not in self.feeds:
            logger.warning(f"Unknown feed: {feed_name}")
            return []

        url = self.feeds[feed_name]
        client = await self._get_client()
        articles = []

        try:
            response = await client.get(url)
            response.raise_for_status()
            content = response.text

            # Simple RSS parsing without external library
            articles = self._parse_rss(content, feed_name)[:limit]

        except Exception as e:
            logger.error(f"RSS fetch error for {feed_name}: {e}")

        return articles

    def _parse_rss(self, content: str, source: str) -> list[NewsArticle]:
        """Parse RSS XML content."""
        articles = []

        # Simple regex-based parsing (works for most RSS feeds)
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        title_pattern = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>")
        link_pattern = re.compile(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>")
        desc_pattern = re.compile(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", re.DOTALL)
        date_pattern = re.compile(r"<pubDate>(.*?)</pubDate>")

        for item_match in item_pattern.finditer(content):
            item_content = item_match.group(1)

            title_match = title_pattern.search(item_content)
            link_match = link_pattern.search(item_content)
            desc_match = desc_pattern.search(item_content)
            date_match = date_pattern.search(item_content)

            title = title_match.group(1).strip() if title_match else ""
            url = link_match.group(1).strip() if link_match else ""
            summary = desc_match.group(1).strip() if desc_match else ""
            date_str = date_match.group(1).strip() if date_match else ""

            # Parse date
            published = datetime.now()
            if date_str:
                try:
                    # Try common RSS date formats
                    for fmt in [
                        "%a, %d %b %Y %H:%M:%S %z",
                        "%a, %d %b %Y %H:%M:%S %Z",
                        "%Y-%m-%dT%H:%M:%S%z",
                    ]:
                        try:
                            published = datetime.strptime(date_str, fmt)
                            if published.tzinfo:
                                published = published.replace(tzinfo=None)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            # Clean HTML from summary
            summary = re.sub(r"<[^>]+>", "", summary)

            if title and url:
                articles.append(NewsArticle(
                    title=title,
                    url=url,
                    source=source,
                    published_at=published,
                    summary=summary[:500] if summary else None,
                ))

        return articles

    async def fetch_all_feeds(
        self,
        limit_per_feed: int = 20,
    ) -> list[NewsArticle]:
        """
        Fetch from all configured feeds.

        Args:
            limit_per_feed: Max articles per feed

        Returns:
            Combined list of articles from all feeds
        """
        tasks = [
            self.fetch_feed(name, limit_per_feed)
            for name in self.feeds
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"RSS feed error: {result}")

        # Sort by date and deduplicate
        all_articles.sort(key=lambda x: x.published_at, reverse=True)

        seen_urls = set()
        unique = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique.append(article)

        return unique


def extract_symbols_from_text(text: str, known_symbols: list[str] | None = None) -> list[str]:
    """
    Extract stock symbols from text.

    Args:
        text: Text to search
        known_symbols: List of valid symbols to match against

    Returns:
        List of found symbols
    """
    # Pattern for stock symbols (1-5 uppercase letters)
    pattern = r"\b([A-Z]{1,5})\b"
    matches = re.findall(pattern, text)

    # Common words to exclude
    exclude = {
        "A", "I", "CEO", "CFO", "IPO", "ETF", "NYSE", "NASDAQ",
        "SEC", "FDA", "US", "UK", "EU", "AI", "IT", "TV", "PC",
        "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
        "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS",
    }

    symbols = []
    for match in matches:
        if match not in exclude:
            if known_symbols is None or match in known_symbols:
                symbols.append(match)

    return list(set(symbols))
