"""Contrarian sentiment strategies.

Strategies that fade extreme retail sentiment, detecting when the crowd
is likely wrong and trading against the herd.

Theory: Retail traders (especially on WSB) are often wrong at extremes.
When sentiment reaches historical extremes, mean reversion is likely.
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ...data.sources.alternative.reddit import (
    BEARISH_WORDS,
    BULLISH_WORDS,
    RedditPost,
    SymbolMention,
)
from ..base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class SentimentExtreme:
    """Represents an extreme sentiment reading."""

    symbol: Symbol
    timestamp: datetime
    sentiment_value: float  # Bullish ratio 0-1 (0.5 = neutral)
    percentile: float  # Historical percentile (0-100)
    z_score: float
    direction: str  # "bullish" or "bearish"
    source: str  # "reddit", "news", "combined"
    mention_count: int
    confidence: float


class SentimentHistory:
    """
    Maintains rolling history of sentiment for percentile calculations.

    Used to determine when current sentiment is at historical extremes.
    """

    def __init__(
        self,
        lookback_days: int = 90,
        min_observations: int = 20,
    ):
        """
        Initialize sentiment history tracker.

        Args:
            lookback_days: Number of days of history to maintain
            min_observations: Minimum observations needed for calculations
        """
        self.lookback_days = lookback_days
        self.min_observations = min_observations
        self._history: dict[Symbol, deque[tuple[datetime, float]]] = {}

    def add_observation(
        self,
        symbol: Symbol,
        timestamp: datetime,
        sentiment: float,
    ) -> None:
        """
        Add a sentiment observation.

        Args:
            symbol: Stock symbol
            timestamp: Observation time
            sentiment: Sentiment value (0-1, 0.5 = neutral)
        """
        if symbol not in self._history:
            self._history[symbol] = deque()

        # Add new observation
        self._history[symbol].append((timestamp, sentiment))

        # Remove old observations
        cutoff = timestamp - timedelta(days=self.lookback_days)
        while self._history[symbol] and self._history[symbol][0][0] < cutoff:
            self._history[symbol].popleft()

    def get_observations(self, symbol: Symbol) -> list[float]:
        """Get all observations for a symbol."""
        if symbol not in self._history:
            return []
        return [obs[1] for obs in self._history[symbol]]

    def get_percentile(
        self,
        symbol: Symbol,
        current_sentiment: float,
    ) -> float | None:
        """
        Get percentile rank of current sentiment vs history.

        Args:
            symbol: Stock symbol
            current_sentiment: Current sentiment value

        Returns:
            Percentile (0-100) or None if insufficient data
        """
        observations = self.get_observations(symbol)

        if len(observations) < self.min_observations:
            return None

        # Calculate percentile rank
        below = sum(1 for obs in observations if obs < current_sentiment)
        equal = sum(1 for obs in observations if obs == current_sentiment)

        percentile = ((below + 0.5 * equal) / len(observations)) * 100
        return percentile

    def get_z_score(
        self,
        symbol: Symbol,
        current_sentiment: float,
    ) -> float | None:
        """
        Get z-score of current sentiment.

        Args:
            symbol: Stock symbol
            current_sentiment: Current sentiment value

        Returns:
            Z-score or None if insufficient data
        """
        observations = self.get_observations(symbol)

        if len(observations) < self.min_observations:
            return None

        mean = np.mean(observations)
        std = np.std(observations)

        if std == 0:
            return 0.0

        return (current_sentiment - mean) / std

    def is_extreme(
        self,
        symbol: Symbol,
        sentiment: float,
        threshold_percentile: float = 90,
    ) -> tuple[bool, str | None]:
        """
        Check if sentiment is at historical extreme.

        Args:
            symbol: Stock symbol
            sentiment: Current sentiment value
            threshold_percentile: Percentile threshold for extreme

        Returns:
            (is_extreme, direction) where direction is "bullish" or "bearish"
        """
        percentile = self.get_percentile(symbol, sentiment)

        if percentile is None:
            return False, None

        if percentile >= threshold_percentile:
            return True, "bullish"
        elif percentile <= (100 - threshold_percentile):
            return True, "bearish"

        return False, None


class ManufacturedSentimentDetector:
    """
    Detect potentially artificial/coordinated sentiment spikes.

    Indicators of manufactured sentiment:
    - Sudden spike in mentions without price catalyst
    - Unusual timing patterns (off-hours posting)
    - Abnormal engagement patterns
    - Repetitive content
    """

    def __init__(
        self,
        spike_threshold: float = 3.0,  # 3 std devs
        new_account_threshold: float = 0.5,  # 50% new accounts
        similarity_threshold: float = 0.8,  # Text similarity
    ):
        """
        Initialize detector.

        Args:
            spike_threshold: Z-score threshold for mention spikes
            new_account_threshold: Max ratio of new accounts
            similarity_threshold: Text similarity threshold for duplicates
        """
        self.spike_threshold = spike_threshold
        self.new_account_threshold = new_account_threshold
        self.similarity_threshold = similarity_threshold
        self._mention_history: dict[Symbol, deque[tuple[datetime, int]]] = {}

    def analyze_posts(
        self,
        posts: list[RedditPost],
        symbol: Symbol,
    ) -> dict[str, Any]:
        """
        Analyze posts for signs of manipulation.

        Args:
            posts: List of Reddit posts
            symbol: Symbol to analyze

        Returns:
            Analysis results with confidence score
        """
        if not posts:
            return {
                "is_suspicious": False,
                "confidence": 0.0,
                "indicators": [],
                "mention_velocity_zscore": 0.0,
            }

        indicators = []
        suspicion_score = 0.0

        # Check 1: Mention velocity spike
        current_count = len(posts)
        velocity_zscore = self._check_velocity_spike(symbol, current_count)
        if velocity_zscore > self.spike_threshold:
            indicators.append(f"mention_spike (z={velocity_zscore:.1f})")
            suspicion_score += min(velocity_zscore / 5, 1.0) * 0.3

        # Check 2: Engagement anomalies
        scores = [p.score for p in posts]
        avg_score = np.mean(scores) if scores else 0
        score_std = np.std(scores) if len(scores) > 1 else 0

        # Low variance in scores can indicate coordinated voting
        if score_std < 5 and avg_score > 50:
            indicators.append("uniform_engagement")
            suspicion_score += 0.2

        # Check 3: Timing patterns (posting concentration)
        hours = [p.created_utc.hour for p in posts]
        hour_counts = {}
        for h in hours:
            hour_counts[h] = hour_counts.get(h, 0) + 1

        max_hour_concentration = max(hour_counts.values()) / len(posts) if posts else 0
        if max_hour_concentration > 0.5:
            indicators.append(f"timing_concentration ({max_hour_concentration:.0%})")
            suspicion_score += 0.2

        # Check 4: Content similarity
        titles = [p.title.lower() for p in posts]
        duplicate_ratio = self._check_duplicate_content(titles)
        if duplicate_ratio > 0.3:
            indicators.append(f"duplicate_content ({duplicate_ratio:.0%})")
            suspicion_score += 0.3

        is_suspicious = suspicion_score >= 0.5

        return {
            "is_suspicious": is_suspicious,
            "confidence": min(suspicion_score, 1.0),
            "indicators": indicators,
            "mention_velocity_zscore": velocity_zscore,
            "duplicate_content_ratio": duplicate_ratio,
            "avg_engagement": avg_score,
            "timing_concentration": max_hour_concentration,
        }

    def _check_velocity_spike(
        self,
        symbol: Symbol,
        current_count: int,
    ) -> float:
        """Check if current mention count is a spike."""
        if symbol not in self._mention_history:
            self._mention_history[symbol] = deque(maxlen=30)

        history = self._mention_history[symbol]

        # Add current observation
        history.append((datetime.now(), current_count))

        if len(history) < 5:
            return 0.0

        # Calculate z-score
        counts = [c for _, c in history]
        mean = np.mean(counts[:-1])  # Exclude current
        std = np.std(counts[:-1])

        if std == 0:
            return 0.0

        return (current_count - mean) / std

    def _check_duplicate_content(self, texts: list[str]) -> float:
        """Check for duplicate/similar content."""
        if len(texts) < 2:
            return 0.0

        # Simple Jaccard similarity
        duplicates = 0
        comparisons = 0

        for i, text1 in enumerate(texts):
            words1 = set(text1.split())
            for text2 in texts[i + 1:]:
                words2 = set(text2.split())
                if not words1 or not words2:
                    continue

                intersection = len(words1 & words2)
                union = len(words1 | words2)
                similarity = intersection / union if union > 0 else 0

                if similarity > self.similarity_threshold:
                    duplicates += 1
                comparisons += 1

        return duplicates / comparisons if comparisons > 0 else 0.0

    def filter_authentic_sentiment(
        self,
        posts: list[RedditPost],
    ) -> list[RedditPost]:
        """
        Filter out likely manufactured posts.

        Simple heuristics:
        - Keep posts with organic engagement patterns
        - Remove posts that look like copy/paste
        """
        if len(posts) < 5:
            return posts

        # Calculate baseline engagement
        scores = [p.score for p in posts]
        median_score = np.median(scores)

        # Filter posts
        filtered = []
        seen_titles = set()

        for post in posts:
            # Skip exact duplicate titles
            title_lower = post.title.lower().strip()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            # Keep posts with reasonable engagement
            if post.score >= median_score * 0.1:
                filtered.append(post)

        return filtered


class InverseSentimentStrategy(Strategy):
    """
    Fade extreme retail sentiment.

    Theory: Retail traders are often wrong at extremes.
    WSB euphoria = short signal
    WSB panic = long signal
    """

    name = "inverse_sentiment"
    description = "Contrarian strategy fading retail sentiment extremes"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        bullish_threshold: float = 0.8,  # Top 20% = extreme bullish
        bearish_threshold: float = 0.2,  # Bottom 20% = extreme bearish
        min_mentions: int = 10,
        lookback_days: int = 30,
        require_price_confirmation: bool = True,
        price_confirmation_bars: int = 2,
        **params: Any,
    ):
        """
        Initialize inverse sentiment strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            bullish_threshold: Bullish ratio threshold for extreme bullish
            bearish_threshold: Bullish ratio threshold for extreme bearish
            min_mentions: Minimum mentions required
            lookback_days: Days of sentiment history for percentiles
            require_price_confirmation: Require price to confirm
            price_confirmation_bars: Bars of price confirmation needed
        """
        super().__init__(universe, timeframe, **params)

        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold
        self.min_mentions = min_mentions
        self.lookback_days = lookback_days
        self.require_price_confirmation = require_price_confirmation
        self.price_confirmation_bars = price_confirmation_bars

        self._sentiment_history = SentimentHistory(lookback_days)

    def get_required_history(self) -> int:
        """Get required price history."""
        return self.price_confirmation_bars + 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        sentiment_data: dict[Symbol, SymbolMention] | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate contrarian signals.

        Args:
            data: Price data
            timestamp: Current timestamp
            sentiment_data: Dict of symbol -> SymbolMention

        Returns:
            List of contrarian signals
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if sentiment_data is None:
            return signals

        # Normalize data format
        if isinstance(data, pd.DataFrame):
            data = {self.universe[0]: data}

        for symbol in self.universe:
            if symbol not in sentiment_data:
                continue

            mention = sentiment_data[symbol]

            # Check minimum mentions
            if mention.mention_count < self.min_mentions:
                continue

            # Get sentiment value (bullish ratio)
            sentiment = mention.bullish_ratio

            # Update history
            self._sentiment_history.add_observation(symbol, timestamp, sentiment)

            # Check for extreme
            percentile = self._sentiment_history.get_percentile(symbol, sentiment)
            if percentile is None:
                continue

            z_score = self._sentiment_history.get_z_score(symbol, sentiment) or 0.0

            # Determine signal direction
            signal_direction = None
            signal_type = None

            if sentiment >= self.bullish_threshold and percentile >= 80:
                # Extreme bullish -> contrarian short
                signal_direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
                extreme_direction = "bullish"
            elif sentiment <= self.bearish_threshold and percentile <= 20:
                # Extreme bearish -> contrarian long
                signal_direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
                extreme_direction = "bearish"
            else:
                continue

            # Optional price confirmation
            if self.require_price_confirmation and symbol in data:
                price_df = data[symbol]
                if not self._check_price_confirmation(price_df, extreme_direction):
                    continue

            # Calculate signal strength and confidence
            strength = abs(z_score) / 3.0  # Normalize z-score to ~0-1
            strength = min(max(strength, 0.1), 1.0)

            confidence = min(mention.mention_count / 50, 1.0) * 0.7
            confidence += (abs(percentile - 50) / 50) * 0.3

            signal = self.create_signal(
                symbol=symbol,
                direction=signal_direction,
                strength=strength if signal_direction == Direction.LONG else -strength,
                confidence=confidence,
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "inverse_sentiment",
                    "sentiment_value": sentiment,
                    "sentiment_percentile": percentile,
                    "z_score": z_score,
                    "extreme_direction": extreme_direction,
                    "mention_count": mention.mention_count,
                    "bullish_count": mention.bullish_count,
                    "bearish_count": mention.bearish_count,
                },
            )
            signals.append(signal)

        return signals

    def _check_price_confirmation(
        self,
        price_df: pd.DataFrame,
        extreme_direction: str,
    ) -> bool:
        """
        Check if price action confirms the trade.

        For bullish extremes (shorting): Look for exhaustion patterns
        For bearish extremes (buying): Look for support/reversal patterns
        """
        if len(price_df) < self.price_confirmation_bars:
            return False

        recent = price_df.tail(self.price_confirmation_bars)
        returns = recent["close"].pct_change().dropna()

        if len(returns) == 0:
            return True  # No confirmation data, proceed anyway

        if extreme_direction == "bullish":
            # For shorting: Look for recent weakness
            return returns.iloc[-1] < 0 or returns.mean() < 0.01
        else:
            # For buying: Look for recent strength or stabilization
            return returns.iloc[-1] > 0 or returns.std() < 0.02

        return True


class SentimentDivergenceStrategy(Strategy):
    """
    Trade divergences between sentiment and price action.

    Bullish divergence: Price making lows but sentiment improving
    Bearish divergence: Price making highs but sentiment deteriorating
    """

    name = "sentiment_divergence"
    description = "Trade sentiment-price divergences"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        price_lookback: int = 10,
        sentiment_lookback: int = 5,
        divergence_threshold: float = 0.3,
        **params: Any,
    ):
        """
        Initialize divergence strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            price_lookback: Bars to look back for price trend
            sentiment_lookback: Observations for sentiment trend
            divergence_threshold: Minimum divergence strength
        """
        super().__init__(universe, timeframe, **params)

        self.price_lookback = price_lookback
        self.sentiment_lookback = sentiment_lookback
        self.divergence_threshold = divergence_threshold

        self._sentiment_series: dict[Symbol, deque[tuple[datetime, float]]] = {}

    def get_required_history(self) -> int:
        """Get required price history."""
        return self.price_lookback + 5

    def _update_sentiment_series(
        self,
        symbol: Symbol,
        timestamp: datetime,
        sentiment: float,
    ) -> None:
        """Update sentiment time series."""
        if symbol not in self._sentiment_series:
            self._sentiment_series[symbol] = deque(maxlen=self.sentiment_lookback * 2)

        self._sentiment_series[symbol].append((timestamp, sentiment))

    def detect_divergence(
        self,
        price_series: pd.Series,
        sentiment_values: list[float],
    ) -> tuple[str | None, float]:
        """
        Detect divergence between price and sentiment.

        Args:
            price_series: Recent price data
            sentiment_values: Recent sentiment values

        Returns:
            (divergence_type, strength) where type is "bullish", "bearish", or None
        """
        if len(price_series) < 3 or len(sentiment_values) < 3:
            return None, 0.0

        # Calculate trends
        price_returns = price_series.pct_change().dropna()
        price_trend = price_returns.mean()

        sentiment_trend = (
            (sentiment_values[-1] - sentiment_values[0]) /
            max(len(sentiment_values), 1)
        )

        # Check for divergence
        if price_trend < -0.01 and sentiment_trend > 0.02:
            # Price falling but sentiment improving -> bullish divergence
            strength = abs(price_trend) + abs(sentiment_trend)
            return "bullish", min(strength * 5, 1.0)

        elif price_trend > 0.01 and sentiment_trend < -0.02:
            # Price rising but sentiment deteriorating -> bearish divergence
            strength = abs(price_trend) + abs(sentiment_trend)
            return "bearish", min(strength * 5, 1.0)

        return None, 0.0

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        sentiment_data: dict[Symbol, SymbolMention] | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate divergence signals.

        Args:
            data: Price data
            timestamp: Current timestamp
            sentiment_data: Dict of symbol -> SymbolMention

        Returns:
            List of divergence signals
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if sentiment_data is None:
            return signals

        # Normalize data format
        if isinstance(data, pd.DataFrame):
            data = {self.universe[0]: data}

        for symbol in self.universe:
            if symbol not in sentiment_data or symbol not in data:
                continue

            mention = sentiment_data[symbol]
            price_df = data[symbol]

            # Update sentiment series
            sentiment = mention.bullish_ratio
            self._update_sentiment_series(symbol, timestamp, sentiment)

            # Get sentiment history
            if symbol not in self._sentiment_series:
                continue

            sentiment_values = [
                v for _, v in list(self._sentiment_series[symbol])[-self.sentiment_lookback:]
            ]

            if len(sentiment_values) < 3:
                continue

            # Get price series
            price_series = price_df["close"].tail(self.price_lookback)

            # Detect divergence
            divergence_type, strength = self.detect_divergence(
                price_series, sentiment_values
            )

            if divergence_type is None or strength < self.divergence_threshold:
                continue

            # Generate signal
            if divergence_type == "bullish":
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            else:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT

            signal = self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength if direction == Direction.LONG else -strength,
                confidence=strength * 0.8,
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "sentiment_divergence",
                    "divergence_type": divergence_type,
                    "divergence_strength": strength,
                    "current_sentiment": sentiment,
                    "sentiment_trend": sentiment_values[-1] - sentiment_values[0],
                    "price_trend": float(price_series.pct_change().mean()),
                },
            )
            signals.append(signal)

        return signals


class ManufacturedSentimentStrategy(Strategy):
    """
    Trade against detected manufactured sentiment.

    If sentiment spike appears artificial, fade it.
    """

    name = "anti_manipulation"
    description = "Fade manufactured sentiment campaigns"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        manipulation_confidence_threshold: float = 0.6,
        min_posts: int = 10,
        **params: Any,
    ):
        """
        Initialize anti-manipulation strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            manipulation_confidence_threshold: Min confidence to act
            min_posts: Minimum posts to analyze
        """
        super().__init__(universe, timeframe, **params)

        self.manipulation_confidence_threshold = manipulation_confidence_threshold
        self.min_posts = min_posts
        self._detector = ManufacturedSentimentDetector()

    def get_required_history(self) -> int:
        return 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        reddit_posts: dict[Symbol, list[RedditPost]] | None = None,
        sentiment_data: dict[Symbol, SymbolMention] | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate anti-manipulation signals.

        Args:
            data: Price data
            timestamp: Current timestamp
            reddit_posts: Dict of symbol -> list of RedditPost
            sentiment_data: Dict of symbol -> SymbolMention

        Returns:
            List of contrarian signals against manipulation
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if reddit_posts is None:
            return signals

        for symbol in self.universe:
            if symbol not in reddit_posts:
                continue

            posts = reddit_posts[symbol]

            if len(posts) < self.min_posts:
                continue

            # Analyze for manipulation
            analysis = self._detector.analyze_posts(posts, symbol)

            if not analysis["is_suspicious"]:
                continue

            if analysis["confidence"] < self.manipulation_confidence_threshold:
                continue

            # Determine sentiment direction being manufactured
            if sentiment_data and symbol in sentiment_data:
                sentiment = sentiment_data[symbol].bullish_ratio
            else:
                # Estimate from posts
                bullish = sum(1 for p in posts if any(w in p.full_text.lower() for w in BULLISH_WORDS))
                bearish = sum(1 for p in posts if any(w in p.full_text.lower() for w in BEARISH_WORDS))
                total = bullish + bearish
                sentiment = bullish / total if total > 0 else 0.5

            # Fade the manufactured sentiment
            if sentiment > 0.6:
                # Bullish manipulation -> short
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
                fade_direction = "bearish"
            elif sentiment < 0.4:
                # Bearish manipulation -> long
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
                fade_direction = "bullish"
            else:
                continue

            signal = self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=analysis["confidence"] if direction == Direction.LONG else -analysis["confidence"],
                confidence=analysis["confidence"],
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "anti_manipulation",
                    "manipulation_confidence": analysis["confidence"],
                    "indicators": analysis["indicators"],
                    "manufactured_sentiment": sentiment,
                    "fade_direction": fade_direction,
                    "post_count": len(posts),
                },
            )
            signals.append(signal)

        return signals


class SentimentExtremesStrategy(Strategy):
    """
    Mean reversion on sentiment extremes.

    When sentiment reaches historical extremes (95th+ percentile),
    bet on mean reversion.
    """

    name = "sentiment_extremes"
    description = "Mean reversion on sentiment extremes"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        extreme_percentile: float = 90.0,
        lookback_days: int = 90,
        exit_percentile: float = 50.0,  # Exit when sentiment normalizes
        min_mentions: int = 5,
        **params: Any,
    ):
        """
        Initialize sentiment extremes strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            extreme_percentile: Percentile threshold for extremes
            lookback_days: Days of history for percentile calculation
            exit_percentile: Percentile at which to exit
            min_mentions: Minimum mentions required
        """
        super().__init__(universe, timeframe, **params)

        self.extreme_percentile = extreme_percentile
        self.lookback_days = lookback_days
        self.exit_percentile = exit_percentile
        self.min_mentions = min_mentions

        self._sentiment_history = SentimentHistory(lookback_days)
        self._active_positions: dict[Symbol, str] = {}  # symbol -> direction

    def get_required_history(self) -> int:
        return 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        sentiment_data: dict[Symbol, SymbolMention] | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate mean reversion signals on sentiment extremes.

        Args:
            data: Price data
            timestamp: Current timestamp
            sentiment_data: Dict of symbol -> SymbolMention

        Returns:
            List of mean reversion signals
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if sentiment_data is None:
            return signals

        for symbol in self.universe:
            if symbol not in sentiment_data:
                continue

            mention = sentiment_data[symbol]

            if mention.mention_count < self.min_mentions:
                continue

            sentiment = mention.bullish_ratio

            # Update history
            self._sentiment_history.add_observation(symbol, timestamp, sentiment)

            percentile = self._sentiment_history.get_percentile(symbol, sentiment)
            if percentile is None:
                continue

            # Check for exit condition
            if symbol in self._active_positions:
                position_direction = self._active_positions[symbol]

                # Check if should exit
                should_exit = False
                exit_percentile = self.exit_percentile

                if position_direction == "short" and percentile <= exit_percentile:
                    # Sentiment normalized from bullish extreme
                    should_exit = True
                    signal_type = SignalType.EXIT_SHORT
                elif position_direction == "long" and percentile >= exit_percentile:
                    # Sentiment normalized from bearish extreme
                    should_exit = True
                    signal_type = SignalType.EXIT_LONG

                if should_exit:
                    signal = self.create_signal(
                        symbol=symbol,
                        direction=Direction.FLAT,
                        strength=0.0,
                        confidence=0.8,
                        timestamp=timestamp,
                        signal_type=signal_type,
                        metadata={
                            "strategy_type": "sentiment_extremes",
                            "action": "exit",
                            "sentiment": sentiment,
                            "percentile": percentile,
                            "position_direction": position_direction,
                        },
                    )
                    signals.append(signal)
                    del self._active_positions[symbol]

                continue  # Don't enter new position while in existing one

            # Check for entry condition
            is_extreme, extreme_direction = self._sentiment_history.is_extreme(
                symbol, sentiment, self.extreme_percentile
            )

            if not is_extreme:
                continue

            # Generate entry signal
            if extreme_direction == "bullish":
                # Extreme bullish -> short for mean reversion
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT
                position_direction = "short"
            else:
                # Extreme bearish -> long for mean reversion
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
                position_direction = "long"

            z_score = self._sentiment_history.get_z_score(symbol, sentiment) or 0.0
            strength = min(abs(z_score) / 3.0, 1.0)
            confidence = abs(percentile - 50) / 50

            signal = self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength if direction == Direction.LONG else -strength,
                confidence=confidence,
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "sentiment_extremes",
                    "action": "entry",
                    "sentiment": sentiment,
                    "percentile": percentile,
                    "z_score": z_score,
                    "extreme_direction": extreme_direction,
                    "mention_count": mention.mention_count,
                },
            )
            signals.append(signal)
            self._active_positions[symbol] = position_direction

        return signals


# Utility functions


def calculate_contrarian_metrics(
    signals: list[Signal],
    price_data: dict[Symbol, pd.DataFrame],
    horizon: int = 5,
) -> dict[str, float]:
    """
    Calculate performance metrics for contrarian signals.

    Args:
        signals: List of signals generated
        price_data: Price data for symbols
        horizon: Forward return horizon in bars

    Returns:
        Dict of performance metrics
    """
    if not signals:
        return {"hit_rate": 0.0, "avg_return": 0.0, "n_signals": 0}

    correct = 0
    total_return = 0.0
    n_evaluated = 0

    for signal in signals:
        if signal.symbol not in price_data:
            continue

        df = price_data[signal.symbol]

        # Find signal date in data
        signal_date = signal.timestamp
        if signal_date not in df.index:
            # Find closest date
            idx = df.index.searchsorted(signal_date)
            if idx >= len(df):
                continue
        else:
            idx = df.index.get_loc(signal_date)

        # Get forward return
        if idx + horizon >= len(df):
            continue

        entry_price = df["close"].iloc[idx]
        exit_price = df["close"].iloc[idx + horizon]
        fwd_return = (exit_price - entry_price) / entry_price

        # Check if signal was correct
        if signal.direction == Direction.LONG:
            if fwd_return > 0:
                correct += 1
            total_return += fwd_return
        elif signal.direction == Direction.SHORT:
            if fwd_return < 0:
                correct += 1
            total_return -= fwd_return

        n_evaluated += 1

    return {
        "hit_rate": correct / n_evaluated if n_evaluated > 0 else 0.0,
        "avg_return": total_return / n_evaluated if n_evaluated > 0 else 0.0,
        "n_signals": n_evaluated,
    }
