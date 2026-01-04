"""
Feature Registry

Central registry of all computable features with:
- Feature definitions (name, description, computation, dependencies)
- Categorization (technical, fundamental, alternative, sentiment, embedding)
- Data source requirements
- Default parameters

50+ features organized by category.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class FeatureCategory(Enum):
    """Feature categories."""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    ALTERNATIVE = "alternative"
    SENTIMENT = "sentiment"
    EMBEDDING = "embedding"
    FLOW = "flow"
    RISK = "risk"
    REGIME = "regime"


class DataSource(Enum):
    """Data sources for features."""
    PRICE_YAHOO = "price_yahoo"
    VOLUME_YAHOO = "volume_yahoo"
    OPTIONS_FLOW = "options_flow"
    SEC_FILINGS = "sec_filings"
    NEWS_RSS = "news_rss"
    NEWS_API = "news_api"
    REDDIT = "reddit"
    STOCKTWITS = "stocktwits"
    INSIDER_SEC = "insider_sec"
    ETF_FLOWS = "etf_flows"
    FRED_ECONOMIC = "fred_economic"
    EARNINGS_CALENDAR = "earnings_calendar"


@dataclass
class FeatureDefinition:
    """Definition of a computable feature."""
    name: str
    description: str
    category: FeatureCategory
    data_sources: list[DataSource]
    compute_fn: Optional[Callable] = None
    dependencies: list[str] = field(default_factory=list)
    default_params: dict = field(default_factory=dict)
    output_columns: list[str] = field(default_factory=list)
    lookback_days: int = 0
    is_realtime: bool = False


# =============================================================================
# FEATURE COMPUTATION FUNCTIONS
# =============================================================================

def compute_returns(df: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
    """Compute returns over various periods."""
    periods = periods or [1, 5, 10, 20, 60]
    result = pd.DataFrame(index=df.index)

    for p in periods:
        result[f"return_{p}d"] = df["close"].pct_change(p)

    return result


def compute_volatility(df: pd.DataFrame, windows: list[int] = None) -> pd.DataFrame:
    """Compute rolling volatility."""
    windows = windows or [5, 10, 20, 60]
    result = pd.DataFrame(index=df.index)

    returns = df["close"].pct_change()

    for w in windows:
        result[f"volatility_{w}d"] = returns.rolling(w).std() * np.sqrt(252)

    return result


def compute_momentum(df: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
    """Compute momentum indicators."""
    periods = periods or [5, 10, 20, 60]
    result = pd.DataFrame(index=df.index)

    for p in periods:
        result[f"momentum_{p}d"] = df["close"].pct_change(p)
        result[f"momentum_rank_{p}d"] = result[f"momentum_{p}d"].rolling(252).rank(pct=True)

    return result


def compute_rsi(df: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
    """Compute RSI for various periods."""
    periods = periods or [7, 14, 21]
    result = pd.DataFrame(index=df.index)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    for p in periods:
        avg_gain = gain.rolling(p).mean()
        avg_loss = loss.rolling(p).mean()
        rs = avg_gain / avg_loss
        result[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    return result


def compute_bollinger(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Compute Bollinger Bands."""
    result = pd.DataFrame(index=df.index)

    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()

    result["bb_upper"] = ma + num_std * std
    result["bb_lower"] = ma - num_std * std
    result["bb_middle"] = ma
    result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / result["bb_middle"]
    result["bb_position"] = (df["close"] - result["bb_lower"]) / (result["bb_upper"] - result["bb_lower"])

    return result


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Compute MACD."""
    result = pd.DataFrame(index=df.index)

    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()

    result["macd_line"] = ema_fast - ema_slow
    result["macd_signal"] = result["macd_line"].ewm(span=signal, adjust=False).mean()
    result["macd_histogram"] = result["macd_line"] - result["macd_signal"]

    return result


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute Average True Range."""
    result = pd.DataFrame(index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    result["atr"] = tr.rolling(period).mean()
    result["atr_pct"] = result["atr"] / close * 100

    return result


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute volume-based features."""
    result = pd.DataFrame(index=df.index)

    volume = df["volume"]

    result["volume_sma_20"] = volume.rolling(20).mean()
    result["volume_ratio"] = volume / result["volume_sma_20"]
    result["volume_momentum"] = volume.pct_change(5)

    # On-Balance Volume
    close_diff = df["close"].diff()
    obv_direction = np.where(close_diff > 0, 1, np.where(close_diff < 0, -1, 0))
    result["obv"] = (volume * obv_direction).cumsum()
    result["obv_momentum"] = result["obv"].pct_change(20)

    # Volume-Price Trend
    result["vpt"] = (volume * df["close"].pct_change()).cumsum()

    return result


def compute_price_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute price pattern features."""
    result = pd.DataFrame(index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    open_ = df["open"]

    # Candlestick patterns
    body = close - open_
    upper_shadow = high - pd.concat([close, open_], axis=1).max(axis=1)
    lower_shadow = pd.concat([close, open_], axis=1).min(axis=1) - low

    result["candle_body"] = body
    result["candle_upper_shadow"] = upper_shadow
    result["candle_lower_shadow"] = lower_shadow

    # Doji (small body)
    avg_range = (high - low).rolling(20).mean()
    result["is_doji"] = (abs(body) < avg_range * 0.1).astype(int)

    # Hammer (long lower shadow)
    result["is_hammer"] = (
        (lower_shadow > abs(body) * 2) &
        (upper_shadow < abs(body) * 0.5)
    ).astype(int)

    # Gap
    result["gap_up"] = (low > high.shift(1)).astype(int)
    result["gap_down"] = (high < low.shift(1)).astype(int)
    result["gap_size"] = (open_ - close.shift(1)) / close.shift(1)

    return result


def compute_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute trend-related features."""
    result = pd.DataFrame(index=df.index)

    close = df["close"]

    # Moving averages
    for period in [10, 20, 50, 200]:
        result[f"sma_{period}"] = close.rolling(period).mean()
        result[f"ema_{period}"] = close.ewm(span=period, adjust=False).mean()
        result[f"price_vs_sma_{period}"] = (close - result[f"sma_{period}"]) / result[f"sma_{period}"]

    # Trend direction
    result["trend_20d"] = np.sign(close - close.shift(20))
    result["trend_50d"] = np.sign(close - close.shift(50))

    # Higher highs / lower lows
    result["higher_high_5d"] = (df["high"] > df["high"].rolling(5).max().shift(1)).astype(int)
    result["lower_low_5d"] = (df["low"] < df["low"].rolling(5).min().shift(1)).astype(int)

    # ADX-like trend strength (simplified)
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    atr = compute_atr(df)["atr"]
    plus_di = 100 * plus_dm.rolling(14).mean() / atr
    minus_di = 100 * minus_dm.rolling(14).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    result["adx"] = dx.rolling(14).mean()

    return result


def compute_mean_reversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute mean reversion features."""
    result = pd.DataFrame(index=df.index)

    close = df["close"]

    # Z-scores
    for period in [20, 50, 100]:
        ma = close.rolling(period).mean()
        std = close.rolling(period).std()
        result[f"zscore_{period}d"] = (close - ma) / std

    # Distance from moving averages
    result["dist_from_52w_high"] = (close - close.rolling(252).max()) / close.rolling(252).max()
    result["dist_from_52w_low"] = (close - close.rolling(252).min()) / close.rolling(252).min()

    # Percentile rank
    result["price_percentile_60d"] = close.rolling(60).rank(pct=True)
    result["price_percentile_252d"] = close.rolling(252).rank(pct=True)

    return result


# =============================================================================
# ALTERNATIVE DATA FEATURES (placeholders - actual computation in separate modules)
# =============================================================================

def compute_options_features(symbol: str, options_data: dict) -> pd.DataFrame:
    """Compute options-derived features."""
    # Placeholder - actual implementation in options_flow.py
    return pd.DataFrame({
        "put_call_ratio": [options_data.get("put_call_ratio", np.nan)],
        "iv_skew": [options_data.get("iv_skew", np.nan)],
        "max_pain_distance": [options_data.get("max_pain_distance", np.nan)],
    })


def compute_filing_features(symbol: str, filing_data: dict) -> pd.DataFrame:
    """Compute SEC filing features."""
    # Placeholder - actual implementation in sec_filings.py
    return pd.DataFrame({
        "filing_sentiment": [filing_data.get("sentiment", np.nan)],
        "risk_factor_count": [filing_data.get("risk_count", np.nan)],
        "sentiment_change": [filing_data.get("sentiment_change", np.nan)],
    })


# =============================================================================
# FEATURE REGISTRY
# =============================================================================

FEATURE_REGISTRY: dict[str, FeatureDefinition] = {}


def register_feature(definition: FeatureDefinition):
    """Register a feature definition."""
    FEATURE_REGISTRY[definition.name] = definition
    return definition


# -----------------------------------------------------------------------------
# TECHNICAL FEATURES (20+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="returns",
    description="Simple returns over multiple periods",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_returns,
    output_columns=["return_1d", "return_5d", "return_10d", "return_20d", "return_60d"],
    lookback_days=60,
))

