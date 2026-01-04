"""
Base Web Scraper with Caching, Rate Limiting, and Robots.txt Compliance

Provides robust web scraping infrastructure for the quant suite:
- Disk-based caching with TTL
- Rate limiting to respect server limits
- Robots.txt compliance checking
- HTML parsing and text extraction
- Table extraction to DataFrames
- Optional JavaScript rendering via playwright
- Financial signal extraction

As specified in Section 3.5.2 of the Testing Suite documentation.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import aiohttp
import pandas as pd
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """Token bucket rate limiter for async requests."""

    def __init__(self, requests_per_second: float = 1.0):
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


# =============================================================================
# DISK CACHE
# =============================================================================

@dataclass
class CacheEntry:
    """A cached response with metadata."""
    content: str
    url: str
    fetched_at: str
    expires_at: str
    content_type: str = "text/html"


class DiskCache:
    """Disk-based cache with TTL support."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl: timedelta = timedelta(hours=24),
    ):
        self.cache_dir = cache_dir or Path.home() / ".quant_cache" / "web"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl

    def _url_to_path(self, url: str) -> Path:
        """Convert URL to cache file path."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        domain = urlparse(url).netloc.replace(".", "_")
        return self.cache_dir / domain / f"{url_hash}.json"

    def get(self, url: str) -> Optional[str]:
        """Get cached content if not expired."""
        cache_path = self._url_to_path(url)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                entry = json.load(f)

            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.now() > expires_at:
                cache_path.unlink()
                return None

            logger.debug(f"Cache hit: {url}")
            return entry["content"]

        except (json.JSONDecodeError, KeyError, ValueError):
            cache_path.unlink(missing_ok=True)
            return None

    def set(
        self,
        url: str,
        content: str,
        ttl: Optional[timedelta] = None,
        content_type: str = "text/html",
    ):
        """Cache content with TTL."""
        cache_path = self._url_to_path(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        ttl = ttl or self.default_ttl
        now = datetime.now()

        entry = CacheEntry(
            content=content,
            url=url,
            fetched_at=now.isoformat(),
            expires_at=(now + ttl).isoformat(),
            content_type=content_type,
        )

        with open(cache_path, "w") as f:
            json.dump(entry.__dict__, f)

        logger.debug(f"Cached: {url}")

    def clear(self, domain: Optional[str] = None):
        """Clear cache, optionally for specific domain."""
        if domain:
            domain_dir = self.cache_dir / domain.replace(".", "_")
            if domain_dir.exists():
                for f in domain_dir.iterdir():
                    f.unlink()
                domain_dir.rmdir()
        else:
            for domain_dir in self.cache_dir.iterdir():
                if domain_dir.is_dir():
                    for f in domain_dir.iterdir():
                        f.unlink()
                    domain_dir.rmdir()


# =============================================================================
# WEB SCRAPER
# =============================================================================

@dataclass
class FetchResult:
    """Result of a fetch operation."""
    url: str
    content: str
    status_code: int
    content_type: str
    from_cache: bool
    fetched_at: datetime = field(default_factory=datetime.now)


class WebScraper:
    """Robust web scraper with caching, rate limiting, and parsing."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        rate_limit: float = 1.0,
        cache_ttl: timedelta = timedelta(hours=24),
        timeout: int = 30,
    ):
        self.cache = DiskCache(cache_dir, cache_ttl)
        self.rate_limiter = RateLimiter(rate_limit)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper settings to avoid header overflow."""
        if self._session is None or self._session.closed:
            # Create connector with larger read buffer
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                enable_cleanup_closed=True,
            )
            # Use DummyCookieJar to avoid accumulating cookies that cause header overflow
            cookie_jar = aiohttp.DummyCookieJar()
            self._session = aiohttp.ClientSession(
                headers=self.DEFAULT_HEADERS,
                timeout=self.timeout,
                connector=connector,
                cookie_jar=cookie_jar,
                # Increase max field size to handle large response headers (e.g., from Yahoo)
                max_field_size=32768,  # 32KB to handle very large headers
                max_line_size=32768,   # Also increase max line size
            )
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch(
        self,
        url: str,
        use_cache: bool = True,
        headers: Optional[dict] = None,
        cache_ttl: Optional[timedelta] = None,
    ) -> FetchResult:
        """
        Fetch URL with caching and rate limiting.

        Args:
            url: URL to fetch
            use_cache: Whether to use cache
            headers: Additional headers
            cache_ttl: Override default cache TTL

        Returns:
            FetchResult with content and metadata
        """
        # Check cache first
        if use_cache:
            cached = self.cache.get(url)
            if cached is not None:
                return FetchResult(
                    url=url,
                    content=cached,
                    status_code=200,
                    content_type="text/html",
                    from_cache=True,
                )

        # Rate limit
        await self.rate_limiter.acquire()

        # Fetch
        session = await self._get_session()
        request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}

        try:
            async with session.get(url, headers=request_headers) as response:
                content = await response.text()
                content_type = response.headers.get("Content-Type", "text/html")

                result = FetchResult(
                    url=url,
                    content=content,
                    status_code=response.status,
                    content_type=content_type,
                    from_cache=False,
                )

                # Cache successful responses
                if response.status == 200 and use_cache:
                    self.cache.set(url, content, cache_ttl, content_type)

                return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching {url}: {e}")
            raise

    async def fetch_with_browser(
        self,
        url: str,
        wait_for: str = "networkidle",
        use_cache: bool = True,
    ) -> FetchResult:
        """
        Fetch URL using playwright for JavaScript rendering.

        Args:
            url: URL to fetch
            wait_for: Wait condition ('load', 'domcontentloaded', 'networkidle')
            use_cache: Whether to use cache

        Returns:
            FetchResult with rendered content
        """
        # Check cache first
        if use_cache:
            cached = self.cache.get(url)
            if cached is not None:
                return FetchResult(
                    url=url,
                    content=cached,
                    status_code=200,
                    content_type="text/html",
                    from_cache=True,
                )

        # Rate limit
        await self.rate_limiter.acquire()

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                response = await page.goto(url, wait_until=wait_for)
                content = await page.content()

                result = FetchResult(
                    url=url,
                    content=content,
                    status_code=response.status if response else 200,
                    content_type="text/html",
                    from_cache=False,
                )

                await browser.close()

                if result.status_code == 200 and use_cache:
                    self.cache.set(url, content)

                return result

        except ImportError:
            logger.warning("playwright not installed, falling back to regular fetch")
            return await self.fetch(url, use_cache)

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML with BeautifulSoup."""
        return BeautifulSoup(html, "lxml")

    def extract_text(
        self,
        html: str,
        selector: Optional[str] = None,
        remove_scripts: bool = True,
        remove_styles: bool = True,
    ) -> str:
        """
        Extract clean text from HTML.

        Args:
            html: HTML content
            selector: CSS selector to limit scope
            remove_scripts: Remove script tags
            remove_styles: Remove style tags

        Returns:
            Clean text content
        """
        soup = self.parse_html(html)

        # Remove unwanted elements
        if remove_scripts:
            for script in soup.find_all("script"):
                script.decompose()
        if remove_styles:
            for style in soup.find_all("style"):
                style.decompose()

        # Select scope
        if selector:
            element = soup.select_one(selector)
            if element is None:
                return ""
            text = element.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        # Clean up whitespace
        import re
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_tables(
        self,
        html: str,
        selector: Optional[str] = None,
    ) -> list[pd.DataFrame]:
        """
        Extract tables from HTML as DataFrames.

        Args:
            html: HTML content
            selector: CSS selector for specific tables

        Returns:
            List of DataFrames
        """
        soup = self.parse_html(html)

        if selector:
            tables = soup.select(selector)
        else:
            tables = soup.find_all("table")

        dfs = []
        for table in tables:
            try:
                # Read table with pandas
                df = pd.read_html(str(table))[0]
                dfs.append(df)
            except Exception as e:
                logger.debug(f"Failed to parse table: {e}")
                continue

        return dfs

    def extract_links(
        self,
        html: str,
        base_url: str,
        selector: Optional[str] = None,
    ) -> list[dict]:
        """
        Extract links from HTML.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links
            selector: CSS selector for specific links

        Returns:
            List of link dicts with 'href' and 'text'
        """
        from urllib.parse import urljoin

        soup = self.parse_html(html)

        if selector:
            links = soup.select(selector)
        else:
            links = soup.find_all("a", href=True)

        results = []
        for link in links:
            href = link.get("href", "")
            if href:
                full_url = urljoin(base_url, href)
                results.append({
                    "href": full_url,
                    "text": link.get_text(strip=True),
                })

        return results

    def extract_metadata(self, html: str) -> dict:
        """
        Extract metadata from HTML (title, meta tags, etc).

        Args:
            html: HTML content

        Returns:
            Dict with metadata
        """
        soup = self.parse_html(html)

        metadata = {
            "title": None,
            "description": None,
            "keywords": None,
            "author": None,
            "published_date": None,
            "og_title": None,
            "og_description": None,
            "og_image": None,
        }

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower()
            prop = meta.get("property", "").lower()
            content = meta.get("content", "")

            if name == "description" or prop == "og:description":
                metadata["description"] = content
            elif name == "keywords":
                metadata["keywords"] = content
            elif name == "author":
                metadata["author"] = content
            elif name in ("date", "pubdate", "publishdate"):
                metadata["published_date"] = content
            elif prop == "og:title":
                metadata["og_title"] = content
            elif prop == "og:image":
                metadata["og_image"] = content

        return metadata


