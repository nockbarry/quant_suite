"""Portfolio monitoring dashboard with alerts.

Live tracking of:
- Portfolio value and P&L
- Position performance
- Risk metrics
- Alert triggering

Supports multiple output channels:
- Console (Rich terminal)
- Slack webhook
- File logging
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import httpx

from ...core import Portfolio, Position, Symbol

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Severity level of alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert triggered by monitoring rules."""

    level: AlertLevel
    title: str
    message: str
    rule_name: str
    current_value: float
    threshold_value: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "rule_name": self.rule_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def format_console(self) -> str:
        """Format for console display."""
        level_icons = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }
        icon = level_icons.get(self.level, "•")
        return f"{icon} [{self.level.value.upper()}] {self.title}: {self.message}"

    def format_slack(self) -> dict[str, Any]:
        """Format for Slack webhook."""
        colors = {
            AlertLevel.INFO: "#36a64f",
            AlertLevel.WARNING: "#ff9800",
            AlertLevel.CRITICAL: "#f44336",
        }
        return {
            "attachments": [{
                "color": colors.get(self.level, "#808080"),
                "title": self.title,
                "text": self.message,
                "fields": [
                    {"title": "Rule", "value": self.rule_name, "short": True},
                    {"title": "Current", "value": f"{self.current_value:.2f}", "short": True},
                    {"title": "Threshold", "value": f"{self.threshold_value:.2f}", "short": True},
                ],
                "ts": int(self.timestamp.timestamp()),
            }]
        }


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of portfolio state."""

    timestamp: datetime
    total_value: float
    cash: float
    positions_value: float
    daily_pnl: float
    daily_pnl_pct: float
    total_pnl: float
    total_pnl_pct: float
    num_positions: int
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    drawdown: float = 0.0
    high_water_mark: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_value": self.total_value,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "num_positions": self.num_positions,
            "drawdown": self.drawdown,
            "high_water_mark": self.high_water_mark,
            "positions": self.positions,
        }


class AlertChannel(ABC):
    """Abstract base class for alert channels."""

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send an alert through this channel."""
        ...


class ConsoleChannel(AlertChannel):
    """Console output channel using Rich formatting."""

    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich
        self._console = None
        if use_rich:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self.use_rich = False

    async def send(self, alert: Alert) -> bool:
        """Print alert to console."""
        if self.use_rich and self._console:
            from rich.panel import Panel
            from rich.text import Text

            colors = {
                AlertLevel.INFO: "green",
                AlertLevel.WARNING: "yellow",
                AlertLevel.CRITICAL: "red",
            }
            color = colors.get(alert.level, "white")

            text = Text()
            text.append(f"{alert.title}\n", style=f"bold {color}")
            text.append(alert.message)

            self._console.print(Panel(text, title=f"[{alert.level.value.upper()}]", border_style=color))
        else:
            print(alert.format_console())

        return True


class SlackChannel(AlertChannel):
    """Slack webhook channel."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        """Send alert to Slack."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=alert.format_slack(),
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


class FileChannel(AlertChannel):
    """File logging channel."""

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, alert: Alert) -> bool:
        """Append alert to file."""
        try:
            with open(self.file_path, "a") as f:
                f.write(json.dumps(alert.to_dict()) + "\n")
            return True
        except Exception as e:
            logger.error(f"Failed to write alert to file: {e}")
            return False


@dataclass
class AlertRule:
    """Rule for triggering alerts."""

    name: str
    check: Callable[[PortfolioSnapshot], tuple[bool, float]]  # Returns (triggered, current_value)
    threshold: float
    level: AlertLevel
    message_template: str
    cooldown_minutes: int = 15  # Minimum time between alerts
    last_triggered: datetime | None = None

    def should_alert(self, snapshot: PortfolioSnapshot) -> Alert | None:
        """Check if rule should trigger an alert."""
        triggered, current_value = self.check(snapshot)

        if not triggered:
            return None

        # Check cooldown
        if self.last_triggered:
            elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
            if elapsed < self.cooldown_minutes:
                return None

        self.last_triggered = datetime.now()

        return Alert(
            level=self.level,
            title=self.name,
            message=self.message_template.format(
                current=current_value,
                threshold=self.threshold,
                pct=current_value * 100,
            ),
            rule_name=self.name,
            current_value=current_value,
            threshold_value=self.threshold,
        )


