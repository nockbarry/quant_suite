"""
Document Embeddings with ChromaDB

Generate and store document embeddings for semantic search and analysis:
- Embed documents using sentence-transformers
- Store in ChromaDB vector database
- Find similar documents
- Track narrative shifts over time
- Cluster documents by topic
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Document:
    """A document for embedding."""
    id: str
    text: str
    symbol: Optional[str] = None
    source: str = ""  # news, sec_filing, social, etc.
    published_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SimilarDocument:
    """A similar document from search."""
    document: Document
    similarity: float
    distance: float


@dataclass
class NarrativeShift:
    """Analysis of narrative shift over time."""
    symbol: str
    current_centroid: np.ndarray
    previous_centroid: np.ndarray
    shift_magnitude: float
    shift_direction: np.ndarray
    dominant_topics: list
    window_days: int


# =============================================================================
# DOCUMENT EMBEDDER
# =============================================================================

class DocumentEmbedder:
    """
    Generate and store document embeddings in ChromaDB.

    Usage:
        embedder = DocumentEmbedder()

        # Embed and store
        doc = Document(id="news_123", text="Apple beats earnings...", symbol="AAPL")
        embedder.embed_and_store(doc)

        # Find similar
        results = embedder.find_similar("tech earnings surprise", top_k=10)

        # Track narrative shift
        shift = embedder.track_narrative_shift("AAPL", window_days=30)
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    COLLECTION_NAME = "quant_documents"

    def __init__(
        self,
        model_name: str = None,
        persist_dir: Optional[Path] = None,
    ):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.persist_dir = persist_dir or Path.home() / ".quant_cache" / "embeddings"
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._model = None
        self._client = None
        self._collection = None

    @property
    def model(self):
        """Lazy load embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model: {self.model_name}")
            except ImportError:
                logger.warning("sentence-transformers not installed, using fallback")
                self._model = FallbackEmbedder()
        return self._model

    @property
    def client(self):
        """Lazy load ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.Client(Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=str(self.persist_dir),
                    anonymized_telemetry=False,
                ))
                logger.info(f"Initialized ChromaDB at {self.persist_dir}")
            except ImportError:
                logger.warning("chromadb not installed, using in-memory fallback")
                self._client = InMemoryVectorStore()
        return self._client

    @property
    def collection(self):
        """Get or create the document collection."""
        if self._collection is None:
            if hasattr(self.client, 'get_or_create_collection'):
                self._collection = self.client.get_or_create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "Quant suite document embeddings"},
                )
            else:
                self._collection = self.client
        return self._collection

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text."""
        if hasattr(self.model, 'encode'):
            return self.model.encode(text, convert_to_numpy=True)
        else:
            return self.model.embed(text)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for multiple texts."""
        if hasattr(self.model, 'encode'):
            return self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        else:
            return np.array([self.model.embed(t) for t in texts])

    def embed_and_store(
        self,
        doc: Document,
        embedding: Optional[np.ndarray] = None,
    ):
        """
        Embed document and store in vector database.

        Args:
            doc: Document to embed and store
            embedding: Pre-computed embedding (optional)
        """
        if embedding is None:
            embedding = self.embed(doc.text)

        metadata = {
            "symbol": doc.symbol or "",
            "source": doc.source,
            "published_at": doc.published_at.isoformat() if doc.published_at else "",
            **doc.metadata,
        }

        # Check if it's ChromaDB collection vs our fallback
        if isinstance(self.collection, InMemoryVectorStore):
            self.collection.add(doc.id, embedding, doc.text, metadata)
        else:
            # ChromaDB-style API
            self.collection.add(
                ids=[doc.id],
                embeddings=[embedding.tolist()],
                documents=[doc.text],
                metadatas=[metadata],
            )

        logger.debug(f"Stored document: {doc.id}")

    def embed_and_store_batch(self, docs: list[Document]):
        """Embed and store multiple documents."""
        if not docs:
            return

        texts = [d.text for d in docs]
        embeddings = self.embed_batch(texts)

        for doc, embedding in zip(docs, embeddings):
            self.embed_and_store(doc, embedding)

        logger.info(f"Stored {len(docs)} documents")

    def find_similar(
        self,
        query: str,
        top_k: int = 10,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        min_date: Optional[datetime] = None,
    ) -> list[SimilarDocument]:
        """
        Find documents similar to query.

        Args:
            query: Query text
            top_k: Number of results to return
            symbol: Filter by symbol
            source: Filter by source
            min_date: Filter by minimum date

        Returns:
            List of similar documents with scores
        """
        query_embedding = self.embed(query)

        # Build filter
        where_filter = {}
        if symbol:
            where_filter["symbol"] = symbol
        if source:
            where_filter["source"] = source

        # Query ChromaDB
        if hasattr(self.collection, 'query'):
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=top_k,
                where=where_filter if where_filter else None,
            )

            similar_docs = []
            for i, doc_id in enumerate(results["ids"][0]):
                doc = Document(
                    id=doc_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    symbol=results["metadatas"][0][i].get("symbol"),
                    source=results["metadatas"][0][i].get("source", ""),
                    metadata=results["metadatas"][0][i],
                )

                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 - distance  # Convert distance to similarity

                similar_docs.append(SimilarDocument(
                    document=doc,
                    similarity=similarity,
                    distance=distance,
                ))

            return similar_docs

        else:
            # Fallback
            return self.collection.search(query_embedding, top_k)

    def get_symbol_embeddings(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[Document], np.ndarray]:
        """Get all embeddings for a symbol in a date range."""
        # Query all documents for symbol
        if hasattr(self.collection, 'get'):
            results = self.collection.get(
                where={"symbol": symbol},
                include=["documents", "embeddings", "metadatas"],
            )

            docs = []
            embeddings = []

            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                published_at_str = metadata.get("published_at", "")

                if published_at_str:
                    try:
                        published_at = datetime.fromisoformat(published_at_str)
                        if start_date and published_at < start_date:
                            continue
                        if end_date and published_at > end_date:
                            continue
                    except ValueError:
                        pass

                doc = Document(
                    id=doc_id,
                    text=results["documents"][i] if results["documents"] else "",
                    symbol=symbol,
                    metadata=metadata,
                )
                docs.append(doc)

                if results["embeddings"]:
                    embeddings.append(results["embeddings"][i])

            return docs, np.array(embeddings) if embeddings else np.array([])

        return [], np.array([])

    def track_narrative_shift(
        self,
        symbol: str,
        window_days: int = 30,
        comparison_window_days: int = 30,
    ) -> NarrativeShift:
        """
        Track how the narrative around a symbol has shifted.

        Args:
            symbol: Stock symbol
            window_days: Current window to analyze
            comparison_window_days: Previous window for comparison

        Returns:
            NarrativeShift with analysis
        """
        now = datetime.now()
        current_start = now - timedelta(days=window_days)
        previous_start = current_start - timedelta(days=comparison_window_days)

        # Get embeddings for each window
        current_docs, current_embeddings = self.get_symbol_embeddings(
            symbol, start_date=current_start, end_date=now
        )
        previous_docs, previous_embeddings = self.get_symbol_embeddings(
            symbol, start_date=previous_start, end_date=current_start
        )

        # Compute centroids
        if len(current_embeddings) > 0:
            current_centroid = np.mean(current_embeddings, axis=0)
        else:
            current_centroid = np.zeros(384)  # Default embedding size

        if len(previous_embeddings) > 0:
            previous_centroid = np.mean(previous_embeddings, axis=0)
        else:
            previous_centroid = np.zeros(384)

        # Compute shift
        shift_direction = current_centroid - previous_centroid
        shift_magnitude = float(np.linalg.norm(shift_direction))

        # Normalize direction
        if shift_magnitude > 0:
            shift_direction = shift_direction / shift_magnitude

        # Find dominant topics (simplified - cluster current embeddings)
        dominant_topics = self._extract_dominant_topics(current_docs)

        return NarrativeShift(
            symbol=symbol,
            current_centroid=current_centroid,
            previous_centroid=previous_centroid,
            shift_magnitude=shift_magnitude,
            shift_direction=shift_direction,
            dominant_topics=dominant_topics,
            window_days=window_days,
        )

    def _extract_dominant_topics(self, docs: list[Document], top_k: int = 5) -> list[str]:
        """Extract dominant topics from documents (simple keyword extraction)."""
        if not docs:
            return []

        # Simple word frequency approach
        from collections import Counter
        import re

        all_words = []
        for doc in docs:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', doc.text.lower())
            all_words.extend(words)

        # Remove common stopwords
        stopwords = {
            "that", "this", "with", "have", "from", "will", "been", "were", "more",
            "their", "other", "which", "about", "would", "there", "could", "should",
            "when", "what", "than", "into", "some", "also", "these", "after", "most",
            "over", "such", "only", "being", "before", "between", "each", "under",
        }

        word_counts = Counter(w for w in all_words if w not in stopwords)
        return [word for word, count in word_counts.most_common(top_k)]

    def cluster_documents(
        self,
        docs: list[Document],
        n_clusters: int = 5,
    ) -> dict[int, list[Document]]:
        """
        Cluster documents by semantic similarity.

        Args:
            docs: Documents to cluster
            n_clusters: Number of clusters

        Returns:
            Dict mapping cluster ID to documents
        """
        if len(docs) < n_clusters:
            return {0: docs}

        embeddings = self.embed_batch([d.text for d in docs])

        try:
            from sklearn.cluster import KMeans

            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            labels = kmeans.fit_predict(embeddings)

            clusters = {}
            for doc, label in zip(docs, labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(doc)

            return clusters

        except ImportError:
            logger.warning("sklearn not installed, returning all docs in one cluster")
            return {0: docs}

    def compute_narrative_velocity(
        self,
        symbol: str,
        lookback_days: int = 60,
        window_size: int = 7,
    ) -> pd.Series:
        """
        Compute how fast the narrative is changing over time.

        Args:
            symbol: Stock symbol
            lookback_days: Total lookback period
            window_size: Rolling window for velocity calculation

        Returns:
            Series with daily narrative velocity
        """
        now = datetime.now()
        start = now - timedelta(days=lookback_days)

        docs, embeddings = self.get_symbol_embeddings(symbol, start_date=start)

        if len(docs) < 2:
            return pd.Series(dtype=float)

        # Group by date
        doc_dates = []
        for doc in docs:
            if doc.metadata.get("published_at"):
                try:
                    date = datetime.fromisoformat(doc.metadata["published_at"]).date()
                    doc_dates.append(date)
                except ValueError:
                    doc_dates.append(now.date())
            else:
                doc_dates.append(now.date())

        # Compute daily centroids
        daily_centroids = {}
        for date, embedding in zip(doc_dates, embeddings):
            if date not in daily_centroids:
                daily_centroids[date] = []
            daily_centroids[date].append(embedding)

        for date in daily_centroids:
            daily_centroids[date] = np.mean(daily_centroids[date], axis=0)

        # Compute velocity (distance between consecutive centroids)
        dates = sorted(daily_centroids.keys())
        velocities = {}

        for i in range(1, len(dates)):
            prev = daily_centroids[dates[i - 1]]
            curr = daily_centroids[dates[i]]
            velocity = float(np.linalg.norm(curr - prev))
            velocities[dates[i]] = velocity

        return pd.Series(velocities)


# =============================================================================
# FALLBACK IMPLEMENTATIONS
# =============================================================================

class FallbackEmbedder:
    """Simple TF-IDF based fallback embedder."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD

            self.vectorizer = TfidfVectorizer(max_features=10000)
            self.svd = TruncatedSVD(n_components=dim)
            self._fitted = False
        except ImportError:
            self.vectorizer = None
            self.svd = None

    def embed(self, text: str) -> np.ndarray:
        """Generate embedding using hash-based approach."""
        # Simple hash-based embedding as ultimate fallback
        h = hashlib.sha256(text.encode()).digest()
        embedding = np.array([b / 255.0 for b in h[:self.dim // 8]])

        # Pad or truncate to desired dimension
        if len(embedding) < self.dim:
            embedding = np.pad(embedding, (0, self.dim - len(embedding)))
        else:
            embedding = embedding[:self.dim]

        return embedding


class InMemoryVectorStore:
    """Simple in-memory vector store fallback."""

    def __init__(self):
        self.documents = {}
        self.embeddings = {}
        self.metadatas = {}

    def add(self, doc_id: str, embedding: np.ndarray, text: str, metadata: dict):
        """Add document to store."""
        self.documents[doc_id] = text
        self.embeddings[doc_id] = embedding
        self.metadatas[doc_id] = metadata

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> list[SimilarDocument]:
        """Search for similar documents."""
        if not self.embeddings:
            return []

        # Compute similarities
        similarities = []
        for doc_id, embedding in self.embeddings.items():
            similarity = float(np.dot(query_embedding, embedding) /
                             (np.linalg.norm(query_embedding) * np.linalg.norm(embedding)))
            similarities.append((doc_id, similarity))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, similarity in similarities[:top_k]:
            doc = Document(
                id=doc_id,
                text=self.documents[doc_id],
                metadata=self.metadatas[doc_id],
            )
            results.append(SimilarDocument(
                document=doc,
                similarity=similarity,
                distance=1 - similarity,
            ))

        return results

    def get(self, where: dict = None, include: list = None) -> dict:
        """Get documents matching filter."""
        ids = []
        documents = []
        embeddings = []
        metadatas = []

        for doc_id, metadata in self.metadatas.items():
            if where:
                match = all(metadata.get(k) == v for k, v in where.items())
                if not match:
                    continue

            ids.append(doc_id)
            documents.append(self.documents[doc_id])
            embeddings.append(self.embeddings[doc_id])
            metadatas.append(metadata)

        return {
            "ids": ids,
            "documents": documents,
            "embeddings": embeddings,
            "metadatas": metadatas,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_embedder: Optional[DocumentEmbedder] = None


def get_embedder() -> DocumentEmbedder:
    """Get global DocumentEmbedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = DocumentEmbedder()
    return _embedder


def embed_text(text: str) -> np.ndarray:
    """Quick embedding of text."""
    return get_embedder().embed(text)


def find_similar_documents(query: str, top_k: int = 10) -> list[SimilarDocument]:
    """Quick similarity search."""
    return get_embedder().find_similar(query, top_k)