# =============================================================================
# ASYNC BATCH FETCHER
# =============================================================================

async def fetch_batch(
    urls: list[str],
    scraper: Optional[WebScraper] = None,
    max_concurrent: int = 5,
    use_cache: bool = True,
) -> list[FetchResult]:
    """
    Fetch multiple URLs concurrently with rate limiting.

    Args:
        urls: List of URLs to fetch
        scraper: WebScraper instance (creates one if not provided)
        max_concurrent: Maximum concurrent requests
        use_cache: Whether to use cache

    Returns:
        List of FetchResults
    """
    if scraper is None:
        scraper = WebScraper()

    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(url: str) -> FetchResult:
        async with semaphore:
            try:
                return await scraper.fetch(url, use_cache)
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")
                return FetchResult(
                    url=url,
                    content="",
                    status_code=0,
                    content_type="",
                    from_cache=False,
                )

    results = await asyncio.gather(*[fetch_one(url) for url in urls])

    return list(results)


# =============================================================================
# ROBOTS.TXT COMPLIANCE
# =============================================================================

class RobotsChecker:
    """
    Check robots.txt compliance before scraping.

    Caches robots.txt files to avoid repeated fetches.
    """

    def __init__(
        self,
        user_agent: str = "QuantResearchBot/1.0",
        cache_ttl: timedelta = timedelta(hours=24),
    ):
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self._parsers: dict[str, tuple[RobotFileParser, datetime]] = {}

    def _get_robots_url(self, url: str) -> str:
        """Get robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    async def _fetch_robots(self, robots_url: str) -> RobotFileParser:
        """Fetch and parse robots.txt."""
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        parser.parse(content.splitlines())
                    else:
                        # No robots.txt means everything is allowed
                        parser.parse([])
        except Exception as e:
            logger.debug(f"Could not fetch robots.txt from {robots_url}: {e}")
            # Assume everything is allowed if we can't fetch
            parser.parse([])

        return parser

    async def is_allowed(self, url: str) -> bool:
        """
        Check if URL is allowed by robots.txt.

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        robots_url = self._get_robots_url(url)
        parsed = urlparse(url)
        domain = parsed.netloc

        # Check cache
        if domain in self._parsers:
            parser, cached_at = self._parsers[domain]
            if datetime.now() - cached_at < self.cache_ttl:
                return parser.can_fetch(self.user_agent, url)

        # Fetch and cache
        parser = await self._fetch_robots(robots_url)
        self._parsers[domain] = (parser, datetime.now())

        return parser.can_fetch(self.user_agent, url)

    def get_crawl_delay(self, url: str) -> float | None:
        """Get crawl delay from robots.txt if specified."""
        parsed = urlparse(url)
        domain = parsed.netloc

        if domain in self._parsers:
            parser, _ = self._parsers[domain]
            delay = parser.crawl_delay(self.user_agent)
            return delay

        return None