register_feature(FeatureDefinition(
    name="volatility",
    description="Rolling volatility (annualized std of returns)",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_volatility,
    output_columns=["volatility_5d", "volatility_10d", "volatility_20d", "volatility_60d"],
    lookback_days=60,
))

register_feature(FeatureDefinition(
    name="momentum",
    description="Price momentum with percentile ranks",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_momentum,
    output_columns=["momentum_5d", "momentum_10d", "momentum_20d", "momentum_60d"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="rsi",
    description="Relative Strength Index for multiple periods",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_rsi,
    output_columns=["rsi_7", "rsi_14", "rsi_21"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="bollinger_bands",
    description="Bollinger Bands with position and width",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_bollinger,
    default_params={"period": 20, "num_std": 2.0},
    output_columns=["bb_upper", "bb_lower", "bb_middle", "bb_width", "bb_position"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="macd",
    description="MACD line, signal, and histogram",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_macd,
    default_params={"fast": 12, "slow": 26, "signal": 9},
    output_columns=["macd_line", "macd_signal", "macd_histogram"],
    lookback_days=40,
))

register_feature(FeatureDefinition(
    name="atr",
    description="Average True Range for volatility",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_atr,
    default_params={"period": 14},
    output_columns=["atr", "atr_pct"],
    lookback_days=20,
))

register_feature(FeatureDefinition(
    name="volume_features",
    description="Volume-based indicators (OBV, VPT, volume ratio)",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.VOLUME_YAHOO],
    compute_fn=compute_volume_features,
    output_columns=["volume_sma_20", "volume_ratio", "obv", "obv_momentum", "vpt"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="price_patterns",
    description="Candlestick patterns and gaps",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_price_patterns,
    output_columns=["candle_body", "is_doji", "is_hammer", "gap_up", "gap_down", "gap_size"],
    lookback_days=25,
))

register_feature(FeatureDefinition(
    name="trend_features",
    description="Trend direction and strength (ADX, moving averages)",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_trend_features,
    output_columns=["sma_20", "sma_50", "sma_200", "trend_20d", "adx", "higher_high_5d"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="mean_reversion",
    description="Z-scores and distance from extremes",
    category=FeatureCategory.TECHNICAL,
    data_sources=[DataSource.PRICE_YAHOO],
    compute_fn=compute_mean_reversion_features,
    output_columns=["zscore_20d", "zscore_50d", "dist_from_52w_high", "price_percentile_252d"],
    lookback_days=252,
))

# -----------------------------------------------------------------------------
# SENTIMENT FEATURES (10+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="news_sentiment",
    description="Sentiment from news articles (FinBERT)",
    category=FeatureCategory.SENTIMENT,
    data_sources=[DataSource.NEWS_RSS, DataSource.NEWS_API],
    output_columns=["news_sentiment", "news_sentiment_5d_avg", "news_volume"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="social_sentiment",
    description="Sentiment from social media (Reddit, StockTwits)",
    category=FeatureCategory.SENTIMENT,
    data_sources=[DataSource.REDDIT, DataSource.STOCKTWITS],
    output_columns=["social_sentiment", "social_momentum", "mention_velocity"],
    lookback_days=7,
))

register_feature(FeatureDefinition(
    name="sentiment_divergence",
    description="Divergence between price and sentiment",
    category=FeatureCategory.SENTIMENT,
    data_sources=[DataSource.NEWS_RSS, DataSource.PRICE_YAHOO],
    dependencies=["news_sentiment", "returns"],
    output_columns=["sentiment_price_divergence", "sentiment_extreme"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="retail_institutional_gap",
    description="Sentiment gap between retail and institutional sources",
    category=FeatureCategory.SENTIMENT,
    data_sources=[DataSource.NEWS_RSS, DataSource.REDDIT],
    output_columns=["retail_sentiment", "institutional_sentiment", "sentiment_gap"],
    lookback_days=14,
))

# -----------------------------------------------------------------------------
# SEC FILING FEATURES (10+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="filing_sentiment_10k",
    description="Sentiment from most recent 10-K filing",
    category=FeatureCategory.ALTERNATIVE,
    data_sources=[DataSource.SEC_FILINGS],
    output_columns=["filing_sentiment", "risk_factor_sentiment", "mda_sentiment"],
    lookback_days=365,
))

register_feature(FeatureDefinition(
    name="filing_sentiment_change",
    description="Change in filing sentiment vs prior period",
    category=FeatureCategory.ALTERNATIVE,
    data_sources=[DataSource.SEC_FILINGS],
    output_columns=["sentiment_change_yoy", "risk_tone_change"],
    lookback_days=730,
))

register_feature(FeatureDefinition(
    name="risk_factor_count",
    description="Number of risk factors in latest filing",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.SEC_FILINGS],
    output_columns=["risk_factor_count", "new_risks", "removed_risks"],
    lookback_days=365,
))

register_feature(FeatureDefinition(
    name="mda_tone",
    description="Management Discussion & Analysis tone",
    category=FeatureCategory.ALTERNATIVE,
    data_sources=[DataSource.SEC_FILINGS],
    output_columns=["mda_positivity", "mda_uncertainty", "mda_litigiousness"],
    lookback_days=365,
))

register_feature(FeatureDefinition(
    name="accounting_complexity",
    description="Complexity and readability of financial notes",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.SEC_FILINGS],
    output_columns=["fog_index", "word_count", "complex_word_pct"],
    lookback_days=365,
))

