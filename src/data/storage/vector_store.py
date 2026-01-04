"""Vector storage for embeddings using ChromaDB.

Stores and retrieves text embeddings for semantic search and similarity-based strategies.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import chromadb
    from chromadb.config import Settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Install with: pip install chromadb")

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not installed. Install with: pip install sentence-transformers")


@dataclass
class EmbeddingDocument:
    """A document with its embedding."""

    id: str
    text: str
    embedding: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None

    @classmethod
    def from_text(
        cls,
        text: str,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> "EmbeddingDocument":
        """Create document from text with auto-generated ID."""
        doc_id = hashlib.md5(text.encode()).hexdigest()[:16]
        return cls(
            id=doc_id,
            text=text,
            metadata=metadata or {},
            timestamp=timestamp or datetime.now(),
        )


@dataclass
class SearchResult:
    """Result from a similarity search."""

    document: EmbeddingDocument
    score: float  # Similarity score (higher = more similar)
    distance: float  # Distance (lower = more similar)


class EmbeddingModel:
    """
    Wrapper for text embedding models.

    Supports sentence-transformers models or custom embedding functions.
    """

    # Popular models for financial text
    RECOMMENDED_MODELS = {
        "default": "all-MiniLM-L6-v2",  # Fast, general purpose
        "financial": "sentence-transformers/all-mpnet-base-v2",  # Higher quality
        "multilingual": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    }

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
    ):
        """
        Initialize embedding model.

        Args:
            model_name: Sentence-transformers model name
            device: Device to use ('cpu', 'cuda', etc.)
        """
        self.model_name = model_name
        self.device = device
        self._model = None
        self._embedding_dim = None

    def _load_model(self) -> None:
        """Lazy load the model."""
        if self._model is not None:
            return

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers required for embeddings. "
                "Install with: pip install sentence-transformers"
            )

        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._embedding_dim = self._model.get_sentence_embedding_dimension()
        logger.info(f"Loaded embedding model: {self.model_name} (dim={self._embedding_dim})")

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension."""
        self._load_model()
        return self._embedding_dim

    def embed(self, texts: str | list[str]) -> np.ndarray:
        """
        Generate embeddings for text(s).

        Args:
            texts: Single text or list of texts

        Returns:
            Embeddings array (n_texts, embedding_dim)
        """
        self._load_model()

        if isinstance(texts, str):
            texts = [texts]

        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return embeddings

    def embed_documents(
        self,
        documents: list[EmbeddingDocument],
        batch_size: int = 32,
    ) -> list[EmbeddingDocument]:
        """
        Add embeddings to documents.

        Args:
            documents: List of documents
            batch_size: Batch size for embedding

        Returns:
            Documents with embeddings attached
        """
        texts = [doc.text for doc in documents]

        # Batch embedding
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embed(batch)
            all_embeddings.extend(embeddings)

        # Attach embeddings to documents
        for doc, emb in zip(documents, all_embeddings):
            doc.embedding = emb

        return documents


