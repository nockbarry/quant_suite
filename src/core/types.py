"""Common type definitions for the quant suite."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, TypeAlias

import pandas as pd
from pydantic import Field


# Type aliases for clarity
Symbol: TypeAlias = str
Price: TypeAlias = Decimal
Quantity: TypeAlias = Decimal
Percentage: TypeAlias = float
Timestamp: TypeAlias = datetime

# Annotated types with constraints
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
UnitFloat = Annotated[float, Field(ge=0, le=1)]
SignalStrength = Annotated[float, Field(ge=-1, le=1)]


class AssetType(str, Enum):
    """Types of tradeable assets."""

    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    FOREX = "forex"
    OPTION = "option"
    FUTURE = "future"


class Timeframe(str, Enum):
    """Trading timeframes."""

    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1M"

    @property
    def minutes(self) -> int:
        """Return timeframe in minutes."""
        mapping = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080,
            "1M": 43200,
        }
        return mapping[self.value]


class Direction(str, Enum):
    """Trading direction."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderType(str, Enum):
    """Order execution types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MarketRegime(str, Enum):
    """Market regime classifications."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"


class SignalType(str, Enum):
    """Types of trading signals."""

    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"
    REBALANCE = "rebalance"


# DataFrame type hints for OHLCV data
OHLCVColumns = ["open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame) -> bool:
    """Validate that a DataFrame has required OHLCV columns."""
    required = set(OHLCVColumns)
    return required.issubset(set(df.columns.str.lower()))
