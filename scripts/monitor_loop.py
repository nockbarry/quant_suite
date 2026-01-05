#!/usr/bin/env python3
"""
Venezuela Thesis - Continuous Position Monitor
Runs for specified duration with periodic checks and trading decisions.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Position targets and stops
POSITION_CONFIG = {
    "SLB": {"target": 0.30, "stop": -0.15, "add_on_dip": -0.05},
    "VLO": {"target": 0.25, "stop": -0.12, "add_on_dip": -0.05},
    "XLE": {"target": 0.15, "stop": -0.10, "add_on_dip": -0.03},
    "HAL": {"target": 0.25, "stop": -0.15, "add_on_dip": -0.05},
    "FRO": {"target": 0.20, "stop": -0.12, "add_on_dip": -0.05},
    "GLD": {"target": 0.15, "stop": -0.08, "add_on_dip": -0.03},
}

def get_client():
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(creds["alpaca"]["api_key"], creds["alpaca"]["secret_key"], paper=True)

def check_positions(client, iteration):
    """Check positions and make trading decisions."""
    account = client.get_account()
    positions = client.get_all_positions()
    
    cash = float(account.cash)
    portfolio_value = float(account.portfolio_value)
    
    print(f"\n{'='*70}")
    print(f"[{iteration}] {datetime.now().strftime('%H:%M:%S')} | Portfolio: ${portfolio_value:,.2f} | Cash: ${cash:,.2f}")
    print(f"{'='*70}")
    
    total_pnl = 0
    actions = []
    
    print(f"{'Symbol':<6} {'Qty':<5} {'Entry':<8} {'Now':<8} {'P&L':<10} {'%':<7} {'Action'}")
    print("-" * 70)
    
    for pos in sorted(positions, key=lambda x: x.symbol):
        symbol = pos.symbol
        qty = int(pos.qty)
        entry = float(pos.avg_entry_price)
        current = float(pos.current_price)
        pnl = float(pos.unrealized_pl)
        pnl_pct = float(pos.unrealized_plpc)
        total_pnl += pnl
        
        config = POSITION_CONFIG.get(symbol, {})
        target = config.get("target", 0.20)
        stop = config.get("stop", -0.15)
        add_dip = config.get("add_on_dip", -0.05)
        
        # Determine action
        action = ""
        if pnl_pct >= target:
            action = ">>> TAKE PROFIT"
            actions.append(("sell", symbol, qty // 2, f"Target hit {pnl_pct:.1%}"))
        elif pnl_pct <= stop:
            action = ">>> STOP LOSS"
            actions.append(("sell", symbol, qty, f"Stop hit {pnl_pct:.1%}"))
        elif pnl_pct <= add_dip and cash > 1000:
            action = "Consider adding"
        elif pnl_pct > 0.05:
            action = "Winning"
        elif pnl_pct < -0.03:
            action = "Watching"
        
        print(f"{symbol:<6} {qty:<5} ${entry:<7.2f} ${current:<7.2f} ${pnl:<+9.2f} {pnl_pct:<+6.1%} {action}")
    
    print("-" * 70)
    print(f"{'TOTAL':<6} {'':<5} {'':<8} {'':<8} ${total_pnl:<+9.2f}")
    
    # Execute any actions
    for action_type, symbol, qty, reason in actions:
        print(f"\n*** EXECUTING: {action_type.upper()} {qty} {symbol} - {reason}")
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL if action_type == "sell" else OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            ))
            print(f"    Order {order.id}: {order.status}")
        except Exception as e:
            print(f"    Order failed: {e}")
    
    # Log snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "iteration": iteration,
        "portfolio_value": portfolio_value,
        "cash": cash,
        "total_pnl": total_pnl,
        "positions": {pos.symbol: {"pnl": float(pos.unrealized_pl), "pnl_pct": float(pos.unrealized_plpc)} for pos in positions}
    }
    
    log_file = OUTPUT_DIR / f"monitor_log_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
    
    return total_pnl, actions

def run_monitor(duration_minutes=30, interval_seconds=60):
    """Run monitoring loop."""
    client = get_client()
    
    end_time = datetime.now() + timedelta(minutes=duration_minutes)
    iteration = 0
    
    print(f"\n{'#'*70}")
    print(f"# VENEZUELA THESIS MONITOR - {duration_minutes} MINUTES")
    print(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# End: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# Interval: {interval_seconds}s")
    print(f"{'#'*70}")
    
    while datetime.now() < end_time:
        iteration += 1
        remaining = (end_time - datetime.now()).seconds // 60
        
        try:
            pnl, actions = check_positions(client, iteration)
            
            if actions:
                print(f"\n*** TRADES EXECUTED THIS ITERATION ***")
            
        except Exception as e:
            print(f"\n[ERROR] {e}")
        
        print(f"\n[{remaining} min remaining] Next check in {interval_seconds}s...")
        time.sleep(interval_seconds)
    
    print(f"\n{'#'*70}")
    print(f"# MONITOR COMPLETE")
    print(f"# Final check:")
    check_positions(client, "FINAL")
    print(f"{'#'*70}")

if __name__ == "__main__":
    import sys
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    run_monitor(duration, interval)
