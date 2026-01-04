"""Execution modeling for realistic trade simulation.

Provides accurate slippage, market impact, and fill simulation for backtesting
and paper trading. Designed with budget traders in mind - focuses on spread
costs rather than market impact for small order sizes.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from ...core import Order, OrderSide, OrderType, Symbol

logger = logging.getLogger(__name__)


class FillType(str, Enum):
    """Type of order fill."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class ExecutionVenue(str, Enum):
    """Execution venue type."""

    EXCHANGE = "exchange"
    DARK_POOL = "dark_pool"
    MARKET_MAKER = "market_maker"


@dataclass
class MarketState:
    """Current market state for execution modeling."""

    symbol: Symbol
    bid: float
    ask: float
    last: float
    bid_size: int = 100
    ask_size: int = 100
    volume: float = 0  # Today's volume so far
    avg_daily_volume: float = 1_000_000
    volatility: float = 0.02  # Daily volatility
    spread_bps: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.spread_bps is None:
            self.spread_bps = ((self.ask - self.bid) / self.mid) * 10000

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @classmethod
    def from_quote(cls, symbol: str, bid: float, ask: float, **kwargs) -> "MarketState":
        """Create from bid/ask quote."""
        return cls(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=(bid + ask) / 2,
            **kwargs,
        )

    @classmethod
    def from_price(
        cls,
        symbol: str,
        price: float,
        spread_bps: float = 5.0,
        **kwargs,
    ) -> "MarketState":
        """Create from single price with estimated spread."""
        half_spread = price * (spread_bps / 10000 / 2)
        return cls(
            symbol=symbol,
            bid=price - half_spread,
            ask=price + half_spread,
            last=price,
            spread_bps=spread_bps,
            **kwargs,
        )


@dataclass
class SimulatedFill:
    """Result of simulating an order fill."""

    order: Order
    fill_type: FillType
    fill_price: float
    fill_quantity: float
    slippage: float  # Price slippage in dollars
    slippage_bps: float  # Slippage in basis points
    market_impact: float  # Market impact cost
    spread_cost: float  # Cost of crossing spread
    total_cost: float  # Total execution cost
    fill_time: datetime = field(default_factory=datetime.now)
    venue: ExecutionVenue = ExecutionVenue.EXCHANGE
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fill_value(self) -> float:
        """Total value of fill."""
        return self.fill_price * self.fill_quantity

    @property
    def effective_price(self) -> float:
        """Effective price including all costs."""
        if self.fill_quantity == 0:
            return 0
        return self.fill_price + (self.total_cost / self.fill_quantity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.order.symbol,
            "side": self.order.side.value,
            "fill_type": self.fill_type.value,
            "fill_price": self.fill_price,
            "fill_quantity": self.fill_quantity,
            "slippage_bps": self.slippage_bps,
            "spread_cost": self.spread_cost,
            "market_impact": self.market_impact,
            "total_cost": self.total_cost,
            "fill_time": self.fill_time.isoformat(),
        }


@dataclass
class ExecutionModelConfig:
    """Configuration for execution model."""

    # Spread costs
    default_spread_bps: float = 5.0  # Default bid-ask spread in bps
    spread_crossing_pct: float = 0.5  # How much of spread we pay (0.5 = half)

    # Slippage
    base_slippage_bps: float = 1.0  # Minimum slippage
    volatility_slippage_mult: float = 0.5  # Multiplier for vol-based slippage

    # Market impact (for larger orders)
    impact_coefficient: float = 0.1  # Square-root impact coefficient
    impact_threshold_pct: float = 0.01  # Only apply impact above this % of ADV

    # Fill simulation
    partial_fill_probability: float = 0.05  # Chance of partial fill
    min_fill_pct: float = 0.5  # Minimum fill if partial

    # Budget trader optimizations
    use_fractional: bool = True  # Alpaca fractional shares
    min_order_value: float = 1.0  # Minimum order value ($1)


