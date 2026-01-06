"""Intraday data pipeline for real-time minute-level data.

Provides:
- Real-time minute bar data from Alpaca
- Historical intraday data from yfinance (fallback)
- Session-filtered data (regular hours only)
- Pre-computed indicators for strategies
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time, date
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IntradayDataConfig:
    """Configuration for intraday data pipeline."""
    symbols: list[str]
    timeframe: str = "5Min"  # 1Min, 5Min, 15Min
    lookback_days: int = 5  # Days of history to load
    include_premarket: bool = False
    include_afterhours: bool = False
    auto_refresh_seconds: int = 60  # Refresh interval


# Market hours (ET)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_START = time(4, 0)
AFTERHOURS_END = time(20, 0)


def is_market_open(t: datetime | None = None) -> bool:
    """Check if market is currently open."""
    t = t or datetime.now()
    current_time = t.time()
    weekday = t.weekday()

    # Weekends
    if weekday >= 5:
        return False

    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def get_session_data(
    df: pd.DataFrame,
    include_premarket: bool = False,
    include_afterhours: bool = False,
) -> pd.DataFrame:
    """
    Filter data to trading session only.

    Args:
        df: DataFrame with DatetimeIndex
        include_premarket: Include 4:00-9:30 AM
        include_afterhours: Include 4:00-8:00 PM

    Returns:
        Filtered DataFrame
    """
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df

    times = df.index.time

    if include_premarket and include_afterhours:
        # Full extended hours
        mask = (times >= PREMARKET_START) | (times <= AFTERHOURS_END)
    elif include_premarket:
        mask = (times >= PREMARKET_START) & (times <= MARKET_CLOSE)
    elif include_afterhours:
        mask = ((times >= MARKET_OPEN) & (times <= AFTERHOURS_END))
    else:
        # Regular hours only
        mask = (times >= MARKET_OPEN) & (times <= MARKET_CLOSE)

    return df[mask]


def compute_intraday_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute common intraday indicators.

    Adds columns:
    - vwap: Volume Weighted Average Price
    - atr: Average True Range (14 period)
    - cum_volume: Cumulative session volume
    - volume_ma: 20-period volume MA
    - rsi: RSI (14 period)
    - ema_9, ema_21: Exponential moving averages
    """
    if df.empty:
        return df

    df = df.copy()

    # VWAP (resets each day)
    df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
    df["tp_volume"] = df["typical_price"] * df["volume"]

    # Group by date for daily reset
    df["date"] = df.index.date
    df["cum_tp_vol"] = df.groupby("date")["tp_volume"].cumsum()
    df["cum_volume"] = df.groupby("date")["volume"].cumsum()
    df["vwap"] = df["cum_tp_vol"] / df["cum_volume"].replace(0, np.nan)

    # ATR
    df["tr"] = pd.concat([
        df["high"] - df["low"],
        abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1)),
    ], axis=1).max(axis=1)
    df["atr"] = df["tr"].rolling(14).mean()

    # Volume MA
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma"].replace(0, np.nan)

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta).where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # EMAs
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()

    # Clean up temp columns
    df.drop(columns=["typical_price", "tp_volume", "cum_tp_vol", "tr", "date"], inplace=True)

    return df


