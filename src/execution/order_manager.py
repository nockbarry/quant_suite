"""Order manager with approval queue for human-in-the-loop trading."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from ..core import Order, OrderSide, OrderStatus, Signal, Symbol, TradeProposal
from .broker.base import Broker, OrderError

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Status of a trade proposal in the approval queue."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class QueuedProposal:
    """A trade proposal in the approval queue."""

    proposal: TradeProposal
    status: ApprovalStatus = ApprovalStatus.PENDING
    queued_at: datetime = field(default_factory=datetime.now)
    processed_at: datetime | None = None
    processed_by: str | None = None
    rejection_reason: str | None = None
    execution_result: Order | None = None

    @property
    def age_seconds(self) -> float:
        """Time since proposal was queued."""
        return (datetime.now() - self.queued_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal.proposal_id,
            "order": self.proposal.order.to_dict(),
            "reasoning": self.proposal.reasoning,
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
            "age_seconds": self.age_seconds,
            "risk_metrics": self.proposal.risk_metrics,
        }


@dataclass
class OrderManagerConfig:
    """Configuration for order manager."""

    require_approval: bool = False  # Fully autonomous — no human approval needed
    auto_approve_threshold: float = 1.0  # Auto-approve all trades within risk limits
    proposal_timeout_seconds: float = 300.0  # 5 minutes
    max_pending_proposals: int = 100
    allow_emergency_stop: bool = True
    notify_on_proposal: bool = True
    notify_on_execution: bool = True


class OrderManager:
    """
    Manages order lifecycle with human-in-the-loop approval.

    Features:
    - Approval queue for trade proposals
    - Risk metrics attached to each proposal
    - Timeout for pending proposals
    - Emergency stop capability
    - Execution tracking
    """

    def __init__(
        self,
        broker: Broker,
        config: OrderManagerConfig | None = None,
        on_proposal: Callable[[QueuedProposal], None] | None = None,
        on_execution: Callable[[Order], None] | None = None,
    ):
        """
        Initialize order manager.

        Args:
            broker: Broker for order execution
            config: Order manager configuration
            on_proposal: Callback when new proposal is queued
            on_execution: Callback when order is executed
        """
        self.broker = broker
        self.config = config or OrderManagerConfig()
        self._on_proposal = on_proposal
        self._on_execution = on_execution

        # Approval queue
        self._pending_queue: dict[str, QueuedProposal] = {}
        self._processed_queue: list[QueuedProposal] = []

        # State
        self._emergency_stop = False
        self._paused = False

        # Statistics
        self._stats = {
            "proposals_received": 0,
            "proposals_approved": 0,
            "proposals_rejected": 0,
            "proposals_expired": 0,
            "proposals_auto_approved": 0,
            "orders_executed": 0,
            "orders_failed": 0,
        }

    @property
    def is_stopped(self) -> bool:
        """Check if trading is stopped."""
        return self._emergency_stop

    @property
    def is_paused(self) -> bool:
        """Check if trading is paused."""
        return self._paused

    def emergency_stop(self) -> None:
        """Activate emergency stop - reject all pending and block new orders."""
        self._emergency_stop = True
        logger.warning("EMERGENCY STOP ACTIVATED")

        # Reject all pending proposals
        for proposal_id in list(self._pending_queue.keys()):
            self.reject_proposal(proposal_id, "Emergency stop activated", "system")

    def resume(self) -> None:
        """Resume trading after emergency stop."""
        self._emergency_stop = False
        self._paused = False
        logger.info("Trading resumed")

    def pause(self) -> None:
        """Pause trading (new proposals queued but not processed)."""
        self._paused = True
        logger.info("Trading paused")

    def unpause(self) -> None:
        """Unpause trading."""
        self._paused = False
        logger.info("Trading unpaused")

    async def propose_trade(
        self,
        order: Order,
        reasoning: str,
        signal: Signal | None = None,
        risk_metrics: dict[str, float] | None = None,
    ) -> QueuedProposal:
        """
        Submit a trade proposal for approval.

        Args:
            order: The order to propose
            reasoning: Explanation of why this trade should be executed
            signal: The signal that generated this trade
            risk_metrics: Risk metrics for the trade

        Returns:
            QueuedProposal with status
        """
        if self._emergency_stop:
            raise OrderError("Trading is stopped", order)

        if len(self._pending_queue) >= self.config.max_pending_proposals:
            raise OrderError("Approval queue is full", order)

        # Create proposal
        proposal = TradeProposal(
            order=order,
            reasoning=reasoning,
            risk_metrics=risk_metrics or {},
            expected_impact={
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": float(order.quantity),
            },
        )

        if signal:
            proposal.expected_impact["signal_strength"] = signal.strength
            proposal.expected_impact["signal_confidence"] = signal.confidence

        # Queue proposal
        queued = QueuedProposal(proposal=proposal)
        self._pending_queue[proposal.proposal_id] = queued
        self._stats["proposals_received"] += 1

        logger.info(
            f"Trade proposal queued: {proposal.proposal_id} - "
            f"{order.symbol} {order.side.value} {order.quantity}"
        )

        # Check for auto-approval
        if not self.config.require_approval:
            return await self._auto_approve(queued)

        if self.config.auto_approve_threshold > 0:
            risk_score = risk_metrics.get("risk_score", 1.0) if risk_metrics else 1.0
            if risk_score < self.config.auto_approve_threshold:
                return await self._auto_approve(queued)

        # Notify
        if self._on_proposal and self.config.notify_on_proposal:
            self._on_proposal(queued)

        return queued

    async def approve_proposal(
        self,
        proposal_id: str,
        approver: str = "user",
    ) -> Order | None:
        """
        Approve a trade proposal and execute the order.

        Args:
            proposal_id: ID of the proposal to approve
            approver: Who approved the trade

        Returns:
            Executed order, or None if execution failed
        """
        queued = self._pending_queue.get(proposal_id)
        if queued is None:
            logger.warning(f"Proposal not found: {proposal_id}")
            return None

        if self._emergency_stop:
            self.reject_proposal(proposal_id, "Emergency stop active", "system")
            return None

        # Update status
        queued.status = ApprovalStatus.APPROVED
        queued.processed_at = datetime.now()
        queued.processed_by = approver
        queued.proposal.approve(approver)

        # Execute order
        try:
            order = await self.broker.submit_order(queued.proposal.order)
            queued.execution_result = order
            self._stats["proposals_approved"] += 1
            self._stats["orders_executed"] += 1

            logger.info(f"Proposal approved and executed: {proposal_id} -> {order.order_id}")

            if self._on_execution and self.config.notify_on_execution:
                self._on_execution(order)

        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            queued.rejection_reason = f"Execution failed: {e}"
            self._stats["orders_failed"] += 1
            order = None

        # Move to processed queue
        del self._pending_queue[proposal_id]
        self._processed_queue.append(queued)

        return order

    def reject_proposal(
        self,
        proposal_id: str,
        reason: str = "",
        rejector: str = "user",
    ) -> bool:
        """
        Reject a trade proposal.

        Args:
            proposal_id: ID of the proposal to reject
            reason: Rejection reason
            rejector: Who rejected the trade

        Returns:
            True if proposal was found and rejected
        """
        queued = self._pending_queue.get(proposal_id)
        if queued is None:
            return False

        queued.status = ApprovalStatus.REJECTED
        queued.processed_at = datetime.now()
        queued.processed_by = rejector
        queued.rejection_reason = reason
        queued.proposal.reject(rejector)

        self._stats["proposals_rejected"] += 1

        logger.info(f"Proposal rejected: {proposal_id} - {reason}")

        # Move to processed queue
        del self._pending_queue[proposal_id]
        self._processed_queue.append(queued)

        return True

    async def _auto_approve(self, queued: QueuedProposal) -> QueuedProposal:
        """Auto-approve a proposal."""
        queued.status = ApprovalStatus.AUTO_APPROVED
        queued.processed_at = datetime.now()
        queued.processed_by = "auto"

        try:
            order = await self.broker.submit_order(queued.proposal.order)
            queued.execution_result = order
            self._stats["proposals_auto_approved"] += 1
            self._stats["orders_executed"] += 1

            logger.info(f"Proposal auto-approved: {queued.proposal.proposal_id}")

            if self._on_execution and self.config.notify_on_execution:
                self._on_execution(order)

        except Exception as e:
            logger.error(f"Auto-approved order failed: {e}")
            queued.rejection_reason = f"Execution failed: {e}"
            self._stats["orders_failed"] += 1

        # Move to processed queue
        del self._pending_queue[queued.proposal.proposal_id]
        self._processed_queue.append(queued)

        return queued

    def expire_stale_proposals(self) -> list[str]:
        """
        Expire proposals that have been pending too long.

        Returns:
            List of expired proposal IDs
        """
        expired = []
        timeout = self.config.proposal_timeout_seconds

        for proposal_id, queued in list(self._pending_queue.items()):
            if queued.age_seconds > timeout:
                queued.status = ApprovalStatus.EXPIRED
                queued.processed_at = datetime.now()
                queued.rejection_reason = "Proposal expired"

                self._stats["proposals_expired"] += 1
                expired.append(proposal_id)

                del self._pending_queue[proposal_id]
                self._processed_queue.append(queued)

                logger.info(f"Proposal expired: {proposal_id}")

        return expired

    def get_pending_proposals(self) -> list[QueuedProposal]:
        """Get all pending proposals."""
        return list(self._pending_queue.values())

    def get_proposal(self, proposal_id: str) -> QueuedProposal | None:
        """Get a specific proposal."""
        return self._pending_queue.get(proposal_id)

    def get_processed_proposals(
        self,
        limit: int = 100,
        status: ApprovalStatus | None = None,
    ) -> list[QueuedProposal]:
        """Get processed proposals."""
        proposals = self._processed_queue[-limit:]
        if status:
            proposals = [p for p in proposals if p.status == status]
        return proposals

    def get_statistics(self) -> dict[str, Any]:
        """Get order manager statistics."""
        return {
            **self._stats,
            "pending_proposals": len(self._pending_queue),
            "is_stopped": self._emergency_stop,
            "is_paused": self._paused,
        }

    def clear_history(self) -> None:
        """Clear processed proposal history."""
        self._processed_queue.clear()


class BatchOrderManager:
    """
    Manages batches of orders for rebalancing.

    Groups related orders and submits them for approval as a batch.
    """

    def __init__(self, order_manager: OrderManager):
        """
        Initialize batch order manager.

        Args:
            order_manager: Underlying order manager
        """
        self.order_manager = order_manager
        self._current_batch: list[tuple[Order, str]] = []
        self._batch_id: str | None = None

    def start_batch(self, batch_id: str | None = None) -> str:
        """Start a new order batch."""
        self._batch_id = batch_id or str(uuid4())
        self._current_batch = []
        return self._batch_id

    def add_to_batch(self, order: Order, reasoning: str) -> None:
        """Add an order to the current batch."""
        if self._batch_id is None:
            raise ValueError("No active batch - call start_batch first")
        self._current_batch.append((order, reasoning))

    async def submit_batch(
        self,
        risk_metrics: dict[str, float] | None = None,
    ) -> list[QueuedProposal]:
        """
        Submit all orders in the batch for approval.

        Args:
            risk_metrics: Risk metrics for the batch

        Returns:
            List of queued proposals
        """
        if not self._current_batch:
            return []

        proposals = []
        for order, reasoning in self._current_batch:
            # Add batch ID to order metadata
            order.metadata["batch_id"] = self._batch_id

            proposal = await self.order_manager.propose_trade(
                order=order,
                reasoning=f"[Batch {self._batch_id[:8]}] {reasoning}",
                risk_metrics=risk_metrics,
            )
            proposals.append(proposal)

        # Clear batch
        self._current_batch = []
        self._batch_id = None

        return proposals

    def cancel_batch(self) -> None:
        """Cancel the current batch without submitting."""
        self._current_batch = []
        self._batch_id = None
