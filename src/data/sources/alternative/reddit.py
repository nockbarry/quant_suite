"""Reddit data source for retail sentiment analysis.

Fetches posts and comments from trading-related subreddits for sentiment
analysis and contrarian strategies.

Supports:
- PRAW (Reddit API) for direct access
- Tradestie API for pre-aggregated WSB sentiment
- Historical data via Pushshift (when available)
"""

import asyncio
import hashlib
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)


# Words that look like tickers but aren't
TICKER_BLACKLIST = {
    # Common words
    "I", "A", "IT", "IS", "AT", "BE", "DO", "GO", "SO", "TO", "ON", "OR",
    "AN", "AS", "BY", "IF", "IN", "OF", "UP", "FOR", "THE", "ALL", "ARE",
    "HAS", "HIS", "HER", "NEW", "OLD", "NOW", "OUT", "OUR", "OWN", "SAY",
    "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "GET", "HIM", "HOW", "ITS",
    "LET", "MAY", "PUT", "SAW", "SHE", "TOO", "USE", "ANY", "CAN", "HAD",
    # Finance/Reddit terms
    "CEO", "CFO", "CTO", "COO", "IPO", "ETF", "NYSE", "SEC", "FDA", "FED",
    "DD", "FD", "YOLO", "FOMO", "IMO", "TL", "DR", "TLDR", "OP", "OG",
    "RN", "DM", "PM", "PSA", "FYI", "AMA", "ELI", "TIL", "IRL", "LOL",
    "LMAO", "ROFL", "STFU", "WTF", "IDK", "IMO", "IMHO", "TBH", "SMH",
    # Countries/regions
    "USA", "UK", "EU", "US", "UN", "NATO",
    # Tech terms
    "AI", "ML", "API", "GPU", "CPU", "RAM", "ROM", "USB", "PDF", "URL",
    # Reddit specific
    "WSB", "GME", "AMC", "HODL", "MOASS", "TENDIES", "APES", "APE",
    "MOON", "STONK", "STONKS", "BAGHOLDER", "DFV", "RC",
    # Common abbreviations that could be tickers
    "EPS", "PE", "PB", "ROE", "ROA", "ROI", "YOY", "QOQ", "MOM",
    "HIGH", "LOW", "OPEN", "CLOSE", "BUY", "SELL", "HOLD", "LONG", "SHORT",
}

# Common company name to ticker mapping
COMPANY_TO_TICKER = {
    "tesla": "TSLA",
    "apple": "AAPL",
    "amazon": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "gamestop": "GME",
    "amc": "AMC",
    "palantir": "PLTR",
    "nio": "NIO",
    "lucid": "LCID",
    "rivian": "RIVN",
    "coinbase": "COIN",
    "robinhood": "HOOD",
    "sofi": "SOFI",
    "paypal": "PYPL",
    "square": "SQ",
    "block": "SQ",
    "shopify": "SHOP",
    "zoom": "ZM",
    "peloton": "PTON",
    "snowflake": "SNOW",
    "crowdstrike": "CRWD",
    "datadog": "DDOG",
    "unity": "U",
    "roblox": "RBLX",
    "draftkings": "DKNG",
    "virgin galactic": "SPCE",
    "blackberry": "BB",
    "bed bath": "BBBY",
    "beyond": "BYND",
    "plug power": "PLUG",
    "fuel cell": "FCEL",
    "clover": "CLOV",
    "wish": "WISH",
    "tilray": "TLRY",
    "sundial": "SNDL",
    "spce": "SPCE",
}

# Bullish context words
BULLISH_WORDS = {
    "buy", "buying", "bought", "long", "calls", "call", "moon", "mooning",
    "rocket", "rockets", "squeeze", "squeezing", "bull", "bullish",
    "tendies", "gains", "gain", "profit", "profits", "up", "upside",
    "breakout", "breaking", "support", "strong", "pump", "pumping",
    "yolo", "all in", "diamond hands", "hodl", "hold", "holding",
    "undervalued", "cheap", "dip", "buying the dip", "btd",
}

