"""
Latent Knowledge Features

Features derived from Claude's market intuitions and domain knowledge.
These encode market patterns that are known from experience but often
not systematically tested:

1. Sector Lead-Lag Relationships
2. Calendar and Seasonality Effects
3. Event Pattern Recognition
4. Regime-Conditional Behaviors
5. Cross-Asset Relationships
6. Behavioral Pattern Features

Each feature encodes a testable hypothesis about market behavior.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
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
# SECTOR LEAD-LAG FEATURES
# =============================================================================


# Sector lead relationships (leader -> follower)
SECTOR_LEAD_RELATIONSHIPS = {
    # Semiconductors lead broader tech
    "tech": {
        "leaders": ["SMH", "SOXX", "AMD", "NVDA"],
        "lead_days": 10,
        "description": "Semis lead tech by 2 weeks",
    },
    # Financials lead rates
    "financials": {
        "leaders": ["XLF", "KRE", "BAC", "JPM"],
        "lead_days": 5,
        "description": "Banks lead rate expectations",
    },
    # Consumer discretionary leads economy
    "consumer": {
        "leaders": ["XRT", "AMZN", "HD"],
        "lead_days": 15,
        "description": "Retail leads economic cycle",
    },
    # Transportation leads industrial
    "industrials": {
        "leaders": ["IYT", "UPS", "FDX"],
        "lead_days": 10,
        "description": "Transport leads industrial activity",
    },
    # Energy leads inflation
    "inflation": {
        "leaders": ["XLE", "USO", "XOM"],
        "lead_days": 20,
        "description": "Energy leads inflation prints",
    },
}


def compute_sector_lead_signal(
    target_df: pd.DataFrame,
    leader_df: pd.DataFrame,
    lead_days: int = 10,
) -> pd.DataFrame:
    """
    Compute sector lead-lag signal.

    If the leader moved X days ago, expect target to follow.

    Args:
        target_df: OHLCV for target symbol
        leader_df: OHLCV for leader symbol/ETF
        lead_days: Number of days leader leads by

    Returns:
        DataFrame with lead signal features
    """
    result = pd.DataFrame(index=target_df.index)

    target_returns = target_df["close"].pct_change()
    leader_returns = leader_df["close"].pct_change()

    # Align indices
    leader_returns = leader_returns.reindex(target_df.index)

    # Leader return over past N days (lagged signal)
    leader_momentum = leader_returns.rolling(lead_days).sum()
    result["leader_momentum"] = leader_momentum

    # Leader direction signal (lagged)
    result["leader_direction"] = np.sign(leader_momentum)

    # Has leader moved significantly?
    leader_vol = leader_returns.rolling(60).std() * np.sqrt(252)
    leader_move_significant = leader_momentum.abs() > leader_vol * 0.5
    result["leader_significant_move"] = leader_move_significant.astype(float)

    # Cross-correlation (for validation)
    result["target_leader_corr"] = target_returns.rolling(60).corr(leader_returns)

    # Lead signal: leader moved, target hasn't caught up yet
    target_momentum = target_returns.rolling(lead_days).sum()
    result["lead_lag_divergence"] = leader_momentum - target_momentum

    # Composite lead signal
    result["sector_lead_signal"] = (
        result["leader_direction"] *
        result["leader_significant_move"] *
        (result["lead_lag_divergence"].abs() > 0.02).astype(float)
    )

    return result


# =============================================================================
# CALENDAR AND SEASONALITY FEATURES
# =============================================================================


class DayOfWeek(Enum):
    """Day of week enumeration."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4


