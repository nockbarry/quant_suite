"""Data source adapters."""

from .alternative import (
    AGRICULTURAL_REGIONS,
    MAJOR_LOCATIONS,
    LocationConfig,
    NewsArticle,
    NewsDataSource,
    NewsSourceConfig,
    RSSNewsSource,
    WeatherData,
    WeatherDataSource,
    WeatherFeatureEngine,
    extract_symbols_from_text,
    get_sector_locations,
)
from .base import (
    DataSource,
    DataSourceError,
    DataUnavailableError,
    RateLimitError,
    SymbolNotFoundError,
)
from .yahoo import YahooFinanceSource

__all__ = [
    # Base
    "DataSource",
    "DataSourceError",
    "DataUnavailableError",
    "RateLimitError",
    "SymbolNotFoundError",
    # Yahoo
    "YahooFinanceSource",
    # News
    "NewsArticle",
    "NewsSourceConfig",
    "NewsDataSource",
    "RSSNewsSource",
    "extract_symbols_from_text",
    # Weather
    "WeatherData",
    "LocationConfig",
    "WeatherDataSource",
    "WeatherFeatureEngine",
    "MAJOR_LOCATIONS",
    "AGRICULTURAL_REGIONS",
    "get_sector_locations",
]
