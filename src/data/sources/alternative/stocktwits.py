#!/usr/bin/env python3
"""Stocktwits Integration - Track stock sentiment from Stocktwits.

Provides:
- Symbol stream monitoring
- Sentiment analysis
- Message volume tracking
- Trending stocks detection

API: Public Stocktwits API (no auth required for basic access)
Rate Limit: 200 requests/hour
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

import requests

from .social_timeseries import get_social_timeseries

logger = logging.getLogger(__name__)


@dataclass
class StocktwitsMessage:
    """A single Stocktwits message."""
    message_id: str
    symbol: str
    body: str
    created_at: datetime
    sentiment: Optional[str]  # Bullish, Bearish, or None
    user_name: str
    user_followers: int
    likes: int
    reshares: int

    @property
    def sentiment_score(self) -> float:
        """Convert sentiment to numeric score."""
        if self.sentiment == "Bullish":
            return 1.0
        elif self.sentiment == "Bearish":
            return -1.0
        return 0.0

    @property
    def engagement(self) -> int:
        """Total engagement."""
        return self.likes + self.reshares

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "symbol": self.symbol,
            "body": self.body[:200],
            "created_at": self.created_at.isoformat(),
            "sentiment": self.sentiment,
            "user_name": self.user_name,
            "user_followers": self.user_followers,
            "likes": self.likes,
            "reshares": self.reshares,
            "sentiment_score": self.sentiment_score,
            "engagement": self.engagement,
        }


@dataclass
class StocktwitsStreamStats:
    """Statistics for a symbol's Stocktwits stream."""
    symbol: str
    message_count: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    avg_sentiment: float
    total_likes: int
    watchers: int  # Number of people watching this stream

    @property
    def bullish_ratio(self) -> float:
        """Ratio of bullish to total sentiment messages."""
        sentiment_total = self.bullish_count + self.bearish_count
        if sentiment_total == 0:
            return 0.5
        return self.bullish_count / sentiment_total

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "message_count": self.message_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "neutral_count": self.neutral_count,
            "avg_sentiment": self.avg_sentiment,
            "bullish_ratio": self.bullish_ratio,
            "total_likes": self.total_likes,
            "watchers": self.watchers,
        }


