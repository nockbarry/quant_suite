"""Transaction cost models for backtesting."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd


@dataclass
class CostModel(ABC):
    """Abstract base class for transaction cost models."""

    @abstractmethod
    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """
        Calculate transaction costs.

        Args:
            price: Execution price
            quantity: Trade quantity
            side: 'buy' or 'sell'

        Returns:
            Total transaction cost
        """
        ...


@dataclass
class PercentageCost(CostModel):
    """
    Percentage-based cost model.

    Charges a fixed percentage of trade value as commission/slippage.
    """

    commission_pct: float = 0.001  # 0.1%
    slippage_pct: float = 0.0005  # 0.05%
    min_commission: float = 1.0  # $1 minimum

    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """Calculate percentage-based costs."""
        notional = abs(price * quantity)

        # Commission
        commission = max(notional * self.commission_pct, self.min_commission)

        # Slippage (adverse price movement)
        slippage = notional * self.slippage_pct

        return commission + slippage


@dataclass
class TieredCost(CostModel):
    """
    Tiered cost model with volume-based discounts.

    Commission rates decrease as trading volume increases.
    """

    tiers: list[tuple[float, float]]  # (volume_threshold, rate)
    slippage_pct: float = 0.0005
    min_commission: float = 1.0

    def __post_init__(self) -> None:
        # Sort tiers by threshold descending
        self.tiers = sorted(self.tiers, key=lambda x: x[0], reverse=True)

    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """Calculate tiered costs."""
        notional = abs(price * quantity)

        # Find applicable tier
        rate = self.tiers[-1][1]  # Default to lowest tier
        for threshold, tier_rate in self.tiers:
            if notional >= threshold:
                rate = tier_rate
                break

        commission = max(notional * rate, self.min_commission)
        slippage = notional * self.slippage_pct

        return commission + slippage


@dataclass
class SpreadCost(CostModel):
    """
    Spread-based cost model.

    Models costs based on bid-ask spread.
    """

    half_spread_pct: float = 0.0005  # Half the spread
    commission_pct: float = 0.0001

    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """Calculate spread-based costs."""
        notional = abs(price * quantity)

        # Spread cost (pay half spread on each side)
        spread_cost = notional * self.half_spread_pct

        # Commission
        commission = notional * self.commission_pct

        return spread_cost + commission


@dataclass
class MarketImpactCost(CostModel):
    """
    Market impact cost model.

    Models price impact based on order size relative to volume.
    Uses square-root market impact model.
    """

    commission_pct: float = 0.001
    impact_coefficient: float = 0.1
    daily_volume: float = 1_000_000  # Default daily volume

    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """Calculate market impact costs."""
        notional = abs(price * quantity)

        # Commission
        commission = notional * self.commission_pct

        # Market impact (square-root model)
        participation_rate = abs(quantity) / self.daily_volume
        impact = self.impact_coefficient * (participation_rate ** 0.5) * price * abs(quantity)

        return commission + impact


@dataclass
class ZeroCost(CostModel):
    """Zero cost model for testing."""

    def calculate(
        self,
        price: float,
        quantity: float,
        side: str,
    ) -> float:
        """No costs."""
        return 0.0


def estimate_slippage(
    price: float,
    quantity: float,
    volatility: float,
    avg_daily_volume: float,
    timeframe_minutes: int = 1,
) -> float:
    """
    Estimate slippage based on market microstructure.

    Args:
        price: Current price
        quantity: Trade quantity
        volatility: Annualized volatility
        avg_daily_volume: Average daily volume
        timeframe_minutes: Execution timeframe in minutes

    Returns:
        Estimated slippage in price terms
    """
    # Participation rate
    minutes_per_day = 390  # US market hours
    expected_volume = avg_daily_volume * (timeframe_minutes / minutes_per_day)
    participation = abs(quantity) / max(expected_volume, 1)

    # Volatility-based component (per-minute vol)
    minute_vol = volatility / (252 ** 0.5 * minutes_per_day ** 0.5)

    # Combine participation and volatility
    slippage_pct = minute_vol * (participation ** 0.5)

    return price * slippage_pct
