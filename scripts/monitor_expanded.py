#!/usr/bin/env python3
"""
Expanded Portfolio Monitor

Monitors all 35+ positions across 8 thesis tiers.
Groups by tier, shows P&L, alerts on targets/stops.

Usage:
    PYTHONPATH=. python scripts/monitor_expanded.py
    PYTHONPATH=. python scripts/monitor_expanded.py --continuous --interval 60
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Position configurations with thesis context
POSITION_CONFIG = {
    # EXISTING TIER 1 POSITIONS
    "SLB": {"tier": "1", "target": 0.30, "stop": -0.15, "thesis": "Reconstruction leader - 15 rigs"},
    "VLO": {"tier": "1", "target": 0.25, "stop": -0.12, "thesis": "Refiner margin expansion"},
    "XLE": {"tier": "1", "target": 0.15, "stop": -0.10, "thesis": "Sector ETF"},
    "HAL": {"tier": "1", "target": 0.25, "stop": -0.15, "thesis": "Oilfield services"},
    "FRO": {"tier": "1", "target": 0.20, "stop": -0.12, "thesis": "Tanker rates"},
    "GLD": {"tier": "1", "target": 0.15, "stop": -0.08, "thesis": "Safe haven + gold reserves"},

    # TIER 1B - ADDITIONAL CORE
    "BKR": {"tier": "1B", "target": 0.25, "stop": -0.15, "thesis": "Baker Hughes oilfield"},
    "WFRD": {"tier": "1B", "target": 0.30, "stop": -0.20, "thesis": "Weatherford equipment"},
    "PBF": {"tier": "1B", "target": 0.25, "stop": -0.15, "thesis": "Heavy crude refiner"},
    "PSX": {"tier": "1B", "target": 0.20, "stop": -0.12, "thesis": "Gulf Coast refining"},
    "MPC": {"tier": "1B", "target": 0.20, "stop": -0.12, "thesis": "Marathon refining"},

    # TIER 2 - TANKERS
    "STNG": {"tier": "2", "target": 0.25, "stop": -0.15, "thesis": "Scorpio tanker rates"},
    "DHT": {"tier": "2", "target": 0.20, "stop": -0.12, "thesis": "DHT VLCC tankers"},
    "INSW": {"tier": "2", "target": 0.20, "stop": -0.12, "thesis": "Int'l Seaways fleet"},

    # TIER 3 - CANADIAN
    "CNQ": {"tier": "3", "target": 0.20, "stop": -0.12, "thesis": "Canadian heavy crude"},
    "SU": {"tier": "3", "target": 0.20, "stop": -0.12, "thesis": "Suncor oil sands"},
    "IMO": {"tier": "3", "target": 0.18, "stop": -0.10, "thesis": "Imperial Oil"},

    # TIER 4 - CUBA DOMINO
    "RCL": {"tier": "4", "target": 0.25, "stop": -0.15, "thesis": "Royal Caribbean Cuba"},
    "CCL": {"tier": "4", "target": 0.25, "stop": -0.15, "thesis": "Carnival Cuba"},
    "NCLH": {"tier": "4", "target": 0.25, "stop": -0.15, "thesis": "Norwegian Cuba"},
    "MAR": {"tier": "4", "target": 0.20, "stop": -0.12, "thesis": "Marriott Cuba hotels"},

    # TIER 5 - DEFENSE/RECONSTRUCTION
    "KBR": {"tier": "5", "target": 0.25, "stop": -0.15, "thesis": "KBR reconstruction"},
    "FLR": {"tier": "5", "target": 0.25, "stop": -0.15, "thesis": "Fluor infrastructure"},
    "PSN": {"tier": "5", "target": 0.20, "stop": -0.12, "thesis": "Parsons govt contracts"},
    "J": {"tier": "5", "target": 0.20, "stop": -0.12, "thesis": "Jacobs engineering"},

    # TIER 6 - GOLD/MINERALS
    "GDX": {"tier": "6", "target": 0.20, "stop": -0.12, "thesis": "Gold miners ETF"},
    "GOLD": {"tier": "6", "target": 0.20, "stop": -0.12, "thesis": "Barrick Gold"},
    "NEM": {"tier": "6", "target": 0.18, "stop": -0.10, "thesis": "Newmont mining"},
    "REMX": {"tier": "6", "target": 0.25, "stop": -0.15, "thesis": "Rare earth ETF"},

    # TIER 7 - EM/DEBT
    "EMB": {"tier": "7", "target": 0.15, "stop": -0.10, "thesis": "EM bonds"},
    "VWOB": {"tier": "7", "target": 0.15, "stop": -0.10, "thesis": "Vanguard EM govt"},
    "EWZ": {"tier": "7", "target": 0.15, "stop": -0.10, "thesis": "Brazil ETF"},

    # TIER 8 - BROAD ENERGY
    "OIH": {"tier": "8", "target": 0.20, "stop": -0.12, "thesis": "Oil services ETF"},
    "XOP": {"tier": "8", "target": 0.18, "stop": -0.12, "thesis": "E&P ETF"},
    "IEO": {"tier": "8", "target": 0.18, "stop": -0.12, "thesis": "iShares E&P"},

    # TIER 9 - SYNTHETIC OPTIONS (Leveraged ETFs)
    "ERX": {"tier": "9", "target": 0.40, "stop": -0.25, "thesis": "2x Bull Energy - call exposure"},
    "GUSH": {"tier": "9", "target": 0.50, "stop": -0.30, "thesis": "2x Bull Oil & Gas E&P"},
    "NUGT": {"tier": "9", "target": 0.40, "stop": -0.25, "thesis": "2x Bull Gold Miners"},
    "UGL": {"tier": "9", "target": 0.30, "stop": -0.20, "thesis": "2x Bull Gold"},
    "ERY": {"tier": "9", "target": 0.30, "stop": -0.25, "thesis": "2x Bear Energy - put hedge"},
    "VXX": {"tier": "9", "target": 0.50, "stop": -0.30, "thesis": "VIX - chaos vol play"},
    "UVXY": {"tier": "9", "target": 0.80, "stop": -0.40, "thesis": "1.5x VIX - amplified vol"},
}

TIER_NAMES = {
    "1": "Core Venezuela",
    "1B": "Additional Core",
    "2": "Tankers",
    "3": "Canadian Heavy",
    "4": "Cuba Domino",
    "5": "Defense/Reconstruction",
    "6": "Gold/Minerals",
    "7": "EM/Debt",
    "8": "Broad Energy",
    "9": "Synthetic Options",
}


def get_client():
    """Initialize Alpaca client."""
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True
    )


def monitor_portfolio(client, execute_stops=True):
    """Monitor all positions by tier."""
    account = client.get_account()
    positions = client.get_all_positions()

    print("\n" + "=" * 90)
    print(f"VENEZUELA THESIS - EXPANDED PORTFOLIO MONITOR")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    print(f"\nPortfolio: ${float(account.portfolio_value):,.2f} | "
          f"Cash: ${float(account.cash):,.2f} | "
          f"Day P&L: ${float(account.equity) - float(account.last_equity):+,.2f}")

    # Group positions by tier
    by_tier = {}
    total_pnl = 0
    total_value = 0
    alerts = []
    actions = []

    for pos in positions:
        symbol = pos.symbol
        config = POSITION_CONFIG.get(symbol, {"tier": "?", "target": 0.20, "stop": -0.15, "thesis": "Unknown"})
        tier = config["tier"]

        if tier not in by_tier:
            by_tier[tier] = []

        pnl = float(pos.unrealized_pl)
        pnl_pct = float(pos.unrealized_plpc)
        value = float(pos.market_value)

        total_pnl += pnl
        total_value += value

        # Check for alerts
        if pnl_pct >= config["target"]:
            alerts.append(f"{symbol}: TARGET HIT {pnl_pct:+.1%}")
            if execute_stops:
                qty = float(pos.qty)
                actions.append(("TAKE_PROFIT", symbol, int(qty // 2), f"Target {config['target']:.0%} hit"))
        elif pnl_pct <= config["stop"]:
            alerts.append(f"{symbol}: STOP HIT {pnl_pct:+.1%}")
            if execute_stops:
                qty = float(pos.qty)
                actions.append(("STOP_LOSS", symbol, int(qty), f"Stop {config['stop']:.0%} hit"))

        by_tier[tier].append({
            "symbol": symbol,
            "qty": float(pos.qty),
            "entry": float(pos.avg_entry_price),
            "current": float(pos.current_price),
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "value": value,
            "thesis": config["thesis"],
            "target": config["target"],
            "stop": config["stop"],
        })

    # Print by tier
    for tier in sorted(by_tier.keys()):
        tier_name = TIER_NAMES.get(tier, "Unknown")
        tier_positions = by_tier[tier]
        tier_pnl = sum(p["pnl"] for p in tier_positions)
        tier_value = sum(p["value"] for p in tier_positions)

        print(f"\n{'─' * 90}")
        print(f"TIER {tier}: {tier_name} | Value: ${tier_value:,.0f} | P&L: ${tier_pnl:+,.2f}")
        print(f"{'─' * 90}")
        print(f"{'Symbol':<6} {'Qty':>6} {'Entry':<8} {'Now':<8} {'P&L':>10} {'%':>7} {'Status':<12} {'Thesis'}")
        print("-" * 90)

        for p in sorted(tier_positions, key=lambda x: x["pnl_pct"], reverse=True):
            # Determine status
            if p["pnl_pct"] >= p["target"]:
                status = ">>> TARGET"
            elif p["pnl_pct"] <= p["stop"]:
                status = ">>> STOP"
            elif p["pnl_pct"] > 0.05:
                status = "Winning"
            elif p["pnl_pct"] < -0.05:
                status = "Watch"
            else:
                status = "Normal"

            qty_str = f"{p['qty']:.1f}" if p['qty'] != int(p['qty']) else f"{int(p['qty'])}"
            print(f"{p['symbol']:<6} {qty_str:>6} ${p['entry']:<7.2f} ${p['current']:<7.2f} "
                  f"${p['pnl']:>+9.2f} {p['pnl_pct']:>+6.1%} {status:<12} {p['thesis']}")

    # Summary
    print("\n" + "=" * 90)
    print(f"TOTAL: {len(positions)} positions | Value: ${total_value:,.2f} | P&L: ${total_pnl:+,.2f}")
    print("=" * 90)

    # Tier summary
    print(f"\n{'Tier':<20} {'Positions':<10} {'Value':>12} {'P&L':>12} {'Avg %':>10}")
    print("-" * 70)
    for tier in sorted(by_tier.keys()):
        tier_name = TIER_NAMES.get(tier, "Unknown")
        tier_positions = by_tier[tier]
        tier_pnl = sum(p["pnl"] for p in tier_positions)
        tier_value = sum(p["value"] for p in tier_positions)
        tier_avg_pct = sum(p["pnl_pct"] for p in tier_positions) / len(tier_positions) if tier_positions else 0
        print(f"{tier}: {tier_name:<17} {len(tier_positions):<10} ${tier_value:>10,.0f} ${tier_pnl:>+10,.2f} {tier_avg_pct:>+9.2%}")

    # Alerts
    if alerts:
        print("\n" + "!" * 90)
        print("ALERTS")
        print("!" * 90)
        for alert in alerts:
            print(f"  {alert}")

    # Execute actions
    if actions:
        print("\n" + "*" * 90)
        print("EXECUTING TRADES")
        print("*" * 90)
        for action_type, symbol, qty, reason in actions:
            print(f"\n{action_type}: {symbol} x {qty} - {reason}")
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                ))
                print(f"  Order {order.id}: {order.status}")
            except Exception as e:
                print(f"  Failed: {e}")

    # Save snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "portfolio_value": float(account.portfolio_value),
        "cash": float(account.cash),
        "total_pnl": total_pnl,
        "total_value": total_value,
        "positions": len(positions),
        "by_tier": {tier: {
            "value": sum(p["value"] for p in positions),
            "pnl": sum(p["pnl"] for p in positions),
            "symbols": [p["symbol"] for p in positions]
        } for tier, positions in by_tier.items()},
        "alerts": alerts,
    }

    log_file = OUTPUT_DIR / f"expanded_monitor_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    return total_pnl, alerts, by_tier


def continuous_monitor(interval_seconds=60, duration_minutes=30):
    """Run continuous monitoring."""
    client = get_client()
    end_time = datetime.now().timestamp() + (duration_minutes * 60)
    iteration = 0

    print(f"\nStarting continuous monitor for {duration_minutes} minutes")
    print(f"Interval: {interval_seconds} seconds")

    while datetime.now().timestamp() < end_time:
        iteration += 1
        remaining = int((end_time - datetime.now().timestamp()) / 60)

        print(f"\n[Iteration {iteration}] {remaining} minutes remaining")
        try:
            pnl, alerts, by_tier = monitor_portfolio(client, execute_stops=True)
        except Exception as e:
            print(f"Error: {e}")

        print(f"\nNext check in {interval_seconds}s...")
        time.sleep(interval_seconds)

    print("\nMonitor complete. Final check:")
    monitor_portfolio(client, execute_stops=False)


def main():
    parser = argparse.ArgumentParser(description="Monitor expanded portfolio")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", type=int, default=60, help="Check interval (seconds)")
    parser.add_argument("--duration", type=int, default=30, help="Duration (minutes)")
    args = parser.parse_args()

    client = get_client()

    if args.continuous:
        continuous_monitor(args.interval, args.duration)
    else:
        monitor_portfolio(client, execute_stops=False)


if __name__ == "__main__":
    main()
