"""Data access tools for LLM agents.

Provides structured interfaces for querying market data, computing features,
and performing market analysis. All functions return JSON-serializable dicts.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd

from ...core import Symbol, Timeframe
from ...data.features import FeatureEngine

logger = logging.getLogger(__name__)


# Tool schemas for LLM discovery
TOOL_SCHEMAS = {
    "get_market_data": {
        "name": "get_market_data",
        "description": "Fetch OHLCV market data for one or more symbols",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of stock symbols (e.g., ['AAPL', 'MSFT'])",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (default: today)",
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d", "1w"],
                    "description": "Data timeframe (default: 1d)",
                },
            },
            "required": ["symbols", "start_date"],
        },
    },
    "get_features": {
        "name": "get_features",
        "description": "Compute technical indicators and features for a symbol",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol"},
                "feature_set": {
                    "type": "string",
                    "enum": ["minimal", "standard", "full"],
                    "description": "Feature set to compute",
                },
                "start_date": {"type": "string", "description": "Start date"},
                "end_date": {"type": "string", "description": "End date"},
            },
            "required": ["symbol"],
        },
    },
    "get_market_summary": {
        "name": "get_market_summary",
        "description": "Get a comprehensive market summary for analysis",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Symbols to summarize",
                },
                "lookback_days": {
                    "type": "integer",
                    "description": "Days of history to analyze",
                },
            },
            "required": ["symbols"],
        },
    },
}


@dataclass
class DataQueryResult:
    """Result from a data query."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


