#!/usr/bin/env python3
"""Market monitor - checks positions and theses every N minutes.

Usage:
    PYTHONPATH=/home/nock/projects/quant_suite python3 scripts/market_monitor.py --interval 5 --duration 60
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.quick_trade import get_broker
from src.knowledge.thesis import ThesisTracker
from src.knowledge.paper_positions import PaperPositionTracker
from src.core.paths import paths


async def check_market(log_file):
    """Single market check iteration."""
    broker = get_broker(paper=True)
    await broker.connect()

    try:
        # Get account and positions
        account = await broker.get_account()
        positions = await broker.get_positions()

        # Get thesis tracker
        tracker = ThesisTracker(paths.theses)
        theses = {t.name: t for t in tracker.get_active_theses()}

        # Map symbols to theses
        symbol_to_thesis = {}
        for thesis in theses.values():
            for sym in thesis.positions:
                symbol_to_thesis[sym] = thesis.name

        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"MARKET CHECK - {datetime.now().strftime('%H:%M:%S')}")
        lines.append(f"{'='*70}")

        # Portfolio summary
        portfolio_value = float(account.portfolio_value)
        cash = float(account.cash)
        total_pnl = sum(float(p.unrealized_pnl or 0) for p in positions.values())
        pnl_sign = "+" if total_pnl >= 0 else ""

        lines.append(f"\nPORTFOLIO: ${portfolio_value:,.0f} | Cash: ${cash:,.0f} | P&L: {pnl_sign}${total_pnl:,.0f}")

        # Thesis performance
        lines.append(f"\n{'─'*70}")
        lines.append("THESIS PERFORMANCE (Real Positions)")
        lines.append(f"{'─'*70}")

        thesis_totals = {}
        for sym, pos in positions.items():
            thesis_name = symbol_to_thesis.get(str(sym), "Unlinked")
            if thesis_name not in thesis_totals:
                thesis_totals[thesis_name] = {"value": 0, "pnl": 0, "positions": []}

            value = float(pos.market_value or 0)
            pnl = float(pos.unrealized_pnl or 0)
            pnl_pct = float(pos.unrealized_pnl_pct or 0) * 100

            thesis_totals[thesis_name]["value"] += value
            thesis_totals[thesis_name]["pnl"] += pnl
            thesis_totals[thesis_name]["positions"].append((str(sym), pnl_pct))

        # Sort by P&L
        for thesis_name in sorted(thesis_totals.keys(), key=lambda x: thesis_totals[x]["pnl"], reverse=True):
            data = thesis_totals[thesis_name]
            if thesis_name == "Unlinked":
                continue
            conviction = theses[thesis_name].conviction if thesis_name in theses else "?"
            pnl_sign = "+" if data["pnl"] >= 0 else ""
            lines.append(f"\n{thesis_name} ({conviction}%)")
            lines.append(f"  Value: ${data['value']:,.0f} | P&L: {pnl_sign}${data['pnl']:,.0f}")

            # Top movers
            sorted_pos = sorted(data["positions"], key=lambda x: x[1], reverse=True)
            movers = []
            for sym, pct in sorted_pos[:3]:
                sign = "+" if pct >= 0 else ""
                movers.append(f"{sym} {sign}{pct:.1f}%")
            lines.append(f"  Movers: {', '.join(movers)}")

        # Paper positions
        lines.append(f"\n{'─'*70}")
        lines.append("PAPER TRACKED POSITIONS")
        lines.append(f"{'─'*70}")

        paper_tracker = PaperPositionTracker()
        paper_positions = await paper_tracker.get_positions_with_prices(broker)

        paper_by_thesis = {}
        for p in paper_positions:
            thesis = p.thesis_name or "Unlinked"
            if thesis not in paper_by_thesis:
                paper_by_thesis[thesis] = {"entry": 0, "current": 0, "positions": []}
            paper_by_thesis[thesis]["entry"] += p.entry_value
            paper_by_thesis[thesis]["current"] += p.current_value or 0
            pnl_pct = ((p.current_value or 0) - p.entry_value) / p.entry_value * 100 if p.entry_value > 0 else 0
            paper_by_thesis[thesis]["positions"].append((p.symbol, pnl_pct))

        for thesis_name, data in paper_by_thesis.items():
            pnl = data["current"] - data["entry"]
            pnl_pct = pnl / data["entry"] * 100 if data["entry"] > 0 else 0
            sign = "+" if pnl >= 0 else ""
            lines.append(f"\n{thesis_name}")
            lines.append(f"  Entry: ${data['entry']:,.0f} | Current: ${data['current']:,.0f} | P&L: {sign}${pnl:,.0f} ({sign}{pnl_pct:.1f}%)")

            sorted_pos = sorted(data["positions"], key=lambda x: x[1], reverse=True)
            movers = []
            for sym, pct in sorted_pos:
                sign = "+" if pct >= 0 else ""
                movers.append(f"{sym} {sign}{pct:.1f}%")
            lines.append(f"  Positions: {', '.join(movers)}")

        # Scheduled trades status
        lines.append(f"\n{'─'*70}")
        lines.append("KEY PRICES")
        lines.append(f"{'─'*70}")

        key_symbols = ["AXP", "SYF", "GOLD", "FRO", "SLB", "GLD", "SPY"]
        price_line = []
        for sym in key_symbols:
            try:
                quote = await broker.get_quote(sym)
                price = float(quote.last)
                price_line.append(f"{sym}:${price:.2f}")
            except:
                pass
        lines.append("  " + " | ".join(price_line))

        # Write to log
        output = "\n".join(lines)
        print(output)

        with open(log_file, 'a') as f:
            f.write(output + "\n")

    finally:
        await broker.disconnect()


async def monitor_loop(interval_minutes: int, duration_minutes: int, log_file: Path):
    """Run market checks at specified interval."""
    iterations = duration_minutes // interval_minutes

    start_msg = f"""
{'='*70}
MARKET MONITOR STARTED
{'='*70}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Interval: {interval_minutes} minutes
Duration: {duration_minutes} minutes ({iterations} checks)
Log file: {log_file}
{'='*70}
"""
    print(start_msg)
    with open(log_file, 'a') as f:
        f.write(start_msg)

    for i in range(iterations):
        try:
            await check_market(log_file)
        except Exception as e:
            error_msg = f"Error in check {i+1}: {e}"
            print(error_msg)
            with open(log_file, 'a') as f:
                f.write(error_msg + "\n")

        if i < iterations - 1:
            next_check = datetime.now() + timedelta(minutes=interval_minutes)
            wait_msg = f"\n... Next check at {next_check.strftime('%H:%M:%S')} ..."
            print(wait_msg)
            with open(log_file, 'a') as f:
                f.write(wait_msg + "\n")
            await asyncio.sleep(interval_minutes * 60)

    end_msg = f"""
{'='*70}
MONITORING COMPLETE - {datetime.now().strftime('%H:%M:%S')}
{'='*70}
"""
    print(end_msg)
    with open(log_file, 'a') as f:
        f.write(end_msg)


def main():
    parser = argparse.ArgumentParser(description="Monitor market positions and theses")
    parser.add_argument("--interval", type=int, default=5, help="Check interval in minutes")
    parser.add_argument("--duration", type=int, default=60, help="Total duration in minutes")
    parser.add_argument("--log", type=str, help="Log file path")

    args = parser.parse_args()

    log_file = Path(args.log) if args.log else (
        paths.base / "logs" / f"market_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)

    asyncio.run(monitor_loop(args.interval, args.duration, log_file))


if __name__ == "__main__":
    main()