class VectorStore:
    """
    Vector store for semantic search using ChromaDB.

    Stores embeddings with metadata for efficient similarity search.
    """

    def __init__(
        self,
        collection_name: str = "documents",
        persist_directory: str | Path | None = None,
        embedding_model: EmbeddingModel | None = None,
    ):
        """
        Initialize vector store.

        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory for persistent storage (None = in-memory)
            embedding_model: Model for generating embeddings
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB required for vector storage. "
                "Install with: pip install chromadb"
            )

        self.collection_name = collection_name
        self.persist_directory = Path(persist_directory) if persist_directory else None
        self.embedding_model = embedding_model or EmbeddingModel()

        # Initialize ChromaDB client
        if self.persist_directory:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self._client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False),
            )

        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )

        logger.info(
            f"Initialized vector store: {collection_name} "
            f"(persist={persist_directory is not None})"
        )

    @property
    def count(self) -> int:
        """Get number of documents in collection."""
        return self._collection.count()

    def add(
        self,
        documents: list[EmbeddingDocument] | list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """
        Add documents to the store.

        Args:
            documents: List of EmbeddingDocument objects or raw texts
            metadatas: Metadata for each document (if using raw texts)
            ids: IDs for each document (if using raw texts)

        Returns:
            List of document IDs
        """
        # Convert strings to EmbeddingDocuments
        if documents and isinstance(documents[0], str):
            docs = []
            for i, text in enumerate(documents):
                meta = metadatas[i] if metadatas else {}
                doc_id = ids[i] if ids else None

                if doc_id:
                    docs.append(EmbeddingDocument(id=doc_id, text=text, metadata=meta))
                else:
                    docs.append(EmbeddingDocument.from_text(text, meta))
            documents = docs

        # Generate embeddings if needed
        texts = []
        embeddings = []
        doc_ids = []
        doc_metadatas = []

        for doc in documents:
            if doc.embedding is None:
                doc.embedding = self.embedding_model.embed(doc.text)[0]

            texts.append(doc.text)
            embeddings.append(doc.embedding.tolist())
            doc_ids.append(doc.id)

            # Prepare metadata (ChromaDB requires specific types)
            meta = {}
            for k, v in doc.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                elif isinstance(v, datetime):
                    meta[k] = v.isoformat()
                else:
                    meta[k] = str(v)

            if doc.timestamp:
                meta["timestamp"] = doc.timestamp.isoformat()

            doc_metadatas.append(meta)

        # Add to collection
        self._collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=doc_metadatas,
            ids=doc_ids,
        )

        logger.debug(f"Added {len(doc_ids)} documents to vector store")
        return doc_ids

    def search(
        self,
        query: str | np.ndarray,
        n_results: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar documents.

        Args:
            query: Query text or embedding
            n_results: Number of results to return
            filter_metadata: Metadata filters (ChromaDB where clause)

        Returns:
            List of SearchResult objects
        """
        # Generate query embedding if text
        if isinstance(query, str):
            query_embedding = self.embedding_model.embed(query)[0].tolist()
        else:
            query_embedding = query.tolist()

        # Build where clause
        where = None
        if filter_metadata:
            where = filter_metadata

        # Query collection
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Convert to SearchResult objects
        search_results = []
        if results["documents"]:
            for i, (doc_text, meta, distance, doc_id) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
                results["ids"][0],
            )):
                # Parse timestamp if present
                timestamp = None
                if "timestamp" in meta:
                    try:
                        timestamp = datetime.fromisoformat(meta["timestamp"])
                        del meta["timestamp"]
                    except Exception:
                        pass

                doc = EmbeddingDocument(
                    id=doc_id,
                    text=doc_text,
                    metadata=meta,
                    timestamp=timestamp,
                )

                # Convert distance to similarity score (cosine)
                similarity = 1 - distance

                search_results.append(SearchResult(
                    document=doc,
                    score=similarity,
                    distance=distance,
                ))

        return search_results

    def search_by_text(
        self,
        text: str,
        n_results: int = 10,
        **kwargs,
    ) -> list[SearchResult]:
        """Convenience method for text-based search."""
        return self.search(text, n_results, **kwargs)

    def get(
        self,
        ids: list[str],
    ) -> list[EmbeddingDocument]:
        """
        Get documents by ID.

        Args:
            ids: Document IDs

        Returns:
            List of documents
        """
        results = self._collection.get(
            ids=ids,
            include=["documents", "metadatas", "embeddings"],
        )

        documents = []
        for doc_id, text, meta, emb in zip(
            results["ids"],
            results["documents"],
            results["metadatas"],
            results["embeddings"] or [None] * len(results["ids"]),
        ):
            documents.append(EmbeddingDocument(
                id=doc_id,
                text=text,
                metadata=meta,
                embedding=np.array(emb) if emb else None,
            ))

        return documents

    def delete(self, ids: list[str]) -> None:
        """
        Delete documents by ID.

        Args:
            ids: Document IDs to delete
        """
        self._collection.delete(ids=ids)
        logger.debug(f"Deleted {len(ids)} documents from vector store")

    def clear(self) -> None:
        """Clear all documents from the collection."""
        # Delete and recreate collection
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Cleared vector store: {self.collection_name}")

    def get_similar_documents(
        self,
        document_id: str,
        n_results: int = 10,
        exclude_self: bool = True,
    ) -> list[SearchResult]:
        """
        Find documents similar to an existing document.

        Args:
            document_id: ID of the reference document
            n_results: Number of results
            exclude_self: Exclude the query document from results

        Returns:
            List of similar documents
        """
        # Get the document's embedding
        docs = self.get([document_id])
        if not docs:
            return []

        doc = docs[0]
        if doc.embedding is None:
            doc.embedding = self.embedding_model.embed(doc.text)[0]

        # Search
        results = self.search(doc.embedding, n_results + (1 if exclude_self else 0))

        # Remove self if needed
        if exclude_self:
            results = [r for r in results if r.document.id != document_id]

        return results[:n_results]


