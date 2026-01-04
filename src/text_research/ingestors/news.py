"""
News Ingestor: Ingest news articles into TextCorpus.

Supports multiple news sources:
- RSS feeds
- Alpha Vantage news API
- Custom news sources

Each article is converted to a TextDocument with proper point-in-time timestamp.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from ..corpus import TextCorpus, TextDocument

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class NewsIngestor:
    """
    Ingest news articles from various sources.

    Supports:
    - RSS feeds (free, wide coverage)
    - Alpha Vantage News API (requires API key)
    - Custom sources via add_custom_source()

    Example Usage:
        ingestor = NewsIngestor(corpus)

        # Ingest from RSS feeds
        count = ingestor.ingest_rss_feeds(symbols=["AAPL", "GOOGL"])

        # Ingest from Alpha Vantage
        count = ingestor.ingest_alpha_vantage(
            symbols=["AAPL"],
            api_key="your_key"
        )
    """

    # Default RSS feeds for financial news
    DEFAULT_RSS_FEEDS = {
        "yahoo_finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
        "seeking_alpha": "https://seekingalpha.com/api/sa/combined/{symbol}.xml",
        "nasdaq": "https://www.nasdaq.com/feed/rssoutbound?symbol={symbol}",
    }

    # Sector mappings for tagging
    SECTOR_MAP = {
        "AAPL": "technology",
        "MSFT": "technology",
        "GOOGL": "technology",
        "AMZN": "technology",
        "META": "technology",
        "NVDA": "semiconductors",
        "AMD": "semiconductors",
        "INTC": "semiconductors",
        "QCOM": "semiconductors",
        "MU": "semiconductors",
        "AVGO": "semiconductors",
        "MRVL": "semiconductors",
        "JPM": "financials",
        "BAC": "financials",
        "GS": "financials",
        "WFC": "financials",
        "XOM": "energy",
        "CVX": "energy",
        "COP": "energy",
    }

    def __init__(self, corpus: TextCorpus):
        """
        Initialize NewsIngestor.

        Args:
            corpus: TextCorpus to add documents to
        """
        self.corpus = corpus
        self._custom_sources: dict[str, Any] = {}

    def ingest_rss_feeds(
        self,
        symbols: list[str],
        feeds: dict[str, str] | None = None,
        max_articles_per_symbol: int = 50,
    ) -> int:
        """
        Ingest articles from RSS feeds.

        Args:
            symbols: List of stock symbols to fetch news for
            feeds: Optional custom feed URLs (uses defaults if None)
            max_articles_per_symbol: Maximum articles per symbol

        Returns:
            Number of documents added
        """
        if not HAS_FEEDPARSER:
            logger.warning("feedparser not available, skipping RSS ingestion")
            return 0

        feed_urls = feeds or self.DEFAULT_RSS_FEEDS
        total_added = 0

        for symbol in symbols:
            symbol_added = 0

            for feed_name, feed_template in feed_urls.items():
                try:
                    url = feed_template.format(symbol=symbol)
                    feed = feedparser.parse(url)

                    for entry in feed.entries[:max_articles_per_symbol]:
                        doc = self._rss_entry_to_document(entry, symbol, feed_name)
                        if doc:
                            try:
                                self.corpus.add_document(doc)
                                symbol_added += 1
                            except ValueError as e:
                                logger.debug(f"Skipping duplicate: {e}")

                except Exception as e:
                    logger.warning(f"Failed to fetch {feed_name} for {symbol}: {e}")

            logger.info(f"Added {symbol_added} articles for {symbol}")
            total_added += symbol_added

        return total_added

    def ingest_alpha_vantage(
        self,
        symbols: list[str],
        api_key: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> int:
        """
        Ingest news from Alpha Vantage News API.

        Args:
            symbols: List of stock symbols
            api_key: Alpha Vantage API key
            time_from: Start time for news (default: 7 days ago)
            time_to: End time for news (default: now)
            limit: Maximum articles to fetch

        Returns:
            Number of documents added
        """
        if not HAS_REQUESTS:
            logger.warning("requests not available, skipping Alpha Vantage")
            return 0

        if not time_from:
            time_from = datetime.now() - timedelta(days=7)
        if not time_to:
            time_to = datetime.now()

        total_added = 0

        for symbol in symbols:
            try:
                url = "https://www.alphavantage.co/query"
                params = {
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol,
                    "time_from": time_from.strftime("%Y%m%dT%H%M"),
                    "time_to": time_to.strftime("%Y%m%dT%H%M"),
                    "limit": limit,
                    "apikey": api_key,
                }

                response = requests.get(url, params=params, timeout=30)
                data = response.json()

                if "feed" not in data:
                    logger.warning(f"No news data for {symbol}: {data.get('Note', 'Unknown error')}")
                    continue

                for article in data["feed"]:
                    doc = self._alpha_vantage_to_document(article, symbol)
                    if doc:
                        try:
                            self.corpus.add_document(doc)
                            total_added += 1
                        except ValueError:
                            pass

            except Exception as e:
                logger.warning(f"Failed to fetch Alpha Vantage for {symbol}: {e}")

        return total_added

    def ingest_from_dict(
        self,
        articles: list[dict],
        default_symbol: str | None = None,
    ) -> int:
        """
        Ingest articles from dictionary format.

        Args:
            articles: List of article dictionaries with keys:
                     title, text, timestamp, symbol(s), source
            default_symbol: Default symbol if not in article

        Returns:
            Number of documents added
        """
        total_added = 0

        for article in articles:
            try:
                # Parse timestamp
                timestamp = article.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)
                elif timestamp is None:
                    timestamp = datetime.now()

                # Get symbols
                symbols = article.get("symbols") or article.get("symbol")
                if isinstance(symbols, str):
                    symbols = [symbols]
                elif not symbols and default_symbol:
                    symbols = [default_symbol]
                elif not symbols:
                    continue

                # Combine title and text
                text = article.get("text", "")
                title = article.get("title", "")
                if title:
                    text = f"{title}\n\n{text}"

                doc = TextDocument(
                    text=text,
                    timestamp=timestamp,
                    source="news",
                    symbols=symbols,
                    sector=self._get_sector(symbols[0]) if symbols else None,
                    metadata={
                        "original_source": article.get("source", "unknown"),
                        "url": article.get("url"),
                        "author": article.get("author"),
                    },
                )

                self.corpus.add_document(doc)
                total_added += 1

            except Exception as e:
                logger.warning(f"Failed to ingest article: {e}")

        return total_added

    def add_custom_source(
        self,
        name: str,
        fetch_fn: Any,
    ) -> None:
        """
        Add a custom news source.

        Args:
            name: Source name
            fetch_fn: Function(symbol) -> list[dict] that returns articles
        """
        self._custom_sources[name] = fetch_fn

    def ingest_custom_sources(
        self,
        symbols: list[str],
    ) -> int:
        """
        Ingest from all custom sources.

        Args:
            symbols: List of symbols to fetch

        Returns:
            Number of documents added
        """
        total_added = 0

        for source_name, fetch_fn in self._custom_sources.items():
            for symbol in symbols:
                try:
                    articles = fetch_fn(symbol)
                    count = self.ingest_from_dict(articles, default_symbol=symbol)
                    total_added += count
                except Exception as e:
                    logger.warning(f"Custom source {source_name} failed for {symbol}: {e}")

        return total_added

    def _rss_entry_to_document(
        self,
        entry: Any,
        symbol: str,
        source: str,
    ) -> TextDocument | None:
        """Convert RSS entry to TextDocument."""
        try:
            # Parse publication date
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                timestamp = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                timestamp = datetime(*entry.updated_parsed[:6])
            else:
                timestamp = datetime.now()

            # Extract text
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            text = f"{title}\n\n{summary}" if summary else title

            if not text.strip():
                return None

            return TextDocument(
                text=text,
                timestamp=timestamp,
                source="news",
                symbols=[symbol],
                sector=self._get_sector(symbol),
                metadata={
                    "rss_source": source,
                    "url": getattr(entry, "link", None),
                    "author": getattr(entry, "author", None),
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse RSS entry: {e}")
            return None

    def _alpha_vantage_to_document(
        self,
        article: dict,
        symbol: str,
    ) -> TextDocument | None:
        """Convert Alpha Vantage article to TextDocument."""
        try:
            # Parse timestamp
            time_str = article.get("time_published", "")
            if time_str:
                timestamp = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
            else:
                timestamp = datetime.now()

            # Extract text
            title = article.get("title", "")
            summary = article.get("summary", "")
            text = f"{title}\n\n{summary}" if summary else title

            if not text.strip():
                return None

            # Get sentiment if available
            sentiment = None
            if "overall_sentiment_score" in article:
                sentiment = float(article["overall_sentiment_score"])

            return TextDocument(
                text=text,
                timestamp=timestamp,
                source="news",
                symbols=[symbol],
                sector=self._get_sector(symbol),
                metadata={
                    "alpha_vantage_sentiment": sentiment,
                    "url": article.get("url"),
                    "source_name": article.get("source"),
                    "category_within_source": article.get("category_within_source"),
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse Alpha Vantage article: {e}")
            return None

    def _get_sector(self, symbol: str) -> str | None:
        """Get sector for a symbol."""
        return self.SECTOR_MAP.get(symbol)

    def __repr__(self) -> str:
        """String representation."""
        return f"NewsIngestor(corpus={self.corpus})"
