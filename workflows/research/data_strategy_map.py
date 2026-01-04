"""
Data-Strategy Mapping

Maps data sources to strategies that use them, and vice versa.
Helps ensure we have the right data for strategies and know
which strategies become available when data sources are added.

Usage:
    # What strategies can we run with options data?
    strategies = get_strategies_for_data('options')

    # What data does momentum_20d need?
    requirements = get_data_requirements('momentum_20d')

    # Can we run this strategy now?
    check = check_data_availability('options_flow_momentum')
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataSource(str, Enum):
    """Available data sources."""

    # Core price data
    PRICE_YAHOO = "price_yahoo"

    # Economic data
    FRED_ECONOMIC = "fred_economic"

    # Alternative data
    INSIDER_SEC = "insider_sec"
    SENTIMENT_NEWS = "sentiment_news"
    SENTIMENT_REDDIT = "sentiment_reddit"
    OPTIONS_FLOW = "options_flow"
    ETF_FLOWS = "etf_flows"

    # Specialized
    CRYPTO = "crypto"
    WEATHER = "weather"


@dataclass
class DataSourceInfo:
    """Information about a data source."""

    source: DataSource
    name: str
    is_available: bool
    requires_api_key: bool
    provider: str
    update_frequency: str
    notes: str = ""


# Data source availability and details
DATA_SOURCES = {
    DataSource.PRICE_YAHOO: DataSourceInfo(
        source=DataSource.PRICE_YAHOO,
        name="Yahoo Finance Price Data",
        is_available=True,
        requires_api_key=False,
        provider="yfinance",
        update_frequency="real-time (delayed)",
    ),
    DataSource.FRED_ECONOMIC: DataSourceInfo(
        source=DataSource.FRED_ECONOMIC,
        name="FRED Economic Data",
        is_available=True,
        requires_api_key=False,  # Free API key available
        provider="fredapi",
        update_frequency="daily/weekly/monthly",
    ),
    DataSource.INSIDER_SEC: DataSourceInfo(
        source=DataSource.INSIDER_SEC,
        name="SEC Insider Trading",
        is_available=True,
        requires_api_key=False,
        provider="EdgarTools/simulation",
        update_frequency="daily",
    ),
    DataSource.SENTIMENT_NEWS: DataSourceInfo(
        source=DataSource.SENTIMENT_NEWS,
        name="News Sentiment",
        is_available=True,
        requires_api_key=False,  # Uses RSS feeds
        provider="RSS + FinBERT",
        update_frequency="continuous",
        notes="Full API access requires NewsAPI key",
    ),
    DataSource.SENTIMENT_REDDIT: DataSourceInfo(
        source=DataSource.SENTIMENT_REDDIT,
        name="Reddit Sentiment",
        is_available=False,
        requires_api_key=True,
        provider="Reddit API",
        update_frequency="continuous",
        notes="Requires Reddit API credentials",
    ),
    DataSource.OPTIONS_FLOW: DataSourceInfo(
        source=DataSource.OPTIONS_FLOW,
        name="Options Flow",
        is_available=True,
        requires_api_key=False,  # Yahoo Finance fallback
        provider="Yahoo Finance / Tradier / Polygon",
        update_frequency="daily",
        notes="Full flow data requires paid API",
    ),
    DataSource.ETF_FLOWS: DataSourceInfo(
        source=DataSource.ETF_FLOWS,
        name="ETF Flows",
        is_available=True,
        requires_api_key=False,  # Yahoo Finance fallback
        provider="Yahoo Finance / Polygon",
        update_frequency="daily",
        notes="Estimated from volume patterns",
    ),
    DataSource.CRYPTO: DataSourceInfo(
        source=DataSource.CRYPTO,
        name="Cryptocurrency Data",
        is_available=True,
        requires_api_key=False,
        provider="CoinGecko / Yahoo",
        update_frequency="real-time",
    ),
    DataSource.WEATHER: DataSourceInfo(
        source=DataSource.WEATHER,
        name="Weather Data",
        is_available=False,
        requires_api_key=True,
        provider="OpenWeatherMap",
        update_frequency="hourly",
        notes="Requires API key",
    ),
}


# Map data sources to strategies that use them
DATA_TO_STRATEGIES = {
    DataSource.PRICE_YAHOO: [
        # Traditional strategies
        "sma_crossover",
        "ema_crossover",
        "macd",
        "rsi_momentum",
        "rsi_reversal",
        "bollinger_breakout",
        "bollinger_reversal",
        "momentum_20d",
        "momentum_60d",
        "trend_breakout",
        "trend_sma_cross",
        "mean_reversion_rsi",
        "volatility_regime",
        # ML strategies (base features)
        "ml_xgboost",
        "ml_random_forest",
        "ml_ensemble",
        "ml_lstm",
        "ml_transformer",
    ],
    DataSource.FRED_ECONOMIC: [
        "regime_adaptive",
        "macro_momentum",
    ],
    DataSource.INSIDER_SEC: [
        "insider_momentum",
        "insider_value",
        "multi_signal",
    ],
    DataSource.SENTIMENT_NEWS: [
        "sentiment_momentum",
        "sentiment_reversal",
        "multi_signal",
    ],
    DataSource.SENTIMENT_REDDIT: [
        "reddit_sentiment",
        "wsb_momentum",
    ],
    DataSource.OPTIONS_FLOW: [
        "options_flow_momentum",
        "put_call_contrarian",
        "max_pain_magnet",
        "gamma_exposure",
    ],
    DataSource.ETF_FLOWS: [
        "sector_rotation",
        "flow_momentum",
        "risk_on_off",
    ],
    DataSource.CRYPTO: [
        "crypto_momentum",
        "crypto_mean_reversion",
    ],
    DataSource.WEATHER: [
        "weather_commodities",
    ],
}


# Map strategies to required data sources
STRATEGY_TO_DATA = {
    # Traditional (need only price)
    "sma_crossover": [DataSource.PRICE_YAHOO],
    "ema_crossover": [DataSource.PRICE_YAHOO],
    "macd": [DataSource.PRICE_YAHOO],
    "rsi_momentum": [DataSource.PRICE_YAHOO],
    "rsi_reversal": [DataSource.PRICE_YAHOO],
    "bollinger_breakout": [DataSource.PRICE_YAHOO],
    "bollinger_reversal": [DataSource.PRICE_YAHOO],
    "momentum_20d": [DataSource.PRICE_YAHOO],
    "momentum_60d": [DataSource.PRICE_YAHOO],
    "trend_breakout": [DataSource.PRICE_YAHOO],
    "trend_sma_cross": [DataSource.PRICE_YAHOO],
    "mean_reversion_rsi": [DataSource.PRICE_YAHOO],
    "volatility_regime": [DataSource.PRICE_YAHOO],

    # ML (need price, optional alternatives)
    "ml_xgboost": [DataSource.PRICE_YAHOO],
    "ml_random_forest": [DataSource.PRICE_YAHOO],
    "ml_ensemble": [DataSource.PRICE_YAHOO],
    "ml_lstm": [DataSource.PRICE_YAHOO],
    "ml_transformer": [DataSource.PRICE_YAHOO],

    # Alternative data strategies
    "regime_adaptive": [DataSource.PRICE_YAHOO, DataSource.FRED_ECONOMIC],
    "insider_momentum": [DataSource.PRICE_YAHOO, DataSource.INSIDER_SEC],
    "insider_value": [DataSource.PRICE_YAHOO, DataSource.INSIDER_SEC],
    "sentiment_momentum": [DataSource.PRICE_YAHOO, DataSource.SENTIMENT_NEWS],
    "sentiment_reversal": [DataSource.PRICE_YAHOO, DataSource.SENTIMENT_NEWS],
    "multi_signal": [
        DataSource.PRICE_YAHOO,
        DataSource.INSIDER_SEC,
        DataSource.SENTIMENT_NEWS,
    ],

    # Options strategies
    "options_flow_momentum": [DataSource.PRICE_YAHOO, DataSource.OPTIONS_FLOW],
    "put_call_contrarian": [DataSource.PRICE_YAHOO, DataSource.OPTIONS_FLOW],
    "max_pain_magnet": [DataSource.PRICE_YAHOO, DataSource.OPTIONS_FLOW],

    # ETF flow strategies
    "sector_rotation": [DataSource.PRICE_YAHOO, DataSource.ETF_FLOWS],
    "flow_momentum": [DataSource.PRICE_YAHOO, DataSource.ETF_FLOWS],
}


def get_strategies_for_data(data_source: str | DataSource) -> list[str]:
    """
    Get strategies that use a specific data source.

    Args:
        data_source: Data source name or enum

    Returns:
        List of strategy names
    """
    if isinstance(data_source, str):
        try:
            data_source = DataSource(data_source)
        except ValueError:
            # Try matching by partial name
            for ds in DataSource:
                if data_source.lower() in ds.value.lower():
                    data_source = ds
                    break
            else:
                return []

    return DATA_TO_STRATEGIES.get(data_source, [])


def get_data_requirements(strategy: str) -> list[DataSource]:
    """
    Get data sources required for a strategy.

    Args:
        strategy: Strategy name

    Returns:
        List of required DataSource enums
    """
    return STRATEGY_TO_DATA.get(strategy, [])


def check_data_availability(strategy: str) -> dict[str, Any]:
    """
    Check if we have the data to run a strategy.

    Args:
        strategy: Strategy name

    Returns:
        Dict with availability status and details
    """
    requirements = get_data_requirements(strategy)

    if not requirements:
        return {
            "can_run": False,
            "reason": f"Unknown strategy: {strategy}",
            "requirements": [],
            "missing": [],
        }

    available = []
    missing = []

    for req in requirements:
        info = DATA_SOURCES.get(req)
        if info and info.is_available:
            available.append(req.value)
        else:
            missing.append(req.value)

    can_run = len(missing) == 0

    return {
        "can_run": can_run,
        "requirements": [r.value for r in requirements],
        "available": available,
        "missing": missing,
        "reason": "All data available" if can_run else f"Missing: {', '.join(missing)}",
    }


def get_available_strategies() -> list[str]:
    """
    Get all strategies that can run with current data sources.

    Returns:
        List of strategy names
    """
    available = []

    for strategy in STRATEGY_TO_DATA.keys():
        check = check_data_availability(strategy)
        if check["can_run"]:
            available.append(strategy)

    return available


def get_unavailable_strategies() -> list[tuple[str, list[str]]]:
    """
    Get strategies that cannot run and what data they need.

    Returns:
        List of (strategy, missing_data) tuples
    """
    unavailable = []

    for strategy in STRATEGY_TO_DATA.keys():
        check = check_data_availability(strategy)
        if not check["can_run"]:
            unavailable.append((strategy, check["missing"]))

    return unavailable


def get_data_source_status() -> dict[str, dict]:
    """
    Get status of all data sources.

    Returns:
        Dict mapping source name to status info
    """
    return {
        source.value: {
            "name": info.name,
            "available": info.is_available,
            "requires_api_key": info.requires_api_key,
            "provider": info.provider,
            "update_frequency": info.update_frequency,
            "notes": info.notes,
            "strategies_count": len(DATA_TO_STRATEGIES.get(source, [])),
        }
        for source, info in DATA_SOURCES.items()
    }


def print_coverage_report() -> None:
    """Print a coverage report to console."""
    print("\n" + "=" * 60)
    print("DATA-STRATEGY COVERAGE REPORT")
    print("=" * 60)

    print("\nData Source Status:")
    print("-" * 40)
    for source, info in DATA_SOURCES.items():
        status = "AVAILABLE" if info.is_available else "NOT AVAILABLE"
        strategies = DATA_TO_STRATEGIES.get(source, [])
        print(f"  {info.name}")
        print(f"    Status: {status}")
        print(f"    Strategies enabled: {len(strategies)}")
        if info.notes:
            print(f"    Note: {info.notes}")
        print()

    available = get_available_strategies()
    unavailable = get_unavailable_strategies()

    print(f"\nStrategies Available: {len(available)}")
    for s in sorted(available)[:10]:
        print(f"  - {s}")
    if len(available) > 10:
        print(f"  ... and {len(available) - 10} more")

    print(f"\nStrategies Unavailable: {len(unavailable)}")
    for s, missing in unavailable[:5]:
        print(f"  - {s} (needs: {', '.join(missing)})")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    print_coverage_report()

    print("\n\nExample checks:")
    print("\nWhat strategies use options data?")
    for s in get_strategies_for_data("options"):
        print(f"  - {s}")

    print("\nCan we run 'put_call_contrarian'?")
    check = check_data_availability("put_call_contrarian")
    print(f"  {check['reason']}")