class NewsVectorStore(VectorStore):
    """
    Specialized vector store for news articles.

    Adds news-specific functionality like date filtering and symbol search.
    """

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        embedding_model: EmbeddingModel | None = None,
    ):
        """Initialize news vector store."""
        super().__init__(
            collection_name="news_articles",
            persist_directory=persist_directory,
            embedding_model=embedding_model,
        )

    def add_articles(
        self,
        articles: list[dict[str, Any]],
    ) -> list[str]:
        """
        Add news articles to the store.

        Args:
            articles: List of article dicts with keys:
                - title: Article title
                - summary: Article summary (optional)
                - content: Full content (optional)
                - url: Article URL
                - published_at: Publication datetime
                - source: News source
                - symbols: Related stock symbols (optional)

        Returns:
            List of document IDs
        """
        documents = []

        for article in articles:
            # Combine title and summary for embedding
            text = article.get("title", "")
            if article.get("summary"):
                text += " " + article["summary"]
            if article.get("content"):
                text += " " + article["content"][:500]  # Limit content

            # Build metadata
            metadata = {
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "source": article.get("source", ""),
            }

            if article.get("symbols"):
                metadata["symbols"] = ",".join(article["symbols"])

            # Parse timestamp
            timestamp = article.get("published_at")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            doc = EmbeddingDocument.from_text(
                text=text,
                metadata=metadata,
                timestamp=timestamp,
            )
            documents.append(doc)

        return self.add(documents)

    def search_news(
        self,
        query: str,
        n_results: int = 10,
        symbol: str | None = None,
        source: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[SearchResult]:
        """
        Search news articles with filters.

        Args:
            query: Search query
            n_results: Number of results
            symbol: Filter by stock symbol
            source: Filter by news source
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            List of search results
        """
        # Build filter
        where_clauses = []

        if symbol:
            where_clauses.append({"symbols": {"$contains": symbol}})

        if source:
            where_clauses.append({"source": source})

        # Combine filters
        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        # Search
        results = self.search(query, n_results * 2, filter_metadata=where)

        # Filter by date (post-query since ChromaDB date filtering is limited)
        if start_date or end_date:
            filtered = []
            for result in results:
                ts = result.document.timestamp
                if ts:
                    if start_date and ts < start_date:
                        continue
                    if end_date and ts > end_date:
                        continue
                filtered.append(result)
            results = filtered

        return results[:n_results]

    def get_articles_for_symbol(
        self,
        symbol: str,
        n_results: int = 50,
    ) -> list[SearchResult]:
        """
        Get all articles mentioning a symbol.

        Args:
            symbol: Stock symbol
            n_results: Maximum results

        Returns:
            List of articles
        """
        # Search with symbol in query for better ranking
        return self.search_news(
            query=symbol,
            n_results=n_results,
            symbol=symbol,
        )


def compute_text_similarity(
    text1: str,
    text2: str,
    model: EmbeddingModel | None = None,
) -> float:
    """
    Compute cosine similarity between two texts.

    Args:
        text1: First text
        text2: Second text
        model: Embedding model (creates default if None)

    Returns:
        Similarity score (0 to 1)
    """
    model = model or EmbeddingModel()
    embeddings = model.embed([text1, text2])
    similarity = np.dot(embeddings[0], embeddings[1])
    return float(similarity)


def batch_embed_texts(
    texts: list[str],
    model: EmbeddingModel | None = None,
    batch_size: int = 32,
) -> np.ndarray:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts: List of texts
        model: Embedding model
        batch_size: Processing batch size

    Returns:
        Embeddings array (n_texts, embedding_dim)
    """
    model = model or EmbeddingModel()

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.embed(batch)
        all_embeddings.append(embeddings)

    return np.vstack(all_embeddings)
