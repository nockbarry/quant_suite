#!/usr/bin/env python3
"""End-of-day snapshot - Archive state and performance data.

Creates daily archives of:
- state.json
- Performance summary
- Thesis snapshots

Usage:
    PYTHONPATH=. python scripts/eod_snapshot.py
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.core.paths import paths


def main():
    """Create EOD snapshot."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Create daily archive directory
    archive_dir = paths.base / "daily_archives" / today
    archive_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating EOD snapshot for {today}...")

    # Copy state.json
    state_file = paths.live_state
    if state_file.exists():
        shutil.copy(state_file, archive_dir / "state.json")
        print(f"  Archived state.json")

    # Create summary
    summary = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "archived_files": [],
    }

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)

        # Portfolio summary
        portfolio = state.get("portfolio", {})
        summary["equity"] = portfolio.get("equity", 0)
        summary["cash"] = portfolio.get("cash", 0)
        summary["buying_power"] = portfolio.get("buying_power", 0)

        # Positions summary
        positions = state.get("positions", [])
        summary["positions_count"] = len(positions)
        summary["total_unrealized_pnl"] = sum(
            p.get("unrealized_pnl", 0) for p in positions
        )
        summary["total_realized_pnl"] = sum(
            p.get("realized_pnl", 0) for p in positions
        )

        # Market summary
        market = state.get("market", {})
        summary["spy_price"] = market.get("spy_price", 0)
        summary["vix"] = market.get("vix", 0)
        summary["regime"] = market.get("regime", "unknown")

        # Theses summary
        theses = state.get("theses", [])
        summary["theses_count"] = len(theses)
        summary["theses"] = [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "conviction": t.get("conviction"),
                "status": t.get("status"),
            }
            for t in theses
        ]

        # Top performers
        sorted_positions = sorted(
            positions,
            key=lambda p: p.get("unrealized_pnl_pct", 0),
            reverse=True,
        )
        summary["top_performers"] = [
            {
                "symbol": p.get("symbol"),
                "unrealized_pnl_pct": p.get("unrealized_pnl_pct", 0),
            }
            for p in sorted_positions[:5]
        ]
        summary["worst_performers"] = [
            {
                "symbol": p.get("symbol"),
                "unrealized_pnl_pct": p.get("unrealized_pnl_pct", 0),
            }
            for p in sorted_positions[-5:]
        ]

        summary["archived_files"].append("state.json")

    # Copy research files
    research_dir = paths.live_research
    if research_dir.exists():
        for f in research_dir.glob("*.json"):
            shutil.copy(f, archive_dir / f.name)
            summary["archived_files"].append(f.name)
        print(f"  Archived research files")

    # Save summary
    with open(archive_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nEOD snapshot complete!")
    print(f"  Archive: {archive_dir}")
    print(f"  Equity: ${summary.get('equity', 0):,.2f}")
    print(f"  Positions: {summary.get('positions_count', 0)}")
    print(f"  Unrealized P&L: ${summary.get('total_unrealized_pnl', 0):,.2f}")

    return summary


if __name__ == "__main__":
    main()
