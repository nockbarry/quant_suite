"""Short interest data source for short squeeze detection.

Provides short interest metrics including:
- Short interest ratio (days to cover)
- Short percent of float
- Short squeeze potential signals
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)

# Try to import yfinance for short interest data
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Install with: pip install yfinance")


@dataclass
class ShortInterestData:
    """Short interest data for a symbol."""

    symbol: Symbol
    timestamp: datetime
    short_interest: int  # Number of shares sold short
    short_percent_of_float: float  # % of float sold short (0-1)
    short_ratio: float  # Days to cover (short interest / avg daily volume)
    avg_daily_volume: int  # Average daily trading volume
    previous_short_interest: int | None = None  # Previous period
    short_change_pct: float | None = None  # % change from previous
    settlement_date: datetime | None = None  # FINRA settlement date
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_high_short_interest(self, threshold: float = 0.20) -> bool:
        """Check if short interest is high (>20% of float by default)."""
        return self.short_percent_of_float > threshold

    def is_squeeze_candidate(
        self,
        min_short_pct: float = 0.15,
        min_days_to_cover: float = 3.0,
    ) -> bool:
        """Check if stock is a potential short squeeze candidate."""
        return (
            self.short_percent_of_float >= min_short_pct
            and self.short_ratio >= min_days_to_cover
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": str(self.symbol),
            "timestamp": self.timestamp.isoformat(),
            "short_interest": self.short_interest,
            "short_percent_of_float": self.short_percent_of_float,
            "short_ratio": self.short_ratio,
            "avg_daily_volume": self.avg_daily_volume,
            "previous_short_interest": self.previous_short_interest,
            "short_change_pct": self.short_change_pct,
            "is_squeeze_candidate": self.is_squeeze_candidate(),
            **self.metadata,
        }


@dataclass
class ShortSqueezeSignal:
    """Short squeeze potential signal."""

    symbol: Symbol
    timestamp: datetime
    squeeze_score: float  # 0-1 score of squeeze potential
    short_percent_of_float: float
    days_to_cover: float
    price_momentum: float  # Recent price momentum
    volume_spike: float  # Volume relative to average
    signal: str  # 'high_squeeze_risk', 'moderate_squeeze_risk', 'low_squeeze_risk'
    metadata: dict[str, Any] = field(default_factory=dict)


class ShortInterestSource:
    """
    Short interest data source.

    Fetches short interest data from available sources:
    - yfinance (includes FINRA short interest)
    - Can be extended with paid data sources
    """

    name = "short_interest"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
    ):
        """
        Initialize short interest source.

        Args:
            cache_ttl_hours: Cache TTL in hours (short interest updates bi-weekly)
        """
        if not YFINANCE_AVAILABLE:
            raise ImportError(
                "yfinance library not available. Install with: pip install yfinance"
            )

        self._cache: dict[str, tuple[datetime, ShortInterestData]] = {}
        self._cache_ttl = timedelta(hours=cache_ttl_hours)

    def fetch_short_interest(
        self,
        symbol: Symbol,
        use_cache: bool = True,
    ) -> ShortInterestData | None:
        """
        Fetch short interest data for a symbol.

        Args:
            symbol: Stock symbol
            use_cache: Whether to use cached data

        Returns:
            ShortInterestData or None if fetch fails
        """
        symbol_str = str(symbol).upper()

        # Check cache
        if use_cache and symbol_str in self._cache:
            cached_time, cached_data = self._cache[symbol_str]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug(f"Using cached short interest for {symbol_str}")
                return cached_data

        try:
            ticker = yf.Ticker(symbol_str)
            info = ticker.info

            # Extract short interest metrics
            short_interest = info.get("sharesShort", 0)
            short_percent_of_float = info.get("shortPercentOfFloat", 0.0)
            short_ratio = info.get("shortRatio", 0.0)
            avg_volume = info.get("averageVolume", 1)
            previous_short = info.get("sharesShortPriorMonth", None)

            # Handle None values
            if short_interest is None:
                short_interest = 0
            if short_percent_of_float is None:
                short_percent_of_float = 0.0
            if short_ratio is None:
                short_ratio = 0.0

            # Calculate change from previous period
            short_change_pct = None
            if previous_short and previous_short > 0:
                short_change_pct = (short_interest - previous_short) / previous_short

            data = ShortInterestData(
                symbol=symbol,
                timestamp=datetime.now(),
                short_interest=int(short_interest),
                short_percent_of_float=float(short_percent_of_float),
                short_ratio=float(short_ratio),
                avg_daily_volume=int(avg_volume) if avg_volume else 1,
                previous_short_interest=int(previous_short) if previous_short else None,
                short_change_pct=short_change_pct,
                metadata={
                    "source": "yfinance",
                    "float_shares": info.get("floatShares", 0),
                    "market_cap": info.get("marketCap", 0),
                },
            )

            # Cache result
            self._cache[symbol_str] = (datetime.now(), data)
            logger.info(
                f"Fetched short interest for {symbol_str}: "
                f"{short_percent_of_float:.1%} of float, {short_ratio:.1f} days to cover"
            )

            return data

        except Exception as e:
            logger.error(f"Failed to fetch short interest for {symbol_str}: {e}")
            return None

    def fetch_batch(
        self,
        symbols: list[Symbol],
        use_cache: bool = True,
    ) -> dict[Symbol, ShortInterestData]:
        """Fetch short interest for multiple symbols."""
        results = {}
        for symbol in symbols:
            data = self.fetch_short_interest(symbol, use_cache)
            if data is not None:
                results[symbol] = data
        return results

    def find_squeeze_candidates(
        self,
        symbols: list[Symbol],
        min_short_pct: float = 0.15,
        min_days_to_cover: float = 3.0,
    ) -> list[ShortInterestData]:
        """
        Find potential short squeeze candidates.

        Args:
            symbols: List of symbols to scan
            min_short_pct: Minimum short percent of float
            min_days_to_cover: Minimum days to cover

        Returns:
            List of ShortInterestData for squeeze candidates
        """
        candidates = []
        for symbol in symbols:
            data = self.fetch_short_interest(symbol)
            if data and data.is_squeeze_candidate(min_short_pct, min_days_to_cover):
                candidates.append(data)

        # Sort by short percent of float descending
        candidates.sort(key=lambda x: x.short_percent_of_float, reverse=True)
        return candidates

    def get_squeeze_signal(
        self,
        symbol: Symbol,
        price_data: pd.DataFrame | None = None,
        momentum_window: int = 5,
    ) -> ShortSqueezeSignal | None:
        """
        Generate short squeeze potential signal.

        Args:
            symbol: Stock symbol
            price_data: OHLCV DataFrame (optional, for momentum calc)
            momentum_window: Window for momentum calculation

        Returns:
            ShortSqueezeSignal or None
        """
        short_data = self.fetch_short_interest(symbol)
        if short_data is None:
            return None

        # Calculate price momentum if data available
        price_momentum = 0.0
        volume_spike = 1.0

        if price_data is not None and len(price_data) >= momentum_window:
            # Price momentum
            closes = price_data["close"]
            price_momentum = (closes.iloc[-1] / closes.iloc[-momentum_window] - 1)

            # Volume spike
            recent_volume = price_data["volume"].iloc[-1]
            avg_volume = price_data["volume"].rolling(window=20).mean().iloc[-1]
            if avg_volume > 0:
                volume_spike = recent_volume / avg_volume

        # Calculate squeeze score (0-1)
        # Components:
        # - Short % of float (higher = more potential)
        # - Days to cover (higher = more potential)
        # - Price momentum (positive = squeeze may be starting)
        # - Volume spike (higher = more pressure)

        short_score = min(1.0, short_data.short_percent_of_float / 0.5)  # 50% = max
        cover_score = min(1.0, short_data.short_ratio / 10.0)  # 10 days = max
        momentum_score = min(1.0, max(0.0, price_momentum * 5 + 0.5))  # Center at 0.5
        volume_score = min(1.0, volume_spike / 3.0)  # 3x avg = max

        # Weighted combination
        squeeze_score = (
            0.35 * short_score +
            0.25 * cover_score +
            0.25 * momentum_score +
            0.15 * volume_score
        )

        # Signal classification
        if squeeze_score > 0.7:
            signal = "high_squeeze_risk"
        elif squeeze_score > 0.4:
            signal = "moderate_squeeze_risk"
        else:
            signal = "low_squeeze_risk"

        return ShortSqueezeSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            squeeze_score=squeeze_score,
            short_percent_of_float=short_data.short_percent_of_float,
            days_to_cover=short_data.short_ratio,
            price_momentum=price_momentum,
            volume_spike=volume_spike,
            signal=signal,
            metadata={
                "short_score": short_score,
                "cover_score": cover_score,
                "momentum_score": momentum_score,
                "volume_score": volume_score,
            },
        )


class ShortInterestFeatures:
    """
    Feature extraction from short interest data.

    Computes features for trading strategies:
    - short_percent_of_float: Raw short interest percentage
    - days_to_cover: Short ratio
    - short_change: Change in short interest
    - squeeze_score: Composite squeeze potential
    """

    def __init__(self, source: ShortInterestSource | None = None):
        """
        Initialize short interest features.

        Args:
            source: ShortInterestSource instance
        """
        self.source = source or ShortInterestSource()

    def compute_features(
        self,
        df: pd.DataFrame,
        symbol: Symbol,
    ) -> pd.DataFrame:
        """
        Add short interest features to DataFrame.

        Note: Short interest is point-in-time data, not time series.
        Features are applied to the entire DataFrame.

        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol

        Returns:
            DataFrame with short interest feature columns
        """
        df = df.copy()

        # Fetch current short interest
        short_data = self.source.fetch_short_interest(symbol)

        if short_data is None:
            logger.warning(f"No short interest data for {symbol}")
            df["short_percent_of_float"] = np.nan
            df["short_days_to_cover"] = np.nan
            df["short_change_pct"] = np.nan
            df["short_squeeze_score"] = np.nan
            return df

        # Get squeeze signal with price data
        squeeze_signal = self.source.get_squeeze_signal(symbol, df)

        # Apply as constant features (short interest is bi-weekly)
        df["short_percent_of_float"] = short_data.short_percent_of_float
        df["short_days_to_cover"] = short_data.short_ratio
        df["short_change_pct"] = short_data.short_change_pct or 0.0

        if squeeze_signal:
            df["short_squeeze_score"] = squeeze_signal.squeeze_score
        else:
            df["short_squeeze_score"] = np.nan

        return df

    def get_squeeze_candidates(
        self,
        symbols: list[Symbol],
        min_short_pct: float = 0.15,
        min_days: float = 3.0,
    ) -> pd.DataFrame:
        """
        Get DataFrame of squeeze candidates.

        Args:
            symbols: List of symbols to scan
            min_short_pct: Minimum short % of float
            min_days: Minimum days to cover

        Returns:
            DataFrame with squeeze candidates and metrics
        """
        candidates = self.source.find_squeeze_candidates(
            symbols, min_short_pct, min_days
        )

        if not candidates:
            return pd.DataFrame()

        return pd.DataFrame([c.to_dict() for c in candidates])


def create_short_interest_source() -> ShortInterestSource | None:
    """
    Factory function to create ShortInterestSource.

    Returns:
        ShortInterestSource or None if yfinance not available
    """
    if not YFINANCE_AVAILABLE:
        logger.warning("yfinance not available, short interest features disabled")
        return None

    try:
        return ShortInterestSource()
    except Exception as e:
        logger.error(f"Failed to create ShortInterestSource: {e}")
        return None
