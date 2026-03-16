#!/usr/bin/env python3
"""
Backtest Equal-Weight vs Concentrated Thesis Allocation.

Validates the trading rule that equal-weighting within theses
outperforms concentration based on conviction.

Usage:
    python3 scripts/backtest_equal_weight.py
    python3 scripts/backtest_equal_weight.py --days 30
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from src.core.paths import paths


def get_historical_trades(days: int = 30) -> list[dict]:
    """Get closed trades from Alpaca."""
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import OrderSide, QueryOrderStatus

    creds_file = Path(__file__).parent.parent / "config/credentials.yaml"
    with open(creds_file) as f:
        creds = yaml.safe_load(f)

    client = TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True
    )

    after_date = datetime.now() - timedelta(days=days)
    request = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        after=after_date,
        limit=500,
    )

    orders = client.get_orders(filter=request)

    trades = []
    for order in orders:
        if order.filled_qty is None or float(order.filled_qty) == 0:
            continue
        if not order.filled_avg_price:
            continue

        trades.append({
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": float(order.filled_qty),
            "price": float(order.filled_avg_price),
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        })

    return trades


def get_thesis_assignments() -> dict[str, str]:
    """Load thesis assignments from theses directory."""
    theses_dir = paths.theses
    assignments = {}

    for thesis_file in theses_dir.glob("*.yaml"):
        try:
            with open(thesis_file) as f:
                thesis = yaml.safe_load(f)
            thesis_name = thesis.get("name", thesis_file.stem)
            for pos in thesis.get("positions", []):
                if isinstance(pos, str):
                    assignments[pos] = thesis_name
                elif isinstance(pos, dict):
                    assignments[pos.get("symbol", "")] = thesis_name
        except Exception as e:
            logger.warning(f"Could not load {thesis_file}: {e}")

    return assignments


def calculate_returns(trades: list[dict]) -> dict:
    """Calculate returns by symbol using FIFO matching."""
    positions = {}

    for trade in sorted(trades, key=lambda x: x.get("filled_at") or ""):
        symbol = trade["symbol"]
        if symbol not in positions:
            positions[symbol] = {
                "buys": [],
                "sells": [],
            }

        entry = {
            "qty": trade["qty"],
            "price": trade["price"],
            "date": trade.get("filled_at"),
        }

        if trade["side"] == "buy":
            positions[symbol]["buys"].append(entry)
        else:
            positions[symbol]["sells"].append(entry)

    # Calculate returns for closed positions
    returns = {}
    for symbol, data in positions.items():
        if not data["buys"] or not data["sells"]:
            continue

        total_buy_qty = sum(b["qty"] for b in data["buys"])
        total_sell_qty = sum(s["qty"] for s in data["sells"])
        total_buy_cost = sum(b["qty"] * b["price"] for b in data["buys"])
        total_sell_proceeds = sum(s["qty"] * s["price"] for s in data["sells"])

        if total_buy_qty == 0:
            continue

        avg_buy = total_buy_cost / total_buy_qty
        avg_sell = total_sell_proceeds / total_sell_qty if total_sell_qty > 0 else 0
        closed_qty = min(total_buy_qty, total_sell_qty)

        if closed_qty == 0 or avg_buy == 0:
            continue

        pnl = closed_qty * (avg_sell - avg_buy)
        pnl_pct = ((avg_sell / avg_buy) - 1) * 100

        returns[symbol] = {
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "cost_basis": total_buy_cost,
            "avg_buy": avg_buy,
            "avg_sell": avg_sell,
            "qty": closed_qty,
        }

    return returns


def simulate_allocations(returns: dict, thesis_assignments: dict, capital: float = 100000) -> dict:
    """
    Compare actual (concentrated) vs equal-weight allocations.

    Returns metrics for both approaches.
    """
    # Group by thesis
    by_thesis = {}
    for symbol, data in returns.items():
        thesis = thesis_assignments.get(symbol, "unassigned")
        if thesis not in by_thesis:
            by_thesis[thesis] = {}
        by_thesis[thesis][symbol] = data

    results = {
        "by_thesis": {},
        "totals": {
            "concentrated": {"pnl": 0, "trades": 0},
            "equal_weight": {"pnl": 0, "trades": 0},
        }
    }

    for thesis, positions in by_thesis.items():
        if len(positions) <= 1:
            continue  # Skip theses with only one position

        # Calculate actual (concentrated) returns
        actual_total = sum(p["cost_basis"] for p in positions.values())
        actual_pnl = sum(p["pnl"] for p in positions.values())
        actual_return_pct = (actual_pnl / actual_total * 100) if actual_total > 0 else 0

        # Calculate equal-weight returns
        n_positions = len(positions)
        ew_total = actual_total  # Same total capital
        ew_per_position = ew_total / n_positions

        ew_pnl = 0
        for symbol, data in positions.items():
            # Hypothetical equal-weight position
            ew_qty = ew_per_position / data["avg_buy"]
            ew_position_pnl = ew_qty * (data["avg_sell"] - data["avg_buy"])
            ew_pnl += ew_position_pnl

        ew_return_pct = (ew_pnl / ew_total * 100) if ew_total > 0 else 0

        results["by_thesis"][thesis] = {
            "positions": list(positions.keys()),
            "num_positions": n_positions,
            "actual": {
                "total_capital": actual_total,
                "pnl": actual_pnl,
                "return_pct": actual_return_pct,
            },
            "equal_weight": {
                "total_capital": ew_total,
                "pnl": ew_pnl,
                "return_pct": ew_return_pct,
            },
            "difference": {
                "pnl": ew_pnl - actual_pnl,
                "return_pct": ew_return_pct - actual_return_pct,
            },
            "winner": "equal_weight" if ew_pnl > actual_pnl else "concentrated",
        }

        results["totals"]["concentrated"]["pnl"] += actual_pnl
        results["totals"]["concentrated"]["trades"] += n_positions
        results["totals"]["equal_weight"]["pnl"] += ew_pnl
        results["totals"]["equal_weight"]["trades"] += n_positions

    return results


def print_report(results: dict) -> None:
    """Print backtest results."""
    print("\n" + "=" * 70)
    print("EQUAL-WEIGHT VS CONCENTRATED ALLOCATION BACKTEST")
    print("=" * 70)

    print("\nBY THESIS:")
    print("-" * 70)

    for thesis, data in results["by_thesis"].items():
        print(f"\n{thesis} ({data['num_positions']} positions):")
        print(f"  Positions: {', '.join(data['positions'])}")
        print(f"  Concentrated: ${data['actual']['pnl']:,.2f} ({data['actual']['return_pct']:+.2f}%)")
        print(f"  Equal-Weight: ${data['equal_weight']['pnl']:,.2f} ({data['equal_weight']['return_pct']:+.2f}%)")
        print(f"  Difference:   ${data['difference']['pnl']:,.2f} ({data['difference']['return_pct']:+.2f}%)")
        print(f"  Winner: {data['winner'].upper()}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    conc = results["totals"]["concentrated"]
    ew = results["totals"]["equal_weight"]

    print(f"\nTotal Concentrated P&L: ${conc['pnl']:,.2f}")
    print(f"Total Equal-Weight P&L: ${ew['pnl']:,.2f}")
    print(f"Difference: ${ew['pnl'] - conc['pnl']:,.2f}")

    if len(results["by_thesis"]) > 0:
        ew_wins = sum(1 for d in results["by_thesis"].values() if d["winner"] == "equal_weight")
        total = len(results["by_thesis"])
        print(f"\nEqual-Weight wins: {ew_wins}/{total} theses ({ew_wins/total*100:.0f}%)")

    print("\n" + "=" * 70)

    # Recommendation
    if ew["pnl"] > conc["pnl"]:
        diff = ew["pnl"] - conc["pnl"]
        print(f"\nRECOMMENDATION: Equal-weight outperformed by ${diff:,.2f}")
        print("Continue using equal-weight allocation within theses.")
    else:
        diff = conc["pnl"] - ew["pnl"]
        print(f"\nRECOMMENDATION: Concentrated outperformed by ${diff:,.2f}")
        print("Review concentrated allocation strategy.")

    print("")


def main():
    parser = argparse.ArgumentParser(description="Backtest Equal-Weight vs Concentrated")
    parser.add_argument("--days", type=int, default=30, help="Days of history")
    args = parser.parse_args()

    print("=" * 70)
    print("EQUAL-WEIGHT THESIS ALLOCATION BACKTEST")
    print("=" * 70)

    logger.info(f"Fetching trades from last {args.days} days...")
    try:
        trades = get_historical_trades(args.days)
        logger.info(f"Found {len(trades)} trades")
    except Exception as e:
        logger.error(f"Could not fetch trades: {e}")
        return

    if not trades:
        logger.warning("No trades found")
        return

    logger.info("Loading thesis assignments...")
    thesis_assignments = get_thesis_assignments()
    logger.info(f"Loaded {len(thesis_assignments)} symbol -> thesis mappings")

    logger.info("Calculating returns...")
    returns = calculate_returns(trades)
    logger.info(f"Calculated returns for {len(returns)} symbols")

    logger.info("Simulating allocations...")
    results = simulate_allocations(returns, thesis_assignments)

    print_report(results)

    # Save results
    output_dir = paths.research
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"equal_weight_backtest_{datetime.now().strftime('%Y%m%d')}.json"

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Results saved to {output_file}")


if __name__ == "__main__":
    main()
