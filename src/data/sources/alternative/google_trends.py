"""Google Trends data source for retail attention signals.

Uses Google Trends data to measure retail investor attention and generate
contrarian or momentum signals based on search interest.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)

# Try to import pytrends
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False
    logger.warning("pytrends not installed. Install with: pip install pytrends")


@dataclass
class TrendsResult:
    """Google Trends query result."""

    keywords: list[str]
    timeframe: str
    geo: str
    interest_over_time: pd.DataFrame | None
    related_queries: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.now)
    error: str | None = None

    def is_valid(self) -> bool:
        """Check if result has valid data."""
        return (
            self.interest_over_time is not None
            and not self.interest_over_time.empty
            and self.error is None
        )


@dataclass
class RetailAttentionSignal:
    """Retail attention signal derived from Google Trends."""

    symbol: Symbol
    timestamp: datetime
    search_volume: float  # Raw normalized search volume (0-100)
    zscore: float  # Z-score vs rolling mean
    momentum: float  # Change in search volume
    percentile: float  # Percentile vs historical (0-1)
    signal: str  # 'high_attention', 'low_attention', 'normal'
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_contrarian_buy(self, threshold: float = -2.0) -> bool:
        """Check if low attention suggests contrarian buy."""
        return self.zscore < threshold

    def is_contrarian_sell(self, threshold: float = 2.0) -> bool:
        """Check if high attention suggests contrarian sell."""
        return self.zscore > threshold


class GoogleTrendsSource:
    """
    Google Trends data source for retail attention signals.

    Provides search volume data for stock tickers and related terms
    to gauge retail investor interest.
    """

    name = "google_trends"

    # Common financial search term mappings
    TICKER_SEARCH_TERMS = {
        "AAPL": ["AAPL stock", "Apple stock", "Apple stock price"],
        "MSFT": ["MSFT stock", "Microsoft stock", "Microsoft stock price"],
        "GOOGL": ["GOOGL stock", "Google stock", "Alphabet stock"],
        "AMZN": ["AMZN stock", "Amazon stock", "Amazon stock price"],
        "TSLA": ["TSLA stock", "Tesla stock", "Tesla stock price"],
        "NVDA": ["NVDA stock", "Nvidia stock", "Nvidia stock price"],
        "META": ["META stock", "Meta stock", "Facebook stock"],
        "AMD": ["AMD stock", "AMD stock price"],
        "SPY": ["SPY ETF", "S&P 500 ETF", "SPY stock"],
        "QQQ": ["QQQ ETF", "Nasdaq ETF", "QQQ stock"],
    }

    def __init__(
        self,
        hl: str = "en-US",
        tz: int = 360,
        timeout: tuple[int, int] = (10, 25),
    ):
        """
        Initialize Google Trends source.

        Args:
            hl: Host language for Google Trends
            tz: Timezone offset from UTC in minutes
            timeout: Request timeout (connect, read)
        """
        if not PYTRENDS_AVAILABLE:
            raise ImportError(
                "pytrends library not available. Install with: pip install pytrends"
            )

        self.hl = hl
        self.tz = tz
        self.timeout = timeout
        self._pytrends = None
        self._cache: dict[str, TrendsResult] = {}
        self._cache_ttl = timedelta(hours=1)

    def _get_pytrends(self) -> "TrendReq":
        """Get or create pytrends instance."""
        if self._pytrends is None:
            # Use minimal parameters to avoid urllib3 compatibility issues
            self._pytrends = TrendReq(
                hl=self.hl,
                tz=self.tz,
            )
        return self._pytrends

    def _get_search_terms(self, symbol: Symbol) -> list[str]:
        """Get search terms for a symbol."""
        symbol_str = str(symbol).upper()
        if symbol_str in self.TICKER_SEARCH_TERMS:
            return self.TICKER_SEARCH_TERMS[symbol_str]
        # Default: use ticker + " stock"
        return [f"{symbol_str} stock", f"{symbol_str} stock price"]

    def fetch_interest_over_time(
        self,
        keywords: list[str],
        timeframe: str = "today 3-m",
        geo: str = "US",
        use_cache: bool = True,
    ) -> TrendsResult:
        """
        Fetch Google Trends interest over time.

        Args:
            keywords: List of keywords to query (max 5)
            timeframe: Time range (e.g., 'today 3-m', 'today 12-m', '2024-01-01 2024-12-31')
            geo: Geographic region (e.g., 'US', 'GB', '')
            use_cache: Whether to use cached results

        Returns:
            TrendsResult with interest_over_time DataFrame
        """
        if len(keywords) > 5:
            logger.warning(f"Google Trends supports max 5 keywords, truncating from {len(keywords)}")
            keywords = keywords[:5]

        cache_key = f"{','.join(sorted(keywords))}|{timeframe}|{geo}"

        # Check cache
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached.fetched_at < self._cache_ttl:
                logger.debug(f"Using cached trends for {keywords}")
                return cached

        pytrends = self._get_pytrends()

        try:
            pytrends.build_payload(
                keywords,
                cat=0,
                timeframe=timeframe,
                geo=geo,
            )
            interest_df = pytrends.interest_over_time()

            # Remove 'isPartial' column if present
            if "isPartial" in interest_df.columns:
                interest_df = interest_df.drop(columns=["isPartial"])

            result = TrendsResult(
                keywords=keywords,
                timeframe=timeframe,
                geo=geo,
                interest_over_time=interest_df,
            )

            # Cache result
            self._cache[cache_key] = result
            logger.info(f"Fetched Google Trends for {keywords}: {len(interest_df)} data points")

            return result

        except Exception as e:
            logger.error(f"Google Trends fetch failed for {keywords}: {e}")
            return TrendsResult(
                keywords=keywords,
                timeframe=timeframe,
                geo=geo,
                interest_over_time=None,
                error=str(e),
            )

    def fetch_related_queries(
        self,
        keywords: list[str],
        timeframe: str = "today 3-m",
        geo: str = "US",
    ) -> dict[str, Any]:
        """Fetch related queries for keywords."""
        pytrends = self._get_pytrends()

        try:
            pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
            return pytrends.related_queries()
        except Exception as e:
            logger.error(f"Related queries fetch failed: {e}")
            return {}

    def get_retail_attention(
        self,
        symbol: Symbol,
        timeframe: str = "today 3-m",
        zscore_window: int = 30,
    ) -> RetailAttentionSignal | None:
        """
        Get retail attention signal for a symbol.

        Args:
            symbol: Stock symbol
            timeframe: Google Trends timeframe
            zscore_window: Window for z-score calculation (days)

        Returns:
            RetailAttentionSignal or None if fetch fails
        """
        search_terms = self._get_search_terms(symbol)

        # Use first search term as primary
        result = self.fetch_interest_over_time(
            keywords=[search_terms[0]],
            timeframe=timeframe,
        )

        if not result.is_valid():
            logger.warning(f"No trends data for {symbol}")
            return None

        df = result.interest_over_time
        primary_term = search_terms[0]

        if primary_term not in df.columns:
            logger.warning(f"Primary term {primary_term} not in trends data")
            return None

        series = df[primary_term]

        # Compute metrics
        current_value = series.iloc[-1]
        rolling_mean = series.rolling(window=zscore_window, min_periods=5).mean()
        rolling_std = series.rolling(window=zscore_window, min_periods=5).std()

        # Z-score
        zscore = (current_value - rolling_mean.iloc[-1]) / (rolling_std.iloc[-1] + 1e-8)

        # Momentum (% change over last 7 days)
        if len(series) >= 7:
            momentum = (series.iloc[-1] / series.iloc[-7] - 1) * 100
        else:
            momentum = 0.0

        # Percentile
        percentile = (series < current_value).sum() / len(series)

        # Signal classification
        if zscore > 2.0:
            signal = "high_attention"
        elif zscore < -1.5:
            signal = "low_attention"
        else:
            signal = "normal"

        return RetailAttentionSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            search_volume=float(current_value),
            zscore=float(zscore),
            momentum=float(momentum),
            percentile=float(percentile),
            signal=signal,
            metadata={
                "search_term": primary_term,
                "timeframe": timeframe,
                "data_points": len(series),
                "rolling_mean": float(rolling_mean.iloc[-1]),
                "rolling_std": float(rolling_std.iloc[-1]),
            },
        )

    def get_batch_attention(
        self,
        symbols: list[Symbol],
        timeframe: str = "today 3-m",
    ) -> dict[Symbol, RetailAttentionSignal]:
        """
        Get retail attention for multiple symbols.

        Note: Google Trends has rate limits, so this may take time.
        """
        results = {}
        for symbol in symbols:
            attention = self.get_retail_attention(symbol, timeframe)
            if attention is not None:
                results[symbol] = attention
        return results


class GoogleTrendsFeatures:
    """
    Feature extraction from Google Trends data.

    Computes features that can be used in trading strategies:
    - search_volume_zscore: Normalized attention level
    - attention_momentum: Rate of change in attention
    - contrarian_signal: High/low attention indicator
    """

    def __init__(self, trends_source: GoogleTrendsSource | None = None):
        """
        Initialize Google Trends features.

        Args:
            trends_source: GoogleTrendsSource instance (creates new if None)
        """
        self.source = trends_source or GoogleTrendsSource()

    def compute_features(
        self,
        df: pd.DataFrame,
        symbol: Symbol,
        timeframe: str = "today 3-m",
    ) -> pd.DataFrame:
        """
        Compute Google Trends features for a symbol.

        Args:
            df: OHLCV DataFrame with DatetimeIndex
            symbol: Stock symbol
            timeframe: Google Trends timeframe

        Returns:
            DataFrame with additional Google Trends feature columns
        """
        df = df.copy()

        # Get trends data
        search_terms = self.source._get_search_terms(symbol)
        result = self.source.fetch_interest_over_time(
            keywords=[search_terms[0]],
            timeframe=timeframe,
        )

        if not result.is_valid():
            logger.warning(f"No Google Trends data for {symbol}, returning empty features")
            df["google_trends_volume"] = np.nan
            df["google_trends_zscore"] = np.nan
            df["google_trends_momentum"] = np.nan
            df["google_trends_percentile"] = np.nan
            df["google_trends_contrarian"] = np.nan
            return df

        trends_df = result.interest_over_time
        primary_term = search_terms[0]

        if primary_term not in trends_df.columns:
            logger.warning(f"Primary term not in trends data")
            df["google_trends_volume"] = np.nan
            df["google_trends_zscore"] = np.nan
            df["google_trends_momentum"] = np.nan
            df["google_trends_percentile"] = np.nan
            df["google_trends_contrarian"] = np.nan
            return df

        # Resample trends to daily if needed and align with price data
        trends_series = trends_df[primary_term]

        # Compute features on trends data
        window = 30
        trends_mean = trends_series.rolling(window=window, min_periods=5).mean()
        trends_std = trends_series.rolling(window=window, min_periods=5).std()
        zscore = (trends_series - trends_mean) / (trends_std + 1e-8)
        momentum = trends_series.pct_change(periods=7) * 100
        percentile = trends_series.rolling(window=90, min_periods=30).apply(
            lambda x: (x < x.iloc[-1]).sum() / len(x), raw=False
        )

        # Contrarian signal: positive when attention is unusually low
        contrarian = -zscore  # Flip sign: low attention = positive signal

        # Create features DataFrame with trends index
        features = pd.DataFrame({
            "google_trends_volume": trends_series,
            "google_trends_zscore": zscore,
            "google_trends_momentum": momentum,
            "google_trends_percentile": percentile,
            "google_trends_contrarian": contrarian,
        }, index=trends_series.index)

        # Merge with price data using forward fill
        # Trends data is often weekly, so we forward fill to daily
        df = df.join(features, how="left")
        df[features.columns] = df[features.columns].ffill()

        return df

    def search_volume_zscore(
        self,
        trends_df: pd.DataFrame,
        column: str,
        window: int = 30,
    ) -> pd.Series:
        """
        Compute z-score of search volume.

        Args:
            trends_df: Trends DataFrame from GoogleTrendsSource
            column: Column name to compute z-score for
            window: Rolling window for mean/std

        Returns:
            Z-score series
        """
        series = trends_df[column]
        rolling_mean = series.rolling(window=window, min_periods=5).mean()
        rolling_std = series.rolling(window=window, min_periods=5).std()
        return (series - rolling_mean) / (rolling_std + 1e-8)

    def contrarian_signal(
        self,
        trends_df: pd.DataFrame,
        column: str,
        buy_threshold: float = -2.0,
        sell_threshold: float = 2.0,
        window: int = 30,
    ) -> pd.Series:
        """
        Generate contrarian signal based on attention extremes.

        Args:
            trends_df: Trends DataFrame
            column: Column name
            buy_threshold: Z-score below which to generate buy signal
            sell_threshold: Z-score above which to generate sell signal
            window: Rolling window for z-score

        Returns:
            Series with values: 1 (buy), -1 (sell), 0 (neutral)
        """
        zscore = self.search_volume_zscore(trends_df, column, window)

        signal = pd.Series(0, index=zscore.index)
        signal[zscore < buy_threshold] = 1  # Low attention = contrarian buy
        signal[zscore > sell_threshold] = -1  # High attention = contrarian sell

        return signal

    def attention_momentum(
        self,
        trends_df: pd.DataFrame,
        column: str,
        periods: int = 7,
    ) -> pd.Series:
        """
        Compute momentum in attention (rate of change).

        Args:
            trends_df: Trends DataFrame
            column: Column name
            periods: Lookback periods for momentum

        Returns:
            Momentum series (percentage change)
        """
        return trends_df[column].pct_change(periods=periods) * 100


def create_google_trends_source() -> GoogleTrendsSource | None:
    """
    Factory function to create GoogleTrendsSource with proper error handling.

    Returns:
        GoogleTrendsSource or None if pytrends not available
    """
    if not PYTRENDS_AVAILABLE:
        logger.warning("pytrends not available, Google Trends features disabled")
        return None

    try:
        return GoogleTrendsSource()
    except Exception as e:
        logger.error(f"Failed to create GoogleTrendsSource: {e}")
        return None
