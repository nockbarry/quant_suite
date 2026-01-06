"""Congressional trading data source.

Tracks stock trades by members of Congress for trading signals.
Research shows congressional members often trade ahead of legislation
and market-moving events.

Data Sources:
- Capitol Trades (capitoltrades.com) - Aggregated filings
- House Stock Watcher (housestockwatcher.com) - RSS feed
- Senate Stock Watcher (senatestockwatcher.com) - RSS feed
- Quiver Quant API (quiverquant.com) - Aggregated data
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


class Chamber(str, Enum):
    """Congressional chamber."""
    HOUSE = "house"
    SENATE = "senate"
    UNKNOWN = "unknown"


class TradeType(str, Enum):
    """Type of congressional trade."""
    PURCHASE = "purchase"
    SALE = "sale"
    SALE_PARTIAL = "sale_partial"
    SALE_FULL = "sale_full"
    EXCHANGE = "exchange"
    UNKNOWN = "unknown"


class AssetType(str, Enum):
    """Type of asset traded."""
    STOCK = "stock"
    STOCK_OPTION = "stock_option"
    BOND = "bond"
    CRYPTO = "crypto"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    OTHER = "other"


# Known influential traders (historically high returns)
NOTABLE_TRADERS = {
    "Nancy Pelosi": {"chamber": Chamber.HOUSE, "influence": "high", "strategy": "tech_options"},
    "Dan Crenshaw": {"chamber": Chamber.HOUSE, "influence": "medium", "strategy": "energy"},
    "Tommy Tuberville": {"chamber": Chamber.SENATE, "influence": "medium", "strategy": "diversified"},
    "Josh Gottheimer": {"chamber": Chamber.HOUSE, "influence": "medium", "strategy": "tech"},
    "Ro Khanna": {"chamber": Chamber.HOUSE, "influence": "medium", "strategy": "tech"},
    "Austin Scott": {"chamber": Chamber.HOUSE, "influence": "medium", "strategy": "diversified"},
}

# Committees with market-moving potential
INFLUENTIAL_COMMITTEES = {
    "House Financial Services": ["banks", "fintech", "crypto"],
    "Senate Banking": ["banks", "fintech", "crypto"],
    "House Energy and Commerce": ["energy", "healthcare", "telecom"],
    "Senate Commerce": ["tech", "telecom", "transport"],
    "House Armed Services": ["defense", "aerospace"],
    "Senate Armed Services": ["defense", "aerospace"],
    "House Ways and Means": ["tax", "trade", "healthcare"],
    "Senate Finance": ["tax", "trade", "healthcare"],
}


@dataclass
class CongressionalTrade:
    """Single congressional trade from disclosure filings."""

    # Core fields
    politician: str
    chamber: Chamber
    symbol: str
    asset_type: AssetType
    trade_type: TradeType
    transaction_date: datetime
    disclosure_date: datetime

    # Value range (filings report ranges, not exact amounts)
    amount_low: float
    amount_high: float

    # Optional details
    asset_description: str | None = None
    comment: str | None = None
    committees: list[str] = field(default_factory=list)
    party: str | None = None
    state: str | None = None

    # Derived/computed
    is_notable_trader: bool = False
    filing_delay_days: int = 0

    def __post_init__(self):
        """Compute derived fields."""
        self.is_notable_trader = self.politician in NOTABLE_TRADERS
        if self.transaction_date and self.disclosure_date:
            self.filing_delay_days = (self.disclosure_date - self.transaction_date).days

    @property
    def amount_estimate(self) -> float:
        """Geometric mean of range as point estimate."""
        if self.amount_low > 0 and self.amount_high > 0:
            return (self.amount_low * self.amount_high) ** 0.5
        return (self.amount_low + self.amount_high) / 2

    @property
    def is_significant(self) -> bool:
        """Check if trade is significant ($100k+)."""
        return self.amount_estimate >= 100_000

    @property
    def is_timely(self) -> bool:
        """Check if filing was timely (within 45 days)."""
        return self.filing_delay_days <= 45

    @property
    def signal_strength(self) -> float:
        """
        Calculate signal strength (0-1).

        Factors:
        - Notable trader bonus
        - Trade size
        - Filing timeliness
        - Committee relevance
        """
        strength = 0.5  # Base

        # Notable trader bonus
        if self.is_notable_trader:
            strength += 0.2

        # Size bonus
        if self.amount_estimate >= 500_000:
            strength += 0.15
        elif self.amount_estimate >= 100_000:
            strength += 0.1

        # Timeliness bonus (filed quickly = more confident)
        if self.filing_delay_days <= 15:
            strength += 0.1
        elif self.filing_delay_days <= 30:
            strength += 0.05

        return min(1.0, strength)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "politician": self.politician,
            "chamber": self.chamber.value,
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "trade_type": self.trade_type.value,
            "transaction_date": self.transaction_date.isoformat(),
            "disclosure_date": self.disclosure_date.isoformat(),
            "amount_low": self.amount_low,
            "amount_high": self.amount_high,
            "amount_estimate": self.amount_estimate,
            "asset_description": self.asset_description,
            "comment": self.comment,
            "committees": self.committees,
            "party": self.party,
            "state": self.state,
            "is_notable_trader": self.is_notable_trader,
            "filing_delay_days": self.filing_delay_days,
            "is_significant": self.is_significant,
            "signal_strength": self.signal_strength,
        }


@dataclass
class CongressionalCluster:
    """Cluster of congressional trades in same symbol."""

    symbol: str
    period_start: datetime
    period_end: datetime
    trades: list[CongressionalTrade]

    @property
    def unique_traders(self) -> int:
        """Count unique politicians trading this symbol."""
        return len(set(t.politician for t in self.trades))

    @property
    def total_purchases(self) -> int:
        """Count purchase trades."""
        return sum(1 for t in self.trades if t.trade_type == TradeType.PURCHASE)

    @property
    def total_sales(self) -> int:
        """Count sale trades."""
        return sum(1 for t in self.trades if t.trade_type in
                   [TradeType.SALE, TradeType.SALE_FULL, TradeType.SALE_PARTIAL])

    @property
    def net_sentiment(self) -> float:
        """
        Net sentiment from -1 (all sells) to +1 (all buys).
        """
        buys = self.total_purchases
        sells = self.total_sales
        total = buys + sells
        if total == 0:
            return 0.0
        return (buys - sells) / total

    @property
    def estimated_volume(self) -> float:
        """Total estimated dollar volume."""
        return sum(t.amount_estimate for t in self.trades)

    @property
    def notable_trader_count(self) -> int:
        """Count trades by notable traders."""
        return sum(1 for t in self.trades if t.is_notable_trader)

    @property
    def signal(self) -> str:
        """
        Generate signal based on cluster activity.

        Strong signals:
        - Multiple politicians buying (cluster buying)
        - Notable traders taking positions
        - All buys or all sells (consensus)
        """
        if self.unique_traders >= 3 and self.net_sentiment > 0.5:
            return "strong_bullish"
        elif self.unique_traders >= 2 and self.net_sentiment > 0:
            return "bullish"
        elif self.unique_traders >= 3 and self.net_sentiment < -0.5:
            return "strong_bearish"
        elif self.unique_traders >= 2 and self.net_sentiment < 0:
            return "bearish"
        elif self.notable_trader_count >= 1 and self.net_sentiment > 0:
            return "notable_bullish"
        elif self.notable_trader_count >= 1 and self.net_sentiment < 0:
            return "notable_bearish"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "unique_traders": self.unique_traders,
            "total_purchases": self.total_purchases,
            "total_sales": self.total_sales,
            "net_sentiment": self.net_sentiment,
            "estimated_volume": self.estimated_volume,
            "notable_trader_count": self.notable_trader_count,
            "signal": self.signal,
            "trades": [t.to_dict() for t in self.trades],
        }


# Amount range mapping from disclosure forms
AMOUNT_RANGES = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
    "$25,000,001 - $50,000,000": (25000001, 50000000),
    "Over $50,000,000": (50000001, 100000000),
}


def parse_amount_range(amount_str: str) -> tuple[float, float]:
    """Parse amount range string to (low, high) tuple."""
    # Direct match
    if amount_str in AMOUNT_RANGES:
        return AMOUNT_RANGES[amount_str]

    # Try to extract numbers
    numbers = re.findall(r'[\d,]+', amount_str)
    if len(numbers) >= 2:
        low = float(numbers[0].replace(',', ''))
        high = float(numbers[1].replace(',', ''))
        return (low, high)
    elif len(numbers) == 1:
        val = float(numbers[0].replace(',', ''))
        return (val, val)

    return (0, 0)


class CongressionalTradesSource:
    """
    Congressional trading data source.

    Aggregates data from multiple free sources:
    - House Stock Watcher RSS
    - Senate Stock Watcher RSS
    - Quiver Quant (if API key provided)
    """

    name = "congressional_trades"

    # RSS feed URLs
    HOUSE_RSS = "https://housestockwatcher.com/api/recent-trades-rss"
    SENATE_RSS = "https://senatestockwatcher.com/api/recent-trades-rss"

    def __init__(
        self,
        quiver_api_key: str | None = None,
        cache_ttl_minutes: int = 30,
    ):
        """
        Initialize congressional trades source.

        Args:
            quiver_api_key: Quiver Quant API key (optional)
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.quiver_api_key = quiver_api_key
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None

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

    async def fetch_recent_trades(
        self,
        days: int = 30,
        chamber: Chamber | None = None,
        symbol: str | None = None,
    ) -> list[CongressionalTrade]:
        """
        Fetch recent congressional trades.

        Args:
            days: Number of days to look back
            chamber: Filter by chamber (House/Senate)
            symbol: Filter by symbol

        Returns:
            List of CongressionalTrade objects
        """
        cache_key = f"trades:{days}:{chamber}:{symbol}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        trades = []

        # Fetch from RSS feeds
        if chamber is None or chamber == Chamber.HOUSE:
            house_trades = await self._fetch_rss(self.HOUSE_RSS, Chamber.HOUSE)
            trades.extend(house_trades)

        if chamber is None or chamber == Chamber.SENATE:
            senate_trades = await self._fetch_rss(self.SENATE_RSS, Chamber.SENATE)
            trades.extend(senate_trades)

        # Fetch from Quiver if available
        if self.quiver_api_key:
            quiver_trades = await self._fetch_quiver(days)
            # Deduplicate by merging
            existing_keys = {(t.politician, t.symbol, t.transaction_date.date()) for t in trades}
            for qt in quiver_trades:
                key = (qt.politician, qt.symbol, qt.transaction_date.date())
                if key not in existing_keys:
                    trades.append(qt)

        # Filter by date
        cutoff = datetime.now() - timedelta(days=days)
        trades = [t for t in trades if t.disclosure_date >= cutoff]

        # Filter by symbol if specified
        if symbol:
            trades = [t for t in trades if t.symbol.upper() == symbol.upper()]

        # Sort by disclosure date (newest first)
        trades.sort(key=lambda x: x.disclosure_date, reverse=True)

        if trades:
            self._update_cache(cache_key, trades)

        return trades

    async def _fetch_rss(
        self,
        url: str,
        chamber: Chamber,
    ) -> list[CongressionalTrade]:
        """Fetch trades from RSS feed."""
        client = await self._get_client()
        trades = []

        try:
            resp = await client.get(url)
            resp.raise_for_status()

            # Parse RSS XML
            root = ElementTree.fromstring(resp.text)

            for item in root.findall(".//item"):
                try:
                    title = item.find("title")
                    description = item.find("description")
                    pub_date = item.find("pubDate")

                    if title is None or description is None:
                        continue

                    title_text = title.text or ""
                    desc_text = description.text or ""

                    # Parse title: "Rep. Nancy Pelosi purchased NVDA"
                    match = re.match(
                        r"(?:Rep\.|Sen\.)\s+(.+?)\s+(purchased|sold)\s+(.+)",
                        title_text,
                        re.IGNORECASE,
                    )

                    if not match:
                        continue

                    politician = match.group(1).strip()
                    action = match.group(2).lower()
                    symbol_or_desc = match.group(3).strip()

                    # Extract symbol (first word if ticker-like)
                    symbol_match = re.search(r'\b([A-Z]{1,5})\b', symbol_or_desc)
                    symbol = symbol_match.group(1) if symbol_match else symbol_or_desc[:10]

                    # Parse trade type
                    trade_type = TradeType.PURCHASE if action == "purchased" else TradeType.SALE

                    # Parse amount from description
                    amount_match = re.search(r'\$[\d,]+\s*-\s*\$[\d,]+', desc_text)
                    if amount_match:
                        amount_low, amount_high = parse_amount_range(amount_match.group())
                    else:
                        amount_low, amount_high = 0, 0

                    # Parse dates
                    disclosure_date = datetime.now()
                    if pub_date is not None and pub_date.text:
                        try:
                            disclosure_date = datetime.strptime(
                                pub_date.text[:25],
                                "%a, %d %b %Y %H:%M:%S",
                            )
                        except ValueError:
                            pass

                    # Transaction date from description
                    trans_match = re.search(r'Transaction Date:\s*(\d{4}-\d{2}-\d{2})', desc_text)
                    if trans_match:
                        transaction_date = datetime.strptime(trans_match.group(1), "%Y-%m-%d")
                    else:
                        transaction_date = disclosure_date - timedelta(days=30)

                    trades.append(CongressionalTrade(
                        politician=politician,
                        chamber=chamber,
                        symbol=symbol,
                        asset_type=AssetType.STOCK,
                        trade_type=trade_type,
                        transaction_date=transaction_date,
                        disclosure_date=disclosure_date,
                        amount_low=amount_low,
                        amount_high=amount_high,
                        asset_description=symbol_or_desc,
                    ))

                except Exception as e:
                    logger.debug(f"Error parsing RSS item: {e}")

        except Exception as e:
            logger.error(f"Error fetching RSS from {url}: {e}")

        return trades

    async def _fetch_quiver(self, days: int) -> list[CongressionalTrade]:
        """Fetch from Quiver Quant API."""
        if not self.quiver_api_key:
            return []

        client = await self._get_client()
        trades = []

        try:
            # Quiver Quant congress trading endpoint
            url = "https://api.quiverquant.com/beta/historical/congresstrading"
            headers = {"Authorization": f"Bearer {self.quiver_api_key}"}

            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            cutoff = datetime.now() - timedelta(days=days)

            for item in data:
                try:
                    trans_date_str = item.get("TransactionDate", "")
                    disc_date_str = item.get("ReportDate", trans_date_str)

                    trans_date = datetime.strptime(trans_date_str, "%Y-%m-%d") if trans_date_str else datetime.now()
                    disc_date = datetime.strptime(disc_date_str, "%Y-%m-%d") if disc_date_str else trans_date

                    if disc_date < cutoff:
                        continue

                    # Map trade type
                    trans_type_str = item.get("Transaction", "").lower()
                    if "purchase" in trans_type_str or "buy" in trans_type_str:
                        trade_type = TradeType.PURCHASE
                    elif "sale" in trans_type_str:
                        if "full" in trans_type_str:
                            trade_type = TradeType.SALE_FULL
                        elif "partial" in trans_type_str:
                            trade_type = TradeType.SALE_PARTIAL
                        else:
                            trade_type = TradeType.SALE
                    else:
                        trade_type = TradeType.UNKNOWN

                    # Map chamber
                    chamber_str = item.get("Chamber", "").lower()
                    if "house" in chamber_str:
                        chamber = Chamber.HOUSE
                    elif "senate" in chamber_str:
                        chamber = Chamber.SENATE
                    else:
                        chamber = Chamber.UNKNOWN

                    # Parse amount
                    amount_str = item.get("Range", "$0 - $0")
                    amount_low, amount_high = parse_amount_range(amount_str)

                    trades.append(CongressionalTrade(
                        politician=item.get("Representative", "Unknown"),
                        chamber=chamber,
                        symbol=item.get("Ticker", ""),
                        asset_type=AssetType.STOCK,
                        trade_type=trade_type,
                        transaction_date=trans_date,
                        disclosure_date=disc_date,
                        amount_low=amount_low,
                        amount_high=amount_high,
                        asset_description=item.get("Description"),
                        party=item.get("Party"),
                        state=item.get("State"),
                    ))

                except Exception as e:
                    logger.debug(f"Error parsing Quiver item: {e}")

        except Exception as e:
            logger.error(f"Error fetching from Quiver: {e}")

        return trades

    async def get_clusters(
        self,
        days: int = 30,
        min_traders: int = 2,
    ) -> list[CongressionalCluster]:
        """
        Find clusters of congressional activity in same symbols.

        Multiple politicians trading same stock = strong signal.

        Args:
            days: Lookback period
            min_traders: Minimum unique traders for cluster

        Returns:
            List of CongressionalCluster objects
        """
        trades = await self.fetch_recent_trades(days=days)

        # Group by symbol
        by_symbol: dict[str, list[CongressionalTrade]] = {}
        for trade in trades:
            if trade.symbol not in by_symbol:
                by_symbol[trade.symbol] = []
            by_symbol[trade.symbol].append(trade)

        # Build clusters
        clusters = []
        period_end = datetime.now()
        period_start = period_end - timedelta(days=days)

        for symbol, symbol_trades in by_symbol.items():
            unique_traders = len(set(t.politician for t in symbol_trades))
            if unique_traders >= min_traders:
                clusters.append(CongressionalCluster(
                    symbol=symbol,
                    period_start=period_start,
                    period_end=period_end,
                    trades=symbol_trades,
                ))

        # Sort by unique traders (most interest first)
        clusters.sort(key=lambda x: x.unique_traders, reverse=True)

        return clusters

    async def get_notable_trades(
        self,
        days: int = 30,
    ) -> list[CongressionalTrade]:
        """
        Get trades by notable/influential traders.

        Args:
            days: Lookback period

        Returns:
            List of trades by notable politicians
        """
        trades = await self.fetch_recent_trades(days=days)
        return [t for t in trades if t.is_notable_trader]

    async def get_pelosi_trades(
        self,
        days: int = 90,
    ) -> list[CongressionalTrade]:
        """
        Get Nancy Pelosi's recent trades.

        She (or her husband) have famously good timing.

        Args:
            days: Lookback period

        Returns:
            List of Pelosi trades
        """
        trades = await self.fetch_recent_trades(days=days)
        return [t for t in trades if "pelosi" in t.politician.lower()]

    async def get_committee_trades(
        self,
        committee: str,
        days: int = 30,
    ) -> list[CongressionalTrade]:
        """
        Get trades by members of a specific committee.

        Committee members may have advance knowledge
        of legislation affecting certain sectors.

        Args:
            committee: Committee name (partial match)
            days: Lookback period

        Returns:
            List of trades by committee members
        """
        # This would require committee membership data
        # For now, return all trades with committee in metadata
        trades = await self.fetch_recent_trades(days=days)
        committee_lower = committee.lower()
        return [t for t in trades if any(
            committee_lower in c.lower() for c in t.committees
        )]

    def to_dataframe(
        self,
        trades: list[CongressionalTrade],
    ) -> pd.DataFrame:
        """Convert trades to DataFrame."""
        if not trades:
            return pd.DataFrame()

        records = [t.to_dict() for t in trades]
        df = pd.DataFrame(records)

        if "disclosure_date" in df.columns:
            df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])
            df = df.sort_values("disclosure_date", ascending=False)

        return df


async def fetch_congressional_trades(
    days: int = 30,
    symbol: str | None = None,
    quiver_api_key: str | None = None,
) -> list[CongressionalTrade]:
    """
    Convenience function to fetch congressional trades.

    Args:
        days: Lookback period
        symbol: Filter by symbol
        quiver_api_key: Quiver Quant API key

    Returns:
        List of CongressionalTrade objects
    """
    source = CongressionalTradesSource(quiver_api_key=quiver_api_key)

    try:
        return await source.fetch_recent_trades(days=days, symbol=symbol)
    finally:
        await source.close()


async def find_congressional_clusters(
    days: int = 30,
    min_traders: int = 2,
    quiver_api_key: str | None = None,
) -> list[CongressionalCluster]:
    """
    Find symbols with multiple congressional traders.

    Args:
        days: Lookback period
        min_traders: Minimum unique traders
        quiver_api_key: Quiver Quant API key

    Returns:
        List of CongressionalCluster objects
    """
    source = CongressionalTradesSource(quiver_api_key=quiver_api_key)

    try:
        return await source.get_clusters(days=days, min_traders=min_traders)
    finally:
        await source.close()
