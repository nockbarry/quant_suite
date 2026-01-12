"""
Enhanced Technical Features

Advanced technical features for ML models that go beyond standard indicators:
- Multi-timeframe momentum alignment
- Divergence detection
- Volatility regime features
- Cross-asset sensitivity (rates, dollar, VIX)
- Volume-price confirmation signals

These features encode market intuitions about how different signals interact.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .feature_registry import (
    FeatureCategory,
    FeatureDefinition,
    DataSource,
    register_feature,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MULTI-TIMEFRAME FEATURES
# =============================================================================


def compute_momentum_alignment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute momentum alignment across multiple timeframes.

    When short, medium, and long-term momentum all align, the trend is stronger.
    This encodes the intuition that confirmed trends are more reliable.

    Returns:
        momentum_alignment_score: -1 to +1, how aligned are the timeframes
        momentum_alignment_count: 0-4, how many timeframes agree on direction
        momentum_acceleration: Is short-term momentum stronger than long-term?
    """
    result = pd.DataFrame(index=df.index)

    close = df["close"]

    # Compute momentum over different periods
    periods = [5, 10, 20, 50]
    momentums = {}
    for p in periods:
        momentums[p] = close.pct_change(p)

    # Alignment score: average sign of all momentums (-1 to +1)
    signs = pd.DataFrame({
        f"sign_{p}": np.sign(momentums[p])
        for p in periods
    })
    result["momentum_alignment_score"] = signs.mean(axis=1)

    # Alignment count: how many agree on direction
    # All positive or all negative = 4, mixed = lower
    result["momentum_alignment_count"] = signs.apply(
        lambda row: max(
            (row > 0).sum(),
            (row < 0).sum()
        ),
        axis=1
    )

    # Acceleration: short-term vs long-term momentum magnitude
    # Positive = accelerating in current direction
    result["momentum_acceleration"] = (
        momentums[5].abs() / (momentums[50].abs() + 1e-10)
    ).clip(-10, 10)

    # Momentum coherence: are all timeframes trending consistently?
    result["momentum_coherence"] = (
        (result["momentum_alignment_count"] >= 3).astype(float) *
        result["momentum_alignment_score"]
    )

    return result


