"""
Feature Store with Versioning

Persistent storage for computed features with:
- Version control for reproducibility
- Metadata tracking (lineage, compute time, parameters)
- Efficient loading with date range filtering
- Feature statistics and validation
"""

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from src.core.paths import paths
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FeatureMetadata:
    """Metadata for a stored feature set."""
    feature_set: str
    symbol: str
    version: str
    created_at: str
    parameters: dict = field(default_factory=dict)
    data_sources: list = field(default_factory=list)
    date_range: tuple = field(default_factory=tuple)  # (start, end)
    row_count: int = 0
    column_count: int = 0
    columns: list = field(default_factory=list)
    compute_time_seconds: float = 0.0
    checksum: str = ""
    notes: str = ""


@dataclass
class FeatureVersion:
    """A specific version of a feature set."""
    version: str
    created_at: datetime
    is_latest: bool = False
    metadata: Optional[FeatureMetadata] = None


@dataclass
class FeatureStats:
    """Statistics for a feature column."""
    name: str
    dtype: str
    count: int
    null_count: int
    null_pct: float
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    unique_count: Optional[int] = None


# =============================================================================
# FEATURE STORE
# =============================================================================

class FeatureStore:
    """
    Persistent feature storage with versioning.

    Features are stored as parquet files organized by:
    - symbol/
      - feature_set/
        - v_YYYYMMDD_HHMMSS/
          - data.parquet
          - metadata.json

    Usage:
        store = FeatureStore()

        # Save features
        store.save_features("AAPL", df, "technical_features")

        # Load latest
        df = store.load_features("AAPL", "technical_features")

        # Load specific version
        df = store.load_features("AAPL", "technical_features", version="v_20240101_120000")

        # Get feature info
        versions = store.list_versions("AAPL", "technical_features")
        stats = store.compute_feature_stats("AAPL", "technical_features")
    """

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or paths.base / "features"
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Keep track of latest versions
        self._latest_cache: dict[tuple[str, str], str] = {}

    def _get_symbol_path(self, symbol: str) -> Path:
        """Get path for symbol."""
        return self.base_path / symbol.upper()

    def _get_feature_set_path(self, symbol: str, feature_set: str) -> Path:
        """Get path for feature set."""
        return self._get_symbol_path(symbol) / feature_set

    def _get_version_path(
        self,
        symbol: str,
        feature_set: str,
        version: str,
    ) -> Path:
        """Get path for specific version."""
        return self._get_feature_set_path(symbol, feature_set) / version

    def _generate_version(self) -> str:
        """Generate a new version string."""
        return f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _compute_checksum(self, df: pd.DataFrame) -> str:
        """Compute checksum for DataFrame."""
        # Use pandas hash for reproducible checksum
        try:
            h = hashlib.sha256()
            h.update(pd.util.hash_pandas_object(df).values.tobytes())
            return h.hexdigest()[:16]
        except Exception:
            return ""

    def save_features(
        self,
        symbol: str,
        features: pd.DataFrame,
        feature_set: str,
        version: Optional[str] = None,
        parameters: Optional[dict] = None,
        data_sources: Optional[list] = None,
        notes: str = "",
        compute_time: float = 0.0,
    ) -> str:
        """
        Save features with versioning.

        Args:
            symbol: Stock symbol
            features: DataFrame with features (index should be dates)
            feature_set: Name of feature set (e.g., "technical", "sentiment")
            version: Optional version string (auto-generated if not provided)
            parameters: Parameters used to compute features
            data_sources: List of data sources used
            notes: Optional notes about this version
            compute_time: Time taken to compute features

        Returns:
            Version string
        """
        start_time = datetime.now()

        # Generate version if not provided
        if version is None:
            version = self._generate_version()

        # Create directory
        version_path = self._get_version_path(symbol, feature_set, version)
        version_path.mkdir(parents=True, exist_ok=True)

        # Save data
        data_path = version_path / "data.parquet"
        features.to_parquet(data_path, engine="pyarrow")

        # Compute metadata
        date_range = ()
        if len(features) > 0:
            if isinstance(features.index, pd.DatetimeIndex):
                date_range = (
                    features.index.min().isoformat(),
                    features.index.max().isoformat(),
                )

        metadata = FeatureMetadata(
            feature_set=feature_set,
            symbol=symbol.upper(),
            version=version,
            created_at=datetime.now().isoformat(),
            parameters=parameters or {},
            data_sources=data_sources or [],
            date_range=date_range,
            row_count=len(features),
            column_count=len(features.columns),
            columns=list(features.columns),
            compute_time_seconds=compute_time or (datetime.now() - start_time).total_seconds(),
            checksum=self._compute_checksum(features),
            notes=notes,
        )

        # Save metadata
        metadata_path = version_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(asdict(metadata), f, indent=2, default=str)

        # Update latest pointer
        self._update_latest(symbol, feature_set, version)

        logger.info(
            f"Saved {feature_set} for {symbol}: {len(features)} rows, "
            f"{len(features.columns)} columns, version={version}"
        )

        return version

    def _update_latest(self, symbol: str, feature_set: str, version: str):
        """Update the 'latest' symlink."""
        feature_set_path = self._get_feature_set_path(symbol, feature_set)
        latest_path = feature_set_path / "latest"

        # Update cache
        self._latest_cache[(symbol.upper(), feature_set)] = version

        # Write latest pointer file
        with open(latest_path, "w") as f:
            f.write(version)

    def _get_latest_version(self, symbol: str, feature_set: str) -> Optional[str]:
        """Get the latest version for a feature set."""
        cache_key = (symbol.upper(), feature_set)
        if cache_key in self._latest_cache:
            return self._latest_cache[cache_key]

        feature_set_path = self._get_feature_set_path(symbol, feature_set)
        latest_path = feature_set_path / "latest"

        if latest_path.exists():
            with open(latest_path) as f:
                version = f.read().strip()
                self._latest_cache[cache_key] = version
                return version

        # Fall back to most recent by name
        versions = self.list_versions(symbol, feature_set)
        if versions:
            return versions[0].version

        return None

    def load_features(
        self,
        symbol: str,
        feature_set: str,
        version: str = "latest",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Load features from store.

        Args:
            symbol: Stock symbol
            feature_set: Name of feature set
            version: Version to load ("latest" for most recent)
            start_date: Optional start date filter
            end_date: Optional end date filter
            columns: Optional list of columns to load

        Returns:
            DataFrame with features
        """
        # Resolve version
        if version == "latest":
            version = self._get_latest_version(symbol, feature_set)
            if version is None:
                raise ValueError(f"No features found for {symbol}/{feature_set}")

        # Load data
        version_path = self._get_version_path(symbol, feature_set, version)
        data_path = version_path / "data.parquet"

        if not data_path.exists():
            raise ValueError(f"Features not found: {symbol}/{feature_set}/{version}")

        # Load with optional column filter
        if columns:
            df = pd.read_parquet(data_path, columns=columns)
        else:
            df = pd.read_parquet(data_path)

        # Apply date filters
        if isinstance(df.index, pd.DatetimeIndex):
            if start_date:
                df = df[df.index >= start_date]
            if end_date:
                df = df[df.index <= end_date]

        logger.debug(f"Loaded {feature_set} for {symbol}: {len(df)} rows")
        return df

    def get_metadata(
        self,
        symbol: str,
        feature_set: str,
        version: str = "latest",
    ) -> FeatureMetadata:
        """Get metadata for a feature set version."""
        if version == "latest":
            version = self._get_latest_version(symbol, feature_set)
            if version is None:
                raise ValueError(f"No features found for {symbol}/{feature_set}")

        version_path = self._get_version_path(symbol, feature_set, version)
        metadata_path = version_path / "metadata.json"

        if not metadata_path.exists():
            raise ValueError(f"Metadata not found: {symbol}/{feature_set}/{version}")

        with open(metadata_path) as f:
            data = json.load(f)
            return FeatureMetadata(**data)

    def list_versions(
        self,
        symbol: str,
        feature_set: str,
    ) -> list[FeatureVersion]:
        """List all versions for a feature set."""
        feature_set_path = self._get_feature_set_path(symbol, feature_set)

        if not feature_set_path.exists():
            return []

        latest = self._get_latest_version(symbol, feature_set)

        versions = []
        for version_dir in sorted(feature_set_path.iterdir(), reverse=True):
            if not version_dir.is_dir() or version_dir.name == "latest":
                continue

            metadata_path = version_dir / "metadata.json"
            metadata = None

            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        data = json.load(f)
                        metadata = FeatureMetadata(**data)
                except Exception:
                    pass

            versions.append(FeatureVersion(
                version=version_dir.name,
                created_at=datetime.strptime(
                    version_dir.name.replace("v_", ""),
                    "%Y%m%d_%H%M%S",
                ) if version_dir.name.startswith("v_") else datetime.now(),
                is_latest=(version_dir.name == latest),
                metadata=metadata,
            ))

        return versions

    def list_feature_sets(self, symbol: str) -> list[str]:
        """List all feature sets for a symbol."""
        symbol_path = self._get_symbol_path(symbol)
        if not symbol_path.exists():
            return []

        return [
            d.name for d in symbol_path.iterdir()
            if d.is_dir()
        ]

    def list_symbols(self) -> list[str]:
        """List all symbols in the store."""
        return [
            d.name for d in self.base_path.iterdir()
            if d.is_dir()
        ]

    def compute_feature_stats(
        self,
        symbol: str,
        feature_set: str,
        version: str = "latest",
    ) -> list[FeatureStats]:
        """Compute statistics for all features in a set."""
        df = self.load_features(symbol, feature_set, version)

        stats = []
        for col in df.columns:
            series = df[col]

            stat = FeatureStats(
                name=col,
                dtype=str(series.dtype),
                count=len(series),
                null_count=series.isna().sum(),
                null_pct=series.isna().sum() / len(series) * 100 if len(series) > 0 else 0,
            )

            if pd.api.types.is_numeric_dtype(series):
                stat.mean = float(series.mean()) if not series.isna().all() else None
                stat.std = float(series.std()) if not series.isna().all() else None
                stat.min = float(series.min()) if not series.isna().all() else None
                stat.max = float(series.max()) if not series.isna().all() else None
            else:
                stat.unique_count = series.nunique()

            stats.append(stat)

        return stats

    def delete_version(
        self,
        symbol: str,
        feature_set: str,
        version: str,
    ):
        """Delete a specific version."""
        if version == "latest":
            raise ValueError("Cannot delete 'latest' - specify explicit version")

        version_path = self._get_version_path(symbol, feature_set, version)
        if version_path.exists():
            shutil.rmtree(version_path)
            logger.info(f"Deleted {symbol}/{feature_set}/{version}")

            # Update latest if needed
            if self._get_latest_version(symbol, feature_set) == version:
                versions = self.list_versions(symbol, feature_set)
                if versions:
                    self._update_latest(symbol, feature_set, versions[0].version)

    def cleanup_old_versions(
        self,
        symbol: str,
        feature_set: str,
        keep_count: int = 5,
    ):
        """Keep only the most recent N versions."""
        versions = self.list_versions(symbol, feature_set)

        if len(versions) <= keep_count:
            return

        for version in versions[keep_count:]:
            self.delete_version(symbol, feature_set, version.version)

        logger.info(
            f"Cleaned up {len(versions) - keep_count} old versions "
            f"for {symbol}/{feature_set}"
        )

    def get_feature_lineage(self, feature_name: str) -> dict:
        """
        Get lineage information for a feature.

        Returns dict with:
        - data_sources: What data is needed
        - dependencies: What other features are needed
        - compute_function: How it's computed
        """
        # This will be populated from FeatureRegistry
        from .feature_registry import FEATURE_REGISTRY

        if feature_name in FEATURE_REGISTRY:
            definition = FEATURE_REGISTRY[feature_name]
            return {
                "feature_name": feature_name,
                "description": definition.description,
                "category": definition.category.value,
                "data_sources": definition.data_sources,
                "dependencies": definition.dependencies,
                "parameters": definition.default_params,
            }

        return {"feature_name": feature_name, "status": "not_in_registry"}

    def get_store_summary(self) -> dict:
        """Get summary of entire feature store."""
        symbols = self.list_symbols()

        total_feature_sets = 0
        total_versions = 0
        total_size_bytes = 0

        symbol_summaries = {}
        for symbol in symbols:
            feature_sets = self.list_feature_sets(symbol)
            total_feature_sets += len(feature_sets)

            symbol_versions = 0
            for fs in feature_sets:
                versions = self.list_versions(symbol, fs)
                symbol_versions += len(versions)
                total_versions += len(versions)

            symbol_summaries[symbol] = {
                "feature_sets": len(feature_sets),
                "versions": symbol_versions,
            }

        # Calculate size
        for path in self.base_path.rglob("*.parquet"):
            total_size_bytes += path.stat().st_size

        return {
            "total_symbols": len(symbols),
            "total_feature_sets": total_feature_sets,
            "total_versions": total_versions,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "symbols": symbol_summaries,
        }


# =============================================================================
# FEATURE STORE SINGLETON
# =============================================================================

_feature_store: Optional[FeatureStore] = None


def get_feature_store() -> FeatureStore:
    """Get the global FeatureStore instance."""
    global _feature_store
    if _feature_store is None:
        _feature_store = FeatureStore()
    return _feature_store
