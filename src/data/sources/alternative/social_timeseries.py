#!/usr/bin/env python3
"""Social Time-Series Database - Track social mentions over time.

Provides:
- SQLite storage for social mention data
- Daily aggregation for trend analysis
- Mention velocity and momentum calculation
- Cross-platform signal consolidation

Used by:
- WSB Tracker
- Stocktwits integration
- Thesis suggester (for convergence detection)
"""

import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DailyMentionStats:
    """Daily aggregated mention statistics."""
    symbol: str
    date: str
    platform: str  # wsb, stocktwits, twitter
    mention_count: int
    avg_sentiment: float
    bullish_count: int
    bearish_count: int
    total_engagement: int  # upvotes + comments
    dd_count: int  # Due diligence posts


@dataclass
class MentionTrend:
    """Trend analysis for a symbol."""
    symbol: str
    platform: str
    current_daily_avg: float  # Last 3 days
    previous_daily_avg: float  # 4-7 days ago
    growth_rate: float  # Percentage change
    momentum_score: float  # Weighted recent activity
    trend_direction: str  # accelerating, stable, declining
    first_seen: str
    last_seen: str
    total_mentions: int


class SocialTimeSeries:
    """Manage time-series data for social mentions across platforms."""

    DB_PATH = Path.home() / "quant_results" / "social" / "social_timeseries.db"

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Raw mentions table (high resolution)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                platform TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                post_id TEXT UNIQUE,
                sentiment REAL,
                engagement INTEGER,
                is_dd INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily aggregates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_aggregates (
                symbol TEXT NOT NULL,
                platform TEXT NOT NULL,
                date TEXT NOT NULL,
                mention_count INTEGER DEFAULT 0,
                avg_sentiment REAL DEFAULT 0,
                bullish_count INTEGER DEFAULT 0,
                bearish_count INTEGER DEFAULT 0,
                total_engagement INTEGER DEFAULT 0,
                dd_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, platform, date)
            )
        """)

        # First seen tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS first_seen (
                symbol TEXT NOT NULL,
                platform TEXT NOT NULL,
                first_date TEXT NOT NULL,
                PRIMARY KEY (symbol, platform)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_symbol ON raw_mentions(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_timestamp ON raw_mentions(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_platform ON raw_mentions(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_aggregates(date)")

        conn.commit()
        conn.close()

    def add_mention(
        self,
        symbol: str,
        platform: str,
        timestamp: datetime,
        post_id: str,
        sentiment: float = 0.0,
        engagement: int = 0,
        is_dd: bool = False,
    ):
        """Add a single mention record."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO raw_mentions
                (symbol, platform, timestamp, post_id, sentiment, engagement, is_dd)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                platform,
                timestamp.isoformat(),
                post_id,
                sentiment,
                engagement,
                1 if is_dd else 0,
            ))

            # Update first seen
            cursor.execute("""
                INSERT OR IGNORE INTO first_seen (symbol, platform, first_date)
                VALUES (?, ?, ?)
            """, (symbol, platform, timestamp.strftime("%Y-%m-%d")))

            conn.commit()
        except Exception as e:
            logger.debug(f"Could not add mention: {e}")
        finally:
            conn.close()

    def update_daily_aggregates(self, date: str = None):
        """Update daily aggregate statistics."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Calculate aggregates for the date
        cursor.execute("""
            INSERT OR REPLACE INTO daily_aggregates
            (symbol, platform, date, mention_count, avg_sentiment, bullish_count, bearish_count, total_engagement, dd_count, updated_at)
            SELECT
                symbol,
                platform,
                date(timestamp) as date,
                COUNT(*) as mention_count,
                AVG(sentiment) as avg_sentiment,
                SUM(CASE WHEN sentiment > 0.2 THEN 1 ELSE 0 END) as bullish_count,
                SUM(CASE WHEN sentiment < -0.2 THEN 1 ELSE 0 END) as bearish_count,
                SUM(engagement) as total_engagement,
                SUM(is_dd) as dd_count,
                datetime('now')
            FROM raw_mentions
            WHERE date(timestamp) = ?
            GROUP BY symbol, platform
        """, (date,))

        conn.commit()
        conn.close()

    def get_daily_stats(
        self,
        symbol: str,
        platform: str = None,
        days: int = 30
    ) -> list[DailyMentionStats]:
        """Get daily mention statistics for a symbol."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        if platform:
            cursor.execute("""
                SELECT symbol, date, platform, mention_count, avg_sentiment,
                       bullish_count, bearish_count, total_engagement, dd_count
                FROM daily_aggregates
                WHERE symbol = ? AND platform = ? AND date >= ?
                ORDER BY date DESC
            """, (symbol, platform, cutoff))
        else:
            cursor.execute("""
                SELECT symbol, date, platform, mention_count, avg_sentiment,
                       bullish_count, bearish_count, total_engagement, dd_count
                FROM daily_aggregates
                WHERE symbol = ? AND date >= ?
                ORDER BY date DESC
            """, (symbol, cutoff))

        rows = cursor.fetchall()
        conn.close()

        return [
            DailyMentionStats(
                symbol=row[0],
                date=row[1],
                platform=row[2],
                mention_count=row[3],
                avg_sentiment=row[4] or 0,
                bullish_count=row[5] or 0,
                bearish_count=row[6] or 0,
                total_engagement=row[7] or 0,
                dd_count=row[8] or 0,
            )
            for row in rows
        ]

    def get_trend(self, symbol: str, platform: str = None) -> Optional[MentionTrend]:
        """Calculate trend metrics for a symbol."""
        stats = self.get_daily_stats(symbol, platform, days=14)

        if not stats:
            return None

        # Consolidate across platforms if not specified
        if platform is None:
            platform = "all"
            # Aggregate by date
            daily_totals = {}
            for stat in stats:
                if stat.date not in daily_totals:
                    daily_totals[stat.date] = 0
                daily_totals[stat.date] += stat.mention_count

            sorted_dates = sorted(daily_totals.keys(), reverse=True)
            recent_counts = [daily_totals[d] for d in sorted_dates[:3]]
            older_counts = [daily_totals[d] for d in sorted_dates[3:7]]
        else:
            sorted_stats = sorted(stats, key=lambda s: s.date, reverse=True)
            recent_counts = [s.mention_count for s in sorted_stats[:3]]
            older_counts = [s.mention_count for s in sorted_stats[3:7]]

        current_avg = sum(recent_counts) / max(len(recent_counts), 1)
        previous_avg = sum(older_counts) / max(len(older_counts), 1)

        if previous_avg > 0:
            growth_rate = (current_avg - previous_avg) / previous_avg
        else:
            growth_rate = 1.0 if current_avg > 0 else 0.0

        # Momentum score (weighted recent activity)
        weights = [3, 2, 1]  # Most recent days weighted higher
        momentum = sum(
            c * w for c, w in zip(recent_counts, weights)
        ) / sum(weights[:len(recent_counts)]) if recent_counts else 0

        # Trend direction
        if growth_rate > 0.2:
            trend_direction = "accelerating"
        elif growth_rate < -0.2:
            trend_direction = "declining"
        else:
            trend_direction = "stable"

        # Get first/last seen
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        if platform == "all":
            cursor.execute("""
                SELECT MIN(first_date), MAX(date)
                FROM first_seen f
                JOIN daily_aggregates d ON f.symbol = d.symbol
                WHERE f.symbol = ?
            """, (symbol,))
        else:
            cursor.execute("""
                SELECT first_date, MAX(d.date)
                FROM first_seen f
                JOIN daily_aggregates d ON f.symbol = d.symbol AND f.platform = d.platform
                WHERE f.symbol = ? AND f.platform = ?
            """, (symbol, platform))

        row = cursor.fetchone()
        conn.close()

        first_seen = row[0] if row and row[0] else datetime.now().strftime("%Y-%m-%d")
        last_seen = row[1] if row and row[1] else datetime.now().strftime("%Y-%m-%d")

        total_mentions = sum(s.mention_count for s in stats)

        return MentionTrend(
            symbol=symbol,
            platform=platform,
            current_daily_avg=current_avg,
            previous_daily_avg=previous_avg,
            growth_rate=growth_rate,
            momentum_score=momentum,
            trend_direction=trend_direction,
            first_seen=first_seen,
            last_seen=last_seen,
            total_mentions=total_mentions,
        )

    def get_trending_symbols(self, platform: str = None, top_n: int = 20) -> list[MentionTrend]:
        """Get symbols with highest momentum."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        if platform:
            cursor.execute("""
                SELECT DISTINCT symbol FROM daily_aggregates
                WHERE platform = ? AND date >= ?
                ORDER BY mention_count DESC
                LIMIT ?
            """, (platform, cutoff, top_n * 2))
        else:
            cursor.execute("""
                SELECT DISTINCT symbol FROM daily_aggregates
                WHERE date >= ?
                GROUP BY symbol
                ORDER BY SUM(mention_count) DESC
                LIMIT ?
            """, (cutoff, top_n * 2))

        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()

        trends = []
        for symbol in symbols:
            trend = self.get_trend(symbol, platform)
            if trend:
                trends.append(trend)

        # Sort by momentum
        trends.sort(key=lambda t: t.momentum_score, reverse=True)
        return trends[:top_n]

    def get_cross_platform_convergence(self, min_platforms: int = 2) -> list[dict]:
        """Find symbols mentioned on multiple platforms."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT symbol, COUNT(DISTINCT platform) as platform_count,
                   SUM(mention_count) as total_mentions,
                   AVG(avg_sentiment) as avg_sentiment
            FROM daily_aggregates
            WHERE date >= ?
            GROUP BY symbol
            HAVING platform_count >= ?
            ORDER BY total_mentions DESC
        """, (cutoff, min_platforms))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "symbol": row[0],
                "platform_count": row[1],
                "total_mentions": row[2],
                "avg_sentiment": row[3] or 0,
            }
            for row in rows
        ]

    def prune_old_data(self, days_to_keep: int = 90):
        """Remove old raw data to save space."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

        cursor.execute("DELETE FROM raw_mentions WHERE date(timestamp) < ?", (cutoff,))
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        logger.info(f"Pruned {deleted} old mention records")
        return deleted


# Singleton instance
_social_timeseries: Optional[SocialTimeSeries] = None


def get_social_timeseries() -> SocialTimeSeries:
    """Get singleton instance."""
    global _social_timeseries
    if _social_timeseries is None:
        _social_timeseries = SocialTimeSeries()
    return _social_timeseries


if __name__ == "__main__":
    ts = SocialTimeSeries()

    # Demo
    print("Trending symbols:")
    for trend in ts.get_trending_symbols(top_n=10):
        print(f"  {trend.symbol}: momentum={trend.momentum_score:.1f}, growth={trend.growth_rate:+.0%}")

    print("\nCross-platform convergence:")
    for conv in ts.get_cross_platform_convergence():
        print(f"  {conv['symbol']}: {conv['platform_count']} platforms, {conv['total_mentions']} mentions")
