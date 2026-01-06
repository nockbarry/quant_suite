"""Real-time news monitoring daemon for intraday trading.

Provides continuous news monitoring during market hours with:
- Multiple source aggregation (Yahoo RSS, Finviz, SEC EDGAR)
- Portfolio-relevant filtering
- Sentiment analysis
- Automatic file output for LLM consumption

Usage:
    from src.data.sources.realtime import NewsDaemon
    from src.core.paths import paths

    daemon = NewsDaemon(
        watchlist=['SLB', 'HAL', 'XLE'],
        output_dir=paths.realtime_news
    )

    # Single check
    summary = await daemon.check_news()

    # Continuous monitoring
    await daemon.start(interval_minutes=30)
    # ... later ...
    await daemon.stop()
"""

import asyncio
import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Common stock symbols to extract from text
STOCK_SYMBOLS = {
    # Major indices and ETFs
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'XLE', 'XLF', 'XLK', 'XLV', 'XLI',
    'XLY', 'XLP', 'XLU', 'XLRE', 'XLB', 'XLC', 'GLD', 'SLV', 'USO', 'UNG',
    # Energy
    'XOM', 'CVX', 'SLB', 'HAL', 'BKR', 'OXY', 'COP', 'VLO', 'MPC', 'PSX',
    'EOG', 'PXD', 'DVN', 'FANG', 'HES',
    # Tech
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
    'INTC', 'CRM', 'ORCL', 'ADBE', 'NFLX', 'PYPL', 'SQ', 'SHOP', 'SNOW',
    # Finance
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'BLK', 'SCHW', 'AXP',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'TMO', 'ABT', 'BMY', 'AMGN',
    # Consumer
    'WMT', 'PG', 'KO', 'PEP', 'COST', 'MCD', 'NKE', 'SBUX', 'HD', 'LOW',
    # Industrials
    'CAT', 'DE', 'BA', 'GE', 'HON', 'UPS', 'UNP', 'LMT', 'RTX', 'MMM',
    # Travel
    'CCL', 'RCL', 'NCLH', 'UAL', 'DAL', 'AAL', 'LUV', 'MAR', 'HLT',
}


@dataclass
class NewsItem:
    """Single news article or update."""

    timestamp: datetime
    source: str
    headline: str
    summary: str
    symbols: list[str] = field(default_factory=list)
    sentiment: float | None = None  # -1 to 1
    priority: str = "NORMAL"  # BREAKING, HIGH, NORMAL, LOW
    url: str = ""
    relevance_score: float = 0.0  # 0-1, how relevant to portfolio
    article_id: str = ""

    def __post_init__(self):
        if not self.article_id:
            self.article_id = hashlib.md5(
                f"{self.url}{self.headline}{self.timestamp.isoformat()}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "article_id": self.article_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "headline": self.headline,
            "summary": self.summary,
            "symbols": self.symbols,
            "sentiment": self.sentiment,
            "priority": self.priority,
            "url": self.url,
            "relevance_score": self.relevance_score,
        }

    def format_console(self) -> str:
        """Format for console output."""
        symbol_str = f"[{', '.join(self.symbols)}]" if self.symbols else ""
        priority_emoji = {
            "BREAKING": "🚨",
            "HIGH": "⚠️",
            "NORMAL": "📰",
            "LOW": "ℹ️",
        }.get(self.priority, "📰")

        return (
            f"{priority_emoji} {self.timestamp.strftime('%H:%M')} "
            f"{symbol_str} {self.headline[:80]}..."
        )

    def get_summary(self) -> str:
        """Get human-readable summary for LLM."""
        lines = [
            f"[{self.timestamp.strftime('%H:%M ET')}] {self.headline}",
            f"  Source: {self.source} | Priority: {self.priority}",
        ]
        if self.symbols:
            lines.append(f"  Symbols: {', '.join(self.symbols)}")
        if self.sentiment is not None:
            sent_label = (
                "positive" if self.sentiment > 0.2
                else "negative" if self.sentiment < -0.2
                else "neutral"
            )
            lines.append(f"  Sentiment: {sent_label} ({self.sentiment:.2f})")
        if self.summary:
            lines.append(f"  Summary: {self.summary[:200]}...")
        return "\n".join(lines)