# Bearish context words
BEARISH_WORDS = {
    "sell", "selling", "sold", "short", "puts", "put", "crash", "crashing",
    "dump", "dumping", "bear", "bearish", "loss", "losses", "down",
    "downside", "resistance", "weak", "overvalued", "expensive",
    "bubble", "correction", "drop", "dropping", "tank", "tanking",
    "bag", "bagholder", "bagholding", "rip", "dead", "dying",
    "paper hands", "paperhands", "fear", "panic",
}


@dataclass
class RedditPost:
    """Represents a Reddit post."""

    id: str
    subreddit: str
    title: str
    selftext: str
    author: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: datetime
    url: str
    is_self: bool
    link_flair_text: str | None
    mentioned_symbols: list[Symbol] = field(default_factory=list)
    awards_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def engagement_score(self) -> float:
        """Calculate engagement score combining upvotes and comments."""
        return self.score * (1 + math.log(1 + self.num_comments))

    @property
    def full_text(self) -> str:
        """Get combined title and body text."""
        return f"{self.title} {self.selftext}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "subreddit": self.subreddit,
            "title": self.title,
            "selftext": self.selftext,
            "author": self.author,
            "score": self.score,
            "upvote_ratio": self.upvote_ratio,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc.isoformat(),
            "url": self.url,
            "is_self": self.is_self,
            "link_flair_text": self.link_flair_text,
            "mentioned_symbols": self.mentioned_symbols,
            "engagement_score": self.engagement_score,
            "awards_count": self.awards_count,
            **self.metadata,
        }


@dataclass
class RedditComment:
    """Represents a Reddit comment."""

    id: str
    post_id: str
    author: str
    body: str
    score: int
    created_utc: datetime
    mentioned_symbols: list[Symbol] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "post_id": self.post_id,
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc.isoformat(),
            "mentioned_symbols": self.mentioned_symbols,
            **self.metadata,
        }


@dataclass
class SymbolMention:
    """Aggregated mentions for a symbol across Reddit."""

    symbol: Symbol
    mention_count: int
    total_score: int
    total_comments: int
    avg_sentiment: float | None
    bullish_count: int
    bearish_count: int
    neutral_count: int
    first_mention: datetime
    last_mention: datetime
    posts: list[RedditPost] = field(default_factory=list)

    @property
    def bullish_ratio(self) -> float:
        """Get ratio of bullish vs bearish mentions."""
        total = self.bullish_count + self.bearish_count
        if total == 0:
            return 0.5
        return self.bullish_count / total

    @property
    def trending_score(self) -> float:
        """Calculate trending score based on velocity and engagement."""
        if not self.posts:
            return 0.0

        # Time range in hours
        time_range = (self.last_mention - self.first_mention).total_seconds() / 3600
        if time_range < 1:
            time_range = 1

        # Mentions per hour * average engagement
        velocity = self.mention_count / time_range
        avg_engagement = self.total_score / max(1, self.mention_count)

        return velocity * math.log(1 + avg_engagement)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "mention_count": self.mention_count,
            "total_score": self.total_score,
            "total_comments": self.total_comments,
            "avg_sentiment": self.avg_sentiment,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "neutral_count": self.neutral_count,
            "bullish_ratio": self.bullish_ratio,
            "trending_score": self.trending_score,
            "first_mention": self.first_mention.isoformat(),
            "last_mention": self.last_mention.isoformat(),
        }


