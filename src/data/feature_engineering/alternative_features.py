"""
Alternative Data Features

Features derived from non-price data sources:
- Congressional trading patterns
- Insider trading clusters
- Options flow signals
- Sentiment indicators (AAII, newsletters, social)
- Event calendars (earnings, economic, FDA)

These features encode information advantages from alternative data.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

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
# CONGRESSIONAL TRADING FEATURES
# =============================================================================


@dataclass
class CongressionalSignal:
    """Computed signal from congressional trading data."""
    symbol: str
    cluster_intensity: float  # Number of buys in window
    cluster_delay: int  # Days since cluster started
    notable_trader_count: int  # Notable traders involved
    party_divergence: float  # R vs D direction difference
    committee_relevance: float  # How relevant are their committees
    signal_strength: float  # Overall signal strength


def compute_congressional_features(
    trades_df: pd.DataFrame,
    symbol: str,
    lookback_days: int = 30,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute congressional trading features for a symbol.

    Args:
        trades_df: DataFrame with columns [symbol, transaction_date, trade_type,
                   politician, chamber, amount_estimate, is_notable_trader, committees]
        symbol: Symbol to compute features for
        lookback_days: Days to look back for clustering
        reference_date: Date to compute features as of (default: today)

    Returns:
        DataFrame with congressional features indexed by date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # Filter to symbol
    symbol_trades = trades_df[trades_df["symbol"] == symbol].copy()

    if len(symbol_trades) == 0:
        return _empty_congressional_features(reference_date)

    # Ensure datetime index
    symbol_trades["transaction_date"] = pd.to_datetime(symbol_trades["transaction_date"])
    symbol_trades = symbol_trades.sort_values("transaction_date")

    # Create daily index
    date_range = pd.date_range(
        start=symbol_trades["transaction_date"].min(),
        end=reference_date,
        freq="D"
    )
    result = pd.DataFrame(index=date_range)

    # Aggregate trades by day
    daily_trades = symbol_trades.groupby(
        symbol_trades["transaction_date"].dt.date
    ).agg({
        "amount_estimate": "sum",
        "is_notable_trader": "sum",
        "politician": "nunique",
        "trade_type": lambda x: (x == "purchase").sum() - (x == "sale").sum(),
    }).rename(columns={
        "amount_estimate": "daily_amount",
        "is_notable_trader": "notable_count",
        "politician": "unique_traders",
        "trade_type": "net_direction",
    })

    # Reindex to full date range
    daily_trades.index = pd.to_datetime(daily_trades.index)
    daily_trades = daily_trades.reindex(date_range).fillna(0)

    # Feature 1: Cluster intensity (rolling sum of trades)
    result["congress_cluster_intensity"] = daily_trades["unique_traders"].rolling(
        lookback_days, min_periods=1
    ).sum()

    # Feature 2: Cluster delay (days since cluster started)
    # A cluster starts when we have 2+ traders in 10 days
    cluster_active = result["congress_cluster_intensity"] >= 2
    cluster_starts = cluster_active & ~cluster_active.shift(1).fillna(False)
    cluster_groups = cluster_starts.cumsum()
    result["congress_cluster_delay"] = cluster_groups.groupby(cluster_groups).cumcount()
    result.loc[~cluster_active, "congress_cluster_delay"] = 0

    # Feature 3: Notable trader involvement
    result["congress_notable_count"] = daily_trades["notable_count"].rolling(
        lookback_days, min_periods=1
    ).sum()

    # Feature 4: Amount weighted signal
    result["congress_amount_signal"] = daily_trades["daily_amount"].rolling(
        lookback_days, min_periods=1
    ).sum()

    # Normalize amount to a signal
    result["congress_amount_signal"] = (
        result["congress_amount_signal"] /
        result["congress_amount_signal"].rolling(252, min_periods=20).max()
    ).clip(0, 1)

    # Feature 5: Net direction (buys - sells)
    result["congress_net_direction"] = daily_trades["net_direction"].rolling(
        lookback_days, min_periods=1
    ).sum()

    # Feature 6: Composite signal
    result["congress_composite_signal"] = (
        (result["congress_cluster_intensity"] > 0).astype(float) * 0.3 +
        (result["congress_notable_count"] > 0).astype(float) * 0.3 +
        result["congress_amount_signal"] * 0.2 +
        (result["congress_net_direction"] > 0).astype(float) * 0.2
    )

    return result


def _empty_congressional_features(reference_date: datetime) -> pd.DataFrame:
    """Return empty congressional features DataFrame."""
    return pd.DataFrame({
        "congress_cluster_intensity": [0.0],
        "congress_cluster_delay": [0],
        "congress_notable_count": [0],
        "congress_amount_signal": [0.0],
        "congress_net_direction": [0],
        "congress_composite_signal": [0.0],
    }, index=[reference_date])


# =============================================================================
# INSIDER TRADING FEATURES
# =============================================================================


def compute_insider_features(
    insider_df: pd.DataFrame,
    symbol: str,
    lookback_days: int = 90,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute insider trading features for a symbol.

    Args:
        insider_df: DataFrame with columns [symbol, transaction_date, transaction_type,
                    insider_role, value, shares, is_purchase]
        symbol: Symbol to compute features for
        lookback_days: Days to look back
        reference_date: Date to compute features as of

    Returns:
        DataFrame with insider features indexed by date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # Filter to symbol
    symbol_insiders = insider_df[insider_df["symbol"] == symbol].copy()

    if len(symbol_insiders) == 0:
        return _empty_insider_features(reference_date)

    # Ensure datetime index
    symbol_insiders["transaction_date"] = pd.to_datetime(symbol_insiders["transaction_date"])
    symbol_insiders = symbol_insiders.sort_values("transaction_date")

    # Create daily index
    date_range = pd.date_range(
        start=symbol_insiders["transaction_date"].min(),
        end=reference_date,
        freq="D"
    )
    result = pd.DataFrame(index=date_range)

    # Separate buys and sells
    buys = symbol_insiders[symbol_insiders.get("is_purchase", False) == True]
    sells = symbol_insiders[symbol_insiders.get("is_purchase", False) == False]

    # Aggregate by day
    daily_buys = buys.groupby(
        buys["transaction_date"].dt.date
    ).agg({
        "value": "sum",
        "insider_role": "nunique",
    }).rename(columns={"value": "buy_value", "insider_role": "buy_count"})

    daily_sells = sells.groupby(
        sells["transaction_date"].dt.date
    ).agg({
        "value": "sum",
        "insider_role": "nunique",
    }).rename(columns={"value": "sell_value", "insider_role": "sell_count"})

    # Combine and reindex
    daily_trades = pd.concat([daily_buys, daily_sells], axis=1).fillna(0)
    daily_trades.index = pd.to_datetime(daily_trades.index)
    daily_trades = daily_trades.reindex(date_range).fillna(0)

    # Feature 1: Cluster buy signal
    result["insider_cluster_buy_count"] = daily_trades.get("buy_count", 0).rolling(
        lookback_days, min_periods=1
    ).sum()

    # Feature 2: Net insider activity (buy value - sell value)
    net_value = daily_trades.get("buy_value", 0) - daily_trades.get("sell_value", 0)
    result["insider_net_value"] = net_value.rolling(lookback_days, min_periods=1).sum()

    # Feature 3: Buy ratio
    buy_value = daily_trades.get("buy_value", 0).rolling(lookback_days, min_periods=1).sum()
    sell_value = daily_trades.get("sell_value", 0).rolling(lookback_days, min_periods=1).sum()
    total_value = buy_value + sell_value
    result["insider_buy_ratio"] = np.where(
        total_value > 0,
        buy_value / total_value,
        0.5
    )

    # Feature 4: Cluster signal (multiple insiders buying in short window)
    short_window = 10
    result["insider_cluster_signal"] = (
        daily_trades.get("buy_count", 0).rolling(short_window, min_periods=1).sum() >= 2
    ).astype(float)

    # Feature 5: Executive vs director
    # Placeholder - would need role-specific aggregation
    result["insider_executive_signal"] = result["insider_cluster_signal"]  # Placeholder

    # Feature 6: Composite signal
    result["insider_composite_signal"] = (
        result["insider_cluster_signal"] * 0.4 +
        (result["insider_buy_ratio"] - 0.5) * 2 * 0.4 +  # Scale to -0.4 to 0.4
        (result["insider_net_value"] > 0).astype(float) * 0.2
    ).clip(-1, 1)

    return result


def _empty_insider_features(reference_date: datetime) -> pd.DataFrame:
    """Return empty insider features DataFrame."""
    return pd.DataFrame({
        "insider_cluster_buy_count": [0.0],
        "insider_net_value": [0.0],
        "insider_buy_ratio": [0.5],
        "insider_cluster_signal": [0.0],
        "insider_executive_signal": [0.0],
        "insider_composite_signal": [0.0],
    }, index=[reference_date])


# =============================================================================
# OPTIONS FLOW FEATURES
# =============================================================================


def compute_options_flow_features(
    options_df: pd.DataFrame,
    symbol: str,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute options flow features for a symbol.

    Args:
        options_df: DataFrame with columns [symbol, date, volume, open_interest,
                    option_type, strike, implied_volatility, ...]
        symbol: Symbol to compute features for
        reference_date: Date to compute features as of

    Returns:
        DataFrame with options features indexed by date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # Filter to symbol
    symbol_options = options_df[options_df["symbol"] == symbol].copy()

    if len(symbol_options) == 0:
        return _empty_options_features(reference_date)

    # Ensure datetime index
    if "date" in symbol_options.columns:
        symbol_options["date"] = pd.to_datetime(symbol_options["date"])
    else:
        symbol_options["date"] = pd.to_datetime(reference_date)

    # Create daily index
    date_range = pd.date_range(
        start=symbol_options["date"].min(),
        end=reference_date,
        freq="D"
    )
    result = pd.DataFrame(index=date_range)

    # Separate calls and puts
    calls = symbol_options[symbol_options["option_type"] == "call"]
    puts = symbol_options[symbol_options["option_type"] == "put"]

    # Aggregate by day
    daily_calls = calls.groupby(calls["date"].dt.date).agg({
        "volume": "sum",
        "open_interest": "sum",
    }).rename(columns={"volume": "call_volume", "open_interest": "call_oi"})

    daily_puts = puts.groupby(puts["date"].dt.date).agg({
        "volume": "sum",
        "open_interest": "sum",
    }).rename(columns={"volume": "put_volume", "open_interest": "put_oi"})

    # Combine
    daily_options = pd.concat([daily_calls, daily_puts], axis=1).fillna(0)
    daily_options.index = pd.to_datetime(daily_options.index)
    daily_options = daily_options.reindex(date_range).fillna(method="ffill")

    # Feature 1: Put/Call ratio (volume)
    total_volume = daily_options.get("call_volume", 0) + daily_options.get("put_volume", 0)
    result["put_call_ratio_volume"] = np.where(
        daily_options.get("call_volume", 0) > 0,
        daily_options.get("put_volume", 0) / daily_options.get("call_volume", 0),
        1.0
    )

    # Feature 2: Put/Call ratio (open interest)
    result["put_call_ratio_oi"] = np.where(
        daily_options.get("call_oi", 0) > 0,
        daily_options.get("put_oi", 0) / daily_options.get("call_oi", 0),
        1.0
    )

    # Feature 3: Unusual volume (vs 20-day average)
    avg_volume = total_volume.rolling(20, min_periods=1).mean()
    result["unusual_options_volume"] = np.where(
        avg_volume > 0,
        total_volume / avg_volume,
        1.0
    )

    # Feature 4: Call volume surge (bullish)
    avg_call_volume = daily_options.get("call_volume", 0).rolling(20, min_periods=1).mean()
    result["call_volume_surge"] = np.where(
        avg_call_volume > 0,
        daily_options.get("call_volume", 0) / avg_call_volume,
        1.0
    )

    # Feature 5: Put/Call sentiment (normalized)
    # <1 = bullish (more calls), >1 = bearish (more puts)
    result["options_sentiment"] = 1 - (result["put_call_ratio_volume"].clip(0, 2) / 2)

    # Feature 6: Unusual call activity signal
    result["unusual_call_signal"] = (
        (result["call_volume_surge"] > 2) &
        (result["put_call_ratio_volume"] < 0.7)
    ).astype(float)

    return result


def _empty_options_features(reference_date: datetime) -> pd.DataFrame:
    """Return empty options features DataFrame."""
    return pd.DataFrame({
        "put_call_ratio_volume": [1.0],
        "put_call_ratio_oi": [1.0],
        "unusual_options_volume": [1.0],
        "call_volume_surge": [1.0],
        "options_sentiment": [0.5],
        "unusual_call_signal": [0.0],
    }, index=[reference_date])


# =============================================================================
# SENTIMENT FEATURES
# =============================================================================


def compute_sentiment_features(
    aaii_df: Optional[pd.DataFrame] = None,
    newsletter_df: Optional[pd.DataFrame] = None,
    social_df: Optional[pd.DataFrame] = None,
    symbol: Optional[str] = None,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute sentiment features from various sources.

    Args:
        aaii_df: AAII sentiment survey data [date, bullish, bearish, neutral]
        newsletter_df: Newsletter sentiment data
        social_df: Social media sentiment for symbol
        symbol: Symbol for symbol-specific sentiment
        reference_date: Date to compute features as of

    Returns:
        DataFrame with sentiment features indexed by date
    """
    if reference_date is None:
        reference_date = datetime.now()

    result_index = pd.DatetimeIndex([reference_date])
    result = pd.DataFrame(index=result_index)

    # AAII Sentiment Features
    if aaii_df is not None and len(aaii_df) > 0:
        aaii_df = aaii_df.copy()
        aaii_df["date"] = pd.to_datetime(aaii_df["date"])
        aaii_df = aaii_df.sort_values("date")

        # Get latest reading
        latest_aaii = aaii_df.iloc[-1]

        # Bull-bear spread
        result["aaii_bull_bear_spread"] = latest_aaii.get("bullish", 0) - latest_aaii.get("bearish", 0)

        # Extreme readings (contrarian)
        bull_pct = latest_aaii.get("bullish", 0)
        bear_pct = latest_aaii.get("bearish", 0)

        # Historical percentiles
        bull_pct_rank = (aaii_df["bullish"] < bull_pct).mean()
        bear_pct_rank = (aaii_df["bearish"] < bear_pct).mean()

        result["aaii_extreme_bullish"] = (bull_pct_rank > 0.9).astype(float)
        result["aaii_extreme_bearish"] = (bear_pct_rank > 0.9).astype(float)

        # Contrarian signal (buy when bearish, sell when bullish)
        result["aaii_contrarian_signal"] = (
            result["aaii_extreme_bearish"].astype(float) -
            result["aaii_extreme_bullish"].astype(float)
        )

    else:
        result["aaii_bull_bear_spread"] = np.nan
        result["aaii_extreme_bullish"] = np.nan
        result["aaii_extreme_bearish"] = np.nan
        result["aaii_contrarian_signal"] = np.nan

    # Newsletter Sentiment Features
    if newsletter_df is not None and len(newsletter_df) > 0:
        newsletter_df = newsletter_df.copy()
        newsletter_df["date"] = pd.to_datetime(newsletter_df["date"])
        latest_newsletter = newsletter_df.iloc[-1]

        result["newsletter_bullish_pct"] = latest_newsletter.get("bullish_pct", 0.5)
        result["newsletter_bearish_pct"] = latest_newsletter.get("bearish_pct", 0.5)

        # Contrarian signal
        result["newsletter_contrarian_signal"] = (
            (result["newsletter_bearish_pct"] > 0.6).astype(float) -
            (result["newsletter_bullish_pct"] > 0.6).astype(float)
        )
    else:
        result["newsletter_bullish_pct"] = np.nan
        result["newsletter_bearish_pct"] = np.nan
        result["newsletter_contrarian_signal"] = np.nan

    # Social Sentiment Features (symbol-specific)
    if social_df is not None and symbol and len(social_df) > 0:
        symbol_social = social_df[social_df.get("symbol", "") == symbol]

        if len(symbol_social) > 0:
            latest = symbol_social.iloc[-1]
            result["social_sentiment_score"] = latest.get("sentiment", 0)
            result["social_volume"] = latest.get("volume", 0)
            result["social_sentiment_extreme"] = (
                abs(latest.get("sentiment", 0)) > 0.5
            )
        else:
            result["social_sentiment_score"] = np.nan
            result["social_volume"] = np.nan
            result["social_sentiment_extreme"] = np.nan
    else:
        result["social_sentiment_score"] = np.nan
        result["social_volume"] = np.nan
        result["social_sentiment_extreme"] = np.nan

    return result