def compute_momentum_divergence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect divergences between price momentum and technical indicators.

    Divergences often precede reversals:
    - Bearish divergence: price makes higher high, RSI makes lower high
    - Bullish divergence: price makes lower low, RSI makes higher low

    Returns:
        rsi_price_divergence: RSI divergence signal (-1 bearish to +1 bullish)
        macd_price_divergence: MACD histogram divergence signal
        volume_price_divergence: Volume not confirming price moves
    """
    result = pd.DataFrame(index=df.index)

    close = df["close"]
    volume = df["volume"]

    # Compute RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Compute MACD histogram
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # Rolling window for detecting divergence
    window = 20

    # Price highs and lows
    price_high = close.rolling(window).max()
    price_low = close.rolling(window).min()

    # RSI at price extremes
    rsi_high = rsi.rolling(window).max()
    rsi_low = rsi.rolling(window).min()

    # Bearish divergence: price near high, RSI declining
    # Bullish divergence: price near low, RSI rising
    price_near_high = (close >= price_high * 0.98)
    price_near_low = (close <= price_low * 1.02)

    rsi_declining = rsi < rsi.shift(5)
    rsi_rising = rsi > rsi.shift(5)

    # RSI-price divergence score
    result["rsi_price_divergence"] = (
        price_near_low.astype(float) * rsi_rising.astype(float) -
        price_near_high.astype(float) * rsi_declining.astype(float)
    )

    # MACD divergence
    macd_high = macd_hist.rolling(window).max()
    macd_low = macd_hist.rolling(window).min()
    macd_declining = macd_hist < macd_high * 0.5
    macd_rising = macd_hist > macd_low * 0.5

    result["macd_price_divergence"] = (
        price_near_low.astype(float) * macd_rising.astype(float) -
        price_near_high.astype(float) * macd_declining.astype(float)
    )

    # Volume-price divergence
    # Strong moves should be confirmed by volume
    vol_sma = volume.rolling(20).mean()
    vol_relative = volume / vol_sma
    price_move = close.pct_change(5).abs()

    # Divergence when large price move but low volume
    result["volume_price_divergence"] = (
        (price_move > price_move.rolling(60).quantile(0.8)) &
        (vol_relative < 0.8)
    ).astype(float) * -1  # Negative = not confirmed

    # Combined divergence signal
    result["divergence_composite"] = (
        result["rsi_price_divergence"] +
        result["macd_price_divergence"] +
        result["volume_price_divergence"]
    ) / 3

    return result


# =============================================================================
# VOLATILITY REGIME FEATURES
# =============================================================================


def compute_volatility_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute volatility regime features.

    Different strategies work in different volatility regimes:
    - Low vol: Mean reversion tends to work
    - High vol: Momentum and breakouts work better

    Returns:
        vol_regime: 0=low, 1=normal, 2=high, 3=crisis
        vol_regime_duration: Days in current regime
        vol_regime_change: Did regime change recently?
        vol_percentile: Current vol vs historical
    """
    result = pd.DataFrame(index=df.index)

    # Compute realized volatility
    returns = df["close"].pct_change()
    vol_20d = returns.rolling(20).std() * np.sqrt(252)

    # Volatility percentile over 252 days
    result["vol_percentile"] = vol_20d.rolling(252).rank(pct=True)

    # Define regimes based on percentile
    # Low: 0-25%, Normal: 25-75%, High: 75-90%, Crisis: 90%+
    def classify_regime(pct):
        if pd.isna(pct):
            return np.nan
        if pct < 0.25:
            return 0  # Low
        elif pct < 0.75:
            return 1  # Normal
        elif pct < 0.90:
            return 2  # High
        else:
            return 3  # Crisis

    result["vol_regime"] = result["vol_percentile"].apply(classify_regime)

    # Regime duration: days in current regime
    regime_changes = result["vol_regime"] != result["vol_regime"].shift(1)
    regime_group = regime_changes.cumsum()
    result["vol_regime_duration"] = regime_group.groupby(regime_group).cumcount() + 1

    # Recent regime change (within 5 days)
    result["vol_regime_change"] = regime_changes.rolling(5).sum().fillna(0)

    # Volatility expansion/contraction
    vol_5d = returns.rolling(5).std() * np.sqrt(252)
    vol_60d = returns.rolling(60).std() * np.sqrt(252)
    result["vol_expansion"] = vol_5d / (vol_60d + 1e-10) - 1

    # Volatility mean reversion signal
    # High vol tends to mean-revert
    result["vol_mean_reversion_signal"] = (
        (result["vol_percentile"] > 0.9).astype(float) * -1 +
        (result["vol_percentile"] < 0.1).astype(float) * 1
    )

    return result


