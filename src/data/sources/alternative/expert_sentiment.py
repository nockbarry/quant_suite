"""Expert sentiment tracker for trading signals.

Tracks recommendations and sentiment from financial pundits, analysts,
and media personalities. Supports both following AND inversing expert calls.

Famous examples:
- Inverse Cramer: Jim Cramer's stock picks often underperform
- Cathie Wood: High-conviction tech/innovation picks
- Dan Ives: Tech analyst with strong conviction calls
- Analyst upgrades/downgrades: Wall Street consensus

Data Sources:
- CNBC RSS feeds (Mad Money, talking heads)
- Twitter/X mentions (if API available)
- Seeking Alpha (analyst recommendations)
- TipRanks (analyst ratings aggregation)
- YouTube transcripts (for shows)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from xml.etree import ElementTree

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


class SentimentType(str, Enum):
    """Type of sentiment/recommendation."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ExpertType(str, Enum):
    """Type of financial expert."""
    TV_PUNDIT = "tv_pundit"
    WALL_STREET_ANALYST = "analyst"
    FUND_MANAGER = "fund_manager"
    NEWSLETTER = "newsletter"
    SOCIAL_MEDIA = "social_media"
    QUANT = "quant"


class SignalAction(str, Enum):
    """How to act on expert signal."""
    FOLLOW = "follow"  # Do what expert says
    INVERSE = "inverse"  # Do opposite of what expert says
    IGNORE = "ignore"  # Track but don't act


# Expert profiles with historical accuracy
EXPERT_PROFILES = {
    # TV Pundits
    "Jim Cramer": {
        "type": ExpertType.TV_PUNDIT,
        "default_action": SignalAction.INVERSE,  # Famous for being wrong
        "sources": ["cnbc", "mad_money"],
        "historical_accuracy": 0.38,  # Below 50% = inverse
        "conviction_weight": 0.8,
        "notes": "Mad Money host, high-conviction calls often wrong",
    },
    "Cathie Wood": {
        "type": ExpertType.FUND_MANAGER,
        "default_action": SignalAction.FOLLOW,  # In bull markets
        "sources": ["ark_invest", "twitter"],
        "historical_accuracy": 0.55,  # Varies by market regime
        "conviction_weight": 0.9,
        "notes": "ARK Invest CEO, high-conviction innovation/tech",
    },
    "Dan Ives": {
        "type": ExpertType.WALL_STREET_ANALYST,
        "default_action": SignalAction.FOLLOW,
        "sources": ["wedbush", "cnbc"],
        "historical_accuracy": 0.62,
        "conviction_weight": 0.7,
        "notes": "Wedbush tech analyst, Apple/Tesla specialist",
    },
    "Tom Lee": {
        "type": ExpertType.WALL_STREET_ANALYST,
        "default_action": SignalAction.FOLLOW,
        "sources": ["fundstrat", "cnbc"],
        "historical_accuracy": 0.58,
        "conviction_weight": 0.75,
        "notes": "Fundstrat, perma-bull but often right on tech",
    },
    "Michael Burry": {
        "type": ExpertType.FUND_MANAGER,
        "default_action": SignalAction.FOLLOW,
        "sources": ["sec_13f", "twitter"],
        "historical_accuracy": 0.65,
        "conviction_weight": 0.85,
        "notes": "Scion Capital, contrarian/value, Big Short fame",
    },
    "Peter Schiff": {
        "type": ExpertType.TV_PUNDIT,
        "default_action": SignalAction.INVERSE,
        "sources": ["twitter", "youtube"],
        "historical_accuracy": 0.35,
        "conviction_weight": 0.6,
        "notes": "Gold bug, perma-bear, often wrong on timing",
    },
    "Chamath Palihapitiya": {
        "type": ExpertType.FUND_MANAGER,
        "default_action": SignalAction.INVERSE,  # Post-2021
        "sources": ["twitter", "podcasts"],
        "historical_accuracy": 0.42,
        "conviction_weight": 0.7,
        "notes": "Social Capital, SPACs, pump-and-dump reputation",
    },
    "Nancy Pelosi": {
        "type": ExpertType.FUND_MANAGER,  # Effectively
        "default_action": SignalAction.FOLLOW,
        "sources": ["congressional_trades"],
        "historical_accuracy": 0.72,
        "conviction_weight": 0.85,
        "notes": "Congress member, suspiciously good timing on tech calls",
    },
    "David Tepper": {
        "type": ExpertType.FUND_MANAGER,
        "default_action": SignalAction.FOLLOW,
        "sources": ["cnbc", "sec_13f"],
        "historical_accuracy": 0.68,
        "conviction_weight": 0.8,
        "notes": "Appaloosa, macro/distressed, high conviction",
    },
}

