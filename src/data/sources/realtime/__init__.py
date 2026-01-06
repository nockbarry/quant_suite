"""Real-time data sources for intraday trading.

Provides continuous monitoring of news, market data, and sentiment
during market hours.
"""

from .news_daemon import (
    NewsDaemon,
    NewsItem,
    NewsSummary,
)

__all__ = [
    "NewsDaemon",
    "NewsItem",
    "NewsSummary",
]
