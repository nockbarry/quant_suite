"""Data layer for the quant suite."""

from .features import FeatureEngine
from .loaders import (
    DatasetBuilder,
    PurgedKFold,
    TimeSeriesDataset,
    WalkForwardSplitter,
)
from .pipeline import DataPipeline
from .sources import (
    AGRICULTURAL_REGIONS,
    MAJOR_LOCATIONS,
    DataSource,
    DataSourceError,
    DataUnavailableError,
    LocationConfig,
    NewsArticle,
    NewsDataSource,
    NewsSourceConfig,
    RateLimitError,
    RSSNewsSource,
    SymbolNotFoundError,
    WeatherData,
    WeatherDataSource,
    WeatherFeatureEngine,
    YahooFinanceSource,
    extract_symbols_from_text,
    get_sector_locations,
)
from .storage import (
    DataNotFoundError,
    EmbeddingDocument,
    EmbeddingModel,
    FeatureMetadata,
    FeatureStore,
    NewsVectorStore,
    ParquetStorage,
    SearchResult,
    Storage,
    StorageError,
    VectorStore,
    batch_embed_texts,
    compute_text_similarity,
)

__all__ = [
    # Pipeline
    "DataPipeline",
    # Features
    "FeatureEngine",
    # Loaders
    "DatasetBuilder",
    "TimeSeriesDataset",
    "WalkForwardSplitter",
    "PurgedKFold",
    # Sources - Base
    "DataSource",
    "DataSourceError",
    "DataUnavailableError",
    "RateLimitError",
    "SymbolNotFoundError",
    "YahooFinanceSource",
    # Sources - News
    "NewsArticle",
    "NewsSourceConfig",
    "NewsDataSource",
    "RSSNewsSource",
    "extract_symbols_from_text",
    # Sources - Weather
    "WeatherData",
    "LocationConfig",
    "WeatherDataSource",
    "WeatherFeatureEngine",
    "MAJOR_LOCATIONS",
    "AGRICULTURAL_REGIONS",
    "get_sector_locations",
    # Storage - Base
    "Storage",
    "StorageError",
    "DataNotFoundError",
    "ParquetStorage",
    # Storage - Feature Store
    "FeatureStore",
    "FeatureMetadata",
    # Storage - Vector
    "EmbeddingDocument",
    "EmbeddingModel",
    "VectorStore",
    "NewsVectorStore",
    "SearchResult",
    "compute_text_similarity",
    "batch_embed_texts",
]
