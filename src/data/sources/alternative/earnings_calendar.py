"""
Earnings Calendar with Whisper Numbers

Tracks upcoming earnings releases with:
- Consensus EPS/revenue estimates
- Whisper numbers (street expectations)
- Historical surprise rates
- Implied moves from options

Data Sources:
- Yahoo Finance calendar
- EarningsWhispers (scrape)
- Options-derived implied moves
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import httpx
except ImportError:
    httpx = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class EarningsEvent:
    """Single earnings event with estimates and context."""

    symbol: str
    company_name: str
    report_date: datetime
    report_time: str  # "BMO" (before market open), "AMC" (after market close), "DMH" (during market hours)

    # Estimates
    eps_estimate: Optional[float] = None
    eps_whisper: Optional[float] = None  # Street whisper number
    revenue_estimate: Optional[float] = None  # In millions

    # Historical context
    historical_surprise_avg: Optional[float] = None  # Average EPS surprise %
    historical_beat_rate: Optional[float] = None  # % of quarters beating estimates
    historical_move_avg: Optional[float] = None  # Average earnings day move %

    # Options-derived
    implied_move: Optional[float] = None  # Implied move from straddle pricing

    # Previous quarter
    prev_eps_actual: Optional[float] = None
    prev_eps_estimate: Optional[float] = None
    prev_surprise_pct: Optional[float] = None

    # Metadata
    sector: Optional[str] = None
    market_cap: Optional[float] = None  # In billions
    source: str = "yahoo"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "report_date": self.report_date.isoformat(),
            "report_time": self.report_time,
            "eps_estimate": self.eps_estimate,
            "eps_whisper": self.eps_whisper,
            "revenue_estimate": self.revenue_estimate,
            "historical_surprise_avg": self.historical_surprise_avg,
            "historical_beat_rate": self.historical_beat_rate,
            "historical_move_avg": self.historical_move_avg,
            "implied_move": self.implied_move,
            "prev_eps_actual": self.prev_eps_actual,
            "prev_eps_estimate": self.prev_eps_estimate,
            "prev_surprise_pct": self.prev_surprise_pct,
            "sector": self.sector,
            "market_cap": self.market_cap,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EarningsEvent":
        return cls(
            symbol=d["symbol"],
            company_name=d["company_name"],
            report_date=datetime.fromisoformat(d["report_date"]),
            report_time=d["report_time"],
            eps_estimate=d.get("eps_estimate"),
            eps_whisper=d.get("eps_whisper"),
            revenue_estimate=d.get("revenue_estimate"),
            historical_surprise_avg=d.get("historical_surprise_avg"),
            historical_beat_rate=d.get("historical_beat_rate"),
            historical_move_avg=d.get("historical_move_avg"),
            implied_move=d.get("implied_move"),
            prev_eps_actual=d.get("prev_eps_actual"),
            prev_eps_estimate=d.get("prev_eps_estimate"),
            prev_surprise_pct=d.get("prev_surprise_pct"),
            sector=d.get("sector"),
            market_cap=d.get("market_cap"),
            source=d.get("source", "yahoo"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_today(self) -> bool:
        return self.report_date.date() == datetime.now().date()

    @property
    def is_tomorrow(self) -> bool:
        return self.report_date.date() == (datetime.now() + timedelta(days=1)).date()

    @property
    def days_until(self) -> int:
        return (self.report_date.date() - datetime.now().date()).days


@dataclass
class EarningsCalendar:
    """Collection of upcoming earnings events."""

    timestamp: datetime
    events: list[EarningsEvent] = field(default_factory=list)

    # Filtered views
    @property
    def today(self) -> list[EarningsEvent]:
        return [e for e in self.events if e.is_today]

    @property
    def tomorrow(self) -> list[EarningsEvent]:
        return [e for e in self.events if e.is_tomorrow]

    @property
    def this_week(self) -> list[EarningsEvent]:
        return [e for e in self.events if 0 <= e.days_until <= 7]

    @property
    def bmo_today(self) -> list[EarningsEvent]:
        """Before market open today."""
        return [e for e in self.today if e.report_time == "BMO"]

    @property
    def amc_today(self) -> list[EarningsEvent]:
        """After market close today."""
        return [e for e in self.today if e.report_time == "AMC"]

    def get_for_symbol(self, symbol: str) -> Optional[EarningsEvent]:
        """Get next earnings event for a specific symbol."""
        for event in self.events:
            if event.symbol.upper() == symbol.upper():
                return event
        return None

    def get_high_impact(self, min_market_cap: float = 10.0) -> list[EarningsEvent]:
        """Get events for large-cap stocks."""
        return [e for e in self.events if e.market_cap and e.market_cap >= min_market_cap]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EarningsCalendar":
        events = [EarningsEvent.from_dict(e) for e in d.get("events", [])]
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            events=events,
        )


class EarningsCalendarSource:
    """
    Fetch earnings calendar data from multiple sources.

    Primary: Yahoo Finance
    Enhanced with: Options implied moves, historical data
    """

    name = "earnings_calendar"

    def __init__(
        self,
        cache_ttl_hours: int = 6,
        cache_dir: Optional[Path] = None,
        lookforward_days: int = 14,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "earnings")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lookforward_days = lookforward_days
        self._cache: Optional[tuple[datetime, EarningsCalendar]] = None

    def _check_cache(self) -> Optional[EarningsCalendar]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, calendar = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return calendar

        # Check file cache
        cache_file = self.cache_dir / "earnings_calendar.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                calendar = EarningsCalendar.from_dict(data)
                if datetime.now() - calendar.timestamp < self.cache_ttl:
                    self._cache = (calendar.timestamp, calendar)
                    return calendar
            except Exception as e:
                logger.warning(f"Failed to load earnings cache: {e}")

        return None

    def _update_cache(self, calendar: EarningsCalendar) -> None:
        """Update cache with new calendar."""
        self._cache = (datetime.now(), calendar)

        cache_file = self.cache_dir / "earnings_calendar.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(calendar.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save earnings cache: {e}")

    async def get_calendar(
        self,
        symbols: Optional[list[str]] = None,
        force_refresh: bool = False,
    ) -> EarningsCalendar:
        """
        Get earnings calendar.

        Args:
            symbols: Optional list of symbols to filter.
            force_refresh: If True, ignores cache.

        Returns:
            EarningsCalendar with upcoming earnings events.
        """
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                if symbols:
                    filtered = EarningsCalendar(timestamp=cached.timestamp)
                    filtered.events = [e for e in cached.events if e.symbol in symbols]
                    return filtered
                return cached

        try:
            calendar = await self._fetch_calendar()
            self._update_cache(calendar)

            if symbols:
                filtered = EarningsCalendar(timestamp=calendar.timestamp)
                filtered.events = [e for e in calendar.events if e.symbol in symbols]
                return filtered

            return calendar

        except Exception as e:
            logger.error(f"Failed to fetch earnings calendar: {e}")
            return EarningsCalendar(timestamp=datetime.now())

    async def _fetch_calendar(self) -> EarningsCalendar:
        """Fetch earnings calendar from Yahoo Finance."""
        if yf is None:
            raise ImportError("yfinance required: pip install yfinance")

        calendar = EarningsCalendar(timestamp=datetime.now())
        loop = asyncio.get_event_loop()

        # Fetch calendar for the next N days
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=self.lookforward_days)

        try:
            # Get earnings calendar
            earnings = await loop.run_in_executor(
                None,
                lambda: yf.Ticker("SPY").calendar  # Placeholder - need to use proper calendar API
            )

            # For a real implementation, we'd use Yahoo Finance's earnings calendar API
            # For now, let's fetch for specific watchlist symbols
            watchlist = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX", "CRM"]

            for symbol in watchlist:
                try:
                    event = await self._fetch_symbol_earnings(symbol)
                    if event and event.report_date.date() <= end_date:
                        calendar.events.append(event)
                except Exception as e:
                    logger.debug(f"Failed to get earnings for {symbol}: {e}")

            # Sort by date
            calendar.events.sort(key=lambda e: e.report_date)

        except Exception as e:
            logger.warning(f"Failed to fetch earnings calendar: {e}")

        return calendar

    async def _fetch_symbol_earnings(self, symbol: str) -> Optional[EarningsEvent]:
        """Fetch earnings data for a specific symbol."""
        if yf is None:
            return None

        loop = asyncio.get_event_loop()

        try:
            ticker = yf.Ticker(symbol)

            # Get calendar info
            calendar_info = await loop.run_in_executor(None, lambda: ticker.calendar)

            if calendar_info is None or calendar_info.empty:
                return None

            # Get basic info
            info = await loop.run_in_executor(None, lambda: ticker.info)

            # Parse earnings date
            earnings_date = None
            if "Earnings Date" in calendar_info.index:
                dates = calendar_info.loc["Earnings Date"]
                if hasattr(dates, "iloc") and len(dates) > 0:
                    earnings_date = dates.iloc[0]
                elif isinstance(dates, datetime):
                    earnings_date = dates

            if earnings_date is None:
                return None

            # Determine report time (simplified - would need more data)
            report_time = "AMC"  # Default to after market close

            # Get estimates
            eps_estimate = None
            if "Earnings Average" in calendar_info.index:
                eps_estimate = float(calendar_info.loc["Earnings Average"].iloc[0])

            revenue_estimate = None
            if "Revenue Average" in calendar_info.index:
                revenue_estimate = float(calendar_info.loc["Revenue Average"].iloc[0]) / 1e6  # Convert to millions

            return EarningsEvent(
                symbol=symbol,
                company_name=info.get("shortName", symbol),
                report_date=earnings_date if isinstance(earnings_date, datetime) else datetime.now(),
                report_time=report_time,
                eps_estimate=eps_estimate,
                revenue_estimate=revenue_estimate,
                sector=info.get("sector"),
                market_cap=info.get("marketCap", 0) / 1e9 if info.get("marketCap") else None,
                source="yahoo",
            )

        except Exception as e:
            logger.debug(f"Error fetching earnings for {symbol}: {e}")
            return None

    async def get_implied_move(self, symbol: str) -> Optional[float]:
        """
        Calculate implied move from options straddle pricing.

        Returns the expected move as a percentage.
        """
        if yf is None:
            return None

        loop = asyncio.get_event_loop()

        try:
            ticker = yf.Ticker(symbol)

            # Get current price
            info = await loop.run_in_executor(None, lambda: ticker.info)
            current_price = info.get("regularMarketPrice") or info.get("previousClose")
            if not current_price:
                return None

            # Get options chain for nearest expiration
            expirations = await loop.run_in_executor(None, lambda: ticker.options)
            if not expirations:
                return None

            chain = await loop.run_in_executor(None, lambda: ticker.option_chain(expirations[0]))

            # Find ATM options
            calls = chain.calls
            puts = chain.puts

            if calls.empty or puts.empty:
                return None

            # Find strike closest to current price
            atm_strike = calls.iloc[(calls["strike"] - current_price).abs().argmin()]["strike"]

            # Get ATM call and put prices
            atm_call = calls[calls["strike"] == atm_strike].iloc[0]
            atm_put = puts[puts["strike"] == atm_strike].iloc[0]

            # Straddle price = call mid + put mid
            call_mid = (atm_call["bid"] + atm_call["ask"]) / 2
            put_mid = (atm_put["bid"] + atm_put["ask"]) / 2
            straddle_price = call_mid + put_mid

            # Implied move = straddle price / current price
            implied_move = (straddle_price / current_price) * 100

            return round(implied_move, 2)

        except Exception as e:
            logger.debug(f"Error calculating implied move for {symbol}: {e}")
            return None

    def has_earnings_soon(self, symbol: str, days: int = 7) -> bool:
        """Check if a symbol has earnings within N days."""
        cached = self._check_cache()
        if cached:
            event = cached.get_for_symbol(symbol)
            if event and event.days_until <= days:
                return True
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_earnings_calendar(days: int = 14) -> EarningsCalendar:
    """Get earnings calendar for the next N days."""
    source = EarningsCalendarSource(lookforward_days=days)
    try:
        return await source.get_calendar()
    finally:
        await source.close()


async def get_earnings_today() -> list[EarningsEvent]:
    """Get earnings events for today."""
    calendar = await get_earnings_calendar(days=1)
    return calendar.today


async def check_earnings_soon(symbol: str, days: int = 7) -> bool:
    """Check if a symbol has earnings within N days."""
    source = EarningsCalendarSource()
    try:
        return source.has_earnings_soon(symbol, days)
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = EarningsCalendarSource()
        calendar = await source.get_calendar()

        print(f"Earnings Calendar - {calendar.timestamp.date()}")
        print(f"Total events: {len(calendar.events)}")

        if calendar.today:
            print("\nToday's Earnings:")
            for e in calendar.today:
                print(f"  {e.symbol} ({e.report_time}): EPS est ${e.eps_estimate or 'N/A'}")

        if calendar.this_week:
            print(f"\nThis Week ({len(calendar.this_week)} events):")
            for e in calendar.this_week[:10]:
                print(f"  {e.report_date.strftime('%m/%d')} {e.symbol}: {e.company_name}")

        await source.close()

    asyncio.run(main())