def compute_volatility_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect volatility breakouts (Bollinger squeeze + expansion).

    When Bollinger Bands get tight (low volatility), a breakout is likely.
    This encodes the intuition that volatility clusters and expands after compression.

    Returns:
        bb_squeeze: Is volatility compressed?
        bb_squeeze_duration: Days of compression
        vol_breakout_signal: Direction of potential breakout
    """
    result = pd.DataFrame(index=df.index)

    close = df["close"]
    volume = df["volume"]

    # Bollinger Band width
    ma_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    bb_upper = ma_20 + 2 * std_20
    bb_lower = ma_20 - 2 * std_20
    bb_width = (bb_upper - bb_lower) / ma_20

    # Percentile of BB width (low = squeeze)
    bb_width_pct = bb_width.rolling(100).rank(pct=True)

    # Squeeze when width is in bottom 20%
    result["bb_squeeze"] = (bb_width_pct < 0.2).astype(float)

    # Squeeze duration
    squeeze_starts = (result["bb_squeeze"] == 1) & (result["bb_squeeze"].shift(1) != 1)
    squeeze_groups = squeeze_starts.cumsum()
    in_squeeze = result["bb_squeeze"] == 1
    result["bb_squeeze_duration"] = in_squeeze.groupby(squeeze_groups).cumsum()

    # Keltner Channel for squeeze detection (alternative method)
    # Squeeze confirmed when BB inside Keltner
    high, low = df["high"], df["low"]
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr_20 = tr.rolling(20).mean()
    kc_upper = ma_20 + 1.5 * atr_20
    kc_lower = ma_20 - 1.5 * atr_20

    result["keltner_squeeze"] = (
        (bb_upper < kc_upper) & (bb_lower > kc_lower)
    ).astype(float)

    # Breakout direction prediction
    # Use momentum during squeeze to predict direction
    mom_10 = close.pct_change(10)
    result["vol_breakout_signal"] = (
        result["bb_squeeze"] * np.sign(mom_10)
    )

    # Volume confirmation of squeeze
    vol_sma = volume.rolling(20).mean()
    vol_low = volume < vol_sma * 0.7
    result["vol_squeeze_confirmed"] = (
        result["bb_squeeze"] * vol_low.astype(float)
    )

    return result


# =============================================================================
# CROSS-ASSET SENSITIVITY FEATURES
# =============================================================================


def compute_cross_asset_sensitivity(
    df: pd.DataFrame,
    rates_data: Optional[pd.DataFrame] = None,
    dollar_data: Optional[pd.DataFrame] = None,
    vix_data: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute sensitivity to macro factors.

    Different stocks have different sensitivities:
    - Banks are rate-sensitive
    - Exporters are dollar-sensitive
    - Growth stocks are VIX-sensitive

    Returns:
        rates_beta: Rolling beta to 10Y yield changes
        dollar_beta: Rolling beta to DXY changes
        vix_beta: Rolling beta to VIX changes
    """
    result = pd.DataFrame(index=df.index)

    stock_returns = df["close"].pct_change()
    window = 60  # Rolling window for beta calculation

    def compute_rolling_beta(stock_rets: pd.Series, factor_rets: pd.Series) -> pd.Series:
        """Compute rolling beta between stock and factor returns."""
        # Align the series
        aligned = pd.concat([stock_rets, factor_rets], axis=1).dropna()
        if len(aligned) < window:
            return pd.Series(index=stock_rets.index, dtype=float)

        # Rolling covariance and variance
        cov = stock_rets.rolling(window).cov(factor_rets)
        var = factor_rets.rolling(window).var()

        return cov / (var + 1e-10)

    # Rates sensitivity
    if rates_data is not None and "close" in rates_data.columns:
        rates_changes = rates_data["close"].pct_change()
        # Align dates
        rates_changes = rates_changes.reindex(df.index)
        result["rates_beta"] = compute_rolling_beta(stock_returns, rates_changes)
        result["rates_beta_abs"] = result["rates_beta"].abs()
    else:
        result["rates_beta"] = np.nan
        result["rates_beta_abs"] = np.nan

    # Dollar sensitivity
    if dollar_data is not None and "close" in dollar_data.columns:
        dollar_changes = dollar_data["close"].pct_change()
        dollar_changes = dollar_changes.reindex(df.index)
        result["dollar_beta"] = compute_rolling_beta(stock_returns, dollar_changes)
        result["dollar_beta_abs"] = result["dollar_beta"].abs()
    else:
        result["dollar_beta"] = np.nan
        result["dollar_beta_abs"] = np.nan

    # VIX sensitivity
    if vix_data is not None and "close" in vix_data.columns:
        vix_changes = vix_data["close"].pct_change()
        vix_changes = vix_changes.reindex(df.index)
        result["vix_beta"] = compute_rolling_beta(stock_returns, vix_changes)
        result["vix_beta_abs"] = result["vix_beta"].abs()

        # VIX regime signal
        # When VIX is high and rising, stocks with negative VIX beta suffer
        vix_high = vix_data["close"] > vix_data["close"].rolling(252).quantile(0.8)
        vix_high = vix_high.reindex(df.index)
        result["vix_regime_risk"] = vix_high.astype(float) * result["vix_beta"].abs()
    else:
        result["vix_beta"] = np.nan
        result["vix_beta_abs"] = np.nan
        result["vix_regime_risk"] = np.nan

    return result


