"""
AAII Sentiment Survey Source

Fetches AAII individual investor sentiment survey data.
Published weekly on Thursdays.

High bullish = contrarian sell signal
High bearish = contrarian buy signal

Historical averages:
- Bullish: 37.5%
- Bearish: 31.0%
- Neutral: 31.5%
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Historical thresholds for interpretation
AAII_HISTORICAL_BULLISH = 37.5
AAII_HISTORICAL_BEARISH = 31.0
AAII_HISTORICAL_NEUTRAL = 31.5

# Extreme thresholds
EXTREME_BULLISH = 55.0  # >55% bullish is extreme (contrarian sell)
HIGH_BULLISH = 45.0
EXTREME_BEARISH = 45.0  # >45% bearish is extreme (contrarian buy)
HIGH_BEARISH = 38.0


@dataclass
class AAIISentiment:
    """AAII Sentiment Survey data with computed signals."""

    survey_date: datetime
    bullish_pct: float
    neutral_pct: float
    bearish_pct: float

    # Computed metrics
    bull_bear_spread: float = 0.0  # bullish - bearish
    historical_avg_bullish: float = AAII_HISTORICAL_BULLISH
    historical_avg_bearish: float = AAII_HISTORICAL_BEARISH

    # Deviation from historical
    bullish_deviation: float = 0.0  # How far from historical average
    bearish_deviation: float = 0.0

    # Historical percentile (where current reading sits)
    bullish_percentile: float = 0.5
    bearish_percentile: float = 0.5

    # Signals
    signal: str = "neutral"  # "extreme_bullish", "bullish", "neutral", "bearish", "extreme_bearish"
    contrarian_signal: float = 0.0  # -1 (contrarian sell/too bullish) to +1 (contrarian buy/too bearish)
    signal_strength: float = 0.0  # 0 to 1

    # Metadata
    source: str = "aaii"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "survey_date": self.survey_date.isoformat(),
            "bullish_pct": self.bullish_pct,
            "neutral_pct": self.neutral_pct,
            "bearish_pct": self.bearish_pct,
            "bull_bear_spread": self.bull_bear_spread,
            "historical_avg_bullish": self.historical_avg_bullish,
            "historical_avg_bearish": self.historical_avg_bearish,
            "bullish_deviation": self.bullish_deviation,
            "bearish_deviation": self.bearish_deviation,
            "bullish_percentile": self.bullish_percentile,
            "bearish_percentile": self.bearish_percentile,
            "signal": self.signal,
            "contrarian_signal": self.contrarian_signal,
            "signal_strength": self.signal_strength,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AAIISentiment":
        """Create from dictionary."""
        return cls(
            survey_date=datetime.fromisoformat(d["survey_date"]),
            bullish_pct=d["bullish_pct"],
            neutral_pct=d["neutral_pct"],
            bearish_pct=d["bearish_pct"],
            bull_bear_spread=d.get("bull_bear_spread", 0.0),
            historical_avg_bullish=d.get("historical_avg_bullish", AAII_HISTORICAL_BULLISH),
            historical_avg_bearish=d.get("historical_avg_bearish", AAII_HISTORICAL_BEARISH),
            bullish_deviation=d.get("bullish_deviation", 0.0),
            bearish_deviation=d.get("bearish_deviation", 0.0),
            bullish_percentile=d.get("bullish_percentile", 0.5),
            bearish_percentile=d.get("bearish_percentile", 0.5),
            signal=d.get("signal", "neutral"),
            contrarian_signal=d.get("contrarian_signal", 0.0),
            signal_strength=d.get("signal_strength", 0.0),
            source=d.get("source", "aaii"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_extreme(self) -> bool:
        """Returns True if sentiment is at extreme levels."""
        return self.signal in ("extreme_bullish", "extreme_bearish")


class AAIISentimentSource:
    """
    Fetch AAII Individual Investor Sentiment Survey data.

    The survey is published weekly on Thursdays, so we cache for 24 hours
    and check for updates.
    """

    name = "aaii_sentiment"

    # AAII doesn't have a public API, so we use cached/estimated data
    # In production, this would scrape from aaii.com/sentimentsurvey
    AAII_URL = "https://www.aaii.com/sentimentsurvey"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "aaii")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, tuple[datetime, AAIISentiment]] = {}
        self._history: list[tuple[datetime, float, float]] = []  # (date, bullish, bearish)

        # Load cached history if available
        self._load_history()

    def _load_history(self) -> None:
        """Load historical data from cache file."""
        history_file = self.cache_dir / "aaii_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                self._history = [
                    (datetime.fromisoformat(d[0]), d[1], d[2])
                    for d in data
                ]
            except Exception as e:
                logger.warning(f"Failed to load AAII history: {e}")

    def _save_history(self) -> None:
        """Save historical data to cache file."""
        history_file = self.cache_dir / "aaii_history.json"
        try:
            data = [
                (d[0].isoformat(), d[1], d[2])
                for d in self._history[-52:]  # Keep 1 year
            ]
            with open(history_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save AAII history: {e}")

    def _check_cache(self) -> Optional[AAIISentiment]:
        """Check if cached data is still valid."""
        cache_key = "aaii_sentiment"
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug("AAII sentiment cache hit")
                return data
        return None

    def _update_cache(self, data: AAIISentiment) -> None:
        """Update cache with new data."""
        self._cache["aaii_sentiment"] = (datetime.now(), data)

        # Add to history if new date
        if not self._history or data.survey_date.date() != self._history[-1][0].date():
            self._history.append((data.survey_date, data.bullish_pct, data.bearish_pct))
            self._save_history()

    async def get_sentiment(self) -> AAIISentiment:
        """
        Get current AAII sentiment data.

        Returns AAIISentiment with survey results and signals.
        """
        # Check cache first
        cached = self._check_cache()
        if cached:
            return cached

        try:
            # Try to fetch from AAII website
            raw_data = await self._fetch_aaii_data()

            # Compute signals
            data = self._compute_signals(raw_data)

            # Update cache
            self._update_cache(data)

            return data

        except Exception as e:
            logger.warning(f"Failed to fetch AAII data: {e}")
            # Return estimated data based on market conditions
            return self._get_estimated_sentiment()

    async def _fetch_aaii_data(self) -> AAIISentiment:
        """
        Fetch AAII sentiment data.

        Note: AAII website requires JavaScript, so we use a fallback approach.
        In production, this would use a proper scraping setup or paid data feed.
        """
        # Try to load from cache file first (most recent saved data)
        cache_file = self.cache_dir / "aaii_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return AAIISentiment.from_dict(data)
            except Exception:
                pass

        # If no cache, return estimated values
        # In a real implementation, this would scrape or use an API
        logger.info("Using estimated AAII sentiment (no fresh data available)")
        return self._get_estimated_sentiment()

    def _get_estimated_sentiment(self) -> AAIISentiment:
        """
        Return estimated sentiment based on typical values.

        This is a fallback when live data isn't available.
        The values should be updated weekly with actual survey results.
        """
        # Default to slightly bullish (typical for bull markets)
        # In practice, this would be updated with actual survey data
        today = datetime.now()

        # Find last Thursday
        days_since_thursday = (today.weekday() - 3) % 7
        last_thursday = today - timedelta(days=days_since_thursday)

        return AAIISentiment(
            survey_date=last_thursday,
            bullish_pct=40.0,  # Slightly above historical
            neutral_pct=30.0,
            bearish_pct=30.0,  # Slightly below historical
            source="estimated",
        )

    def _compute_signals(self, data: AAIISentiment) -> AAIISentiment:
        """Compute sentiment signals from raw data."""

        # Bull-bear spread
        data.bull_bear_spread = data.bullish_pct - data.bearish_pct

        # Deviation from historical averages
        data.bullish_deviation = data.bullish_pct - AAII_HISTORICAL_BULLISH
        data.bearish_deviation = data.bearish_pct - AAII_HISTORICAL_BEARISH

        # Calculate percentiles from history
        if self._history:
            bullish_values = sorted([h[1] for h in self._history])
            bearish_values = sorted([h[2] for h in self._history])

            bullish_rank = sum(1 for v in bullish_values if v < data.bullish_pct)
            bearish_rank = sum(1 for v in bearish_values if v < data.bearish_pct)

            data.bullish_percentile = bullish_rank / len(bullish_values) if bullish_values else 0.5
            data.bearish_percentile = bearish_rank / len(bearish_values) if bearish_values else 0.5

        # Classify signal based on bullish percentage (primary driver)
        if data.bullish_pct >= EXTREME_BULLISH:
            data.signal = "extreme_bullish"
            data.contrarian_signal = -0.9  # Strong contrarian sell
            data.signal_strength = min(1.0, (data.bullish_pct - EXTREME_BULLISH) / 10 + 0.7)
        elif data.bullish_pct >= HIGH_BULLISH:
            data.signal = "bullish"
            data.contrarian_signal = -0.4  # Moderate contrarian sell
            data.signal_strength = (data.bullish_pct - HIGH_BULLISH) / (EXTREME_BULLISH - HIGH_BULLISH) * 0.3 + 0.3
        elif data.bearish_pct >= EXTREME_BEARISH:
            data.signal = "extreme_bearish"
            data.contrarian_signal = 0.9  # Strong contrarian buy
            data.signal_strength = min(1.0, (data.bearish_pct - EXTREME_BEARISH) / 10 + 0.7)
        elif data.bearish_pct >= HIGH_BEARISH:
            data.signal = "bearish"
            data.contrarian_signal = 0.4  # Moderate contrarian buy
            data.signal_strength = (data.bearish_pct - HIGH_BEARISH) / (EXTREME_BEARISH - HIGH_BEARISH) * 0.3 + 0.3
        else:
            data.signal = "neutral"
            data.contrarian_signal = 0.0
            data.signal_strength = 0.0

        # Adjust signal based on bull-bear spread
        # Very positive spread (>20) is more bearish for contrarians
        # Very negative spread (<-10) is more bullish for contrarians
        if data.bull_bear_spread > 20:
            data.contrarian_signal = min(-0.5, data.contrarian_signal - 0.2)
        elif data.bull_bear_spread < -10:
            data.contrarian_signal = max(0.5, data.contrarian_signal + 0.2)

        data.last_updated = datetime.now()
        return data

    def save_latest(self, data: AAIISentiment) -> None:
        """Save latest AAII data to cache file."""
        cache_file = self.cache_dir / "aaii_latest.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(data.to_dict(), f, indent=2)
            logger.info(f"Saved AAII data to {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save AAII data: {e}")

    def update_survey(
        self,
        survey_date: datetime,
        bullish_pct: float,
        neutral_pct: float,
        bearish_pct: float,
    ) -> AAIISentiment:
        """
        Manually update with new survey results.

        Use this to input weekly survey data.
        """
        data = AAIISentiment(
            survey_date=survey_date,
            bullish_pct=bullish_pct,
            neutral_pct=neutral_pct,
            bearish_pct=bearish_pct,
            source="manual_update",
        )
        data = self._compute_signals(data)
        self.save_latest(data)
        self._update_cache(data)
        return data

    def get_signal(self) -> float:
        """
        Get the contrarian signal synchronously.

        Returns:
            Float from -1 (too bullish/contrarian sell) to +1 (too bearish/contrarian buy)
        """
        cached = self._check_cache()
        if cached:
            return cached.contrarian_signal
        return 0.0

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache.clear()


# Convenience functions
async def get_aaii_sentiment() -> AAIISentiment:
    """Get current AAII sentiment data."""
    source = AAIISentimentSource()
    try:
        return await source.get_sentiment()
    finally:
        await source.close()


async def get_aaii_signal() -> float:
    """
    Get AAII contrarian signal.

    Returns:
        -1 to +1: negative = too bullish (contrarian sell), positive = too bearish (contrarian buy)
    """
    data = await get_aaii_sentiment()
    return data.contrarian_signal


if __name__ == "__main__":
    # Test the source
    async def main():
        source = AAIISentimentSource()
        data = await source.get_sentiment()
        print(f"Survey Date: {data.survey_date.date()}")
        print(f"Bullish: {data.bullish_pct:.1f}% (avg: {data.historical_avg_bullish:.1f}%)")
        print(f"Neutral: {data.neutral_pct:.1f}%")
        print(f"Bearish: {data.bearish_pct:.1f}% (avg: {data.historical_avg_bearish:.1f}%)")
        print(f"Bull-Bear Spread: {data.bull_bear_spread:.1f}%")
        print(f"Signal: {data.signal}")
        print(f"Contrarian Signal: {data.contrarian_signal:.2f}")
        print(f"Source: {data.source}")
        await source.close()

    asyncio.run(main())
