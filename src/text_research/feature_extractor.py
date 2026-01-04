"""
TextFeatureExtractor: Extract Numeric Features from Text.

Converts text corpus into tradeable numeric features:
- Sentiment features (mean, momentum, volatility)
- Embedding-based features (centroid shift, novelty)
- Volume features (mention velocity, coverage)
- Cross-symbol features (correlation, divergence)

All features are computed with point-in-time safety and
registered with the main FeatureRegistry for use in strategies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Any, Callable

import numpy as np
import pandas as pd

from .corpus import TextCorpus, TextDocument
from .embedding_engine import EmbeddingEngine

logger = logging.getLogger(__name__)

# Try to import sentiment analyzer
try:
    from src.strategies.alternative.sentiment import SentimentAnalyzer
    HAS_SENTIMENT = True
except ImportError:
    HAS_SENTIMENT = False
    logger.warning("SentimentAnalyzer not available")


@dataclass
class TextFeatureDefinition:
    """Definition of a text feature."""
    name: str
    lookback_days: int
    source: str  # 'news', 'sec', 'all', etc.
    compute_fn: str  # Method name to compute
    description: str
    category: str = "text"


class TextFeatureExtractor:
    """
    Extract numeric features from text corpus for trading signals.

    Features are designed to capture different aspects of text-based alpha:
    - Sentiment: Market mood from news/social media
    - Narrative: How the story around a stock is evolving
    - Attention: Volume of coverage and mention patterns
    - Similarity: Cross-symbol relationships in text space

    Example Usage:
        extractor = TextFeatureExtractor(corpus, embedding_engine)

        # Get all features for a symbol on a date
        features = extractor.compute_features(
            symbol="AAPL",
            as_of_date=date(2026, 1, 3)
        )

        # Get feature time series
        df = extractor.compute_feature_series(
            symbol="AAPL",
            feature_name="text_sentiment_momentum",
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 3)
        )
    """

    # Feature definitions
    FEATURE_DEFINITIONS = {
        "text_sentiment_mean": TextFeatureDefinition(
            name="text_sentiment_mean",
            lookback_days=7,
            source="news",
            compute_fn="compute_sentiment_mean",
            description="Average sentiment score over lookback period",
        ),
        "text_sentiment_momentum": TextFeatureDefinition(
            name="text_sentiment_momentum",
            lookback_days=14,
            source="news",
            compute_fn="compute_sentiment_momentum",
            description="Change in sentiment over lookback period",
        ),
        "text_sentiment_volatility": TextFeatureDefinition(
            name="text_sentiment_volatility",
            lookback_days=14,
            source="news",
            compute_fn="compute_sentiment_volatility",
            description="Standard deviation of sentiment",
        ),
        "text_mention_velocity": TextFeatureDefinition(
            name="text_mention_velocity",
            lookback_days=7,
            source="news",
            compute_fn="compute_mention_velocity",
            description="Rate of change in document count",
        ),
        "text_narrative_shift": TextFeatureDefinition(
            name="text_narrative_shift",
            lookback_days=30,
            source="all",
            compute_fn="compute_narrative_shift",
            description="Cosine distance of recent vs historical centroid",
        ),
        "text_semantic_novelty": TextFeatureDefinition(
            name="text_semantic_novelty",
            lookback_days=30,
            source="all",
            compute_fn="compute_semantic_novelty",
            description="How different recent docs are from historical average",
        ),
        "text_topic_concentration": TextFeatureDefinition(
            name="text_topic_concentration",
            lookback_days=30,
            source="all",
            compute_fn="compute_topic_concentration",
            description="Concentration of embedding space (inverse dispersion)",
        ),
    }

    def __init__(
        self,
        corpus: TextCorpus,
        embedding_engine: EmbeddingEngine,
        sentiment_analyzer: Any | None = None,
    ):
        """
        Initialize TextFeatureExtractor.

        Args:
            corpus: TextCorpus for document retrieval
            embedding_engine: EmbeddingEngine for text embeddings
            sentiment_analyzer: Optional custom sentiment analyzer
        """
        self.corpus = corpus
        self.embeddings = embedding_engine

        # Initialize sentiment analyzer
        if sentiment_analyzer:
            self.sentiment = sentiment_analyzer
        elif HAS_SENTIMENT:
            try:
                self.sentiment = SentimentAnalyzer()
            except Exception as e:
                logger.warning(f"Failed to initialize SentimentAnalyzer: {e}")
                self.sentiment = None
        else:
            self.sentiment = None

        # Cache for computed features
        self._feature_cache: dict[str, dict[str, Any]] = {}

    def compute_features(
        self,
        symbol: str,
        as_of_date: date,
        features: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Compute all text features for a symbol on a date.

        Args:
            symbol: Stock symbol
            as_of_date: Reference date (point-in-time safe)
            features: Optional list of specific features to compute

        Returns:
            Dictionary mapping feature name to value
        """
        feature_list = features or list(self.FEATURE_DEFINITIONS.keys())
        result = {}

        for feature_name in feature_list:
            if feature_name not in self.FEATURE_DEFINITIONS:
                logger.warning(f"Unknown feature: {feature_name}")
                continue

            defn = self.FEATURE_DEFINITIONS[feature_name]
            compute_fn = getattr(self, defn.compute_fn, None)

            if compute_fn is None:
                logger.warning(f"Compute function not found: {defn.compute_fn}")
                continue

            try:
                value = compute_fn(
                    symbol=symbol,
                    as_of_date=as_of_date,
                    lookback_days=defn.lookback_days,
                    source=defn.source,
                )
                result[feature_name] = value
            except Exception as e:
                logger.warning(f"Failed to compute {feature_name}: {e}")
                result[feature_name] = np.nan

        return result

    def compute_feature_series(
        self,
        symbol: str,
        feature_name: str,
        start_date: date,
        end_date: date,
        step_days: int = 1,
    ) -> pd.Series:
        """
        Compute time series of a single feature.

        Args:
            symbol: Stock symbol
            feature_name: Name of feature to compute
            start_date: Start date
            end_date: End date
            step_days: Step size between observations

        Returns:
            Pandas Series indexed by date
        """
        if feature_name not in self.FEATURE_DEFINITIONS:
            raise ValueError(f"Unknown feature: {feature_name}")

        defn = self.FEATURE_DEFINITIONS[feature_name]
        compute_fn = getattr(self, defn.compute_fn, None)

        if compute_fn is None:
            raise ValueError(f"Compute function not found: {defn.compute_fn}")

        values = {}
        current = start_date

        while current <= end_date:
            try:
                value = compute_fn(
                    symbol=symbol,
                    as_of_date=current,
                    lookback_days=defn.lookback_days,
                    source=defn.source,
                )
                values[current] = value
            except Exception as e:
                logger.debug(f"Failed to compute {feature_name} for {current}: {e}")
                values[current] = np.nan

            current += timedelta(days=step_days)

        return pd.Series(values, name=feature_name)

    def compute_all_features_series(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        features: list[str] | None = None,
        step_days: int = 1,
    ) -> pd.DataFrame:
        """
        Compute time series of all features.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            features: Optional list of specific features
            step_days: Step size between observations

        Returns:
            DataFrame with date index and feature columns
        """
        feature_list = features or list(self.FEATURE_DEFINITIONS.keys())

        series_dict = {}
        for feature_name in feature_list:
            try:
                series = self.compute_feature_series(
                    symbol=symbol,
                    feature_name=feature_name,
                    start_date=start_date,
                    end_date=end_date,
                    step_days=step_days,
                )
                series_dict[feature_name] = series
            except Exception as e:
                logger.warning(f"Failed to compute series for {feature_name}: {e}")

        return pd.DataFrame(series_dict)

    # ==================== Feature Computation Methods ====================

    def compute_sentiment_mean(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 7,
        source: str = "news",
    ) -> float:
        """
        Compute average sentiment score over lookback period.

        Returns:
            Sentiment score in range [-1, 1], or NaN if no data
        """
        docs = self._get_documents(symbol, as_of_date, lookback_days, source)

        if not docs:
            return np.nan

        if not self.sentiment:
            # Fallback: use simple positive/negative word count
            return self._simple_sentiment(docs)

        # Compute sentiment for each document
        sentiments = []
        for doc in docs:
            try:
                score, confidence = self.sentiment.analyze(doc.text)
                sentiments.append(score)
            except Exception:
                continue

        if not sentiments:
            return np.nan

        return float(np.mean(sentiments))

    def compute_sentiment_momentum(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 14,
        source: str = "news",
    ) -> float:
        """
        Compute change in sentiment (recent vs earlier).

        Compares sentiment in recent half vs earlier half of lookback.

        Returns:
            Change in sentiment [-2, 2], positive = improving
        """
        half = lookback_days // 2

        recent_sentiment = self.compute_sentiment_mean(
            symbol, as_of_date, half, source
        )
        earlier_sentiment = self.compute_sentiment_mean(
            symbol, as_of_date - timedelta(days=half), half, source
        )

        if np.isnan(recent_sentiment) or np.isnan(earlier_sentiment):
            return np.nan

        return recent_sentiment - earlier_sentiment

    def compute_sentiment_volatility(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 14,
        source: str = "news",
    ) -> float:
        """
        Compute standard deviation of sentiment scores.

        High volatility suggests mixed or changing narratives.

        Returns:
            Sentiment std dev, or NaN if insufficient data
        """
        docs = self._get_documents(symbol, as_of_date, lookback_days, source)

        if len(docs) < 3:
            return np.nan

        if not self.sentiment:
            return np.nan

        sentiments = []
        for doc in docs:
            try:
                score, _ = self.sentiment.analyze(doc.text)
                sentiments.append(score)
            except Exception:
                continue

        if len(sentiments) < 3:
            return np.nan

        return float(np.std(sentiments))

    def compute_mention_velocity(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 7,
        source: str = "news",
    ) -> float:
        """
        Compute rate of change in document count.

        Compares document count in recent period vs earlier period.

        Returns:
            Log ratio of recent/earlier counts, or 0 if stable
        """
        half = lookback_days // 2

        recent_docs = self._get_documents(symbol, as_of_date, half, source)
        earlier_docs = self._get_documents(
            symbol, as_of_date - timedelta(days=half), half, source
        )

        recent_count = len(recent_docs)
        earlier_count = len(earlier_docs)

        # Avoid division by zero
        if earlier_count == 0:
            if recent_count == 0:
                return 0.0
            return 1.0  # Significant increase from zero

        # Log ratio for symmetric treatment of increases/decreases
        ratio = (recent_count + 1) / (earlier_count + 1)
        return float(np.log(ratio))

    def compute_narrative_shift(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 30,
        source: str = "all",
    ) -> float:
        """
        Compute how much the narrative has shifted.

        Measures cosine distance between recent and historical centroids.

        Returns:
            Distance in [0, 2], 0 = no change, 2 = opposite
        """
        # Recent centroid (last 7 days)
        recent_centroid = self.embeddings.get_symbol_centroid(
            corpus=self.corpus,
            symbol=symbol,
            as_of_date=as_of_date,
            lookback_days=7,
            sources=[source] if source != "all" else None,
        )

        # Historical centroid (earlier part of lookback)
        historical_centroid = self.embeddings.get_symbol_centroid(
            corpus=self.corpus,
            symbol=symbol,
            as_of_date=as_of_date - timedelta(days=7),
            lookback_days=lookback_days - 7,
            sources=[source] if source != "all" else None,
        )

        if recent_centroid is None or historical_centroid is None:
            return np.nan

        # Cosine distance = 1 - cosine_similarity
        similarity = self.embeddings.compute_similarity(recent_centroid, historical_centroid)
        return float(1 - similarity)

    def compute_semantic_novelty(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 30,
        source: str = "all",
    ) -> float:
        """
        Compute how different recent documents are from historical.

        High novelty suggests new information entering the market.

        Returns:
            Average novelty score, higher = more novel
        """
        # Get historical centroid
        historical_centroid = self.embeddings.get_symbol_centroid(
            corpus=self.corpus,
            symbol=symbol,
            as_of_date=as_of_date - timedelta(days=7),
            lookback_days=lookback_days - 7,
            sources=[source] if source != "all" else None,
        )

        if historical_centroid is None:
            return np.nan

        # Get recent documents
        recent_docs = self._get_documents(symbol, as_of_date, 7, source)

        if not recent_docs:
            return np.nan

        # Compute novelty for each recent doc
        novelties = []
        for doc in recent_docs:
            result = self.embeddings.embed_document(doc)
            similarity = self.embeddings.compute_similarity(
                result.embedding, historical_centroid
            )
            novelty = 1 - similarity  # Convert similarity to novelty
            novelties.append(novelty)

        return float(np.mean(novelties))

    def compute_topic_concentration(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int = 30,
        source: str = "all",
    ) -> float:
        """
        Compute concentration of documents in embedding space.

        Low concentration (high dispersion) suggests diverse topics.
        High concentration suggests focused narrative.

        Returns:
            Concentration score (inverse of dispersion)
        """
        docs = self._get_documents(symbol, as_of_date, lookback_days, source)

        if len(docs) < 3:
            return np.nan

        # Get embeddings
        results = self.embeddings.embed_documents(docs)
        embeddings = [r.embedding for r in results.values()]

        if len(embeddings) < 3:
            return np.nan

        # Compute centroid
        centroid = np.mean(embeddings, axis=0)

        # Compute average distance from centroid
        distances = []
        for emb in embeddings:
            dist = np.linalg.norm(emb - centroid)
            distances.append(dist)

        dispersion = np.mean(distances)

        # Convert to concentration (inverse)
        if dispersion == 0:
            return 1.0

        return float(1.0 / (1.0 + dispersion))

    def compute_cross_symbol_divergence(
        self,
        symbol: str,
        peer_symbols: list[str],
        as_of_date: date,
        lookback_days: int = 14,
    ) -> float:
        """
        Compute how different symbol's narrative is from peers.

        Useful for detecting when a stock's story diverges from sector.

        Args:
            symbol: Target symbol
            peer_symbols: List of peer symbols to compare against
            as_of_date: Reference date
            lookback_days: Lookback period

        Returns:
            Divergence score [0, 2], higher = more different from peers
        """
        # Get target centroid
        target_centroid = self.embeddings.get_symbol_centroid(
            corpus=self.corpus,
            symbol=symbol,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
        )

        if target_centroid is None:
            return np.nan

        # Get peer centroids
        peer_centroids = []
        for peer in peer_symbols:
            centroid = self.embeddings.get_symbol_centroid(
                corpus=self.corpus,
                symbol=peer,
                as_of_date=as_of_date,
                lookback_days=lookback_days,
            )
            if centroid is not None:
                peer_centroids.append(centroid)

        if not peer_centroids:
            return np.nan

        # Compute average peer centroid
        peer_avg = np.mean(peer_centroids, axis=0)

        # Compute divergence
        similarity = self.embeddings.compute_similarity(target_centroid, peer_avg)
        return float(1 - similarity)

    # ==================== Helper Methods ====================

    def _get_documents(
        self,
        symbol: str,
        as_of_date: date,
        lookback_days: int,
        source: str,
    ) -> list[TextDocument]:
        """Get documents from corpus with source filtering."""
        sources = [source] if source != "all" else None
        return self.corpus.get_documents_as_of(
            as_of_date=as_of_date,
            symbols=[symbol],
            sources=sources,
            lookback_days=lookback_days,
        )

    def _simple_sentiment(self, docs: list[TextDocument]) -> float:
        """Simple sentiment fallback using keyword matching."""
        positive_words = {
            "surge", "soar", "jump", "gain", "rise", "beat", "exceed",
            "strong", "growth", "profit", "bullish", "upgrade", "buy",
            "positive", "optimistic", "record", "success", "breakthrough",
        }
        negative_words = {
            "fall", "drop", "plunge", "decline", "miss", "weak", "loss",
            "bearish", "downgrade", "sell", "negative", "concern", "risk",
            "warning", "failure", "crash", "layoff", "cut",
        }

        total_score = 0
        total_words = 0

        for doc in docs:
            words = doc.text.lower().split()
            for word in words:
                word_clean = word.strip(".,!?\"'")
                if word_clean in positive_words:
                    total_score += 1
                    total_words += 1
                elif word_clean in negative_words:
                    total_score -= 1
                    total_words += 1

        if total_words == 0:
            return 0.0

        # Normalize to [-1, 1]
        return float(total_score / total_words)

    def get_feature_definitions(self) -> dict[str, TextFeatureDefinition]:
        """Get all feature definitions."""
        return self.FEATURE_DEFINITIONS.copy()

    def register_with_feature_registry(self) -> None:
        """
        Register text features with the main FeatureRegistry.

        This allows text features to be used alongside traditional
        technical and fundamental features in strategies.
        """
        try:
            from src.data.feature_engineering.feature_registry import FeatureRegistry

            registry = FeatureRegistry()

            for name, defn in self.FEATURE_DEFINITIONS.items():
                registry.register_feature(
                    name=name,
                    compute_fn=lambda symbol, df, _defn=defn: self._registry_compute_wrapper(
                        symbol, df, _defn
                    ),
                    lookback_days=defn.lookback_days,
                    category=defn.category,
                    description=defn.description,
                )

            logger.info(f"Registered {len(self.FEATURE_DEFINITIONS)} text features")

        except ImportError:
            logger.warning("FeatureRegistry not available for registration")

    def _registry_compute_wrapper(
        self,
        symbol: str,
        df: pd.DataFrame,
        defn: TextFeatureDefinition,
    ) -> pd.Series:
        """Wrapper for feature registry compute function."""
        # Extract dates from DataFrame index
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        values = {}
        for dt in df.index:
            as_of_date = dt.date()
            compute_fn = getattr(self, defn.compute_fn, None)
            if compute_fn:
                try:
                    value = compute_fn(
                        symbol=symbol,
                        as_of_date=as_of_date,
                        lookback_days=defn.lookback_days,
                        source=defn.source,
                    )
                    values[dt] = value
                except Exception:
                    values[dt] = np.nan
            else:
                values[dt] = np.nan

        return pd.Series(values, name=defn.name)

    def __repr__(self) -> str:
        """String representation."""
        return f"TextFeatureExtractor({len(self.FEATURE_DEFINITIONS)} features)"
