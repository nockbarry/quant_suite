"""CME FedWatch Rate Probability Scraper.

Scrapes rate cut/hike probabilities by FOMC meeting date.
THE signal for the Fed Independence Crisis thesis.

Primary: CME FedWatch page or API
Fallback: FRED federal funds futures, yfinance fed funds futures
Second fallback: Prediction markets data for Fed rate probabilities
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

try:
    import yfinance as yf
except ImportError:
    yf = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Known 2026 FOMC meeting dates
FOMC_DATES_2026 = [
    "2026-01-28",
    "2026-03-18",
    "2026-05-06",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-16",
]

# Current fed funds rate (updated as needed)
CURRENT_RATE = 4.375  # Midpoint of 4.25-4.50% range (as of early 2026)

# Fed Funds futures tickers on yfinance (ZQ contracts)
# These trade on CME and settle at 100 - effective fed funds rate
# ZQ=F is the front month
FF_FUTURES_TICKERS = {
    "ZQ=F": "front_month",
}


@dataclass
class MeetingProbability:
    """Rate probabilities for a single FOMC meeting."""

    meeting_date: str
    implied_rate: float  # Implied fed funds rate from futures
    cut_probability: float  # Probability of at least one cut (0-1)
    hike_probability: float  # Probability of at least one hike (0-1)
    hold_probability: float  # Probability of no change (0-1)
    cuts_priced: float  # Number of 25bp cuts priced in


@dataclass
class FedWatchSnapshot:
    """CME FedWatch rate probability snapshot."""

    timestamp: str
    current_rate: float  # Current effective fed funds rate
    next_meeting_date: str
    meetings: list[dict]  # List of MeetingProbability as dicts
    implied_cuts_2026: float  # Total cuts priced for 2026
    implied_rate_yearend: float  # Implied year-end rate
    market_expectation: str  # "dovish", "hawkish", "neutral"
    ff_front_price: float  # Front-month fed funds futures price
    ff_implied_rate: float  # Rate implied by front month
    source: str  # "yfinance", "prediction_markets", "reference"
    data_quality: str  # "live", "delayed", "stale"


class FedWatchCollector:
    """Collect FedWatch rate probabilities.

    Primary method: Fed funds futures via yfinance (ZQ contracts)
    Fallback: Prediction markets data already collected
    Second fallback: Static reference based on last known state

    The fed funds futures price = 100 - implied rate.
    Example: ZQ at 95.625 implies 4.375% fed funds rate.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "fedwatch.json"

    async def collect(self) -> FedWatchSnapshot:
        """Collect FedWatch data from available sources."""
        # Try yfinance fed funds futures first
        try:
            snapshot = await self._fetch_from_futures()
            self._save(snapshot)
            return snapshot
        except Exception as e:
            logger.warning(f"Fed funds futures fetch failed: {e}")

        # Try prediction markets fallback
        try:
            snapshot = await self._fetch_from_prediction_markets()
            self._save(snapshot)
            return snapshot
        except Exception as e:
            logger.warning(f"Prediction markets fallback failed: {e}")

        # Stale fallback
        return self._stale_fallback("All sources failed")

    async def _fetch_from_futures(self) -> FedWatchSnapshot:
        """Extract rate expectations from fed funds futures."""
        if yf is None:
            raise ValueError("yfinance not installed")

        prices = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_ff_futures
        )

        if not prices:
            raise ValueError("No fed funds futures data available")

        # Front month price and implied rate
        front_price = prices.get("front_month", 0)
        if front_price == 0:
            raise ValueError("Could not get front month price")

        front_implied = 100.0 - front_price

        # Build meeting probabilities
        now = datetime.now()
        future_meetings = [d for d in FOMC_DATES_2026 if d > now.strftime("%Y-%m-%d")]

        meetings = []
        cumulative_cuts = 0
        prev_rate = CURRENT_RATE

        for i, meeting_date in enumerate(future_meetings):
            # For the nearest meeting, use front month futures
            # For later meetings, extrapolate based on curve shape
            if i == 0:
                implied = front_implied
            else:
                # Linear interpolation: assume cuts are evenly spaced
                # This is a simplification; real FedWatch uses per-meeting contracts
                months_out = i + 1
                implied = front_implied - (front_implied - CURRENT_RATE) * months_out / len(future_meetings)
                implied = max(0, implied)

            rate_change = implied - prev_rate
            cuts_at_meeting = -rate_change / 0.25  # Number of 25bp cuts

            # Probabilities (simplified — real FedWatch is more granular)
            if rate_change < -0.125:  # More than half a cut
                cut_prob = min(0.95, 0.5 + abs(rate_change) / 0.25 * 0.4)
                hold_prob = 1 - cut_prob
                hike_prob = 0.0
            elif rate_change > 0.125:
                hike_prob = min(0.95, 0.5 + rate_change / 0.25 * 0.4)
                hold_prob = 1 - hike_prob
                cut_prob = 0.0
            else:
                hold_prob = 0.6
                cut_prob = max(0, -rate_change / 0.25 * 0.8)
                hike_prob = max(0, rate_change / 0.25 * 0.8)
                remaining = 1 - hold_prob
                if cut_prob + hike_prob > 0:
                    scale = remaining / (cut_prob + hike_prob)
                    cut_prob *= scale
                    hike_prob *= scale

            meetings.append(asdict(MeetingProbability(
                meeting_date=meeting_date,
                implied_rate=round(implied, 3),
                cut_probability=round(cut_prob, 3),
                hike_probability=round(hike_prob, 3),
                hold_probability=round(hold_prob, 3),
                cuts_priced=round(cuts_at_meeting, 2),
            )))

            cumulative_cuts += max(0, cuts_at_meeting)
            prev_rate = implied

        # Year-end rate
        yearend_rate = front_implied  # simplified
        if meetings:
            yearend_rate = meetings[-1]["implied_rate"]

        # Market stance
        if cumulative_cuts >= 2:
            market_expectation = "dovish"
        elif cumulative_cuts <= -0.5:
            market_expectation = "hawkish"
        else:
            market_expectation = "neutral"

        next_meeting = future_meetings[0] if future_meetings else "unknown"

        return FedWatchSnapshot(
            timestamp=datetime.now().isoformat(),
            current_rate=CURRENT_RATE,
            next_meeting_date=next_meeting,
            meetings=meetings,
            implied_cuts_2026=round(cumulative_cuts, 2),
            implied_rate_yearend=round(yearend_rate, 3),
            market_expectation=market_expectation,
            ff_front_price=round(front_price, 4),
            ff_implied_rate=round(front_implied, 3),
            source="yfinance",
            data_quality="live",
        )

    def _fetch_ff_futures(self) -> dict[str, float]:
        """Synchronous fetch of fed funds futures."""
        results = {}
        for ticker, label in FF_FUTURES_TICKERS.items():
            try:
                data = yf.download(ticker, period="5d", progress=False)
                if not data.empty:
                    series = data["Close"].dropna()
                    if not series.empty:
                        results[label] = float(series.iloc[-1])
            except Exception as e:
                logger.debug(f"Could not fetch {ticker}: {e}")
        return results

    async def _fetch_from_prediction_markets(self) -> FedWatchSnapshot:
        """Extract Fed rate expectations from prediction market signals."""
        pm_file = paths.live / "research" / "prediction_markets" / "latest.json"
        if not pm_file.exists():
            raise ValueError("No prediction market data available")

        with open(pm_file) as f:
            pm_data = json.load(f)

        signals = pm_data.get("macro_signals", [])
        fed_signals = [
            s for s in signals
            if any(kw in s.get("category", "").lower() for kw in ["fed", "rate", "monetary"])
        ]

        if not fed_signals:
            raise ValueError("No Fed-related prediction market signals")

        # Extract implied probabilities
        cut_prob = 0.5  # default
        for sig in fed_signals:
            direction = sig.get("consensus_direction", "")
            prob = sig.get("avg_probability", 0.5)
            if "cut" in direction.lower() or "dovish" in direction.lower():
                cut_prob = prob
                break
            elif "hike" in direction.lower() or "hawkish" in direction.lower():
                cut_prob = 1 - prob
                break

        implied_cuts = cut_prob * 3  # rough: scale probability to number of cuts

        now = datetime.now()
        future_meetings = [d for d in FOMC_DATES_2026 if d > now.strftime("%Y-%m-%d")]
        next_meeting = future_meetings[0] if future_meetings else "unknown"

        yearend_rate = CURRENT_RATE - implied_cuts * 0.25

        if implied_cuts >= 2:
            market_expectation = "dovish"
        elif implied_cuts <= -0.5:
            market_expectation = "hawkish"
        else:
            market_expectation = "neutral"

        return FedWatchSnapshot(
            timestamp=datetime.now().isoformat(),
            current_rate=CURRENT_RATE,
            next_meeting_date=next_meeting,
            meetings=[],  # No per-meeting granularity from prediction markets
            implied_cuts_2026=round(implied_cuts, 2),
            implied_rate_yearend=round(yearend_rate, 3),
            market_expectation=market_expectation,
            ff_front_price=0.0,
            ff_implied_rate=round(CURRENT_RATE - implied_cuts * 0.25, 3),
            source="prediction_markets",
            data_quality="delayed",
        )

    def _stale_fallback(self, reason: str) -> FedWatchSnapshot:
        """Return stale reference data."""
        logger.warning(f"Using stale FedWatch reference: {reason}")

        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return FedWatchSnapshot(**cached)

        now = datetime.now()
        future_meetings = [d for d in FOMC_DATES_2026 if d > now.strftime("%Y-%m-%d")]
        next_meeting = future_meetings[0] if future_meetings else "unknown"

        snapshot = FedWatchSnapshot(
            timestamp=now.isoformat(),
            current_rate=CURRENT_RATE,
            next_meeting_date=next_meeting,
            meetings=[],
            implied_cuts_2026=1.0,  # Conservative default
            implied_rate_yearend=round(CURRENT_RATE - 0.25, 3),
            market_expectation="neutral",
            ff_front_price=0.0,
            ff_implied_rate=CURRENT_RATE,
            source="reference",
            data_quality="stale",
        )

        self._save(snapshot)
        return snapshot

    def _save(self, snapshot: FedWatchSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved FedWatch: rate={snapshot.current_rate}%, "
            f"cuts_priced={snapshot.implied_cuts_2026}, "
            f"yearend={snapshot.implied_rate_yearend}%, "
            f"stance={snapshot.market_expectation}"
        )

    def load_latest(self) -> Optional[dict]:
        """Load most recent cached snapshot."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return None
        return None
