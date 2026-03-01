"""Portfolio panel — reads state.json for equity, cash, positions."""

import json
import os
from pathlib import Path

from textual.widgets import Static


def _state_path() -> Path:
    results = os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
    return Path(results) / "live" / "state.json"


class PortfolioPanel(Static):
    """Portfolio summary from state.json."""

    def refresh_data(self) -> None:
        lines = ["[b]PORTFOLIO[/b]", ""]
        try:
            path = _state_path()
            if not path.exists():
                lines.append("  [dim]state.json not found[/dim]")
                self.update("\n".join(lines))
                return

            state = json.loads(path.read_text())
            portfolio = state.get("portfolio", {})

            equity = portfolio.get("equity", 0)
            cash = portfolio.get("cash", 0)
            day_pnl = portfolio.get("day_pnl", 0)
            positions = portfolio.get("positions", [])

            lines.append(f"  Equity:    ${equity:>12,.2f}")
            lines.append(f"  Cash:      ${cash:>12,.2f}")

            pnl_color = "green" if day_pnl >= 0 else "red"
            lines.append(f"  Day P&L:   [{pnl_color}]${day_pnl:>+12,.2f}[/{pnl_color}]")
            lines.append(f"  Positions: {len(positions):>12}")

            # Top 5 positions by unrealized P&L %
            if positions:
                lines.append("")
                lines.append("  [b]Top Movers[/b]")
                sorted_pos = sorted(
                    positions,
                    key=lambda p: abs(p.get("unrealized_pnl_pct", 0)),
                    reverse=True,
                )
                for p in sorted_pos[:5]:
                    sym = p.get("symbol", "?")[:6]
                    pct = p.get("unrealized_pnl_pct", 0)
                    color = "green" if pct >= 0 else "red"
                    lines.append(f"    {sym:<6} [{color}]{pct:>+7.1f}%[/{color}]")

            # Thesis allocation if available
            thesis_alloc = state.get("thesis_allocation", {})
            if thesis_alloc:
                lines.append("")
                lines.append("  [b]Thesis Allocation[/b]")
                for name, pct in sorted(thesis_alloc.items(), key=lambda x: -x[1])[:5]:
                    lines.append(f"    {name[:20]:<20} {pct:>5.1f}%")

        except Exception as e:
            lines.append(f"  [red]Error: {e}[/red]")

        self.update("\n".join(lines))
