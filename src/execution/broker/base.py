"""Base broker interface for order execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from ...core import Fill, Order, OrderSide, OrderStatus, OrderType, Position, Symbol


class BrokerStatus(str, Enum):
    """Broker connection status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


@dataclass
class AccountInfo:
    """Broker account information."""

    account_id: str
    cash: Decimal
    portfolio_value: Decimal
    buying_power: Decimal
    currency: str = "USD"
    margin_enabled: bool = False
    day_trade_count: int = 0
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def cash_available(self) -> Decimal:
        """Cash available for trading."""
        return self.buying_power


@dataclass
class Quote:
    """Real-time quote for a symbol."""

    symbol: Symbol
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    last: Decimal
    last_size: int
    volume: int
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        """Mid-point price."""
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        """Bid-ask spread."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid."""
        if self.mid == 0:
            return 0.0
        return float(self.spread / self.mid)


class Broker(ABC):
    """
    Abstract base class for broker integrations.

    Provides a common interface for order execution, position management,
    and account information across different brokers.
    """

    name: str = "base_broker"
    supports_short: bool = True
    supports_fractional: bool = False
    supports_crypto: bool = False

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the broker.

        Returns:
            True if connection successful
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker."""
        ...

    @abstractmethod
    async def get_status(self) -> BrokerStatus:
        """
        Get current connection status.

        Returns:
            BrokerStatus enum value
        """
        ...

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """
        Get account information.

        Returns:
            AccountInfo with balances and status
        """
        ...

    @abstractmethod
    async def get_positions(self) -> dict[Symbol, Position]:
        """
        Get all current positions.

        Returns:
            Dictionary mapping symbols to positions
        """
        ...

    @abstractmethod
    async def get_position(self, symbol: Symbol) -> Position | None:
        """
        Get position for a specific symbol.

        Args:
            symbol: The asset symbol

        Returns:
            Position if exists, None otherwise
        """
        ...

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """
        Submit an order for execution.

        Args:
            order: Order to submit

        Returns:
            Order with updated status and broker order ID
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: The order ID to cancel

        Returns:
            True if cancellation successful
        """
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order | None:
        """
        Get order by ID.

        Args:
            order_id: The order ID

        Returns:
            Order if found, None otherwise
        """
        ...

    @abstractmethod
    async def get_open_orders(self) -> list[Order]:
        """
        Get all open/pending orders.

        Returns:
            List of open orders
        """
        ...

    @abstractmethod
    async def get_quote(self, symbol: Symbol) -> Quote | None:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: The asset symbol

        Returns:
            Quote if available, None otherwise
        """
        ...

    @abstractmethod
    async def get_quotes(self, symbols: list[Symbol]) -> dict[Symbol, Quote]:
        """
        Get real-time quotes for multiple symbols.

        Args:
            symbols: List of symbols

        Returns:
            Dictionary mapping symbols to quotes
        """
        ...

    async def market_buy(
        self,
        symbol: Symbol,
        quantity: Decimal,
        **kwargs: Any,
    ) -> Order:
        """
        Submit a market buy order.

        Args:
            symbol: Symbol to buy
            quantity: Quantity to buy
            **kwargs: Additional order parameters

        Returns:
            Submitted order
        """
        order = Order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
            **kwargs,
        )
        return await self.submit_order(order)

    async def market_sell(
        self,
        symbol: Symbol,
        quantity: Decimal,
        **kwargs: Any,
    ) -> Order:
        """
        Submit a market sell order.

        Args:
            symbol: Symbol to sell
            quantity: Quantity to sell
            **kwargs: Additional order parameters

        Returns:
            Submitted order
        """
        order = Order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
            **kwargs,
        )
        return await self.submit_order(order)

    async def limit_buy(
        self,
        symbol: Symbol,
        quantity: Decimal,
        limit_price: Decimal,
        **kwargs: Any,
    ) -> Order:
        """
        Submit a limit buy order.

        Args:
            symbol: Symbol to buy
            quantity: Quantity to buy
            limit_price: Maximum price to pay
            **kwargs: Additional order parameters

        Returns:
            Submitted order
        """
        order = Order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            **kwargs,
        )
        return await self.submit_order(order)

    async def limit_sell(
        self,
        symbol: Symbol,
        quantity: Decimal,
        limit_price: Decimal,
        **kwargs: Any,
    ) -> Order:
        """
        Submit a limit sell order.

        Args:
            symbol: Symbol to sell
            quantity: Quantity to sell
            limit_price: Minimum price to receive
            **kwargs: Additional order parameters

        Returns:
            Submitted order
        """
        order = Order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            **kwargs,
        )
        return await self.submit_order(order)

    async def close_position(self, symbol: Symbol) -> Order | None:
        """
        Close entire position for a symbol.

        Args:
            symbol: Symbol to close

        Returns:
            Closing order, or None if no position
        """
        position = await self.get_position(symbol)
        if position is None or position.quantity == 0:
            return None

        if position.quantity > 0:
            return await self.market_sell(symbol, abs(position.quantity))
        else:
            return await self.market_buy(symbol, abs(position.quantity))

    async def close_all_positions(self) -> list[Order]:
        """
        Close all open positions.

        Returns:
            List of closing orders
        """
        positions = await self.get_positions()
        orders = []

        for symbol in positions:
            order = await self.close_position(symbol)
            if order:
                orders.append(order)

        return orders


class BrokerError(Exception):
    """Base exception for broker errors."""

    pass


class ConnectionError(BrokerError):
    """Raised when broker connection fails."""

    pass


class OrderError(BrokerError):
    """Raised when order submission fails."""

    def __init__(self, message: str, order: Order | None = None):
        super().__init__(message)
        self.order = order


class InsufficientFundsError(OrderError):
    """Raised when account has insufficient funds."""

    pass


class InvalidOrderError(OrderError):
    """Raised when order parameters are invalid."""

    pass


class MarketClosedError(BrokerError):
    """Raised when market is closed."""

    pass