class DataQueryTool:
    """Tool for LLM agents to query market data."""

    def __init__(
        self,
        data_source: Any | None = None,
        storage: Any | None = None,
        cache_ttl: int = 300,
    ):
        """
        Initialize data query tool.

        Args:
            data_source: Data source for fetching new data
            storage: Storage for cached data
            cache_ttl: Cache time-to-live in seconds
        """
        self._data_source = data_source
        self._storage = storage
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[datetime, pd.DataFrame]] = {}

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema for LLM discovery."""
        return TOOL_SCHEMAS["get_market_data"]

    def _get_from_cache(self, key: str) -> pd.DataFrame | None:
        """Get data from cache if not expired."""
        if key in self._cache:
            cached_time, data = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: pd.DataFrame) -> None:
        """Set data in cache."""
        self._cache[key] = (datetime.now(), data)

    async def query(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
        timeframe: str = "1d",
    ) -> DataQueryResult:
        """
        Query market data for symbols.

        Args:
            symbols: List of symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), default today
            timeframe: Data timeframe

        Returns:
            DataQueryResult with OHLCV data
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

            results = {}
            for symbol in symbols:
                cache_key = f"{symbol}_{start_date}_{end_date}_{timeframe}"
                cached = self._get_from_cache(cache_key)

                if cached is not None:
                    df = cached
                elif self._data_source is not None:
                    df = await self._data_source.fetch(symbol, start, end)
                    self._set_cache(cache_key, df)
                elif self._storage is not None:
                    df = self._storage.load(symbol)
                    if df is not None:
                        df = df[(df.index >= start) & (df.index <= end)]
                        self._set_cache(cache_key, df)
                else:
                    # Generate sample data for testing
                    df = self._generate_sample_data(symbol, start, end)

                if df is not None and not df.empty:
                    results[symbol] = self._dataframe_to_dict(df)

            return DataQueryResult(
                success=True,
                data=results,
                metadata={
                    "symbols": symbols,
                    "start_date": start_date,
                    "end_date": end_date or datetime.now().strftime("%Y-%m-%d"),
                    "timeframe": timeframe,
                    "rows_per_symbol": {s: len(d["close"]) for s, d in results.items()},
                },
            )

        except Exception as e:
            logger.error(f"Data query failed: {e}")
            return DataQueryResult(success=False, error=str(e))

    def _generate_sample_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Generate sample data for testing."""
        dates = pd.date_range(start=start, end=end, freq="D")
        dates = dates[dates.dayofweek < 5]  # Business days only

        np.random.seed(hash(symbol) % 2**32)
        n = len(dates)

        # Random walk for prices
        returns = np.random.normal(0.0005, 0.02, n)
        close = 100 * np.exp(np.cumsum(returns))

        # Generate OHLCV
        high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
        open_ = low + (high - low) * np.random.random(n)
        volume = np.random.lognormal(15, 1, n).astype(int)

        return pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )

    def _dataframe_to_dict(self, df: pd.DataFrame) -> dict[str, Any]:
        """Convert DataFrame to JSON-serializable dict."""
        result = {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "open": df["open"].round(2).tolist(),
            "high": df["high"].round(2).tolist(),
            "low": df["low"].round(2).tolist(),
            "close": df["close"].round(2).tolist(),
            "volume": df["volume"].astype(int).tolist(),
        }

        # Add any additional columns
        for col in df.columns:
            if col not in ["open", "high", "low", "close", "volume"]:
                if df[col].dtype in [np.float64, np.float32]:
                    result[col] = df[col].round(4).tolist()
                else:
                    result[col] = df[col].tolist()

        return result


class FeatureEngineTool:
    """Tool for computing technical features."""

    def __init__(self, data_tool: DataQueryTool | None = None):
        """Initialize feature engine tool."""
        self._data_tool = data_tool or DataQueryTool()

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema for LLM discovery."""
        return TOOL_SCHEMAS["get_features"]

    async def compute_features(
        self,
        symbol: str,
        feature_set: Literal["minimal", "standard", "full"] = "standard",
        start_date: str | None = None,
        end_date: str | None = None,
        custom_features: list[str] | None = None,
    ) -> DataQueryResult:
        """
        Compute technical features for a symbol.

        Args:
            symbol: Stock symbol
            feature_set: Predefined feature set
            start_date: Start date
            end_date: End date
            custom_features: List of specific features to compute

        Returns:
            DataQueryResult with feature data
        """
        try:
            # Default date range
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d")

            # Get base data
            data_result = await self._data_tool.query(
                symbols=[symbol],
                start_date=start_date,
                end_date=end_date,
            )

            if not data_result.success or symbol not in data_result.data:
                return DataQueryResult(
                    success=False,
                    error=f"Failed to get data for {symbol}",
                )

            # Convert back to DataFrame
            raw_data = data_result.data[symbol]
            df = pd.DataFrame(
                {
                    "open": raw_data["open"],
                    "high": raw_data["high"],
                    "low": raw_data["low"],
                    "close": raw_data["close"],
                    "volume": raw_data["volume"],
                },
                index=pd.to_datetime(raw_data["dates"]),
            )

            # Compute features based on set
            if feature_set == "minimal":
                df = self._add_minimal_features(df)
            elif feature_set == "standard":
                df = self._add_standard_features(df)
            else:  # full
                df = FeatureEngine.add_all_features(df)

            # Add custom features if specified
            if custom_features:
                df = self._add_custom_features(df, custom_features)

            # Convert to dict
            feature_dict = self._dataframe_to_feature_dict(df)

            return DataQueryResult(
                success=True,
                data={
                    "symbol": symbol,
                    "features": feature_dict,
                    "feature_names": list(feature_dict.keys()),
                    "n_features": len(feature_dict) - 1,  # Exclude dates
                },
                metadata={
                    "feature_set": feature_set,
                    "start_date": start_date,
                    "end_date": end_date,
                    "n_rows": len(df),
                },
            )

        except Exception as e:
            logger.error(f"Feature computation failed: {e}")
            return DataQueryResult(success=False, error=str(e))

    def _add_minimal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add minimal feature set."""
        df = df.copy()

        # Returns
        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))

        # Moving averages
        df["sma_20"] = df["close"].rolling(20).mean()
        df["sma_50"] = df["close"].rolling(50).mean()

        # Volatility
        df["volatility_20"] = df["returns"].rolling(20).std() * np.sqrt(252)

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        return df

    def _add_standard_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add standard feature set."""
        df = self._add_minimal_features(df)

        # Bollinger Bands
        df["bb_middle"] = df["close"].rolling(20).mean()
        bb_std = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_middle"] + 2 * bb_std
        df["bb_lower"] = df["bb_middle"] - 2 * bb_std
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (
            df["bb_upper"] - df["bb_lower"]
        )

        # MACD
        ema12 = df["close"].ewm(span=12).mean()
        ema26 = df["close"].ewm(span=26).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # ATR
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()

        # Volume features
        df["volume_sma"] = df["volume"].rolling(20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        # Momentum
        df["momentum_10"] = df["close"] / df["close"].shift(10) - 1
        df["momentum_20"] = df["close"] / df["close"].shift(20) - 1

        return df

    def _add_custom_features(
        self,
        df: pd.DataFrame,
        features: list[str],
    ) -> pd.DataFrame:
        """Add specific custom features."""
        # Map feature names to computation functions
        feature_map = {
            "sma": lambda d, p: d["close"].rolling(p).mean(),
            "ema": lambda d, p: d["close"].ewm(span=p).mean(),
            "rsi": lambda d, p: self._compute_rsi(d, p),
            "atr": lambda d, p: self._compute_atr(d, p),
            "volatility": lambda d, p: d["close"].pct_change().rolling(p).std()
            * np.sqrt(252),
        }

        for feature in features:
            # Parse feature name (e.g., "sma_10", "rsi_14")
            parts = feature.lower().split("_")
            if len(parts) >= 2:
                name = parts[0]
                try:
                    period = int(parts[1])
                except ValueError:
                    continue

                if name in feature_map:
                    df[feature] = feature_map[name](df, period)

        return df

    def _compute_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Compute RSI."""
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _compute_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Compute ATR."""
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _dataframe_to_feature_dict(self, df: pd.DataFrame) -> dict[str, list]:
        """Convert feature DataFrame to dict."""
        result = {"dates": df.index.strftime("%Y-%m-%d").tolist()}

        for col in df.columns:
            if df[col].dtype in [np.float64, np.float32]:
                # Handle NaN values
                values = df[col].fillna(0).round(6).tolist()
            else:
                values = df[col].tolist()
            result[col] = values

        return result


class MarketAnalysisTool:
    """Tool for market analysis and summarization."""

    def __init__(self, data_tool: DataQueryTool | None = None):
        """Initialize market analysis tool."""
        self._data_tool = data_tool or DataQueryTool()

    @property
    def schema(self) -> dict[str, Any]:
        """Get tool schema for LLM discovery."""
        return TOOL_SCHEMAS["get_market_summary"]

    async def get_summary(
        self,
        symbols: list[str],
        lookback_days: int = 30,
    ) -> DataQueryResult:
        """
        Get comprehensive market summary.

        Args:
            symbols: Symbols to analyze
            lookback_days: Days of history

        Returns:
            DataQueryResult with market summary
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days + 50)  # Extra for indicators

            # Get data
            data_result = await self._data_tool.query(
                symbols=symbols,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )

            if not data_result.success:
                return data_result

            summaries = {}
            for symbol, raw_data in data_result.data.items():
                df = pd.DataFrame(
                    {
                        "open": raw_data["open"],
                        "high": raw_data["high"],
                        "low": raw_data["low"],
                        "close": raw_data["close"],
                        "volume": raw_data["volume"],
                    },
                    index=pd.to_datetime(raw_data["dates"]),
                )

                # Trim to lookback period for analysis
                df = df.tail(lookback_days)

                summaries[symbol] = self._compute_summary(df, symbol)

            # Add cross-asset analysis
            if len(symbols) > 1:
                cross_asset = await self._compute_cross_asset_analysis(
                    data_result.data, lookback_days
                )
            else:
                cross_asset = None

            return DataQueryResult(
                success=True,
                data={
                    "symbols": summaries,
                    "cross_asset": cross_asset,
                    "analysis_date": end_date.strftime("%Y-%m-%d"),
                },
                metadata={
                    "lookback_days": lookback_days,
                    "n_symbols": len(symbols),
                },
            )

        except Exception as e:
            logger.error(f"Market analysis failed: {e}")
            return DataQueryResult(success=False, error=str(e))

    def _compute_summary(self, df: pd.DataFrame, symbol: str) -> dict[str, Any]:
        """Compute summary statistics for a symbol."""
        returns = df["close"].pct_change().dropna()

        # Price stats
        current_price = df["close"].iloc[-1]
        price_change = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
        high_52w = df["high"].max()
        low_52w = df["low"].min()

        # Return stats
        total_return = price_change
        annualized_return = (1 + total_return) ** (252 / len(df)) - 1
        volatility = returns.std() * np.sqrt(252)
        sharpe = annualized_return / volatility if volatility > 0 else 0

        # Drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Trend indicators
        sma_20 = df["close"].rolling(20).mean().iloc[-1]
        sma_50 = df["close"].rolling(50).mean().iloc[-1] if len(df) >= 50 else None

        # Determine trend
        if sma_50 is not None:
            if current_price > sma_20 > sma_50:
                trend = "strong_uptrend"
            elif current_price > sma_20:
                trend = "uptrend"
            elif current_price < sma_20 < sma_50:
                trend = "strong_downtrend"
            elif current_price < sma_20:
                trend = "downtrend"
            else:
                trend = "sideways"
        else:
            trend = "uptrend" if current_price > sma_20 else "downtrend"

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + gain / loss)) if loss != 0 else 50

        # Volume analysis
        avg_volume = df["volume"].mean()
        recent_volume = df["volume"].tail(5).mean()
        volume_trend = "increasing" if recent_volume > avg_volume * 1.2 else (
            "decreasing" if recent_volume < avg_volume * 0.8 else "stable"
        )

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "price_change_pct": round(price_change * 100, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "distance_from_high_pct": round(
                (current_price / high_52w - 1) * 100, 2
            ),
            "returns": {
                "total": round(total_return * 100, 2),
                "annualized": round(annualized_return * 100, 2),
                "volatility": round(volatility * 100, 2),
                "sharpe_ratio": round(sharpe, 2),
                "max_drawdown": round(max_drawdown * 100, 2),
            },
            "technical": {
                "trend": trend,
                "rsi_14": round(rsi, 1),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2) if sma_50 else None,
                "above_sma_20": current_price > sma_20,
                "above_sma_50": current_price > sma_50 if sma_50 else None,
            },
            "volume": {
                "average": int(avg_volume),
                "recent": int(recent_volume),
                "trend": volume_trend,
            },
            "signal_summary": self._generate_signal_summary(
                trend, rsi, current_price, sma_20, sma_50
            ),
        }

    def _generate_signal_summary(
        self,
        trend: str,
        rsi: float,
        price: float,
        sma_20: float,
        sma_50: float | None,
    ) -> dict[str, Any]:
        """Generate trading signal summary."""
        signals = []
        overall_bias = 0

        # Trend signals
        if trend in ["strong_uptrend", "uptrend"]:
            signals.append({"type": "trend", "signal": "bullish", "strength": 0.7})
            overall_bias += 1
        elif trend in ["strong_downtrend", "downtrend"]:
            signals.append({"type": "trend", "signal": "bearish", "strength": 0.7})
            overall_bias -= 1

        # RSI signals
        if rsi > 70:
            signals.append({"type": "rsi", "signal": "overbought", "strength": 0.6})
            overall_bias -= 0.5
        elif rsi < 30:
            signals.append({"type": "rsi", "signal": "oversold", "strength": 0.6})
            overall_bias += 0.5

        # MA crossover
        if sma_50 is not None:
            if sma_20 > sma_50 and price > sma_20:
                signals.append({"type": "ma_cross", "signal": "bullish", "strength": 0.5})
                overall_bias += 0.5
            elif sma_20 < sma_50 and price < sma_20:
                signals.append({"type": "ma_cross", "signal": "bearish", "strength": 0.5})
                overall_bias -= 0.5

        # Determine overall signal
        if overall_bias > 0.5:
            overall = "bullish"
        elif overall_bias < -0.5:
            overall = "bearish"
        else:
            overall = "neutral"

        return {
            "overall": overall,
            "bias_score": round(overall_bias, 2),
            "individual_signals": signals,
        }

    async def _compute_cross_asset_analysis(
        self,
        data: dict[str, dict],
        lookback_days: int,
    ) -> dict[str, Any]:
        """Compute cross-asset correlation analysis."""
        # Build returns DataFrame
        returns_dict = {}
        for symbol, raw_data in data.items():
            closes = pd.Series(raw_data["close"], index=pd.to_datetime(raw_data["dates"]))
            returns_dict[symbol] = closes.pct_change().dropna().tail(lookback_days)

        returns_df = pd.DataFrame(returns_dict).dropna()

        if returns_df.empty or len(returns_df.columns) < 2:
            return None

        # Correlation matrix
        corr_matrix = returns_df.corr()

        # Find highest and lowest correlations
        correlations = []
        symbols = list(corr_matrix.columns)
        for i, sym1 in enumerate(symbols):
            for j, sym2 in enumerate(symbols):
                if i < j:
                    correlations.append({
                        "pair": f"{sym1}-{sym2}",
                        "correlation": round(corr_matrix.loc[sym1, sym2], 3),
                    })

        correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        return {
            "correlation_matrix": {
                s: {s2: round(v, 3) for s2, v in corr_matrix[s].items()}
                for s in corr_matrix.columns
            },
            "top_correlations": correlations[:5],
            "average_correlation": round(
                corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean(),
                3,
            ),
        }

    async def get_correlation_matrix(
        self,
        symbols: list[str],
        lookback_days: int = 60,
    ) -> DataQueryResult:
        """Get correlation matrix for symbols."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days + 10)

            data_result = await self._data_tool.query(
                symbols=symbols,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )

            if not data_result.success:
                return data_result

            cross_asset = await self._compute_cross_asset_analysis(
                data_result.data, lookback_days
            )

            if cross_asset is None:
                return DataQueryResult(
                    success=False,
                    error="Not enough data for correlation analysis",
                )

            return DataQueryResult(
                success=True,
                data=cross_asset,
                metadata={
                    "symbols": symbols,
                    "lookback_days": lookback_days,
                },
            )

        except Exception as e:
            logger.error(f"Correlation analysis failed: {e}")
            return DataQueryResult(success=False, error=str(e))


# Convenience functions for direct LLM use
async def get_market_data(
    symbols: list[str],
    start_date: str,
    end_date: str | None = None,
    timeframe: str = "1d",
) -> dict[str, Any]:
    """
    Fetch OHLCV market data.

    Args:
        symbols: List of stock symbols
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        timeframe: Data timeframe

    Returns:
        Dict with success status and data
    """
    tool = DataQueryTool()
    result = await tool.query(symbols, start_date, end_date, timeframe)
    return result.to_dict()


async def get_features(
    symbol: str,
    feature_set: str = "standard",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Compute technical features for a symbol.

    Args:
        symbol: Stock symbol
        feature_set: "minimal", "standard", or "full"
        start_date: Start date
        end_date: End date

    Returns:
        Dict with success status and features
    """
    tool = FeatureEngineTool()
    result = await tool.compute_features(symbol, feature_set, start_date, end_date)
    return result.to_dict()


async def get_market_summary(
    symbols: list[str],
    lookback_days: int = 30,
) -> dict[str, Any]:
    """
    Get comprehensive market summary.

    Args:
        symbols: Symbols to analyze
        lookback_days: Days of history

    Returns:
        Dict with market summary
    """
    tool = MarketAnalysisTool()
    result = await tool.get_summary(symbols, lookback_days)
    return result.to_dict()


async def get_correlation_matrix(
    symbols: list[str],
    lookback_days: int = 60,
) -> dict[str, Any]:
    """
    Get correlation matrix for symbols.

    Args:
        symbols: Symbols to analyze
        lookback_days: Days for correlation calculation

    Returns:
        Dict with correlation matrix
    """
    tool = MarketAnalysisTool()
    result = await tool.get_correlation_matrix(symbols, lookback_days)
    return result.to_dict()


async def get_symbol_info(symbol: str) -> dict[str, Any]:
    """
    Get basic info about a symbol.

    Args:
        symbol: Stock symbol

    Returns:
        Dict with symbol information
    """
    tool = MarketAnalysisTool()
    result = await tool.get_summary([symbol], lookback_days=252)
    if result.success and symbol in result.data.get("symbols", {}):
        return {
            "success": True,
            "data": result.data["symbols"][symbol],
        }
    return {"success": False, "error": "Symbol not found"}