class SymbolExtractor:
    """
    Extract stock symbols from Reddit text.

    Handles:
    - $TICKER format (explicit)
    - TICKER format (context-aware)
    - Company name to ticker mapping
    - Filtering common words that look like tickers
    """

    def __init__(self, valid_symbols: set[str] | None = None):
        """
        Initialize symbol extractor.

        Args:
            valid_symbols: Set of valid tickers for validation (optional)
        """
        self.valid_symbols = valid_symbols
        self.blacklist = TICKER_BLACKLIST
        self.company_map = COMPANY_TO_TICKER

    def extract(self, text: str) -> list[tuple[str, int]]:
        """
        Extract symbols with mention counts.

        Args:
            text: Text to extract symbols from

        Returns:
            List of (symbol, count) tuples
        """
        if not text:
            return []

        text_upper = text.upper()
        text_lower = text.lower()
        symbol_counts: dict[str, int] = {}

        # Pattern 1: $TICKER format (most reliable)
        dollar_pattern = r'\$([A-Z]{1,5})\b'
        for match in re.finditer(dollar_pattern, text_upper):
            symbol = match.group(1)
            if symbol not in self.blacklist:
                if self.valid_symbols is None or symbol in self.valid_symbols:
                    symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

        # Pattern 2: Plain TICKER (all caps, word boundary)
        plain_pattern = r'\b([A-Z]{2,5})\b'
        for match in re.finditer(plain_pattern, text):  # Use original case
            symbol = match.group(1)
            if symbol.isupper() and symbol not in self.blacklist:
                if self.valid_symbols is None or symbol in self.valid_symbols:
                    # Lower weight for non-$ mentions
                    symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

        # Pattern 3: Company name mapping
        for company, ticker in self.company_map.items():
            if company in text_lower:
                symbol_counts[ticker] = symbol_counts.get(ticker, 0) + 1

        return sorted(symbol_counts.items(), key=lambda x: -x[1])

    def classify_sentiment(self, text: str, symbol: str) -> str:
        """
        Classify sentiment for a symbol mention based on context.

        Args:
            text: Text containing the mention
            symbol: Symbol to classify

        Returns:
            "bullish", "bearish", or "neutral"
        """
        text_lower = text.lower()

        # Find context window around symbol mention
        symbol_lower = symbol.lower()
        positions = []

        # Find all positions of symbol mention
        for match in re.finditer(rf'\b{re.escape(symbol)}\b', text, re.IGNORECASE):
            positions.append(match.start())
        for match in re.finditer(rf'\${re.escape(symbol)}\b', text, re.IGNORECASE):
            positions.append(match.start())

        if not positions:
            # Check whole text if no specific mention found
            context = text_lower
        else:
            # Get context window around mentions (50 chars each side)
            contexts = []
            for pos in positions:
                start = max(0, pos - 50)
                end = min(len(text), pos + len(symbol) + 50)
                contexts.append(text_lower[start:end])
            context = " ".join(contexts)

        # Count sentiment words
        bullish_count = sum(1 for word in BULLISH_WORDS if word in context)
        bearish_count = sum(1 for word in BEARISH_WORDS if word in context)

        if bullish_count > bearish_count:
            return "bullish"
        elif bearish_count > bullish_count:
            return "bearish"
        else:
            return "neutral"