class IntradayDataPipeline:
    """
    Real-time intraday data pipeline.

    Fetches and maintains minute-level data for intraday strategies.
    """

    def __init__(
        self,
        config: IntradayDataConfig,
        alpaca_api_key: str | None = None,
        alpaca_secret_key: str | None = None,
    ):
        """
        Initialize intraday data pipeline.

        Args:
            config: Pipeline configuration
            alpaca_api_key: Alpaca API key
            alpaca_secret_key: Alpaca secret key
        """
        self.config = config
        self.alpaca_api_key = alpaca_api_key
        self.alpaca_secret_key = alpaca_secret_key

        # Data cache
        self._data: dict[str, pd.DataFrame] = {}
        self._last_update: dict[str, datetime] = {}

    async def initialize(self) -> None:
        """Initialize pipeline with historical data."""
        for symbol in self.config.symbols:
            await self.refresh_symbol(symbol)

    async def refresh_symbol(self, symbol: str) -> pd.DataFrame:
        """
        Refresh data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Updated DataFrame
        """
        try:
            df = await self._fetch_data(symbol)

            if df is not None and not df.empty:
                # Filter to session
                df = get_session_data(
                    df,
                    include_premarket=self.config.include_premarket,
                    include_afterhours=self.config.include_afterhours,
                )

                # Compute indicators
                df = compute_intraday_indicators(df)

                self._data[symbol] = df
                self._last_update[symbol] = datetime.now()

                logger.info(f"Refreshed {symbol}: {len(df)} bars")

            return df

        except Exception as e:
            logger.error(f"Error refreshing {symbol}: {e}")
            return pd.DataFrame()

    async def _fetch_data(self, symbol: str) -> pd.DataFrame:
        """
        Fetch intraday data for a symbol.

        Uses Alpaca if available, falls back to yfinance.
        """
        # Try Alpaca first
        if self.alpaca_api_key:
            try:
                return await self._fetch_alpaca(symbol)
            except Exception as e:
                logger.warning(f"Alpaca fetch failed for {symbol}: {e}, trying yfinance")

        # Fallback to yfinance
        return self._fetch_yfinance(symbol)

    async def _fetch_alpaca(self, symbol: str) -> pd.DataFrame:
        """Fetch from Alpaca."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            client = StockHistoricalDataClient(
                self.alpaca_api_key,
                self.alpaca_secret_key,
            )

            # Map timeframe
            tf_map = {
                "1Min": TimeFrame(1, TimeFrameUnit.Minute),
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            }
            timeframe = tf_map.get(self.config.timeframe, TimeFrame(5, TimeFrameUnit.Minute))

            # Request
            end = datetime.now()
            start = end - timedelta(days=self.config.lookback_days)

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                start=start,
                end=end,
                timeframe=timeframe,
            )

            bars = client.get_stock_bars(request)

            if symbol in bars:
                df = bars[symbol].df
                df = df.rename(columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                })
                return df[["open", "high", "low", "close", "volume"]]

            return pd.DataFrame()

        except ImportError:
            logger.warning("Alpaca SDK not installed")
            raise

    def _fetch_yfinance(self, symbol: str) -> pd.DataFrame:
        """Fetch from yfinance (fallback)."""
        try:
            import yfinance as yf

            # yfinance interval options: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h
            tf_map = {
                "1Min": "1m",
                "5Min": "5m",
                "15Min": "15m",
            }
            interval = tf_map.get(self.config.timeframe, "5m")

            # yfinance limits: 1m = 7 days, 5m = 60 days
            days = min(self.config.lookback_days, 7 if interval == "1m" else 60)

            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d", interval=interval)

            if df.empty:
                return df

            # Standardize columns
            df.columns = df.columns.str.lower()
            df = df[["open", "high", "low", "close", "volume"]]

            return df

        except ImportError:
            logger.error("yfinance not installed")
            return pd.DataFrame()

    def get_data(self, symbol: str) -> pd.DataFrame:
        """
        Get cached data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            DataFrame with OHLCV + indicators
        """
        return self._data.get(symbol, pd.DataFrame())

    def get_latest_bar(self, symbol: str) -> pd.Series | None:
        """
        Get the most recent bar for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Series with latest bar data
        """
        df = self.get_data(symbol)
        if df.empty:
            return None
        return df.iloc[-1]

    def get_current_vwap(self, symbol: str) -> float | None:
        """Get current VWAP for a symbol."""
        bar = self.get_latest_bar(symbol)
        if bar is None:
            return None
        return float(bar.get("vwap")) if "vwap" in bar else None

    def get_session_data_today(self, symbol: str) -> pd.DataFrame:
        """Get today's session data only."""
        df = self.get_data(symbol)
        if df.empty:
            return df

        today = date.today()
        return df[df.index.date == today]

    def needs_refresh(self, symbol: str) -> bool:
        """Check if symbol needs refresh."""
        last = self._last_update.get(symbol)
        if last is None:
            return True
        age = (datetime.now() - last).total_seconds()
        return age >= self.config.auto_refresh_seconds

    async def refresh_all(self) -> dict[str, int]:
        """
        Refresh all symbols that need updating.

        Returns:
            Dict of symbol -> bar count
        """
        results = {}

        for symbol in self.config.symbols:
            if self.needs_refresh(symbol):
                df = await self.refresh_symbol(symbol)
                results[symbol] = len(df)

        return results

    def get_summary(self) -> dict[str, Any]:
        """Get pipeline summary."""
        return {
            "symbols": self.config.symbols,
            "timeframe": self.config.timeframe,
            "cached_symbols": list(self._data.keys()),
            "last_updates": {
                symbol: dt.isoformat() if dt else None
                for symbol, dt in self._last_update.items()
            },
            "bar_counts": {
                symbol: len(df) for symbol, df in self._data.items()
            },
        }


async def create_intraday_pipeline(
    symbols: list[str],
    timeframe: str = "5Min",
    lookback_days: int = 5,
    alpaca_api_key: str | None = None,
    alpaca_secret_key: str | None = None,
) -> IntradayDataPipeline:
    """
    Create and initialize an intraday data pipeline.

    Args:
        symbols: List of symbols
        timeframe: Bar timeframe
        lookback_days: Days of history
        alpaca_api_key: Alpaca API key
        alpaca_secret_key: Alpaca secret key

    Returns:
        Initialized IntradayDataPipeline
    """
    config = IntradayDataConfig(
        symbols=symbols,
        timeframe=timeframe,
        lookback_days=lookback_days,
    )

    pipeline = IntradayDataPipeline(
        config=config,
        alpaca_api_key=alpaca_api_key,
        alpaca_secret_key=alpaca_secret_key,
    )

    await pipeline.initialize()

    return pipeline