def compute_sector_correlation(
    df: pd.DataFrame,
    sector_etf_data: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute correlation with sector ETF.

    High sector correlation = more systematic risk
    Low sector correlation = more idiosyncratic, harder to hedge

    Returns:
        sector_correlation: Rolling correlation with sector ETF
        relative_strength_vs_sector: Outperformance vs sector
    """
    result = pd.DataFrame(index=df.index)

    stock_returns = df["close"].pct_change()
    window = 60

    if sector_etf_data is not None and "close" in sector_etf_data.columns:
        sector_returns = sector_etf_data["close"].pct_change()
        sector_returns = sector_returns.reindex(df.index)

        # Rolling correlation
        result["sector_correlation"] = stock_returns.rolling(window).corr(sector_returns)

        # Relative strength vs sector
        cumulative_stock = (1 + stock_returns).rolling(20).apply(np.prod, raw=True) - 1
        cumulative_sector = (1 + sector_returns).rolling(20).apply(np.prod, raw=True) - 1
        result["relative_strength_vs_sector"] = cumulative_stock - cumulative_sector

        # Decoupling signal
        # When stock decouples from sector (low corr), it may be signaling something
        result["sector_decoupling"] = (
            result["sector_correlation"] < result["sector_correlation"].rolling(252).quantile(0.2)
        ).astype(float)
    else:
        result["sector_correlation"] = np.nan
        result["relative_strength_vs_sector"] = np.nan
        result["sector_decoupling"] = np.nan

    return result


# =============================================================================
# CONFIRMATION FEATURES
# =============================================================================


def compute_signal_confirmation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute signal confirmation features.

    Strong signals are confirmed by multiple indicators.
    This encodes the intuition that confluence is important.

    Returns:
        bullish_signal_count: How many bullish signals are active
        bearish_signal_count: How many bearish signals are active
        signal_clarity: Difference between bullish and bearish
    """
    result = pd.DataFrame(index=df.index)

    close = df["close"]
    volume = df["volume"]

    # Compute various signals
    signals = pd.DataFrame(index=df.index)

    # 1. Price above/below moving averages
    signals["above_sma_20"] = (close > close.rolling(20).mean()).astype(int)
    signals["above_sma_50"] = (close > close.rolling(50).mean()).astype(int)
    signals["above_sma_200"] = (close > close.rolling(200).mean()).astype(int)

    # 2. RSI signals
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    signals["rsi_bullish"] = (rsi > 50).astype(int)
    signals["rsi_oversold"] = (rsi < 30).astype(int)  # Potential reversal
    signals["rsi_overbought"] = (rsi > 70).astype(int)  # Potential reversal

    # 3. MACD signals
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    signals["macd_bullish"] = (macd_line > macd_signal).astype(int)

    # 4. Momentum signals
    signals["momentum_positive"] = (close.pct_change(10) > 0).astype(int)
    signals["momentum_strong"] = (close.pct_change(10) > 0.05).astype(int)

    # 5. Volume confirmation
    vol_sma = volume.rolling(20).mean()
    signals["volume_above_avg"] = (volume > vol_sma).astype(int)

    # Bullish signal count (positive signals)
    bullish_cols = [
        "above_sma_20", "above_sma_50", "above_sma_200",
        "rsi_bullish", "macd_bullish", "momentum_positive"
    ]
    result["bullish_signal_count"] = signals[bullish_cols].sum(axis=1)

    # Bearish signal count (inverse of positive signals)
    result["bearish_signal_count"] = len(bullish_cols) - result["bullish_signal_count"]

    # Signal clarity: net bullish - bearish
    result["signal_clarity"] = (
        result["bullish_signal_count"] - result["bearish_signal_count"]
    )

    # Extreme readings
    result["extreme_bullish"] = (result["bullish_signal_count"] >= 5).astype(float)
    result["extreme_bearish"] = (result["bearish_signal_count"] >= 5).astype(float)

    # Conflicting signals
    result["signal_conflict"] = (
        (result["bullish_signal_count"] >= 3) &
        (result["bearish_signal_count"] >= 3)
    ).astype(float)

    return result


# =============================================================================
# REGISTER ENHANCED FEATURES
# =============================================================================


# Momentum alignment
register_feature(FeatureDefinition(
    name="momentum_alignment",
    description="Multi-timeframe momentum alignment (5/10/20/50 periods)",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_momentum_alignment,
    output_columns=[
        "momentum_alignment_score", "momentum_alignment_count",
        "momentum_acceleration", "momentum_coherence"
    ],
    lookback_days=60,
))

# Momentum divergence
register_feature(FeatureDefinition(
    name="momentum_divergence",
    description="RSI/MACD/Volume divergences from price",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.VOLUME_YAHOO],
    compute_fn=compute_momentum_divergence,
    output_columns=[
        "rsi_price_divergence", "macd_price_divergence",
        "volume_price_divergence", "divergence_composite"
    ],
    lookback_days=60,
))

# Volatility regime
register_feature(FeatureDefinition(
    name="volatility_regime_enhanced",
    description="Volatility regime classification with duration and signals",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_volatility_regime_features,
    output_columns=[
        "vol_regime", "vol_regime_duration", "vol_regime_change",
        "vol_percentile", "vol_expansion", "vol_mean_reversion_signal"
    ],
    lookback_days=252,
))

