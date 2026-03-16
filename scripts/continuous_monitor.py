#!/usr/bin/env python3
"""
Continuous Market Monitor - 7-hour surveillance with 10-minute intervals.

Usage:
    PYTHONPATH=. python3 scripts/continuous_monitor.py
    PYTHONPATH=. python3 scripts/continuous_monitor.py --hours 7 --interval 10
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.synthesis.state import UnifiedState
from src.core.paths import paths

# Configuration
RESULTS_DIR = paths.base
LOG_FILE = RESULTS_DIR / "logs" / f"market_watch_{datetime.now().strftime('%Y%m%d')}.jsonl"

# Alert thresholds
STOP_LOSS_PCT = -12.0
PROFIT_TARGET_PCT = 35.0
LARGE_MOVE_PCT = 5.0
VIX_WARNING = 20.0
VIX_CRITICAL = 25.0
GOLD_SUPPORT = 4900.0
GOLD_INVALIDATION = 4500.0
ENERGY_MAX_PCT = 50.0

# Watch list - positions to monitor closely
WATCH_LIST = {
    "LEN": {"reason": "stop_loss_watch", "threshold": -12.0},
    "GOLD": {"reason": "profit_target", "threshold": 35.0},
    "FRO": {"reason": "profit_target", "threshold": 35.0},
    "STNG": {"reason": "profit_target", "threshold": 30.0},
    "INSW": {"reason": "profit_target", "threshold": 30.0},
}


def load_state():
    """Load current unified state."""
    state_file = RESULTS_DIR / "live" / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {}


def get_position_metrics(state):
    """Extract position metrics from state."""
    positions = state.get("positions", [])
    metrics = []

    for p in positions:
        symbol = p.get("symbol", "?")
        pnl_pct = p.get("unrealized_pnl_pct", 0)
        value = p.get("market_value", 0)
        qty = p.get("quantity", 0)

        metrics.append({
            "symbol": symbol,
            "pnl_pct": pnl_pct,
            "value": value,
            "qty": qty,
        })

    return sorted(metrics, key=lambda x: x["pnl_pct"])


def calculate_sector_exposure(state):
    """Calculate sector concentration."""
    positions = state.get("positions", [])
    total = sum(p.get("market_value", 0) for p in positions)

    if total == 0:
        return {}

    # Energy symbols (approximate)
    energy_symbols = {
        "SLB", "HAL", "XLE", "XOP", "OIH", "ERX", "GUSH", "IEO",
        "BKR", "FRO", "STNG", "INSW", "DHT", "MPC", "PSX", "PBF",
        "CNQ", "SU", "IMO", "PBR", "WFRD"
    }

    energy_value = sum(
        p.get("market_value", 0) for p in positions
        if p.get("symbol") in energy_symbols
    )

    return {
        "energy_pct": (energy_value / total * 100) if total else 0,
        "energy_value": energy_value,
        "total_value": total,
    }


def check_alerts(positions, sector_exposure, prev_positions=None):
    """Check for alert conditions."""
    alerts = []
    recommendations = []

    # Position alerts
    for p in positions:
        symbol = p["symbol"]
        pnl_pct = p["pnl_pct"]

        # Stop loss breach
        if pnl_pct <= STOP_LOSS_PCT:
            alerts.append({
                "level": "CRITICAL",
                "type": "stop_loss",
                "symbol": symbol,
                "message": f"{symbol} at {pnl_pct:.1f}% - STOP LOSS BREACHED",
                "action": "EXIT IMMEDIATELY"
            })
            recommendations.append({
                "action": "SELL",
                "symbol": symbol,
                "reason": f"Stop loss at {pnl_pct:.1f}%",
                "urgency": "immediate"
            })

        # Near stop loss
        elif pnl_pct <= STOP_LOSS_PCT + 2:
            alerts.append({
                "level": "WARNING",
                "type": "stop_loss_warning",
                "symbol": symbol,
                "message": f"{symbol} at {pnl_pct:.1f}% - approaching stop loss",
            })

        # Profit target
        if pnl_pct >= PROFIT_TARGET_PCT:
            alerts.append({
                "level": "INFO",
                "type": "profit_target",
                "symbol": symbol,
                "message": f"{symbol} at +{pnl_pct:.1f}% - above profit target",
            })
            recommendations.append({
                "action": "TRIM",
                "symbol": symbol,
                "reason": f"Profit target reached at +{pnl_pct:.1f}%",
                "size": "50%",
                "urgency": "when_convenient"
            })

        # Watch list specific
        if symbol in WATCH_LIST:
            watch = WATCH_LIST[symbol]
            if watch["reason"] == "stop_loss_watch" and pnl_pct <= watch["threshold"]:
                alerts.append({
                    "level": "CRITICAL",
                    "type": "watch_list_trigger",
                    "symbol": symbol,
                    "message": f"{symbol} hit watch threshold {watch['threshold']}%",
                })

    # Sector concentration
    if sector_exposure.get("energy_pct", 0) >= ENERGY_MAX_PCT:
        alerts.append({
            "level": "WARNING",
            "type": "concentration",
            "message": f"Energy at {sector_exposure['energy_pct']:.1f}% - at limit",
            "action": "NO new energy positions"
        })

    return alerts, recommendations


def log_observation(cycle, portfolio, markets, alerts, recommendations):
    """Log observation to JSONL file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    observation = {
        "timestamp": datetime.now().isoformat(),
        "cycle": cycle,
        "portfolio": portfolio,
        "markets": markets,
        "alerts": alerts,
        "recommendations": recommendations,
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(observation) + "\n")

    return observation


