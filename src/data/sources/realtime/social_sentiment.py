"""Social Sentiment Scraper - WallStreetBets and Reddit sentiment.

Scrapes social media sources for sentiment data:
- WallStreetBets trending tickers
- Reddit stock discussions
- Sentiment analysis

Integrates with TextCorpus for persistent storage.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Any
import json

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class RedditPost:
    """A Reddit post or comment."""

    id: str
    subreddit: str
    title: str
    text: str
    author: str
    score: int
    num_comments: int
    created_utc: datetime
    url: str
    symbols_mentioned: list[str] = field(default_factory=list)
    sentiment: str = "neutral"  # bullish, bearish, neutral
    sentiment_score: float = 0.0  # -1 to 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subreddit": self.subreddit,
            "title": self.title,
            "text": self.text,
            "author": self.author,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc.isoformat(),
            "url": self.url,
            "symbols_mentioned": self.symbols_mentioned,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RedditPost":
        return cls(
            id=data["id"],
            subreddit=data["subreddit"],
            title=data["title"],
            text=data["text"],
            author=data["author"],
            score=data["score"],
            num_comments=data["num_comments"],
            created_utc=datetime.fromisoformat(data["created_utc"]),
            url=data["url"],
            symbols_mentioned=data.get("symbols_mentioned", []),
            sentiment=data.get("sentiment", "neutral"),
            sentiment_score=data.get("sentiment_score", 0.0),
        )


@dataclass
class TrendingTicker:
    """A trending ticker from social media."""

    symbol: str
    mentions: int
    sentiment: str  # bullish, bearish, neutral
    sentiment_score: float  # -1 to 1
    change_24h: float  # Change in mentions vs. 24h ago
    top_posts: list[str]  # Post IDs

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "mentions": self.mentions,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "change_24h": self.change_24h,
            "top_posts": self.top_posts,
        }


@dataclass
class SocialSentimentSummary:
    """Summary of social sentiment."""

    timestamp: datetime
    source: str  # wallstreetbets, stocks, etc.
    trending_tickers: list[TrendingTicker]
    overall_sentiment: str  # bullish, bearish, neutral
    hot_topics: list[str]
    contrarian_signal: Optional[str]  # buy, sell when sentiment is extreme

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "trending_tickers": [t.to_dict() for t in self.trending_tickers],
            "overall_sentiment": self.overall_sentiment,
            "hot_topics": self.hot_topics,
            "contrarian_signal": self.contrarian_signal,
        }


class WallStreetBetsScraper:
    """
    Scrapes WallStreetBets for sentiment data.

    Uses Reddit's public JSON API (no auth required for public subreddits).
    """

    BASE_URL = "https://www.reddit.com"
    USER_AGENT = "quant_suite/1.0 (research bot)"

    # Common stock ticker pattern
    TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5})\b')

    # Exclude common words that look like tickers
    EXCLUDE_TICKERS = {
        "I", "A", "THE", "TO", "FOR", "AT", "BE", "IS", "IT", "OR", "ON", "IN",
        "SO", "AS", "IF", "BY", "DO", "GO", "HE", "ME", "MY", "NO", "OF", "UP",
        "US", "WE", "DD", "IMO", "CEO", "CFO", "EPS", "IPO", "ETF", "OTM", "ITM",
        "ATM", "PM", "AM", "WSB", "USA", "GDP", "SEC", "FED", "USD", "EU", "UK",
        "CEO", "ATH", "HOD", "LOD", "EOD", "AH", "PM", "YOLO", "FOMO", "FUD",
        "TA", "FA", "RSI", "SMA", "EMA", "MACD", "VWAP", "OI", "IV", "HV",
    }

    # Bullish/bearish keywords
    BULLISH_KEYWORDS = [
        "moon", "rocket", "calls", "long", "buy", "bull", "undervalued",
        "squeeze", "breakout", "gap up", "tendies", "diamond hands",
    ]
    BEARISH_KEYWORDS = [
        "puts", "short", "sell", "bear", "overvalued", "dump", "crash",
        "gap down", "paper hands", "bagholder", "rip",
    ]

    def __init__(self):
        """Initialize scraper."""
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if not HAS_HTTPX:
            raise ImportError("httpx required for social scraping")

        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.USER_AGENT},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_hot_posts(
        self,
        subreddit: str = "wallstreetbets",
        limit: int = 25,
    ) -> list[RedditPost]:
        """
        Get hot posts from a subreddit.

        Args:
            subreddit: Subreddit name
            limit: Number of posts to fetch

        Returns:
            List of RedditPost objects.
        """
        cache_key = f"hot_{subreddit}_{limit}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if (datetime.now() - cached_time).seconds < self._cache_ttl:
                return cached_data

        try:
            client = await self._get_client()
            url = f"{self.BASE_URL}/r/{subreddit}/hot.json"
            response = await client.get(url, params={"limit": limit})
            response.raise_for_status()
            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                post = self._parse_post(post_data, subreddit)
                posts.append(post)

            self._cache[cache_key] = (datetime.now(), posts)
            return posts

        except Exception as e:
            logger.error(f"Failed to fetch hot posts from r/{subreddit}: {e}")
            return []

    async def get_trending_tickers(
        self,
        subreddit: str = "wallstreetbets",
        limit: int = 50,
    ) -> list[TrendingTicker]:
        """
        Get trending tickers from a subreddit.

        Args:
            subreddit: Subreddit name
            limit: Number of posts to analyze

        Returns:
            List of TrendingTicker objects sorted by mentions.
        """
        posts = await self.get_hot_posts(subreddit, limit)

        # Count mentions
        ticker_mentions: dict[str, dict] = {}
        ticker_posts: dict[str, list[str]] = {}
        ticker_sentiments: dict[str, list[float]] = {}

        for post in posts:
            for symbol in post.symbols_mentioned:
                if symbol not in ticker_mentions:
                    ticker_mentions[symbol] = {"count": 0, "score_sum": 0}
                    ticker_posts[symbol] = []
                    ticker_sentiments[symbol] = []

                ticker_mentions[symbol]["count"] += 1
                ticker_mentions[symbol]["score_sum"] += post.score
                ticker_posts[symbol].append(post.id)
                ticker_sentiments[symbol].append(post.sentiment_score)

        # Build trending list
        trending = []
        for symbol, data in ticker_mentions.items():
            sentiments = ticker_sentiments[symbol]
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

            if avg_sentiment > 0.2:
                sentiment_label = "bullish"
            elif avg_sentiment < -0.2:
                sentiment_label = "bearish"
            else:
                sentiment_label = "neutral"

            trending.append(TrendingTicker(
                symbol=symbol,
                mentions=data["count"],
                sentiment=sentiment_label,
                sentiment_score=avg_sentiment,
                change_24h=0.0,  # Would need historical data
                top_posts=ticker_posts[symbol][:5],
            ))

        # Sort by mentions
        trending.sort(key=lambda x: x.mentions, reverse=True)
        return trending[:20]  # Top 20

    async def get_sentiment(self, symbol: str) -> dict:
        """
        Get sentiment for a specific symbol.

        Args:
            symbol: Stock ticker

        Returns:
            Dict with sentiment data.
        """
        posts = await self.get_hot_posts("wallstreetbets", 100)

        symbol_posts = [p for p in posts if symbol.upper() in p.symbols_mentioned]

        if not symbol_posts:
            return {
                "symbol": symbol,
                "mentions": 0,
                "sentiment": "unknown",
                "sentiment_score": 0.0,
                "sample_size": 0,
            }

        sentiments = [p.sentiment_score for p in symbol_posts]
        avg_sentiment = sum(sentiments) / len(sentiments)

        return {
            "symbol": symbol,
            "mentions": len(symbol_posts),
            "sentiment": "bullish" if avg_sentiment > 0.2 else "bearish" if avg_sentiment < -0.2 else "neutral",
            "sentiment_score": avg_sentiment,
            "sample_size": len(symbol_posts),
            "top_posts": [p.to_dict() for p in symbol_posts[:5]],
        }

    async def get_daily_summary(self) -> SocialSentimentSummary:
        """Get daily sentiment summary."""
        trending = await self.get_trending_tickers("wallstreetbets", 100)

        # Overall sentiment from top tickers
        if trending:
            avg_sentiment = sum(t.sentiment_score for t in trending[:10]) / min(10, len(trending))
            if avg_sentiment > 0.3:
                overall = "bullish"
                contrarian = "sell" if avg_sentiment > 0.5 else None
            elif avg_sentiment < -0.3:
                overall = "bearish"
                contrarian = "buy" if avg_sentiment < -0.5 else None
            else:
                overall = "neutral"
                contrarian = None
        else:
            overall = "unknown"
            contrarian = None

        # Hot topics from post titles
        posts = await self.get_hot_posts("wallstreetbets", 25)
        hot_topics = [p.title[:50] for p in posts[:5]]

        return SocialSentimentSummary(
            timestamp=datetime.now(),
            source="wallstreetbets",
            trending_tickers=trending,
            overall_sentiment=overall,
            hot_topics=hot_topics,
            contrarian_signal=contrarian,
        )

    def _parse_post(self, data: dict, subreddit: str) -> RedditPost:
        """Parse Reddit API response into RedditPost."""
        title = data.get("title", "")
        text = data.get("selftext", "")
        full_text = f"{title} {text}"

        # Extract tickers
        symbols = self._extract_tickers(full_text)

        # Analyze sentiment
        sentiment, score = self._analyze_sentiment(full_text)

        return RedditPost(
            id=data.get("id", ""),
            subreddit=subreddit,
            title=title,
            text=text[:1000],  # Truncate
            author=data.get("author", ""),
            score=data.get("score", 0),
            num_comments=data.get("num_comments", 0),
            created_utc=datetime.fromtimestamp(data.get("created_utc", 0)),
            url=f"https://reddit.com{data.get('permalink', '')}",
            symbols_mentioned=symbols,
            sentiment=sentiment,
            sentiment_score=score,
        )

    def _extract_tickers(self, text: str) -> list[str]:
        """Extract stock tickers from text."""
        matches = self.TICKER_PATTERN.findall(text)
        tickers = []
        for match in matches:
            if match not in self.EXCLUDE_TICKERS and len(match) >= 2:
                tickers.append(match)
        return list(set(tickers))[:10]  # Max 10 per post

    def _analyze_sentiment(self, text: str) -> tuple[str, float]:
        """Simple keyword-based sentiment analysis."""
        text_lower = text.lower()

        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text_lower)

        total = bullish_count + bearish_count
        if total == 0:
            return "neutral", 0.0

        score = (bullish_count - bearish_count) / total

        if score > 0.3:
            return "bullish", score
        if score < -0.3:
            return "bearish", score
        return "neutral", score


class SocialSentimentAggregator:
    """
    Aggregates social sentiment and integrates with TextCorpus.

    Fetches sentiment data and stores in text corpus for
    point-in-time safe research.
    """

    def __init__(self):
        """Initialize aggregator."""
        self.wsb_scraper = WallStreetBetsScraper()
        self.output_dir = paths.realtime_sentiment

    async def update_corpus(self) -> int:
        """
        Fetch social sentiment and add to text corpus.

        Returns:
            Number of documents added.
        """
        docs_added = 0

        try:
            # Get WSB summary
            summary = await self.wsb_scraper.get_daily_summary()

            # Save to output dir
            output_file = self.output_dir / f"social_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
            with open(output_file, "w") as f:
                json.dump(summary.to_dict(), f, indent=2)

            logger.info(f"Saved social sentiment to {output_file}")
            docs_added = 1

            # Optionally add to text corpus
            try:
                from src.text_research.corpus import TextCorpus, TextDocument

                corpus = TextCorpus()

                # Add summary as document
                doc = TextDocument(
                    text=json.dumps(summary.to_dict()),
                    timestamp=summary.timestamp,
                    source="social_sentiment",
                    symbols=[t.symbol for t in summary.trending_tickers[:10]],
                    metadata={
                        "overall_sentiment": summary.overall_sentiment,
                        "contrarian_signal": summary.contrarian_signal,
                    },
                )
                corpus.add_document(doc)
                docs_added += 1

            except ImportError:
                logger.debug("TextCorpus not available, skipping corpus integration")

        except Exception as e:
            logger.error(f"Failed to update social sentiment: {e}")

        return docs_added

    async def get_watchlist_sentiment(
        self,
        watchlist: list[str],
    ) -> dict[str, dict]:
        """
        Get sentiment for a watchlist of symbols.

        Args:
            watchlist: List of symbols

        Returns:
            Dict mapping symbol to sentiment data.
        """
        results = {}
        for symbol in watchlist:
            try:
                results[symbol] = await self.wsb_scraper.get_sentiment(symbol)
            except Exception as e:
                logger.warning(f"Failed to get sentiment for {symbol}: {e}")
                results[symbol] = {"symbol": symbol, "mentions": 0, "sentiment": "unknown"}

        return results

    async def close(self) -> None:
        """Clean up resources."""
        await self.wsb_scraper.close()


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Social Sentiment Scraper")
    parser.add_argument("--symbol", type=str, help="Get sentiment for symbol")
    parser.add_argument("--trending", action="store_true", help="Get trending tickers")
    parser.add_argument("--summary", action="store_true", help="Get daily summary")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    scraper = WallStreetBetsScraper()

    try:
        if args.symbol:
            result = await scraper.get_sentiment(args.symbol)
            print(json.dumps(result, indent=2))
        elif args.trending:
            trending = await scraper.get_trending_tickers()
            for t in trending[:10]:
                print(f"{t.symbol}: {t.mentions} mentions, {t.sentiment} ({t.sentiment_score:+.2f})")
        elif args.summary:
            summary = await scraper.get_daily_summary()
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            # Default: show summary
            summary = await scraper.get_daily_summary()
            print(f"\n=== WSB Daily Summary ===")
            print(f"Overall: {summary.overall_sentiment}")
            if summary.contrarian_signal:
                print(f"Contrarian Signal: {summary.contrarian_signal}")
            print(f"\nTop Trending:")
            for t in summary.trending_tickers[:10]:
                print(f"  ${t.symbol}: {t.mentions} mentions ({t.sentiment})")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
