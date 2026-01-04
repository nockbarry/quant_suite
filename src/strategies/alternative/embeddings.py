"""Embedding-based trading strategies.

Uses text embeddings and semantic similarity for signal generation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import Strategy

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from ...data.storage.vector_store import (
        EmbeddingDocument,
        EmbeddingModel,
        VectorStore,
        compute_text_similarity,
    )

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("Embedding dependencies not available")


@dataclass
class SemanticSignal:
    """Signal derived from semantic analysis."""

    symbol: Symbol
    timestamp: datetime
    reference_text: str
    similarity_score: float
    signal_type: str  # "bullish_pattern", "bearish_pattern", "news_similarity"
    metadata: dict[str, Any] = field(default_factory=dict)


# Reference patterns for semantic matching
BULLISH_PATTERNS = [
    "Company reports strong earnings beat and raises guidance for the year",
    "Major analyst upgrades stock to buy with significant price target increase",
    "Company announces strategic acquisition to accelerate growth",
    "Record revenue and expanding profit margins signal strong business momentum",
    "Institutional investors increase positions significantly",
    "Company wins major contract worth billions in revenue",
    "New product launch exceeds expectations with strong demand",
    "Company raises dividend and announces share buyback program",
    "Breaking into new markets with successful expansion strategy",
    "Management expresses confidence in future outlook during earnings call",
]

BEARISH_PATTERNS = [
    "Company misses earnings expectations and cuts guidance for the year",
    "Major analyst downgrades stock citing deteriorating fundamentals",
    "Company announces layoffs and cost cutting measures",
    "Revenue decline and shrinking margins indicate business challenges",
    "Institutional investors reduce positions significantly",
    "Company loses major customer contract affecting future revenue",
    "Product recall or quality issues impact sales and reputation",
    "Company suspends dividend and faces liquidity concerns",
    "Regulatory investigation or legal challenges threaten business",
    "Management expresses caution about challenging market conditions",
]


class SemanticPatternStrategy(Strategy):
    """
    Strategy that matches news to semantic patterns.

    Compares incoming news to predefined bullish/bearish patterns
    using embedding similarity.
    """

    name = "semantic_pattern"
    description = "Semantic pattern matching strategy using embeddings"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        similarity_threshold: float = 0.5,
        bullish_patterns: list[str] | None = None,
        bearish_patterns: list[str] | None = None,
        model_name: str = "all-MiniLM-L6-v2",
        **params: Any,
    ):
        """
        Initialize semantic pattern strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            similarity_threshold: Minimum similarity for pattern match
            bullish_patterns: Custom bullish patterns
            bearish_patterns: Custom bearish patterns
            model_name: Embedding model name
        """
        super().__init__(
            universe,
            timeframe,
            similarity_threshold=similarity_threshold,
            model_name=model_name,
            **params,
        )
        self.similarity_threshold = similarity_threshold
        self.bullish_patterns = bullish_patterns or BULLISH_PATTERNS
        self.bearish_patterns = bearish_patterns or BEARISH_PATTERNS

        if EMBEDDINGS_AVAILABLE:
            self.embedding_model = EmbeddingModel(model_name)
            self._bullish_embeddings = None
            self._bearish_embeddings = None
        else:
            self.embedding_model = None
            logger.warning("Embeddings not available - strategy will not generate signals")

    def get_required_history(self) -> int:
        return 1

    def _ensure_pattern_embeddings(self) -> None:
        """Compute pattern embeddings if not already done."""
        if self._bullish_embeddings is None:
            self._bullish_embeddings = self.embedding_model.embed(self.bullish_patterns)
        if self._bearish_embeddings is None:
            self._bearish_embeddings = self.embedding_model.embed(self.bearish_patterns)

    def match_patterns(
        self,
        text: str,
    ) -> tuple[float, float, str, str]:
        """
        Match text against bullish and bearish patterns.

        Args:
            text: Text to match

        Returns:
            Tuple of (bullish_score, bearish_score, best_bullish_pattern, best_bearish_pattern)
        """
        if not EMBEDDINGS_AVAILABLE or self.embedding_model is None:
            return 0.0, 0.0, "", ""

        self._ensure_pattern_embeddings()

        # Embed the text
        text_embedding = self.embedding_model.embed(text)[0]

        # Calculate similarities to bullish patterns
        bullish_similarities = np.dot(self._bullish_embeddings, text_embedding)
        best_bullish_idx = np.argmax(bullish_similarities)
        bullish_score = float(bullish_similarities[best_bullish_idx])
        best_bullish = self.bullish_patterns[best_bullish_idx]

        # Calculate similarities to bearish patterns
        bearish_similarities = np.dot(self._bearish_embeddings, text_embedding)
        best_bearish_idx = np.argmax(bearish_similarities)
        bearish_score = float(bearish_similarities[best_bearish_idx])
        best_bearish = self.bearish_patterns[best_bearish_idx]

        return bullish_score, bearish_score, best_bullish, best_bearish

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        news_data: dict[Symbol, list[dict[str, Any]]] | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on semantic pattern matching.

        Args:
            data: OHLCV data (for context)
            timestamp: Current timestamp
            news_data: Dict mapping symbols to news articles

        Returns:
            List of signals
        """
        if not EMBEDDINGS_AVAILABLE or news_data is None:
            return []

        signals = []
        ts = timestamp or datetime.now()

        for symbol in self.universe:
            articles = news_data.get(symbol, [])

            if not articles:
                continue

            # Aggregate pattern scores across articles
            bullish_scores = []
            bearish_scores = []
            pattern_matches = []

            for article in articles:
                text = article.get("title", "")
                if article.get("summary"):
                    text += " " + article["summary"]

                bullish, bearish, best_bull, best_bear = self.match_patterns(text)
                bullish_scores.append(bullish)
                bearish_scores.append(bearish)
                pattern_matches.append({
                    "text": text[:100],
                    "bullish_score": bullish,
                    "bearish_score": bearish,
                    "best_bullish_pattern": best_bull,
                    "best_bearish_pattern": best_bear,
                })

            # Calculate aggregate scores
            avg_bullish = np.mean(bullish_scores)
            avg_bearish = np.mean(bearish_scores)
            max_bullish = np.max(bullish_scores)
            max_bearish = np.max(bearish_scores)

            # Determine signal
            net_signal = avg_bullish - avg_bearish

            # Check thresholds
            if max_bullish >= self.similarity_threshold and max_bullish > max_bearish:
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
                strength = min(1.0, net_signal)
                confidence = max_bullish
            elif max_bearish >= self.similarity_threshold and max_bearish > max_bullish:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
                strength = max(-1.0, net_signal)
                confidence = max_bearish
            else:
                continue

            signals.append(self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=confidence,
                timestamp=ts,
                signal_type=signal_type,
                metadata={
                    "avg_bullish": float(avg_bullish),
                    "avg_bearish": float(avg_bearish),
                    "max_bullish": float(max_bullish),
                    "max_bearish": float(max_bearish),
                    "num_articles": len(articles),
                    "top_match": pattern_matches[0] if pattern_matches else None,
                    "strategy_type": "semantic_pattern",
                },
            ))

        return signals


