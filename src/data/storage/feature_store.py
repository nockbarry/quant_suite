"""Point-in-time feature store using DuckDB.

Provides persistent storage for computed features with:
- Point-in-time queries to prevent look-ahead bias
- Feature versioning for reproducibility
- Batch computation support
- Efficient columnar storage
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ...core import Symbol

logger = logging.getLogger(__name__)


@dataclass
class FeatureMetadata:
    """Metadata about a stored feature."""

    name: str
    description: str = ""
    category: str = "unknown"  # technical, fundamental, alternative, sentiment
    lookback_days: int = 0  # How many days of history needed to compute
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "lookback_days": self.lookback_days,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "dependencies": self.dependencies,
        }


class FeatureStore:
    """
    Point-in-time feature store using DuckDB.

    Stores computed features with proper timestamping to enable:
    - Point-in-time queries (as-of semantics)
    - Feature versioning
    - Reproducible backtesting

    Schema:
        features: (symbol, date, feature_name, value, computed_at, version)
        metadata: (feature_name, description, category, lookback_days, version, created_at)
    """

    DEFAULT_DB_PATH = Path.home() / ".quant_cache" / "feature_store.duckdb"

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize feature store.

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with duckdb.connect(str(self.db_path)) as conn:
            # Main feature storage table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    symbol VARCHAR NOT NULL,
                    date DATE NOT NULL,
                    feature_name VARCHAR NOT NULL,
                    value DOUBLE,
                    computed_at TIMESTAMP NOT NULL,
                    version VARCHAR DEFAULT '1.0',
                    PRIMARY KEY (symbol, date, feature_name, version)
                )
            """)

            # Feature metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_metadata (
                    feature_name VARCHAR PRIMARY KEY,
                    description VARCHAR,
                    category VARCHAR,
                    lookback_days INTEGER DEFAULT 0,
                    version VARCHAR DEFAULT '1.0',
                    created_at TIMESTAMP,
                    dependencies VARCHAR
                )
            """)

            # Indexes for common query patterns
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_symbol_date
                ON features (symbol, date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_date
                ON features (date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_computed_at
                ON features (computed_at)
            """)

    def store_features(
        self,
        symbol: Symbol,
        date: datetime | pd.Timestamp,
        features: dict[str, float],
        computed_at: datetime | None = None,
        version: str = "1.0",
    ) -> None:
        """
        Store feature values for a symbol on a date.

        Args:
            symbol: Stock symbol
            date: The date the features apply to
            features: Dict of feature_name -> value
            computed_at: When features were computed (defaults to now)
            version: Feature version for reproducibility
        """
        if computed_at is None:
            computed_at = datetime.now()

        date_val = pd.Timestamp(date).date()

        with duckdb.connect(str(self.db_path)) as conn:
            for feature_name, value in features.items():
                if value is None or pd.isna(value):
                    continue
                conn.execute("""
                    INSERT OR REPLACE INTO features
                    (symbol, date, feature_name, value, computed_at, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (symbol, date_val, feature_name, float(value), computed_at, version))

    def store_features_batch(
        self,
        data: pd.DataFrame,
        computed_at: datetime | None = None,
        version: str = "1.0",
    ) -> int:
        """
        Store features from a DataFrame in batch.

        Args:
            data: DataFrame with columns: symbol, date, and feature columns
                  OR MultiIndex (symbol, date) with feature columns
            computed_at: When features were computed
            version: Feature version

        Returns:
            Number of feature values stored
        """
        if computed_at is None:
            computed_at = datetime.now()

        # Handle MultiIndex
        if isinstance(data.index, pd.MultiIndex):
            data = data.reset_index()

        if "symbol" not in data.columns or "date" not in data.columns:
            raise ValueError("DataFrame must have 'symbol' and 'date' columns")

        feature_cols = [c for c in data.columns if c not in ("symbol", "date")]
        if not feature_cols:
            return 0

        # Melt to long format
        melted = data.melt(
            id_vars=["symbol", "date"],
            value_vars=feature_cols,
            var_name="feature_name",
            value_name="value",
        )

        # Remove nulls
        melted = melted.dropna(subset=["value"])

        # Add metadata
        melted["computed_at"] = computed_at
        melted["version"] = version
        melted["date"] = pd.to_datetime(melted["date"]).dt.date

        count = 0
        with duckdb.connect(str(self.db_path)) as conn:
            for _, row in melted.iterrows():
                conn.execute("""
                    INSERT OR REPLACE INTO features
                    (symbol, date, feature_name, value, computed_at, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row["symbol"],
                    row["date"],
                    row["feature_name"],
                    float(row["value"]),
                    row["computed_at"],
                    row["version"],
                ))
                count += 1

        return count

    def get_features(
        self,
        symbol: Symbol,
        start_date: datetime | pd.Timestamp | None = None,
        end_date: datetime | pd.Timestamp | None = None,
        feature_names: list[str] | None = None,
        as_of: datetime | None = None,
        version: str | None = None,
    ) -> pd.DataFrame:
        """
        Get features for a symbol over a date range.

        Args:
            symbol: Stock symbol
            start_date: Start of date range
            end_date: End of date range
            feature_names: Specific features to retrieve (None = all)
            as_of: Point-in-time query - only include features computed before this time
            version: Specific version to retrieve

        Returns:
            DataFrame with date index and feature columns
        """
        query = "SELECT date, feature_name, value FROM features WHERE symbol = ?"
        params: list = [symbol]

        if start_date:
            query += " AND date >= ?"
            params.append(pd.Timestamp(start_date).date())

        if end_date:
            query += " AND date <= ?"
            params.append(pd.Timestamp(end_date).date())

        if feature_names:
            placeholders = ", ".join("?" * len(feature_names))
            query += f" AND feature_name IN ({placeholders})"
            params.extend(feature_names)

        if as_of:
            query += " AND computed_at <= ?"
            params.append(as_of)

        if version:
            query += " AND version = ?"
            params.append(version)

        # Get latest version for each (date, feature_name) combo
        query = f"""
            WITH ranked AS (
                SELECT date, feature_name, value, computed_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY date, feature_name
                           ORDER BY computed_at DESC
                       ) as rn
                FROM ({query})
            )
            SELECT date, feature_name, value
            FROM ranked WHERE rn = 1
        """

        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(query, params).fetchdf()

        if result.empty:
            return pd.DataFrame()

        # Pivot to wide format
        pivoted = result.pivot(index="date", columns="feature_name", values="value")
        pivoted.index = pd.to_datetime(pivoted.index)
        return pivoted

    def get_point_in_time(
        self,
        symbol: Symbol,
        date: datetime | pd.Timestamp,
        as_of: datetime | None = None,
        feature_names: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Get features for a specific date with point-in-time semantics.

        This is the key method for preventing look-ahead bias. It only
        returns features that were computed BEFORE the as_of timestamp.

        Args:
            symbol: Stock symbol
            date: The date to get features for
            as_of: Only return features computed before this time
                   (defaults to the date itself at market close)
            feature_names: Specific features to retrieve

        Returns:
            Dict of feature_name -> value
        """
        if as_of is None:
            # Default: features available at market close on the date
            as_of = pd.Timestamp(date).replace(hour=16, minute=0, second=0)
            if isinstance(as_of, pd.Timestamp):
                as_of = as_of.to_pydatetime()

        date_val = pd.Timestamp(date).date()

        query = """
            SELECT feature_name, value
            FROM (
                SELECT feature_name, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY feature_name
                           ORDER BY computed_at DESC
                       ) as rn
                FROM features
                WHERE symbol = ?
                  AND date = ?
                  AND computed_at <= ?
            )
            WHERE rn = 1
        """
        params = [symbol, date_val, as_of]

        if feature_names:
            placeholders = ", ".join("?" * len(feature_names))
            query = query.replace(
                "WHERE symbol = ?",
                f"WHERE symbol = ? AND feature_name IN ({placeholders})",
            )
            params = [symbol] + feature_names + [date_val, as_of]

        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(query, params).fetchdf()

        return dict(zip(result["feature_name"], result["value"])) if not result.empty else {}

    def get_latest_features(
        self,
        symbols: list[Symbol],
        feature_names: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Get the most recent features for multiple symbols.

        Args:
            symbols: List of symbols
            feature_names: Specific features (None = all)

        Returns:
            DataFrame with symbol index and feature columns
        """
        placeholders = ", ".join("?" * len(symbols))

        query = f"""
            WITH latest_dates AS (
                SELECT symbol, MAX(date) as latest_date
                FROM features
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
            ),
            latest_features AS (
                SELECT f.symbol, f.feature_name, f.value
                FROM features f
                INNER JOIN latest_dates ld
                    ON f.symbol = ld.symbol AND f.date = ld.latest_date
            )
            SELECT symbol, feature_name, value
            FROM (
                SELECT symbol, feature_name, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol, feature_name
                           ORDER BY computed_at DESC
                       ) as rn
                FROM latest_features
            )
            WHERE rn = 1
        """
        params = list(symbols)

        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(query, params).fetchdf()

        if result.empty:
            return pd.DataFrame()

        pivoted = result.pivot(index="symbol", columns="feature_name", values="value")

        if feature_names:
            available = [f for f in feature_names if f in pivoted.columns]
            pivoted = pivoted[available]

        return pivoted

    def register_feature(self, metadata: FeatureMetadata) -> None:
        """Register feature metadata."""
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO feature_metadata
                (feature_name, description, category, lookback_days, version, created_at, dependencies)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.name,
                metadata.description,
                metadata.category,
                metadata.lookback_days,
                metadata.version,
                metadata.created_at,
                ",".join(metadata.dependencies),
            ))

    def get_feature_metadata(self, feature_name: str) -> FeatureMetadata | None:
        """Get metadata for a feature."""
        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(
                "SELECT * FROM feature_metadata WHERE feature_name = ?",
                (feature_name,),
            ).fetchone()

        if result is None:
            return None

        return FeatureMetadata(
            name=result[0],
            description=result[1] or "",
            category=result[2] or "unknown",
            lookback_days=result[3] or 0,
            version=result[4] or "1.0",
            created_at=result[5] if result[5] else datetime.now(),
            dependencies=result[6].split(",") if result[6] else [],
        )

    def list_features(self, category: str | None = None) -> list[str]:
        """List all registered features."""
        query = "SELECT DISTINCT feature_name FROM features"
        params = []

        if category:
            query = """
                SELECT feature_name FROM feature_metadata
                WHERE category = ?
            """
            params = [category]

        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(query, params).fetchdf()

        return result["feature_name"].tolist() if not result.empty else []

    def list_symbols(self) -> list[Symbol]:
        """List all symbols with stored features."""
        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute("SELECT DISTINCT symbol FROM features").fetchdf()
        return result["symbol"].tolist() if not result.empty else []

    def get_date_range(self, symbol: Symbol) -> tuple[datetime, datetime] | None:
        """Get the date range of features for a symbol."""
        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute("""
                SELECT MIN(date), MAX(date)
                FROM features
                WHERE symbol = ?
            """, (symbol,)).fetchone()

        if result and result[0] and result[1]:
            return (
                pd.Timestamp(result[0]).to_pydatetime(),
                pd.Timestamp(result[1]).to_pydatetime(),
            )
        return None

    def get_feature_coverage(
        self,
        symbols: list[Symbol],
        feature_names: list[str],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Get feature coverage statistics.

        Returns DataFrame with:
        - Index: symbols
        - Columns: feature names
        - Values: count of available data points
        """
        placeholders_symbols = ", ".join("?" * len(symbols))
        placeholders_features = ", ".join("?" * len(feature_names))

        query = f"""
            SELECT symbol, feature_name, COUNT(*) as count
            FROM features
            WHERE symbol IN ({placeholders_symbols})
              AND feature_name IN ({placeholders_features})
        """
        params = list(symbols) + list(feature_names)

        if start_date:
            query += " AND date >= ?"
            params.append(pd.Timestamp(start_date).date())

        if end_date:
            query += " AND date <= ?"
            params.append(pd.Timestamp(end_date).date())

        query += " GROUP BY symbol, feature_name"

        with duckdb.connect(str(self.db_path)) as conn:
            result = conn.execute(query, params).fetchdf()

        if result.empty:
            return pd.DataFrame(index=symbols, columns=feature_names).fillna(0)

        pivoted = result.pivot(index="symbol", columns="feature_name", values="count")
        pivoted = pivoted.reindex(index=symbols, columns=feature_names).fillna(0)
        return pivoted.astype(int)

    def delete_features(
        self,
        symbol: Symbol | None = None,
        feature_name: str | None = None,
        before_date: datetime | None = None,
        version: str | None = None,
    ) -> int:
        """
        Delete features matching criteria.

        Args:
            symbol: Delete only for this symbol
            feature_name: Delete only this feature
            before_date: Delete features before this date
            version: Delete only this version

        Returns:
            Number of rows deleted
        """
        conditions = []
        params = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        if feature_name:
            conditions.append("feature_name = ?")
            params.append(feature_name)

        if before_date:
            conditions.append("date < ?")
            params.append(pd.Timestamp(before_date).date())

        if version:
            conditions.append("version = ?")
            params.append(version)

        if not conditions:
            raise ValueError("At least one filter must be specified")

        where_clause = " AND ".join(conditions)

        with duckdb.connect(str(self.db_path)) as conn:
            # Get count first
            count = conn.execute(
                f"SELECT COUNT(*) FROM features WHERE {where_clause}",
                params,
            ).fetchone()[0]

            # Delete
            conn.execute(f"DELETE FROM features WHERE {where_clause}", params)

        return count

    def vacuum(self) -> None:
        """Optimize database storage."""
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("VACUUM")

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        with duckdb.connect(str(self.db_path)) as conn:
            total_rows = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            total_symbols = conn.execute("SELECT COUNT(DISTINCT symbol) FROM features").fetchone()[0]
            total_features = conn.execute("SELECT COUNT(DISTINCT feature_name) FROM features").fetchone()[0]

            date_range = conn.execute("""
                SELECT MIN(date), MAX(date) FROM features
            """).fetchone()

            size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_rows": total_rows,
            "total_symbols": total_symbols,
            "total_features": total_features,
            "date_range": (str(date_range[0]), str(date_range[1])) if date_range[0] else None,
            "db_path": str(self.db_path),
            "size_mb": round(size_bytes / (1024 * 1024), 2),
        }
