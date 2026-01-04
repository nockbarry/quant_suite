"""Feature engineering for trading strategies."""

from typing import Callable

import numpy as np
import pandas as pd


class FeatureEngine:
    """
    Feature engineering utilities for OHLCV data.

    Provides methods to compute technical indicators, rolling features,
    and labels for ML models.
    """

    @staticmethod
    def add_returns(
        df: pd.DataFrame,
        periods: list[int] | None = None,
        column: str = "close",
    ) -> pd.DataFrame:
        """
        Add return columns for various periods.

        Args:
            df: OHLCV DataFrame
            periods: List of periods for returns (default: [1, 5, 10, 21])
            column: Price column to use

        Returns:
            DataFrame with return columns added
        """
        periods = periods or [1, 5, 10, 21]
        df = df.copy()

        for period in periods:
            df[f"return_{period}d"] = df[column].pct_change(period)

        # Log returns
        df["log_return"] = np.log(df[column] / df[column].shift(1))

        return df

    @staticmethod
    def add_volatility(
        df: pd.DataFrame,
        windows: list[int] | None = None,
        column: str = "close",
    ) -> pd.DataFrame:
        """
        Add volatility features.

        Args:
            df: OHLCV DataFrame
            windows: Rolling window sizes (default: [5, 10, 21, 63])
            column: Price column to use

        Returns:
            DataFrame with volatility columns
        """
        windows = windows or [5, 10, 21, 63]
        df = df.copy()

        log_returns = np.log(df[column] / df[column].shift(1))

        for window in windows:
            # Historical volatility (annualized)
            df[f"volatility_{window}d"] = log_returns.rolling(window).std() * np.sqrt(252)

        # Parkinson volatility (using high/low)
        if "high" in df.columns and "low" in df.columns:
            log_hl = np.log(df["high"] / df["low"])
            df["parkinson_vol"] = (
                log_hl.rolling(21).apply(
                    lambda x: np.sqrt((1 / (4 * np.log(2))) * (x**2).mean())
                )
                * np.sqrt(252)
            )

        return df

    @staticmethod
    def add_moving_averages(
        df: pd.DataFrame,
        windows: list[int] | None = None,
        column: str = "close",
    ) -> pd.DataFrame:
        """
        Add simple and exponential moving averages.

        Args:
            df: OHLCV DataFrame
            windows: Window sizes (default: [5, 10, 20, 50, 200])
            column: Price column to use

        Returns:
            DataFrame with MA columns
        """
        windows = windows or [5, 10, 20, 50, 200]
        df = df.copy()

        for window in windows:
            df[f"sma_{window}"] = df[column].rolling(window).mean()
            df[f"ema_{window}"] = df[column].ewm(span=window, adjust=False).mean()

        return df

    @staticmethod
    def add_momentum_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add momentum-based technical indicators.

        Includes RSI, MACD, Stochastic, Williams %R.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with momentum indicators
        """
        df = df.copy()
        close = df["close"]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Stochastic Oscillator
        if "high" in df.columns and "low" in df.columns:
            low_14 = df["low"].rolling(14).min()
            high_14 = df["high"].rolling(14).max()
            df["stoch_k"] = 100 * (close - low_14) / (high_14 - low_14)
            df["stoch_d"] = df["stoch_k"].rolling(3).mean()

            # Williams %R
            df["williams_r"] = -100 * (high_14 - close) / (high_14 - low_14)

        # Rate of Change
        df["roc_10"] = (close / close.shift(10) - 1) * 100
        df["roc_21"] = (close / close.shift(21) - 1) * 100

        return df

    @staticmethod
    def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add volume-based indicators.

        Includes OBV, VWAP, volume MA, volume rate.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with volume indicators
        """
        df = df.copy()
        close = df["close"]
        volume = df["volume"]

        # On-Balance Volume (OBV)
        obv = (np.sign(close.diff()) * volume).cumsum()
        df["obv"] = obv

        # Volume Moving Average
        df["volume_ma_20"] = volume.rolling(20).mean()
        df["volume_ratio"] = volume / df["volume_ma_20"]

        # VWAP (simplified - intraday would need high/low/close average)
        if "high" in df.columns and "low" in df.columns:
            typical_price = (df["high"] + df["low"] + close) / 3
            df["vwap_20"] = (
                (typical_price * volume).rolling(20).sum() / volume.rolling(20).sum()
            )

        # Money Flow Index
        if "high" in df.columns and "low" in df.columns:
            typical_price = (df["high"] + df["low"] + close) / 3
            raw_money_flow = typical_price * volume
            money_flow_pos = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
            money_flow_neg = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
            mf_ratio = money_flow_pos.rolling(14).sum() / money_flow_neg.rolling(14).sum()
            df["mfi_14"] = 100 - (100 / (1 + mf_ratio))

        return df

    @staticmethod
    def add_trend_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add trend-following indicators.

        Includes ADX, Bollinger Bands, ATR.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with trend indicators
        """
        df = df.copy()
        close = df["close"]
        high = df.get("high", close)
        low = df.get("low", close)

        # Bollinger Bands
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        df["bb_upper"] = sma_20 + 2 * std_20
        df["bb_lower"] = sma_20 - 2 * std_20
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / sma_20
        df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # Average True Range (ATR)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr_14"] = true_range.rolling(14).mean()
        df["atr_pct"] = df["atr_14"] / close

        # ADX (Average Directional Index)
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        atr_14 = true_range.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr_14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr_14)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df["adx_14"] = dx.rolling(14).mean()

        return df

    @staticmethod
    def add_price_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add price pattern features.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with pattern features
        """
        df = df.copy()
        close = df["close"]
        open_ = df.get("open", close)
        high = df.get("high", close)
        low = df.get("low", close)

        # Candle body and shadow ratios
        body = abs(close - open_)
        range_ = high - low
        df["body_ratio"] = body / range_.replace(0, np.nan)
        df["upper_shadow"] = (high - pd.concat([close, open_], axis=1).max(axis=1)) / range_.replace(0, np.nan)
        df["lower_shadow"] = (pd.concat([close, open_], axis=1).min(axis=1) - low) / range_.replace(0, np.nan)

        # Gap detection
        df["gap_up"] = (low > high.shift(1)).astype(int)
        df["gap_down"] = (high < low.shift(1)).astype(int)

        # Higher highs / lower lows
        df["higher_high"] = (high > high.shift(1)).astype(int)
        df["lower_low"] = (low < low.shift(1)).astype(int)

        # Distance from recent high/low
        df["dist_from_high_20"] = close / high.rolling(20).max() - 1
        df["dist_from_low_20"] = close / low.rolling(20).min() - 1

        return df

    @classmethod
    def add_all_features(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all available features.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with all features
        """
        df = cls.add_returns(df)
        df = cls.add_volatility(df)
        df = cls.add_moving_averages(df)
        df = cls.add_momentum_indicators(df)
        df = cls.add_volume_indicators(df)
        df = cls.add_trend_indicators(df)
        df = cls.add_price_patterns(df)
        return df

    @staticmethod
    def create_labels(
        df: pd.DataFrame,
        horizon: int = 5,
        method: str = "binary",
        threshold: float = 0.0,
        column: str = "close",
    ) -> pd.Series:
        """
        Create labels for supervised learning.

        Args:
            df: OHLCV DataFrame
            horizon: Forward-looking period
            method: Label method - 'binary', 'ternary', 'regression'
            threshold: Threshold for classification (for ternary)
            column: Price column to use

        Returns:
            Series with labels
        """
        # Forward returns
        future_return = df[column].shift(-horizon) / df[column] - 1

        if method == "binary":
            # 1 if positive return, 0 otherwise
            return (future_return > 0).astype(int)

        elif method == "ternary":
            # 1 for up, 0 for neutral, -1 for down
            labels = pd.Series(0, index=df.index)
            labels[future_return > threshold] = 1
            labels[future_return < -threshold] = -1
            return labels

        elif method == "regression":
            # Raw future returns
            return future_return

        else:
            raise ValueError(f"Unknown label method: {method}")

    @staticmethod
    def create_sample_weights(
        df: pd.DataFrame,
        method: str = "time_decay",
        decay_factor: float = 0.999,
    ) -> pd.Series:
        """
        Create sample weights for training.

        Args:
            df: DataFrame with DatetimeIndex
            method: Weighting method - 'time_decay', 'volatility', 'uniform'
            decay_factor: Decay factor for time_decay method

        Returns:
            Series with sample weights
        """
        n = len(df)

        if method == "time_decay":
            # More recent samples get higher weight
            weights = decay_factor ** np.arange(n)[::-1]
            return pd.Series(weights / weights.sum(), index=df.index)

        elif method == "volatility":
            # Weight by inverse volatility
            if "volatility_21d" in df.columns:
                vol = df["volatility_21d"].fillna(df["volatility_21d"].median())
                weights = 1 / vol
                return weights / weights.sum()
            else:
                return pd.Series(1 / n, index=df.index)

        elif method == "uniform":
            return pd.Series(1 / n, index=df.index)

        else:
            raise ValueError(f"Unknown weighting method: {method}")

    @staticmethod
    def add_cross_sectional_features(
        panel: pd.DataFrame,
        column: str = "close",
    ) -> pd.DataFrame:
        """
        Add cross-sectional features (for multi-asset strategies).

        Args:
            panel: Wide DataFrame with assets as columns
            column: Column prefix for features

        Returns:
            Panel with cross-sectional features
        """
        # Returns relative to cross-sectional mean
        cs_mean = panel.mean(axis=1)
        cs_std = panel.std(axis=1)

        result = panel.copy()

        # Z-score relative to cross-section
        for col in panel.columns:
            result[f"{col}_cs_zscore"] = (panel[col] - cs_mean) / cs_std

        # Rank (percentile)
        ranks = panel.rank(axis=1, pct=True)
        for col in panel.columns:
            result[f"{col}_cs_rank"] = ranks[col]

        return result