class NewsSimilarityStrategy(Strategy):
    """
    Strategy based on news similarity to historical patterns.

    Finds similar historical news and uses subsequent price movement
    as a signal for current news.
    """

    name = "news_similarity"
    description = "News similarity-based strategy using historical patterns"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        similarity_threshold: float = 0.7,
        min_historical_matches: int = 3,
        forward_return_days: int = 5,
        model_name: str = "all-MiniLM-L6-v2",
        vector_store_path: str | None = None,
        **params: Any,
    ):
        """
        Initialize news similarity strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            similarity_threshold: Minimum similarity for match
            min_historical_matches: Minimum matches required
            forward_return_days: Days to look ahead for historical returns
            model_name: Embedding model name
            vector_store_path: Path to persist vector store
        """
        super().__init__(
            universe,
            timeframe,
            similarity_threshold=similarity_threshold,
            min_historical_matches=min_historical_matches,
            forward_return_days=forward_return_days,
            model_name=model_name,
            **params,
        )
        self.similarity_threshold = similarity_threshold
        self.min_historical_matches = min_historical_matches
        self.forward_return_days = forward_return_days

        if EMBEDDINGS_AVAILABLE:
            self.embedding_model = EmbeddingModel(model_name)
            self.vector_store = VectorStore(
                collection_name="historical_news",
                persist_directory=vector_store_path,
                embedding_model=self.embedding_model,
            )
        else:
            self.embedding_model = None
            self.vector_store = None

        # Cache for historical returns
        self._historical_returns: dict[str, float] = {}

    def get_required_history(self) -> int:
        return self.forward_return_days + 5

    def add_historical_news(
        self,
        articles: list[dict[str, Any]],
        price_data: dict[Symbol, pd.DataFrame],
    ) -> int:
        """
        Add historical news with associated price returns.

        Args:
            articles: List of historical articles with:
                - title, summary, published_at, symbol
            price_data: Price data for calculating forward returns

        Returns:
            Number of articles added
        """
        if not EMBEDDINGS_AVAILABLE:
            return 0

        documents = []

        for article in articles:
            symbol = article.get("symbol")
            if not symbol or symbol not in price_data:
                continue

            pub_time = article.get("published_at")
            if isinstance(pub_time, str):
                try:
                    pub_time = datetime.fromisoformat(pub_time)
                except Exception:
                    continue

            # Calculate forward return
            df = price_data[symbol]
            forward_return = self._calculate_forward_return(df, pub_time)

            if forward_return is None:
                continue

            # Create document
            text = article.get("title", "")
            if article.get("summary"):
                text += " " + article["summary"]

            doc = EmbeddingDocument.from_text(
                text=text,
                metadata={
                    "symbol": symbol,
                    "forward_return": forward_return,
                    "return_direction": "positive" if forward_return > 0 else "negative",
                },
                timestamp=pub_time,
            )
            documents.append(doc)

            # Cache return for lookup
            self._historical_returns[doc.id] = forward_return

        if documents:
            self.vector_store.add(documents)

        return len(documents)

    def _calculate_forward_return(
        self,
        df: pd.DataFrame,
        start_date: datetime,
    ) -> float | None:
        """Calculate forward return from a date."""
        try:
            # Find the closest date
            start_idx = df.index.get_indexer([start_date], method="nearest")[0]
            end_idx = start_idx + self.forward_return_days

            if end_idx >= len(df):
                return None

            start_price = df["close"].iloc[start_idx]
            end_price = df["close"].iloc[end_idx]

            return float((end_price / start_price) - 1)

        except Exception:
            return None

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        news_data: dict[Symbol, list[dict[str, Any]]] | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on similarity to historical news.

        Args:
            data: OHLCV data
            timestamp: Current timestamp
            news_data: Current news articles

        Returns:
            List of signals
        """
        if not EMBEDDINGS_AVAILABLE or news_data is None:
            return []

        if self.vector_store.count == 0:
            logger.warning("No historical news in vector store")
            return []

        signals = []
        ts = timestamp or datetime.now()

        for symbol in self.universe:
            articles = news_data.get(symbol, [])

            if not articles:
                continue

            # Find similar historical news for each article
            similar_returns = []

            for article in articles:
                text = article.get("title", "")
                if article.get("summary"):
                    text += " " + article["summary"]

                # Search for similar historical news
                results = self.vector_store.search(
                    text,
                    n_results=10,
                    filter_metadata={"symbol": symbol},
                )

                for result in results:
                    if result.score >= self.similarity_threshold:
                        # Get the forward return for this historical article
                        hist_return = result.document.metadata.get("forward_return")
                        if hist_return is not None:
                            similar_returns.append({
                                "return": hist_return,
                                "similarity": result.score,
                            })

            if len(similar_returns) < self.min_historical_matches:
                continue

            # Calculate expected return based on similar historical news
            weights = [r["similarity"] for r in similar_returns]
            returns = [r["return"] for r in similar_returns]

            weights = np.array(weights) / sum(weights)
            expected_return = float(np.average(returns, weights=weights))

            # Calculate consistency (what % of similar news had same direction)
            positive_matches = sum(1 for r in similar_returns if r["return"] > 0)
            consistency = positive_matches / len(similar_returns)
            if expected_return < 0:
                consistency = 1 - consistency

            # Generate signal
            if abs(expected_return) < 0.005:  # Minimum 0.5% expected return
                continue

            direction = Direction.LONG if expected_return > 0 else Direction.SHORT
            signal_type = SignalType.ENTRY_LONG if expected_return > 0 else SignalType.ENTRY_SHORT
            strength = np.tanh(expected_return * 20)  # Scale to [-1, 1]

            signals.append(self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=consistency,
                timestamp=ts,
                signal_type=signal_type,
                metadata={
                    "expected_return": expected_return,
                    "num_similar": len(similar_returns),
                    "consistency": consistency,
                    "avg_similarity": float(np.mean([r["similarity"] for r in similar_returns])),
                    "strategy_type": "news_similarity",
                },
            ))

        return signals


class EmbeddingMomentumStrategy(Strategy):
    """
    Strategy based on embedding space momentum.

    Tracks how news embeddings move through semantic space over time.
    Rapid movement toward bullish/bearish regions signals direction.
    """

    name = "embedding_momentum"
    description = "Embedding space momentum strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_days: int = 5,
        momentum_threshold: float = 0.1,
        model_name: str = "all-MiniLM-L6-v2",
        **params: Any,
    ):
        """
        Initialize embedding momentum strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            lookback_days: Days to track embedding history
            momentum_threshold: Minimum momentum for signal
            model_name: Embedding model name
        """
        super().__init__(
            universe,
            timeframe,
            lookback_days=lookback_days,
            momentum_threshold=momentum_threshold,
            model_name=model_name,
            **params,
        )
        self.lookback_days = lookback_days
        self.momentum_threshold = momentum_threshold

        if EMBEDDINGS_AVAILABLE:
            self.embedding_model = EmbeddingModel(model_name)
            # Pre-compute anchor embeddings
            self._bullish_anchor = self.embedding_model.embed(
                " ".join(BULLISH_PATTERNS[:5])
            )[0]
            self._bearish_anchor = self.embedding_model.embed(
                " ".join(BEARISH_PATTERNS[:5])
            )[0]
        else:
            self.embedding_model = None
            self._bullish_anchor = None
            self._bearish_anchor = None

        # History of embeddings per symbol
        self._embedding_history: dict[Symbol, list[tuple[datetime, np.ndarray]]] = {}

    def get_required_history(self) -> int:
        return 1

    def update_embeddings(
        self,
        symbol: Symbol,
        timestamp: datetime,
        texts: list[str],
    ) -> None:
        """
        Update embedding history for a symbol.

        Args:
            symbol: Stock symbol
            timestamp: Current timestamp
            texts: News texts to embed
        """
        if not EMBEDDINGS_AVAILABLE or not texts:
            return

        # Compute average embedding for the day's news
        embeddings = self.embedding_model.embed(texts)
        avg_embedding = np.mean(embeddings, axis=0)

        if symbol not in self._embedding_history:
            self._embedding_history[symbol] = []

        self._embedding_history[symbol].append((timestamp, avg_embedding))

        # Keep only recent history
        cutoff = timestamp - timedelta(days=self.lookback_days * 2)
        self._embedding_history[symbol] = [
            (ts, emb) for ts, emb in self._embedding_history[symbol]
            if ts >= cutoff
        ]

    def calculate_embedding_momentum(
        self,
        symbol: Symbol,
        current_time: datetime,
    ) -> tuple[float, float] | None:
        """
        Calculate momentum in embedding space.

        Returns movement toward bullish/bearish anchors.

        Args:
            symbol: Stock symbol
            current_time: Current timestamp

        Returns:
            Tuple of (bullish_momentum, bearish_momentum) or None
        """
        if symbol not in self._embedding_history:
            return None

        history = self._embedding_history[symbol]
        if len(history) < 2:
            return None

        # Get current and past embeddings
        current_embedding = history[-1][1]

        lookback = current_time - timedelta(days=self.lookback_days)
        past_embedding = None
        for ts, emb in reversed(history[:-1]):
            if ts <= lookback:
                past_embedding = emb
                break

        if past_embedding is None:
            past_embedding = history[0][1]

        # Calculate distances to anchors
        current_bullish_dist = 1 - np.dot(current_embedding, self._bullish_anchor)
        current_bearish_dist = 1 - np.dot(current_embedding, self._bearish_anchor)
        past_bullish_dist = 1 - np.dot(past_embedding, self._bullish_anchor)
        past_bearish_dist = 1 - np.dot(past_embedding, self._bearish_anchor)

        # Momentum = decrease in distance (moving toward anchor)
        bullish_momentum = past_bullish_dist - current_bullish_dist
        bearish_momentum = past_bearish_dist - current_bearish_dist

        return float(bullish_momentum), float(bearish_momentum)

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        news_data: dict[Symbol, list[dict[str, Any]]] | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on embedding momentum.

        Args:
            data: OHLCV data
            timestamp: Current timestamp
            news_data: Current news articles

        Returns:
            List of signals
        """
        if not EMBEDDINGS_AVAILABLE or news_data is None:
            return []

        signals = []
        ts = timestamp or datetime.now()

        for symbol in self.universe:
            articles = news_data.get(symbol, [])

            if articles:
                # Extract texts
                texts = []
                for article in articles:
                    text = article.get("title", "")
                    if article.get("summary"):
                        text += " " + article["summary"]
                    texts.append(text)

                # Update embedding history
                self.update_embeddings(symbol, ts, texts)

            # Calculate momentum
            momentum = self.calculate_embedding_momentum(symbol, ts)

            if momentum is None:
                continue

            bullish_mom, bearish_mom = momentum
            net_momentum = bullish_mom - bearish_mom

            if abs(net_momentum) < self.momentum_threshold:
                continue

            direction = Direction.LONG if net_momentum > 0 else Direction.SHORT
            signal_type = SignalType.ENTRY_LONG if net_momentum > 0 else SignalType.ENTRY_SHORT
            strength = np.tanh(net_momentum * 5)
            confidence = min(1.0, abs(net_momentum) / 0.2)

            signals.append(self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=confidence,
                timestamp=ts,
                signal_type=signal_type,
                metadata={
                    "bullish_momentum": bullish_mom,
                    "bearish_momentum": bearish_mom,
                    "net_momentum": net_momentum,
                    "history_length": len(self._embedding_history.get(symbol, [])),
                    "strategy_type": "embedding_momentum",
                },
            ))

        return signals
