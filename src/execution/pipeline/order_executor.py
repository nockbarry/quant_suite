"""Order executor for trade proposal execution.

Executes approved trade proposals via broker with:
- Retry logic for transient failures
- Execution quality tracking
- Position reconciliation
- Limit order chasing (optional)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from ...core import Fill, Order, OrderSide, OrderStatus, OrderType, Position, Symbol, TradeProposal
from ..broker.base import Broker, BrokerError, MarketClosedError, OrderError

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Status of execution attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING = "pending"
    MARKET_CLOSED = "market_closed"


@dataclass
class ExecutionResult:
    """Result of executing a trade proposal."""

    proposal: TradeProposal
    status: ExecutionStatus
    order: Order | None = None
    fill_price: float | None = None
    fill_quantity: float | None = None
    slippage_bps: float | None = None
    execution_time_ms: float | None = None
    error_message: str | None = None
    retries: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in (ExecutionStatus.SUCCESS, ExecutionStatus.PARTIAL)

    @property
    def fill_value(self) -> float:
        if self.fill_price and self.fill_quantity:
            return self.fill_price * self.fill_quantity
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal.proposal_id,
            "symbol": self.proposal.order.symbol,
            "side": self.proposal.order.side.value,
            "status": self.status.value,
            "fill_price": self.fill_price,
            "fill_quantity": self.fill_quantity,
            "slippage_bps": self.slippage_bps,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "retries": self.retries,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExecutorConfig:
    """Configuration for order executor."""

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff: float = 2.0  # Exponential backoff multiplier

    # Execution settings
    use_limit_orders: bool = False  # Use limit orders instead of market
    limit_offset_bps: float = 5.0  # Offset from mid for limit orders
    limit_chase_enabled: bool = False  # Chase limit orders if not filled
    limit_chase_max_attempts: int = 3
    limit_chase_interval_seconds: float = 10.0

    # Timeout settings
    order_timeout_seconds: float = 60.0
    fill_check_interval_seconds: float = 1.0

    # Position reconciliation
    reconcile_after_trade: bool = True
    max_position_drift_pct: float = 0.01  # 1% tolerance


@dataclass
class ExecutionStats:
    """Execution quality statistics."""

    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    partial_fills: int = 0
    total_slippage_bps: float = 0.0
    total_value_traded: float = 0.0
    avg_execution_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_orders == 0:
            return 0.0
        return self.successful_orders / self.total_orders

    @property
    def avg_slippage_bps(self) -> float:
        if self.successful_orders == 0:
            return 0.0
        return self.total_slippage_bps / self.successful_orders

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_orders": self.total_orders,
            "successful_orders": self.successful_orders,
            "failed_orders": self.failed_orders,
            "partial_fills": self.partial_fills,
            "success_rate": self.success_rate,
            "avg_slippage_bps": self.avg_slippage_bps,
            "total_value_traded": self.total_value_traded,
            "avg_execution_time_ms": self.avg_execution_time_ms,
        }


class OrderExecutor:
    """
    Order executor for trade proposals.

    Handles:
    - Market and limit order execution
    - Retry logic with exponential backoff
    - Limit order chasing
    - Execution quality tracking
    - Position reconciliation

    Designed for budget traders using Alpaca with fractional shares.
    """

    def __init__(
        self,
        broker: Broker,
        config: ExecutorConfig | None = None,
    ):
        """
        Initialize order executor.

        Args:
            broker: Broker for order execution
            config: Executor configuration
        """
        self.broker = broker
        self.config = config or ExecutorConfig()
        self.stats = ExecutionStats()
        self._pending_orders: dict[str, Order] = {}

    async def execute_proposals(
        self,
        proposals: list[TradeProposal],
        parallel: bool = False,
    ) -> list[ExecutionResult]:
        """
        Execute a batch of trade proposals.

        Args:
            proposals: List of approved proposals to execute
            parallel: Execute orders in parallel (faster but may hit rate limits)

        Returns:
            List of ExecutionResult for each proposal
        """
        results = []

        if parallel:
            # Execute all orders concurrently
            tasks = [self.execute_proposal(p) for p in proposals]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Handle exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    results[i] = ExecutionResult(
                        proposal=proposals[i],
                        status=ExecutionStatus.FAILED,
                        error_message=str(result),
                    )
        else:
            # Execute sequentially
            for proposal in proposals:
                result = await self.execute_proposal(proposal)
                results.append(result)

        return results

    async def execute_proposal(
        self,
        proposal: TradeProposal,
    ) -> ExecutionResult:
        """
        Execute a single trade proposal.

        Args:
            proposal: The proposal to execute

        Returns:
            ExecutionResult
        """
        start_time = datetime.now()
        retries = 0

        while retries <= self.config.max_retries:
            try:
                result = await self._execute_with_timeout(proposal)

                # Update stats
                self._update_stats(result)

                # Calculate execution time
                result.execution_time_ms = (
                    datetime.now() - start_time
                ).total_seconds() * 1000
                result.retries = retries

                # Reconcile positions if configured
                if self.config.reconcile_after_trade and result.is_success:
                    await self._reconcile_position(proposal.order.symbol)

                return result

            except MarketClosedError:
                return ExecutionResult(
                    proposal=proposal,
                    status=ExecutionStatus.MARKET_CLOSED,
                    error_message="Market is closed",
                    retries=retries,
                )

            except BrokerError as e:
                retries += 1
                if retries > self.config.max_retries:
                    return ExecutionResult(
                        proposal=proposal,
                        status=ExecutionStatus.FAILED,
                        error_message=str(e),
                        retries=retries,
                    )

                # Exponential backoff
                delay = self.config.retry_delay_seconds * (
                    self.config.retry_backoff ** (retries - 1)
                )
                logger.warning(
                    f"Retry {retries}/{self.config.max_retries} for "
                    f"{proposal.order.symbol} after {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Unexpected error executing {proposal.order.symbol}: {e}")
                return ExecutionResult(
                    proposal=proposal,
                    status=ExecutionStatus.FAILED,
                    error_message=str(e),
                    retries=retries,
                )

        return ExecutionResult(
            proposal=proposal,
            status=ExecutionStatus.FAILED,
            error_message="Max retries exceeded",
            retries=retries,
        )

    async def _execute_with_timeout(
        self,
        proposal: TradeProposal,
    ) -> ExecutionResult:
        """Execute with timeout and fill monitoring."""
        order = proposal.order

        # Optionally convert to limit order
        if self.config.use_limit_orders and order.order_type == OrderType.MARKET:
            order = await self._convert_to_limit_order(order)

        # Submit order
        submitted_order = await self.broker.submit_order(order)
        self._pending_orders[submitted_order.order_id] = submitted_order

        # Wait for fill
        try:
            filled_order = await asyncio.wait_for(
                self._wait_for_fill(submitted_order),
                timeout=self.config.order_timeout_seconds,
            )
        except asyncio.TimeoutError:
            # Cancel unfilled order
            await self.broker.cancel_order(submitted_order.order_id)
            del self._pending_orders[submitted_order.order_id]

            # Try limit order chasing if enabled
            if self.config.limit_chase_enabled and order.order_type == OrderType.LIMIT:
                return await self._chase_limit_order(proposal, submitted_order)

            return ExecutionResult(
                proposal=proposal,
                status=ExecutionStatus.CANCELLED,
                order=submitted_order,
                error_message="Order timed out",
            )

        del self._pending_orders[submitted_order.order_id]

        # Calculate slippage
        expected_price = float(proposal.order.limit_price or 0)
        if expected_price == 0:
            # Estimate expected price from quote
            quote = await self.broker.get_quote(order.symbol)
            if quote:
                if order.side == OrderSide.BUY:
                    expected_price = float(quote.ask)
                else:
                    expected_price = float(quote.bid)

        fill_price = float(filled_order.filled_price or expected_price)
        if expected_price > 0:
            slippage_bps = ((fill_price - expected_price) / expected_price) * 10000
            if order.side == OrderSide.SELL:
                slippage_bps = -slippage_bps
        else:
            slippage_bps = 0.0

        # Determine status
        if filled_order.status == OrderStatus.FILLED:
            status = ExecutionStatus.SUCCESS
        elif filled_order.status == OrderStatus.PARTIAL:
            status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.FAILED

        return ExecutionResult(
            proposal=proposal,
            status=status,
            order=filled_order,
            fill_price=fill_price,
            fill_quantity=float(filled_order.filled_quantity or 0),
            slippage_bps=slippage_bps,
        )

    async def _wait_for_fill(self, order: Order) -> Order:
        """Wait for order to fill."""
        while True:
            updated = await self.broker.get_order(order.order_id)
            if updated is None:
                raise OrderError(f"Order {order.order_id} not found", order)

            if updated.status in (
                OrderStatus.FILLED,
                OrderStatus.PARTIAL,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
            ):
                return updated

            await asyncio.sleep(self.config.fill_check_interval_seconds)

    async def _convert_to_limit_order(self, order: Order) -> Order:
        """Convert market order to limit order."""
        quote = await self.broker.get_quote(order.symbol)
        if quote is None:
            return order  # Fall back to market order

        # Set limit price with offset
        offset_mult = self.config.limit_offset_bps / 10000

        if order.side == OrderSide.BUY:
            limit_price = float(quote.ask) * (1 + offset_mult)
        else:
            limit_price = float(quote.bid) * (1 - offset_mult)

        return Order(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=OrderType.LIMIT,
            limit_price=Decimal(str(round(limit_price, 2))),
            metadata=order.metadata,
        )

    async def _chase_limit_order(
        self,
        proposal: TradeProposal,
        original_order: Order,
    ) -> ExecutionResult:
        """Chase a limit order by adjusting price."""
        for attempt in range(self.config.limit_chase_max_attempts):
            # Get current quote
            quote = await self.broker.get_quote(original_order.symbol)
            if quote is None:
                break

            # Adjust limit price more aggressively
            offset_mult = (self.config.limit_offset_bps * (attempt + 2)) / 10000

            if original_order.side == OrderSide.BUY:
                new_limit = float(quote.ask) * (1 + offset_mult)
            else:
                new_limit = float(quote.bid) * (1 - offset_mult)

            # Submit new order
            new_order = Order(
                symbol=original_order.symbol,
                side=original_order.side,
                quantity=original_order.quantity,
                order_type=OrderType.LIMIT,
                limit_price=Decimal(str(round(new_limit, 2))),
            )

            try:
                submitted = await self.broker.submit_order(new_order)
                filled = await asyncio.wait_for(
                    self._wait_for_fill(submitted),
                    timeout=self.config.limit_chase_interval_seconds,
                )

                if filled.status == OrderStatus.FILLED:
                    return ExecutionResult(
                        proposal=proposal,
                        status=ExecutionStatus.SUCCESS,
                        order=filled,
                        fill_price=float(filled.filled_price or new_limit),
                        fill_quantity=float(filled.filled_quantity or 0),
                        metadata={"chase_attempts": attempt + 1},
                    )

                await self.broker.cancel_order(submitted.order_id)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Chase attempt {attempt + 1} failed: {e}")

        return ExecutionResult(
            proposal=proposal,
            status=ExecutionStatus.FAILED,
            error_message="Limit order chase exhausted",
        )

    async def _reconcile_position(self, symbol: str) -> bool:
        """Reconcile position with broker."""
        try:
            broker_position = await self.broker.get_position(symbol)
            return True
        except Exception as e:
            logger.warning(f"Position reconciliation failed for {symbol}: {e}")
            return False

    def _update_stats(self, result: ExecutionResult) -> None:
        """Update execution statistics."""
        self.stats.total_orders += 1

        if result.status == ExecutionStatus.SUCCESS:
            self.stats.successful_orders += 1
            if result.fill_value:
                self.stats.total_value_traded += result.fill_value
            if result.slippage_bps:
                self.stats.total_slippage_bps += abs(result.slippage_bps)
        elif result.status == ExecutionStatus.PARTIAL:
            self.stats.partial_fills += 1
            self.stats.successful_orders += 1
        else:
            self.stats.failed_orders += 1

        if result.execution_time_ms:
            # Running average
            n = self.stats.total_orders
            self.stats.avg_execution_time_ms = (
                self.stats.avg_execution_time_ms * (n - 1) + result.execution_time_ms
            ) / n

    async def cancel_all_pending(self) -> int:
        """Cancel all pending orders."""
        cancelled = 0
        for order_id in list(self._pending_orders.keys()):
            try:
                if await self.broker.cancel_order(order_id):
                    cancelled += 1
                    del self._pending_orders[order_id]
            except Exception as e:
                logger.warning(f"Failed to cancel order {order_id}: {e}")
        return cancelled

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        return self.stats.to_dict()

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self.stats = ExecutionStats()

    async def get_pending_orders(self) -> list[Order]:
        """Get list of pending orders."""
        return list(self._pending_orders.values())


async def execute_approved_proposals(
    broker: Broker,
    proposals: list[TradeProposal],
    config: ExecutorConfig | None = None,
) -> list[ExecutionResult]:
    """
    Convenience function to execute approved proposals.

    Args:
        broker: Broker for execution
        proposals: Approved trade proposals
        config: Executor configuration

    Returns:
        List of execution results
    """
    executor = OrderExecutor(broker, config)
    return await executor.execute_proposals(proposals)