class RedditDataSource:
    """
    Reddit data source for retail sentiment.

    Supports multiple access methods:
    - PRAW (Reddit API - requires credentials)
    - Tradestie API (free, rate-limited)
    """

    name = "reddit"

    # Target subreddits for trading sentiment
    TRADING_SUBREDDITS = [
        "wallstreetbets",
        "stocks",
        "investing",
        "options",
        "stockmarket",
        "pennystocks",
        "smallstreetbets",
        "superstonk",
        "thetagang",
        "dividends",
    ]

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str = "QuantSuite/1.0",
        subreddits: list[str] | None = None,
        cache_ttl_minutes: int = 5,
        valid_symbols: set[str] | None = None,
    ):
        """
        Initialize Reddit data source.

        Args:
            client_id: Reddit API client ID (for PRAW)
            client_secret: Reddit API client secret (for PRAW)
            user_agent: User agent string
            subreddits: List of subreddits to monitor
            cache_ttl_minutes: Cache TTL in minutes
            valid_symbols: Set of valid symbols for filtering
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.subreddits = subreddits or self.TRADING_SUBREDDITS
        self.cache_ttl_minutes = cache_ttl_minutes

        self.extractor = SymbolExtractor(valid_symbols)
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._praw = None

    def _init_praw(self) -> Any:
        """Initialize PRAW if credentials available."""
        if self._praw is not None:
            return self._praw

        if self.client_id and self.client_secret:
            try:
                import praw

                self._praw = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent,
                )
                return self._praw
            except ImportError:
                logger.warning("PRAW not installed, using Tradestie API")
        return None

    def _check_cache(self, key: str) -> Any | None:
        """Check if cached data is still valid."""
        if key in self._cache:
            cached_time, data = self._cache[key]
            if datetime.now() - cached_time < timedelta(minutes=self.cache_ttl_minutes):
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache with new data."""
        self._cache[key] = (datetime.now(), data)

    async def fetch_hot_posts(
        self,
        subreddit: str,
        limit: int = 100,
    ) -> list[RedditPost]:
        """
        Fetch hot posts from subreddit.

        Args:
            subreddit: Subreddit name
            limit: Maximum posts to fetch

        Returns:
            List of RedditPost objects
        """
        cache_key = f"hot:{subreddit}:{limit}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        posts = []

        # Try PRAW first
        praw = self._init_praw()
        if praw:
            try:
                sub = praw.subreddit(subreddit)
                for submission in sub.hot(limit=limit):
                    symbols = self.extractor.extract(
                        f"{submission.title} {submission.selftext}"
                    )
                    post = RedditPost(
                        id=submission.id,
                        subreddit=subreddit,
                        title=submission.title,
                        selftext=submission.selftext or "",
                        author=str(submission.author) if submission.author else "[deleted]",
                        score=submission.score,
                        upvote_ratio=submission.upvote_ratio,
                        num_comments=submission.num_comments,
                        created_utc=datetime.fromtimestamp(submission.created_utc),
                        url=submission.url,
                        is_self=submission.is_self,
                        link_flair_text=submission.link_flair_text,
                        mentioned_symbols=[s for s, _ in symbols],
                        awards_count=submission.total_awards_received,
                    )
                    posts.append(post)
            except Exception as e:
                logger.warning(f"PRAW error for r/{subreddit}: {e}")

        # Fallback: Use Reddit JSON API (no auth needed for public data)
        if not posts:
            posts = await self._fetch_via_json_api(subreddit, "hot", limit)

        self._update_cache(cache_key, posts)
        return posts

    async def fetch_new_posts(
        self,
        subreddit: str,
        limit: int = 100,
    ) -> list[RedditPost]:
        """
        Fetch new posts from subreddit.

        Args:
            subreddit: Subreddit name
            limit: Maximum posts to fetch

        Returns:
            List of RedditPost objects
        """
        cache_key = f"new:{subreddit}:{limit}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        posts = await self._fetch_via_json_api(subreddit, "new", limit)
        self._update_cache(cache_key, posts)
        return posts

    async def _fetch_via_json_api(
        self,
        subreddit: str,
        sort: str,
        limit: int,
    ) -> list[RedditPost]:
        """Fetch posts using Reddit's JSON API (no auth needed)."""
        posts = []
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params={"limit": limit},
                    headers={"User-Agent": self.user_agent},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                for child in data.get("data", {}).get("children", []):
                    post_data = child.get("data", {})
                    text = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
                    symbols = self.extractor.extract(text)

                    post = RedditPost(
                        id=post_data.get("id", ""),
                        subreddit=subreddit,
                        title=post_data.get("title", ""),
                        selftext=post_data.get("selftext", ""),
                        author=post_data.get("author", "[deleted]"),
                        score=post_data.get("score", 0),
                        upvote_ratio=post_data.get("upvote_ratio", 0.5),
                        num_comments=post_data.get("num_comments", 0),
                        created_utc=datetime.fromtimestamp(post_data.get("created_utc", 0)),
                        url=post_data.get("url", ""),
                        is_self=post_data.get("is_self", False),
                        link_flair_text=post_data.get("link_flair_text"),
                        mentioned_symbols=[s for s, _ in symbols],
                        awards_count=post_data.get("total_awards_received", 0),
                    )
                    posts.append(post)

            except Exception as e:
                logger.warning(f"JSON API error for r/{subreddit}: {e}")

        return posts

    async def fetch_posts_for_symbol(
        self,
        symbol: Symbol,
        subreddits: list[str] | None = None,
        limit_per_sub: int = 50,
    ) -> list[RedditPost]:
        """
        Fetch posts mentioning a specific symbol.

        Args:
            symbol: Stock symbol to search for
            subreddits: Subreddits to search (default: all trading subs)
            limit_per_sub: Max posts per subreddit

        Returns:
            List of posts mentioning the symbol
        """
        subreddits = subreddits or self.subreddits
        all_posts = []

        for sub in subreddits:
            posts = await self.fetch_hot_posts(sub, limit_per_sub)
            for post in posts:
                if symbol in post.mentioned_symbols:
                    all_posts.append(post)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        return all_posts

    async def aggregate_symbol_mentions(
        self,
        subreddits: list[str] | None = None,
        hours_back: int = 24,
        min_mentions: int = 2,
    ) -> dict[Symbol, SymbolMention]:
        """
        Aggregate symbol mentions across subreddits.

        Args:
            subreddits: Subreddits to scan
            hours_back: How far back to look
            min_mentions: Minimum mentions to include

        Returns:
            Dict mapping symbols to SymbolMention objects
        """
        subreddits = subreddits or self.subreddits
        cutoff = datetime.now() - timedelta(hours=hours_back)

        # Collect all posts
        all_posts: list[RedditPost] = []
        for sub in subreddits:
            posts = await self.fetch_hot_posts(sub, 100)
            all_posts.extend([p for p in posts if p.created_utc > cutoff])
            await asyncio.sleep(0.3)

        # Aggregate by symbol
        symbol_data: dict[Symbol, dict] = {}

        for post in all_posts:
            for symbol in post.mentioned_symbols:
                if symbol not in symbol_data:
                    symbol_data[symbol] = {
                        "mention_count": 0,
                        "total_score": 0,
                        "total_comments": 0,
                        "bullish": 0,
                        "bearish": 0,
                        "neutral": 0,
                        "first_mention": post.created_utc,
                        "last_mention": post.created_utc,
                        "posts": [],
                    }

                data = symbol_data[symbol]
                data["mention_count"] += 1
                data["total_score"] += post.score
                data["total_comments"] += post.num_comments
                data["posts"].append(post)

                # Classify sentiment
                sentiment = self.extractor.classify_sentiment(post.full_text, symbol)
                data[sentiment] += 1

                # Update time range
                if post.created_utc < data["first_mention"]:
                    data["first_mention"] = post.created_utc
                if post.created_utc > data["last_mention"]:
                    data["last_mention"] = post.created_utc

        # Create SymbolMention objects
        mentions = {}
        for symbol, data in symbol_data.items():
            if data["mention_count"] >= min_mentions:
                mentions[symbol] = SymbolMention(
                    symbol=symbol,
                    mention_count=data["mention_count"],
                    total_score=data["total_score"],
                    total_comments=data["total_comments"],
                    avg_sentiment=None,  # Can be computed with SentimentAnalyzer
                    bullish_count=data["bullish"],
                    bearish_count=data["bearish"],
                    neutral_count=data["neutral"],
                    first_mention=data["first_mention"],
                    last_mention=data["last_mention"],
                    posts=data["posts"],
                )

        return mentions

    async def get_trending_symbols(
        self,
        top_n: int = 20,
        hours_back: int = 24,
    ) -> list[SymbolMention]:
        """
        Get trending symbols by mention velocity and engagement.

        Args:
            top_n: Number of top symbols to return
            hours_back: Time window

        Returns:
            List of SymbolMention sorted by trending score
        """
        mentions = await self.aggregate_symbol_mentions(hours_back=hours_back)

        # Sort by trending score
        sorted_mentions = sorted(
            mentions.values(),
            key=lambda x: x.trending_score,
            reverse=True,
        )

        return sorted_mentions[:top_n]

    def to_dataframe(
        self,
        posts: list[RedditPost],
    ) -> pd.DataFrame:
        """
        Convert posts to DataFrame.

        Args:
            posts: List of RedditPost objects

        Returns:
            DataFrame with post data
        """
        records = [post.to_dict() for post in posts]
        df = pd.DataFrame(records)
        if not df.empty and "created_utc" in df.columns:
            df["created_utc"] = pd.to_datetime(df["created_utc"])
            df = df.set_index("created_utc").sort_index()
        return df