def compute_calendar_features(
    df: pd.DataFrame,
    reference_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Compute calendar-based features encoding known seasonality patterns.

    Patterns encoded:
    - Monday reversal: Friday momentum tends to reverse Monday
    - FOMC week effects: Different behavior around Fed meetings
    - Month-end effects: Rebalancing at month boundaries
    - Options expiration: Third Friday effects
    - Quarter-end: Mutual fund window dressing

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        reference_date: Current date for computing features

    Returns:
        DataFrame with calendar features
    """
    result = pd.DataFrame(index=df.index)

    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    close = df["close"]
    returns = close.pct_change()

    # Day of week
    result["day_of_week"] = df.index.dayofweek
    result["is_monday"] = (result["day_of_week"] == 0).astype(float)
    result["is_friday"] = (result["day_of_week"] == 4).astype(float)

    # Monday reversal signal
    # If Friday was strong, expect Monday to be weak
    friday_return = returns.shift(3).where(result["is_monday"] == 1, np.nan)
    result["friday_momentum"] = friday_return.ffill()
    result["monday_reversal_signal"] = -result["friday_momentum"].where(
        result["is_monday"] == 1, 0
    )

    # Month boundaries
    result["is_month_start"] = (df.index.day <= 3).astype(float)
    result["is_month_end"] = (df.index.day >= 28).astype(float)
    result["days_to_month_end"] = (
        df.index.to_period("M").end_time - df.index
    ).apply(lambda x: x.days if pd.notna(x) else 0)

    # Quarter boundaries
    result["is_quarter_end"] = (
        (df.index.month.isin([3, 6, 9, 12])) &
        (df.index.day >= 25)
    ).astype(float)

    # Options expiration (third Friday)
    result["is_opex_week"] = (
        (result["day_of_week"] <= 4) &
        (df.index.day >= 15) &
        (df.index.day <= 21)
    ).astype(float)

    # Compute historical patterns
    # Monday average return
    monday_returns = returns.where(result["is_monday"] == 1)
    result["monday_avg_return"] = monday_returns.rolling(252, min_periods=20).mean()

    # Month-end drift
    month_end_returns = returns.where(result["is_month_end"] == 1)
    result["month_end_effect"] = month_end_returns.rolling(252, min_periods=10).mean()

    return result


# =============================================================================
# GAP AND MOMENTUM PATTERN FEATURES
# =============================================================================


def compute_gap_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute gap-related features.

    Key patterns:
    - Gap fade: Large gaps (>3%) tend to fade within the day
    - Gap fill: Most gaps eventually fill
    - Gap and go: Some gaps signal continuation

    Args:
        df: OHLCV DataFrame

    Returns:
        DataFrame with gap features
    """
    result = pd.DataFrame(index=df.index)

    high, low, open_, close = df["high"], df["low"], df["open"], df["close"]

    # Gap size (open vs prior close)
    prior_close = close.shift(1)
    result["gap_size"] = (open_ - prior_close) / prior_close
    result["gap_size_abs"] = result["gap_size"].abs()

    # Gap direction
    result["gap_up"] = (result["gap_size"] > 0.01).astype(float)
    result["gap_down"] = (result["gap_size"] < -0.01).astype(float)

    # Large gap flag (>3%)
    result["large_gap_up"] = (result["gap_size"] > 0.03).astype(float)
    result["large_gap_down"] = (result["gap_size"] < -0.03).astype(float)
    result["large_gap"] = result["large_gap_up"] + result["large_gap_down"]

    # Gap fade: Did price reverse during the day?
    day_return = (close - open_) / open_
    gap_faded = np.sign(result["gap_size"]) != np.sign(day_return)
    result["gap_faded"] = gap_faded.astype(float)

    # Gap fade signal (contrarian on large gaps)
    result["gap_fade_signal"] = (
        result["large_gap_up"] * -1 +  # Fade large gap ups
        result["large_gap_down"] * 1    # Buy large gap downs
    )

    # Historical gap fade rate
    large_gaps = result["large_gap"] == 1
    result["gap_fade_rate"] = result["gap_faded"].where(large_gaps).rolling(
        252, min_periods=10
    ).mean()

    # Gap fill probability
    # Did the gap fill within 5 days?
    for i in range(1, 6):
        future_low = low.shift(-i)
        future_high = high.shift(-i)
        gap_filled = (
            ((result["gap_size"] > 0) & (future_low <= prior_close)) |
            ((result["gap_size"] < 0) & (future_high >= prior_close))
        )
        result[f"gap_filled_{i}d"] = gap_filled.astype(float)

    return result


# =============================================================================
# VOLATILITY PATTERN FEATURES
# =============================================================================


def compute_vix_features(
    target_df: pd.DataFrame,
    vix_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute VIX-based features encoding volatility patterns.

    Key patterns:
    - VIX mean reversion: VIX >30 mean-reverts within 10 days
    - Vol crush after events: IV collapses post-catalyst
    - VIX term structure: Contango vs backwardation

    Args:
        target_df: Target symbol OHLCV
        vix_df: VIX data (optional, uses realized vol if not provided)

    Returns:
        DataFrame with VIX features
    """
    result = pd.DataFrame(index=target_df.index)

    # Realized volatility as proxy if no VIX data
    returns = target_df["close"].pct_change()
    realized_vol = returns.rolling(20).std() * np.sqrt(252) * 100  # Annualized %

    if vix_df is not None and "close" in vix_df.columns:
        vix = vix_df["close"].reindex(target_df.index)
    else:
        # Use realized vol as proxy (scaled to VIX-like levels)
        vix = realized_vol * 1.2  # VIX typically higher than realized

    result["vix_level"] = vix
    result["vix_percentile"] = vix.rolling(252).rank(pct=True)

    # VIX mean reversion signal
    # When VIX is very high, expect it to mean-revert (stocks rally)
    result["vix_extreme_high"] = (result["vix_percentile"] > 0.9).astype(float)
    result["vix_extreme_low"] = (result["vix_percentile"] < 0.1).astype(float)

    # Mean reversion signal (bullish when VIX extreme high)
    result["vix_mean_reversion_signal"] = (
        result["vix_extreme_high"] * 1 +  # Buy when VIX very high
        result["vix_extreme_low"] * -1     # Sell when VIX very low
    )

    # VIX change features
    vix_change_1d = vix.pct_change()
    vix_change_5d = vix.pct_change(5)

    result["vix_spike"] = (vix_change_1d > 0.15).astype(float)  # 15%+ spike
    result["vix_collapse"] = (vix_change_1d < -0.10).astype(float)  # 10%+ drop

    # After VIX spike, expect reversal
    result["post_spike_signal"] = result["vix_spike"].shift(1) * 1  # Bullish after spike

    # VIX vs realized vol spread
    result["vol_risk_premium"] = vix - realized_vol

    return result


# =============================================================================
# CROSS-ASSET RELATIONSHIP FEATURES
# =============================================================================


def compute_cross_asset_features(
    target_df: pd.DataFrame,
    rates_df: Optional[pd.DataFrame] = None,
    dollar_df: Optional[pd.DataFrame] = None,
    credit_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute cross-asset relationship features.

    Key relationships:
    - Banks-rates: Banks outperform in rising rate regimes
    - Dollar impact: Strong dollar hurts exporters
    - Credit leads equity: Credit stress precedes equity weakness
    - Energy-inflation: Energy leads inflation expectations

    Args:
        target_df: Target symbol OHLCV
        rates_df: 10Y yield data (optional)
        dollar_df: DXY dollar index data (optional)
        credit_df: Credit spread data (optional)

    Returns:
        DataFrame with cross-asset features
    """
    result = pd.DataFrame(index=target_df.index)

    target_returns = target_df["close"].pct_change()

    # Rates relationship
    if rates_df is not None and "close" in rates_df.columns:
        rates = rates_df["close"].reindex(target_df.index)
        rates_change = rates.diff()

        # Rates regime (rising vs falling)
        result["rates_rising"] = (rates.pct_change(20) > 0).astype(float)
        result["rates_falling"] = (rates.pct_change(20) < 0).astype(float)

        # Banks-rates beta (for financial stocks)
        result["rates_beta_20d"] = target_returns.rolling(20).cov(
            rates.pct_change()
        ) / rates.pct_change().rolling(20).var()

        # Rising rates signal (positive for banks, negative for utilities)
        result["rising_rates_signal"] = result["rates_rising"] * np.sign(
            result["rates_beta_20d"].fillna(0)
        )
    else:
        result["rates_rising"] = np.nan
        result["rates_falling"] = np.nan
        result["rates_beta_20d"] = np.nan
        result["rising_rates_signal"] = np.nan

    # Dollar relationship
    if dollar_df is not None and "close" in dollar_df.columns:
        dollar = dollar_df["close"].reindex(target_df.index)
        dollar_returns = dollar.pct_change()

        # Dollar trend
        result["dollar_trend_20d"] = np.sign(dollar.pct_change(20))

        # Dollar sensitivity
        result["dollar_beta_20d"] = target_returns.rolling(20).cov(
            dollar_returns
        ) / dollar_returns.rolling(20).var()

        # Dollar impact (negative beta = hurt by strong dollar)
        result["dollar_impact_signal"] = (
            result["dollar_trend_20d"] * result["dollar_beta_20d"]
        )
    else:
        result["dollar_trend_20d"] = np.nan
        result["dollar_beta_20d"] = np.nan
        result["dollar_impact_signal"] = np.nan

    # Credit spread relationship
    if credit_df is not None and "close" in credit_df.columns:
        credit = credit_df["close"].reindex(target_df.index)

        # Credit spread widening (stress signal)
        credit_change_20d = credit.pct_change(20)
        result["credit_widening"] = (credit_change_20d > 0.1).astype(float)
        result["credit_tightening"] = (credit_change_20d < -0.1).astype(float)

        # Credit leads equity (high spread = bearish for stocks)
        credit_percentile = credit.rolling(252).rank(pct=True)
        result["credit_stress_signal"] = (credit_percentile > 0.8).astype(float) * -1
    else:
        result["credit_widening"] = np.nan
        result["credit_tightening"] = np.nan
        result["credit_stress_signal"] = np.nan

    return result


# =============================================================================
# EARNINGS AND EVENT PATTERN FEATURES
# =============================================================================


def compute_earnings_pattern_features(
    df: pd.DataFrame,
    earnings_df: Optional[pd.DataFrame] = None,
    symbol: Optional[str] = None,
) -> pd.DataFrame:
    """
    Compute earnings pattern features.

    Key patterns:
    - Post-earnings drift: Beats continue to outperform
    - Pre-earnings volatility: IV expansion before earnings
    - Earnings momentum: Beats cluster within sectors

    Args:
        df: OHLCV DataFrame
        earnings_df: Earnings calendar with results
        symbol: Symbol for symbol-specific features

    Returns:
        DataFrame with earnings pattern features
    """
    result = pd.DataFrame(index=df.index)

    close = df["close"]
    returns = close.pct_change()

    if earnings_df is not None and symbol:
        symbol_earnings = earnings_df[earnings_df.get("symbol", "") == symbol].copy()

        if len(symbol_earnings) > 0:
            symbol_earnings["date"] = pd.to_datetime(symbol_earnings["date"])

            # Mark earnings days
            earnings_dates = set(symbol_earnings["date"].dt.date)
            result["is_earnings_day"] = df.index.date.isin(earnings_dates).astype(float)

            # Days since last earnings
            last_earnings = None
            days_since = []
            for date in df.index:
                past = symbol_earnings[symbol_earnings["date"] <= date]
                if len(past) > 0:
                    last_earnings = past.iloc[-1]["date"]
                    days_since.append((date - last_earnings).days)
                else:
                    days_since.append(np.nan)
            result["days_since_earnings"] = days_since

            # Earnings reaction (return on day after)
            earnings_reaction = returns.where(
                result["is_earnings_day"].shift(1) == 1
            ).ffill()
            result["last_earnings_reaction"] = earnings_reaction

            # Post-earnings drift signal
            # Positive reaction -> expect continued outperformance
            result["post_earnings_drift_signal"] = np.sign(
                result["last_earnings_reaction"]
            ) * (result["days_since_earnings"] <= 20).astype(float)
        else:
            result["is_earnings_day"] = 0.0
            result["days_since_earnings"] = np.nan
            result["last_earnings_reaction"] = np.nan
            result["post_earnings_drift_signal"] = np.nan
    else:
        result["is_earnings_day"] = np.nan
        result["days_since_earnings"] = np.nan
        result["last_earnings_reaction"] = np.nan
        result["post_earnings_drift_signal"] = np.nan

    # Volatility pattern around events (using price data)
    vol_5d = returns.rolling(5).std() * np.sqrt(252)
    vol_20d = returns.rolling(20).std() * np.sqrt(252)
    result["vol_expansion"] = vol_5d / vol_20d - 1

    # High vol expansion may signal event coming
    result["vol_event_signal"] = (result["vol_expansion"] > 0.5).astype(float)

    return result


# =============================================================================
# REGISTER LATENT KNOWLEDGE FEATURES
# =============================================================================


# Sector lead-lag
register_feature(FeatureDefinition(
    name="sector_lead_lag",
    description="Sector lead-lag relationship signals (semis->tech, etc.)",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=None,  # Requires leader data
    output_columns=[
        "leader_momentum", "leader_direction", "leader_significant_move",
        "target_leader_corr", "lead_lag_divergence", "sector_lead_signal"
    ],
    lookback_days=60,
))

# Calendar effects
register_feature(FeatureDefinition(
    name="calendar_effects",
    description="Calendar-based seasonality patterns",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_calendar_features,
    output_columns=[
        "day_of_week", "is_monday", "is_friday",
        "monday_reversal_signal", "is_month_end", "is_quarter_end",
        "is_opex_week", "monday_avg_return", "month_end_effect"
    ],
    lookback_days=5,
))

# Gap patterns
register_feature(FeatureDefinition(
    name="gap_patterns",
    description="Gap fade and fill patterns",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_gap_features,
    output_columns=[
        "gap_size", "gap_up", "gap_down", "large_gap",
        "gap_faded", "gap_fade_signal", "gap_fade_rate"
    ],
    lookback_days=252,
))

# VIX patterns
register_feature(FeatureDefinition(
    name="vix_patterns",
    description="VIX mean reversion and volatility patterns",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=None,  # Requires VIX data
    output_columns=[
        "vix_level", "vix_percentile", "vix_extreme_high",
        "vix_mean_reversion_signal", "vix_spike", "post_spike_signal"
    ],
    lookback_days=252,
))

# Cross-asset relationships
register_feature(FeatureDefinition(
    name="cross_asset_relationships",
    description="Rates, dollar, credit relationship signals",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.FRED_ECONOMIC],
    compute_fn=None,  # Requires cross-asset data
    output_columns=[
        "rates_rising", "rates_beta_20d", "rising_rates_signal",
        "dollar_trend_20d", "dollar_impact_signal", "credit_stress_signal"
    ],
    lookback_days=60,
))

# Earnings patterns
register_feature(FeatureDefinition(
    name="earnings_patterns",
    description="Post-earnings drift and event patterns",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.EARNINGS_CALENDAR],
    compute_fn=None,  # Requires earnings data
    output_columns=[
        "is_earnings_day", "days_since_earnings",
        "last_earnings_reaction", "post_earnings_drift_signal"
    ],
    lookback_days=90,
))