@dataclass
class NewsSummary:
    """Summary of news for a time period."""

    timestamp: datetime
    period_start: datetime
    period_end: datetime
    items: list[NewsItem] = field(default_factory=list)
    portfolio_relevant: list[NewsItem] = field(default_factory=list)
    sentiment_shift: float = 0.0
    key_themes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_items": len(self.items),
            "portfolio_relevant_count": len(self.portfolio_relevant),
            "sentiment_shift": self.sentiment_shift,
            "key_themes": self.key_themes,
            "items": [item.to_dict() for item in self.items],
            "portfolio_relevant": [item.to_dict() for item in self.portfolio_relevant],
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"NEWS SUMMARY - {self.timestamp.strftime('%H:%M ET')}",
            "=" * 50,
            f"Period: {self.period_start.strftime('%H:%M')} - {self.period_end.strftime('%H:%M')}",
            f"Total Items: {len(self.items)}",
            f"Portfolio Relevant: {len(self.portfolio_relevant)}",
        ]

        if self.sentiment_shift != 0:
            direction = "improved" if self.sentiment_shift > 0 else "worsened"
            lines.append(f"Sentiment: {direction} ({self.sentiment_shift:+.2f})")

        if self.key_themes:
            lines.append(f"\nKey Themes: {', '.join(self.key_themes)}")

        if self.portfolio_relevant:
            lines.append("\nPORTFOLIO-RELEVANT NEWS:")
            for item in self.portfolio_relevant[:5]:
                lines.append(item.format_console())

        if len(self.items) > len(self.portfolio_relevant):
            lines.append(f"\nOTHER MARKET NEWS ({len(self.items) - len(self.portfolio_relevant)}):")
            other = [i for i in self.items if i not in self.portfolio_relevant]
            for item in other[:3]:
                lines.append(item.format_console())

        return "\n".join(lines)