# -----------------------------------------------------------------------------
# EMBEDDING FEATURES (5+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="narrative_centroid_distance",
    description="Distance from 30-day news narrative centroid",
    category=FeatureCategory.EMBEDDING,
    data_sources=[DataSource.NEWS_RSS],
    output_columns=["narrative_distance", "narrative_velocity"],
    lookback_days=60,
))

register_feature(FeatureDefinition(
    name="topic_concentration",
    description="How focused is news coverage",
    category=FeatureCategory.EMBEDDING,
    data_sources=[DataSource.NEWS_RSS],
    output_columns=["topic_concentration", "dominant_topic", "topic_entropy"],
    lookback_days=30,
))

register_feature(FeatureDefinition(
    name="topic_emergence",
    description="Detection of newly emerging topics",
    category=FeatureCategory.EMBEDDING,
    data_sources=[DataSource.NEWS_RSS],
    output_columns=["emerging_topic_score", "topic_novelty"],
    lookback_days=14,
))

register_feature(FeatureDefinition(
    name="peer_narrative_similarity",
    description="Similarity of narrative to peer companies",
    category=FeatureCategory.EMBEDDING,
    data_sources=[DataSource.NEWS_RSS],
    output_columns=["peer_narrative_similarity", "narrative_uniqueness"],
    lookback_days=30,
))

