"""Paper trading simulator for testing strategies without real money."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from ...core import Fill, Order, OrderSide, OrderStatus, OrderType, Position, Symbol
from .base import (
    AccountInfo,
    Broker,
    BrokerStatus,
    InsufficientFundsError,
    InvalidOrderError,
    Quote,
)

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingConfig:
    """Configuration for paper trading simulator."""

    initial_capital: Decimal = Decimal("100000")
    commission_per_share: Decimal = Decimal("0.00")
    commission_minimum: Decimal = Decimal("0.00")
    commission_percentage: Decimal = Decimal("0.001")  # 0.1%
    slippage_percentage: Decimal = Decimal("0.0005")  # 0.05%
    allow_short: bool = True
    allow_fractional: bool = True
    margin_multiplier: Decimal = Decimal("1.0")  # No margin by default


class PaperBroker(Broker):
    """
    Paper trading broker simulator.

    Simulates order execution, position tracking, and P&L calculation
    without connecting to a real broker. Useful for backtesting and
    strategy development.
    """

    name = "paper"
    supports_short = True
    supports_fractional = True
    supports_crypto = True

    def __init__(
        self,
        config: PaperTradingConfig | None = None,
        price_provider: Callable[[Symbol], Decimal | None] | None = None,
    ):
        """
        Initialize paper broker.

        Args:
            config: Paper trading configuration
            price_provider: Function to get current prices for symbols
        """
        self.config = config or PaperTradingConfig()
        self._price_provider = price_provider

        # Account state
        self._cash = self.config.initial_capital
        self._positions: dict[Symbol, Position] = {}
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._status = BrokerStatus.DISCONNECTED

        # Price cache
        self._prices: dict[Symbol, Decimal] = {}

        # Statistics
        self._total_trades = 0
        self._total_commission = Decimal("0")

    async def connect(self) -> bool:
        """Connect (always succeeds for paper trading)."""
        self._status = BrokerStatus.CONNECTED
        logger.info("Paper trading broker connected")
        return True

    async def disconnect(self) -> None:
        """Disconnect."""
        self._status = BrokerStatus.DISCONNECTED
        logger.info("Paper trading broker disconnected")

    async def get_status(self) -> BrokerStatus:
        """Get connection status."""
        return self._status

    async def get_account(self) -> AccountInfo:
        """Get account information."""
        portfolio_value = self._cash + self._get_positions_value()
        buying_power = self._cash * self.config.margin_multiplier

        return AccountInfo(
            account_id="PAPER",
            cash=self._cash,
            portfolio_value=portfolio_value,
            buying_power=buying_power,
            currency="USD",
            margin_enabled=self.config.margin_multiplier > 1,
            metadata={
                "total_trades": self._total_trades,
                "total_commission": str(self._total_commission),
                "num_positions": len(self._positions),
            },
        )

    async def get_positions(self) -> dict[Symbol, Position]:
        """Get all positions."""
        # Update current prices
        for symbol, position in self._positions.items():
            price = self._get_price(symbol)
            if price:
                position.update_price(price)

        return self._positions.copy()

    async def get_position(self, symbol: Symbol) -> Position | None:
        """Get position for a symbol."""
        position = self._positions.get(symbol)
        if position:
            price = self._get_price(symbol)
            if price:
                position.update_price(price)
        return position

    async def submit_order(self, order: Order) -> Order:
        """Submit and execute order (immediate fill for market orders)."""
        # Generate order ID
        order.order_id = str(uuid4())
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.now()

        # Validate order
        self._validate_order(order)

        # Store order
        self._orders[order.order_id] = order

        # Execute market orders immediately
        if order.order_type == OrderType.MARKET:
            await self._execute_order(order)
        else:
            # Limit/stop orders stay pending
            logger.info(f"Order pending: {order.order_id} - {order.symbol} {order.order_type.value}")

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        order = self._orders.get(order_id)
        if order is None:
            return False

        if order.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED):
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            logger.info(f"Order cancelled: {order_id}")
            return True

        return False

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return self._orders.get(order_id)

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL)
        ]

    async def get_quote(self, symbol: Symbol) -> Quote | None:
        """Get quote for a symbol."""
        price = self._get_price(symbol)
        if price is None:
            return None

        # Simulate bid/ask spread
        spread = price * self.config.slippage_percentage
        bid = price - spread / 2
        ask = price + spread / 2

        return Quote(
            symbol=symbol,
            bid=bid,
            ask=ask,
            bid_size=100,
            ask_size=100,
            last=price,
            last_size=100,
            volume=1000000,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[Symbol]) -> dict[Symbol, Quote]:
        """Get quotes for multiple symbols."""
        quotes = {}
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                quotes[symbol] = quote
        return quotes

    def set_price(self, symbol: Symbol, price: Decimal) -> None:
        """
        Set price for a symbol (for simulation).

        Args:
            symbol: The symbol
            price: The price to set
        """
        self._prices[symbol] = price

    def set_prices(self, prices: dict[Symbol, Decimal]) -> None:
        """
        Set prices for multiple symbols.

        Args:
            prices: Dictionary of symbol to price
        """
        self._prices.update(prices)

    def reset(self) -> None:
        """Reset broker to initial state."""
        self._cash = self.config.initial_capital
        self._positions.clear()
        self._orders.clear()
        self._fills.clear()
        self._total_trades = 0
        self._total_commission = Decimal("0")
        logger.info("Paper broker reset")

    def get_trade_history(self) -> list[Fill]:
        """Get all fills/trades."""
        return self._fills.copy()

    def _get_price(self, symbol: Symbol) -> Decimal | None:
        """Get current price for a symbol."""
        # Check cache first
        if symbol in self._prices:
            return self._prices[symbol]

        # Try price provider
        if self._price_provider:
            price = self._price_provider(symbol)
            if price:
                self._prices[symbol] = price
                return price

        return None

    def _get_positions_value(self) -> Decimal:
        """Calculate total value of all positions."""
        total = Decimal("0")
        for symbol, position in self._positions.items():
            price = self._get_price(symbol)
            if price:
                total += abs(position.quantity) * price
        return total

    def _validate_order(self, order: Order) -> None:
        """Validate order parameters."""
        # Check quantity
        if order.quantity <= 0:
            raise InvalidOrderError("Order quantity must be positive", order)

        # Check fractional shares
        if not self.config.allow_fractional and order.quantity != int(order.quantity):
            raise InvalidOrderError("Fractional shares not allowed", order)

        # Check short selling
        if order.side == OrderSide.SELL:
            position = self._positions.get(order.symbol)
            if position is None or position.quantity < order.quantity:
                if not self.config.allow_short:
                    raise InvalidOrderError("Short selling not allowed", order)

        # Check buying power
        if order.side == OrderSide.BUY:
            price = self._get_price(order.symbol)
            if price:
                required = order.quantity * price
                if required > self._cash * self.config.margin_multiplier:
                    raise InsufficientFundsError("Insufficient buying power", order)

    async def _execute_order(self, order: Order) -> None:
        """Execute an order."""
        price = self._get_price(order.symbol)
        if price is None:
            order.status = OrderStatus.REJECTED
            order.metadata["reject_reason"] = "No price available"
            logger.warning(f"Order rejected - no price: {order.order_id}")
            return

        # Apply slippage
        slippage = price * self.config.slippage_percentage
        if order.side == OrderSide.BUY:
            execution_price = price + slippage
        else:
            execution_price = price - slippage

        # Calculate commission
        commission = self._calculate_commission(order.quantity, execution_price)

        # Create fill
        fill = Fill(
            order_id=order.order_id,
            quantity=order.quantity,
            price=execution_price,
            timestamp=datetime.now(),
            commission=commission,
            venue="PAPER",
        )

        # Update order
        order.filled_quantity = order.quantity
        order.filled_price = execution_price
        order.commission = commission
        order.status = OrderStatus.FILLED
        order.updated_at = datetime.now()

        # Update cash
        trade_value = order.quantity * execution_price
        if order.side == OrderSide.BUY:
            self._cash -= trade_value + commission
        else:
            self._cash += trade_value - commission

        # Update position
        self._update_position(order.symbol, order.side, order.quantity, execution_price)

        # Record fill
        self._fills.append(fill)
        self._total_trades += 1
        self._total_commission += commission

        logger.info(
            f"Order filled: {order.order_id} - {order.symbol} "
            f"{order.side.value} {order.quantity} @ {execution_price}"
        )

    def _calculate_commission(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Calculate commission for a trade."""
        # Per-share commission
        per_share = quantity * self.config.commission_per_share

        # Percentage commission
        percentage = quantity * price * self.config.commission_percentage

        # Take the larger of per-share or percentage
        commission = max(per_share, percentage)

        # Apply minimum
        commission = max(commission, self.config.commission_minimum)

        return commission

    def _update_position(
        self,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Update position after a trade."""
        current = self._positions.get(symbol)

        if side == OrderSide.BUY:
            delta = quantity
        else:
            delta = -quantity

        if current is None:
            # New position
            if delta != 0:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=delta,
                    entry_price=price,
                    current_price=price,
                    entry_time=datetime.now(),
                )
        else:
            # Update existing position
            new_quantity = current.quantity + delta

            if new_quantity == 0:
                # Position closed
                del self._positions[symbol]
            elif (current.quantity > 0 and new_quantity > 0) or \
                 (current.quantity < 0 and new_quantity < 0):
                # Same direction - update average price
                if delta > 0:  # Adding to long or covering short
                    total_cost = abs(current.quantity) * current.entry_price + abs(delta) * price
                    current.entry_price = total_cost / abs(new_quantity)
                current.quantity = new_quantity
            else:
                # Direction changed
                current.quantity = new_quantity
                current.entry_price = price
                current.entry_time = datetime.now()

            current.current_price = price

    async def process_pending_orders(self) -> list[Order]:
        """
        Process pending limit/stop orders against current prices.

        Returns:
            List of orders that were executed
        """
        executed = []

        for order in list(self._orders.values()):
            if order.status not in (OrderStatus.PENDING, OrderStatus.SUBMITTED):
                continue

            price = self._get_price(order.symbol)
            if price is None:
                continue

            should_execute = False

            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and price <= order.limit_price:
                    should_execute = True
                elif order.side == OrderSide.SELL and price >= order.limit_price:
                    should_execute = True

            elif order.order_type == OrderType.STOP:
                if order.side == OrderSide.BUY and price >= order.stop_price:
                    should_execute = True
                elif order.side == OrderSide.SELL and price <= order.stop_price:
                    should_execute = True

            elif order.order_type == OrderType.STOP_LIMIT:
                # Check stop trigger first
                if order.side == OrderSide.BUY and price >= order.stop_price:
                    if price <= order.limit_price:
                        should_execute = True
                elif order.side == OrderSide.SELL and price <= order.stop_price:
                    if price >= order.limit_price:
                        should_execute = True

            if should_execute:
                await self._execute_order(order)
                executed.append(order)

        return executed
