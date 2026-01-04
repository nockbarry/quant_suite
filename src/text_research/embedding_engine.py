"""
EmbeddingEngine: Multi-Model Text Embedding with Point-in-Time Safety.

Provides text embedding capabilities with:
- Multiple model support (sentence-transformers, FinBERT)
- Point-in-time safe embedding retrieval
- Incremental updates for online learning
- Vector store integration for similarity search

Key Design:
- Embeddings are computed and stored with timestamps
- get_embeddings_as_of() ensures no future embeddings leak
- Incremental update avoids recomputing existing embeddings
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .corpus import TextCorpus, TextDocument

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("sentence_transformers not available, using fallback")

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("transformers not available for FinBERT")


@dataclass
class EmbeddingResult:
    """Result of embedding a document."""
    doc_id: str
    embedding: np.ndarray
    model_name: str
    computed_at: datetime


class EmbeddingEngine:
    """
    Multi-model embedding engine with point-in-time safety.

    Supports multiple embedding models:
    - sentence-transformers (default): Fast, general-purpose embeddings
    - finbert: Financial domain-specific embeddings
    - custom: User-provided embedding functions

    Example Usage:
        engine = EmbeddingEngine()

        # Embed a document
        embedding = engine.embed_document(doc)

        # Get symbol centroid (average embedding over time)
        centroid = engine.get_symbol_centroid(
            corpus=corpus,
            symbol="AAPL",
            as_of_date=date(2026, 1, 3),
            lookback_days=30
        )

        # Incremental update with new documents
        engine.update_embeddings_incremental(corpus, new_docs)
    """

    # Default models
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    FINBERT_MODEL = "ProsusAI/finbert"

    def __init__(
        self,
        models: list[str] | None = None,
        cache_path: str | Path | None = None,
        default_model: str | None = None,
    ):
        """
        Initialize EmbeddingEngine.

        Args:
            models: List of model names to load. Defaults to sentence-transformers default.
            cache_path: Path for caching embeddings.
                       Defaults to /home/nock/quant_results/embeddings_cache
            default_model: Default model to use for embedding.
        """
        self.cache_path = Path(cache_path or "/home/nock/quant_results/embeddings_cache")
        self.cache_path.mkdir(parents=True, exist_ok=True)

        # Load models
        self._models: dict[str, Any] = {}
        self._model_dims: dict[str, int] = {}

        model_list = models or [self.DEFAULT_MODEL]
        for model_name in model_list:
            self._load_model(model_name)

        self.default_model = default_model or (model_list[0] if model_list else self.DEFAULT_MODEL)

        # Embedding cache: model_name -> doc_id -> EmbeddingResult
        self._cache: dict[str, dict[str, EmbeddingResult]] = {}
        self._load_cache()

    def _load_model(self, model_name: str) -> bool:
        """Load a model by name."""
        if model_name in self._models:
            return True

        # Sentence transformers
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                if "finbert" not in model_name.lower():
                    model = SentenceTransformer(model_name)
                    self._models[model_name] = model
                    # Get embedding dimension
                    test_emb = model.encode(["test"])
                    self._model_dims[model_name] = test_emb.shape[1]
                    logger.info(f"Loaded sentence-transformer model: {model_name}")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load {model_name}: {e}")

        # FinBERT
        if HAS_TRANSFORMERS and "finbert" in model_name.lower():
            try:
                tokenizer = AutoTokenizer.from_pretrained(self.FINBERT_MODEL)
                model = AutoModelForSequenceClassification.from_pretrained(self.FINBERT_MODEL)
                self._models[model_name] = {"tokenizer": tokenizer, "model": model}
                self._model_dims[model_name] = 768  # FinBERT hidden size
                logger.info(f"Loaded FinBERT model: {model_name}")
                return True
            except Exception as e:
                logger.warning(f"Failed to load FinBERT: {e}")

        # Fallback to random embeddings for testing
        logger.warning(f"Using fallback random embeddings for {model_name}")
        self._models[model_name] = "fallback"
        self._model_dims[model_name] = 384
        return True

    def _load_cache(self) -> None:
        """Load embedding cache from disk."""
        cache_file = self.cache_path / "embedding_index.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                for model_name, doc_cache in data.items():
                    self._cache[model_name] = {}
                    for doc_id, info in doc_cache.items():
                        # Load embedding from file
                        emb_file = self.cache_path / f"{model_name}_{doc_id}.npy"
                        if emb_file.exists():
                            embedding = np.load(emb_file)
                            self._cache[model_name][doc_id] = EmbeddingResult(
                                doc_id=doc_id,
                                embedding=embedding,
                                model_name=model_name,
                                computed_at=datetime.fromisoformat(info["computed_at"]),
                            )
                logger.info(f"Loaded embedding cache with {sum(len(c) for c in self._cache.values())} embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")

    def _save_cache(self) -> None:
        """Save embedding cache to disk."""
        # Save index
        index_data = {}
        for model_name, doc_cache in self._cache.items():
            index_data[model_name] = {}
            for doc_id, result in doc_cache.items():
                index_data[model_name][doc_id] = {
                    "computed_at": result.computed_at.isoformat(),
                }
                # Save embedding array
                emb_file = self.cache_path / f"{model_name}_{doc_id}.npy"
                np.save(emb_file, result.embedding)

        cache_file = self.cache_path / "embedding_index.json"
        with open(cache_file, "w") as f:
            json.dump(index_data, f)

    def embed_text(
        self,
        text: str,
        model_name: str | None = None,
    ) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed
            model_name: Model to use (defaults to default_model)

        Returns:
            Embedding vector as numpy array
        """
        model_name = model_name or self.default_model

        if model_name not in self._models:
            self._load_model(model_name)

        model = self._models.get(model_name)

        # Sentence transformers
        if HAS_SENTENCE_TRANSFORMERS and isinstance(model, SentenceTransformer):
            embedding = model.encode([text])[0]
            return np.array(embedding, dtype=np.float32)

        # FinBERT
        if HAS_TRANSFORMERS and isinstance(model, dict) and "tokenizer" in model:
            tokenizer = model["tokenizer"]
            bert_model = model["model"]

            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                outputs = bert_model(**inputs, output_hidden_states=True)
                # Use CLS token from last hidden state
                embedding = outputs.hidden_states[-1][0, 0, :].numpy()
            return np.array(embedding, dtype=np.float32)

        # Fallback: deterministic random based on text hash
        text_hash = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(text_hash)
        return rng.standard_normal(self._model_dims.get(model_name, 384)).astype(np.float32)

    def embed_document(
        self,
        doc: TextDocument,
        model_name: str | None = None,
        use_cache: bool = True,
    ) -> EmbeddingResult:
        """
        Embed a document.

        Args:
            doc: TextDocument to embed
            model_name: Model to use
            use_cache: Whether to use cached embeddings

        Returns:
            EmbeddingResult with embedding and metadata
        """
        model_name = model_name or self.default_model

        # Check cache
        if use_cache:
            if model_name in self._cache and doc.doc_id in self._cache[model_name]:
                return self._cache[model_name][doc.doc_id]

        # Compute embedding
        embedding = self.embed_text(doc.text, model_name)

        result = EmbeddingResult(
            doc_id=doc.doc_id,
            embedding=embedding,
            model_name=model_name,
            computed_at=datetime.now(),
        )

        # Update cache
        if model_name not in self._cache:
            self._cache[model_name] = {}
        self._cache[model_name][doc.doc_id] = result

        return result

    def embed_documents(
        self,
        docs: list[TextDocument],
        model_name: str | None = None,
        use_cache: bool = True,
        batch_size: int = 32,
    ) -> dict[str, EmbeddingResult]:
        """
        Batch embed multiple documents.

        Args:
            docs: List of TextDocuments
            model_name: Model to use
            use_cache: Whether to use cached embeddings
            batch_size: Batch size for embedding

        Returns:
            Dictionary mapping doc_id to EmbeddingResult
        """
        model_name = model_name or self.default_model
        results = {}

        # Separate cached vs uncached
        to_embed = []
        for doc in docs:
            if use_cache and model_name in self._cache and doc.doc_id in self._cache[model_name]:
                results[doc.doc_id] = self._cache[model_name][doc.doc_id]
            else:
                to_embed.append(doc)

        if not to_embed:
            return results

        # Batch embed
        model = self._models.get(model_name)

        if HAS_SENTENCE_TRANSFORMERS and isinstance(model, SentenceTransformer):
            # Efficient batch encoding
            texts = [doc.text for doc in to_embed]
            embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)

            for doc, embedding in zip(to_embed, embeddings):
                result = EmbeddingResult(
                    doc_id=doc.doc_id,
                    embedding=np.array(embedding, dtype=np.float32),
                    model_name=model_name,
                    computed_at=datetime.now(),
                )
                results[doc.doc_id] = result

                if model_name not in self._cache:
                    self._cache[model_name] = {}
                self._cache[model_name][doc.doc_id] = result
        else:
            # Fallback to individual embedding
            for doc in to_embed:
                result = self.embed_document(doc, model_name, use_cache=False)
                results[doc.doc_id] = result

        # Save cache periodically
        if len(to_embed) > 10:
            self._save_cache()

        return results

    def embed_corpus_as_of(
        self,
        corpus: TextCorpus,
        as_of_date: date,
        model_name: str | None = None,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
        lookback_days: int = 30,
    ) -> dict[str, np.ndarray]:
        """
        Embed all documents in corpus available as of date (NO LOOKAHEAD).

        This method ensures point-in-time safety by only returning embeddings
        for documents that were available on or before the specified date.

        Args:
            corpus: TextCorpus to embed
            as_of_date: Reference date for point-in-time
            model_name: Model to use
            symbols: Optional symbols to filter by
            sources: Optional sources to filter by
            lookback_days: Number of days to look back

        Returns:
            Dictionary mapping doc_id to embedding array
        """
        # Get documents as of date
        docs = corpus.get_documents_as_of(
            as_of_date=as_of_date,
            symbols=symbols,
            sources=sources,
            lookback_days=lookback_days,
        )

        if not docs:
            return {}

        # Embed documents
        results = self.embed_documents(docs, model_name)

        return {doc_id: r.embedding for doc_id, r in results.items()}

    def get_symbol_centroid(
        self,
        corpus: TextCorpus,
        symbol: str,
        as_of_date: date,
        model_name: str | None = None,
        lookback_days: int = 30,
        sources: list[str] | None = None,
    ) -> np.ndarray | None:
        """
        Get average embedding for a symbol over lookback period.

        The centroid represents the "average narrative" for a stock
        over the specified time window.

        Args:
            corpus: TextCorpus to query
            symbol: Stock symbol
            as_of_date: Reference date (point-in-time)
            model_name: Model to use
            lookback_days: Number of days to look back
            sources: Optional sources to filter by

        Returns:
            Centroid embedding or None if no documents found
        """
        model_name = model_name or self.default_model

        # Get documents for symbol
        docs = corpus.get_documents_as_of(
            as_of_date=as_of_date,
            symbols=[symbol],
            sources=sources,
            lookback_days=lookback_days,
        )

        if not docs:
            return None

        # Get embeddings
        results = self.embed_documents(docs, model_name)

        if not results:
            return None

        # Compute centroid (mean of embeddings)
        embeddings = [r.embedding for r in results.values()]
        centroid = np.mean(embeddings, axis=0)

        return centroid.astype(np.float32)

    def get_symbol_centroids_time_series(
        self,
        corpus: TextCorpus,
        symbol: str,
        start_date: date,
        end_date: date,
        model_name: str | None = None,
        lookback_days: int = 30,
        step_days: int = 1,
    ) -> dict[date, np.ndarray]:
        """
        Get time series of symbol centroids.

        Useful for tracking how the narrative around a stock evolves over time.

        Args:
            corpus: TextCorpus to query
            symbol: Stock symbol
            start_date: Start of time series
            end_date: End of time series
            model_name: Model to use
            lookback_days: Rolling window size
            step_days: Step size between observations

        Returns:
            Dictionary mapping date to centroid embedding
        """
        centroids = {}
        current = start_date

        while current <= end_date:
            centroid = self.get_symbol_centroid(
                corpus=corpus,
                symbol=symbol,
                as_of_date=current,
                model_name=model_name,
                lookback_days=lookback_days,
            )
            if centroid is not None:
                centroids[current] = centroid
            current += timedelta(days=step_days)

        return centroids

    def update_embeddings_incremental(
        self,
        corpus: TextCorpus,
        new_docs: list[TextDocument],
        model_name: str | None = None,
    ) -> int:
        """
        Incrementally update embeddings with new documents.

        This method adds embeddings for new documents without recomputing
        existing ones - key for efficient online learning.

        Args:
            corpus: TextCorpus (for context)
            new_docs: New documents to embed
            model_name: Model to use

        Returns:
            Number of new embeddings computed
        """
        model_name = model_name or self.default_model

        # Filter to documents not already cached
        to_embed = []
        for doc in new_docs:
            if model_name not in self._cache or doc.doc_id not in self._cache.get(model_name, {}):
                to_embed.append(doc)

        if not to_embed:
            logger.info("All documents already have embeddings")
            return 0

        # Embed new documents
        results = self.embed_documents(to_embed, model_name, use_cache=False)

        # Save cache
        self._save_cache()

        logger.info(f"Computed {len(results)} new embeddings")
        return len(results)

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score [-1, 1]
        """
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(embedding1, embedding2) / (norm1 * norm2))

    def find_similar_documents(
        self,
        query_embedding: np.ndarray,
        corpus: TextCorpus,
        as_of_date: date,
        model_name: str | None = None,
        top_k: int = 10,
        symbols: list[str] | None = None,
    ) -> list[tuple[TextDocument, float]]:
        """
        Find documents most similar to query embedding.

        Args:
            query_embedding: Query embedding vector
            corpus: TextCorpus to search
            as_of_date: Reference date (point-in-time)
            model_name: Model to use
            top_k: Number of results to return
            symbols: Optional symbols to filter by

        Returns:
            List of (document, similarity_score) tuples
        """
        model_name = model_name or self.default_model

        # Get embeddings as of date
        embeddings = self.embed_corpus_as_of(
            corpus=corpus,
            as_of_date=as_of_date,
            model_name=model_name,
            symbols=symbols,
        )

        if not embeddings:
            return []

        # Compute similarities
        similarities = []
        for doc_id, embedding in embeddings.items():
            sim = self.compute_similarity(query_embedding, embedding)
            similarities.append((doc_id, sim))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Get top-k documents
        results = []
        for doc_id, sim in similarities[:top_k]:
            doc = corpus.get_document(doc_id)
            if doc:
                results.append((doc, sim))

        return results

    def get_embedding_dim(self, model_name: str | None = None) -> int:
        """Get embedding dimension for a model."""
        model_name = model_name or self.default_model
        return self._model_dims.get(model_name, 384)

    def save_cache(self) -> None:
        """Explicitly save cache to disk."""
        self._save_cache()

    def clear_cache(self, model_name: str | None = None) -> None:
        """
        Clear embedding cache.

        Args:
            model_name: Specific model to clear, or None for all
        """
        if model_name:
            self._cache[model_name] = {}
        else:
            self._cache = {}
        self._save_cache()

    def __repr__(self) -> str:
        """String representation."""
        total_embeddings = sum(len(c) for c in self._cache.values())
        models = list(self._models.keys())
        return f"EmbeddingEngine(models={models}, cached={total_embeddings})"