def print_status(cycle, portfolio, positions, sector_exp, alerts, recommendations):
    """Print formatted status to console."""
    now = datetime.now().strftime("%H:%M:%S")

    print(f"\n{'='*70}")
    print(f"MARKET WATCH - Cycle {cycle} - {now}")
    print(f"{'='*70}")

    # Portfolio
    print(f"\nPORTFOLIO: ${portfolio.get('equity', 0):,.0f} | "
          f"Day P&L: ${portfolio.get('day_pnl', 0):+,.0f} "
          f"({portfolio.get('day_pnl_pct', 0):+.2f}%)")

    # Sector exposure
    print(f"Energy Exposure: {sector_exp.get('energy_pct', 0):.1f}% "
          f"(${sector_exp.get('energy_value', 0):,.0f})")

    # Alerts
    if alerts:
        print(f"\n{'!'*30} ALERTS {'!'*30}")
        for a in alerts:
            level_icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(a["level"], "⚪")
            print(f"  {level_icon} [{a['level']}] {a['message']}")
            if a.get("action"):
                print(f"     Action: {a['action']}")

    # Recommendations
    if recommendations:
        print(f"\nRECOMMENDATIONS:")
        for r in recommendations:
            print(f"  → {r['action']} {r['symbol']}: {r['reason']}")

    # Watch list
    print(f"\nWATCH LIST:")
    for p in positions:
        if p["symbol"] in WATCH_LIST:
            icon = "🔴" if p["pnl_pct"] < -8 else "🟡" if p["pnl_pct"] < 0 else "🟢"
            print(f"  {icon} {p['symbol']}: {p['pnl_pct']:+.1f}% (${p['value']:,.0f})")

    # Top gainers/losers
    print(f"\nTOP LOSERS:")
    for p in positions[:3]:
        print(f"  {p['symbol']}: {p['pnl_pct']:+.1f}%")

    print(f"\nTOP GAINERS:")
    for p in positions[-3:]:
        print(f"  {p['symbol']}: {p['pnl_pct']:+.1f}%")


