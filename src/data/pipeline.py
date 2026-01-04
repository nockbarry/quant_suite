"""Data ingestion and management pipeline."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from ..core import Symbol, Timeframe
from .sources.base import DataSource
from .storage.base import Storage

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    Data ingestion and management pipeline.

    Coordinates fetching data from sources and storing it locally.
    Handles incremental updates and data quality checks.
    """

    def __init__(
        self,
        source: DataSource,
        storage: Storage,
        max_concurrent: int = 5,
    ):
        """
        Initialize data pipeline.

        Args:
            source: Data source to fetch from
            storage: Storage backend to save to
            max_concurrent: Maximum concurrent fetch operations
        """
        self.source = source
        self.storage = storage
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_and_store(
        self,
        symbol: Symbol,
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
        overwrite: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch data for a symbol and store it.

        Args:
            symbol: The asset symbol
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe
            overwrite: If True, overwrite existing data

        Returns:
            The fetched DataFrame
        """
        async with self._semaphore:
            logger.info(f"Fetching {symbol} from {start.date()} to {end.date()}")

            try:
                data = await self.source.fetch_ohlcv(symbol, start, end, timeframe)

                if data.empty:
                    logger.warning(f"No data returned for {symbol}")
                    return data

                if overwrite:
                    self.storage.save(symbol, data, timeframe)
                else:
                    self.storage.append(symbol, data, timeframe)

                logger.info(f"Stored {len(data)} rows for {symbol}")
                return data

            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                raise

    async def fetch_multiple(
        self,
        symbols: list[Symbol],
        start: datetime,
        end: datetime,
        timeframe: Timeframe = Timeframe.DAILY,
        overwrite: bool = False,
    ) -> dict[Symbol, pd.DataFrame]:
        """
        Fetch and store data for multiple symbols concurrently.

        Args:
            symbols: List of asset symbols
            start: Start datetime
            end: End datetime
            timeframe: Data timeframe
            overwrite: If True, overwrite existing data

        Returns:
            Dictionary mapping symbols to DataFrames
        """
        tasks = [
            self.fetch_and_store(symbol, start, end, timeframe, overwrite)
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[Symbol, pd.DataFrame] = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch {symbol}: {result}")
            elif isinstance(result, pd.DataFrame) and not result.empty:
                output[symbol] = result

        return output

    async def update_symbol(
        self,
        symbol: Symbol,
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_days: int = 5,
    ) -> pd.DataFrame | None:
        """
        Update a symbol with latest data.

        Fetches data from the last stored date to now.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe
            lookback_days: Days to look back for overlap/verification

        Returns:
            Newly fetched data, or None if up to date
        """
        end = datetime.now()

        # Get existing date range
        date_range = self.storage.get_date_range(symbol, timeframe)

        if date_range:
            # Start from last date minus lookback for overlap
            start = date_range[1] - timedelta(days=lookback_days)
        else:
            # No existing data, fetch last year
            start = end - timedelta(days=365)

        return await self.fetch_and_store(symbol, start, end, timeframe)

    async def update_all(
        self,
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_days: int = 5,
    ) -> dict[Symbol, pd.DataFrame]:
        """
        Update all symbols in storage with latest data.

        Args:
            timeframe: Data timeframe
            lookback_days: Days to look back for overlap

        Returns:
            Dictionary of updated symbols and their new data
        """
        symbols = self.storage.list_symbols(timeframe)
        logger.info(f"Updating {len(symbols)} symbols")

        tasks = [
            self.update_symbol(symbol, timeframe, lookback_days)
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[Symbol, pd.DataFrame] = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to update {symbol}: {result}")
            elif result is not None and not result.empty:
                output[symbol] = result

        return output

    def load(
        self,
        symbol: Symbol,
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Load data for a symbol from storage.

        Args:
            symbol: The asset symbol
            start: Optional start datetime filter
            end: Optional end datetime filter
            timeframe: Data timeframe

        Returns:
            DataFrame with OHLCV data
        """
        return self.storage.load(symbol, start, end, timeframe)

    def load_multiple(
        self,
        symbols: list[Symbol],
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: Timeframe = Timeframe.DAILY,
        column: str = "close",
    ) -> pd.DataFrame:
        """
        Load a single column for multiple symbols as a wide DataFrame.

        Args:
            symbols: List of asset symbols
            start: Optional start datetime filter
            end: Optional end datetime filter
            timeframe: Data timeframe
            column: Column to extract (default: 'close')

        Returns:
            DataFrame with symbols as columns
        """
        dfs = {}
        for symbol in symbols:
            try:
                df = self.load(symbol, start, end, timeframe)
                if column in df.columns:
                    dfs[symbol] = df[column]
            except Exception as e:
                logger.warning(f"Could not load {symbol}: {e}")

        if not dfs:
            return pd.DataFrame()

        return pd.DataFrame(dfs)

    def get_coverage_report(
        self,
        symbols: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Get a report of data coverage for symbols.

        Args:
            symbols: List of symbols to check
            timeframe: Data timeframe

        Returns:
            DataFrame with coverage information
        """
        rows = []
        for symbol in symbols:
            date_range = self.storage.get_date_range(symbol, timeframe)
            if date_range:
                df = self.storage.load(symbol, timeframe=timeframe)
                rows.append({
                    "symbol": symbol,
                    "start_date": date_range[0],
                    "end_date": date_range[1],
                    "num_rows": len(df),
                    "has_gaps": self._check_gaps(df, timeframe),
                })
            else:
                rows.append({
                    "symbol": symbol,
                    "start_date": None,
                    "end_date": None,
                    "num_rows": 0,
                    "has_gaps": False,
                })

        return pd.DataFrame(rows)

    def _check_gaps(self, df: pd.DataFrame, timeframe: Timeframe) -> bool:
        """Check if data has gaps (missing days for daily data)."""
        if len(df) < 2:
            return False

        if timeframe == Timeframe.DAILY:
            # For daily data, check for gaps > 5 days (accounting for weekends/holidays)
            diff = df.index.to_series().diff()
            return bool((diff > timedelta(days=5)).any())

        return False

    def validate_data(
        self,
        symbol: Symbol,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> dict[str, Any]:
        """
        Validate stored data for quality issues.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            Dictionary with validation results
        """
        try:
            df = self.storage.load(symbol, timeframe=timeframe)
        except Exception as e:
            return {"valid": False, "error": str(e)}

        issues = []

        # Check for missing values
        null_counts = df.isnull().sum()
        if null_counts.any():
            issues.append(f"Missing values: {null_counts.to_dict()}")

        # Check for negative prices
        for col in ["open", "high", "low", "close"]:
            if col in df.columns and (df[col] < 0).any():
                issues.append(f"Negative values in {col}")

        # Check OHLC consistency
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            invalid_high = df["high"] < df[["open", "close"]].max(axis=1)
            invalid_low = df["low"] > df[["open", "close"]].min(axis=1)
            if invalid_high.any():
                issues.append(f"High < max(open, close) on {invalid_high.sum()} rows")
            if invalid_low.any():
                issues.append(f"Low > min(open, close) on {invalid_low.sum()} rows")

        # Check for duplicate indices
        if df.index.duplicated().any():
            issues.append(f"Duplicate indices: {df.index.duplicated().sum()}")

        # Check for out-of-order index
        if not df.index.is_monotonic_increasing:
            issues.append("Index is not sorted")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "rows": len(df),
            "columns": list(df.columns),
            "date_range": (df.index.min(), df.index.max()) if len(df) > 0 else None,
        }