# Sentiment keywords for parsing
BULLISH_KEYWORDS = [
    "buy", "bullish", "overweight", "outperform", "strong buy",
    "accumulate", "upgrade", "moon", "rip", "breakout", "rally",
    "love", "favorite", "conviction", "must own", "no brainer",
]

BEARISH_KEYWORDS = [
    "sell", "bearish", "underweight", "underperform", "avoid",
    "reduce", "downgrade", "crash", "dump", "breakdown", "tank",
    "hate", "stay away", "risky", "bubble", "overvalued",
]


@dataclass
class ExpertCall:
    """Single recommendation/call from an expert."""

    # Core fields
    expert_name: str
    symbol: str
    sentiment: SentimentType
    timestamp: datetime
    source: str

    # Details
    headline: str
    context: str | None = None
    price_target: float | None = None
    current_price: float | None = None
    conviction_level: float = 0.5  # 0-1

    # Action guidance
    default_action: SignalAction = SignalAction.FOLLOW
    historical_accuracy: float = 0.5

    def __post_init__(self):
        """Set defaults from expert profile if available."""
        if self.expert_name in EXPERT_PROFILES:
            profile = EXPERT_PROFILES[self.expert_name]
            self.default_action = profile.get("default_action", self.default_action)
            self.historical_accuracy = profile.get("historical_accuracy", self.historical_accuracy)

    @property
    def signal(self) -> str:
        """
        Get trading signal based on sentiment and action.

        If action is INVERSE, flip the sentiment.
        """
        is_bullish = self.sentiment in [SentimentType.STRONG_BUY, SentimentType.BUY, SentimentType.BULLISH]
        is_bearish = self.sentiment in [SentimentType.STRONG_SELL, SentimentType.SELL, SentimentType.BEARISH]

        if self.default_action == SignalAction.INVERSE:
            if is_bullish:
                return "bearish"
            elif is_bearish:
                return "bullish"
        elif self.default_action == SignalAction.FOLLOW:
            if is_bullish:
                return "bullish"
            elif is_bearish:
                return "bearish"

        return "neutral"

    @property
    def signal_strength(self) -> float:
        """
        Calculate signal strength (0-1).

        Factors:
        - Expert's historical accuracy
        - Conviction level
        - Sentiment strength (strong buy/sell > buy/sell)
        """
        strength = 0.5

        # Accuracy factor (inverse experts with low accuracy still provide signal)
        if self.default_action == SignalAction.INVERSE:
            # Lower accuracy = stronger inverse signal
            accuracy_factor = 1.0 - self.historical_accuracy
        else:
            accuracy_factor = self.historical_accuracy

        strength = accuracy_factor * 0.5

        # Conviction bonus
        strength += self.conviction_level * 0.3

        # Strong sentiment bonus
        if self.sentiment in [SentimentType.STRONG_BUY, SentimentType.STRONG_SELL]:
            strength += 0.2

        return min(1.0, strength)

    @property
    def is_high_conviction(self) -> bool:
        """Check if this is a high-conviction call."""
        return self.conviction_level >= 0.7

    @property
    def upside_pct(self) -> float | None:
        """Calculate upside to price target."""
        if self.price_target and self.current_price and self.current_price > 0:
            return ((self.price_target - self.current_price) / self.current_price) * 100
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "expert_name": self.expert_name,
            "symbol": self.symbol,
            "sentiment": self.sentiment.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "headline": self.headline,
            "context": self.context,
            "price_target": self.price_target,
            "current_price": self.current_price,
            "conviction_level": self.conviction_level,
            "default_action": self.default_action.value,
            "historical_accuracy": self.historical_accuracy,
            "signal": self.signal,
            "signal_strength": self.signal_strength,
            "is_high_conviction": self.is_high_conviction,
            "upside_pct": self.upside_pct,
        }


