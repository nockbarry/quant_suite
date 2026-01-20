#!/usr/bin/env python3
"""
Market Watcher Daemon - Runs independently of Claude Code.

This script monitors the market at configurable intervals and logs to the
central agent activity log, making activity visible in the unified dashboard.

Usage:
    python3 scripts/daemons/market_watcher.py [interval_seconds] [duration_minutes]

    # Run for 1 hour with 5-minute checks (default)
    python3 scripts/daemons/market_watcher.py

    # Run for 2 hours with 2-minute checks
    python3 scripts/daemons/market_watcher.py 120 120

    # Run continuously (8 hours for market day)
    nohup python3 scripts/daemons/market_watcher.py 300 480 &
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path


def log_to_dashboard(event_type: str, data: dict):
    """Log activity to the central agent activity log."""
    log_path = Path.home() / "quant_results" / "logs" / "agent_activity.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        **data,
    }

    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def market_check(check_num: int, baseline: dict | None = None):
    """Perform a single market check."""
    state_file = Path.home() / "quant_results" / "live" / "state.json"
    log_file = Path.home() / "quant_results" / "logs" / "market_watch.log"

    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(state_file) as f:
            state = json.load(f)

        market = state.get("market", {})
        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        # Extract metrics
        spy_price = market.get("spy_price", 0)
        spy_change = market.get("spy_change_pct", 0)
        qqq_price = market.get("qqq_price", 0)
        qqq_change = market.get("qqq_change_pct", 0)
        vix = market.get("vix", 0)
        equity = portfolio.get("equity", 0)
        day_pnl = portfolio.get("day_pnl", 0)
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)

        # Set baseline on first check
        if baseline is None:
            baseline = {"equity": equity, "spy": spy_price}

        # Calculate session change
        session_change_pct = ((equity - baseline["equity"]) / baseline["equity"] * 100) if baseline["equity"] else 0

        # Check alerts
        alerts = []
        if vix > 25:
            alerts.append(f"VIX HIGH: {vix:.2f}")
        if day_pnl_pct < -3:
            alerts.append(f"DRAWDOWN: {day_pnl_pct:.2f}%")
        if session_change_pct < -2:
            alerts.append(f"SESSION DOWN: {session_change_pct:.2f}%")

        # Check individual positions
        notable_moves = []
        for pos in positions:
            try:
                pnl = float(pos.get("unrealized_pnl_pct", 0))
                symbol = pos.get("symbol", "UNK")
                if pnl < -5:
                    alerts.append(f"{symbol} DOWN {pnl:.1f}%")
                if abs(pnl) > 10:
                    notable_moves.append(f"{symbol}: {pnl:+.1f}%")
            except (TypeError, ValueError):
                continue

        # Format check
        timestamp = datetime.now().strftime("%H:%M:%S")
        alert_banner = ""
        if alerts:
            alert_banner = f"\n{'!'*60}\nALERTS: {'; '.join(alerts)}\n{'!'*60}\n"

        check = f"""{alert_banner}
=== MARKET CHECK [{timestamp}] (Check #{check_num}) ===
SPY: ${spy_price:.2f} ({spy_change:+.2f}%)
QQQ: ${qqq_price:.2f} ({qqq_change:+.2f}%)
VIX: {vix:.2f}
Portfolio: ${equity:,.2f} ({day_pnl_pct:+.2f}% day, {session_change_pct:+.2f}% session)
Day P&L: ${day_pnl:,.2f}
Notable Moves: {', '.join(notable_moves[:5]) if notable_moves else 'None'}
Alerts: {'; '.join(alerts) if alerts else 'None'}
"""

        # Write to market watch log
        with open(log_file, "a") as f:
            f.write(check)

        # Log to agent activity dashboard
        log_to_dashboard("market_check", {
            "agent_id": "market_watcher_daemon",
            "agent_type": "monitor",
            "check_num": check_num,
            "spy_price": spy_price,
            "spy_change": spy_change,
            "vix": vix,
            "equity": equity,
            "day_pnl": day_pnl,
            "day_pnl_pct": day_pnl_pct,
            "session_change_pct": session_change_pct,
            "alerts": alerts,
            "alert_count": len(alerts),
        })

        return check, alerts, baseline

    except Exception as e:
        error_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}\n"
        log_to_dashboard("market_check_error", {
            "agent_id": "market_watcher_daemon",
            "error": str(e),
        })
        return error_msg, [], baseline


def run_watcher(interval_seconds: int = 300, duration_minutes: int = 60):
    """Run market watcher for specified duration."""
    checks = int(duration_minutes * 60 / interval_seconds)

    # Log session start
    log_to_dashboard("agent_start", {
        "agent_id": "market_watcher_daemon",
        "agent_type": "monitor",
        "task": f"Market monitoring: {checks} checks, {interval_seconds}s interval, {duration_minutes}m duration",
        "started_at": datetime.now().isoformat(),
        "status": "running",
    })

    header = f"""
{'='*60}
MARKET WATCHER SESSION STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Interval: {interval_seconds}s | Duration: {duration_minutes}m | Checks: {checks}
{'='*60}
"""
    print(header)

    # Write header to log
    log_file = Path.home() / "quant_results" / "logs" / "market_watch.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(header)

    baseline = None
    total_alerts = 0

    for i in range(1, checks + 1):
        check, alerts, baseline = market_check(i, baseline)
        print(check)
        total_alerts += len(alerts)

        if i < checks:
            print(f"Next check in {interval_seconds}s...")
            time.sleep(interval_seconds)

    # Log session complete
    footer = f"""
{'='*60}
MARKET WATCHER SESSION COMPLETE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total checks: {checks} | Total alerts: {total_alerts}
{'='*60}
"""
    print(footer)

    with open(log_file, "a") as f:
        f.write(footer)

    log_to_dashboard("agent_complete", {
        "agent_id": "market_watcher_daemon",
        "agent_type": "monitor",
        "status": "completed",
        "result_summary": f"Completed {checks} checks with {total_alerts} total alerts",
        "completed_at": datetime.now().isoformat(),
        "checks_completed": checks,
        "total_alerts": total_alerts,
    })


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    run_watcher(interval, duration)