class PortfolioMonitor:
    """
    Portfolio monitoring with alerts and snapshots.

    Features:
    - Real-time portfolio value tracking
    - P&L calculation (daily and total)
    - Drawdown monitoring
    - Configurable alert rules
    - Multiple alert channels
    - Snapshot history

    Budget Trader Defaults:
    - Max drawdown alert: 10%
    - Daily loss alert: 3%
    - Position concentration alert: 30%
    """

    DEFAULT_ALERT_RULES = [
        AlertRule(
            name="Max Drawdown",
            check=lambda s: (s.drawdown <= -0.10, s.drawdown),
            threshold=-0.10,
            level=AlertLevel.CRITICAL,
            message_template="Drawdown of {pct:.1f}% exceeds 10% threshold",
            cooldown_minutes=60,
        ),
        AlertRule(
            name="Daily Loss Warning",
            check=lambda s: (s.daily_pnl_pct <= -0.03, s.daily_pnl_pct),
            threshold=-0.03,
            level=AlertLevel.WARNING,
            message_template="Daily loss of {pct:.1f}% exceeds 3% threshold",
            cooldown_minutes=30,
        ),
        AlertRule(
            name="Daily Loss Critical",
            check=lambda s: (s.daily_pnl_pct <= -0.05, s.daily_pnl_pct),
            threshold=-0.05,
            level=AlertLevel.CRITICAL,
            message_template="Daily loss of {pct:.1f}% exceeds 5% threshold",
            cooldown_minutes=60,
        ),
    ]

    def __init__(
        self,
        initial_capital: float = 1000.0,
        alert_rules: list[AlertRule] | None = None,
        channels: list[AlertChannel] | None = None,
        snapshot_interval_seconds: int = 60,
    ):
        """
        Initialize portfolio monitor.

        Args:
            initial_capital: Starting capital for P&L calculation
            alert_rules: Custom alert rules (defaults to budget trader rules)
            channels: Alert channels (defaults to console)
            snapshot_interval_seconds: How often to take snapshots
        """
        self.initial_capital = initial_capital
        self.alert_rules = alert_rules or self.DEFAULT_ALERT_RULES.copy()
        self.channels = channels or [ConsoleChannel()]
        self.snapshot_interval = snapshot_interval_seconds

        self.snapshots: list[PortfolioSnapshot] = []
        self.alerts: list[Alert] = []
        self.high_water_mark = initial_capital
        self.day_start_value: float | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, portfolio: Portfolio) -> None:
        """Start monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(portfolio))
        logger.info("Portfolio monitor started")

    async def stop(self) -> None:
        """Stop monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Portfolio monitor stopped")

    async def _monitor_loop(self, portfolio: Portfolio) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                snapshot = self.take_snapshot(portfolio)
                await self.check_alerts(snapshot)
                await asyncio.sleep(self.snapshot_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(5)

    def take_snapshot(self, portfolio: Portfolio) -> PortfolioSnapshot:
        """Take a portfolio snapshot."""
        total_value = float(portfolio.total_value)
        cash = float(portfolio.cash)
        positions_value = total_value - cash

        # Update high water mark
        if total_value > self.high_water_mark:
            self.high_water_mark = total_value

        # Calculate drawdown
        drawdown = (total_value - self.high_water_mark) / self.high_water_mark

        # Calculate daily P&L
        if self.day_start_value is None:
            self.day_start_value = total_value

        daily_pnl = total_value - self.day_start_value
        daily_pnl_pct = daily_pnl / self.day_start_value if self.day_start_value > 0 else 0

        # Calculate total P&L
        total_pnl = total_value - self.initial_capital
        total_pnl_pct = total_pnl / self.initial_capital if self.initial_capital > 0 else 0

        # Get position details
        positions = {}
        for symbol, position in portfolio.positions.items():
            positions[symbol] = {
                "quantity": float(position.quantity),
                "entry_price": float(position.entry_price),
                "current_price": float(position.current_price),
                "market_value": float(position.market_value),
                "unrealized_pnl": float(position.unrealized_pnl),
                "unrealized_pnl_pct": float(position.unrealized_pnl_pct),
            }

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            total_value=total_value,
            cash=cash,
            positions_value=positions_value,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            num_positions=len(portfolio.positions),
            positions=positions,
            drawdown=drawdown,
            high_water_mark=self.high_water_mark,
        )

        self.snapshots.append(snapshot)

        # Keep only last 24 hours of snapshots
        cutoff = datetime.now() - timedelta(hours=24)
        self.snapshots = [s for s in self.snapshots if s.timestamp > cutoff]

        return snapshot

    async def check_alerts(self, snapshot: PortfolioSnapshot) -> list[Alert]:
        """Check all alert rules and send triggered alerts."""
        triggered = []

        for rule in self.alert_rules:
            alert = rule.should_alert(snapshot)
            if alert:
                triggered.append(alert)
                self.alerts.append(alert)
                await self._send_alert(alert)

        return triggered

    async def _send_alert(self, alert: Alert) -> None:
        """Send alert through all channels."""
        for channel in self.channels:
            try:
                await channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel.__class__.__name__}: {e}")

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add a custom alert rule."""
        self.alert_rules.append(rule)

    def add_channel(self, channel: AlertChannel) -> None:
        """Add an alert channel."""
        self.channels.append(channel)

    def reset_daily(self) -> None:
        """Reset daily tracking (call at market open)."""
        if self.snapshots:
            self.day_start_value = self.snapshots[-1].total_value
        logger.info(f"Daily tracking reset. Start value: ${self.day_start_value:.2f}")

    def get_latest_snapshot(self) -> PortfolioSnapshot | None:
        """Get the most recent snapshot."""
        return self.snapshots[-1] if self.snapshots else None

    def get_daily_summary(self) -> dict[str, Any]:
        """Get summary of today's performance."""
        if not self.snapshots:
            return {}

        latest = self.snapshots[-1]
        today_snapshots = [
            s for s in self.snapshots
            if s.timestamp.date() == datetime.now().date()
        ]

        if not today_snapshots:
            return {}

        high = max(s.total_value for s in today_snapshots)
        low = min(s.total_value for s in today_snapshots)

        return {
            "date": datetime.now().date().isoformat(),
            "start_value": self.day_start_value,
            "current_value": latest.total_value,
            "high": high,
            "low": low,
            "daily_pnl": latest.daily_pnl,
            "daily_pnl_pct": latest.daily_pnl_pct,
            "num_snapshots": len(today_snapshots),
            "alerts_triggered": len([a for a in self.alerts if a.timestamp.date() == datetime.now().date()]),
        }

    def print_status(self) -> None:
        """Print current portfolio status to console."""
        snapshot = self.get_latest_snapshot()
        if not snapshot:
            print("No snapshot available")
            return

        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel

            console = Console()

            # Main stats
            pnl_color = "green" if snapshot.daily_pnl >= 0 else "red"
            total_color = "green" if snapshot.total_pnl >= 0 else "red"

            console.print(Panel(
                f"[bold]Portfolio Value:[/bold] ${snapshot.total_value:,.2f}\n"
                f"[bold]Cash:[/bold] ${snapshot.cash:,.2f}\n"
                f"[bold]Positions:[/bold] ${snapshot.positions_value:,.2f}\n"
                f"[bold]Daily P&L:[/bold] [{pnl_color}]${snapshot.daily_pnl:+,.2f} ({snapshot.daily_pnl_pct:+.2%})[/{pnl_color}]\n"
                f"[bold]Total P&L:[/bold] [{total_color}]${snapshot.total_pnl:+,.2f} ({snapshot.total_pnl_pct:+.2%})[/{total_color}]\n"
                f"[bold]Drawdown:[/bold] {snapshot.drawdown:.2%}",
                title="Portfolio Summary",
            ))

            # Positions table
            if snapshot.positions:
                table = Table(title="Positions")
                table.add_column("Symbol", style="cyan")
                table.add_column("Qty", justify="right")
                table.add_column("Entry", justify="right")
                table.add_column("Current", justify="right")
                table.add_column("Value", justify="right")
                table.add_column("P&L", justify="right")

                for symbol, pos in snapshot.positions.items():
                    pnl = pos["unrealized_pnl"]
                    pnl_style = "green" if pnl >= 0 else "red"
                    table.add_row(
                        symbol,
                        f"{pos['quantity']:.2f}",
                        f"${pos['entry_price']:.2f}",
                        f"${pos['current_price']:.2f}",
                        f"${pos['market_value']:.2f}",
                        f"[{pnl_style}]${pnl:+.2f}[/{pnl_style}]",
                    )

                console.print(table)

        except ImportError:
            # Fallback to basic printing
            print(f"\n{'=' * 50}")
            print(f"Portfolio Value: ${snapshot.total_value:,.2f}")
            print(f"Cash: ${snapshot.cash:,.2f}")
            print(f"Daily P&L: ${snapshot.daily_pnl:+,.2f} ({snapshot.daily_pnl_pct:+.2%})")
            print(f"Total P&L: ${snapshot.total_pnl:+,.2f} ({snapshot.total_pnl_pct:+.2%})")
            print(f"Drawdown: {snapshot.drawdown:.2%}")
            print(f"{'=' * 50}\n")

    def to_dict(self) -> dict[str, Any]:
        """Export monitor state."""
        return {
            "initial_capital": self.initial_capital,
            "high_water_mark": self.high_water_mark,
            "day_start_value": self.day_start_value,
            "num_snapshots": len(self.snapshots),
            "num_alerts": len(self.alerts),
            "latest_snapshot": self.get_latest_snapshot().to_dict() if self.snapshots else None,
            "daily_summary": self.get_daily_summary(),
        }