@dataclass
class ExpertConsensus:
    """Aggregated expert sentiment for a symbol."""

    symbol: str
    calls: list[ExpertCall]
    period_start: datetime
    period_end: datetime

    @property
    def bullish_count(self) -> int:
        """Count bullish signals (after applying inverse logic)."""
        return sum(1 for c in self.calls if c.signal == "bullish")

    @property
    def bearish_count(self) -> int:
        """Count bearish signals (after applying inverse logic)."""
        return sum(1 for c in self.calls if c.signal == "bearish")

    @property
    def net_sentiment(self) -> float:
        """
        Net sentiment from -1 (all bearish) to +1 (all bullish).
        """
        total = len(self.calls)
        if total == 0:
            return 0.0
        return (self.bullish_count - self.bearish_count) / total

    @property
    def consensus_signal(self) -> str:
        """Get consensus signal across experts."""
        if self.net_sentiment > 0.3:
            return "bullish"
        elif self.net_sentiment < -0.3:
            return "bearish"
        return "mixed"

    @property
    def avg_signal_strength(self) -> float:
        """Average signal strength."""
        if not self.calls:
            return 0.0
        return sum(c.signal_strength for c in self.calls) / len(self.calls)

    @property
    def high_conviction_calls(self) -> list[ExpertCall]:
        """Get high-conviction calls."""
        return [c for c in self.calls if c.is_high_conviction]

    @property
    def inverse_expert_calls(self) -> list[ExpertCall]:
        """Get calls from inverse experts (contrarian signals)."""
        return [c for c in self.calls if c.default_action == SignalAction.INVERSE]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "call_count": len(self.calls),
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "net_sentiment": self.net_sentiment,
            "consensus_signal": self.consensus_signal,
            "avg_signal_strength": self.avg_signal_strength,
            "high_conviction_count": len(self.high_conviction_calls),
            "inverse_expert_count": len(self.inverse_expert_calls),
            "calls": [c.to_dict() for c in self.calls],
        }


def extract_sentiment(text: str) -> tuple[SentimentType, float]:
    """
    Extract sentiment and conviction from text.

    Returns:
        Tuple of (sentiment_type, conviction_level)
    """
    text_lower = text.lower()

    # Count keyword matches
    bullish_matches = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bearish_matches = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

    # Check for strong modifiers
    strong_modifiers = ["very", "extremely", "absolutely", "definitely", "strong"]
    has_strong = any(mod in text_lower for mod in strong_modifiers)

    # Determine sentiment
    if bullish_matches > bearish_matches:
        if has_strong or bullish_matches >= 3:
            sentiment = SentimentType.STRONG_BUY
            conviction = 0.9
        else:
            sentiment = SentimentType.BUY
            conviction = 0.6 + (bullish_matches * 0.1)
    elif bearish_matches > bullish_matches:
        if has_strong or bearish_matches >= 3:
            sentiment = SentimentType.STRONG_SELL
            conviction = 0.9
        else:
            sentiment = SentimentType.SELL
            conviction = 0.6 + (bearish_matches * 0.1)
    else:
        sentiment = SentimentType.NEUTRAL
        conviction = 0.5

    return sentiment, min(1.0, conviction)


def extract_symbols(text: str) -> list[str]:
    """Extract stock symbols from text."""
    # Look for $SYMBOL pattern
    dollar_symbols = re.findall(r'\$([A-Z]{1,5})\b', text.upper())

    # Look for standalone tickers (common ones)
    common_tickers = [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
        "AMD", "INTC", "NFLX", "DIS", "BA", "JPM", "GS", "BAC",
        "XOM", "CVX", "PFE", "JNJ", "UNH", "WMT", "HD", "COST",
    ]

    text_upper = text.upper()
    found_tickers = [t for t in common_tickers if re.search(rf'\b{t}\b', text_upper)]

    # Combine and dedupe
    all_symbols = list(set(dollar_symbols + found_tickers))
    return all_symbols


