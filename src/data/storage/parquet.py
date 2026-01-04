"""Parquet file storage for OHLCV data."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ...core import Symbol, Timeframe
from .base import DataNotFoundError, Storage, ensure_directory


class ParquetStorage(Storage):
    """
    Parquet file-based storage for OHLCV data.

    Stores data in a directory structure:
        base_path/
            {timeframe}/
                {symbol}.parquet

    Parquet provides efficient columnar storage with good compression
    and fast read performance for time-series data.
    """

    def __init__(
        self,
        base_path: str | Path,
        compression: str = "snappy",
    ):
        """
        Initialize Parquet storage.

        Args:
            base_path: Base directory for storing parquet files
            compression: Compression codec ('snappy', 'gzip', 'zstd', 'none')
        """
        self.base_path = Path(base_path)
        self.compression = compression if compression != "none" else None
        ensure_directory(self.base_path)

    def _get_path(self, symbol: Symbol, timeframe: Timeframe) -> Path:
        """Get the file path for a symbol's data."""
        # Sanitize symbol for filename (replace / with _)
        safe_symbol = symbol.replace("/", "_").replace("^", "_")
        return self.base_path / timeframe.value / f"{safe_symbol}.parquet"

    def _ensure_timeframe_dir(self, timeframe: Timeframe) -> Path:
        """Ensure the timeframe directory exists."""
        path = self.base_path / timeframe.value
        return ensure_directory(path)

    def save(
        self,
        symbol: Symbol,
        data: pd.DataFrame,
        timeframe: Timeframe = Timeframe.DAILY,
        **kwargs: Any,
    ) -> None:
        """
        Save OHLCV data to a Parquet file.

        Args:
            symbol: The asset symbol
            data: DataFrame with OHLCV data (DatetimeIndex)
            timeframe: Data timeframe
            **kwargs: Additional options (passed to write_table)
        """
        if data.empty:
            return

        self._ensure_timeframe_dir(timeframe)
        file_path = self._get_path(symbol, timeframe)

        # Ensure index is datetime
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)

        # Sort by index
        data = data.sort_index()

        # Convert to PyArrow Table
        table = pa.Table.from_pandas(data, preserve_index=True)

        # Write to parquet
        pq.write_table(
            table,
            file_path,
            compression=self.compression,
            **kwargs,
        )

    def load(
        self,
        symbol: Symbol,
        start: datetime | None = None,
        end: datetime | None = None,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> pd.DataFrame:
        """
        Load OHLCV data from a Parquet file.

        Args:
            symbol: The asset symbol
            start: Optional start datetime filter
            end: Optional end datetime filter
            timeframe: Data timeframe

        Returns:
            DataFrame with OHLCV data
        """
        file_path = self._get_path(symbol, timeframe)

        if not file_path.exists():
            raise DataNotFoundError(symbol, timeframe.value)

        # Read parquet file
        df = pd.read_parquet(file_path)

        # Ensure index is datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            df.index = pd.to_datetime(df.index)

        # Apply date filters
        if start is not None:
            df = df[df.index >= start]
        if end is not None:
            df = df[df.index <= end]

        return df

    def exists(self, symbol: Symbol, timeframe: Timeframe = Timeframe.DAILY) -> bool:
        """
        Check if data exists for a symbol.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            True if parquet file exists
        """
        return self._get_path(symbol, timeframe).exists()

    def list_symbols(self, timeframe: Timeframe = Timeframe.DAILY) -> list[Symbol]:
        """
        List all symbols with stored data.

        Args:
            timeframe: Data timeframe

        Returns:
            List of symbols
        """
        timeframe_dir = self.base_path / timeframe.value
        if not timeframe_dir.exists():
            return []

        symbols = []
        for file in timeframe_dir.glob("*.parquet"):
            # Convert filename back to symbol
            symbol = file.stem.replace("_", "/")
            symbols.append(symbol)

        return sorted(symbols)

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
        file_path = self._get_path(symbol, timeframe)

        if not file_path.exists():
            return None

        # Read metadata without loading full data
        parquet_file = pq.ParquetFile(file_path)
        metadata = parquet_file.schema_arrow.pandas_metadata

        if metadata:
            # Try to get from pandas metadata
            df = pd.read_parquet(file_path, columns=[])
            if not df.index.empty:
                return (df.index.min().to_pydatetime(), df.index.max().to_pydatetime())

        # Fallback: load the data
        df = self.load(symbol, timeframe=timeframe)
        if df.empty:
            return None

        return (df.index.min().to_pydatetime(), df.index.max().to_pydatetime())

    def delete(self, symbol: Symbol, timeframe: Timeframe = Timeframe.DAILY) -> bool:
        """
        Delete stored data for a symbol.

        Args:
            symbol: The asset symbol
            timeframe: Data timeframe

        Returns:
            True if file was deleted
        """
        file_path = self._get_path(symbol, timeframe)

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def append(
        self,
        symbol: Symbol,
        data: pd.DataFrame,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> None:
        """
        Append new data to existing stored data.

        Efficiently handles deduplication and sorting.

        Args:
            symbol: The asset symbol
            data: New DataFrame to append
            timeframe: Data timeframe
        """
        if data.empty:
            return

        file_path = self._get_path(symbol, timeframe)

        if file_path.exists():
            # Load existing data
            existing = self.load(symbol, timeframe=timeframe)

            # Combine and deduplicate
            combined = pd.concat([existing, data])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()

            self.save(symbol, combined, timeframe)
        else:
            self.save(symbol, data, timeframe)

    def get_storage_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage stats
        """
        stats: dict[str, Any] = {
            "base_path": str(self.base_path),
            "compression": self.compression,
            "timeframes": {},
        }

        total_size = 0
        total_files = 0

        for timeframe_dir in self.base_path.iterdir():
            if timeframe_dir.is_dir():
                files = list(timeframe_dir.glob("*.parquet"))
                size = sum(f.stat().st_size for f in files)
                stats["timeframes"][timeframe_dir.name] = {
                    "num_symbols": len(files),
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                }
                total_size += size
                total_files += len(files)

        stats["total_files"] = total_files
        stats["total_size_bytes"] = total_size
        stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)

        return stats
