#!/usr/bin/env python3
"""WallStreetBets Tracker - Monitor WSB for early alpha signals.

Tracks:
- Symbol mention frequency over time
- Sentiment evolution
- Key DD (due diligence) posts
- Signal "vintage" (days since first detection)
- Signal phase (early/growing/mainstream/peaked)

Usage:
    from src.data.sources.alternative.wsb_tracker import WSBTracker

    tracker = WSBTracker()
    await tracker.scan_recent_posts()
    signals = tracker.get_early_signals()
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Try to import PRAW (Reddit API)
try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logger.info("PRAW not installed. Using public JSON API fallback.")

import requests


class SignalPhase(Enum):
    """Phase of a social signal's lifecycle."""
    EARLY = "early"           # <7 days, <100 mentions/day
    GROWING = "growing"       # Growing >20%/day
    MAINSTREAM = "mainstream" # >500 mentions/day or in news
    PEAKED = "peaked"         # Mentions declining


@dataclass
class WSBMention:
    """A single mention of a symbol on WSB."""
    symbol: str
    timestamp: datetime
    post_id: str
    post_title: str
    is_dd: bool  # Is this a DD (due diligence) post?
    upvotes: int
    comments: int
    sentiment: float  # -1 to 1
    author: str
    author_karma: int = 0
    url: str = ""

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "post_id": self.post_id,
            "post_title": self.post_title,
            "is_dd": self.is_dd,
            "upvotes": self.upvotes,
            "comments": self.comments,
            "sentiment": self.sentiment,
            "author": self.author,
            "author_karma": self.author_karma,
            "url": self.url,
        }


@dataclass
class WSBSignal:
    """Aggregated signal for a symbol from WSB tracking."""
    symbol: str
    first_seen: datetime
    last_seen: datetime
    mention_count: int
    mention_history: list = field(default_factory=list)  # List of (date, count)
    sentiment_history: list = field(default_factory=list)  # List of (date, sentiment)
    key_posts: list = field(default_factory=list)  # Top DD posts
    signal_vintage: int = 0  # Days since first detection
    current_phase: SignalPhase = SignalPhase.EARLY
    growth_rate: float = 0.0  # Daily growth rate
    avg_sentiment: float = 0.0
    total_upvotes: int = 0
    dd_count: int = 0

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "mention_count": self.mention_count,
            "mention_history": self.mention_history,
            "sentiment_history": self.sentiment_history,
            "key_posts": self.key_posts[:5],
            "signal_vintage": self.signal_vintage,
            "current_phase": self.current_phase.value,
            "growth_rate": self.growth_rate,
            "avg_sentiment": self.avg_sentiment,
            "total_upvotes": self.total_upvotes,
            "dd_count": self.dd_count,
        }


