"""Sentiment-based trading strategies.

Uses news sentiment and social media analysis to generate trading signals.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import Strategy

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


@dataclass
class SentimentScore:
    """Sentiment analysis result."""

    symbol: Symbol
    timestamp: datetime
    score: float  # -1 (negative) to 1 (positive)
    confidence: float  # 0 to 1
    num_articles: int
    source: str
    metadata: dict[str, Any] | None = None


class SentimentAnalyzer:
    """
    Analyzes text sentiment using various methods.

    Supports:
    - Transformer-based models (FinBERT, etc.)
    - Lexicon-based analysis
    - API-based sentiment (pre-computed)
    """

    # Financial sentiment models
    MODELS = {
        "finbert": "ProsusAI/finbert",
        "distilbert": "distilbert-base-uncased-finetuned-sst-2-english",
        "twitter": "cardiffnlp/twitter-roberta-base-sentiment",
    }

    def __init__(
        self,
        model_name: str = "finbert",
        device: int = -1,  # -1 for CPU
        force_transformer: bool = False,
    ):
        """
        Initialize sentiment analyzer.

        Args:
            model_name: Model to use (finbert, distilbert, twitter, or HuggingFace path)
            device: Device ID (-1 for CPU, 0+ for GPU)
            force_transformer: If True, raise error if transformers unavailable (no lexicon fallback)
        """
        self.model_name = model_name
        self.device = device
        self.force_transformer = force_transformer
        self._pipeline = None
        self._lexicon = None

        # Validate transformer availability if forced
        if self.force_transformer and not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                f"force_transformer=True but transformers library not available. "
                f"Install with: pip install transformers torch"
            )

    def _load_pipeline(self) -> None:
        """Lazy load the transformer pipeline."""
        if self._pipeline is not None:
            return

        if not TRANSFORMERS_AVAILABLE:
            if self.force_transformer:
                raise ImportError(
                    "Transformers library not available. "
                    "Install with: pip install transformers torch"
                )
            logger.warning("Transformers not available, falling back to lexicon-based sentiment")
            return

        model_path = self.MODELS.get(self.model_name, self.model_name)

        try:
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=model_path,
                device=self.device,
                truncation=True,
                max_length=512,
            )
            logger.info(f"Loaded sentiment model: {model_path}")
        except Exception as e:
            if self.force_transformer:
                raise RuntimeError(f"Failed to load sentiment model '{model_path}': {e}")
            logger.error(f"Failed to load sentiment model: {e}")

    def _load_lexicon(self) -> None:
        """Load lexicon for rule-based sentiment."""
        if self._lexicon is not None:
            return

        # Simple financial sentiment lexicon
        self._lexicon = {
            # Positive words
            "bullish": 1.0, "buy": 0.8, "upgrade": 0.9, "beat": 0.7,
            "growth": 0.6, "profit": 0.7, "gain": 0.6, "surge": 0.8,
            "rally": 0.8, "strong": 0.5, "outperform": 0.8, "positive": 0.6,
            "optimistic": 0.7, "exceed": 0.7, "record": 0.5, "breakout": 0.7,
            "momentum": 0.5, "upturn": 0.7, "recovery": 0.6, "opportunity": 0.5,

            # Negative words
            "bearish": -1.0, "sell": -0.8, "downgrade": -0.9, "miss": -0.7,
            "decline": -0.6, "loss": -0.7, "drop": -0.6, "plunge": -0.8,
            "crash": -0.9, "weak": -0.5, "underperform": -0.8, "negative": -0.6,
            "pessimistic": -0.7, "fail": -0.7, "warning": -0.5, "breakdown": -0.7,
            "risk": -0.4, "downturn": -0.7, "recession": -0.8, "concern": -0.4,
            "volatility": -0.3, "uncertainty": -0.4, "lawsuit": -0.6, "fraud": -0.9,
        }

    def analyze(
        self,
        text: str,
        use_transformer: bool = True,
    ) -> tuple[float, float]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            use_transformer: Whether to use transformer model

        Returns:
            Tuple of (sentiment_score, confidence)
        """
        if use_transformer and TRANSFORMERS_AVAILABLE:
            return self._analyze_transformer(text)
        else:
            return self._analyze_lexicon(text)

    def _analyze_transformer(self, text: str) -> tuple[float, float]:
        """Analyze using transformer model."""
        self._load_pipeline()

        if self._pipeline is None:
            if self.force_transformer:
                raise RuntimeError(
                    "Transformer pipeline not loaded and force_transformer=True. "
                    "Cannot fall back to lexicon."
                )
            return self._analyze_lexicon(text)

        try:
            result = self._pipeline(text[:512])[0]
            label = result["label"].lower()
            score = result["score"]

            # Convert to -1 to 1 scale
            if "positive" in label:
                sentiment = score
            elif "negative" in label:
                sentiment = -score
            else:  # neutral
                sentiment = 0.0

            return sentiment, score

        except Exception as e:
            if self.force_transformer:
                raise RuntimeError(f"Transformer analysis failed: {e}")
            logger.warning(f"Transformer analysis failed: {e}")
            return self._analyze_lexicon(text)

    def _analyze_lexicon(self, text: str) -> tuple[float, float]:
        """Analyze using lexicon-based method."""
        self._load_lexicon()

        text_lower = text.lower()
        words = text_lower.split()

        scores = []
        for word in words:
            # Check exact match
            if word in self._lexicon:
                scores.append(self._lexicon[word])
            # Check if word contains lexicon term
            else:
                for term, score in self._lexicon.items():
                    if term in word:
                        scores.append(score * 0.5)  # Partial match
                        break

        if not scores:
            return 0.0, 0.3  # Neutral with low confidence

        sentiment = np.mean(scores)
        confidence = min(1.0, len(scores) / 5)  # More matches = higher confidence

        return float(sentiment), float(confidence)

    def analyze_batch(
        self,
        texts: list[str],
        use_transformer: bool = True,
    ) -> list[tuple[float, float]]:
        """Analyze sentiment for multiple texts."""
        if use_transformer and TRANSFORMERS_AVAILABLE:
            self._load_pipeline()
            if self._pipeline:
                try:
                    results = self._pipeline(texts, truncation=True, max_length=512)
                    return [
                        (
                            r["score"] if "positive" in r["label"].lower()
                            else -r["score"] if "negative" in r["label"].lower()
                            else 0.0,
                            r["score"],
                        )
                        for r in results
                    ]
                except Exception as e:
                    if self.force_transformer:
                        raise RuntimeError(f"Batch transformer analysis failed: {e}")
                    logger.warning(f"Batch analysis failed: {e}")
            elif self.force_transformer:
                raise RuntimeError(
                    "Transformer pipeline not loaded and force_transformer=True. "
                    "Cannot fall back to lexicon for batch analysis."
                )
        elif use_transformer and self.force_transformer and not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "Transformers not available but force_transformer=True. "
                "Install with: pip install transformers torch"
            )

        return [self._analyze_lexicon(text) for text in texts]