# Volatility breakout
register_feature(FeatureDefinition(
    name="volatility_breakout",
    description="Bollinger squeeze and breakout detection",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.VOLUME_YAHOO],
    compute_fn=compute_volatility_breakout,
    output_columns=[
        "bb_squeeze", "bb_squeeze_duration", "keltner_squeeze",
        "vol_breakout_signal", "vol_squeeze_confirmed"
    ],
    lookback_days=100,
))

# Signal confirmation
register_feature(FeatureDefinition(
    name="signal_confirmation",
    description="Multi-indicator signal confluence detection",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.VOLUME_YAHOO],
    compute_fn=compute_signal_confirmation,
    output_columns=[
        "bullish_signal_count", "bearish_signal_count", "signal_clarity",
        "extreme_bullish", "extreme_bearish", "signal_conflict"
    ],
    lookback_days=200,
))

# Note: Cross-asset sensitivity and sector correlation require external data
# They are registered as placeholders and computed separately when data is available

register_feature(FeatureDefinition(
    name="cross_asset_sensitivity",
    description="Sensitivity to rates, dollar, VIX (requires macro data)",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.FRED_ECONOMIC],
    compute_fn=None,  # Computed separately with macro data
    output_columns=[
        "rates_beta", "dollar_beta", "vix_beta",
        "rates_beta_abs", "dollar_beta_abs", "vix_beta_abs", "vix_regime_risk"
    ],
    lookback_days=60,
))


# =============================================================================
# HELPER CLASS
# =============================================================================


class EnhancedTechnicalFeatures:
    """
    Compute enhanced technical features.

    Usage:
        etf = EnhancedTechnicalFeatures()
        features = etf.compute_all(df)

        # With macro data
        features = etf.compute_all(
            df,
            rates_data=rates_df,
            dollar_data=dollar_df,
            vix_data=vix_df,
        )
    """

    def __init__(self):
        self.feature_functions = {
            "momentum_alignment": compute_momentum_alignment,
            "momentum_divergence": compute_momentum_divergence,
            "volatility_regime": compute_volatility_regime_features,
            "volatility_breakout": compute_volatility_breakout,
            "signal_confirmation": compute_signal_confirmation,
        }

    def compute_all(
        self,
        df: pd.DataFrame,
        rates_data: Optional[pd.DataFrame] = None,
        dollar_data: Optional[pd.DataFrame] = None,
        vix_data: Optional[pd.DataFrame] = None,
        sector_etf_data: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Compute all enhanced technical features.

        Args:
            df: OHLCV DataFrame
            rates_data: Optional 10Y yield data
            dollar_data: Optional DXY data
            vix_data: Optional VIX data
            sector_etf_data: Optional sector ETF data

        Returns:
            DataFrame with all enhanced features
        """
        result = pd.DataFrame(index=df.index)

        # Compute standard enhanced features
        for name, func in self.feature_functions.items():
            try:
                features = func(df)
                result = pd.concat([result, features], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute {name}: {e}")

        # Compute cross-asset sensitivity if data available
        if any([rates_data is not None, dollar_data is not None, vix_data is not None]):
            try:
                sensitivity = compute_cross_asset_sensitivity(
                    df, rates_data, dollar_data, vix_data
                )
                result = pd.concat([result, sensitivity], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute cross_asset_sensitivity: {e}")

        # Compute sector correlation if data available
        if sector_etf_data is not None:
            try:
                sector_corr = compute_sector_correlation(df, sector_etf_data)
                result = pd.concat([result, sector_corr], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute sector_correlation: {e}")

        return result

    def compute_single(
        self,
        feature_name: str,
        df: pd.DataFrame,
        **kwargs,
    ) -> pd.DataFrame:
        """Compute a single enhanced feature."""
        if feature_name in self.feature_functions:
            return self.feature_functions[feature_name](df)
        elif feature_name == "cross_asset_sensitivity":
            return compute_cross_asset_sensitivity(df, **kwargs)
        elif feature_name == "sector_correlation":
            return compute_sector_correlation(df, **kwargs)
        else:
            raise ValueError(f"Unknown feature: {feature_name}")

    @staticmethod
    def get_feature_list() -> list[str]:
        """Get list of all enhanced feature names."""
        return [
            "momentum_alignment",
            "momentum_divergence",
            "volatility_regime",
            "volatility_breakout",
            "signal_confirmation",
            "cross_asset_sensitivity",
            "sector_correlation",
        ]
