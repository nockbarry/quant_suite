"""
Newsletter Sentiment Source (Investors Intelligence)

Tracks newsletter writer/advisor sentiment as a contrarian indicator.
Similar to AAII but from professional advisors.

Historical averages:
- Bulls: ~45%
- Bears: ~25%
- Correction: ~30%

Extreme readings (>60% bulls or >45% bears) are contrarian signals.

Data Sources:
- Yardeni Research (free charts)
- Manual weekly updates
- Fallback to estimated values
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Historical thresholds for interpretation
II_HISTORICAL_BULLS = 45.0
II_HISTORICAL_BEARS = 25.0
II_HISTORICAL_CORRECTION = 30.0

# Extreme thresholds
EXTREME_BULLISH = 60.0  # >60% bulls is extreme (contrarian sell)
HIGH_BULLISH = 52.0
EXTREME_BEARISH = 45.0  # >45% bears is extreme (contrarian buy)
HIGH_BEARISH = 35.0


@dataclass
class NewsletterSentiment:
    """Investors Intelligence newsletter sentiment data."""

    survey_date: datetime
    bulls_pct: float
    bears_pct: float
    correction_pct: float  # Expecting correction but not bear market

    # Computed metrics
    bull_bear_spread: float = 0.0
    historical_avg_bulls: float = II_HISTORICAL_BULLS
    historical_avg_bears: float = II_HISTORICAL_BEARS

    # Deviation from historical
    bulls_deviation: float = 0.0
    bears_deviation: float = 0.0

    # Historical percentile
    bulls_percentile: float = 0.5
    bears_percentile: float = 0.5

    # Signals
    signal: str = "neutral"  # "extreme_bullish", "bullish", "neutral", "bearish", "extreme_bearish"
    contrarian_signal: float = 0.0  # -1 (contrarian sell) to +1 (contrarian buy)
    signal_strength: float = 0.0  # 0 to 1

    # Metadata
    source: str = "investors_intelligence"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "survey_date": self.survey_date.isoformat(),
            "bulls_pct": self.bulls_pct,
            "bears_pct": self.bears_pct,
            "correction_pct": self.correction_pct,
            "bull_bear_spread": self.bull_bear_spread,
            "historical_avg_bulls": self.historical_avg_bulls,
            "historical_avg_bears": self.historical_avg_bears,
            "bulls_deviation": self.bulls_deviation,
            "bears_deviation": self.bears_deviation,
            "bulls_percentile": self.bulls_percentile,
            "bears_percentile": self.bears_percentile,
            "signal": self.signal,
            "contrarian_signal": self.contrarian_signal,
            "signal_strength": self.signal_strength,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NewsletterSentiment":
        return cls(
            survey_date=datetime.fromisoformat(d["survey_date"]),
            bulls_pct=d["bulls_pct"],
            bears_pct=d["bears_pct"],
            correction_pct=d["correction_pct"],
            bull_bear_spread=d.get("bull_bear_spread", 0.0),
            historical_avg_bulls=d.get("historical_avg_bulls", II_HISTORICAL_BULLS),
            historical_avg_bears=d.get("historical_avg_bears", II_HISTORICAL_BEARS),
            bulls_deviation=d.get("bulls_deviation", 0.0),
            bears_deviation=d.get("bears_deviation", 0.0),
            bulls_percentile=d.get("bulls_percentile", 0.5),
            bears_percentile=d.get("bears_percentile", 0.5),
            signal=d.get("signal", "neutral"),
            contrarian_signal=d.get("contrarian_signal", 0.0),
            signal_strength=d.get("signal_strength", 0.0),
            source=d.get("source", "investors_intelligence"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_extreme(self) -> bool:
        """Returns True if sentiment is at extreme levels."""
        return self.signal in ("extreme_bullish", "extreme_bearish")


class NewsletterSentimentSource:
    """
    Fetch Investors Intelligence newsletter sentiment data.

    Published weekly, typically on Wednesday.
    Uses cached data with manual update capability.
    """

    name = "newsletter_sentiment"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "newsletter")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, tuple[datetime, NewsletterSentiment]] = {}
        self._history: list[tuple[datetime, float, float]] = []  # (date, bulls, bears)

        # Load cached history
        self._load_history()

    def _load_history(self) -> None:
        """Load historical data from cache file."""
        history_file = self.cache_dir / "newsletter_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                self._history = [
                    (datetime.fromisoformat(d[0]), d[1], d[2])
                    for d in data
                ]
            except Exception as e:
                logger.warning(f"Failed to load newsletter history: {e}")

    def _save_history(self) -> None:
        """Save historical data to cache file."""
        history_file = self.cache_dir / "newsletter_history.json"
        try:
            data = [
                (d[0].isoformat(), d[1], d[2])
                for d in self._history[-52:]  # Keep 1 year
            ]
            with open(history_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save newsletter history: {e}")

    def _check_cache(self) -> Optional[NewsletterSentiment]:
        """Check if cached data is still valid."""
        cache_key = "newsletter_sentiment"
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug("Newsletter sentiment cache hit")
                return data

        # Check file cache
        cache_file = self.cache_dir / "newsletter_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                sentiment = NewsletterSentiment.from_dict(data)
                if datetime.now() - sentiment.last_updated < self.cache_ttl:
                    self._cache[cache_key] = (sentiment.last_updated, sentiment)
                    return sentiment
            except Exception:
                pass

        return None

    def _update_cache(self, data: NewsletterSentiment) -> None:
        """Update cache with new data."""
        self._cache["newsletter_sentiment"] = (datetime.now(), data)

        # Add to history if new date
        if not self._history or data.survey_date.date() != self._history[-1][0].date():
            self._history.append((data.survey_date, data.bulls_pct, data.bears_pct))
            self._save_history()

    async def get_sentiment(self) -> NewsletterSentiment:
        """
        Get current newsletter sentiment data.

        Returns NewsletterSentiment with survey results and signals.
        """
        # Check cache first
        cached = self._check_cache()
        if cached:
            return cached

        try:
            # Try to load from cache file
            raw_data = await self._fetch_data()

            # Compute signals
            data = self._compute_signals(raw_data)

            # Update cache
            self._update_cache(data)

            return data

        except Exception as e:
            logger.warning(f"Failed to fetch newsletter data: {e}")
            return self._get_estimated_sentiment()

    async def _fetch_data(self) -> NewsletterSentiment:
        """
        Fetch newsletter sentiment data.

        In production, this would scrape Yardeni or use a data feed.
        For now, uses cached/estimated data.
        """
        # Try to load from cache file first
        cache_file = self.cache_dir / "newsletter_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return NewsletterSentiment.from_dict(data)
            except Exception:
                pass

        logger.info("Using estimated newsletter sentiment (no fresh data available)")
        return self._get_estimated_sentiment()

    def _get_estimated_sentiment(self) -> NewsletterSentiment:
        """
        Return estimated sentiment based on typical values.

        This is a fallback when live data isn't available.
        """
        today = datetime.now()

        # Find last Wednesday (typical release day)
        days_since_wednesday = (today.weekday() - 2) % 7
        last_wednesday = today - timedelta(days=days_since_wednesday)

        return NewsletterSentiment(
            survey_date=last_wednesday,
            bulls_pct=47.0,  # Slightly above historical
            bears_pct=23.0,  # Slightly below historical
            correction_pct=30.0,
            source="estimated",
        )

    def _compute_signals(self, data: NewsletterSentiment) -> NewsletterSentiment:
        """Compute sentiment signals from raw data."""

        # Bull-bear spread
        data.bull_bear_spread = data.bulls_pct - data.bears_pct

        # Deviation from historical averages
        data.bulls_deviation = data.bulls_pct - II_HISTORICAL_BULLS
        data.bears_deviation = data.bears_pct - II_HISTORICAL_BEARS

        # Calculate percentiles from history
        if self._history:
            bulls_values = sorted([h[1] for h in self._history])
            bears_values = sorted([h[2] for h in self._history])

            bulls_rank = sum(1 for v in bulls_values if v < data.bulls_pct)
            bears_rank = sum(1 for v in bears_values if v < data.bears_pct)

            data.bulls_percentile = bulls_rank / len(bulls_values) if bulls_values else 0.5
            data.bears_percentile = bears_rank / len(bears_values) if bears_values else 0.5

        # Classify signal based on bulls percentage
        if data.bulls_pct >= EXTREME_BULLISH:
            data.signal = "extreme_bullish"
            data.contrarian_signal = -0.9  # Strong contrarian sell
            data.signal_strength = min(1.0, (data.bulls_pct - EXTREME_BULLISH) / 10 + 0.7)
        elif data.bulls_pct >= HIGH_BULLISH:
            data.signal = "bullish"
            data.contrarian_signal = -0.4  # Moderate contrarian sell
            data.signal_strength = (data.bulls_pct - HIGH_BULLISH) / (EXTREME_BULLISH - HIGH_BULLISH) * 0.3 + 0.3
        elif data.bears_pct >= EXTREME_BEARISH:
            data.signal = "extreme_bearish"
            data.contrarian_signal = 0.9  # Strong contrarian buy
            data.signal_strength = min(1.0, (data.bears_pct - EXTREME_BEARISH) / 10 + 0.7)
        elif data.bears_pct >= HIGH_BEARISH:
            data.signal = "bearish"
            data.contrarian_signal = 0.4  # Moderate contrarian buy
            data.signal_strength = (data.bears_pct - HIGH_BEARISH) / (EXTREME_BEARISH - HIGH_BEARISH) * 0.3 + 0.3
        else:
            data.signal = "neutral"
            data.contrarian_signal = 0.0
            data.signal_strength = 0.0

        # Adjust for extreme bull-bear spreads
        if data.bull_bear_spread > 35:
            data.contrarian_signal = min(-0.6, data.contrarian_signal - 0.2)
        elif data.bull_bear_spread < -5:
            data.contrarian_signal = max(0.6, data.contrarian_signal + 0.2)

        data.last_updated = datetime.now()
        return data

    def save_latest(self, data: NewsletterSentiment) -> None:
        """Save latest newsletter data to cache file."""
        cache_file = self.cache_dir / "newsletter_latest.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(data.to_dict(), f, indent=2)
            logger.info(f"Saved newsletter data to {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save newsletter data: {e}")

    def update_survey(
        self,
        survey_date: datetime,
        bulls_pct: float,
        bears_pct: float,
        correction_pct: float,
    ) -> NewsletterSentiment:
        """
        Manually update with new survey results.

        Use this to input weekly survey data.
        """
        data = NewsletterSentiment(
            survey_date=survey_date,
            bulls_pct=bulls_pct,
            bears_pct=bears_pct,
            correction_pct=correction_pct,
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
async def get_newsletter_sentiment() -> NewsletterSentiment:
    """Get current newsletter sentiment data."""
    source = NewsletterSentimentSource()
    try:
        return await source.get_sentiment()
    finally:
        await source.close()


async def get_newsletter_signal() -> float:
    """
    Get newsletter contrarian signal.

    Returns:
        -1 to +1: negative = too bullish (contrarian sell), positive = too bearish (contrarian buy)
    """
    data = await get_newsletter_sentiment()
    return data.contrarian_signal


if __name__ == "__main__":
    # Test the source
    async def main():
        source = NewsletterSentimentSource()
        data = await source.get_sentiment()
        print(f"Survey Date: {data.survey_date.date()}")
        print(f"Bulls: {data.bulls_pct:.1f}% (avg: {data.historical_avg_bulls:.1f}%)")
        print(f"Bears: {data.bears_pct:.1f}% (avg: {data.historical_avg_bears:.1f}%)")
        print(f"Correction: {data.correction_pct:.1f}%")
        print(f"Bull-Bear Spread: {data.bull_bear_spread:.1f}%")
        print(f"Signal: {data.signal}")
        print(f"Contrarian Signal: {data.contrarian_signal:.2f}")
        print(f"Source: {data.source}")
        await source.close()

    asyncio.run(main())
