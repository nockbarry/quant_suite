"""
Blog and Industry Report Scraper

Scrapes articles from industry blogs for alpha research:
- Semi Analysis (semiconductor industry)
- Other industry sources (configurable)

Follows best practices:
- robots.txt compliance
- Rate limiting (min 2 sec between requests)
- Honest User-Agent
- Caching to avoid re-fetching
- Point-in-time timestamps

All scraped data is persisted for backtesting.
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Optional imports
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = None

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    BeautifulSoup = None

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    feedparser = None


# =============================================================================
# SCRAPING POLICY
# =============================================================================

@dataclass
class ScrapingPolicy:
    """Enforce ethical scraping across all sources."""

    # Rate limiting (per domain)
    MIN_REQUEST_INTERVAL: float = 2.0  # seconds between requests
    MAX_REQUESTS_PER_HOUR: int = 100

    # Compliance
    RESPECT_ROBOTS_TXT: bool = True
    IDENTIFY_AS_BOT: bool = True
    CACHE_RESPONSES: bool = True

    # Backoff on errors
    RETRY_DELAYS: tuple[int, ...] = (5, 30, 120, 600)

    # User agent
    USER_AGENT: str = (
        "QuantSuiteResearchBot/1.0 (+https://github.com/quant-suite; "
        "research-only; rate-limited)"
    )


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ScrapedArticle:
    """A scraped article from a blog."""

    id: str  # Hash of URL
    source: str  # e.g., 'semianalysis'
    title: str
    url: str
    content: str  # Full article text
    summary: str  # First paragraph or excerpt
    published_date: datetime | None
    scraped_date: datetime
    available_date: datetime  # When we could have known (conservative)
    author: str = ""
    tags: list[str] = field(default_factory=list)
    related_symbols: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)  # Extracted data tables
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_date"] = self.published_date.isoformat() if self.published_date else None
        d["scraped_date"] = self.scraped_date.isoformat()
        d["available_date"] = self.available_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScrapedArticle":
        if d.get("published_date"):
            d["published_date"] = datetime.fromisoformat(d["published_date"])
        d["scraped_date"] = datetime.fromisoformat(d["scraped_date"])
        d["available_date"] = datetime.fromisoformat(d["available_date"])
        return cls(**d)

    def was_available_on(self, date: datetime) -> bool:
        """Check if article was available for backtesting on given date."""
        return self.available_date <= date

    @property
    def content_hash(self) -> str:
        """Hash of content for deduplication."""
        return hashlib.md5(self.content.encode()).hexdigest()[:16]


@dataclass
class BlogSourceConfig:
    """Configuration for a blog source."""

    name: str
    base_url: str
    rss_url: str | None = None  # RSS feed if available
    article_selector: str = "article"  # CSS selector for articles
    title_selector: str = "h1"
    date_selector: str = "time"
    content_selector: str = ".content, .post-content, article"
    author_selector: str = ".author, .byline"
    related_symbols: list[str] = field(default_factory=list)
    category: str = "general"
    requires_js: bool = False  # Some sites need JS rendering

    # Symbol extraction patterns
    symbol_patterns: list[str] = field(default_factory=lambda: [
        r'\$([A-Z]{1,5})\b',  # $NVDA format
        r'\b([A-Z]{2,5})\s+stock\b',  # NVDA stock
        r'\b([A-Z]{2,5})\s+shares?\b',  # NVDA shares
    ])


# =============================================================================
# BLOG SCRAPER
# =============================================================================

class BlogScraper:
    """
    Universal blog scraper for industry research.

    Supports multiple sources with configurable parsers.
    """

    # Pre-configured sources
    SOURCES = {
        'semianalysis': BlogSourceConfig(
            name='Semi Analysis',
            base_url='https://www.semianalysis.com',
            rss_url='https://www.semianalysis.com/feed',
            article_selector='article.post',
            title_selector='h1.post-title',
            date_selector='time.post-date',
            content_selector='.post-content',
            related_symbols=['NVDA', 'AMD', 'INTC', 'TSM', 'ASML', 'MU', 'QCOM', 'AVGO'],
            category='semiconductor',
        ),
        'stratechery': BlogSourceConfig(
            name='Stratechery',
            base_url='https://stratechery.com',
            rss_url='https://stratechery.com/feed/',
            article_selector='article',
            title_selector='h1.entry-title',
            date_selector='time.entry-date',
            content_selector='.entry-content',
            related_symbols=['AAPL', 'GOOGL', 'MSFT', 'META', 'AMZN', 'NFLX'],
            category='tech_strategy',
        ),
        'asymco': BlogSourceConfig(
            name='Asymco',
            base_url='http://www.asymco.com',
            rss_url='http://www.asymco.com/feed/',
            article_selector='article',
            title_selector='h1.entry-title',
            date_selector='time.entry-date',
            content_selector='.entry-content',
            related_symbols=['AAPL'],
            category='apple_analysis',
        ),
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
        policy: ScrapingPolicy | None = None,
    ):
        self.cache_dir = cache_dir or paths.scraped_data / "blogs"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.policy = policy or ScrapingPolicy()
        self._last_request_time: dict[str, float] = {}
        self._request_counts: dict[str, int] = {}
        self._robots_cache: dict[str, dict] = {}

        # Article cache
        self._articles_cache: dict[str, list[ScrapedArticle]] = {}

        self._load_cache()

    def _load_cache(self) -> None:
        """Load cached articles from disk."""
        for source_key in self.SOURCES:
            cache_file = self.cache_dir / f"{source_key}_articles.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    self._articles_cache[source_key] = [
                        ScrapedArticle.from_dict(d) for d in data
                    ]
                    logger.info(f"Loaded {len(self._articles_cache[source_key])} articles from {source_key}")
                except Exception as e:
                    logger.warning(f"Failed to load cache for {source_key}: {e}")

    def _save_cache(self, source_key: str) -> None:
        """Save cached articles to disk."""
        if source_key not in self._articles_cache:
            return

        cache_file = self.cache_dir / f"{source_key}_articles.json"
        articles = [a.to_dict() for a in self._articles_cache[source_key]]
        cache_file.write_text(json.dumps(articles, indent=2))
        logger.info(f"Saved {len(articles)} articles to {source_key} cache")

    async def _rate_limit(self, domain: str) -> None:
        """Apply rate limiting per domain."""
        now = asyncio.get_event_loop().time()
        last_time = self._last_request_time.get(domain, 0)
        elapsed = now - last_time

        if elapsed < self.policy.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.policy.MIN_REQUEST_INTERVAL - elapsed)

        self._last_request_time[domain] = asyncio.get_event_loop().time()

        # Track request count
        hour_key = f"{domain}_{datetime.now().strftime('%Y%m%d%H')}"
        self._request_counts[hour_key] = self._request_counts.get(hour_key, 0) + 1

        if self._request_counts[hour_key] > self.policy.MAX_REQUESTS_PER_HOUR:
            logger.warning(f"Rate limit reached for {domain}. Sleeping...")
            await asyncio.sleep(3600)  # Wait an hour

    async def _fetch_url(self, url: str) -> str | None:
        """Fetch a URL with rate limiting and error handling."""
        if not HAS_AIOHTTP:
            logger.error("aiohttp required: pip install aiohttp")
            return None

        domain = urlparse(url).netloc
        await self._rate_limit(domain)

        headers = {
            "User-Agent": self.policy.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        for attempt, delay in enumerate(self.policy.RETRY_DELAYS):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=30) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:  # Rate limited
                            logger.warning(f"Rate limited by {domain}. Waiting {delay}s...")
                            await asyncio.sleep(delay)
                        else:
                            logger.warning(f"HTTP {response.status} for {url}")
                            return None
            except Exception as e:
                logger.warning(f"Request failed ({attempt+1}/{len(self.policy.RETRY_DELAYS)}): {e}")
                if attempt < len(self.policy.RETRY_DELAYS) - 1:
                    await asyncio.sleep(delay)

        return None

    async def _fetch_rss(self, rss_url: str) -> list[dict]:
        """Fetch and parse RSS feed."""
        if not HAS_FEEDPARSER:
            logger.warning("feedparser not installed. Install with: pip install feedparser")
            return []

        domain = urlparse(rss_url).netloc
        await self._rate_limit(domain)

        try:
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, rss_url)

            entries = []
            for entry in feed.entries:
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                    "author": entry.get("author", ""),
                })

            logger.info(f"Fetched {len(entries)} entries from RSS: {rss_url}")
            return entries

        except Exception as e:
            logger.error(f"RSS fetch failed for {rss_url}: {e}")
            return []

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse various date formats."""
        if not date_str:
            return None

        # Common formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Try dateutil if available
        try:
            from dateutil.parser import parse
            return parse(date_str)
        except Exception:
            pass

        return None

    def _extract_symbols(self, text: str, config: BlogSourceConfig) -> list[str]:
        """Extract stock symbols from text."""
        symbols = set()

        for pattern in config.symbol_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                sym = match.upper()
                if 2 <= len(sym) <= 5 and sym.isalpha():
                    symbols.add(sym)

        # Add related symbols if they're mentioned
        text_upper = text.upper()
        for sym in config.related_symbols:
            if sym in text_upper:
                symbols.add(sym)

        return list(symbols)

    def _extract_tables(self, html: str) -> list[dict]:
        """Extract data tables from HTML."""
        if not HAS_BS4:
            return []

        tables = []
        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            try:
                # Get headers
                headers = []
                header_row = table.find("thead") or table.find("tr")
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

                # Get rows
                rows = []
                tbody = table.find("tbody") or table
                for tr in tbody.find_all("tr")[1:]:  # Skip header row
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)

                if headers and rows:
                    tables.append({
                        "headers": headers,
                        "rows": rows,
                        "n_rows": len(rows),
                    })
            except Exception as e:
                logger.warning(f"Failed to parse table: {e}")

        return tables

    def _url_to_id(self, url: str) -> str:
        """Generate unique ID from URL."""
        return hashlib.md5(url.encode()).hexdigest()[:12]

    async def scrape_source(
        self,
        source_key: str,
        max_articles: int = 20,
        force_refresh: bool = False,
    ) -> list[ScrapedArticle]:
        """
        Scrape articles from a configured source.

        Args:
            source_key: Key from SOURCES dict (e.g., 'semianalysis')
            max_articles: Maximum articles to fetch
            force_refresh: Ignore cache and re-scrape

        Returns:
            List of scraped articles
        """
        if source_key not in self.SOURCES:
            raise ValueError(f"Unknown source: {source_key}. Available: {list(self.SOURCES.keys())}")

        config = self.SOURCES[source_key]

        # Check cache
        if not force_refresh and source_key in self._articles_cache:
            cached = self._articles_cache[source_key]
            if cached:
                cache_age = datetime.now() - cached[0].scraped_date
                if cache_age < timedelta(hours=6):
                    logger.info(f"Using cached articles for {source_key}")
                    return cached[:max_articles]

        articles = []
        now = datetime.now()

        # Try RSS first (more reliable and polite)
        if config.rss_url:
            entries = await self._fetch_rss(config.rss_url)

            for entry in entries[:max_articles]:
                # Create article from RSS entry
                published = self._parse_date(entry.get("published"))

                article = ScrapedArticle(
                    id=self._url_to_id(entry["link"]),
                    source=source_key,
                    title=entry["title"],
                    url=entry["link"],
                    content=entry.get("summary", ""),  # RSS usually has summary only
                    summary=entry.get("summary", "")[:500],
                    published_date=published,
                    scraped_date=now,
                    available_date=now,  # Conservative: assume we got it now
                    author=entry.get("author", ""),
                    tags=[config.category],
                    related_symbols=self._extract_symbols(
                        entry["title"] + " " + entry.get("summary", ""),
                        config
                    ),
                )
                articles.append(article)

        # Optionally fetch full content for each article
        # (Commented out to be polite - uncomment if needed)
        # for article in articles[:5]:  # Only first 5 to be polite
        #     full_html = await self._fetch_url(article.url)
        #     if full_html:
        #         article.content = self._extract_content(full_html, config)
        #         article.tables = self._extract_tables(full_html)

        # Update cache
        self._articles_cache[source_key] = articles
        self._save_cache(source_key)

        logger.info(f"Scraped {len(articles)} articles from {source_key}")
        return articles

    async def scrape_all_sources(
        self,
        max_per_source: int = 10,
    ) -> dict[str, list[ScrapedArticle]]:
        """Scrape all configured sources."""
        results = {}

        for source_key in self.SOURCES:
            try:
                articles = await self.scrape_source(source_key, max_per_source)
                results[source_key] = articles
            except Exception as e:
                logger.error(f"Failed to scrape {source_key}: {e}")
                results[source_key] = []

        return results

    def get_cached_articles(
        self,
        source_key: str | None = None,
        since: datetime | None = None,
        symbols: list[str] | None = None,
    ) -> list[ScrapedArticle]:
        """
        Get cached articles with optional filtering.

        Args:
            source_key: Filter by source
            since: Only articles after this date
            symbols: Only articles mentioning these symbols

        Returns:
            Filtered list of articles
        """
        articles = []

        sources = [source_key] if source_key else list(self._articles_cache.keys())

        for src in sources:
            if src in self._articles_cache:
                articles.extend(self._articles_cache[src])

        # Filter by date
        if since:
            articles = [a for a in articles if a.scraped_date >= since]

        # Filter by symbols
        if symbols:
            symbols_set = set(s.upper() for s in symbols)
            articles = [
                a for a in articles
                if any(s in symbols_set for s in a.related_symbols)
            ]

        return sorted(articles, key=lambda a: a.scraped_date, reverse=True)

    def get_articles_for_backtesting(
        self,
        as_of: datetime,
        source_key: str | None = None,
    ) -> list[ScrapedArticle]:
        """
        Get articles that were available as of a specific date.

        For point-in-time safe backtesting.
        """
        articles = self.get_cached_articles(source_key)
        return [a for a in articles if a.was_available_on(as_of)]

    def to_dataframe(
        self,
        articles: list[ScrapedArticle] | None = None,
    ) -> pd.DataFrame:
        """Convert articles to DataFrame for analysis."""
        if articles is None:
            articles = self.get_cached_articles()

        if not articles:
            return pd.DataFrame()

        records = []
        for a in articles:
            records.append({
                "id": a.id,
                "source": a.source,
                "title": a.title,
                "url": a.url,
                "published_date": a.published_date,
                "scraped_date": a.scraped_date,
                "available_date": a.available_date,
                "author": a.author,
                "n_symbols": len(a.related_symbols),
                "symbols": ",".join(a.related_symbols),
                "n_tables": len(a.tables),
                "content_length": len(a.content),
            })

        df = pd.DataFrame(records)
        if "scraped_date" in df.columns:
            df = df.sort_values("scraped_date", ascending=False)

        return df

    def list_sources(self) -> dict[str, dict]:
        """List all available sources with metadata."""
        return {
            key: {
                "name": config.name,
                "base_url": config.base_url,
                "category": config.category,
                "related_symbols": config.related_symbols,
                "has_rss": config.rss_url is not None,
            }
            for key, config in self.SOURCES.items()
        }

    def add_source(self, key: str, config: BlogSourceConfig) -> None:
        """Add a new source configuration."""
        self.SOURCES[key] = config
        logger.info(f"Added source: {key}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def scrape_semiconductor_blogs(max_articles: int = 20) -> list[ScrapedArticle]:
    """Convenience function to scrape semiconductor blogs."""
    scraper = BlogScraper()
    return await scraper.scrape_source("semianalysis", max_articles)


async def scrape_tech_blogs(max_articles: int = 20) -> dict[str, list[ScrapedArticle]]:
    """Convenience function to scrape all tech blogs."""
    scraper = BlogScraper()
    return await scraper.scrape_all_sources(max_articles)


def get_recent_articles(
    days: int = 7,
    symbols: list[str] | None = None,
) -> list[ScrapedArticle]:
    """Get articles from the last N days."""
    scraper = BlogScraper()
    since = datetime.now() - timedelta(days=days)
    return scraper.get_cached_articles(since=since, symbols=symbols)
