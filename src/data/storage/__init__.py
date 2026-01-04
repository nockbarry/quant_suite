"""Data storage backends."""

from .base import DataNotFoundError, Storage, StorageError, ensure_directory
from .feature_store import FeatureMetadata, FeatureStore
from .parquet import ParquetStorage
from .vector_store import (
    EmbeddingDocument,
    EmbeddingModel,
    NewsVectorStore,
    SearchResult,
    VectorStore,
    batch_embed_texts,
    compute_text_similarity,
)

__all__ = [
    # Base
    "Storage",
    "StorageError",
    "DataNotFoundError",
    "ensure_directory",
    # Feature Store
    "FeatureStore",
    "FeatureMetadata",
    # Parquet
    "ParquetStorage",
    # Vector Store
    "EmbeddingDocument",
    "EmbeddingModel",
    "VectorStore",
    "NewsVectorStore",
    "SearchResult",
    "compute_text_similarity",
    "batch_embed_texts",
]
