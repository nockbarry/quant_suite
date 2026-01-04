"""Alpaca broker integration for paper and live trading."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from ...core import Fill, Order, OrderSide, OrderStatus, OrderType, Position, Symbol
from .base import (
    AccountInfo,
    Broker,
    BrokerError,
    BrokerStatus,
    ConnectionError,
    InsufficientFundsError,
    InvalidOrderError,
    MarketClosedError,
    OrderError,
    Quote,
)

logger = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    """
    Alpaca broker integration.

    Supports both paper trading and live trading via Alpaca's API.
    Paper trading uses paper-api.alpaca.markets.
    Live trading uses api.alpaca.markets.
    """

    name = "alpaca"
    supports_short = True
    supports_fractional = True
    supports_crypto = True

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: If True, use paper trading API
            max_retries: Maximum retries for API calls
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.max_retries = max_retries

        self._api: Any = None
        self._trading_client: Any = None
        self._data_client: Any = None
        self._status = BrokerStatus.DISCONNECTED

        # Base URLs
        self._base_url = (
            "https://paper-api.alpaca.markets"
            if paper
            else "https://api.alpaca.markets"
        )

    async def connect(self) -> bool:
        """Connect to Alpaca API."""
        self._status = BrokerStatus.CONNECTING

        try:
            # Import alpaca-trade-api
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

            # Initialize clients
            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )

            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )

            # Verify connection by getting account
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None, self._trading_client.get_account
            )

            if account:
                self._status = BrokerStatus.CONNECTED
                logger.info(
                    f"Connected to Alpaca {'paper' if self.paper else 'live'} trading"
                )
                return True

        except ImportError:
            logger.error("alpaca-py package not installed. Run: pip install alpaca-py")
            self._status = BrokerStatus.ERROR
            raise ConnectionError("alpaca-py package not installed")

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            self._status = BrokerStatus.ERROR
            raise ConnectionError(f"Failed to connect: {e}")

        return False

    async def disconnect(self) -> None:
        """Disconnect from Alpaca."""
        self._trading_client = None
        self._data_client = None
        self._status = BrokerStatus.DISCONNECTED
        logger.info("Disconnected from Alpaca")

    async def get_status(self) -> BrokerStatus:
        """Get connection status."""
        return self._status

    async def get_account(self) -> AccountInfo:
        """Get account information from Alpaca."""
        self._ensure_connected()

        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(
            None, self._trading_client.get_account
        )

        return AccountInfo(
            account_id=account.account_number,
            cash=Decimal(str(account.cash)),
            portfolio_value=Decimal(str(account.portfolio_value)),
            buying_power=Decimal(str(account.buying_power)),
            currency=account.currency,
            margin_enabled=account.shorting_enabled,
            day_trade_count=account.daytrade_count,
            pattern_day_trader=account.pattern_day_trader,
            trading_blocked=account.trading_blocked,
            metadata={
                "equity": str(account.equity),
                "last_equity": str(account.last_equity),
                "multiplier": str(account.multiplier),
                "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
            },
        )

    async def get_positions(self) -> dict[Symbol, Position]:
        """Get all positions."""
        self._ensure_connected()

        loop = asyncio.get_event_loop()
        alpaca_positions = await loop.run_in_executor(
            None, self._trading_client.get_all_positions
        )

        positions = {}
        for pos in alpaca_positions:
            symbol = pos.symbol
            positions[symbol] = Position(
                symbol=symbol,
                quantity=Decimal(str(pos.qty)),
                entry_price=Decimal(str(pos.avg_entry_price)),
                current_price=Decimal(str(pos.current_price)),
                entry_time=datetime.now(),  # Alpaca doesn't provide entry time
                metadata={
                    "market_value": str(pos.market_value),
                    "unrealized_pl": str(pos.unrealized_pl),
                    "unrealized_plpc": str(pos.unrealized_plpc),
                    "side": pos.side.value if hasattr(pos.side, 'value') else str(pos.side),
                },
            )

        return positions

    async def get_position(self, symbol: Symbol) -> Position | None:
        """Get position for a symbol."""
        self._ensure_connected()

        try:
            loop = asyncio.get_event_loop()
            pos = await loop.run_in_executor(
                None,
                lambda: self._trading_client.get_open_position(symbol),
            )

            return Position(
                symbol=symbol,
                quantity=Decimal(str(pos.qty)),
                entry_price=Decimal(str(pos.avg_entry_price)),
                current_price=Decimal(str(pos.current_price)),
                entry_time=datetime.now(),
                metadata={
                    "market_value": str(pos.market_value),
                    "unrealized_pl": str(pos.unrealized_pl),
                },
            )
        except Exception:
            return None

    async def submit_order(self, order: Order) -> Order:
        """Submit order to Alpaca."""
        self._ensure_connected()

        from alpaca.trading.requests import (
            MarketOrderRequest,
            LimitOrderRequest,
            StopOrderRequest,
            StopLimitOrderRequest,
        )
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce

        # Map order side
        side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL

        # Build order request based on type
        try:
            if order.order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
            elif order.order_type == OrderType.LIMIT:
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=float(order.limit_price),
                )
            elif order.order_type == OrderType.STOP:
                request = StopOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    stop_price=float(order.stop_price),
                )
            elif order.order_type == OrderType.STOP_LIMIT:
                request = StopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    stop_price=float(order.stop_price),
                    limit_price=float(order.limit_price),
                )
            else:
                raise InvalidOrderError(f"Unsupported order type: {order.order_type}")

            # Submit order
            loop = asyncio.get_event_loop()
            alpaca_order = await loop.run_in_executor(
                None,
                lambda: self._trading_client.submit_order(request),
            )

            # Update order with Alpaca response
            order.order_id = alpaca_order.id
            order.status = self._map_order_status(alpaca_order.status)
            order.submitted_at = alpaca_order.submitted_at
            order.metadata["alpaca_order_id"] = alpaca_order.id
            order.metadata["client_order_id"] = alpaca_order.client_order_id

            logger.info(f"Order submitted: {order.order_id} - {order.symbol} {order.side.value} {order.quantity}")
            return order

        except Exception as e:
            error_msg = str(e)
            if "insufficient" in error_msg.lower():
                raise InsufficientFundsError(error_msg, order)
            elif "market" in error_msg.lower() and "closed" in error_msg.lower():
                raise MarketClosedError(error_msg)
            else:
                raise OrderError(f"Order submission failed: {e}", order)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        self._ensure_connected()

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._trading_client.cancel_order_by_id(order_id),
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        self._ensure_connected()

        try:
            loop = asyncio.get_event_loop()
            alpaca_order = await loop.run_in_executor(
                None,
                lambda: self._trading_client.get_order_by_id(order_id),
            )

            return self._convert_alpaca_order(alpaca_order)
        except Exception:
            return None

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        self._ensure_connected()

        loop = asyncio.get_event_loop()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        alpaca_orders = await loop.run_in_executor(
            None,
            lambda: self._trading_client.get_orders(request),
        )

        return [self._convert_alpaca_order(o) for o in alpaca_orders]

    async def get_quote(self, symbol: Symbol) -> Quote | None:
        """Get real-time quote."""
        self._ensure_connected()

        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            loop = asyncio.get_event_loop()
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = await loop.run_in_executor(
                None,
                lambda: self._data_client.get_stock_latest_quote(request),
            )

            if symbol in quotes:
                q = quotes[symbol]
                return Quote(
                    symbol=symbol,
                    bid=Decimal(str(q.bid_price)),
                    ask=Decimal(str(q.ask_price)),
                    bid_size=q.bid_size,
                    ask_size=q.ask_size,
                    last=Decimal(str(q.bid_price)),  # Use bid as last
                    last_size=0,
                    volume=0,
                    timestamp=q.timestamp,
                )
        except Exception as e:
            logger.warning(f"Failed to get quote for {symbol}: {e}")

        return None

    async def get_quotes(self, symbols: list[Symbol]) -> dict[Symbol, Quote]:
        """Get quotes for multiple symbols."""
        self._ensure_connected()

        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            loop = asyncio.get_event_loop()
            request = StockLatestQuoteRequest(symbol_or_symbols=symbols)
            alpaca_quotes = await loop.run_in_executor(
                None,
                lambda: self._data_client.get_stock_latest_quote(request),
            )

            quotes = {}
            for symbol, q in alpaca_quotes.items():
                quotes[symbol] = Quote(
                    symbol=symbol,
                    bid=Decimal(str(q.bid_price)),
                    ask=Decimal(str(q.ask_price)),
                    bid_size=q.bid_size,
                    ask_size=q.ask_size,
                    last=Decimal(str(q.bid_price)),
                    last_size=0,
                    volume=0,
                    timestamp=q.timestamp,
                )
            return quotes

        except Exception as e:
            logger.warning(f"Failed to get quotes: {e}")
            return {}

    def _ensure_connected(self) -> None:
        """Ensure broker is connected."""
        if self._status != BrokerStatus.CONNECTED:
            raise ConnectionError("Not connected to Alpaca")

    def _map_order_status(self, alpaca_status: Any) -> OrderStatus:
        """Map Alpaca order status to our OrderStatus."""
        status_str = alpaca_status.value if hasattr(alpaca_status, 'value') else str(alpaca_status)
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "partially_filled": OrderStatus.PARTIAL,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "rejected": OrderStatus.REJECTED,
            "pending_cancel": OrderStatus.SUBMITTED,
            "pending_replace": OrderStatus.SUBMITTED,
        }
        return mapping.get(status_str.lower(), OrderStatus.PENDING)

    def _convert_alpaca_order(self, alpaca_order: Any) -> Order:
        """Convert Alpaca order to our Order type."""
        # Map order type
        order_type_str = alpaca_order.order_type.value if hasattr(alpaca_order.order_type, 'value') else str(alpaca_order.order_type)
        order_type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        order_type = order_type_map.get(order_type_str.lower(), OrderType.MARKET)

        # Map side
        side_str = alpaca_order.side.value if hasattr(alpaca_order.side, 'value') else str(alpaca_order.side)
        side = OrderSide.BUY if side_str.lower() == "buy" else OrderSide.SELL

        return Order(
            symbol=alpaca_order.symbol,
            side=side,
            quantity=Decimal(str(alpaca_order.qty)),
            order_type=order_type,
            limit_price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
            stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
            status=self._map_order_status(alpaca_order.status),
            order_id=alpaca_order.id,
            filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal(0),
            filled_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
            metadata={
                "alpaca_order_id": alpaca_order.id,
                "client_order_id": alpaca_order.client_order_id,
            },
        )
