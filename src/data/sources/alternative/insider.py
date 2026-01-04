"""Insider trading data source from SEC Form 4 filings.

Tracks insider buying and selling activity for trading signals.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)


class TransactionType(str, Enum):
    """Type of insider transaction."""

    PURCHASE = "P"  # Open market purchase
    SALE = "S"  # Open market sale
    ACQUISITION = "A"  # Acquisition (award, exercise)
    DISPOSITION = "D"  # Disposition (not sale)
    EXERCISE = "M"  # Exercise of derivative
    CONVERSION = "C"  # Conversion
    GIFT = "G"  # Gift


class InsiderRole(str, Enum):
    """Role of insider in the company."""

    CEO = "CEO"
    CFO = "CFO"
    COO = "COO"
    PRESIDENT = "President"
    DIRECTOR = "Director"
    VP = "VP"
    OFFICER = "Officer"
    TEN_PCT_OWNER = "10% Owner"
    OTHER = "Other"


@dataclass
class InsiderTransaction:
    """Single insider transaction from Form 4."""

    symbol: str
    company_name: str
    insider_name: str
    insider_role: InsiderRole
    transaction_type: TransactionType
    transaction_date: datetime
    filing_date: datetime
    shares: int
    price: float
    value: float
    shares_owned_after: int
    is_direct: bool = True  # Direct vs indirect ownership
    footnotes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_purchase(self) -> bool:
        """Check if this is a purchase transaction."""
        return self.transaction_type == TransactionType.PURCHASE

    @property
    def is_sale(self) -> bool:
        """Check if this is a sale transaction."""
        return self.transaction_type == TransactionType.SALE

    @property
    def ownership_change_pct(self) -> float:
        """Calculate percentage change in ownership."""
        if self.shares_owned_after == 0:
            return -100.0
        prev_shares = self.shares_owned_after - self.shares
        if prev_shares <= 0:
            return float('inf')
        return (self.shares / prev_shares) * 100

    @property
    def is_cluster_buy(self) -> bool:
        """Check if transaction is significant cluster buying."""
        return self.is_purchase and self.value >= 100_000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "insider_name": self.insider_name,
            "insider_role": self.insider_role.value,
            "transaction_type": self.transaction_type.value,
            "transaction_date": self.transaction_date.isoformat(),
            "filing_date": self.filing_date.isoformat(),
            "shares": self.shares,
            "price": self.price,
            "value": self.value,
            "shares_owned_after": self.shares_owned_after,
            "is_direct": self.is_direct,
            "is_purchase": self.is_purchase,
            "ownership_change_pct": self.ownership_change_pct,
            **self.metadata,
        }


@dataclass
class InsiderSummary:
    """Aggregated insider activity summary for a symbol."""

    symbol: str
    period_start: datetime
    period_end: datetime
    total_purchases: int
    total_sales: int
    total_buy_value: float
    total_sell_value: float
    unique_buyers: int
    unique_sellers: int
    net_shares: int
    net_value: float
    largest_buy: InsiderTransaction | None = None
    largest_sale: InsiderTransaction | None = None
    c_suite_activity: list[InsiderTransaction] = field(default_factory=list)

    @property
    def buy_sell_ratio(self) -> float:
        """Ratio of buys to sells by count."""
        if self.total_sales == 0:
            return float('inf') if self.total_purchases > 0 else 1.0
        return self.total_purchases / self.total_sales

    @property
    def value_ratio(self) -> float:
        """Ratio of buy value to sell value."""
        if self.total_sell_value == 0:
            return float('inf') if self.total_buy_value > 0 else 1.0
        return self.total_buy_value / self.total_sell_value

    @property
    def signal(self) -> str:
        """Determine signal strength from insider activity."""
        # Strong buy signal: multiple insiders buying, no selling
        if self.unique_buyers >= 3 and self.unique_sellers == 0:
            return "strong_bullish"

        # Bullish: net buying
        if self.net_value > 0 and self.buy_sell_ratio >= 2:
            return "bullish"

        # Bearish: net selling, especially from C-suite
        c_suite_sells = sum(
            1 for t in self.c_suite_activity if t.is_sale
        )
        if c_suite_sells >= 2 or self.value_ratio < 0.3:
            return "bearish"

        # Strong bearish: multiple C-suite selling
        if c_suite_sells >= 3:
            return "strong_bearish"

        return "neutral"

    @property
    def cluster_buying(self) -> bool:
        """Check for cluster buying pattern (multiple insiders buying)."""
        return self.unique_buyers >= 3 and self.total_buy_value >= 500_000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_purchases": self.total_purchases,
            "total_sales": self.total_sales,
            "total_buy_value": self.total_buy_value,
            "total_sell_value": self.total_sell_value,
            "unique_buyers": self.unique_buyers,
            "unique_sellers": self.unique_sellers,
            "net_shares": self.net_shares,
            "net_value": self.net_value,
            "buy_sell_ratio": self.buy_sell_ratio,
            "value_ratio": self.value_ratio,
            "signal": self.signal,
            "cluster_buying": self.cluster_buying,
        }


class InsiderDataSource:
    """
    Insider trading data source from SEC filings.

    Fetches Form 4 insider transactions for trading signals.
    """

    name = "insider_trading"

    # SEC EDGAR endpoints
    SEC_BASE_URL = "https://www.sec.gov"
    SEC_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index"

    def __init__(
        self,
        finnhub_key: str | None = None,
        polygon_key: str | None = None,
        cache_ttl_minutes: int = 60,
    ):
        """
        Initialize insider data source.

        Args:
            finnhub_key: Finnhub API key
            polygon_key: Polygon.io API key
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.finnhub_key = finnhub_key
        self.polygon_key = polygon_key
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
                    "Accept": "application/json",
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

    def _parse_role(self, role_str: str) -> InsiderRole:
        """Parse insider role from string."""
        role_upper = role_str.upper()

        if "CEO" in role_upper or "CHIEF EXECUTIVE" in role_upper:
            return InsiderRole.CEO
        elif "CFO" in role_upper or "CHIEF FINANCIAL" in role_upper:
            return InsiderRole.CFO
        elif "COO" in role_upper or "CHIEF OPERATING" in role_upper:
            return InsiderRole.COO
        elif "PRESIDENT" in role_upper:
            return InsiderRole.PRESIDENT
        elif "DIRECTOR" in role_upper:
            return InsiderRole.DIRECTOR
        elif "VP" in role_upper or "VICE PRESIDENT" in role_upper:
            return InsiderRole.VP
        elif "10%" in role_str:
            return InsiderRole.TEN_PCT_OWNER
        elif "OFFICER" in role_upper:
            return InsiderRole.OFFICER
        else:
            return InsiderRole.OTHER

    async def fetch_transactions(
        self,
        symbol: Symbol,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[InsiderTransaction]:
        """
        Fetch insider transactions for a symbol.

        Args:
            symbol: Stock symbol
            start: Start date
            end: End date
            limit: Maximum transactions

        Returns:
            List of InsiderTransaction objects
        """
        cache_key = f"insider:{symbol}:{start}:{end}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        transactions = []

        # Try Finnhub first, then Polygon
        if self.finnhub_key:
            transactions = await self._fetch_finnhub(symbol, start, end)
        elif self.polygon_key:
            transactions = await self._fetch_polygon(symbol, start, end)

        # Filter by date range
        if start:
            transactions = [t for t in transactions if t.transaction_date >= start]
        if end:
            transactions = [t for t in transactions if t.transaction_date <= end]

        # Sort by date (newest first)
        transactions.sort(key=lambda x: x.transaction_date, reverse=True)
        transactions = transactions[:limit]

        if transactions:
            self._update_cache(cache_key, transactions)

        return transactions

    async def _fetch_finnhub(
        self,
        symbol: Symbol,
        start: datetime | None,
        end: datetime | None,
    ) -> list[InsiderTransaction]:
        """Fetch from Finnhub insider transactions API."""
        client = await self._get_client()
        transactions = []

        try:
            url = "https://finnhub.io/api/v1/stock/insider-transactions"
            params = {
                "symbol": symbol,
                "token": self.finnhub_key,
            }

            if start:
                params["from"] = start.strftime("%Y-%m-%d")
            if end:
                params["to"] = end.strftime("%Y-%m-%d")

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                try:
                    trans_date = datetime.strptime(
                        item.get("transactionDate", ""),
                        "%Y-%m-%d",
                    )
                    filing_date = datetime.strptime(
                        item.get("filingDate", item.get("transactionDate", "")),
                        "%Y-%m-%d",
                    )

                    # Parse transaction code
                    trans_code = item.get("transactionCode", "P")
                    if trans_code == "P":
                        trans_type = TransactionType.PURCHASE
                    elif trans_code == "S":
                        trans_type = TransactionType.SALE
                    elif trans_code == "A":
                        trans_type = TransactionType.ACQUISITION
                    elif trans_code == "M":
                        trans_type = TransactionType.EXERCISE
                    elif trans_code == "G":
                        trans_type = TransactionType.GIFT
                    else:
                        trans_type = TransactionType.DISPOSITION

                    shares = abs(int(item.get("share", 0)))
                    price = float(item.get("transactionPrice", 0) or 0)
                    value = shares * price

                    transactions.append(InsiderTransaction(
                        symbol=symbol,
                        company_name=item.get("name", symbol),
                        insider_name=item.get("name", "Unknown"),
                        insider_role=self._parse_role(item.get("position", "")),
                        transaction_type=trans_type,
                        transaction_date=trans_date,
                        filing_date=filing_date,
                        shares=shares,
                        price=price,
                        value=value,
                        shares_owned_after=int(item.get("share", 0)),
                        is_direct=True,
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Finnhub insider: {e}")

        except Exception as e:
            logger.error(f"Finnhub insider fetch error: {e}")

        return transactions

    async def _fetch_polygon(
        self,
        symbol: Symbol,
        start: datetime | None,
        end: datetime | None,
    ) -> list[InsiderTransaction]:
        """Fetch from Polygon.io insider transactions."""
        client = await self._get_client()
        transactions = []

        try:
            url = f"https://api.polygon.io/v3/reference/insiders/{symbol}/transactions"
            params = {"apiKey": self.polygon_key, "limit": 100}

            if start:
                params["filing_date.gte"] = start.strftime("%Y-%m-%d")
            if end:
                params["filing_date.lte"] = end.strftime("%Y-%m-%d")

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", []):
                try:
                    trans_date_str = item.get("transaction_date", "")
                    filing_date_str = item.get("filing_date", trans_date_str)

                    trans_date = datetime.strptime(trans_date_str, "%Y-%m-%d") if trans_date_str else datetime.now()
                    filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d") if filing_date_str else trans_date

                    # Map transaction type
                    acq_disp = item.get("acquisition_or_disposition", "A")
                    if acq_disp == "A":
                        trans_type = TransactionType.PURCHASE
                    else:
                        trans_type = TransactionType.SALE

                    shares = abs(int(item.get("shares", 0)))
                    price = float(item.get("price_per_share", 0) or 0)
                    value = shares * price

                    insider_info = item.get("reporting_owner", {})

                    transactions.append(InsiderTransaction(
                        symbol=symbol,
                        company_name=item.get("issuer", {}).get("name", symbol),
                        insider_name=insider_info.get("name", "Unknown"),
                        insider_role=self._parse_role(
                            insider_info.get("relationship", {}).get("officer_title", "")
                        ),
                        transaction_type=trans_type,
                        transaction_date=trans_date,
                        filing_date=filing_date,
                        shares=shares,
                        price=price,
                        value=value,
                        shares_owned_after=int(item.get("shares_owned_following_transaction", 0)),
                        is_direct=item.get("ownership_nature", "") == "D",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Polygon insider: {e}")

        except Exception as e:
            logger.error(f"Polygon insider fetch error: {e}")

        return transactions

    async def get_summary(
        self,
        symbol: Symbol,
        days: int = 90,
    ) -> InsiderSummary:
        """
        Get insider activity summary for a symbol.

        Args:
            symbol: Stock symbol
            days: Number of days to look back

        Returns:
            InsiderSummary with aggregated metrics
        """
        end = datetime.now()
        start = end - timedelta(days=days)

        transactions = await self.fetch_transactions(symbol, start, end)

        if not transactions:
            return InsiderSummary(
                symbol=symbol,
                period_start=start,
                period_end=end,
                total_purchases=0,
                total_sales=0,
                total_buy_value=0,
                total_sell_value=0,
                unique_buyers=0,
                unique_sellers=0,
                net_shares=0,
                net_value=0,
            )

        # Aggregate metrics
        purchases = [t for t in transactions if t.is_purchase]
        sales = [t for t in transactions if t.is_sale]

        total_buy_value = sum(t.value for t in purchases)
        total_sell_value = sum(t.value for t in sales)
        total_buy_shares = sum(t.shares for t in purchases)
        total_sell_shares = sum(t.shares for t in sales)

        unique_buyers = len(set(t.insider_name for t in purchases))
        unique_sellers = len(set(t.insider_name for t in sales))

        # Find largest transactions
        largest_buy = max(purchases, key=lambda x: x.value) if purchases else None
        largest_sale = max(sales, key=lambda x: x.value) if sales else None

        # C-suite activity
        c_suite_roles = {InsiderRole.CEO, InsiderRole.CFO, InsiderRole.COO, InsiderRole.PRESIDENT}
        c_suite = [t for t in transactions if t.insider_role in c_suite_roles]

        return InsiderSummary(
            symbol=symbol,
            period_start=start,
            period_end=end,
            total_purchases=len(purchases),
            total_sales=len(sales),
            total_buy_value=total_buy_value,
            total_sell_value=total_sell_value,
            unique_buyers=unique_buyers,
            unique_sellers=unique_sellers,
            net_shares=total_buy_shares - total_sell_shares,
            net_value=total_buy_value - total_sell_value,
            largest_buy=largest_buy,
            largest_sale=largest_sale,
            c_suite_activity=c_suite,
        )

    async def get_cluster_buying(
        self,
        symbols: list[Symbol] | None = None,
        days: int = 30,
        min_buyers: int = 3,
        min_value: float = 500_000,
    ) -> list[InsiderSummary]:
        """
        Find stocks with cluster buying pattern.

        Cluster buying: multiple insiders buying around same time.
        This is historically a strong bullish signal.

        Args:
            symbols: Symbols to check
            days: Lookback period
            min_buyers: Minimum unique buyers
            min_value: Minimum total buy value

        Returns:
            List of InsiderSummary for stocks with cluster buying
        """
        if symbols is None:
            # Default to S&P 500 subset
            symbols = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
                "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD",
            ]

        cluster_stocks = []

        for symbol in symbols:
            try:
                summary = await self.get_summary(symbol, days)

                if summary.unique_buyers >= min_buyers and summary.total_buy_value >= min_value:
                    cluster_stocks.append(summary)

                await asyncio.sleep(0.3)  # Rate limiting

            except Exception as e:
                logger.warning(f"Error checking cluster buying for {symbol}: {e}")

        # Sort by buy value
        cluster_stocks.sort(key=lambda x: x.total_buy_value, reverse=True)
        return cluster_stocks

    async def get_c_suite_activity(
        self,
        symbols: list[Symbol] | None = None,
        days: int = 30,
    ) -> dict[str, list[InsiderTransaction]]:
        """
        Get C-suite (CEO, CFO, COO) activity across symbols.

        Args:
            symbols: Symbols to check
            days: Lookback period

        Returns:
            Dict mapping symbols to C-suite transactions
        """
        if symbols is None:
            symbols = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
            ]

        results = {}
        c_suite_roles = {InsiderRole.CEO, InsiderRole.CFO, InsiderRole.COO, InsiderRole.PRESIDENT}

        for symbol in symbols:
            try:
                end = datetime.now()
                start = end - timedelta(days=days)

                transactions = await self.fetch_transactions(symbol, start, end)
                c_suite = [t for t in transactions if t.insider_role in c_suite_roles]

                if c_suite:
                    results[symbol] = c_suite

                await asyncio.sleep(0.3)

            except Exception as e:
                logger.warning(f"Error fetching C-suite activity for {symbol}: {e}")

        return results

    def to_dataframe(
        self,
        transactions: list[InsiderTransaction],
    ) -> pd.DataFrame:
        """Convert transactions to DataFrame."""
        if not transactions:
            return pd.DataFrame()

        records = [t.to_dict() for t in transactions]
        df = pd.DataFrame(records)

        if "transaction_date" in df.columns:
            df["transaction_date"] = pd.to_datetime(df["transaction_date"])
            df = df.sort_values("transaction_date", ascending=False)

        return df


class Form4Monitor:
    """
    Real-time Form 4 filing monitor.

    Monitors SEC EDGAR for new insider filings.
    """

    SEC_RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self, symbols: list[Symbol] | None = None):
        """
        Initialize Form 4 monitor.

        Args:
            symbols: Symbols to monitor (None for all)
        """
        self.symbols = set(symbols) if symbols else None
        self._client: httpx.AsyncClient | None = None
        self._last_check: datetime | None = None
        self._seen_filings: set[str] = set()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0 (research@example.com)"},
            )
        return self._client

    async def close(self) -> None:
        """Close client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def check_new_filings(self) -> list[dict[str, Any]]:
        """
        Check for new Form 4 filings.

        Returns:
            List of new filing metadata
        """
        client = await self._get_client()
        new_filings = []

        try:
            # SEC EDGAR RSS for Form 4 filings
            url = f"{self.SEC_RSS_URL}"
            params = {
                "action": "getcurrent",
                "type": "4",
                "company": "",
                "dateb": "",
                "owner": "include",
                "count": 40,
                "output": "atom",
            }

            resp = await client.get(url, params=params)
            resp.raise_for_status()

            # Parse RSS/Atom feed (simplified)
            content = resp.text

            # Extract entries (simplified parsing)
            entry_pattern = re.compile(
                r'<entry>.*?<title>(.*?)</title>.*?<link.*?href="(.*?)".*?</entry>',
                re.DOTALL,
            )

            for match in entry_pattern.finditer(content):
                title = match.group(1)
                link = match.group(2)

                # Extract symbol from title if possible
                symbol_match = re.search(r'\(([A-Z]{1,5})\)', title)
                symbol = symbol_match.group(1) if symbol_match else None

                # Filter by watched symbols
                if self.symbols and symbol and symbol not in self.symbols:
                    continue

                # Check if we've seen this filing
                filing_id = link.split("/")[-1] if link else title
                if filing_id in self._seen_filings:
                    continue

                self._seen_filings.add(filing_id)
                new_filings.append({
                    "title": title,
                    "link": link,
                    "symbol": symbol,
                    "timestamp": datetime.now(),
                })

            self._last_check = datetime.now()

        except Exception as e:
            logger.error(f"Error checking Form 4 filings: {e}")

        return new_filings


async def fetch_insider_summary(
    symbol: Symbol,
    days: int = 90,
    finnhub_key: str | None = None,
    polygon_key: str | None = None,
) -> InsiderSummary:
    """
    Convenience function to fetch insider activity summary.

    Args:
        symbol: Stock symbol
        days: Lookback period
        finnhub_key: Finnhub API key
        polygon_key: Polygon API key

    Returns:
        InsiderSummary
    """
    source = InsiderDataSource(
        finnhub_key=finnhub_key,
        polygon_key=polygon_key,
    )

    try:
        return await source.get_summary(symbol, days)
    finally:
        await source.close()


async def find_cluster_buying(
    symbols: list[Symbol] | None = None,
    days: int = 30,
    finnhub_key: str | None = None,
    polygon_key: str | None = None,
) -> list[InsiderSummary]:
    """
    Find stocks with cluster insider buying.

    Args:
        symbols: Symbols to check
        days: Lookback period
        finnhub_key: Finnhub API key
        polygon_key: Polygon API key

    Returns:
        List of InsiderSummary for stocks with cluster buying
    """
    source = InsiderDataSource(
        finnhub_key=finnhub_key,
        polygon_key=polygon_key,
    )

    try:
        return await source.get_cluster_buying(symbols, days)
    finally:
        await source.close()