# =============================================================================
# HELPER CLASS
# =============================================================================


class LatentKnowledgeFeatures:
    """
    Compute features derived from market intuitions and domain knowledge.

    This class encodes Claude's understanding of market patterns
    into testable, quantifiable features.

    Usage:
        lkf = LatentKnowledgeFeatures()

        # Compute all features
        features = lkf.compute_all(
            df=price_df,
            symbol="AAPL",
            vix_df=vix_data,
            rates_df=rates_data,
            earnings_df=earnings_data,
        )

        # Compute specific features
        gap_features = lkf.compute_gap_patterns(df)
        calendar_features = lkf.compute_calendar_effects(df)
    """

    def __init__(self):
        self.sector_relationships = SECTOR_LEAD_RELATIONSHIPS

    def compute_sector_lead_lag(
        self,
        target_df: pd.DataFrame,
        leader_df: pd.DataFrame,
        lead_days: int = 10,
    ) -> pd.DataFrame:
        """Compute sector lead-lag features."""
        return compute_sector_lead_signal(target_df, leader_df, lead_days)

    def compute_calendar_effects(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute calendar-based seasonality features."""
        return compute_calendar_features(df)

    def compute_gap_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute gap fade and fill patterns."""
        return compute_gap_features(df)

    def compute_vix_patterns(
        self,
        df: pd.DataFrame,
        vix_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Compute VIX-based volatility patterns."""
        return compute_vix_features(df, vix_df)

    def compute_cross_asset(
        self,
        df: pd.DataFrame,
        rates_df: Optional[pd.DataFrame] = None,
        dollar_df: Optional[pd.DataFrame] = None,
        credit_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Compute cross-asset relationship features."""
        return compute_cross_asset_features(df, rates_df, dollar_df, credit_df)

    def compute_earnings_patterns(
        self,
        df: pd.DataFrame,
        earnings_df: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None,
    ) -> pd.DataFrame:
        """Compute earnings and event pattern features."""
        return compute_earnings_pattern_features(df, earnings_df, symbol)

    def compute_all(
        self,
        df: pd.DataFrame,
        symbol: Optional[str] = None,
        leader_df: Optional[pd.DataFrame] = None,
        vix_df: Optional[pd.DataFrame] = None,
        rates_df: Optional[pd.DataFrame] = None,
        dollar_df: Optional[pd.DataFrame] = None,
        credit_df: Optional[pd.DataFrame] = None,
        earnings_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Compute all latent knowledge features.

        Args:
            df: Target symbol OHLCV data
            symbol: Symbol name (for earnings patterns)
            leader_df: Sector leader data (for lead-lag)
            vix_df: VIX data
            rates_df: 10Y yield data
            dollar_df: Dollar index data
            credit_df: Credit spread data
            earnings_df: Earnings calendar data

        Returns:
            DataFrame with all latent knowledge features
        """
        result = pd.DataFrame(index=df.index)

        # Always compute these (only need price data)
        try:
            calendar = self.compute_calendar_effects(df)
            result = pd.concat([result, calendar], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute calendar features: {e}")

        try:
            gaps = self.compute_gap_patterns(df)
            result = pd.concat([result, gaps], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute gap features: {e}")

        # Optional features requiring external data
        if leader_df is not None:
            try:
                lead_lag = self.compute_sector_lead_lag(df, leader_df)
                result = pd.concat([result, lead_lag], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute lead-lag features: {e}")

        # VIX patterns (can use realized vol as proxy)
        try:
            vix = self.compute_vix_patterns(df, vix_df)
            result = pd.concat([result, vix], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute VIX features: {e}")

        # Cross-asset relationships
        if any([rates_df is not None, dollar_df is not None, credit_df is not None]):
            try:
                cross_asset = self.compute_cross_asset(
                    df, rates_df, dollar_df, credit_df
                )
                result = pd.concat([result, cross_asset], axis=1)
            except Exception as e:
                logger.warning(f"Failed to compute cross-asset features: {e}")

        # Earnings patterns
        try:
            earnings = self.compute_earnings_patterns(df, earnings_df, symbol)
            result = pd.concat([result, earnings], axis=1)
        except Exception as e:
            logger.warning(f"Failed to compute earnings features: {e}")

        return result

    @staticmethod
    def get_hypotheses() -> dict[str, str]:
        """
        Get list of latent knowledge hypotheses being tested.

        Returns:
            Dictionary of hypothesis name -> description
        """
        return {
            # Sector relationships
            "semis_lead_tech": "Semiconductors lead broader tech by 2-4 weeks",
            "energy_inflation": "Energy prices lead inflation prints",
            "banks_rates": "Banks outperform in rising rate regimes",
            "transport_industrial": "Transportation leads industrial activity",
            "retail_consumer": "Retail leads consumer sentiment",

            # Behavioral patterns
            "gap_fade": "Opening gaps >3% fade 60%+ of time",
            "monday_reversal": "Friday momentum reverses Monday",
            "month_end_drift": "Positive drift on last days of month",
            "quarter_end_window": "Mutual fund window dressing at quarter end",
            "opex_effects": "Options expiration affects price action",

            # Volatility patterns
            "vix_mean_reversion": "VIX >30 mean-reverts within 10 days",
            "vol_crush_post_event": "IV collapses after catalysts",
            "volatility_clustering": "High vol begets high vol",

            # Cross-asset
            "credit_leads_equity": "Credit stress precedes equity weakness",
            "dollar_impact": "Strong dollar hurts emerging market exporters",

            # Event patterns
            "post_earnings_drift": "Earnings beats continue to outperform",
            "fed_day_drift": "Markets drift in direction of initial move post-FOMC",
            "insider_timing": "Insiders buy 2-3 months before catalysts",
            "options_flow_lead": "Unusual options precedes news by 1-3 days",
            "analyst_herding": "Analyst upgrades cluster and lag reality",
        }

    @staticmethod
    def get_feature_list() -> list[str]:
        """Get list of all latent knowledge feature names."""
        return [
            # Sector lead-lag
            "leader_momentum",
            "leader_direction",
            "leader_significant_move",
            "target_leader_corr",
            "lead_lag_divergence",
            "sector_lead_signal",
            # Calendar effects
            "day_of_week",
            "is_monday",
            "is_friday",
            "monday_reversal_signal",
            "is_month_start",
            "is_month_end",
            "days_to_month_end",
            "is_quarter_end",
            "is_opex_week",
            "monday_avg_return",
            "month_end_effect",
            # Gap patterns
            "gap_size",
            "gap_size_abs",
            "gap_up",
            "gap_down",
            "large_gap_up",
            "large_gap_down",
            "large_gap",
            "gap_faded",
            "gap_fade_signal",
            "gap_fade_rate",
            # VIX patterns
            "vix_level",
            "vix_percentile",
            "vix_extreme_high",
            "vix_extreme_low",
            "vix_mean_reversion_signal",
            "vix_spike",
            "vix_collapse",
            "post_spike_signal",
            "vol_risk_premium",
            # Cross-asset
            "rates_rising",
            "rates_falling",
            "rates_beta_20d",
            "rising_rates_signal",
            "dollar_trend_20d",
            "dollar_beta_20d",
            "dollar_impact_signal",
            "credit_widening",
            "credit_tightening",
            "credit_stress_signal",
            # Earnings patterns
            "is_earnings_day",
            "days_since_earnings",
            "last_earnings_reaction",
            "post_earnings_drift_signal",
            "vol_expansion",
            "vol_event_signal",
        ]