class StocktwitsClient:
    """Client for Stocktwits API."""

    BASE_URL = "https://api.stocktwits.com/api/2"
    CACHE_PATH = paths.base / "social" / "stocktwits_cache.json"

    # Rate limiting
    REQUESTS_PER_HOUR = 200
    MIN_REQUEST_INTERVAL = 3600 / REQUESTS_PER_HOUR  # ~18 seconds

    def __init__(self):
        self._last_request_time = 0
        self._cache = {}
        self._load_cache()
        self.timeseries = get_social_timeseries()

    def _load_cache(self):
        """Load cached data."""
        if self.CACHE_PATH.exists():
            try:
                with open(self.CACHE_PATH) as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self):
        """Save cache to disk."""
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CACHE_PATH, "w") as f:
            json.dump(self._cache, f, indent=2)

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make API request with rate limiting."""
        self._rate_limit()

        url = f"{self.BASE_URL}/{endpoint}"
        # Use browser-like headers for better compatibility
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning("Stocktwits rate limit hit")
            elif e.response.status_code == 403:
                logger.warning(f"Stocktwits access denied for {endpoint} - API may require authentication")
            else:
                logger.error(f"Stocktwits API error: {e}")
        except Exception as e:
            logger.error(f"Stocktwits request failed: {e}")

        return None

    def get_symbol_stream(self, symbol: str, limit: int = 30) -> list[StocktwitsMessage]:
        """Get recent messages for a symbol."""
        data = self._make_request(f"streams/symbol/{symbol}.json", {"limit": limit})

        if not data or "messages" not in data:
            return []

        messages = []
        for msg in data.get("messages", []):
            try:
                sentiment = None
                entities = msg.get("entities", {})
                if entities and entities.get("sentiment"):
                    sentiment = entities["sentiment"].get("basic")

                user = msg.get("user", {})

                message = StocktwitsMessage(
                    message_id=str(msg.get("id", "")),
                    symbol=symbol,
                    body=msg.get("body", ""),
                    created_at=datetime.strptime(
                        msg.get("created_at", ""),
                        "%Y-%m-%dT%H:%M:%SZ"
                    ) if msg.get("created_at") else datetime.now(),
                    sentiment=sentiment,
                    user_name=user.get("username", ""),
                    user_followers=user.get("followers", 0),
                    likes=msg.get("likes", {}).get("total", 0),
                    reshares=msg.get("reshares", {}).get("reshared_count", 0),
                )
                messages.append(message)

                # Store in time series
                self.timeseries.add_mention(
                    symbol=symbol,
                    platform="stocktwits",
                    timestamp=message.created_at,
                    post_id=message.message_id,
                    sentiment=message.sentiment_score,
                    engagement=message.engagement,
                )
            except Exception as e:
                logger.debug(f"Could not parse message: {e}")

        return messages

    def get_symbol_stats(self, symbol: str) -> Optional[StocktwitsStreamStats]:
        """Get statistics for a symbol's stream."""
        messages = self.get_symbol_stream(symbol, limit=30)

        if not messages:
            return None

        bullish = sum(1 for m in messages if m.sentiment == "Bullish")
        bearish = sum(1 for m in messages if m.sentiment == "Bearish")
        neutral = len(messages) - bullish - bearish

        sentiment_messages = [m for m in messages if m.sentiment in ["Bullish", "Bearish"]]
        avg_sentiment = (
            sum(m.sentiment_score for m in sentiment_messages) / len(sentiment_messages)
            if sentiment_messages else 0
        )

        total_likes = sum(m.likes for m in messages)

        # Get watchers from symbol info
        symbol_data = self._make_request(f"streams/symbol/{symbol}.json")
        watchers = 0
        if symbol_data and "symbol" in symbol_data:
            watchers = symbol_data["symbol"].get("watchlist_count", 0)

        return StocktwitsStreamStats(
            symbol=symbol,
            message_count=len(messages),
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            avg_sentiment=avg_sentiment,
            total_likes=total_likes,
            watchers=watchers,
        )

    def get_trending(self) -> list[dict]:
        """Get trending stocks from Stocktwits."""
        data = self._make_request("trending/symbols.json")

        if not data or "symbols" not in data:
            return []

        trending = []
        for item in data.get("symbols", []):
            trending.append({
                "symbol": item.get("symbol", ""),
                "title": item.get("title", ""),
                "watchlist_count": item.get("watchlist_count", 0),
            })

        return trending

    def scan_symbols(self, symbols: list[str]) -> dict[str, StocktwitsStreamStats]:
        """Scan multiple symbols for sentiment."""
        results = {}

        for symbol in symbols:
            stats = self.get_symbol_stats(symbol)
            if stats:
                results[symbol] = stats

            # Update time series aggregates
            self.timeseries.update_daily_aggregates()

        return results

    def generate_report(self, symbols: list[str] = None) -> str:
        """Generate report of Stocktwits sentiment."""
        lines = [
            "STOCKTWITS SENTIMENT REPORT",
            "═" * 60,
            "",
        ]

        # Trending
        trending = self.get_trending()
        if trending:
            lines.append("TRENDING STOCKS")
            lines.append("─" * 40)
            for item in trending[:10]:
                lines.append(f"  {item['symbol']:6} | watchers: {item['watchlist_count']:,}")
            lines.append("")

        # Symbol stats
        if symbols:
            lines.append("SYMBOL SENTIMENT")
            lines.append("─" * 40)

            for symbol in symbols[:10]:
                stats = self.get_symbol_stats(symbol)
                if stats:
                    sentiment_icon = "📈" if stats.avg_sentiment > 0.2 else "📉" if stats.avg_sentiment < -0.2 else "➖"
                    lines.append(
                        f"  {sentiment_icon} {stats.symbol:6} | "
                        f"bull: {stats.bullish_ratio:.0%} | "
                        f"msgs: {stats.message_count} | "
                        f"likes: {stats.total_likes}"
                    )

        lines.extend(["", "═" * 60])
        return "\n".join(lines)


# Singleton instance
_stocktwits_client: Optional[StocktwitsClient] = None


def get_stocktwits_client() -> StocktwitsClient:
    """Get singleton instance."""
    global _stocktwits_client
    if _stocktwits_client is None:
        _stocktwits_client = StocktwitsClient()
    return _stocktwits_client


if __name__ == "__main__":
    client = StocktwitsClient()

    # Demo: Check trending and a few symbols
    print("Fetching trending...")
    trending = client.get_trending()
    print(f"Found {len(trending)} trending symbols")

    # Get sentiment for top trending
    if trending:
        top_symbols = [t["symbol"] for t in trending[:5]]
        print(client.generate_report(top_symbols))