# -----------------------------------------------------------------------------
# FLOW FEATURES (5+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="options_put_call",
    description="Put/call ratio from options market",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.OPTIONS_FLOW],
    output_columns=["put_call_ratio", "put_call_oi_ratio", "options_signal"],
    lookback_days=1,
    is_realtime=True,
))

register_feature(FeatureDefinition(
    name="options_iv_skew",
    description="Implied volatility skew (put vs call IV)",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.OPTIONS_FLOW],
    output_columns=["iv_skew", "iv_term_structure"],
    lookback_days=1,
    is_realtime=True,
))

register_feature(FeatureDefinition(
    name="max_pain_distance",
    description="Distance from options max pain strike",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.OPTIONS_FLOW],
    output_columns=["max_pain", "max_pain_distance_pct"],
    lookback_days=1,
    is_realtime=True,
))

register_feature(FeatureDefinition(
    name="etf_sector_flows",
    description="Sector ETF flow estimates",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.ETF_FLOWS],
    output_columns=["sector_flow_20d", "sector_flow_rank", "sector_momentum"],
    lookback_days=20,
))

register_feature(FeatureDefinition(
    name="insider_activity",
    description="Recent insider trading activity",
    category=FeatureCategory.FLOW,
    data_sources=[DataSource.INSIDER_SEC],
    output_columns=["insider_buy_ratio", "insider_net_shares", "insider_signal"],
    lookback_days=90,
))

