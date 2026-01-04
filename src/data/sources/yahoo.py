"""Yahoo Finance data source."""

import asyncio
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf

from ...core import AssetType, Symbol, Timeframe
from .base import DataSource, DataSourceError, SymbolNotFoundError


# Map our Timeframe enum to yfinance interval strings
TIMEFRAME_MAP = {
    Timeframe.MINUTE_1: "1m",
    Timeframe.MINUTE_5: "5m",
    Timeframe.MINUTE_15: "15m",
    Timeframe.MINUTE_30: "30m",
    Timeframe.HOUR_1: "1h",
    Timeframe.HOUR_4: "4h",  # Note: yfinance may not support 4h directly
    Timeframe.DAILY: "1d",
    Timeframe.WEEKLY: "1wk",
    Timeframe.MONTHLY: "1mo",
}


class YahooFinanceSource(DataSource):
    """
    Yahoo Finance data source using yfinance library.

    Provides free access to historical OHLCV data for stocks, ETFs,
    indices, and some crypto pairs.
    """

    name = "yahoo_finance"
    supported_asset_types = [AssetType.EQUITY, AssetType.ETF, AssetType.CRYPTO]
    supported_timeframes = list(TIMEFRAME_MAP.keys())

    def __init__(self, rate_limit_delay: float = 0.5):
        """
        Initialize Yahoo Finance data source.

        Args:
            rate_limit_delay: Delay between requests in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0

    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to lowercase."""
        df.columns = df.columns.str.lower()
        # Keep only OHLCV columns
        columns = ["open", "high", "low", "close", "volume"]
        available = [c for c in columns if c in df.columns]
        return df[available]

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a symbol from Yahoo Finance.

        Args:
            symbol: The ticker symbol (e.g., 'AAPL', 'BTC-USD')
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe/frequency

        Returns:
            DataFrame with columns: ['open', 'high', 'low', 'close', 'volume']
        """
        await self._rate_limit()

        interval = TIMEFRAME_MAP.get(timeframe, "1d")

        try:
            # Run yfinance in thread pool since it's blocking
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: yf.download(
                    symbol,
                    start=start,
                    end=end,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                ),
            )
        except Exception as e:
            raise DataSourceError(f"Failed to fetch data for {symbol}: {e}") from e

        if df.empty:
            raise SymbolNotFoundError(symbol, self.name)

        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        return self._normalize_columns(df)

    async def fetch_multiple(
        self,
        symbols: list[Symbol],
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> dict[Symbol, pd.DataFrame]:
        """
        Fetch historical OHLCV data for multiple symbols.

        Uses yfinance batch download for efficiency.

        Args:
            symbols: List of ticker symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe/frequency

        Returns:
            Dictionary mapping symbols to DataFrames
        """
        await self._rate_limit()

        interval = TIMEFRAME_MAP.get(timeframe, "1d")

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                lambda: yf.download(
                    symbols,
                    start=start,
                    end=end,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                    group_by="ticker",
                ),
            )
        except Exception as e:
            raise DataSourceError(f"Failed to fetch data: {e}") from e

        result: dict[Symbol, pd.DataFrame] = {}

        if len(symbols) == 1:
            # Single symbol - not grouped
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)
                result[symbols[0]] = self._normalize_columns(data)
        else:
            # Multiple symbols - grouped by ticker
            for symbol in symbols:
                try:
                    if symbol in data.columns.get_level_values(0):
                        df = data[symbol].copy()
                        df.columns = df.columns.str.lower()
                        if not df.dropna(how="all").empty:
                            result[symbol] = self._normalize_columns(df.dropna())
                except (KeyError, AttributeError):
                    continue

        return result

    async def fetch_realtime(self, symbols: list[Symbol]) -> pd.DataFrame:
        """
        Fetch current quotes for symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            DataFrame with latest quotes
        """
        await self._rate_limit()

        rows = []
        for symbol in symbols:
            try:
                loop = asyncio.get_event_loop()
                ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
                info = await loop.run_in_executor(None, lambda: ticker.info)

                rows.append({
                    "symbol": symbol,
                    "price": info.get("regularMarketPrice") or info.get("currentPrice"),
                    "bid": info.get("bid"),
                    "ask": info.get("ask"),
                    "volume": info.get("regularMarketVolume"),
                    "market_cap": info.get("marketCap"),
                    "timestamp": datetime.now(),
                })
            except Exception:
                continue

        return pd.DataFrame(rows)

    async def get_asset_info(self, symbol: Symbol) -> dict[str, Any]:
        """
        Get asset metadata from Yahoo Finance.

        Args:
            symbol: The ticker symbol

        Returns:
            Dictionary with asset information
        """
        await self._rate_limit()

        try:
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
            info = await loop.run_in_executor(None, lambda: ticker.info)

            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency", "USD"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "description": info.get("longBusinessSummary"),
            }
        except Exception as e:
            raise DataSourceError(f"Failed to get info for {symbol}: {e}") from e

    async def search_symbols(self, query: str) -> list[dict[str, Any]]:
        """
        Search for symbols matching a query.

        Note: yfinance has limited search capability.

        Args:
            query: Search query string

        Returns:
            List of matching symbols with metadata
        """
        # yfinance doesn't have great search, so we try to get info directly
        try:
            info = await self.get_asset_info(query.upper())
            if info.get("name"):
                return [info]
        except DataSourceError:
            pass
        return []

    def validate_symbol(self, symbol: Symbol) -> bool:
        """
        Validate that a symbol format is correct for Yahoo Finance.

        Args:
            symbol: The symbol to validate

        Returns:
            True if symbol format is valid
        """
        # Basic validation - alphanumeric with optional ., -, ^
        import re
        return bool(re.match(r"^[A-Za-z0-9\.\-\^]+$", symbol))