class NewsSentimentStrategy(Strategy):
    """
    News sentiment-based trading strategy.

    Generates signals based on aggregated sentiment from news articles.
    """

    name = "news_sentiment"
    description = "News sentiment-based trading strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        sentiment_threshold: float = 0.3,
        min_articles: int = 3,
        lookback_hours: int = 24,
        decay_factor: float = 0.9,
        model_name: str = "finbert",
        force_transformer: bool = False,
        **params: Any,
    ):
        """
        Initialize news sentiment strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            sentiment_threshold: Minimum sentiment for signal generation
            min_articles: Minimum articles required for signal
            lookback_hours: Hours to look back for news
            decay_factor: Time decay for older news
            model_name: Sentiment model to use
            force_transformer: If True, raise error if transformers unavailable
        """
        super().__init__(
            universe,
            timeframe,
            sentiment_threshold=sentiment_threshold,
            min_articles=min_articles,
            lookback_hours=lookback_hours,
            decay_factor=decay_factor,
            model_name=model_name,
            force_transformer=force_transformer,
            **params,
        )
        self.sentiment_threshold = sentiment_threshold
        self.min_articles = min_articles
        self.lookback_hours = lookback_hours
        self.decay_factor = decay_factor

        self.analyzer = SentimentAnalyzer(model_name, force_transformer=force_transformer)
        self._sentiment_cache: dict[str, SentimentScore] = {}

    def get_required_history(self) -> int:
        return 1  # Only needs current sentiment

    def compute_sentiment(
        self,
        articles: list[dict[str, Any]],
        current_time: datetime | None = None,
    ) -> tuple[float, float, int]:
        """
        Compute aggregated sentiment from articles.

        Args:
            articles: List of article dicts with 'title', 'summary', 'published_at'
            current_time: Reference time for decay calculation

        Returns:
            Tuple of (sentiment, confidence, num_articles)
        """
        current_time = current_time or datetime.now()
        cutoff_time = current_time - timedelta(hours=self.lookback_hours)

        scores = []
        confidences = []
        weights = []

        for article in articles:
            # Parse timestamp
            pub_time = article.get("published_at")
            if isinstance(pub_time, str):
                try:
                    pub_time = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                    if pub_time.tzinfo:
                        pub_time = pub_time.replace(tzinfo=None)
                except Exception:
                    pub_time = current_time

            # Skip old articles
            if pub_time < cutoff_time:
                continue

            # Analyze text
            text = article.get("title", "")
            if article.get("summary"):
                text += " " + article["summary"]

            # Check for pre-computed sentiment
            if "sentiment" in article and article["sentiment"] is not None:
                sentiment = article["sentiment"]
                confidence = 0.8
            else:
                sentiment, confidence = self.analyzer.analyze(text)

            # Calculate time decay weight
            hours_old = (current_time - pub_time).total_seconds() / 3600
            decay = self.decay_factor ** (hours_old / 24)

            scores.append(sentiment)
            confidences.append(confidence)
            weights.append(decay)

        if not scores:
            return 0.0, 0.0, 0

        # Weighted average
        weights = np.array(weights)
        weights = weights / weights.sum()

        avg_sentiment = float(np.average(scores, weights=weights))
        avg_confidence = float(np.average(confidences, weights=weights))

        return avg_sentiment, avg_confidence, len(scores)

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        news_data: dict[Symbol, list[dict[str, Any]]] | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on news sentiment.

        Args:
            data: OHLCV data (for price context)
            timestamp: Current timestamp
            news_data: Dict mapping symbols to lists of news articles

        Returns:
            List of signals
        """
        if news_data is None:
            logger.warning("No news data provided to sentiment strategy")
            return []

        signals = []
        ts = timestamp or datetime.now()

        for symbol in self.universe:
            articles = news_data.get(symbol, [])

            if len(articles) < self.min_articles:
                continue

            sentiment, confidence, num_articles = self.compute_sentiment(articles, ts)

            # Cache sentiment score
            self._sentiment_cache[symbol] = SentimentScore(
                symbol=symbol,
                timestamp=ts,
                score=sentiment,
                confidence=confidence,
                num_articles=num_articles,
                source="news",
            )

            # Generate signal if sentiment exceeds threshold
            if abs(sentiment) >= self.sentiment_threshold:
                direction = Direction.LONG if sentiment > 0 else Direction.SHORT
                signal_type = SignalType.ENTRY_LONG if sentiment > 0 else SignalType.ENTRY_SHORT

                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=direction,
                    strength=sentiment,
                    confidence=confidence,
                    timestamp=ts,
                    signal_type=signal_type,
                    metadata={
                        "sentiment": sentiment,
                        "num_articles": num_articles,
                        "strategy_type": "news_sentiment",
                    },
                ))

        return signals

    def get_sentiment_scores(self) -> dict[Symbol, SentimentScore]:
        """Get cached sentiment scores."""
        return self._sentiment_cache.copy()


class SentimentMomentumStrategy(Strategy):
    """
    Combines price momentum with sentiment momentum.

    Looks for alignment between price trends and sentiment trends.
    """

    name = "sentiment_momentum"
    description = "Combined sentiment and price momentum strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        price_momentum_period: int = 20,
        sentiment_momentum_period: int = 5,
        alignment_threshold: float = 0.5,
        model_name: str = "finbert",
        force_transformer: bool = False,
        **params: Any,
    ):
        """
        Initialize sentiment momentum strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            price_momentum_period: Period for price momentum
            sentiment_momentum_period: Days for sentiment trend
            alignment_threshold: Required alignment for signal
            model_name: Sentiment model to use
            force_transformer: If True, raise error if transformers unavailable
        """
        super().__init__(
            universe,
            timeframe,
            price_momentum_period=price_momentum_period,
            sentiment_momentum_period=sentiment_momentum_period,
            alignment_threshold=alignment_threshold,
            model_name=model_name,
            force_transformer=force_transformer,
            **params,
        )
        self.price_momentum_period = price_momentum_period
        self.sentiment_momentum_period = sentiment_momentum_period
        self.alignment_threshold = alignment_threshold

        self.analyzer = SentimentAnalyzer(model_name, force_transformer=force_transformer)
        self._sentiment_history: dict[Symbol, list[tuple[datetime, float]]] = {}

    def get_required_history(self) -> int:
        return self.price_momentum_period + 5

    def update_sentiment(
        self,
        symbol: Symbol,
        timestamp: datetime,
        sentiment: float,
    ) -> None:
        """Update sentiment history for a symbol."""
        if symbol not in self._sentiment_history:
            self._sentiment_history[symbol] = []

        self._sentiment_history[symbol].append((timestamp, sentiment))

        # Keep only recent history
        cutoff = timestamp - timedelta(days=self.sentiment_momentum_period * 2)
        self._sentiment_history[symbol] = [
            (ts, s) for ts, s in self._sentiment_history[symbol]
            if ts >= cutoff
        ]

    def get_sentiment_trend(
        self,
        symbol: Symbol,
        current_time: datetime,
    ) -> float | None:
        """Calculate sentiment trend (change over period)."""
        if symbol not in self._sentiment_history:
            return None

        history = self._sentiment_history[symbol]
        if len(history) < 2:
            return None

        # Get sentiment from sentiment_momentum_period days ago
        lookback = current_time - timedelta(days=self.sentiment_momentum_period)

        recent_sentiment = history[-1][1]
        old_sentiment = None

        for ts, s in reversed(history):
            if ts <= lookback:
                old_sentiment = s
                break

        if old_sentiment is None:
            return None

        return recent_sentiment - old_sentiment

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        news_data: dict[Symbol, list[dict[str, Any]]] | None = None,
        sentiment_scores: dict[Symbol, float] | None = None,
    ) -> list[Signal]:
        """
        Generate signals based on sentiment-price momentum alignment.

        Args:
            data: OHLCV data
            timestamp: Current timestamp
            news_data: News articles for sentiment calculation
            sentiment_scores: Pre-computed sentiment scores

        Returns:
            List of signals
        """
        if not isinstance(data, dict):
            return []

        signals = []
        ts = timestamp or datetime.now()

        for symbol in self.universe:
            df = data.get(symbol)
            if df is None or len(df) < self.get_required_history():
                continue

            # Calculate price momentum
            close = df["close"]
            price_momentum = (close.iloc[-1] / close.iloc[-self.price_momentum_period] - 1)

            # Get current sentiment
            current_sentiment = None

            if sentiment_scores and symbol in sentiment_scores:
                current_sentiment = sentiment_scores[symbol]
            elif news_data and symbol in news_data:
                articles = news_data[symbol]
                if articles:
                    sentiment, _, _ = NewsSentimentStrategy.compute_sentiment(
                        self, articles, ts
                    )
                    current_sentiment = sentiment

            if current_sentiment is not None:
                self.update_sentiment(symbol, ts, current_sentiment)

            # Get sentiment trend
            sentiment_trend = self.get_sentiment_trend(symbol, ts)

            if sentiment_trend is None:
                continue

            # Check for alignment
            price_direction = 1 if price_momentum > 0 else -1
            sentiment_direction = 1 if sentiment_trend > 0 else -1

            # Both must be moving in same direction
            if price_direction != sentiment_direction:
                continue

            # Calculate combined signal strength
            normalized_price_mom = np.tanh(price_momentum * 10)  # Scale to [-1, 1]
            normalized_sent_trend = np.tanh(sentiment_trend * 2)

            # Alignment score (how well they agree)
            alignment = normalized_price_mom * normalized_sent_trend

            if abs(alignment) < self.alignment_threshold:
                continue

            # Combined strength
            strength = (normalized_price_mom + normalized_sent_trend) / 2

            direction = Direction.LONG if strength > 0 else Direction.SHORT
            signal_type = SignalType.ENTRY_LONG if strength > 0 else SignalType.ENTRY_SHORT

            signals.append(self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=abs(alignment),
                timestamp=ts,
                signal_type=signal_type,
                metadata={
                    "price_momentum": float(price_momentum),
                    "sentiment_trend": float(sentiment_trend),
                    "alignment": float(alignment),
                    "current_sentiment": current_sentiment,
                    "strategy_type": "sentiment_momentum",
                },
            ))

        return signals


def aggregate_sentiment_scores(
    scores: list[SentimentScore],
    method: str = "weighted_mean",
) -> float:
    """
    Aggregate multiple sentiment scores.

    Args:
        scores: List of SentimentScore objects
        method: Aggregation method (mean, weighted_mean, median)

    Returns:
        Aggregated sentiment score
    """
    if not scores:
        return 0.0

    values = [s.score for s in scores]
    confidences = [s.confidence for s in scores]

    if method == "mean":
        return float(np.mean(values))
    elif method == "weighted_mean":
        weights = np.array(confidences)
        if weights.sum() > 0:
            return float(np.average(values, weights=weights))
        return float(np.mean(values))
    elif method == "median":
        return float(np.median(values))
    else:
        return float(np.mean(values))
