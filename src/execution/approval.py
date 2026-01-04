"""Human-in-the-loop approval interface for trade proposals."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .order_manager import ApprovalStatus, OrderManager, QueuedProposal

logger = logging.getLogger(__name__)
console = Console()


class ApprovalInterface(ABC):
    """Abstract base class for approval interfaces."""

    @abstractmethod
    async def present_proposal(self, proposal: QueuedProposal) -> bool:
        """
        Present a proposal for approval.

        Args:
            proposal: The proposal to present

        Returns:
            True if approved, False if rejected
        """
        ...

    @abstractmethod
    async def notify(self, message: str, level: str = "info") -> None:
        """
        Send a notification.

        Args:
            message: The message to send
            level: Notification level (info, warning, error)
        """
        ...


class CLIApprovalInterface(ApprovalInterface):
    """
    Command-line interface for trade approval.

    Presents trade proposals in a rich terminal UI and prompts
    for approval/rejection.
    """

    def __init__(
        self,
        auto_reject_timeout: float | None = None,
        show_risk_details: bool = True,
    ):
        """
        Initialize CLI approval interface.

        Args:
            auto_reject_timeout: Timeout in seconds before auto-rejecting
            show_risk_details: Whether to show detailed risk metrics
        """
        self.auto_reject_timeout = auto_reject_timeout
        self.show_risk_details = show_risk_details

    async def present_proposal(self, proposal: QueuedProposal) -> bool:
        """Present proposal in CLI and get user decision."""
        order = proposal.proposal.order
        reasoning = proposal.proposal.reasoning
        risk_metrics = proposal.proposal.risk_metrics

        # Build proposal display
        console.print()
        console.print(Panel(
            f"[bold cyan]Trade Proposal[/bold cyan]\n"
            f"ID: {proposal.proposal.proposal_id[:8]}...\n"
            f"Time: {proposal.queued_at.strftime('%H:%M:%S')}",
            title="[bold yellow]⚠️  APPROVAL REQUIRED[/bold yellow]",
        ))

        # Order details table
        order_table = Table(title="Order Details", show_header=True)
        order_table.add_column("Field", style="cyan")
        order_table.add_column("Value", style="green")

        order_table.add_row("Symbol", order.symbol)
        order_table.add_row("Side", order.side.value.upper())
        order_table.add_row("Quantity", f"{order.quantity:,.4f}")
        order_table.add_row("Type", order.order_type.value.upper())
        if order.limit_price:
            order_table.add_row("Limit Price", f"${order.limit_price:,.2f}")
        if order.stop_price:
            order_table.add_row("Stop Price", f"${order.stop_price:,.2f}")
        order_table.add_row("Strategy", order.strategy_name or "N/A")

        console.print(order_table)

        # Reasoning
        console.print(Panel(
            reasoning,
            title="[bold]Reasoning[/bold]",
            border_style="blue",
        ))

        # Risk metrics
        if self.show_risk_details and risk_metrics:
            risk_table = Table(title="Risk Metrics", show_header=True)
            risk_table.add_column("Metric", style="cyan")
            risk_table.add_column("Value", style="yellow")

            for metric, value in risk_metrics.items():
                if isinstance(value, float):
                    risk_table.add_row(metric, f"{value:.4f}")
                else:
                    risk_table.add_row(metric, str(value))

            console.print(risk_table)

        # Get approval
        console.print()

        try:
            if self.auto_reject_timeout:
                # With timeout
                approved = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: Confirm.ask(
                            "[bold yellow]Approve this trade?[/bold yellow]",
                            default=False,
                        ),
                    ),
                    timeout=self.auto_reject_timeout,
                )
            else:
                approved = Confirm.ask(
                    "[bold yellow]Approve this trade?[/bold yellow]",
                    default=False,
                )

            if approved:
                console.print("[bold green]✓ Trade APPROVED[/bold green]")
            else:
                console.print("[bold red]✗ Trade REJECTED[/bold red]")

            return approved

        except asyncio.TimeoutError:
            console.print("[bold red]✗ Trade AUTO-REJECTED (timeout)[/bold red]")
            return False

    async def notify(self, message: str, level: str = "info") -> None:
        """Print notification to console."""
        if level == "error":
            console.print(f"[bold red]ERROR:[/bold red] {message}")
        elif level == "warning":
            console.print(f"[bold yellow]WARNING:[/bold yellow] {message}")
        else:
            console.print(f"[bold blue]INFO:[/bold blue] {message}")


class InteractiveApprovalSession:
    """
    Interactive session for reviewing and approving trade proposals.

    Provides a CLI menu for managing the approval queue.
    """

    def __init__(
        self,
        order_manager: OrderManager,
        interface: ApprovalInterface | None = None,
    ):
        """
        Initialize interactive session.

        Args:
            order_manager: Order manager with approval queue
            interface: Approval interface (defaults to CLI)
        """
        self.order_manager = order_manager
        self.interface = interface or CLIApprovalInterface()
        self._running = False

    async def run(self) -> None:
        """Run the interactive approval session."""
        self._running = True
        console.print(Panel(
            "[bold]Trade Approval Session[/bold]\n"
            "Review and approve/reject trade proposals",
            title="[bold cyan]Quant Suite[/bold cyan]",
        ))

        while self._running:
            try:
                await self._show_menu()
            except KeyboardInterrupt:
                console.print("\n[yellow]Session interrupted[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    async def _show_menu(self) -> None:
        """Show main menu and handle selection."""
        # Expire stale proposals first
        self.order_manager.expire_stale_proposals()

        pending = self.order_manager.get_pending_proposals()
        stats = self.order_manager.get_statistics()

        console.print()
        console.print(f"[bold]Pending proposals:[/bold] {len(pending)}")
        console.print(f"[dim]Approved: {stats['proposals_approved']} | "
                     f"Rejected: {stats['proposals_rejected']} | "
                     f"Expired: {stats['proposals_expired']}[/dim]")

        if self.order_manager.is_stopped:
            console.print("[bold red]⚠️  TRADING STOPPED[/bold red]")
        elif self.order_manager.is_paused:
            console.print("[bold yellow]⏸  TRADING PAUSED[/bold yellow]")

        console.print()
        console.print("[bold]Commands:[/bold]")
        console.print("  [cyan]1[/cyan] - Review pending proposals")
        console.print("  [cyan]2[/cyan] - Approve all pending")
        console.print("  [cyan]3[/cyan] - Reject all pending")
        console.print("  [cyan]4[/cyan] - View statistics")
        console.print("  [cyan]5[/cyan] - Toggle pause")
        console.print("  [cyan]6[/cyan] - Emergency stop")
        console.print("  [cyan]q[/cyan] - Quit")
        console.print()

        choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "5", "6", "q"], default="1")

        if choice == "1":
            await self._review_proposals()
        elif choice == "2":
            await self._approve_all()
        elif choice == "3":
            await self._reject_all()
        elif choice == "4":
            self._show_statistics()
        elif choice == "5":
            self._toggle_pause()
        elif choice == "6":
            self._emergency_stop()
        elif choice == "q":
            self._running = False

    async def _review_proposals(self) -> None:
        """Review pending proposals one by one."""
        pending = self.order_manager.get_pending_proposals()

        if not pending:
            console.print("[yellow]No pending proposals[/yellow]")
            return

        for i, queued in enumerate(pending, 1):
            console.print(f"\n[bold]Proposal {i}/{len(pending)}[/bold]")

            approved = await self.interface.present_proposal(queued)

            if approved:
                await self.order_manager.approve_proposal(
                    queued.proposal.proposal_id,
                    "user",
                )
            else:
                reason = Prompt.ask("Rejection reason", default="User rejected")
                self.order_manager.reject_proposal(
                    queued.proposal.proposal_id,
                    reason,
                    "user",
                )

            # Ask to continue
            if i < len(pending):
                if not Confirm.ask("Continue to next proposal?", default=True):
                    break

    async def _approve_all(self) -> None:
        """Approve all pending proposals."""
        pending = self.order_manager.get_pending_proposals()

        if not pending:
            console.print("[yellow]No pending proposals[/yellow]")
            return

        if Confirm.ask(f"Approve all {len(pending)} proposals?", default=False):
            for queued in pending:
                await self.order_manager.approve_proposal(
                    queued.proposal.proposal_id,
                    "user_batch",
                )
            console.print(f"[green]Approved {len(pending)} proposals[/green]")

    async def _reject_all(self) -> None:
        """Reject all pending proposals."""
        pending = self.order_manager.get_pending_proposals()

        if not pending:
            console.print("[yellow]No pending proposals[/yellow]")
            return

        if Confirm.ask(f"Reject all {len(pending)} proposals?", default=False):
            reason = Prompt.ask("Rejection reason", default="Batch rejection")
            for queued in pending:
                self.order_manager.reject_proposal(
                    queued.proposal.proposal_id,
                    reason,
                    "user_batch",
                )
            console.print(f"[red]Rejected {len(pending)} proposals[/red]")

    def _show_statistics(self) -> None:
        """Show order manager statistics."""
        stats = self.order_manager.get_statistics()

        table = Table(title="Order Manager Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in stats.items():
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

    def _toggle_pause(self) -> None:
        """Toggle pause state."""
        if self.order_manager.is_paused:
            self.order_manager.unpause()
            console.print("[green]Trading unpaused[/green]")
        else:
            self.order_manager.pause()
            console.print("[yellow]Trading paused[/yellow]")

    def _emergency_stop(self) -> None:
        """Activate emergency stop."""
        if self.order_manager.is_stopped:
            if Confirm.ask("Resume trading?", default=False):
                self.order_manager.resume()
                console.print("[green]Trading resumed[/green]")
        else:
            if Confirm.ask("[bold red]ACTIVATE EMERGENCY STOP?[/bold red]", default=False):
                self.order_manager.emergency_stop()
                console.print("[bold red]⚠️  EMERGENCY STOP ACTIVATED[/bold red]")


async def run_approval_session(order_manager: OrderManager) -> None:
    """
    Convenience function to run an interactive approval session.

    Args:
        order_manager: Order manager to use
    """
    session = InteractiveApprovalSession(order_manager)
    await session.run()