class ExecutionModel:
    """
    Execution model for realistic trade simulation.

    Designed for budget traders using Alpaca with fractional shares.
    Focuses on spread costs (the main cost for small orders) rather
    than market impact (negligible for small sizes).

    Key features:
    - Spread-based slippage for small orders
    - Volume-adjusted impact for larger orders
    - Volatility-aware execution
    - Partial fill simulation
    """

    def __init__(self, config: ExecutionModelConfig | None = None):
        """
        Initialize execution model.

        Args:
            config: Model configuration
        """
        self.config = config or ExecutionModelConfig()

    def estimate_slippage(
        self,
        order: Order,
        market_state: MarketState,
    ) -> tuple[float, float]:
        """
        Estimate slippage for an order.

        Args:
            order: The order to estimate slippage for
            market_state: Current market state

        Returns:
            Tuple of (slippage in dollars, slippage in bps)
        """
        quantity = float(order.quantity)
        mid_price = market_state.mid

        # Component 1: Spread-based slippage
        spread_slippage = self._spread_slippage(order, market_state)

        # Component 2: Volatility-based slippage
        vol_slippage = self._volatility_slippage(market_state)

        # Component 3: Size-based slippage (only for larger orders)
        size_slippage = self._size_slippage(order, market_state)

        # Total slippage
        total_slippage_bps = (
            spread_slippage + vol_slippage + size_slippage + self.config.base_slippage_bps
        )

        slippage_dollars = mid_price * quantity * (total_slippage_bps / 10000)

        return slippage_dollars, total_slippage_bps

    def _spread_slippage(self, order: Order, market_state: MarketState) -> float:
        """Calculate spread-based slippage in bps."""
        spread_bps = market_state.spread_bps or self.config.default_spread_bps

        # Market orders cross the spread
        if order.order_type == OrderType.MARKET:
            return spread_bps * self.config.spread_crossing_pct

        # Limit orders may or may not cross
        if order.order_type == OrderType.LIMIT and order.limit_price:
            limit = float(order.limit_price)
            mid = market_state.mid

            if order.side == OrderSide.BUY:
                if limit >= market_state.ask:
                    return spread_bps * self.config.spread_crossing_pct
                elif limit > mid:
                    # Partial spread crossing
                    cross_pct = (limit - mid) / (market_state.ask - mid)
                    return spread_bps * self.config.spread_crossing_pct * cross_pct
            else:  # SELL
                if limit <= market_state.bid:
                    return spread_bps * self.config.spread_crossing_pct
                elif limit < mid:
                    cross_pct = (mid - limit) / (mid - market_state.bid)
                    return spread_bps * self.config.spread_crossing_pct * cross_pct

        return 0.0

    def _volatility_slippage(self, market_state: MarketState) -> float:
        """Calculate volatility-based slippage in bps."""
        # Daily vol to per-trade vol (assume ~10 minute execution)
        minutes_per_day = 390
        execution_minutes = 10
        per_trade_vol = market_state.volatility * np.sqrt(execution_minutes / minutes_per_day)

        return per_trade_vol * 10000 * self.config.volatility_slippage_mult

    def _size_slippage(self, order: Order, market_state: MarketState) -> float:
        """Calculate size-based slippage (market impact) in bps."""
        quantity = float(order.quantity)
        adv = market_state.avg_daily_volume

        # Participation rate
        participation = quantity / adv

        # Only apply impact above threshold
        if participation < self.config.impact_threshold_pct:
            return 0.0

        # Square-root market impact model
        impact_bps = self.config.impact_coefficient * np.sqrt(participation) * 10000

        return impact_bps

    def estimate_market_impact(
        self,
        order: Order,
        market_state: MarketState,
    ) -> float:
        """
        Estimate market impact for an order.

        Uses Almgren-Chriss style square-root impact model.

        Args:
            order: The order
            market_state: Market state

        Returns:
            Estimated market impact in dollars
        """
        quantity = float(order.quantity)
        price = market_state.mid
        adv = market_state.avg_daily_volume

        # For budget traders, impact is typically negligible
        participation = quantity / adv

        if participation < self.config.impact_threshold_pct:
            return 0.0

        # Square-root impact
        impact_pct = self.config.impact_coefficient * np.sqrt(participation)
        impact_dollars = price * quantity * impact_pct

        return impact_dollars

    def simulate_fill(
        self,
        order: Order,
        market_state: MarketState,
        allow_partial: bool = True,
    ) -> SimulatedFill:
        """
        Simulate filling an order.

        Args:
            order: The order to fill
            market_state: Current market state
            allow_partial: Whether to allow partial fills

        Returns:
            SimulatedFill with execution details
        """
        quantity = float(order.quantity)

        # Determine fill type
        fill_type, fill_quantity = self._determine_fill(
            order, market_state, allow_partial
        )

        if fill_type == FillType.NONE:
            return SimulatedFill(
                order=order,
                fill_type=FillType.NONE,
                fill_price=0.0,
                fill_quantity=0.0,
                slippage=0.0,
                slippage_bps=0.0,
                market_impact=0.0,
                spread_cost=0.0,
                total_cost=0.0,
            )

        # Calculate execution price
        fill_price = self._calculate_fill_price(order, market_state)

        # Calculate costs
        slippage, slippage_bps = self.estimate_slippage(order, market_state)
        market_impact = self.estimate_market_impact(order, market_state)

        # Spread cost
        spread_cost = (market_state.spread / 2) * fill_quantity

        # Total cost
        total_cost = slippage + market_impact

        return SimulatedFill(
            order=order,
            fill_type=fill_type,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            slippage=slippage,
            slippage_bps=slippage_bps,
            market_impact=market_impact,
            spread_cost=spread_cost,
            total_cost=total_cost,
            metadata={
                "mid_price": market_state.mid,
                "spread_bps": market_state.spread_bps,
                "volatility": market_state.volatility,
            },
        )

    def _determine_fill(
        self,
        order: Order,
        market_state: MarketState,
        allow_partial: bool,
    ) -> tuple[FillType, float]:
        """Determine fill type and quantity."""
        quantity = float(order.quantity)

        # Market orders always fill (in simulation)
        if order.order_type == OrderType.MARKET:
            if allow_partial and np.random.random() < self.config.partial_fill_probability:
                fill_pct = np.random.uniform(self.config.min_fill_pct, 1.0)
                return FillType.PARTIAL, quantity * fill_pct
            return FillType.FULL, quantity

        # Limit orders
        if order.order_type == OrderType.LIMIT and order.limit_price:
            limit = float(order.limit_price)

            if order.side == OrderSide.BUY:
                if limit >= market_state.ask:
                    return FillType.FULL, quantity
                elif limit >= market_state.bid:
                    # Might get partial fill
                    if np.random.random() < 0.5:
                        fill_pct = np.random.uniform(0.3, 0.8)
                        return FillType.PARTIAL, quantity * fill_pct
                    return FillType.NONE, 0.0
                else:
                    return FillType.NONE, 0.0
            else:  # SELL
                if limit <= market_state.bid:
                    return FillType.FULL, quantity
                elif limit <= market_state.ask:
                    if np.random.random() < 0.5:
                        fill_pct = np.random.uniform(0.3, 0.8)
                        return FillType.PARTIAL, quantity * fill_pct
                    return FillType.NONE, 0.0
                else:
                    return FillType.NONE, 0.0

        # Stop orders trigger then become market
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if order.stop_price:
                stop = float(order.stop_price)
                if order.side == OrderSide.BUY and market_state.last >= stop:
                    return FillType.FULL, quantity
                elif order.side == OrderSide.SELL and market_state.last <= stop:
                    return FillType.FULL, quantity

        return FillType.NONE, 0.0

    def _calculate_fill_price(
        self,
        order: Order,
        market_state: MarketState,
    ) -> float:
        """Calculate the fill price including slippage."""
        mid = market_state.mid

        # Base price depends on side
        if order.side == OrderSide.BUY:
            base_price = market_state.ask
        else:
            base_price = market_state.bid

        # For limit orders, price is capped at limit
        if order.order_type == OrderType.LIMIT and order.limit_price:
            limit = float(order.limit_price)
            if order.side == OrderSide.BUY:
                base_price = min(base_price, limit)
            else:
                base_price = max(base_price, limit)

        # Add volatility-based slippage
        vol_slip = self._volatility_slippage(market_state) / 10000 * mid
        if order.side == OrderSide.BUY:
            return base_price + vol_slip
        else:
            return base_price - vol_slip

    def estimate_execution_cost(
        self,
        orders: list[Order],
        market_states: dict[Symbol, MarketState],
    ) -> dict[str, Any]:
        """
        Estimate total execution cost for a batch of orders.

        Args:
            orders: List of orders
            market_states: Market state for each symbol

        Returns:
            Summary of execution costs
        """
        total_slippage = 0.0
        total_impact = 0.0
        total_spread = 0.0
        total_value = 0.0

        for order in orders:
            if order.symbol not in market_states:
                continue

            market = market_states[order.symbol]
            fill = self.simulate_fill(order, market, allow_partial=False)

            total_slippage += fill.slippage
            total_impact += fill.market_impact
            total_spread += fill.spread_cost
            total_value += fill.fill_value

        return {
            "total_slippage": total_slippage,
            "total_impact": total_impact,
            "total_spread": total_spread,
            "total_cost": total_slippage + total_impact,
            "total_value": total_value,
            "cost_bps": (total_slippage + total_impact) / total_value * 10000 if total_value > 0 else 0,
            "num_orders": len(orders),
        }


