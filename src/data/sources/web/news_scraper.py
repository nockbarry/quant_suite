"""
News Scraper

Scrapes financial news headlines and articles from various sources.
Uses rate limiting and caching to be respectful to sources.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

from .scraper import WebScraper, FetchResult

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Headline:
    """A news headline with metadata."""
    title: str
    source: str
    url: str
    symbol: str
    published_at: Optional[datetime] = None
    snippet: str = ""
    sentiment_hint: str = ""  # positive, negative, neutral based on keywords


@dataclass
class Article:
    """A full news article."""
    headline: Headline
    content: str
    author: str = ""
    tags: list = field(default_factory=list)


@dataclass
class AnalystRating:
    """An analyst rating or price target."""
    symbol: str
    analyst: str
    firm: str
    rating: str  # buy, hold, sell, upgrade, downgrade
    price_target: Optional[float] = None
    previous_target: Optional[float] = None
    date: Optional[datetime] = None


# =============================================================================
# NEWS SCRAPER
# =============================================================================

class NewsResearchScraper:
    """
    Scrape financial news from multiple sources.

    Usage:
        scraper = NewsResearchScraper()

        # Get headlines for a symbol
        headlines = await scraper.fetch_headlines("AAPL", max_results=20)

        # Get from specific source
        headlines = await scraper.fetch_from_yahoo("AAPL")

        # Extract analyst ratings
        ratings = await scraper.get_analyst_ratings("MSFT")
    """

    # Keywords for basic sentiment detection
    POSITIVE_KEYWORDS = [
        "beat", "exceeds", "surge", "soar", "rally", "gain", "upgrade",
        "bullish", "outperform", "buy", "strong", "growth", "profit",
        "record", "breakthrough", "success", "optimistic", "positive",
    ]

    NEGATIVE_KEYWORDS = [
        "miss", "falls", "drop", "plunge", "decline", "loss", "downgrade",
        "bearish", "underperform", "sell", "weak", "warning", "concern",
        "lawsuit", "recall", "investigation", "disappointing", "negative",
    ]

    def __init__(self, cache_dir: str = None):
        self.scraper = WebScraper(cache_dir=cache_dir)

    async def fetch_headlines(
        self,
        symbol: str,
        max_results: int = 20,
        sources: list = None,
    ) -> list[Headline]:
        """
        Fetch headlines from multiple sources.

        Args:
            symbol: Stock ticker symbol
            max_results: Maximum headlines to return
            sources: List of sources to use (default: all available)

        Returns:
            List of Headline objects sorted by recency
        """
        if sources is None:
            # Prioritize finviz as it's most reliable, yahoo has header issues
            sources = ["finviz", "marketwatch", "yahoo"]

        all_headlines = []

        # Fetch from each source concurrently
        tasks = []
        for source in sources:
            if source == "yahoo":
                tasks.append(self.fetch_from_yahoo(symbol))
            elif source == "finviz":
                tasks.append(self.fetch_from_finviz(symbol))
            elif source == "marketwatch":
                tasks.append(self.fetch_from_marketwatch(symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_headlines.extend(result)
            elif isinstance(result, Exception):
                logger.debug(f"Error fetching headlines: {result}")

        # Sort by date if available, deduplicate by title similarity
        seen_titles = set()
        unique_headlines = []
        for h in all_headlines:
            # Simple dedup by normalized title
            normalized = h.title.lower()[:50]
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique_headlines.append(h)

        # Add sentiment hints
        for h in unique_headlines:
            h.sentiment_hint = self._detect_sentiment(h.title)

        return unique_headlines[:max_results]

    async def fetch_from_yahoo(self, symbol: str) -> list[Headline]:
        """Fetch headlines from Yahoo Finance."""
        headlines = []

        try:
            url = f"https://finance.yahoo.com/quote/{symbol}/news"
            result = await self.scraper.fetch(url, use_cache=True)

            if result.status_code != 200:
                return headlines

            soup = BeautifulSoup(result.content, "lxml")

            # Yahoo Finance news items
            news_items = soup.find_all("li", class_=re.compile(r"js-stream-content"))
            if not news_items:
                # Try alternative selectors
                news_items = soup.find_all("div", {"data-testid": "news-item"})

            for item in news_items[:15]:
                try:
                    # Extract title and link
                    link_tag = item.find("a", href=True)
                    if not link_tag:
                        continue

                    title = link_tag.get_text(strip=True)
                    href = link_tag["href"]

                    if not href.startswith("http"):
                        href = f"https://finance.yahoo.com{href}"

                    if title and len(title) > 10:
                        headlines.append(Headline(
                            title=title,
                            source="yahoo",
                            url=href,
                            symbol=symbol,
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing Yahoo headline: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Error fetching Yahoo news for {symbol}: {e}")

        return headlines

    async def fetch_from_finviz(self, symbol: str) -> list[Headline]:
        """Fetch headlines from Finviz."""
        headlines = []

        try:
            url = f"https://finviz.com/quote.ashx?t={symbol}"
            result = await self.scraper.fetch(url, use_cache=True)

            if result.status_code != 200:
                return headlines

            soup = BeautifulSoup(result.content, "lxml")

            # Finviz news table
            news_table = soup.find("table", id="news-table")
            if not news_table:
                return headlines

            rows = news_table.find_all("tr")
            current_date = None

            for row in rows[:20]:
                try:
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue

                    # First cell may contain date
                    date_cell = cells[0].get_text(strip=True)
                    if len(date_cell) > 8:  # Has date
                        current_date = date_cell

                    # Second cell contains headline
                    link = cells[1].find("a")
                    if not link:
                        continue

                    title = link.get_text(strip=True)
                    href = link.get("href", "")

                    if title and len(title) > 10:
                        headlines.append(Headline(
                            title=title,
                            source="finviz",
                            url=href,
                            symbol=symbol,
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing Finviz headline: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Error fetching Finviz news for {symbol}: {e}")

        return headlines

    async def fetch_from_marketwatch(self, symbol: str) -> list[Headline]:
        """Fetch headlines from MarketWatch."""
        headlines = []

        try:
            url = f"https://www.marketwatch.com/investing/stock/{symbol.lower()}"
            result = await self.scraper.fetch(url, use_cache=True)

            if result.status_code != 200:
                return headlines

            soup = BeautifulSoup(result.content, "lxml")

            # MarketWatch news items
            news_items = soup.find_all("div", class_=re.compile(r"article__content"))
            if not news_items:
                news_items = soup.find_all("a", class_=re.compile(r"link"))

            for item in news_items[:15]:
                try:
                    if item.name == "a":
                        title = item.get_text(strip=True)
                        href = item.get("href", "")
                    else:
                        link = item.find("a")
                        if not link:
                            continue
                        title = link.get_text(strip=True)
                        href = link.get("href", "")

                    if not href.startswith("http"):
                        href = f"https://www.marketwatch.com{href}"

                    if title and len(title) > 10:
                        headlines.append(Headline(
                            title=title,
                            source="marketwatch",
                            url=href,
                            symbol=symbol,
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing MarketWatch headline: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Error fetching MarketWatch news for {symbol}: {e}")

        return headlines

    async def fetch_article(self, headline: Headline) -> Optional[Article]:
        """Fetch full article content from a headline."""
        try:
            result = await self.scraper.fetch(headline.url, use_cache=True)

            if result.status_code != 200:
                return None

            soup = BeautifulSoup(result.content, "lxml")

            # Extract article body - try common selectors
            content = ""
            for selector in ["article", ".article-body", ".caas-body", "#article-body"]:
                article_elem = soup.select_one(selector)
                if article_elem:
                    # Get all paragraphs
                    paragraphs = article_elem.find_all("p")
                    content = " ".join(p.get_text(strip=True) for p in paragraphs)
                    break

            if not content:
                # Fallback: extract all text
                content = self.scraper.extract_text(result.content)

            # Extract author
            author = ""
            author_elem = soup.find(class_=re.compile(r"author|byline"))
            if author_elem:
                author = author_elem.get_text(strip=True)

            return Article(
                headline=headline,
                content=content[:10000],  # Limit content size
                author=author,
            )

        except Exception as e:
            logger.debug(f"Error fetching article: {e}")
            return None

    async def get_analyst_ratings(self, symbol: str) -> list[AnalystRating]:
        """Extract analyst ratings for a symbol."""
        ratings = []

        try:
            # Try Finviz for analyst ratings
            url = f"https://finviz.com/quote.ashx?t={symbol}"
            result = await self.scraper.fetch(url, use_cache=True)

            if result.status_code != 200:
                return ratings

            soup = BeautifulSoup(result.content, "lxml")

            # Look for analyst table
            tables = soup.find_all("table", class_=re.compile(r"fullview-ratings"))

            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    try:
                        cells = row.find_all("td")
                        if len(cells) < 4:
                            continue

                        date_str = cells[0].get_text(strip=True)
                        action = cells[1].get_text(strip=True).lower()
                        firm = cells[2].get_text(strip=True)
                        rating = cells[3].get_text(strip=True)

                        # Parse price target if present
                        price_target = None
                        if len(cells) > 4:
                            target_text = cells[4].get_text(strip=True)
                            match = re.search(r"\$?([\d,.]+)", target_text)
                            if match:
                                price_target = float(match.group(1).replace(",", ""))

                        ratings.append(AnalystRating(
                            symbol=symbol,
                            analyst="",
                            firm=firm,
                            rating=action if action else rating.lower(),
                            price_target=price_target,
                        ))
                    except Exception as e:
                        logger.debug(f"Error parsing analyst rating: {e}")
                        continue

        except Exception as e:
            logger.debug(f"Error fetching analyst ratings for {symbol}: {e}")

        return ratings

    def _detect_sentiment(self, text: str) -> str:
        """Detect basic sentiment from text using keywords."""
        text_lower = text.lower()

        positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text_lower)
        negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        return "neutral"

    def compute_news_features(self, headlines: list[Headline]) -> dict:
        """
        Compute features from a list of headlines.

        Returns:
            Dict with features like sentiment_score, headline_count, etc.
        """
        if not headlines:
            return {
                "headline_count": 0,
                "sentiment_score": 0.0,
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "source_diversity": 0,
            }

        positive = sum(1 for h in headlines if h.sentiment_hint == "positive")
        negative = sum(1 for h in headlines if h.sentiment_hint == "negative")
        total = len(headlines)

        sources = set(h.source for h in headlines)

        # Sentiment score: -1 to 1
        sentiment_score = (positive - negative) / total if total > 0 else 0.0

        return {
            "headline_count": total,
            "sentiment_score": sentiment_score,
            "positive_ratio": positive / total if total > 0 else 0.0,
            "negative_ratio": negative / total if total > 0 else 0.0,
            "source_diversity": len(sources),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_news_headlines(symbol: str, max_results: int = 20) -> list[Headline]:
    """Quick access to fetch headlines for a symbol."""
    scraper = NewsResearchScraper()
    return await scraper.fetch_headlines(symbol, max_results=max_results)


async def get_news_sentiment(symbol: str) -> dict:
    """Get news sentiment features for a symbol."""
    scraper = NewsResearchScraper()
    headlines = await scraper.fetch_headlines(symbol, max_results=30)
    return scraper.compute_news_features(headlines)