class NewsDaemon:
    """
    Real-time news monitoring daemon.

    Features:
    - Multiple source aggregation
    - Portfolio-relevant filtering
    - Continuous monitoring loop
    - File output for persistence
    - LLM-friendly summaries
    """

    def __init__(
        self,
        watchlist: list[str],
        output_dir: Path | None = None,
        cache_ttl_minutes: int = 15,
    ):
        """
        Initialize news daemon.

        Args:
            watchlist: Symbols to monitor (e.g., ['SLB', 'HAL', 'XLE'])
            output_dir: Directory for news files
            cache_ttl_minutes: Cache TTL for deduplication
        """
        self.watchlist = set(s.upper() for s in watchlist)
        self.output_dir = output_dir
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        # State
        self._running = False
        self._task: asyncio.Task | None = None
        self._seen_articles: dict[str, datetime] = {}  # article_id -> first_seen
        self._last_summary: NewsSummary | None = None
        self._all_items: list[NewsItem] = []
        self._previous_sentiment: float = 0.0

        # HTTP client
        self._client: httpx.AsyncClient | None = None

        # RSS feed URLs
        self._rss_feeds = {
            "yahoo_finance": "https://finance.yahoo.com/rss/",
            "seeking_alpha": "https://seekingalpha.com/feed.xml",
            "benzinga": "https://www.benzinga.com/feed",
            "reuters_business": "https://www.rss.reuters.com/rssFeed/businessNews",
        }

        # Keywords for sentiment analysis (simple rule-based)
        self._positive_keywords = {
            "surge", "soar", "rally", "gain", "rise", "jump", "beat",
            "upgrade", "buy", "bullish", "strong", "growth", "profit",
            "record", "breakthrough", "outperform", "positive", "up",
        }
        self._negative_keywords = {
            "fall", "drop", "plunge", "crash", "decline", "loss",
            "downgrade", "sell", "bearish", "weak", "cut", "miss",
            "warning", "concern", "risk", "down", "underperform", "negative",
        }

        logger.info(f"NewsDaemon initialized with watchlist: {self.watchlist}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; QuantSuite/1.0)"
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _extract_symbols(self, text: str) -> list[str]:
        """Extract stock symbols from text."""
        found = []
        text_upper = text.upper()

        # Check watchlist first (higher priority)
        for symbol in self.watchlist:
            if symbol in text_upper or f"${symbol}" in text_upper:
                found.append(symbol)

        # Check common symbols
        for symbol in STOCK_SYMBOLS:
            if symbol not in found:
                # Look for $SYMBOL or standalone SYMBOL
                if f"${symbol}" in text_upper or re.search(rf'\b{symbol}\b', text_upper):
                    found.append(symbol)

        return found[:10]  # Limit to 10 symbols

    def _analyze_sentiment(self, text: str) -> float:
        """Simple rule-based sentiment analysis (-1 to 1)."""
        text_lower = text.lower()
        positive_count = sum(1 for word in self._positive_keywords if word in text_lower)
        negative_count = sum(1 for word in self._negative_keywords if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return 0.0

        return (positive_count - negative_count) / total

    def _determine_priority(self, headline: str, symbols: list[str]) -> str:
        """Determine news priority."""
        headline_lower = headline.lower()

        # Breaking news indicators
        breaking_keywords = {"breaking", "urgent", "just in", "alert"}
        if any(kw in headline_lower for kw in breaking_keywords):
            return "BREAKING"

        # High priority if it mentions watchlist symbols
        if any(s in self.watchlist for s in symbols):
            return "HIGH"

        # High priority for major events
        high_keywords = {"fed", "fomc", "earnings", "gdp", "jobs", "inflation", "recession"}
        if any(kw in headline_lower for kw in high_keywords):
            return "HIGH"

        return "NORMAL"

    def _calculate_relevance(self, symbols: list[str]) -> float:
        """Calculate relevance to portfolio (0-1)."""
        if not symbols:
            return 0.0

        watchlist_matches = sum(1 for s in symbols if s in self.watchlist)
        if watchlist_matches > 0:
            return min(1.0, 0.5 + (watchlist_matches * 0.2))

        # Related sectors get some relevance
        energy_symbols = {'XOM', 'CVX', 'SLB', 'HAL', 'BKR', 'OXY', 'COP', 'VLO', 'XLE'}
        if any(s in energy_symbols for s in symbols):
            if any(s in energy_symbols for s in self.watchlist):
                return 0.3

        return 0.1

    def _is_duplicate(self, article_id: str) -> bool:
        """Check if article was already seen."""
        if article_id in self._seen_articles:
            return True

        # Clean old entries
        cutoff = datetime.now() - self.cache_ttl
        self._seen_articles = {
            k: v for k, v in self._seen_articles.items() if v > cutoff
        }

        self._seen_articles[article_id] = datetime.now()
        return False

    async def _fetch_rss(self, url: str, source: str) -> list[NewsItem]:
        """Fetch news from RSS feed."""
        items = []
        try:
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()

            root = ET.fromstring(response.text)

            # Handle different RSS formats
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")
                pubdate_elem = item.find("pubDate")

                if title_elem is None:
                    continue

                headline = title_elem.text or ""
                url_str = link_elem.text if link_elem is not None else ""
                summary = desc_elem.text if desc_elem is not None else ""

                # Parse date
                timestamp = datetime.now()
                if pubdate_elem is not None and pubdate_elem.text:
                    try:
                        # Handle common RSS date formats
                        timestamp = datetime.strptime(
                            pubdate_elem.text.strip()[:25],
                            "%a, %d %b %Y %H:%M:%S"
                        )
                    except ValueError:
                        pass

                # Extract symbols and analyze
                symbols = self._extract_symbols(headline + " " + (summary or ""))
                sentiment = self._analyze_sentiment(headline + " " + (summary or ""))
                priority = self._determine_priority(headline, symbols)
                relevance = self._calculate_relevance(symbols)

                news_item = NewsItem(
                    timestamp=timestamp,
                    source=source,
                    headline=headline,
                    summary=summary[:500] if summary else "",
                    symbols=symbols,
                    sentiment=sentiment,
                    priority=priority,
                    url=url_str,
                    relevance_score=relevance,
                )

                if not self._is_duplicate(news_item.article_id):
                    items.append(news_item)

        except Exception as e:
            logger.warning(f"Failed to fetch RSS from {source}: {e}")

        return items

    async def _fetch_finviz_news(self, symbol: str) -> list[NewsItem]:
        """Fetch news from Finviz for a specific symbol."""
        items = []
        url = f"https://finviz.com/quote.ashx?t={symbol}"

        try:
            client = await self._get_client()
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )

            if response.status_code == 200:
                # Parse news table (simplified - real implementation would use BeautifulSoup)
                content = response.text

                # Look for news links in the page
                news_pattern = r'<a[^>]+class="tab-link-news"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
                matches = re.findall(news_pattern, content, re.IGNORECASE)

                for url_match, headline in matches[:5]:  # Limit to 5
                    symbols = [symbol]
                    sentiment = self._analyze_sentiment(headline)
                    priority = self._determine_priority(headline, symbols)
                    relevance = self._calculate_relevance(symbols)

                    news_item = NewsItem(
                        timestamp=datetime.now(),
                        source="finviz",
                        headline=headline,
                        summary="",
                        symbols=symbols,
                        sentiment=sentiment,
                        priority=priority,
                        url=url_match if url_match.startswith("http") else f"https://finviz.com{url_match}",
                        relevance_score=relevance,
                    )

                    if not self._is_duplicate(news_item.article_id):
                        items.append(news_item)

        except Exception as e:
            logger.warning(f"Failed to fetch Finviz news for {symbol}: {e}")

        return items

    async def _fetch_sec_filings(self) -> list[NewsItem]:
        """Fetch recent SEC 8-K filings for watchlist."""
        items = []

        for symbol in list(self.watchlist)[:5]:  # Limit API calls
            try:
                # SEC EDGAR company search
                search_url = f"https://efts.sec.gov/LATEST/search-index?q={symbol}&dateRange=1d&forms=8-K"
                client = await self._get_client()

                # Note: Real implementation would use proper SEC API
                # This is simplified for demonstration
                response = await client.get(
                    search_url,
                    headers={"Accept": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    hits = data.get("hits", {}).get("hits", [])

                    for hit in hits[:2]:  # Limit per symbol
                        source_data = hit.get("_source", {})
                        form_type = source_data.get("form", "8-K")
                        filing_date = source_data.get("file_date", "")

                        news_item = NewsItem(
                            timestamp=datetime.now(),
                            source="sec_edgar",
                            headline=f"{symbol}: New {form_type} Filing",
                            summary=f"SEC {form_type} filing detected",
                            symbols=[symbol],
                            sentiment=0.0,  # Neutral for filings
                            priority="HIGH",  # SEC filings are important
                            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=8-K",
                            relevance_score=1.0,
                        )

                        if not self._is_duplicate(news_item.article_id):
                            items.append(news_item)

            except Exception as e:
                logger.debug(f"SEC fetch for {symbol}: {e}")

        return items

    def _identify_themes(self, items: list[NewsItem]) -> list[str]:
        """Identify key themes from news items."""
        theme_keywords = {
            "Venezuela": ["venezuela", "maduro", "caracas", "pdvsa"],
            "Fed Policy": ["fed", "fomc", "powell", "rate", "monetary"],
            "Earnings": ["earnings", "eps", "revenue", "beat", "miss"],
            "Energy": ["oil", "crude", "opec", "drilling", "refinery"],
            "Tech": ["ai", "artificial intelligence", "cloud", "semiconductor"],
            "Geopolitical": ["war", "conflict", "sanctions", "tariff"],
            "Economic Data": ["jobs", "employment", "gdp", "inflation", "cpi"],
            "M&A": ["merger", "acquisition", "buyout", "deal"],
        }

        all_text = " ".join(
            (item.headline + " " + item.summary).lower()
            for item in items
        )

        themes = []
        for theme, keywords in theme_keywords.items():
            if any(kw in all_text for kw in keywords):
                themes.append(theme)

        return themes[:5]  # Limit themes

    async def check_news(self) -> NewsSummary:
        """
        Run a single news check cycle.

        Returns:
            NewsSummary with all fetched news
        """
        period_start = datetime.now()
        all_items: list[NewsItem] = []

        # Fetch from RSS feeds
        fetch_tasks = []
        for source, url in self._rss_feeds.items():
            fetch_tasks.append(self._fetch_rss(url, source))

        # Fetch from Finviz for watchlist
        for symbol in list(self.watchlist)[:5]:
            fetch_tasks.append(self._fetch_finviz_news(symbol))

        # Fetch SEC filings
        fetch_tasks.append(self._fetch_sec_filings())

        # Execute all fetches concurrently
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Fetch error: {result}")

        # Sort by timestamp (newest first)
        all_items.sort(key=lambda x: x.timestamp, reverse=True)

        # Filter portfolio-relevant items
        portfolio_relevant = [
            item for item in all_items
            if item.relevance_score >= 0.3 or any(s in self.watchlist for s in item.symbols)
        ]

        # Calculate sentiment shift
        if all_items:
            current_sentiment = sum(
                item.sentiment or 0 for item in all_items
            ) / len(all_items)
            sentiment_shift = current_sentiment - self._previous_sentiment
            self._previous_sentiment = current_sentiment
        else:
            sentiment_shift = 0.0

        # Identify themes
        themes = self._identify_themes(all_items)

        period_end = datetime.now()

        summary = NewsSummary(
            timestamp=datetime.now(),
            period_start=period_start,
            period_end=period_end,
            items=all_items,
            portfolio_relevant=portfolio_relevant,
            sentiment_shift=sentiment_shift,
            key_themes=themes,
        )

        self._last_summary = summary
        self._all_items.extend(all_items)

        # Save to file if output_dir configured
        if self.output_dir:
            await self._save_summary(summary)

        logger.info(
            f"News check complete: {len(all_items)} items, "
            f"{len(portfolio_relevant)} portfolio-relevant"
        )

        return summary

    async def _save_summary(self, summary: NewsSummary) -> None:
        """Save news summary to file."""
        try:
            # Create date-based subdirectory
            date_str = summary.timestamp.strftime("%Y-%m-%d")
            date_dir = self.output_dir / date_str
            date_dir.mkdir(parents=True, exist_ok=True)

            # Save timestamped file
            time_str = summary.timestamp.strftime("%H%M")
            filename = date_dir / f"news_{time_str}.json"

            with open(filename, "w") as f:
                json.dump(summary.to_dict(), f, indent=2)

            logger.debug(f"Saved news summary to {filename}")

        except Exception as e:
            logger.error(f"Failed to save news summary: {e}")

    async def start(self, interval_minutes: int = 30) -> None:
        """
        Start continuous news monitoring.

        Args:
            interval_minutes: Minutes between checks (default 30)
        """
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(interval_minutes))
        logger.info(f"Started news daemon (interval: {interval_minutes}m)")

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self.close()
        logger.info("Stopped news daemon")

    async def _monitor_loop(self, interval_minutes: int) -> None:
        """Main monitoring loop."""
        interval_seconds = interval_minutes * 60

        while self._running:
            try:
                await self.check_news()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"News daemon error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    def get_latest(self) -> NewsSummary | None:
        """Get most recent news summary."""
        return self._last_summary

    def get_portfolio_alerts(self) -> list[NewsItem]:
        """Get high-priority items for current positions."""
        if not self._last_summary:
            return []

        return [
            item for item in self._last_summary.portfolio_relevant
            if item.priority in ("BREAKING", "HIGH")
        ]

    def search(self, query: str, hours_back: int = 24) -> list[NewsItem]:
        """
        Search historical news items.

        Args:
            query: Search query
            hours_back: How far back to search

        Returns:
            Matching news items
        """
        cutoff = datetime.now() - timedelta(hours=hours_back)
        query_lower = query.lower()

        return [
            item for item in self._all_items
            if item.timestamp > cutoff
            and (
                query_lower in item.headline.lower()
                or query_lower in item.summary.lower()
                or query_lower.upper() in item.symbols
            )
        ]

    def get_summary_for_llm(self) -> str:
        """Get formatted summary for LLM consumption."""
        if self._last_summary:
            return self._last_summary.get_summary()
        return "No news data available. Run check_news() first."

    async def save_daily_summary(self) -> Path | None:
        """Save end-of-day news compilation."""
        if not self.output_dir or not self._all_items:
            return None

        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            date_dir = self.output_dir / date_str
            date_dir.mkdir(parents=True, exist_ok=True)

            filename = date_dir / "daily_summary.json"

            # Filter to today's items
            today = datetime.now().date()
            today_items = [
                item for item in self._all_items
                if item.timestamp.date() == today
            ]

            portfolio_items = [
                item for item in today_items
                if item.relevance_score >= 0.3
            ]

            summary_data = {
                "date": date_str,
                "total_items": len(today_items),
                "portfolio_relevant": len(portfolio_items),
                "themes": self._identify_themes(today_items),
                "items": [item.to_dict() for item in today_items],
                "portfolio_items": [item.to_dict() for item in portfolio_items],
            }

            with open(filename, "w") as f:
                json.dump(summary_data, f, indent=2)

            logger.info(f"Saved daily news summary to {filename}")
            return filename

        except Exception as e:
            logger.error(f"Failed to save daily summary: {e}")
            return None