class BudgetExecutionModel(ExecutionModel):
    """
    Execution model optimized for budget traders ($200-$2000 accounts).

    Key differences from standard model:
    - Ignores market impact (negligible for small orders)
    - Focuses on spread costs
    - Accounts for fractional share trading
    - Uses conservative slippage estimates
    """

    def __init__(self):
        """Initialize with budget-optimized config."""
        config = ExecutionModelConfig(
            default_spread_bps=10.0,  # Conservative spread estimate
            spread_crossing_pct=0.5,
            base_slippage_bps=2.0,
            volatility_slippage_mult=0.3,
            impact_coefficient=0.0,  # Ignore impact for small orders
            impact_threshold_pct=1.0,  # Effectively disable impact
            partial_fill_probability=0.02,  # Lower partial fill chance
            use_fractional=True,
            min_order_value=1.0,
        )
        super().__init__(config)

    def estimate_market_impact(
        self,
        order: Order,
        market_state: MarketState,
    ) -> float:
        """Budget traders have negligible market impact."""
        return 0.0

    def estimate_total_cost_bps(
        self,
        price: float,
        volatility: float = 0.02,
        spread_bps: float = 10.0,
    ) -> float:
        """
        Quick estimate of total execution cost in basis points.

        Args:
            price: Stock price
            volatility: Daily volatility
            spread_bps: Bid-ask spread in bps

        Returns:
            Estimated total cost in bps
        """
        spread_cost = spread_bps * self.config.spread_crossing_pct
        vol_cost = volatility * 10000 * self.config.volatility_slippage_mult * 0.1
        base_cost = self.config.base_slippage_bps

        return spread_cost + vol_cost + base_cost
