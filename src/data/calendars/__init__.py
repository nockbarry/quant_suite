"""Economic and Earnings Calendar Management.

Provides tracking of:
- Earnings dates and estimates
- Economic events (Fed meetings, jobs, CPI)
- Options expiration dates
- Dividend ex-dates
"""

from .calendar_manager import (
    CalendarManager,
    Calendar,
    EarningsEvent,
    EconomicEvent,
)

__all__ = [
    "CalendarManager",
    "Calendar",
    "EarningsEvent",
    "EconomicEvent",
]
