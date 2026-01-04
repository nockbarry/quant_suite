"""Order management types."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .types import OrderSide, OrderStatus, OrderType, Symbol


@dataclass
class Order:
    """
    A trading order.

    Attributes:
        symbol: Asset symbol
        side: Buy or sell
        quantity: Number of units to trade
        order_type: Market, limit, stop, etc.
        limit_price: Price for limit orders
        stop_price: Price for stop orders
        status: Current order status
        strategy_name: Strategy that generated this order
    """

    symbol: Symbol
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING
    strategy_name: str = ""
    order_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_quantity: Decimal = field(default=Decimal(0))
    filled_price: Decimal | None = None
    commission: Decimal = field(default=Decimal(0))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate order parameters."""
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit orders require a limit_price")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("Stop orders require a stop_price")
        if self.order_type == OrderType.STOP_LIMIT and (
            self.limit_price is None or self.stop_price is None
        ):
            raise ValueError("Stop-limit orders require both limit_price and stop_price")

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.side == OrderSide.SELL

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """Check if order is still active (can be filled)."""
        return self.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL)

    @property
    def remaining_quantity(self) -> Decimal:
        """Quantity remaining to be filled."""
        return self.quantity - self.filled_quantity

    @property
    def fill_ratio(self) -> float:
        """Ratio of filled to total quantity."""
        if self.quantity == 0:
            return 0.0
        return float(self.filled_quantity / self.quantity)

    @property
    def notional_value(self) -> Decimal | None:
        """Notional value of the order."""
        price = self.filled_price or self.limit_price
        if price is None:
            return None
        return self.quantity * price

    def submit(self) -> None:
        """Mark order as submitted."""
        self.status = OrderStatus.SUBMITTED
        self.updated_at = datetime.now()

    def cancel(self) -> None:
        """Cancel the order."""
        if not self.is_active:
            raise ValueError(f"Cannot cancel order in status {self.status}")
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now()

    def reject(self, reason: str = "") -> None:
        """Reject the order."""
        self.status = OrderStatus.REJECTED
        self.metadata["reject_reason"] = reason
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": float(self.quantity),
            "order_type": self.order_type.value,
            "limit_price": float(self.limit_price) if self.limit_price else None,
            "stop_price": float(self.stop_price) if self.stop_price else None,
            "status": self.status.value,
            "strategy_name": self.strategy_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_quantity": float(self.filled_quantity),
            "filled_price": float(self.filled_price) if self.filled_price else None,
            "commission": float(self.commission),
        }


@dataclass
class Fill:
    """
    A fill (execution) event for an order.

    Attributes:
        order_id: ID of the order being filled
        quantity: Quantity filled in this execution
        price: Execution price
        timestamp: When the fill occurred
        commission: Commission charged
    """

    order_id: str
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    commission: Decimal = field(default=Decimal(0))
    fill_id: str = field(default_factory=lambda: str(uuid4()))
    venue: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def notional(self) -> Decimal:
        """Notional value of the fill."""
        return self.quantity * self.price

    @property
    def total_cost(self) -> Decimal:
        """Total cost including commission."""
        return self.notional + self.commission

    def to_dict(self) -> dict[str, Any]:
        """Convert fill to dictionary."""
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "timestamp": self.timestamp.isoformat(),
            "commission": float(self.commission),
            "venue": self.venue,
            "notional": float(self.notional),
        }


def apply_fill(order: Order, fill: Fill) -> None:
    """
    Apply a fill to an order, updating its state.

    Args:
        order: The order to update
        fill: The fill to apply
    """
    if fill.order_id != order.order_id:
        raise ValueError("Fill order_id does not match order")

    if not order.is_active:
        raise ValueError(f"Cannot fill order in status {order.status}")

    if fill.quantity > order.remaining_quantity:
        raise ValueError("Fill quantity exceeds remaining order quantity")

    # Update average fill price
    if order.filled_price is None:
        order.filled_price = fill.price
    else:
        total_filled = order.filled_quantity * order.filled_price + fill.quantity * fill.price
        order.filled_price = total_filled / (order.filled_quantity + fill.quantity)

    order.filled_quantity += fill.quantity
    order.commission += fill.commission
    order.updated_at = fill.timestamp

    # Update status
    if order.filled_quantity >= order.quantity:
        order.status = OrderStatus.FILLED
    else:
        order.status = OrderStatus.PARTIAL


@dataclass
class TradeProposal:
    """
    A proposed trade awaiting human approval.

    Used in human-in-the-loop execution mode.
    """

    order: Order
    reasoning: str
    expected_impact: dict[str, Any] = field(default_factory=dict)
    risk_metrics: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    proposal_id: str = field(default_factory=lambda: str(uuid4()))
    approved: bool | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None

    def approve(self, approver: str = "user") -> None:
        """Approve the trade proposal."""
        self.approved = True
        self.approved_at = datetime.now()
        self.approved_by = approver

    def reject(self, approver: str = "user") -> None:
        """Reject the trade proposal."""
        self.approved = False
        self.approved_at = datetime.now()
        self.approved_by = approver

    @property
    def is_pending(self) -> bool:
        """Check if proposal is still pending approval."""
        return self.approved is None

    def to_dict(self) -> dict[str, Any]:
        """Convert proposal to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "order": self.order.to_dict(),
            "reasoning": self.reasoning,
            "expected_impact": self.expected_impact,
            "risk_metrics": self.risk_metrics,
            "created_at": self.created_at.isoformat(),
            "approved": self.approved,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
        }