# -----------------------------------------------------------------------------
# RISK FEATURES (5+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="beta",
    description="Beta relative to market (SPY)",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.PRICE_YAHOO],
    default_params={"lookback": 252},
    output_columns=["beta_252d", "beta_60d"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="drawdown",
    description="Current and max drawdown metrics",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.PRICE_YAHOO],
    output_columns=["current_drawdown", "max_drawdown_60d", "days_since_high"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="tail_risk",
    description="Tail risk metrics (VaR, expected shortfall)",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.PRICE_YAHOO],
    output_columns=["var_5pct", "expected_shortfall", "skewness", "kurtosis"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="correlation_to_market",
    description="Rolling correlation to SPY",
    category=FeatureCategory.RISK,
    data_sources=[DataSource.PRICE_YAHOO],
    output_columns=["corr_spy_20d", "corr_spy_60d", "corr_change"],
    lookback_days=60,
))

# -----------------------------------------------------------------------------
# REGIME FEATURES (5+)
# -----------------------------------------------------------------------------

register_feature(FeatureDefinition(
    name="market_regime",
    description="Current market regime (trending/mean-reverting/volatile)",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO, DataSource.FRED_ECONOMIC],
    output_columns=["regime", "regime_confidence", "regime_duration"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="volatility_regime",
    description="Volatility regime (low/normal/high/crisis)",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.PRICE_YAHOO],
    output_columns=["vol_regime", "vol_percentile", "vol_regime_change"],
    lookback_days=252,
))

register_feature(FeatureDefinition(
    name="earnings_proximity",
    description="Proximity to earnings announcement",
    category=FeatureCategory.REGIME,
    data_sources=[DataSource.EARNINGS_CALENDAR],
    output_columns=["days_to_earnings", "days_since_earnings", "is_earnings_window"],
    lookback_days=90,
))


# =============================================================================
# FEATURE COMPUTER
# =============================================================================

class FeatureComputer:
    """Compute features from registry definitions."""

    def __init__(self):
        self.registry = FEATURE_REGISTRY

    def compute_feature(
        self,
        feature_name: str,
        df: pd.DataFrame,
        **params,
    ) -> pd.DataFrame:
        """Compute a single feature."""
        if feature_name not in self.registry:
            raise ValueError(f"Unknown feature: {feature_name}")

        definition = self.registry[feature_name]

        if definition.compute_fn is None:
            raise ValueError(f"No compute function for: {feature_name}")

        # Merge default params with provided params
        compute_params = {**definition.default_params, **params}

        # Call compute function
        return definition.compute_fn(df, **compute_params)

    def compute_all_technical(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all technical features."""
        result = pd.DataFrame(index=df.index)

        for name, definition in self.registry.items():
            if definition.category == FeatureCategory.TECHNICAL:
                if definition.compute_fn is not None:
                    try:
                        features = definition.compute_fn(df)
                        result = pd.concat([result, features], axis=1)
                    except Exception as e:
                        logger.warning(f"Failed to compute {name}: {e}")

        return result

    def get_dependency_order(self, features: list[str]) -> list[str]:
        """Topological sort of feature dependencies."""
        from collections import defaultdict, deque

        # Build dependency graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)

        for feature in features:
            if feature in self.registry:
                for dep in self.registry[feature].dependencies:
                    graph[dep].append(feature)
                    in_degree[feature] += 1

        # Topological sort (Kahn's algorithm)
        queue = deque([f for f in features if in_degree[f] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_feature_definition(name: str) -> Optional[FeatureDefinition]:
    """Get a feature definition by name."""
    return FEATURE_REGISTRY.get(name)


def list_features_by_category(category: FeatureCategory) -> list[str]:
    """List all features in a category."""
    return [
        name for name, defn in FEATURE_REGISTRY.items()
        if defn.category == category
    ]


def list_features_by_data_source(source: DataSource) -> list[str]:
    """List all features that use a data source."""
    return [
        name for name, defn in FEATURE_REGISTRY.items()
        if source in defn.data_sources
    ]


def get_all_feature_names() -> list[str]:
    """Get all registered feature names."""
    return list(FEATURE_REGISTRY.keys())


def get_registry_summary() -> dict:
    """Get summary of feature registry."""
    by_category = {}
    for category in FeatureCategory:
        features = list_features_by_category(category)
        by_category[category.value] = len(features)

    return {
        "total_features": len(FEATURE_REGISTRY),
        "by_category": by_category,
        "feature_names": get_all_feature_names(),
    }
