"""Base data source interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import pandas as pd

from ...core import AssetType, Symbol, Timeframe


class DataSource(ABC):
    """
    Abstract base class for all data sources.

    All data sources must implement the core methods for fetching
    historical and real-time market data.
    """

    name: str = "base"
    supported_asset_types: list[AssetType] = []
    supported_timeframes: list[Timeframe] = []

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a symbol.

        Args:
            symbol: The asset symbol
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe/frequency

        Returns:
            DataFrame with columns: ['open', 'high', 'low', 'close', 'volume']
            Index should be DatetimeIndex
        """
        ...

    @abstractmethod
    async def fetch_multiple(
        self,
        symbols: list[Symbol],
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> dict[Symbol, pd.DataFrame]:
        """
        Fetch historical OHLCV data for multiple symbols.

        Args:
            symbols: List of asset symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe/frequency

        Returns:
            Dictionary mapping symbols to DataFrames
        """
        ...

    async def fetch_realtime(self, symbols: list[Symbol]) -> pd.DataFrame:
        """
        Fetch real-time quotes for symbols.

        Default implementation raises NotImplementedError.
        Override in subclasses that support real-time data.

        Args:
            symbols: List of asset symbols

        Returns:
            DataFrame with latest quotes
        """
        raise NotImplementedError(f"{self.name} does not support real-time data")

    async def get_asset_info(self, symbol: Symbol) -> dict[str, Any]:
        """
        Get asset metadata/info.

        Default implementation returns empty dict.
        Override in subclasses that provide asset info.

        Args:
            symbol: The asset symbol

        Returns:
            Dictionary with asset information
        """
        return {}

    async def search_symbols(self, query: str) -> list[dict[str, Any]]:
        """
        Search for symbols matching a query.

        Default implementation returns empty list.
        Override in subclasses that support symbol search.

        Args:
            query: Search query string

        Returns:
            List of matching symbols with metadata
        """
        return []

    def validate_symbol(self, symbol: Symbol) -> bool:
        """
        Validate that a symbol is supported.

        Default implementation returns True.
        Override for data sources with specific symbol formats.

        Args:
            symbol: The symbol to validate

        Returns:
            True if symbol is valid for this data source
        """
        return True

    def supports_timeframe(self, timeframe: Timeframe) -> bool:
        """Check if the data source supports a timeframe."""
        return timeframe in self.supported_timeframes or not self.supported_timeframes

    def supports_asset_type(self, asset_type: AssetType) -> bool:
        """Check if the data source supports an asset type."""
        return asset_type in self.supported_asset_types or not self.supported_asset_types


class DataSourceError(Exception):
    """Base exception for data source errors."""

    pass


class SymbolNotFoundError(DataSourceError):
    """Raised when a symbol cannot be found."""

    def __init__(self, symbol: str, source: str = ""):
        self.symbol = symbol
        self.source = source
        super().__init__(f"Symbol '{symbol}' not found" + (f" in {source}" if source else ""))


class RateLimitError(DataSourceError):
    """Raised when rate limit is exceeded."""

    def __init__(self, source: str, retry_after: float | None = None):
        self.source = source
        self.retry_after = retry_after
        msg = f"Rate limit exceeded for {source}"
        if retry_after:
            msg += f", retry after {retry_after}s"
        super().__init__(msg)


class DataUnavailableError(DataSourceError):
    """Raised when data is not available for the requested period."""

    def __init__(self, symbol: str, start: datetime, end: datetime):
        self.symbol = symbol
        self.start = start
        self.end = end
        super().__init__(
            f"Data unavailable for {symbol} from {start.date()} to {end.date()}"
        )
