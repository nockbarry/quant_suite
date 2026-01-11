"""
Fed Funds Futures - Rate Expectations

Tracks implied probabilities for Fed rate decisions from:
- CME FedWatch tool
- Fed funds futures pricing

Provides:
- Probability of hike/cut/hold at next meeting
- Implied rate path over 6-12 months
- Hawkish/dovish signal
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


# Current Fed rate info (update as needed)
CURRENT_FED_RATE = 5.25  # Upper bound of target range
CURRENT_FED_RATE_LOWER = 5.00  # Lower bound


# Known FOMC meeting dates for 2026 (update annually)
FOMC_DATES_2026 = [
    datetime(2026, 1, 28),
    datetime(2026, 3, 18),
    datetime(2026, 5, 6),
    datetime(2026, 6, 17),
    datetime(2026, 7, 29),
    datetime(2026, 9, 16),
    datetime(2026, 11, 4),
    datetime(2026, 12, 16),
]


@dataclass
class FOMCMeeting:
    """Single FOMC meeting with rate probabilities."""

    meeting_date: datetime
    days_until: int

    # Probabilities (should sum to ~100%)
    prob_hike_25: float = 0.0  # Probability of 25bp hike
    prob_hike_50: float = 0.0  # Probability of 50bp hike
    prob_hold: float = 0.0  # Probability of no change
    prob_cut_25: float = 0.0  # Probability of 25bp cut
    prob_cut_50: float = 0.0  # Probability of 50bp cut

    # Implied rate after meeting
    implied_rate: float = CURRENT_FED_RATE

    def to_dict(self) -> dict:
        return {
            "meeting_date": self.meeting_date.isoformat(),
            "days_until": self.days_until,
            "prob_hike_25": self.prob_hike_25,
            "prob_hike_50": self.prob_hike_50,
            "prob_hold": self.prob_hold,
            "prob_cut_25": self.prob_cut_25,
            "prob_cut_50": self.prob_cut_50,
            "implied_rate": self.implied_rate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FOMCMeeting":
        return cls(
            meeting_date=datetime.fromisoformat(d["meeting_date"]),
            days_until=d["days_until"],
            prob_hike_25=d.get("prob_hike_25", 0.0),
            prob_hike_50=d.get("prob_hike_50", 0.0),
            prob_hold=d.get("prob_hold", 0.0),
            prob_cut_25=d.get("prob_cut_25", 0.0),
            prob_cut_50=d.get("prob_cut_50", 0.0),
            implied_rate=d.get("implied_rate", CURRENT_FED_RATE),
        )

    @property
    def prob_hike(self) -> float:
        """Total probability of any hike."""
        return self.prob_hike_25 + self.prob_hike_50

    @property
    def prob_cut(self) -> float:
        """Total probability of any cut."""
        return self.prob_cut_25 + self.prob_cut_50

    @property
    def direction(self) -> str:
        """Most likely direction."""
        if self.prob_hike > self.prob_hold and self.prob_hike > self.prob_cut:
            return "hike"
        elif self.prob_cut > self.prob_hold and self.prob_cut > self.prob_hike:
            return "cut"
        return "hold"


@dataclass
class FedExpectations:
    """Fed rate expectations over multiple meetings."""

    timestamp: datetime
    current_rate: float
    current_rate_lower: float

    # Next meeting
    next_meeting: FOMCMeeting

    # All upcoming meetings
    meetings: list[FOMCMeeting] = field(default_factory=list)

    # Aggregate probabilities for next meeting
    prob_hike: float = 0.0
    prob_cut: float = 0.0
    prob_hold: float = 0.0

    # Implied rates at horizons
    implied_rate_3m: float = CURRENT_FED_RATE
    implied_rate_6m: float = CURRENT_FED_RATE
    implied_rate_12m: float = CURRENT_FED_RATE

    # Total expected cuts/hikes over 12 months
    expected_cuts_12m: float = 0.0  # Number of 25bp cuts
    expected_hikes_12m: float = 0.0  # Number of 25bp hikes

    # Signal
    rate_path_signal: str = "neutral"  # "hawkish", "dovish", "neutral"
    signal_strength: float = 0.0  # 0 to 1

    # Metadata
    source: str = "estimated"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "current_rate": self.current_rate,
            "current_rate_lower": self.current_rate_lower,
            "next_meeting": self.next_meeting.to_dict(),
            "meetings": [m.to_dict() for m in self.meetings],
            "prob_hike": self.prob_hike,
            "prob_cut": self.prob_cut,
            "prob_hold": self.prob_hold,
            "implied_rate_3m": self.implied_rate_3m,
            "implied_rate_6m": self.implied_rate_6m,
            "implied_rate_12m": self.implied_rate_12m,
            "expected_cuts_12m": self.expected_cuts_12m,
            "expected_hikes_12m": self.expected_hikes_12m,
            "rate_path_signal": self.rate_path_signal,
            "signal_strength": self.signal_strength,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FedExpectations":
        meetings = [FOMCMeeting.from_dict(m) for m in d.get("meetings", [])]
        next_meeting = FOMCMeeting.from_dict(d["next_meeting"]) if "next_meeting" in d else (meetings[0] if meetings else None)

        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            current_rate=d["current_rate"],
            current_rate_lower=d["current_rate_lower"],
            next_meeting=next_meeting,
            meetings=meetings,
            prob_hike=d.get("prob_hike", 0.0),
            prob_cut=d.get("prob_cut", 0.0),
            prob_hold=d.get("prob_hold", 0.0),
            implied_rate_3m=d.get("implied_rate_3m", CURRENT_FED_RATE),
            implied_rate_6m=d.get("implied_rate_6m", CURRENT_FED_RATE),
            implied_rate_12m=d.get("implied_rate_12m", CURRENT_FED_RATE),
            expected_cuts_12m=d.get("expected_cuts_12m", 0.0),
            expected_hikes_12m=d.get("expected_hikes_12m", 0.0),
            rate_path_signal=d.get("rate_path_signal", "neutral"),
            signal_strength=d.get("signal_strength", 0.0),
            source=d.get("source", "estimated"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )


class FedFuturesSource:
    """
    Track Fed rate expectations from futures markets.

    In production, would scrape CME FedWatch or use futures data.
    For now, provides estimated/manual input capability.
    """

    name = "fed_futures"

    # CME FedWatch URL (for reference)
    CME_URL = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"

    def __init__(
        self,
        cache_ttl_hours: int = 1,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "fed")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[tuple[datetime, FedExpectations]] = None

    def _check_cache(self) -> Optional[FedExpectations]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, data = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return data

        cache_file = self.cache_dir / "fed_expectations.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                expectations = FedExpectations.from_dict(data)
                if datetime.now() - expectations.last_updated < self.cache_ttl:
                    self._cache = (expectations.last_updated, expectations)
                    return expectations
            except Exception as e:
                logger.warning(f"Failed to load Fed cache: {e}")

        return None

    def _update_cache(self, expectations: FedExpectations) -> None:
        """Update cache."""
        self._cache = (datetime.now(), expectations)

        cache_file = self.cache_dir / "fed_expectations.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(expectations.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save Fed cache: {e}")

    async def get_expectations(self) -> FedExpectations:
        """
        Get current Fed rate expectations.

        Returns:
            FedExpectations with probabilities and rate path.
        """
        cached = self._check_cache()
        if cached:
            return cached

        try:
            expectations = await self._fetch_expectations()
            expectations = self._compute_signals(expectations)
            self._update_cache(expectations)
            return expectations
        except Exception as e:
            logger.error(f"Failed to fetch Fed expectations: {e}")
            return self._get_estimated_expectations()

    async def _fetch_expectations(self) -> FedExpectations:
        """
        Fetch Fed expectations.

        In production, would scrape CME FedWatch.
        For now, returns estimated values.
        """
        cache_file = self.cache_dir / "fed_expectations.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return FedExpectations.from_dict(data)
            except Exception:
                pass

        return self._get_estimated_expectations()

    def _get_estimated_expectations(self) -> FedExpectations:
        """Generate estimated Fed expectations."""
        now = datetime.now()

        # Find next FOMC meeting
        upcoming_meetings = [d for d in FOMC_DATES_2026 if d > now]
        if not upcoming_meetings:
            # Use placeholder if no 2026 dates available
            upcoming_meetings = [now + timedelta(days=30)]

        next_meeting_date = upcoming_meetings[0]
        days_until = (next_meeting_date.date() - now.date()).days

        # Create meeting objects with estimated probabilities
        meetings = []
        for i, meeting_date in enumerate(upcoming_meetings[:8]):
            days = (meeting_date.date() - now.date()).days

            # Estimated probabilities (current market expects gradual cuts)
            if i == 0:
                # Next meeting - typically more certain
                meeting = FOMCMeeting(
                    meeting_date=meeting_date,
                    days_until=days,
                    prob_hold=70.0,
                    prob_cut_25=25.0,
                    prob_hike_25=5.0,
                    implied_rate=CURRENT_FED_RATE - 0.05,
                )
            else:
                # Future meetings - more uncertainty, lean toward cuts
                cut_prob = min(50.0 + i * 5, 70.0)
                meeting = FOMCMeeting(
                    meeting_date=meeting_date,
                    days_until=days,
                    prob_hold=100.0 - cut_prob - 5.0,
                    prob_cut_25=cut_prob,
                    prob_hike_25=5.0,
                    implied_rate=CURRENT_FED_RATE - (0.25 * (i / 2)),
                )

            meetings.append(meeting)

        # Calculate aggregate metrics
        next_meeting = meetings[0] if meetings else FOMCMeeting(
            meeting_date=next_meeting_date,
            days_until=days_until,
            prob_hold=100.0,
        )

        expectations = FedExpectations(
            timestamp=now,
            current_rate=CURRENT_FED_RATE,
            current_rate_lower=CURRENT_FED_RATE_LOWER,
            next_meeting=next_meeting,
            meetings=meetings,
            prob_hike=next_meeting.prob_hike,
            prob_cut=next_meeting.prob_cut,
            prob_hold=next_meeting.prob_hold,
            implied_rate_3m=CURRENT_FED_RATE - 0.10,
            implied_rate_6m=CURRENT_FED_RATE - 0.35,
            implied_rate_12m=CURRENT_FED_RATE - 0.75,
            expected_cuts_12m=3.0,  # Expected 75bp of cuts
            expected_hikes_12m=0.0,
            source="estimated",
        )

        return expectations

    def _compute_signals(self, expectations: FedExpectations) -> FedExpectations:
        """Compute trading signals from expectations."""

        # Rate path direction
        rate_change_12m = expectations.implied_rate_12m - expectations.current_rate

        if rate_change_12m > 0.25:
            expectations.rate_path_signal = "hawkish"
            expectations.signal_strength = min(rate_change_12m / 1.0, 1.0)
        elif rate_change_12m < -0.25:
            expectations.rate_path_signal = "dovish"
            expectations.signal_strength = min(abs(rate_change_12m) / 1.0, 1.0)
        else:
            expectations.rate_path_signal = "neutral"
            expectations.signal_strength = 0.0

        expectations.last_updated = datetime.now()
        return expectations

    def update_expectations(
        self,
        prob_hike: float,
        prob_cut: float,
        prob_hold: float,
        implied_rate_3m: float,
        implied_rate_6m: float,
        implied_rate_12m: float,
    ) -> FedExpectations:
        """
        Manually update Fed expectations.

        Use this to input current market pricing.
        """
        expectations = self._get_estimated_expectations()
        expectations.prob_hike = prob_hike
        expectations.prob_cut = prob_cut
        expectations.prob_hold = prob_hold
        expectations.implied_rate_3m = implied_rate_3m
        expectations.implied_rate_6m = implied_rate_6m
        expectations.implied_rate_12m = implied_rate_12m
        expectations.next_meeting.prob_hike_25 = prob_hike
        expectations.next_meeting.prob_cut_25 = prob_cut
        expectations.next_meeting.prob_hold = prob_hold
        expectations.source = "manual_update"

        expectations = self._compute_signals(expectations)
        self._update_cache(expectations)

        return expectations

    def get_signal(self) -> float:
        """
        Get Fed path signal synchronously.

        Returns:
            -1 to +1: negative = dovish (bullish for stocks), positive = hawkish (bearish)
        """
        cached = self._check_cache()
        if cached:
            if cached.rate_path_signal == "dovish":
                return -cached.signal_strength
            elif cached.rate_path_signal == "hawkish":
                return cached.signal_strength
        return 0.0

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_fed_expectations() -> FedExpectations:
    """Get current Fed rate expectations."""
    source = FedFuturesSource()
    try:
        return await source.get_expectations()
    finally:
        await source.close()


async def get_rate_path_signal() -> float:
    """
    Get Fed rate path signal.

    Returns:
        -1 to +1: negative = dovish (expect cuts), positive = hawkish (expect hikes)
    """
    expectations = await get_fed_expectations()
    if expectations.rate_path_signal == "dovish":
        return -expectations.signal_strength
    elif expectations.rate_path_signal == "hawkish":
        return expectations.signal_strength
    return 0.0


async def get_next_fomc_date() -> datetime:
    """Get date of next FOMC meeting."""
    expectations = await get_fed_expectations()
    return expectations.next_meeting.meeting_date


if __name__ == "__main__":
    async def main():
        source = FedFuturesSource()
        expectations = await source.get_expectations()

        print(f"Fed Expectations - {expectations.timestamp.date()}")
        print(f"Current Rate: {expectations.current_rate:.2f}%")
        print()
        print(f"Next Meeting: {expectations.next_meeting.meeting_date.date()}")
        print(f"  Days Until: {expectations.next_meeting.days_until}")
        print(f"  P(Hike): {expectations.prob_hike:.1f}%")
        print(f"  P(Hold): {expectations.prob_hold:.1f}%")
        print(f"  P(Cut):  {expectations.prob_cut:.1f}%")
        print()
        print("Rate Path:")
        print(f"  3M Implied: {expectations.implied_rate_3m:.2f}%")
        print(f"  6M Implied: {expectations.implied_rate_6m:.2f}%")
        print(f"  12M Implied: {expectations.implied_rate_12m:.2f}%")
        print()
        print(f"Signal: {expectations.rate_path_signal} (strength: {expectations.signal_strength:.2f})")

        await source.close()

    asyncio.run(main())
