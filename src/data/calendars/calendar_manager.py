"""Calendar Manager for trading events.

Provides:
- Earnings dates and estimates for portfolio and watchlist
- Economic events from FRED and other sources
- Options expiration tracking
- Portfolio catalyst aggregation

Usage:
    from src.data.calendars import CalendarManager

    manager = CalendarManager(
        portfolio=['SLB', 'HAL', 'VLO'],
        watchlist=['XOM', 'CVX', 'BKR']
    )

    today = manager.get_today()
    week = manager.get_week()
    catalysts = manager.get_portfolio_catalysts()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class EarningsEvent:
    """Earnings report event."""

    symbol: str
    date: date
    time: str  # "BMO" (before market open), "AMC" (after market close), "DMH" (during)
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    surprise_pct: float | None = None
    guidance: str | None = None
    is_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "time": self.time,
            "eps_estimate": self.eps_estimate,
            "eps_actual": self.eps_actual,
            "revenue_estimate": self.revenue_estimate,
            "revenue_actual": self.revenue_actual,
            "surprise_pct": self.surprise_pct,
            "guidance": self.guidance,
            "is_confirmed": self.is_confirmed,
        }

    def format_display(self) -> str:
        """Format for display."""
        est_str = f"EPS est: ${self.eps_estimate:.2f}" if self.eps_estimate else "EPS TBD"
        return f"{self.symbol} ({self.time}) - {est_str}"


@dataclass
class EconomicEvent:
    """Economic data release or Fed event."""

    name: str
    date: datetime
    importance: str  # "HIGH", "MEDIUM", "LOW"
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None
    impact: str = "neutral"  # "bullish", "bearish", "neutral"
    category: str = "economic"  # "economic", "fed", "other"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "date": self.date.isoformat(),
            "importance": self.importance,
            "previous": self.previous,
            "forecast": self.forecast,
            "actual": self.actual,
            "impact": self.impact,
            "category": self.category,
        }

    def format_display(self) -> str:
        """Format for display."""
        time_str = self.date.strftime("%H:%M") if self.date.hour > 0 else ""
        return f"{self.name} ({time_str}) - {self.importance}"


@dataclass
class DividendEvent:
    """Dividend event."""

    symbol: str
    ex_date: date
    pay_date: date | None
    amount: float
    yield_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ex_date": self.ex_date.isoformat(),
            "pay_date": self.pay_date.isoformat() if self.pay_date else None,
            "amount": self.amount,
            "yield_pct": self.yield_pct,
        }


@dataclass
class OptionsExpiryEvent:
    """Options expiration event."""

    symbol: str
    expiration: date
    strike: float
    option_type: str  # "call", "put"
    contracts: int
    current_value: float | None = None
    moneyness: str = "OTM"  # "ITM", "ATM", "OTM"
    days_to_expiry: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "strike": self.strike,
            "option_type": self.option_type,
            "contracts": self.contracts,
            "current_value": self.current_value,
            "moneyness": self.moneyness,
            "days_to_expiry": self.days_to_expiry,
        }


@dataclass
class Calendar:
    """Daily calendar of events."""

    date: date

    # Portfolio-specific events
    portfolio_earnings: list[EarningsEvent] = field(default_factory=list)
    portfolio_dividends: list[DividendEvent] = field(default_factory=list)
    portfolio_expiries: list[OptionsExpiryEvent] = field(default_factory=list)

    # Watchlist events
    watchlist_earnings: list[EarningsEvent] = field(default_factory=list)

    # Market events
    economic_events: list[EconomicEvent] = field(default_factory=list)
    fed_speakers: list[dict] = field(default_factory=list)

    # Flags
    is_options_expiry: bool = False  # Monthly or weekly expiry
    is_market_holiday: bool = False
    is_early_close: bool = False

    # Summary
    risk_events: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "portfolio_earnings": [e.to_dict() for e in self.portfolio_earnings],
            "portfolio_dividends": [d.to_dict() for d in self.portfolio_dividends],
            "portfolio_expiries": [e.to_dict() for e in self.portfolio_expiries],
            "watchlist_earnings": [e.to_dict() for e in self.watchlist_earnings],
            "economic_events": [e.to_dict() for e in self.economic_events],
            "fed_speakers": self.fed_speakers,
            "is_options_expiry": self.is_options_expiry,
            "is_market_holiday": self.is_market_holiday,
            "is_early_close": self.is_early_close,
            "risk_events": self.risk_events,
            "notes": self.notes,
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"CALENDAR - {self.date.strftime('%A, %B %d, %Y')}",
            "=" * 50,
        ]

        if self.is_market_holiday:
            lines.append("🔴 MARKET CLOSED")
            return "\n".join(lines)

        if self.is_early_close:
            lines.append("⚠️ Early Close Day")

        # Economic events
        high_impact = [e for e in self.economic_events if e.importance == "HIGH"]
        if high_impact:
            lines.extend(["", "HIGH-IMPACT EVENTS:"])
            for event in high_impact:
                lines.append(f"  🔴 {event.format_display()}")

        med_impact = [e for e in self.economic_events if e.importance == "MEDIUM"]
        if med_impact:
            lines.extend(["", "MEDIUM-IMPACT EVENTS:"])
            for event in med_impact[:3]:
                lines.append(f"  🟡 {event.format_display()}")

        # Portfolio earnings
        if self.portfolio_earnings:
            lines.extend(["", "PORTFOLIO EARNINGS:"])
            for earn in self.portfolio_earnings:
                lines.append(f"  ⭐ {earn.format_display()}")

        # Watchlist earnings
        if self.watchlist_earnings:
            lines.extend(["", "WATCHLIST EARNINGS:"])
            for earn in self.watchlist_earnings[:5]:
                lines.append(f"  📊 {earn.format_display()}")

        # Options expiries
        if self.portfolio_expiries:
            lines.extend(["", "OPTIONS EXPIRING:"])
            for exp in self.portfolio_expiries:
                lines.append(
                    f"  ⏰ {exp.symbol} ${exp.strike} {exp.option_type} ({exp.moneyness})"
                )

        if self.is_options_expiry:
            lines.append("  📅 Monthly/Weekly options expiration day")

        # Risk events
        if self.risk_events:
            lines.extend(["", "⚠️ RISK EVENTS:"])
            for risk in self.risk_events:
                lines.append(f"  - {risk}")

        return "\n".join(lines)


class CalendarManager:
    """
    Manages trading calendar events.

    Tracks earnings, economic events, options expiries,
    and other catalysts for portfolio and watchlist symbols.
    """

    def __init__(
        self,
        portfolio: list[str] | None = None,
        watchlist: list[str] | None = None,
    ):
        """
        Initialize calendar manager.

        Args:
            portfolio: Symbols currently held
            watchlist: Symbols being watched
        """
        self.portfolio = set(s.upper() for s in (portfolio or []))
        self.watchlist = set(s.upper() for s in (watchlist or []))

        # Cache
        self._earnings_cache: dict[str, EarningsEvent] = {}
        self._cache_date: date | None = None

        # Known economic events (would be fetched from API in production)
        self._static_events = self._load_static_events()

    def _load_static_events(self) -> list[EconomicEvent]:
        """Load known upcoming economic events."""
        # In production, would fetch from FRED, Investing.com, etc.
        # This provides structure for common events
        today = date.today()

        events = [
            # Weekly recurring
            EconomicEvent(
                name="Initial Jobless Claims",
                date=datetime(today.year, today.month, today.day, 8, 30),
                importance="MEDIUM",
                category="economic",
            ),
        ]

        return events

    def _get_earnings_from_yfinance(self, symbol: str) -> EarningsEvent | None:
        """Get next earnings date for symbol from yfinance."""
        if symbol in self._earnings_cache and self._cache_date == date.today():
            return self._earnings_cache[symbol]

        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar

            if calendar is not None and not calendar.empty:
                # yfinance calendar format varies
                if isinstance(calendar, pd.DataFrame):
                    if "Earnings Date" in calendar.columns:
                        earn_date = calendar["Earnings Date"].iloc[0]
                    elif len(calendar) > 0:
                        earn_date = calendar.iloc[0, 0]
                    else:
                        return None
                else:
                    return None

                if pd.isna(earn_date):
                    return None

                # Convert to date
                if isinstance(earn_date, pd.Timestamp):
                    earn_date = earn_date.date()
                elif isinstance(earn_date, datetime):
                    earn_date = earn_date.date()

                # Get estimates if available
                eps_estimate = None
                try:
                    info = ticker.info
                    eps_estimate = info.get("trailingEps")  # Use trailing as proxy
                except Exception:
                    pass

                event = EarningsEvent(
                    symbol=symbol,
                    date=earn_date,
                    time="TBD",  # yfinance doesn't always provide timing
                    eps_estimate=eps_estimate,
                    is_confirmed=True,
                )

                self._earnings_cache[symbol] = event
                return event

        except Exception as e:
            logger.debug(f"Could not get earnings for {symbol}: {e}")

        return None

    def _is_options_expiry(self, check_date: date) -> bool:
        """Check if date is monthly or weekly options expiry."""
        # Monthly expiry: 3rd Friday of month
        # Weekly expiry: Every Friday

        if check_date.weekday() != 4:  # Not Friday
            return False

        # Check if 3rd Friday (monthly expiry)
        first_day = check_date.replace(day=1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(days=14)

        return check_date == third_friday or check_date.weekday() == 4

    def _is_market_holiday(self, check_date: date) -> bool:
        """Check if date is a market holiday."""
        # Simplified list - would use proper calendar in production
        year = check_date.year
        holidays = [
            date(year, 1, 1),   # New Year's
            date(year, 7, 4),   # Independence Day
            date(year, 12, 25), # Christmas
        ]

        # MLK Day (3rd Monday of January)
        jan1 = date(year, 1, 1)
        mlk = jan1 + timedelta(days=(7 - jan1.weekday()) % 7 + 14)
        holidays.append(mlk)

        return check_date in holidays

    def update_portfolio(self, portfolio: list[str]) -> None:
        """Update portfolio symbols."""
        self.portfolio = set(s.upper() for s in portfolio)

    def update_watchlist(self, watchlist: list[str]) -> None:
        """Update watchlist symbols."""
        self.watchlist = set(s.upper() for s in watchlist)

    def get_today(self) -> Calendar:
        """Get today's calendar."""
        return self.get_calendar(date.today())

    def get_calendar(self, for_date: date) -> Calendar:
        """
        Get calendar for a specific date.

        Args:
            for_date: Date to get calendar for

        Returns:
            Calendar with all events for the date
        """
        calendar = Calendar(date=for_date)

        # Check for holiday
        calendar.is_market_holiday = self._is_market_holiday(for_date)
        if calendar.is_market_holiday:
            return calendar

        # Check for options expiry
        calendar.is_options_expiry = self._is_options_expiry(for_date)

        # Get earnings for portfolio
        for symbol in self.portfolio:
            earnings = self._get_earnings_from_yfinance(symbol)
            if earnings and earnings.date == for_date:
                calendar.portfolio_earnings.append(earnings)

        # Get earnings for watchlist
        for symbol in self.watchlist:
            earnings = self._get_earnings_from_yfinance(symbol)
            if earnings and earnings.date == for_date:
                calendar.watchlist_earnings.append(earnings)

        # Add static economic events for this date
        for event in self._static_events:
            if event.date.date() == for_date:
                calendar.economic_events.append(event)

        # Generate risk events
        if calendar.portfolio_earnings:
            calendar.risk_events.append(
                f"Earnings: {', '.join(e.symbol for e in calendar.portfolio_earnings)}"
            )

        high_impact = [e for e in calendar.economic_events if e.importance == "HIGH"]
        if high_impact:
            calendar.risk_events.extend(e.name for e in high_impact)

        if calendar.is_options_expiry:
            calendar.risk_events.append("Options expiration - potential volatility")

        return calendar

    def get_week(self) -> list[Calendar]:
        """Get calendar for the current week."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())

        calendars = []
        for i in range(5):  # Mon-Fri
            day = monday + timedelta(days=i)
            calendars.append(self.get_calendar(day))

        return calendars

    def get_earnings(self, symbol: str) -> EarningsEvent | None:
        """Get next earnings for a symbol."""
        return self._get_earnings_from_yfinance(symbol)

    def get_upcoming_earnings(self, days_ahead: int = 30) -> list[EarningsEvent]:
        """Get all upcoming earnings for portfolio and watchlist."""
        events = []
        cutoff = date.today() + timedelta(days=days_ahead)

        for symbol in self.portfolio | self.watchlist:
            earnings = self._get_earnings_from_yfinance(symbol)
            if earnings and earnings.date <= cutoff:
                events.append(earnings)

        # Sort by date
        events.sort(key=lambda x: x.date)
        return events

    def get_economic_events(self, days_ahead: int = 7) -> list[EconomicEvent]:
        """Get upcoming economic events."""
        cutoff = datetime.now() + timedelta(days=days_ahead)
        return [
            e for e in self._static_events
            if e.date <= cutoff
        ]

    def get_portfolio_catalysts(self) -> list[dict]:
        """
        Get all upcoming catalysts for portfolio.

        Returns:
            List of catalyst dicts with type, date, and description
        """
        catalysts = []
        today = date.today()
        cutoff = today + timedelta(days=30)

        # Earnings
        for symbol in self.portfolio:
            earnings = self._get_earnings_from_yfinance(symbol)
            if earnings and today <= earnings.date <= cutoff:
                catalysts.append({
                    "type": "earnings",
                    "date": earnings.date.isoformat(),
                    "symbol": symbol,
                    "description": f"{symbol} earnings ({earnings.time})",
                    "days_until": (earnings.date - today).days,
                    "importance": "HIGH",
                })

        # Options expiries (would need to track actual positions)
        # For now, just note monthly expiry dates
        for i in range(30):
            check_date = today + timedelta(days=i)
            if self._is_options_expiry(check_date) and check_date.weekday() == 4:
                # Check if it's monthly (3rd Friday)
                first_day = check_date.replace(day=1)
                first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
                third_friday = first_friday + timedelta(days=14)

                if check_date == third_friday:
                    catalysts.append({
                        "type": "options_expiry",
                        "date": check_date.isoformat(),
                        "symbol": "MARKET",
                        "description": "Monthly options expiration",
                        "days_until": i,
                        "importance": "MEDIUM",
                    })

        # Sort by date
        catalysts.sort(key=lambda x: x["date"])
        return catalysts

    def get_summary(self) -> str:
        """Get human-readable summary of upcoming events."""
        today_cal = self.get_today()
        week = self.get_week()
        catalysts = self.get_portfolio_catalysts()

        lines = [
            "CALENDAR SUMMARY",
            "=" * 50,
            "",
            "TODAY:",
            today_cal.get_summary(),
            "",
            "THIS WEEK:",
        ]

        for cal in week:
            if cal.date > date.today():
                events = []
                if cal.portfolio_earnings:
                    events.append(f"Earnings: {', '.join(e.symbol for e in cal.portfolio_earnings)}")
                if cal.is_options_expiry:
                    events.append("Options expiry")

                if events:
                    lines.append(f"  {cal.date.strftime('%a %b %d')}: {'; '.join(events)}")

        if catalysts:
            lines.extend(["", "UPCOMING CATALYSTS:"])
            for cat in catalysts[:5]:
                lines.append(f"  {cat['date']}: {cat['description']} ({cat['days_until']} days)")

        return "\n".join(lines)