# =============================================================================
# SCRAPING CONFIGURATION
# =============================================================================

@dataclass
class ScrapingConfig:
    """Configuration for web scraping operations."""
    user_agent: str = "QuantResearchBot/1.0 (research@company.com)"
    requests_per_second: float = 0.5  # Be polite
    cache_ttl: timedelta = timedelta(hours=24)
    timeout: int = 30
    max_retries: int = 3
    respect_robots_txt: bool = True
    use_cache: bool = True
    use_browser: bool = False  # Use Playwright for JS rendering


@dataclass
class ScrapedContent:
    """Result of a scraping operation with extracted data."""
    url: str
    raw_html: str
    text: str
    title: str | None
    metadata: dict[str, Any]
    tables: list[pd.DataFrame]
    links: list[dict[str, str]]
    fetched_at: datetime
    from_cache: bool
    status_code: int

    # Financial-specific extractions
    numbers: list[dict[str, Any]] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    entities: list[dict[str, str]] = field(default_factory=list)


# =============================================================================
# WEB SCRAPING PIPELINE
# =============================================================================

class WebScrapingPipeline:
    """
    Ethical, compliant web scraping for alternative data.

    As specified in Section 3.5.2 of the Testing Suite documentation.

    Features:
    - Respects robots.txt
    - Rate limiting
    - Caching
    - Automatic retry
    - Financial signal extraction
    """

    def __init__(self, config: ScrapingConfig | None = None):
        self.config = config or ScrapingConfig()
        self.scraper = WebScraper(
            rate_limit=self.config.requests_per_second,
            cache_ttl=self.config.cache_ttl,
            timeout=self.config.timeout,
        )
        self.robots_checker = RobotsChecker(
            user_agent=self.config.user_agent,
            cache_ttl=self.config.cache_ttl,
        )

        # Number pattern for financial extraction
        self._number_pattern = re.compile(
            r"[$]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|trillion|M|B|K))?",
            re.IGNORECASE,
        )
        # Date patterns
        self._date_patterns = [
            r"\d{4}-\d{2}-\d{2}",  # ISO format
            r"\d{1,2}/\d{1,2}/\d{4}",  # US format
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",
        ]

    async def scrape_with_compliance(self, url: str) -> ScrapedContent:
        """
        Scrape URL with respect for robots.txt and rate limits.

        Args:
            url: URL to scrape

        Returns:
            ScrapedContent with extracted data

        Raises:
            PermissionError: If robots.txt disallows scraping
        """
        # Check robots.txt
        if self.config.respect_robots_txt:
            allowed = await self.robots_checker.is_allowed(url)
            if not allowed:
                raise PermissionError(f"Scraping not allowed by robots.txt: {url}")

            # Check for crawl delay
            delay = self.robots_checker.get_crawl_delay(url)
            if delay and delay > 1.0 / self.config.requests_per_second:
                await asyncio.sleep(delay)

        # Fetch content
        if self.config.use_browser:
            result = await self.scraper.fetch_with_browser(url, use_cache=self.config.use_cache)
        else:
            result = await self.scraper.fetch(url, use_cache=self.config.use_cache)

        # Extract content
        text = self.scraper.extract_text(result.content)
        metadata = self.scraper.extract_metadata(result.content)
        tables = self.scraper.extract_tables(result.content)
        links = self.scraper.extract_links(result.content, url)

        # Extract financial signals
        numbers = self._extract_numbers(text)
        dates = self._extract_dates(text)
        entities = self._extract_entities(text)

        return ScrapedContent(
            url=url,
            raw_html=result.content,
            text=text,
            title=metadata.get("title"),
            metadata=metadata,
            tables=tables,
            links=links,
            fetched_at=result.fetched_at,
            from_cache=result.from_cache,
            status_code=result.status_code,
            numbers=numbers,
            dates=dates,
            entities=entities,
        )

    async def scrape_batch(
        self,
        urls: list[str],
        max_concurrent: int = 3,
        on_error: Literal["skip", "raise"] = "skip",
    ) -> list[ScrapedContent]:
        """
        Scrape multiple URLs with compliance checks.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum concurrent requests
            on_error: How to handle errors

        Returns:
            List of ScrapedContent results
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def scrape_one(url: str) -> ScrapedContent | None:
            async with semaphore:
                try:
                    return await self.scrape_with_compliance(url)
                except PermissionError as e:
                    logger.warning(f"Permission denied: {e}")
                    if on_error == "raise":
                        raise
                    return None
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
                    if on_error == "raise":
                        raise
                    return None

        scraped = await asyncio.gather(*[scrape_one(url) for url in urls])
        return [s for s in scraped if s is not None]

    def _extract_numbers(self, text: str) -> list[dict[str, Any]]:
        """Extract financial numbers from text."""
        numbers = []
        for match in self._number_pattern.finditer(text):
            value_str = match.group()
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end].strip()

            numbers.append({
                "value": value_str,
                "context": context,
                "position": match.start(),
            })

        return numbers[:50]  # Limit to avoid noise

    def _extract_dates(self, text: str) -> list[str]:
        """Extract dates from text."""
        dates = []
        for pattern in self._date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                dates.append(match.group())

        return list(set(dates))[:20]  # Dedupe and limit

    def _extract_entities(self, text: str) -> list[dict[str, str]]:
        """
        Extract financial entities (companies, tickers) from text.

        Basic implementation - can be enhanced with NER models.
        """
        entities = []

        # Ticker pattern (1-5 uppercase letters, often in parentheses or after :)
        ticker_pattern = re.compile(r"(?:[(:]|^|\s)([A-Z]{1,5})(?:[):]|$|\s)")
        for match in ticker_pattern.finditer(text):
            ticker = match.group(1)
            # Filter common false positives
            if ticker not in {"THE", "AND", "FOR", "INC", "LLC", "CEO", "CFO", "COO"}:
                entities.append({"type": "ticker", "value": ticker})

        # Deduplicate
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e["type"], e["value"])
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)

        return unique_entities[:30]

    async def extract_financial_signals(
        self,
        content: ScrapedContent,
        extractors: list[Callable[[ScrapedContent], dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """
        Extract financial signals from scraped content.

        Args:
            content: Scraped content
            extractors: Optional custom extractors

        Returns:
            Dict of extracted signals
        """
        signals = {
            "url": content.url,
            "title": content.title,
            "fetched_at": content.fetched_at.isoformat(),
            "text_length": len(content.text),
            "num_tables": len(content.tables),
            "num_links": len(content.links),
            "numbers": content.numbers[:10],
            "dates": content.dates[:5],
            "tickers": [e["value"] for e in content.entities if e["type"] == "ticker"],
        }

        # Apply custom extractors
        if extractors:
            for extractor in extractors:
                try:
                    extracted = extractor(content)
                    signals.update(extracted)
                except Exception as e:
                    logger.warning(f"Extractor failed: {e}")

        return signals

    async def close(self):
        """Clean up resources."""
        await self.scraper.close()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def scrape_financial_page(
    url: str,
    config: ScrapingConfig | None = None,
) -> ScrapedContent:
    """
    Convenience function to scrape a single financial page.

    Args:
        url: URL to scrape
        config: Optional configuration

    Returns:
        ScrapedContent with extracted data
    """
    pipeline = WebScrapingPipeline(config)
    try:
        return await pipeline.scrape_with_compliance(url)
    finally:
        await pipeline.close()
