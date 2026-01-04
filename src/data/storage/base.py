"""Base storage interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ...core import Symbol, Timeframe


class Storage(ABC):
    """
    Abstract base class for data storage backends.

    Provides a common interface for storing and retrieving
    market data across different storage backends.
    """

    @abstractmethod
    def save(
        self,
        symbol: Symbol,
        data: pd.DataFrame,
        timeframe: Timeframe = Timeframe.DAILY,
        **kwargs: Any,
    ) -> None:
        """
        Save OHLCV data for a symbol.

        Args:
            symbol: The asset symbol
            data: DataFrame with OHLCV data
            timeframe: Data timeframe
            **kwargs: Additional storage options
        """
        ...

    @abstractmethod
    def load(
        self,
        symbol: Symbol,
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Load OHLCV data for a symbol.

        Args:
            symbol: The asset symbol
            start: Optional start datetime filter
            end: Optional end datetime filter
            timeframe: Data timeframe

        Returns:
            DataFrame with OHLCV data
        """
        ...

    @abstractmethod
    def exists(self, symbol: Symbol, timeframe: Timeframe = Timeframe.DAILY) -> bool:
        """
        Check if data exists for a symbol.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            True if data exists
        """
        ...

    @abstractmethod
    def list_symbols(self, timeframe: Timeframe = Timeframe.DAILY) -> list[Symbol]:
        """
        List all symbols with stored data.

        Args:
            timeframe: Data timeframe

        Returns:
            List of symbols
        """
        ...

    @abstractmethod
    def get_date_range(
        self,
        symbol: Symbol,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> tuple[datetime, datetime] | None:
        """
        Get the date range of stored data for a symbol.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            Tuple of (start, end) datetimes, or None if no data
        """
        ...

    @abstractmethod
    def delete(self, symbol: Symbol, timeframe: Timeframe = Timeframe.DAILY) -> bool:
        """
        Delete stored data for a symbol.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            True if data was deleted
        """
        ...

    def append(
        self,
        symbol: Symbol,
        data: pd.DataFrame,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> None:
        """
        Append new data to existing stored data.

        Default implementation loads existing data, concatenates,
        removes duplicates, and saves. Override for more efficient
        implementations.

        Args:
            symbol: The asset symbol
            data: New DataFrame to append
            timeframe: Data timeframe
        """
        if self.exists(symbol, timeframe):
            existing = self.load(symbol, timeframe=timeframe)
            combined = pd.concat([existing, data])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            self.save(symbol, combined, timeframe)
        else:
            self.save(symbol, data, timeframe)


class StorageError(Exception):
    """Base exception for storage errors."""

    pass


class DataNotFoundError(StorageError):
    """Raised when requested data is not found."""

    def __init__(self, symbol: str, timeframe: str = ""):
        self.symbol = symbol
        self.timeframe = timeframe
        msg = f"Data not found for {symbol}"
        if timeframe:
            msg += f" ({timeframe})"
        super().__init__(msg)


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path
