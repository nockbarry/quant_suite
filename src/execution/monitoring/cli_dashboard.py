#!/usr/bin/env python3
"""
CLI Portfolio Monitoring Dashboard.

Real-time terminal dashboard for budget traders showing:
- Portfolio value and P&L
- Position summary
- Risk limit status
- Recent signals and trades
- Alert history

Usage:
    python -m src.execution.monitoring.cli_dashboard
    python -m src.execution.monitoring.cli_dashboard --mode live
    python -m src.execution.monitoring.cli_dashboard --refresh 5
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.core.paths import paths

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich.columns import Columns
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Rich not installed. Run: pip install rich")
    sys.exit(1)

from src.core import Portfolio, Position
from src.execution.monitoring.dashboard import (
    PortfolioMonitor,
    PortfolioSnapshot,
    AlertLevel,
    Alert,
)


class CLIDashboard:
    """
    Interactive CLI dashboard for portfolio monitoring.

    Displays:
    - Portfolio summary (value, cash, P&L)
    - Positions with real-time P&L
    - Risk status (drawdown, daily loss)
    - Recent signals from daily runs
    - Alert history
    - PDT status
    """

    def __init__(
        self,
        capital: float = 1000.0,
        refresh_seconds: int = 10,
        results_dir: Path | None = None,
    ):
        self.capital = capital
        self.refresh_seconds = refresh_seconds
        self.results_dir = results_dir or paths.daily_runs

        self.console = Console()
        self.monitor = PortfolioMonitor(initial_capital=capital)

        # State
        self._running = False
        self._broker = None
        self._last_signals: list[dict] = []
        self._last_trades: list[dict] = []

    def _load_recent_signals(self) -> list[dict]:
        """Load recent signal results from disk."""
        signals = []

        if not self.results_dir.exists():
            return signals

        # Get signal files from last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        signal_files = sorted(
            self.results_dir.glob("signals_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]  # Last 5 runs

        for filepath in signal_files:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    signals.append({
                        "timestamp": data.get("timestamp", ""),
                        "num_signals": data.get("num_signals", 0),
                        "num_proposals": data.get("num_proposals", 0),
                        "signals": data.get("signals", [])[:3],  # Top 3
                    })
            except Exception:
                pass

        return signals

    def _load_recent_trades(self) -> list[dict]:
        """Load recent execution results from disk."""
        trades = []

        if not self.results_dir.exists():
            return trades

        exec_files = sorted(
            self.results_dir.glob("execution_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]

        for filepath in exec_files:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    for trade in data[:3]:
                        trades.append(trade)
            except Exception:
                pass

        return trades[:10]  # Last 10 trades

    def _make_header(self) -> Panel:
        """Create header panel."""
        now = datetime.now()
        market_status = self._get_market_status()

        header = Text()
        header.append("QUANT SUITE ", style="bold cyan")
        header.append("| ", style="dim")
        header.append(f"{now.strftime('%Y-%m-%d %H:%M:%S')} ", style="white")
        header.append("| ", style="dim")
        header.append(f"Market: {market_status}", style="green" if market_status == "OPEN" else "yellow")

        return Panel(
            Align.center(header),
            border_style="cyan",
        )

    def _get_market_status(self) -> str:
        """Check if market is open."""
        now = datetime.now()
        # Simplified check (9:30 AM - 4:00 PM ET, weekdays)
        if now.weekday() >= 5:
            return "CLOSED (Weekend)"

        hour = now.hour
        if 9 <= hour < 16:
            if hour == 9 and now.minute < 30:
                return "PRE-MARKET"
            return "OPEN"
        elif hour < 9:
            return "PRE-MARKET"
        else:
            return "AFTER-HOURS"

    def _make_portfolio_panel(self, snapshot: PortfolioSnapshot | None) -> Panel:
        """Create portfolio summary panel."""
        if not snapshot:
            snapshot = PortfolioSnapshot(
                timestamp=datetime.now(),
                total_value=self.capital,
                cash=self.capital,
                positions_value=0,
                daily_pnl=0,
                daily_pnl_pct=0,
                total_pnl=0,
                total_pnl_pct=0,
                num_positions=0,
            )

        # Colors based on P&L
        daily_color = "green" if snapshot.daily_pnl >= 0 else "red"
        total_color = "green" if snapshot.total_pnl >= 0 else "red"
        dd_color = "green" if snapshot.drawdown > -0.05 else ("yellow" if snapshot.drawdown > -0.10 else "red")

        content = Text()
        content.append(f"Portfolio Value:  ", style="dim")
        content.append(f"${snapshot.total_value:,.2f}\n", style="bold white")

        content.append(f"Cash:             ", style="dim")
        content.append(f"${snapshot.cash:,.2f}\n", style="white")

        content.append(f"Positions Value:  ", style="dim")
        content.append(f"${snapshot.positions_value:,.2f}\n", style="white")

        content.append(f"\nDaily P&L:        ", style="dim")
        content.append(f"${snapshot.daily_pnl:+,.2f} ", style=f"bold {daily_color}")
        content.append(f"({snapshot.daily_pnl_pct:+.2%})\n", style=daily_color)

        content.append(f"Total P&L:        ", style="dim")
        content.append(f"${snapshot.total_pnl:+,.2f} ", style=f"bold {total_color}")
        content.append(f"({snapshot.total_pnl_pct:+.2%})\n", style=total_color)

        content.append(f"\nDrawdown:         ", style="dim")
        content.append(f"{snapshot.drawdown:.2%}", style=dd_color)

        return Panel(content, title="Portfolio", border_style="blue")

    def _make_positions_table(self, snapshot: PortfolioSnapshot | None) -> Table:
        """Create positions table."""
        table = Table(title="Positions", expand=True)
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Qty", justify="right", width=8)
        table.add_column("Entry", justify="right", width=10)
        table.add_column("Current", justify="right", width=10)
        table.add_column("Value", justify="right", width=12)
        table.add_column("P&L", justify="right", width=12)

        if snapshot and snapshot.positions:
            for symbol, pos in snapshot.positions.items():
                pnl = pos.get("unrealized_pnl", 0)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                pnl_style = "green" if pnl >= 0 else "red"

                table.add_row(
                    symbol,
                    f"{pos.get('quantity', 0):.2f}",
                    f"${pos.get('entry_price', 0):.2f}",
                    f"${pos.get('current_price', 0):.2f}",
                    f"${pos.get('market_value', 0):.2f}",
                    f"[{pnl_style}]${pnl:+.2f} ({pnl_pct:+.1%})[/{pnl_style}]",
                )
        else:
            table.add_row(
                "[dim]No positions[/dim]",
                "-", "-", "-", "-", "-"
            )

        return table

    def _make_risk_panel(self, snapshot: PortfolioSnapshot | None) -> Panel:
        """Create risk status panel."""
        content = Text()

        # PDT Status (from saved state or default)
        pdt_trades = 0  # Would come from broker
        content.append("PDT Status: ", style="dim")
        content.append(f"{pdt_trades}/3 day trades\n",
                      style="green" if pdt_trades < 3 else "red")

        # Max position
        max_pos_pct = 0.0
        if snapshot and snapshot.positions:
            max_pos_pct = max(
                pos.get("market_value", 0) / snapshot.total_value
                for pos in snapshot.positions.values()
            ) if snapshot.total_value > 0 else 0

        content.append("Max Position:  ", style="dim")
        pos_color = "green" if max_pos_pct <= 0.20 else ("yellow" if max_pos_pct <= 0.25 else "red")
        content.append(f"{max_pos_pct:.1%} ", style=pos_color)
        content.append("(limit: 25%)\n", style="dim")

        # Drawdown
        drawdown = snapshot.drawdown if snapshot else 0
        content.append("Drawdown:      ", style="dim")
        dd_color = "green" if drawdown > -0.10 else ("yellow" if drawdown > -0.15 else "red")
        content.append(f"{drawdown:.1%} ", style=dd_color)
        content.append("(limit: 15%)\n", style="dim")

        # Daily loss
        daily_pnl_pct = snapshot.daily_pnl_pct if snapshot else 0
        content.append("Daily Loss:    ", style="dim")
        loss_color = "green" if daily_pnl_pct > -0.03 else ("yellow" if daily_pnl_pct > -0.05 else "red")
        content.append(f"{daily_pnl_pct:.1%} ", style=loss_color)
        content.append("(limit: 5%)", style="dim")

        return Panel(content, title="Risk Limits", border_style="yellow")

    def _make_signals_panel(self) -> Panel:
        """Create recent signals panel."""
        content = Text()

        signals = self._load_recent_signals()

        if not signals:
            content.append("[dim]No recent signals[/dim]")
        else:
            for run in signals[:3]:
                ts = run.get("timestamp", "")[:16]
                n_sig = run.get("num_signals", 0)
                n_prop = run.get("num_proposals", 0)

                content.append(f"{ts}: ", style="dim")
                content.append(f"{n_sig} signals, {n_prop} proposals\n",
                              style="green" if n_prop > 0 else "white")

                for sig in run.get("signals", [])[:2]:
                    sym = sig.get("symbol", "?")
                    direction = sig.get("direction", "?")
                    strength = sig.get("strength", 0)
                    dir_color = "green" if direction == "LONG" else "red"
                    content.append(f"  {sym} ", style="cyan")
                    content.append(f"{direction} ", style=dir_color)
                    content.append(f"({strength:.2f})\n", style="dim")

        return Panel(content, title="Recent Signals (24h)", border_style="magenta")

    def _make_alerts_panel(self) -> Panel:
        """Create alerts panel."""
        content = Text()

        if not self.monitor.alerts:
            content.append("[dim]No alerts[/dim]")
        else:
            for alert in self.monitor.alerts[-5:]:
                level_style = {
                    AlertLevel.INFO: "blue",
                    AlertLevel.WARNING: "yellow",
                    AlertLevel.CRITICAL: "red",
                }.get(alert.level, "white")

                content.append(f"[{alert.level.value.upper()}] ", style=level_style)
                content.append(f"{alert.title}: ", style="white")
                content.append(f"{alert.message}\n", style="dim")

        return Panel(content, title="Alerts", border_style="red")

    def _make_layout(self, snapshot: PortfolioSnapshot | None) -> Layout:
        """Create full dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )

        layout["left"].split_column(
            Layout(name="portfolio"),
            Layout(name="positions"),
        )

        layout["right"].split_column(
            Layout(name="risk"),
            Layout(name="signals"),
            Layout(name="alerts"),
        )

        # Populate
        layout["header"].update(self._make_header())
        layout["portfolio"].update(self._make_portfolio_panel(snapshot))
        layout["positions"].update(self._make_positions_table(snapshot))
        layout["risk"].update(self._make_risk_panel(snapshot))
        layout["signals"].update(self._make_signals_panel())
        layout["alerts"].update(self._make_alerts_panel())

        # Footer
        footer = Text()
        footer.append("Press ", style="dim")
        footer.append("Ctrl+C", style="bold")
        footer.append(" to exit | ", style="dim")
        footer.append(f"Refresh: {self.refresh_seconds}s", style="dim")
        layout["footer"].update(Panel(Align.center(footer), border_style="dim"))

        return layout

    async def run(self) -> None:
        """Run the live dashboard."""
        self._running = True

        self.console.print("[bold cyan]Starting Portfolio Dashboard...[/bold cyan]")
        self.console.print(f"[dim]Results dir: {self.results_dir}[/dim]\n")

        # Initial snapshot
        portfolio = self._get_mock_portfolio()
        snapshot = self.monitor.take_snapshot(portfolio)

        try:
            with Live(
                self._make_layout(snapshot),
                console=self.console,
                refresh_per_second=1,
                screen=True,
            ) as live:
                while self._running:
                    # Update snapshot
                    portfolio = self._get_mock_portfolio()
                    snapshot = self.monitor.take_snapshot(portfolio)

                    # Check alerts
                    await self.monitor.check_alerts(snapshot)

                    # Update display
                    live.update(self._make_layout(snapshot))

                    await asyncio.sleep(self.refresh_seconds)

        except KeyboardInterrupt:
            self._running = False
            self.console.print("\n[yellow]Dashboard stopped.[/yellow]")

    def _get_mock_portfolio(self) -> Portfolio:
        """Get portfolio (mock for now, would connect to broker)."""
        # In production, this would fetch from Alpaca
        return Portfolio(
            initial_capital=Decimal(str(self.capital)),
            cash=Decimal(str(self.capital)),
            positions={},
        )

    def print_summary(self) -> None:
        """Print a one-time summary instead of live dashboard."""
        self.console.print(self._make_header())

        portfolio = self._get_mock_portfolio()
        snapshot = self.monitor.take_snapshot(portfolio)

        self.console.print(
            Columns([
                self._make_portfolio_panel(snapshot),
                self._make_risk_panel(snapshot),
            ])
        )

        self.console.print(self._make_positions_table(snapshot))

        self.console.print(
            Columns([
                self._make_signals_panel(),
                self._make_alerts_panel(),
            ])
        )


async def main():
    parser = argparse.ArgumentParser(description="Portfolio Monitoring Dashboard")
    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Account capital",
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=10,
        help="Refresh interval in seconds",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary and exit (no live mode)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Directory with signal/execution results",
    )

    args = parser.parse_args()

    dashboard = CLIDashboard(
        capital=args.capital,
        refresh_seconds=args.refresh,
        results_dir=args.results_dir,
    )

    if args.summary:
        dashboard.print_summary()
    else:
        await dashboard.run()


if __name__ == "__main__":
    asyncio.run(main())
