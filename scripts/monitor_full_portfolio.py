#!/usr/bin/env python3
"""
Full Portfolio Monitor - Stocks + Options

Monitors all positions including actual options contracts.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from alpaca.trading.client import TradingClient

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")


def get_client():
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(creds["alpaca"]["api_key"], creds["alpaca"]["secret_key"], paper=True)


def parse_option_symbol(symbol):
    """Parse option symbol like SLB260206C00044000."""
    if len(symbol) < 15:
        return None
    try:
        underlying = symbol[:3] if symbol[3].isdigit() else symbol[:4]
        rest = symbol[len(underlying):]
        exp_date = rest[:6]  # YYMMDD
        opt_type = "CALL" if rest[6] == "C" else "PUT"
        strike = float(rest[7:]) / 1000
        return {
            "underlying": underlying,
            "expiration": f"20{exp_date[:2]}-{exp_date[2:4]}-{exp_date[4:6]}",
            "type": opt_type,
            "strike": strike,
        }
    except:
        return None


def monitor_portfolio(client):
    """Monitor full portfolio."""
    account = client.get_account()
    positions = client.get_all_positions()

    # Separate stocks and options
    stocks = []
    options = []

    for pos in positions:
        if len(pos.symbol) > 10:
            options.append(pos)
        else:
            stocks.append(pos)

    print("\n" + "=" * 95)
    print(f"FULL PORTFOLIO MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 95)

    portfolio_value = float(account.portfolio_value)
    cash = float(account.cash)
    equity = float(account.equity)
    last_equity = float(account.last_equity)
    day_pnl = equity - last_equity

    print(f"\nPortfolio: ${portfolio_value:,.2f} | Cash: ${cash:,.2f} | Day P&L: ${day_pnl:+,.2f}")
    print(f"Positions: {len(stocks)} stocks + {len(options)} options = {len(positions)} total")

    # Stock summary
    stock_value = 0
    stock_pnl = 0
    for pos in stocks:
        try:
            stock_value += float(pos.market_value) if pos.market_value else 0
            stock_pnl += float(pos.unrealized_pl) if pos.unrealized_pl else 0
        except:
            pass

    print(f"\nStocks: ${stock_value:,.2f} | P&L: ${stock_pnl:+,.2f}")

    # Options detail
    print("\n" + "-" * 95)
    print("OPTIONS POSITIONS")
    print("-" * 95)
    print(f"{'Underlying':<6} {'Type':<5} {'Strike':>8} {'Exp':<12} {'Qty':>4} {'Entry':>7} {'Now':>7} {'P&L':>10} {'%':>8}")
    print("-" * 95)

    options_value = 0
    options_pnl = 0
    options_by_underlying = {}

    for pos in sorted(options, key=lambda x: x.symbol):
        try:
            parsed = parse_option_symbol(pos.symbol)
            if not parsed:
                continue

            entry = float(pos.avg_entry_price) if pos.avg_entry_price else 0
            current = float(pos.current_price) if pos.current_price else entry
            pnl = float(pos.unrealized_pl) if pos.unrealized_pl else 0
            pnl_pct = float(pos.unrealized_plpc) if pos.unrealized_plpc else 0
            qty = float(pos.qty) if pos.qty else 0
            value = float(pos.market_value) if pos.market_value else 0

            options_value += value
            options_pnl += pnl

            underlying = parsed["underlying"]
            if underlying not in options_by_underlying:
                options_by_underlying[underlying] = {"value": 0, "pnl": 0, "count": 0}
            options_by_underlying[underlying]["value"] += value
            options_by_underlying[underlying]["pnl"] += pnl
            options_by_underlying[underlying]["count"] += 1

            # Status indicator
            if pnl_pct <= -0.50:
                status = "!!!"
            elif pnl_pct <= -0.25:
                status = "! "
            elif pnl_pct >= 0.25:
                status = "+++"
            elif pnl_pct >= 0:
                status = "+ "
            else:
                status = "  "

            print(f"{parsed['underlying']:<6} {parsed['type']:<5} ${parsed['strike']:>7.0f} "
                  f"{parsed['expiration']:<12} {qty:>4.0f} ${entry:>6.2f} ${current:>6.2f} "
                  f"${pnl:>+9.2f} {pnl_pct:>+7.1%} {status}")

        except Exception as e:
            print(f"{pos.symbol}: Error - {e}")

    print("-" * 95)
    print(f"{'OPTIONS TOTAL':<6} {'':<5} {'':<8} {'':<12} {'':<4} {'':<7} {'':<7} "
          f"${options_pnl:>+9.2f}")

    # Summary by underlying
    print("\n" + "-" * 95)
    print("OPTIONS BY UNDERLYING")
    print("-" * 95)
    print(f"{'Symbol':<8} {'Contracts':>10} {'Value':>12} {'P&L':>12}")
    print("-" * 50)

    for sym in sorted(options_by_underlying.keys()):
        data = options_by_underlying[sym]
        print(f"{sym:<8} {data['count']:>10} ${data['value']:>11,.2f} ${data['pnl']:>+11.2f}")

    # Total summary
    print("\n" + "=" * 95)
    print("PORTFOLIO SUMMARY")
    print("=" * 95)
    print(f"{'Category':<20} {'Positions':>10} {'Value':>15} {'P&L':>15}")
    print("-" * 65)
    print(f"{'Stocks':<20} {len(stocks):>10} ${stock_value:>14,.2f} ${stock_pnl:>+14,.2f}")
    print(f"{'Options':<20} {len(options):>10} ${options_value:>14,.2f} ${options_pnl:>+14,.2f}")
    print("-" * 65)
    total_value = stock_value + options_value
    total_pnl = stock_pnl + options_pnl
    print(f"{'TOTAL':<20} {len(positions):>10} ${total_value:>14,.2f} ${total_pnl:>+14,.2f}")

    # Save snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "portfolio_value": portfolio_value,
        "cash": cash,
        "day_pnl": day_pnl,
        "stocks": {"count": len(stocks), "value": stock_value, "pnl": stock_pnl},
        "options": {"count": len(options), "value": options_value, "pnl": options_pnl},
        "total_pnl": total_pnl,
    }

    log_file = OUTPUT_DIR / f"full_portfolio_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    return total_pnl


def continuous_monitor(interval=60, duration=60):
    """Run continuous monitoring."""
    client = get_client()
    end_time = datetime.now().timestamp() + (duration * 60)
    iteration = 0

    print(f"Starting continuous monitor for {duration} minutes...")

    while datetime.now().timestamp() < end_time:
        iteration += 1
        remaining = int((end_time - datetime.now().timestamp()) / 60)

        try:
            pnl = monitor_portfolio(client)
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n[{remaining} min remaining] Next check in {interval}s...")
        time.sleep(interval)

    print("\n=== MONITOR COMPLETE ===")
    monitor_portfolio(client)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        continuous_monitor(interval, duration)
    else:
        client = get_client()
        monitor_portfolio(client)