def print_hourly_summary(cycle, all_alerts, all_recommendations):
    """Print hourly summary."""
    print(f"\n{'#'*70}")
    print(f"HOURLY SUMMARY - After {cycle} cycles")
    print(f"{'#'*70}")

    # Count alerts by level
    alert_counts = {}
    for a in all_alerts:
        level = a.get("level", "UNKNOWN")
        alert_counts[level] = alert_counts.get(level, 0) + 1

    print(f"\nAlert Summary:")
    for level, count in sorted(alert_counts.items()):
        print(f"  {level}: {count}")

    # Unique recommendations
    rec_actions = {}
    for r in all_recommendations:
        key = f"{r['action']} {r['symbol']}"
        if key not in rec_actions:
            rec_actions[key] = r

    if rec_actions:
        print(f"\nPending Recommendations:")
        for key, r in rec_actions.items():
            print(f"  → {key}: {r['reason']}")


async def run_monitor(hours: int = 7, interval_minutes: int = 10):
    """Run the monitoring loop."""
    total_cycles = (hours * 60) // interval_minutes
    interval_seconds = interval_minutes * 60

    print(f"\n{'='*70}")
    print(f"CONTINUOUS MARKET MONITOR STARTING")
    print(f"Duration: {hours} hours | Interval: {interval_minutes} min | Cycles: {total_cycles}")
    print(f"Log file: {LOG_FILE}")
    print(f"{'='*70}")

    all_alerts = []
    all_recommendations = []
    prev_positions = None

    for cycle in range(1, total_cycles + 1):
        try:
            # Load state
            state = load_state()

            # Get metrics
            positions = get_position_metrics(state)
            sector_exp = calculate_sector_exposure(state)

            portfolio = {
                "equity": state.get("portfolio", {}).get("equity", 0),
                "day_pnl": state.get("portfolio", {}).get("day_pnl", 0),
                "day_pnl_pct": state.get("portfolio", {}).get("day_pnl_pct", 0),
                "cash": state.get("portfolio", {}).get("cash", 0),
            }

            markets = {
                "regime": state.get("market", {}).get("regime", "unknown"),
                "sentiment": state.get("sentiment", {}).get("overall", "neutral"),
            }

            # Check alerts
            alerts, recommendations = check_alerts(positions, sector_exp, prev_positions)
            all_alerts.extend(alerts)
            all_recommendations.extend(recommendations)

            # Log observation
            log_observation(cycle, portfolio, markets, alerts, recommendations)

            # Print status
            print_status(cycle, portfolio, positions, sector_exp, alerts, recommendations)

            # Hourly summary
            if cycle % 6 == 0:  # Every hour (6 x 10min)
                print_hourly_summary(cycle, all_alerts, all_recommendations)

            # Store for next comparison
            prev_positions = {p["symbol"]: p for p in positions}

            # Wait for next cycle (unless last)
            if cycle < total_cycles:
                print(f"\nNext check in {interval_minutes} minutes... (Ctrl+C to stop)")
                await asyncio.sleep(interval_seconds)

        except KeyboardInterrupt:
            print(f"\n\nMonitoring stopped by user after {cycle} cycles.")
            break
        except Exception as e:
            print(f"\nError in cycle {cycle}: {e}")
            await asyncio.sleep(60)  # Wait 1 min on error

    print(f"\n{'='*70}")
    print(f"MONITORING COMPLETE - {cycle} cycles over {hours} hours")
    print(f"Log saved to: {LOG_FILE}")
    print(f"{'='*70}")

    # Final summary
    print_hourly_summary(cycle, all_alerts, all_recommendations)


def main():
    parser = argparse.ArgumentParser(description="Continuous Market Monitor")
    parser.add_argument("--hours", type=int, default=7, help="Hours to monitor")
    parser.add_argument("--interval", type=int, default=10, help="Interval in minutes")
    args = parser.parse_args()

    asyncio.run(run_monitor(hours=args.hours, interval_minutes=args.interval))


if __name__ == "__main__":
    main()