# =============================================================================
# EVENT CALENDAR FEATURES
# =============================================================================


def compute_event_features(
    earnings_df: Optional[pd.DataFrame] = None,
    economic_df: Optional[pd.DataFrame] = None,
    fda_df: Optional[pd.DataFrame] = None,
    symbol: Optional[str] = None,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute event calendar features.

    Args:
        earnings_df: Earnings calendar [symbol, date, time, estimate]
        economic_df: Economic calendar [date, event, importance]
        fda_df: FDA calendar [symbol, date, event_type]
        symbol: Symbol for symbol-specific events
        reference_date: Date to compute features as of

    Returns:
        DataFrame with event features indexed by date
    """
    if reference_date is None:
        reference_date = datetime.now()

    result_index = pd.DatetimeIndex([reference_date])
    result = pd.DataFrame(index=result_index)

    # Earnings Features
    if earnings_df is not None and symbol:
        symbol_earnings = earnings_df[earnings_df.get("symbol", "") == symbol]

        if len(symbol_earnings) > 0:
            symbol_earnings = symbol_earnings.copy()
            symbol_earnings["date"] = pd.to_datetime(symbol_earnings["date"])

            # Days to next earnings
            future_earnings = symbol_earnings[
                symbol_earnings["date"] > reference_date
            ].sort_values("date")

            if len(future_earnings) > 0:
                next_earnings = future_earnings.iloc[0]["date"]
                result["days_to_earnings"] = (next_earnings - reference_date).days
            else:
                result["days_to_earnings"] = 999

            # Days since last earnings
            past_earnings = symbol_earnings[
                symbol_earnings["date"] <= reference_date
            ].sort_values("date", ascending=False)

            if len(past_earnings) > 0:
                last_earnings = past_earnings.iloc[0]["date"]
                result["days_since_earnings"] = (reference_date - last_earnings).days
            else:
                result["days_since_earnings"] = 999

            # Earnings window flag (7 days before or after)
            result["is_earnings_window"] = (
                (result["days_to_earnings"] <= 7) |
                (result["days_since_earnings"] <= 7)
            ).astype(float)
        else:
            result["days_to_earnings"] = np.nan
            result["days_since_earnings"] = np.nan
            result["is_earnings_window"] = np.nan
    else:
        result["days_to_earnings"] = np.nan
        result["days_since_earnings"] = np.nan
        result["is_earnings_window"] = np.nan

    # Economic Event Features
    if economic_df is not None:
        economic_df = economic_df.copy()
        economic_df["date"] = pd.to_datetime(economic_df["date"])

        # High importance events in next 5 days
        future_events = economic_df[
            (economic_df["date"] > reference_date) &
            (economic_df["date"] <= reference_date + timedelta(days=5))
        ]

        high_importance = future_events[
            future_events.get("importance", "") == "high"
        ]

        result["high_impact_events_5d"] = len(high_importance)
        result["is_fed_week"] = any(
            "fomc" in str(e).lower() or "fed" in str(e).lower()
            for e in future_events.get("event", [])
        )
    else:
        result["high_impact_events_5d"] = np.nan
        result["is_fed_week"] = np.nan

    # FDA Event Features
    if fda_df is not None and symbol:
        symbol_fda = fda_df[fda_df.get("symbol", "") == symbol]

        if len(symbol_fda) > 0:
            symbol_fda = symbol_fda.copy()
            symbol_fda["date"] = pd.to_datetime(symbol_fda["date"])

            # Days to next FDA event
            future_fda = symbol_fda[
                symbol_fda["date"] > reference_date
            ].sort_values("date")

            if len(future_fda) > 0:
                result["days_to_fda_event"] = (
                    future_fda.iloc[0]["date"] - reference_date
                ).days
                result["is_fda_window"] = (result["days_to_fda_event"] <= 30).astype(float)
            else:
                result["days_to_fda_event"] = np.nan
                result["is_fda_window"] = 0.0
        else:
            result["days_to_fda_event"] = np.nan
            result["is_fda_window"] = np.nan
    else:
        result["days_to_fda_event"] = np.nan
        result["is_fda_window"] = np.nan

    return result


# =============================================================================
# REGISTER ALTERNATIVE FEATURES
# =============================================================================


# Congressional trading
register_feature(FeatureDefinition(
    name="congressional_trading",
    description="Congressional trading cluster signals and patterns",
    category=FeatureCategory.ALTERNATIVE,
    data_sources=[],  # Custom data source
    compute_fn=None,  # Computed separately with trades data
    output_columns=[
        "congress_cluster_intensity", "congress_cluster_delay",
        "congress_notable_count", "congress_amount_signal",
        "congress_net_direction", "congress_composite_signal"
    ],
    lookback_days=30,
))

# Insider trading
register_feature(FeatureDefinition(
    name="insider_trading",
    description="Insider trading cluster signals",
    category=FeatureCategory.ALTERNATIVE,
    data_sources=[DataSource.INSIDER_SEC],
    compute_fn=None,  # Computed separately with insider data
    output_columns=[
        "insider_cluster_buy_count", "insider_net_value",
        "insider_buy_ratio", "insider_cluster_signal",
        "insider_executive_signal", "insider_composite_signal"
    ],
    lookback_days=90,
))

# Options flow
register_feature(FeatureDefinition(
    name="options_flow",
    description="Options flow signals and unusual activity",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.OPTIONS_FLOW],
    compute_fn=None,  # Computed separately with options data
    output_columns=[
        "put_call_ratio_volume", "put_call_ratio_oi",
        "unusual_options_volume", "call_volume_surge",
        "options_sentiment", "unusual_call_signal"
    ],
    lookback_days=1,
    is_realtime=True,
))

# Sentiment composite
register_feature(FeatureDefinition(
    name="sentiment_composite",
    description="Composite sentiment from AAII, newsletters, social media",
    category=FeatureCategory.SENTIMENT,
    data_sources=[DataSource.REDDIT, DataSource.STOCKTWITS],
    compute_fn=None,  # Computed separately
    output_columns=[
        "aaii_bull_bear_spread", "aaii_contrarian_signal",
        "newsletter_contrarian_signal", "social_sentiment_score"
    ],
    lookback_days=7,
))

# Event calendar
register_feature(FeatureDefinition(
    name="event_calendar",
    description="Upcoming earnings, economic events, FDA dates",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.EARNINGS_CALENDAR],
    compute_fn=None,  # Computed separately
    output_columns=[
        "days_to_earnings", "days_since_earnings", "is_earnings_window",
        "high_impact_events_5d", "is_fed_week", "is_fda_window"
    ],
    lookback_days=90,
))


# =============================================================================
# HELPER CLASS
# =============================================================================


class AlternativeDataFeatures:
    """
    Compute features from alternative data sources.

    Usage:
        adf = AlternativeDataFeatures()

        # Congressional features
        congress_feats = adf.compute_congressional(trades_df, symbol)

        # All features for a symbol
        features = adf.compute_all(
            symbol="AAPL",
            congressional_trades=trades_df,
            insider_trades=insider_df,
            options_data=options_df,
            aaii_sentiment=aaii_df,
            earnings_calendar=earnings_df,
        )
    """

    def __init__(self):
        pass

    def compute_congressional(
        self,
        trades_df: pd.DataFrame,
        symbol: str,
        lookback_days: int = 30,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Compute congressional trading features."""
        return compute_congressional_features(
            trades_df, symbol, lookback_days, reference_date
        )

    def compute_insider(
        self,
        insider_df: pd.DataFrame,
        symbol: str,
        lookback_days: int = 90,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Compute insider trading features."""
        return compute_insider_features(
            insider_df, symbol, lookback_days, reference_date
        )

    def compute_options(
        self,
        options_df: pd.DataFrame,
        symbol: str,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Compute options flow features."""
        return compute_options_flow_features(options_df, symbol, reference_date)

    def compute_sentiment(
        self,
        symbol: str,
        aaii_df: Optional[pd.DataFrame] = None,
        newsletter_df: Optional[pd.DataFrame] = None,
        social_df: Optional[pd.DataFrame] = None,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Compute sentiment features."""
        return compute_sentiment_features(
            aaii_df, newsletter_df, social_df, symbol, reference_date
        )

    def compute_events(
        self,
        symbol: str,
        earnings_df: Optional[pd.DataFrame] = None,
        economic_df: Optional[pd.DataFrame] = None,
        fda_df: Optional[pd.DataFrame] = None,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Compute event calendar features."""
        return compute_event_features(
            earnings_df, economic_df, fda_df, symbol, reference_date
        )

    def compute_all(
        self,
        symbol: str,
        congressional_trades: Optional[pd.DataFrame] = None,
        insider_trades: Optional[pd.DataFrame] = None,
        options_data: Optional[pd.DataFrame] = None,
        aaii_sentiment: Optional[pd.DataFrame] = None,
        newsletter_sentiment: Optional[pd.DataFrame] = None,
        social_sentiment: Optional[pd.DataFrame] = None,
        earnings_calendar: Optional[pd.DataFrame] = None,
        economic_calendar: Optional[pd.DataFrame] = None,
        fda_calendar: Optional[pd.DataFrame] = None,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Compute all alternative data features for a symbol.

        Returns:
            DataFrame with all available alternative features
        """
        if reference_date is None:
            reference_date = datetime.now()

        result = pd.DataFrame()

        # Congressional features
        if congressional_trades is not None:
            try:
                congress_feats = self.compute_congressional(
                    congressional_trades, symbol, reference_date=reference_date
                )
                result = pd.concat([result, congress_feats], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute congressional features: {e}")

        # Insider features
        if insider_trades is not None:
            try:
                insider_feats = self.compute_insider(
                    insider_trades, symbol, reference_date=reference_date
                )
                result = pd.concat([result, insider_feats], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute insider features: {e}")

        # Options features
        if options_data is not None:
            try:
                options_feats = self.compute_options(
                    options_data, symbol, reference_date=reference_date
                )
                result = pd.concat([result, options_feats], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute options features: {e}")

        # Sentiment features
        if any([aaii_sentiment is not None, newsletter_sentiment is not None,
                social_sentiment is not None]):
            try:
                sentiment_feats = self.compute_sentiment(
                    symbol,
                    aaii_df=aaii_sentiment,
                    newsletter_df=newsletter_sentiment,
                    social_df=social_sentiment,
                    reference_date=reference_date,
                )
                result = pd.concat([result, sentiment_feats], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute sentiment features: {e}")

        # Event features
        if any([earnings_calendar is not None, economic_calendar is not None,
                fda_calendar is not None]):
            try:
                event_feats = self.compute_events(
                    symbol,
                    earnings_df=earnings_calendar,
                    economic_df=economic_calendar,
                    fda_df=fda_calendar,
                    reference_date=reference_date,
                )
                result = pd.concat([result, event_feats], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute event features: {e}")

        return result

    @staticmethod
    def get_feature_list() -> list[str]:
        """Get list of all alternative data feature names."""
        return [
            # Congressional
            "congress_cluster_intensity",
            "congress_cluster_delay",
            "congress_notable_count",
            "congress_amount_signal",
            "congress_net_direction",
            "congress_composite_signal",
            # Insider
            "insider_cluster_buy_count",
            "insider_net_value",
            "insider_buy_ratio",
            "insider_cluster_signal",
            "insider_executive_signal",
            "insider_composite_signal",
            # Options
            "put_call_ratio_volume",
            "put_call_ratio_oi",
            "unusual_options_volume",
            "call_volume_surge",
            "options_sentiment",
            "unusual_call_signal",
            # Sentiment
            "aaii_bull_bear_spread",
            "aaii_extreme_bullish",
            "aaii_extreme_bearish",
            "aaii_contrarian_signal",
            "newsletter_bullish_pct",
            "newsletter_bearish_pct",
            "newsletter_contrarian_signal",
            "social_sentiment_score",
            "social_volume",
            "social_sentiment_extreme",
            # Events
            "days_to_earnings",
            "days_since_earnings",
            "is_earnings_window",
            "high_impact_events_5d",
            "is_fed_week",
            "days_to_fda_event",
            "is_fda_window",
        ]
