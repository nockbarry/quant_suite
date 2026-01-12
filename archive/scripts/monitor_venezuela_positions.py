#!/usr/bin/env python3
"""
Venezuela Thesis Position Monitor

Real-time monitoring of paper trading positions.
Tracks P&L, alerts on significant moves, and logs performance.

Usage:
    PYTHONPATH=. python scripts/monitor_venezuela_positions.py
    PYTHONPATH=. python scripts/monitor_venezuela_positions.py --continuous --interval 60
"""

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml
from alpaca.trading.client import TradingClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Thesis targets and stops
POSITION_CONFIG = {
    "SLB": {
        "thesis": "Reconstruction leader - 15 rigs in Venezuela",
        "target_pct": 0.30,  # +30% target
        "stop_pct": -0.15,  # -15% stop
        "confidence": 0.75,
    },
    "VLO": {
        "thesis": "Refiner margin expansion on heavy crude",
        "target_pct": 0.25,
        "stop_pct": -0.12,
        "confidence": 0.80,
    },
    "XLE": {
        "thesis": "Sector ETF - best backtested strategy",
        "target_pct": 0.15,
        "stop_pct": -0.10,
        "confidence": 0.72,
    },
    "HAL": {
        "thesis": "Oilfield services - well repair contracts",
        "target_pct": 0.25,
        "stop_pct": -0.15,
        "confidence": 0.70,
    },
    "FRO": {
        "thesis": "Tanker rates from shadow fleet disruption",
        "target_pct": 0.20,
        "stop_pct": -0.12,
        "confidence": 0.65,
    },
    "GLD": {
        "thesis": "Safe haven + Venezuela gold reserves",
        "target_pct": 0.15,
        "stop_pct": -0.08,
        "confidence": 0.60,
    },
}


def get_client():
    """Initialize Alpaca client."""
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=creds["alpaca"]["paper"]
    )


def print_positions(client):
    """Print current positions with thesis context."""
    account = client.get_account()
    positions = client.get_all_positions()

    print("\n" + "=" * 80)
    print("VENEZUELA THESIS - POSITION MONITOR")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print(f"\nAccount Value: ${float(account.portfolio_value):,.2f}")
    print(f"Cash: ${float(account.cash):,.2f}")
    print(f"Day P&L: ${float(account.equity) - float(account.last_equity):+,.2f}")

    print("\n" + "-" * 80)
    print(f"{'Symbol':<8} {'Qty':<6} {'Entry':<10} {'Current':<10} {'P&L':<12} {'P&L%':<8} {'Target':<10} {'Status'}")
    print("-" * 80)

    total_value = 0
    total_pnl = 0
    alerts = []

    for pos in sorted(positions, key=lambda x: x.symbol):
        symbol = pos.symbol
        qty = int(pos.qty)
        entry = float(pos.avg_entry_price)
        current = float(pos.current_price)
        pnl = float(pos.unrealized_pl)
        pnl_pct = float(pos.unrealized_plpc)
        market_value = float(pos.market_value)

        total_value += market_value
        total_pnl += pnl

        # Get config
        config = POSITION_CONFIG.get(symbol, {})
        target_pct = config.get("target_pct", 0.20)
        stop_pct = config.get("stop_pct", -0.15)

        # Determine status
        if pnl_pct >= target_pct:
            status = "[TARGET HIT]"
            alerts.append(f"{symbol}: TARGET reached at {pnl_pct:+.1%}")
        elif pnl_pct <= stop_pct:
            status = "[STOP HIT]"
            alerts.append(f"{symbol}: STOP triggered at {pnl_pct:+.1%}")
        elif pnl_pct > 0:
            status = "Profit"
        elif pnl_pct < -0.05:
            status = "Watch"
        else:
            status = "Normal"

        target_price = entry * (1 + target_pct)

        print(f"{symbol:<8} {qty:<6} ${entry:<9.2f} ${current:<9.2f} "
              f"${pnl:<+11.2f} {pnl_pct:<+7.1%} ${target_price:<9.2f} {status}")

    print("-" * 80)
    print(f"{'TOTAL':<8} {'':<6} {'':<10} {'':<10} ${total_pnl:<+11.2f}")
    print(f"\nTotal Position Value: ${total_value:,.2f}")

    # Print alerts
    if alerts:
        print("\n" + "!" * 80)
        print("ALERTS")
        print("!" * 80)
        for alert in alerts:
            print(f"  {alert}")

    # Thesis summary
    print("\n" + "-" * 80)
    print("THESIS TRACKING")
    print("-" * 80)

    for pos in sorted(positions, key=lambda x: x.symbol):
        config = POSITION_CONFIG.get(pos.symbol, {})
        thesis = config.get("thesis", "No thesis defined")
        confidence = config.get("confidence", 0)
        pnl_pct = float(pos.unrealized_plpc)

        # Progress toward target
        target = config.get("target_pct", 0.20)
        progress = min(1.0, max(0, pnl_pct / target)) if target > 0 else 0
        bar = "█" * int(progress * 10) + "░" * (10 - int(progress * 10))

        print(f"{pos.symbol}: {thesis}")
        print(f"  Confidence: {confidence:.0%} | Progress: [{bar}] {pnl_pct:+.1%} / {target:+.0%}")

    return total_pnl


def save_snapshot(client):
    """Save position snapshot to file."""
    positions = client.get_all_positions()
    account = client.get_account()

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "account_value": float(account.portfolio_value),
        "cash": float(account.cash),
        "positions": [
            {
                "symbol": pos.symbol,
                "qty": int(pos.qty),
                "entry_price": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(pos.unrealized_pl),
                "unrealized_pnl_pct": float(pos.unrealized_plpc),
            }
            for pos in positions
        ],
    }

    # Append to daily log
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = OUTPUT_DIR / f"positions_{date_str}.jsonl"

    with open(log_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    return snapshot


def continuous_monitor(interval_seconds: int = 60):
    """Run continuous monitoring loop."""
    client = get_client()
    logger.info(f"Starting continuous monitor (interval: {interval_seconds}s)")

    last_pnl = 0

    while True:
        try:
            pnl = print_positions(client)
            save_snapshot(client)

            # Alert on significant change
            if abs(pnl - last_pnl) > 100:
                logger.warning(f"Significant P&L change: ${pnl - last_pnl:+,.2f}")

            last_pnl = pnl

        except Exception as e:
            logger.error(f"Monitor error: {e}")

        print(f"\nNext update in {interval_seconds} seconds... (Ctrl+C to stop)")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Monitor Venezuela thesis positions")
    parser.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--interval", type=int, default=60, help="Update interval in seconds")
    args = parser.parse_args()

    client = get_client()

    if args.continuous:
        continuous_monitor(args.interval)
    else:
        print_positions(client)
        save_snapshot(client)


if __name__ == "__main__":
    main()
