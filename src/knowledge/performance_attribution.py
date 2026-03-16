#!/usr/bin/env python3
"""Performance Attribution - Attribute returns to theses, signals, and timing.

Answers: Where did our returns come from?
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional
from collections import defaultdict

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class Attribution:
    """Attribution of returns to a source."""
    source_type: str  # thesis, signal, timing, market
    source_name: str
    contribution_pct: float  # Contribution to total return
    contribution_dollars: float
    positions: list[str]
    win_rate: float = 0.0
    avg_holding_days: float = 0.0

    def to_dict(self):
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "contribution_pct": self.contribution_pct,
            "contribution_dollars": self.contribution_dollars,
            "positions": self.positions,
            "win_rate": self.win_rate,
            "avg_holding_days": self.avg_holding_days,
        }


@dataclass
class AttributionReport:
    """Full performance attribution report."""
    period_start: datetime
    period_end: datetime
    total_return_pct: float
    total_return_dollars: float
    attributions: list[Attribution]
    market_return_pct: float = 0.0
    alpha_pct: float = 0.0  # Return above market
    best_thesis: str = ""
    worst_thesis: str = ""

    def to_dict(self):
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_return_pct": self.total_return_pct,
            "total_return_dollars": self.total_return_dollars,
            "attributions": [a.to_dict() for a in self.attributions],
            "market_return_pct": self.market_return_pct,
            "alpha_pct": self.alpha_pct,
            "best_thesis": self.best_thesis,
            "worst_thesis": self.worst_thesis,
        }


class PerformanceAttributor:
    """Attribute portfolio performance to various sources."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or paths.base
        self.trades_dir = self.data_dir / "trades"
        self.theses_dir = self.data_dir / "theses"
        self.reports_dir = self.data_dir / "attribution"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def load_trades(self, start_date: date, end_date: date) -> list[dict]:
        """Load trades within date range."""
        trades = []

        # Try to load from trade history files
        for trade_file in self.trades_dir.glob("*.json"):
            try:
                with open(trade_file) as f:
                    file_trades = json.load(f)
                if isinstance(file_trades, list):
                    for trade in file_trades:
                        trade_date = datetime.fromisoformat(trade.get("timestamp", "")).date()
                        if start_date <= trade_date <= end_date:
                            trades.append(trade)
            except Exception as e:
                logger.debug(f"Could not load {trade_file}: {e}")

        return trades

    def load_theses(self) -> dict[str, dict]:
        """Load thesis information."""
        theses = {}

        for thesis_file in self.theses_dir.glob("*.yaml"):
            try:
                import yaml
                with open(thesis_file) as f:
                    thesis = yaml.safe_load(f)
                if thesis:
                    thesis_id = thesis.get("id", thesis_file.stem)
                    theses[thesis_id] = thesis
            except Exception as e:
                logger.debug(f"Could not load {thesis_file}: {e}")

        return theses

    def get_thesis_for_symbol(self, symbol: str, theses: dict) -> Optional[str]:
        """Find thesis that contains a symbol."""
        for thesis_id, thesis in theses.items():
            positions = thesis.get("positions", [])
            if symbol in positions:
                return thesis.get("name", thesis_id)
        return None

    def calculate_attribution(self, trades: list[dict], theses: dict,
                             portfolio_value: float) -> list[Attribution]:
        """Calculate attribution for each source."""
        # Group trades by thesis
        thesis_pnl: dict[str, dict] = defaultdict(lambda: {
            "pnl": 0.0,
            "positions": set(),
            "wins": 0,
            "losses": 0,
            "holding_days": [],
        })

        # Also track non-thesis trades
        signal_pnl: dict[str, dict] = defaultdict(lambda: {
            "pnl": 0.0,
            "positions": set(),
            "wins": 0,
            "losses": 0,
        })

        for trade in trades:
            symbol = trade.get("symbol", "")
            pnl = trade.get("realized_pnl", 0.0)
            thesis_name = self.get_thesis_for_symbol(symbol, theses)

            if thesis_name:
                thesis_pnl[thesis_name]["pnl"] += pnl
                thesis_pnl[thesis_name]["positions"].add(symbol)
                if pnl > 0:
                    thesis_pnl[thesis_name]["wins"] += 1
                elif pnl < 0:
                    thesis_pnl[thesis_name]["losses"] += 1

                # Track holding period if available
                if "holding_days" in trade:
                    thesis_pnl[thesis_name]["holding_days"].append(trade["holding_days"])
            else:
                # Attribute to signal type
                signal_type = trade.get("signal_type", "other")
                signal_pnl[signal_type]["pnl"] += pnl
                signal_pnl[signal_type]["positions"].add(symbol)
                if pnl > 0:
                    signal_pnl[signal_type]["wins"] += 1
                elif pnl < 0:
                    signal_pnl[signal_type]["losses"] += 1

        # Build attributions
        attributions = []

        # Thesis attributions
        for thesis_name, data in thesis_pnl.items():
            total_trades = data["wins"] + data["losses"]
            win_rate = data["wins"] / total_trades if total_trades > 0 else 0

            avg_holding = (sum(data["holding_days"]) / len(data["holding_days"])
                         if data["holding_days"] else 0)

            attributions.append(Attribution(
                source_type="thesis",
                source_name=thesis_name,
                contribution_pct=(data["pnl"] / portfolio_value * 100) if portfolio_value > 0 else 0,
                contribution_dollars=data["pnl"],
                positions=list(data["positions"]),
                win_rate=win_rate,
                avg_holding_days=avg_holding,
            ))

        # Signal attributions
        for signal_type, data in signal_pnl.items():
            total_trades = data["wins"] + data["losses"]
            win_rate = data["wins"] / total_trades if total_trades > 0 else 0

            attributions.append(Attribution(
                source_type="signal",
                source_name=signal_type,
                contribution_pct=(data["pnl"] / portfolio_value * 100) if portfolio_value > 0 else 0,
                contribution_dollars=data["pnl"],
                positions=list(data["positions"]),
                win_rate=win_rate,
            ))

        # Sort by contribution
        attributions.sort(key=lambda x: x.contribution_dollars, reverse=True)

        return attributions

    async def generate_report(self, start_date: date, end_date: date,
                             portfolio_value: float,
                             total_return_pct: float) -> AttributionReport:
        """Generate full attribution report."""
        trades = self.load_trades(start_date, end_date)
        theses = self.load_theses()

        attributions = self.calculate_attribution(trades, theses, portfolio_value)

        total_dollars = portfolio_value * total_return_pct / 100

        # Find best and worst thesis
        thesis_attrs = [a for a in attributions if a.source_type == "thesis"]
        best_thesis = thesis_attrs[0].source_name if thesis_attrs else ""
        worst_thesis = thesis_attrs[-1].source_name if thesis_attrs else ""

        # Get market return (SPY) for alpha calculation
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            spy_data = spy.history(start=start_date, end=end_date)
            if not spy_data.empty:
                market_return = (spy_data["Close"].iloc[-1] / spy_data["Close"].iloc[0] - 1) * 100
            else:
                market_return = 0.0
        except:
            market_return = 0.0

        report = AttributionReport(
            period_start=datetime.combine(start_date, datetime.min.time()),
            period_end=datetime.combine(end_date, datetime.max.time()),
            total_return_pct=total_return_pct,
            total_return_dollars=total_dollars,
            attributions=attributions,
            market_return_pct=market_return,
            alpha_pct=total_return_pct - market_return,
            best_thesis=best_thesis,
            worst_thesis=worst_thesis,
        )

        # Save report
        report_file = self.reports_dir / f"attribution_{end_date.strftime('%Y%m%d')}.json"
        with open(report_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        return report

    def get_report_summary(self, report: AttributionReport) -> str:
        """Get human-readable report summary."""
        lines = [
            "Performance Attribution Report",
            "=" * 50,
            f"Period: {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}",
            f"Total Return: {report.total_return_pct:+.2f}% (${report.total_return_dollars:+,.0f})",
            f"Market (SPY): {report.market_return_pct:+.2f}%",
            f"Alpha: {report.alpha_pct:+.2f}%",
            "",
            "Attribution by Source:",
            "-" * 40,
        ]

        for attr in report.attributions:
            lines.append(
                f"  [{attr.source_type:6s}] {attr.source_name:25s} "
                f"{attr.contribution_pct:+.2f}% (${attr.contribution_dollars:+,.0f})"
            )
            if attr.win_rate > 0:
                lines.append(f"           Win rate: {attr.win_rate:.0%}, Positions: {', '.join(attr.positions[:3])}")

        lines.extend([
            "",
            f"Best Thesis: {report.best_thesis}",
            f"Worst Thesis: {report.worst_thesis}",
        ])

        return "\n".join(lines)


async def main():
    """Test performance attribution."""
    attributor = PerformanceAttributor()

    # Generate report for last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    print(f"Generating attribution report for {start_date} to {end_date}...")

    # Mock data for testing
    report = await attributor.generate_report(
        start_date=start_date,
        end_date=end_date,
        portfolio_value=100000,
        total_return_pct=5.5,
    )

    print("\n" + attributor.get_report_summary(report))


if __name__ == "__main__":
    asyncio.run(main())