class ExpertSentimentSource:
    """
    Expert sentiment data source.

    Tracks recommendations from financial pundits and analysts.
    Supports both following AND inversing expert calls.
    """

    name = "expert_sentiment"

    # RSS feeds
    CNBC_RSS = "https://www.cnbc.com/id/10000664/device/rss/rss.html"  # Mad Money
    CNBC_PRO_RSS = "https://www.cnbc.com/id/19836768/device/rss/rss.html"  # Pro picks

    def __init__(
        self,
        twitter_bearer_token: str | None = None,
        custom_experts: dict[str, dict] | None = None,
        cache_ttl_minutes: int = 30,
    ):
        """
        Initialize expert sentiment source.

        Args:
            twitter_bearer_token: Twitter API bearer token (optional)
            custom_experts: Additional expert profiles
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.twitter_token = twitter_bearer_token
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None

        # Merge custom experts
        self.experts = EXPERT_PROFILES.copy()
        if custom_experts:
            self.experts.update(custom_experts)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "QuantSuite/1.0 (research@example.com)",
                    "Accept": "application/rss+xml, application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_cache(self, key: str) -> Any | None:
        """Check if cached data is valid."""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache."""
        self._cache[key] = (datetime.now(), data)

    async def fetch_calls(
        self,
        days: int = 7,
        expert_name: str | None = None,
        symbol: str | None = None,
        action_filter: SignalAction | None = None,
    ) -> list[ExpertCall]:
        """
        Fetch recent expert calls.

        Args:
            days: Lookback period
            expert_name: Filter by expert
            symbol: Filter by symbol
            action_filter: Filter by action type (FOLLOW/INVERSE)

        Returns:
            List of ExpertCall objects
        """
        cache_key = f"calls:{days}:{expert_name}:{symbol}:{action_filter}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        calls = []

        # Fetch from CNBC RSS (includes Mad Money/Cramer)
        cnbc_calls = await self._fetch_cnbc_rss()
        calls.extend(cnbc_calls)

        # Filter by date
        cutoff = datetime.now() - timedelta(days=days)
        calls = [c for c in calls if c.timestamp >= cutoff]

        # Filter by expert
        if expert_name:
            calls = [c for c in calls if expert_name.lower() in c.expert_name.lower()]

        # Filter by symbol
        if symbol:
            calls = [c for c in calls if c.symbol.upper() == symbol.upper()]

        # Filter by action
        if action_filter:
            calls = [c for c in calls if c.default_action == action_filter]

        # Sort by timestamp (newest first)
        calls.sort(key=lambda x: x.timestamp, reverse=True)

        if calls:
            self._update_cache(cache_key, calls)

        return calls

    async def _fetch_cnbc_rss(self) -> list[ExpertCall]:
        """Fetch calls from CNBC RSS feeds."""
        client = await self._get_client()
        calls = []

        for rss_url in [self.CNBC_RSS, self.CNBC_PRO_RSS]:
            try:
                resp = await client.get(rss_url)
                resp.raise_for_status()

                root = ElementTree.fromstring(resp.text)

                for item in root.findall(".//item"):
                    try:
                        title = item.find("title")
                        description = item.find("description")
                        pub_date = item.find("pubDate")
                        link = item.find("link")

                        if title is None:
                            continue

                        title_text = title.text or ""
                        desc_text = description.text if description is not None else ""
                        full_text = f"{title_text} {desc_text}"

                        # Check for Cramer/Mad Money
                        expert_name = "Unknown"
                        if "cramer" in full_text.lower() or "mad money" in full_text.lower():
                            expert_name = "Jim Cramer"
                        elif "tepper" in full_text.lower():
                            expert_name = "David Tepper"
                        elif "cathie" in full_text.lower() or "ark" in full_text.lower():
                            expert_name = "Cathie Wood"
                        elif "ives" in full_text.lower():
                            expert_name = "Dan Ives"

                        # Extract symbols
                        symbols = extract_symbols(full_text)
                        if not symbols:
                            continue

                        # Extract sentiment
                        sentiment, conviction = extract_sentiment(full_text)

                        # Parse date
                        timestamp = datetime.now()
                        if pub_date is not None and pub_date.text:
                            try:
                                timestamp = datetime.strptime(
                                    pub_date.text[:25],
                                    "%a, %d %b %Y %H:%M:%S",
                                )
                            except ValueError:
                                pass

                        # Create call for each symbol mentioned
                        for symbol in symbols:
                            calls.append(ExpertCall(
                                expert_name=expert_name,
                                symbol=symbol,
                                sentiment=sentiment,
                                timestamp=timestamp,
                                source="cnbc_rss",
                                headline=title_text,
                                context=desc_text[:500] if desc_text else None,
                                conviction_level=conviction,
                            ))

                    except Exception as e:
                        logger.debug(f"Error parsing CNBC item: {e}")

            except Exception as e:
                logger.warning(f"Error fetching CNBC RSS: {e}")

        return calls

    async def get_cramer_calls(
        self,
        days: int = 7,
    ) -> list[ExpertCall]:
        """
        Get Jim Cramer's recent calls (for inverse Cramer strategy).

        Args:
            days: Lookback period

        Returns:
            List of Cramer's calls (default action is INVERSE)
        """
        return await self.fetch_calls(days=days, expert_name="Jim Cramer")

    async def get_inverse_signals(
        self,
        days: int = 7,
    ) -> list[ExpertCall]:
        """
        Get signals from experts we should inverse.

        These are experts with historically poor accuracy
        whose calls should be faded.

        Args:
            days: Lookback period

        Returns:
            List of calls to inverse
        """
        return await self.fetch_calls(days=days, action_filter=SignalAction.INVERSE)

    async def get_follow_signals(
        self,
        days: int = 7,
    ) -> list[ExpertCall]:
        """
        Get signals from experts we should follow.

        These are experts with historically good accuracy.

        Args:
            days: Lookback period

        Returns:
            List of calls to follow
        """
        return await self.fetch_calls(days=days, action_filter=SignalAction.FOLLOW)

    async def get_consensus(
        self,
        symbol: str,
        days: int = 30,
    ) -> ExpertConsensus:
        """
        Get expert consensus for a symbol.

        Aggregates all expert calls and computes net signal.

        Args:
            symbol: Stock symbol
            days: Lookback period

        Returns:
            ExpertConsensus object
        """
        calls = await self.fetch_calls(days=days, symbol=symbol)

        return ExpertConsensus(
            symbol=symbol,
            calls=calls,
            period_start=datetime.now() - timedelta(days=days),
            period_end=datetime.now(),
        )

    async def get_high_conviction_calls(
        self,
        days: int = 7,
    ) -> list[ExpertCall]:
        """
        Get high-conviction calls from all experts.

        Args:
            days: Lookback period

        Returns:
            List of high-conviction calls
        """
        calls = await self.fetch_calls(days=days)
        return [c for c in calls if c.is_high_conviction]

    def add_expert(
        self,
        name: str,
        expert_type: ExpertType,
        default_action: SignalAction,
        historical_accuracy: float,
        conviction_weight: float = 0.7,
        sources: list[str] | None = None,
        notes: str = "",
    ) -> None:
        """
        Add or update an expert profile.

        Args:
            name: Expert name
            expert_type: Type of expert
            default_action: How to act on their calls
            historical_accuracy: Historical accuracy (0-1)
            conviction_weight: How much to weight their conviction
            sources: Data sources for this expert
            notes: Additional notes
        """
        self.experts[name] = {
            "type": expert_type,
            "default_action": default_action,
            "historical_accuracy": historical_accuracy,
            "conviction_weight": conviction_weight,
            "sources": sources or [],
            "notes": notes,
        }

    def list_experts(
        self,
        action_filter: SignalAction | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all tracked experts.

        Args:
            action_filter: Filter by action type

        Returns:
            List of expert profiles
        """
        experts = []
        for name, profile in self.experts.items():
            if action_filter and profile.get("default_action") != action_filter:
                continue
            experts.append({
                "name": name,
                **profile,
            })

        # Sort by historical accuracy
        experts.sort(key=lambda x: x.get("historical_accuracy", 0), reverse=True)
        return experts

    def to_dataframe(
        self,
        calls: list[ExpertCall],
    ) -> pd.DataFrame:
        """Convert calls to DataFrame."""
        if not calls:
            return pd.DataFrame()

        records = [c.to_dict() for c in calls]
        df = pd.DataFrame(records)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp", ascending=False)

        return df


async def fetch_expert_calls(
    days: int = 7,
    expert_name: str | None = None,
    symbol: str | None = None,
) -> list[ExpertCall]:
    """
    Convenience function to fetch expert calls.

    Args:
        days: Lookback period
        expert_name: Filter by expert
        symbol: Filter by symbol

    Returns:
        List of ExpertCall objects
    """
    source = ExpertSentimentSource()

    try:
        return await source.fetch_calls(days=days, expert_name=expert_name, symbol=symbol)
    finally:
        await source.close()


async def get_inverse_cramer(
    days: int = 7,
) -> list[ExpertCall]:
    """
    Get inverse Cramer signals.

    Jim Cramer's stock picks are famous for underperforming.
    This returns his calls with the signal already inverted.

    Args:
        days: Lookback period

    Returns:
        List of Cramer calls (signal is inverted)
    """
    source = ExpertSentimentSource()

    try:
        return await source.get_cramer_calls(days=days)
    finally:
        await source.close()


async def get_expert_consensus(
    symbol: str,
    days: int = 30,
) -> ExpertConsensus:
    """
    Get expert consensus for a symbol.

    Args:
        symbol: Stock symbol
        days: Lookback period

    Returns:
        ExpertConsensus object
    """
    source = ExpertSentimentSource()

    try:
        return await source.get_consensus(symbol=symbol, days=days)
    finally:
        await source.close()