class WSBTracker:
    """Track WallStreetBets for early alpha signals."""

    DB_PATH = paths.base / "social" / "wsb.db"
    SIGNALS_PATH = paths.base / "social" / "wsb_signals.json"

    # Common stock ticker pattern
    TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b')

    # Exclude common words that look like tickers
    EXCLUDED_TICKERS = {
        'A', 'I', 'DD', 'CEO', 'CFO', 'USA', 'SEC', 'FDA', 'IPO', 'ETF',
        'WSB', 'YOLO', 'FOMO', 'IMO', 'TBH', 'TLDR', 'ATH', 'ATL', 'EPS',
        'P&L', 'ITM', 'OTM', 'PUT', 'CALL', 'LEAP', 'FD', 'EOD', 'EOW',
        'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN',
        'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'HAS', 'NEW', 'NOW', 'OLD',
    }

    # Subreddits to monitor
    SUBREDDITS = ['wallstreetbets', 'stocks', 'investing', 'options']

    def __init__(self, use_praw: bool = True):
        self.reddit = None
        if use_praw and PRAW_AVAILABLE:
            self._init_praw()
        self._init_db()

    def _init_praw(self):
        """Initialize PRAW client."""
        try:
            # Try to load credentials
            creds_path = Path.home() / "projects/quant_suite/config/credentials.yaml"
            if creds_path.exists():
                import yaml
                with open(creds_path) as f:
                    creds = yaml.safe_load(f)
                    reddit_creds = creds.get("reddit", {})
                    if reddit_creds.get("client_id"):
                        self.reddit = praw.Reddit(
                            client_id=reddit_creds["client_id"],
                            client_secret=reddit_creds["client_secret"],
                            user_agent=reddit_creds.get("user_agent", "quant_suite/1.0"),
                        )
                        logger.info("PRAW initialized with credentials")
                        return

            # Use read-only mode without credentials
            self.reddit = praw.Reddit(
                client_id="YOUR_CLIENT_ID",
                client_secret="YOUR_CLIENT_SECRET",
                user_agent="quant_suite/1.0 (by u/quant_trader)",
            )
        except Exception as e:
            logger.warning(f"Could not initialize PRAW: {e}")
            self.reddit = None

    def _init_db(self):
        """Initialize SQLite database for mention history."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Mentions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                post_id TEXT UNIQUE,
                post_title TEXT,
                is_dd INTEGER,
                upvotes INTEGER,
                comments INTEGER,
                sentiment REAL,
                author TEXT,
                author_karma INTEGER,
                url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily aggregates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                mention_count INTEGER,
                avg_sentiment REAL,
                total_upvotes INTEGER,
                dd_count INTEGER,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_symbol ON mentions(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mentions_timestamp ON mentions(timestamp)")

        conn.commit()
        conn.close()

    def _extract_tickers(self, text: str) -> list[str]:
        """Extract stock tickers from text."""
        tickers = set()

        for match in self.TICKER_PATTERN.finditer(text):
            ticker = match.group(1) or match.group(2)
            if ticker and ticker not in self.EXCLUDED_TICKERS:
                # Basic validation - must be 1-5 uppercase letters
                if 1 <= len(ticker) <= 5 and ticker.isalpha():
                    tickers.add(ticker)

        return list(tickers)

    def _analyze_sentiment(self, title: str, text: str = "") -> float:
        """Simple sentiment analysis based on keywords.

        Returns -1 (bearish) to 1 (bullish).
        """
        content = (title + " " + text).lower()

        bullish_words = [
            'moon', 'rocket', 'buy', 'calls', 'bull', 'going up', 'breakout',
            'squeeze', 'undervalued', 'long', 'yolo', 'diamond hands', 'hold',
            'tendies', 'gain', 'profit', 'winner', 'bullish', 'pumping',
        ]

        bearish_words = [
            'puts', 'bear', 'short', 'crash', 'dump', 'sell', 'overvalued',
            'bag holder', 'loss', 'rip', 'bearish', 'tanking', 'falling',
            'bubble', 'scam', 'fraud', 'dead', 'worthless',
        ]

        bullish_count = sum(1 for word in bullish_words if word in content)
        bearish_count = sum(1 for word in bearish_words if word in content)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        return (bullish_count - bearish_count) / total

    async def scan_reddit_api(self, subreddit: str = "wallstreetbets", limit: int = 100) -> list[WSBMention]:
        """Scan Reddit using public JSON API (no auth needed)."""
        mentions = []

        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
            headers = {"User-Agent": "quant_suite/1.0"}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            for post_data in posts:
                post = post_data.get("data", {})
                title = post.get("title", "")
                selftext = post.get("selftext", "")

                tickers = self._extract_tickers(title + " " + selftext)

                for ticker in tickers:
                    flair = post.get("link_flair_text") or ""
                    is_dd = (
                        flair.lower() == "dd" or
                        "dd" in title.lower()[:20]
                    )

                    mention = WSBMention(
                        symbol=ticker,
                        timestamp=datetime.fromtimestamp(post.get("created_utc", 0)),
                        post_id=post.get("id", ""),
                        post_title=title[:200],
                        is_dd=is_dd,
                        upvotes=post.get("ups", 0),
                        comments=post.get("num_comments", 0),
                        sentiment=self._analyze_sentiment(title, selftext),
                        author=post.get("author", ""),
                        author_karma=0,  # Not available in JSON API
                        url=f"https://reddit.com{post.get('permalink', '')}",
                    )
                    mentions.append(mention)

        except Exception as e:
            logger.error(f"Error scanning Reddit API: {e}")

        return mentions

    async def scan_recent_posts(self, limit: int = 100) -> list[WSBMention]:
        """Scan recent posts from all monitored subreddits."""
        all_mentions = []

        for subreddit in self.SUBREDDITS:
            try:
                mentions = await self.scan_reddit_api(subreddit, limit=limit // len(self.SUBREDDITS))
                all_mentions.extend(mentions)
                logger.info(f"Found {len(mentions)} mentions in r/{subreddit}")
            except Exception as e:
                logger.warning(f"Error scanning r/{subreddit}: {e}")

        # Store in database
        self._store_mentions(all_mentions)

        # Emit events for significant mentions
        for mention in all_mentions:
            try:
                if mention.is_dd or mention.upvotes >= 100:
                    from src.core.events import emit
                    emit(
                        "signal_social_wsb",
                        source="wsb",
                        symbol=mention.symbol,
                        title=f"WSB {'DD' if mention.is_dd else 'mention'}: {mention.symbol} ({mention.upvotes} upvotes)",
                        detail={"post_title": mention.post_title, "upvotes": mention.upvotes,
                                "is_dd": mention.is_dd, "post_id": mention.post_id},
                        confidence=min(1.0, 0.3 + (mention.upvotes / 1000)),
                        direction="bullish" if mention.sentiment > 0 else "bearish" if mention.sentiment < 0 else "neutral",
                        description=mention.post_title[:200],
                        detection_method="wsb_scan",
                    )
            except Exception:
                pass

        return all_mentions

    def _store_mentions(self, mentions: list[WSBMention]):
        """Store mentions in database."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        for mention in mentions:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO mentions
                    (symbol, timestamp, post_id, post_title, is_dd, upvotes,
                     comments, sentiment, author, author_karma, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mention.symbol,
                    mention.timestamp.isoformat(),
                    mention.post_id,
                    mention.post_title,
                    1 if mention.is_dd else 0,
                    mention.upvotes,
                    mention.comments,
                    mention.sentiment,
                    mention.author,
                    mention.author_karma,
                    mention.url,
                ))
            except Exception as e:
                logger.debug(f"Could not store mention: {e}")

        conn.commit()
        conn.close()

    def _update_daily_stats(self):
        """Update daily aggregated statistics."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Aggregate today's mentions
        cursor.execute("""
            INSERT OR REPLACE INTO daily_stats (symbol, date, mention_count, avg_sentiment, total_upvotes, dd_count)
            SELECT
                symbol,
                date(timestamp) as date,
                COUNT(*) as mention_count,
                AVG(sentiment) as avg_sentiment,
                SUM(upvotes) as total_upvotes,
                SUM(is_dd) as dd_count
            FROM mentions
            WHERE date(timestamp) = ?
            GROUP BY symbol
        """, (today,))

        conn.commit()
        conn.close()

    def get_signal(self, symbol: str) -> Optional[WSBSignal]:
        """Get aggregated signal for a symbol."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Get mention history
        cursor.execute("""
            SELECT date, mention_count, avg_sentiment, total_upvotes, dd_count
            FROM daily_stats
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT 30
        """, (symbol,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        # Build signal
        mention_history = [(row[0], row[1]) for row in rows]
        sentiment_history = [(row[0], row[2]) for row in rows]

        first_seen = datetime.strptime(rows[-1][0], "%Y-%m-%d")
        last_seen = datetime.strptime(rows[0][0], "%Y-%m-%d")
        total_mentions = sum(row[1] for row in rows)
        total_upvotes = sum(row[3] or 0 for row in rows)
        dd_count = sum(row[4] or 0 for row in rows)
        avg_sentiment = sum(row[2] or 0 for row in rows) / len(rows) if rows else 0

        # Calculate vintage
        signal_vintage = (datetime.now() - first_seen).days

        # Calculate growth rate (7-day rolling)
        if len(rows) >= 2:
            recent_avg = sum(r[1] for r in rows[:3]) / min(3, len(rows))
            older_avg = sum(r[1] for r in rows[3:7]) / max(1, min(4, len(rows) - 3))
            growth_rate = (recent_avg - older_avg) / max(older_avg, 1) if older_avg > 0 else 0
        else:
            growth_rate = 0

        # Determine phase
        daily_avg = total_mentions / max(signal_vintage, 1)
        if signal_vintage < 7 and daily_avg < 100:
            phase = SignalPhase.EARLY
        elif growth_rate > 0.2:
            phase = SignalPhase.GROWING
        elif daily_avg > 500:
            phase = SignalPhase.MAINSTREAM
        elif growth_rate < -0.2:
            phase = SignalPhase.PEAKED
        else:
            phase = SignalPhase.GROWING if growth_rate > 0 else SignalPhase.MAINSTREAM

        return WSBSignal(
            symbol=symbol,
            first_seen=first_seen,
            last_seen=last_seen,
            mention_count=total_mentions,
            mention_history=mention_history,
            sentiment_history=sentiment_history,
            key_posts=[],  # Would need separate query
            signal_vintage=signal_vintage,
            current_phase=phase,
            growth_rate=growth_rate,
            avg_sentiment=avg_sentiment,
            total_upvotes=total_upvotes,
            dd_count=dd_count,
        )

    def get_early_signals(self, max_vintage_days: int = 7, max_daily_mentions: int = 100) -> list[WSBSignal]:
        """Get signals that are still in early phase.

        Early signals are:
        - First detected < 7 days ago
        - Average < 100 mentions/day
        - Growing momentum preferred
        """
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Get symbols with recent activity
        cutoff = (datetime.now() - timedelta(days=max_vintage_days)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT DISTINCT symbol
            FROM daily_stats
            WHERE date >= ?
        """, (cutoff,))

        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()

        early_signals = []
        for symbol in symbols:
            signal = self.get_signal(symbol)
            if signal and signal.current_phase in [SignalPhase.EARLY, SignalPhase.GROWING]:
                daily_avg = signal.mention_count / max(signal.signal_vintage, 1)
                if daily_avg < max_daily_mentions:
                    early_signals.append(signal)

        # Sort by growth rate (highest first)
        early_signals.sort(key=lambda s: s.growth_rate, reverse=True)

        # Emit events for early/growing signals
        for signal in early_signals:
            try:
                from src.core.events import emit
                emit(
                    "signal_social_early",
                    source="wsb",
                    symbol=signal.symbol,
                    title=f"WSB early signal: {signal.symbol} ({signal.current_phase.value}, growth {signal.growth_rate:+.0%})",
                    detail={"phase": signal.current_phase.value, "growth_rate": signal.growth_rate,
                            "mention_count": signal.mention_count, "vintage_days": signal.signal_vintage},
                    confidence=min(1.0, 0.4 + signal.growth_rate * 0.3),
                    direction="bullish" if signal.avg_sentiment > 0 else "neutral",
                    description=f"WSB {signal.current_phase.value}: {signal.mention_count} mentions, {signal.growth_rate:+.0%} growth",
                    detection_method="wsb_early_scan",
                )
            except Exception:
                pass

        return early_signals

    def get_trending_signals(self, top_n: int = 10) -> list[WSBSignal]:
        """Get signals with highest recent activity."""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # Get top symbols by recent mention volume
        cursor.execute("""
            SELECT symbol, SUM(mention_count) as total
            FROM daily_stats
            WHERE date >= date('now', '-7 days')
            GROUP BY symbol
            ORDER BY total DESC
            LIMIT ?
        """, (top_n * 2,))  # Get more to filter

        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()

        signals = []
        for symbol in symbols[:top_n]:
            signal = self.get_signal(symbol)
            if signal:
                signals.append(signal)

        return signals

    def save_signals(self):
        """Save current signals to JSON for other components."""
        early = self.get_early_signals()
        trending = self.get_trending_signals()

        output = {
            "updated_at": datetime.now().isoformat(),
            "early_signals": [s.to_dict() for s in early],
            "trending_signals": [s.to_dict() for s in trending],
        }

        self.SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.SIGNALS_PATH, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved {len(early)} early and {len(trending)} trending signals")

    def generate_report(self) -> str:
        """Generate ASCII report of WSB signals."""
        early = self.get_early_signals()
        trending = self.get_trending_signals()

        lines = [
            "WALLSTREETBETS SIGNAL TRACKER",
            "═" * 60,
            "",
            "EARLY SIGNALS (Potential Alpha)",
            "─" * 40,
        ]

        if early:
            for signal in early[:10]:
                sentiment_icon = "📈" if signal.avg_sentiment > 0.2 else "📉" if signal.avg_sentiment < -0.2 else "➖"
                lines.append(
                    f"  {sentiment_icon} {signal.symbol:6} | "
                    f"vintage: {signal.signal_vintage}d | "
                    f"growth: {signal.growth_rate:+.0%} | "
                    f"mentions: {signal.mention_count}"
                )
        else:
            lines.append("  No early signals detected")

        lines.extend([
            "",
            "TRENDING SIGNALS (High Volume)",
            "─" * 40,
        ])

        if trending:
            for signal in trending[:10]:
                phase_icon = {
                    SignalPhase.EARLY: "🌱",
                    SignalPhase.GROWING: "📈",
                    SignalPhase.MAINSTREAM: "🔥",
                    SignalPhase.PEAKED: "📉",
                }.get(signal.current_phase, "•")
                lines.append(
                    f"  {phase_icon} {signal.symbol:6} | "
                    f"phase: {signal.current_phase.value:10} | "
                    f"mentions: {signal.mention_count:5} | "
                    f"DD posts: {signal.dd_count}"
                )
        else:
            lines.append("  No trending signals")

        lines.extend([
            "",
            "═" * 60,
        ])

        return "\n".join(lines)


# Singleton instance
_wsb_tracker: Optional[WSBTracker] = None


def get_wsb_tracker() -> WSBTracker:
    """Get singleton WSB tracker instance."""
    global _wsb_tracker
    if _wsb_tracker is None:
        _wsb_tracker = WSBTracker()
    return _wsb_tracker


if __name__ == "__main__":
    import asyncio

    async def main():
        tracker = WSBTracker()
        print("Scanning Reddit...")
        mentions = await tracker.scan_recent_posts(limit=100)
        print(f"Found {len(mentions)} mentions")
        tracker._update_daily_stats()
        tracker.save_signals()
        print(tracker.generate_report())

    asyncio.run(main())