class TradestieAPI:
    """
    Tradestie API wrapper for pre-aggregated WSB sentiment.

    Free API providing:
    - Top mentioned stocks on WSB
    - Sentiment analysis (bullish/bearish)
    - Rate limited to 20 requests/minute
    """

    BASE_URL = "https://tradestie.com/api/v1/apps/reddit"

    def __init__(self, cache_ttl_minutes: int = 15):
        """
        Initialize Tradestie API.

        Args:
            cache_ttl_minutes: Cache TTL
        """
        self.cache_ttl_minutes = cache_ttl_minutes
        self._cache: dict[str, tuple[datetime, Any]] = {}

    def _check_cache(self, key: str) -> Any | None:
        """Check cache."""
        if key in self._cache:
            cached_time, data = self._cache[key]
            if datetime.now() - cached_time < timedelta(minutes=self.cache_ttl_minutes):
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache."""
        self._cache[key] = (datetime.now(), data)

    async def get_wsb_mentions(
        self,
        limit: int = 50,
    ) -> list[dict]:
        """
        Get top WSB mentioned stocks.

        Returns:
            List of dicts with ticker, comments, sentiment, sentiment_score
        """
        cache_key = f"wsb_mentions:{limit}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.BASE_URL, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                # Filter and sort
                mentions = data[:limit] if isinstance(data, list) else []
                self._update_cache(cache_key, mentions)
                return mentions

            except Exception as e:
                logger.warning(f"Tradestie API error: {e}")
                return []

    async def get_stock_sentiment(
        self,
        symbol: str,
    ) -> dict | None:
        """
        Get sentiment for a specific stock.

        Args:
            symbol: Stock ticker

        Returns:
            Dict with sentiment data or None
        """
        mentions = await self.get_wsb_mentions(limit=100)

        for mention in mentions:
            if mention.get("ticker", "").upper() == symbol.upper():
                return mention

        return None


# Convenience functions


async def fetch_reddit_sentiment(
    symbols: list[Symbol] | None = None,
    subreddits: list[str] | None = None,
    hours_back: int = 24,
    min_mentions: int = 2,
) -> dict[Symbol, SymbolMention]:
    """
    Fetch Reddit sentiment for symbols.

    Args:
        symbols: Specific symbols to fetch (None = all trending)
        subreddits: Subreddits to scan
        hours_back: Time window
        min_mentions: Minimum mentions to include

    Returns:
        Dict mapping symbols to SymbolMention objects
    """
    source = RedditDataSource()
    mentions = await source.aggregate_symbol_mentions(
        subreddits=subreddits,
        hours_back=hours_back,
        min_mentions=min_mentions,
    )

    if symbols:
        return {s: m for s, m in mentions.items() if s in symbols}
    return mentions


async def fetch_wsb_trending(top_n: int = 20) -> list[dict]:
    """
    Fetch trending WSB stocks via Tradestie API.

    Args:
        top_n: Number of stocks to return

    Returns:
        List of trending stocks with sentiment
    """
    api = TradestieAPI()
    return await api.get_wsb_mentions(limit=top_n)
