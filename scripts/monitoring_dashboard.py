#!/usr/bin/env python3
"""Unified Monitoring Dashboard.

Single-pane view of all trading system health:
- Portfolio status and P&L
- Active positions and drawdowns
- Signal health
- Execution quality
- Thesis performance
- Alerts and warnings

Usage:
    python scripts/monitoring_dashboard.py
    python scripts/monitoring_dashboard.py --refresh 60  # Refresh every 60 seconds

Created: 2026-01-20
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths


def clear_screen():
    """Clear terminal screen."""
    print("\033[2J\033[H", end="")


def color(text: str, color_code: str) -> str:
    """Add ANSI color to text."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color_code, '')}{text}{colors['reset']}"


def pnl_color(value: float) -> str:
    """Color P&L values appropriately."""
    if value > 0:
        return color(f"+${value:,.0f}", "green")
    elif value < 0:
        return color(f"-${abs(value):,.0f}", "red")
    else:
        return f"${value:,.0f}"


def pct_color(value: float) -> str:
    """Color percentage values appropriately."""
    if value > 0:
        return color(f"+{value:.2f}%", "green")
    elif value < 0:
        return color(f"{value:.2f}%", "red")
    else:
        return f"{value:.2f}%"


def load_unified_state() -> dict:
    """Load unified state from file."""
    state_path = paths.live_state
    if not state_path.exists():
        return {}

    with open(state_path) as f:
        return json.load(f)


def load_signal_health() -> dict:
    """Load signal health metrics."""
    health_path = paths.knowledge / "signal_health" / "signal_metrics.json"
    if not health_path.exists():
        return {}

    with open(health_path) as f:
        return json.load(f)


def load_execution_quality() -> dict:
    """Load execution quality summary."""
    exec_path = paths.knowledge / "execution" / "execution_summary.json"
    if not exec_path.exists():
        return {}

    with open(exec_path) as f:
        return json.load(f)


def load_drawdown_state() -> dict:
    """Load drawdown state."""
    dd_path = paths.live / "drawdown" / "drawdown_state.json"
    if not dd_path.exists():
        return {}

    with open(dd_path) as f:
        return json.load(f)


def print_header():
    """Print dashboard header."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S ET")
    print(color("=" * 70, "cyan"))
    print(color(f"  PROJECT ATHENA - MONITORING DASHBOARD  |  {now}", "bold"))
    print(color("=" * 70, "cyan"))
    print()


def print_portfolio_section(state: dict):
    """Print portfolio status section."""
    print(color("PORTFOLIO STATUS", "bold"))
    print("-" * 40)

    portfolio = state.get("portfolio", {})
    if not portfolio:
        print("  No portfolio data available")
        return

    equity = portfolio.get("equity", 0)
    day_pnl = portfolio.get("day_pnl", 0)
    day_pnl_pct = portfolio.get("day_pnl_pct", 0)

    print(f"  Equity:     ${equity:,.0f}")
    print(f"  Day P&L:    {pnl_color(day_pnl)} ({pct_color(day_pnl_pct)})")
    print(f"  Cash:       ${portfolio.get('cash', 0):,.0f}")
    print(f"  Buying Pwr: ${portfolio.get('buying_power', 0):,.0f}")
    print()


def print_positions_section(state: dict):
    """Print positions section."""
    print(color("POSITIONS", "bold"))
    print("-" * 40)

    positions = state.get("positions", [])
    if not positions:
        print("  No positions")
        return

    # Sort by market value
    sorted_pos = sorted(positions, key=lambda x: x.get("market_value", 0), reverse=True)

    for pos in sorted_pos[:8]:  # Top 8
        symbol = pos.get("symbol", "???")
        mv = pos.get("market_value", 0)
        pnl_pct = pos.get("unrealized_pnl_pct", 0)
        day_pnl = pos.get("day_pnl", 0)

        pnl_str = pct_color(pnl_pct)
        day_str = pnl_color(day_pnl)

        print(f"  {symbol:6s}  ${mv:>8,.0f}  {pnl_str:>10s}  Day: {day_str}")

    if len(positions) > 8:
        print(f"  ... and {len(positions) - 8} more positions")
    print()


def print_thesis_section(state: dict):
    """Print thesis performance section."""
    print(color("THESIS PERFORMANCE", "bold"))
    print("-" * 40)

    thesis_perf = state.get("thesis_performance", {})
    if not thesis_perf:
        print("  No thesis data available")
        return

    for thesis_id, perf in thesis_perf.items():
        name = perf.get("thesis_name", thesis_id)
        value = perf.get("total_value", 0)
        pnl = perf.get("total_pnl", 0)
        pnl_pct = perf.get("total_pnl_pct", 0)
        weight = perf.get("weight_in_portfolio_pct", 0)

        pnl_str = pnl_color(pnl)

        print(f"  {name[:20]:20s}  ${value:>8,.0f}  {pnl_str:>10s} ({pnl_pct:+.1f}%)")
        print(f"    Weight: {weight:.1f}% | Positions: {perf.get('position_count', 0)}")

    print()


def print_drawdown_section(drawdown: dict):
    """Print drawdown monitoring section."""
    print(color("DRAWDOWN MONITOR", "bold"))
    print("-" * 40)

    if not drawdown:
        print("  No drawdown data available")
        return

    portfolio_dd = drawdown.get("PORTFOLIO", {})
    if portfolio_dd:
        current_dd = portfolio_dd.get("current_drawdown_pct", 0)
        max_dd = portfolio_dd.get("max_drawdown_pct", 0)
        intraday_dd = portfolio_dd.get("intraday_drawdown_pct", 0)
        alert_level = portfolio_dd.get("alert_level", "none")

        if alert_level == "critical":
            dd_color = "red"
        elif alert_level == "warning":
            dd_color = "yellow"
        else:
            dd_color = "white"

        print(f"  Portfolio DD: {color(f'{current_dd:.1f}%', dd_color)}")
        print(f"  Max DD:       {max_dd:.1f}%")
        print(f"  Intraday DD:  {intraday_dd:.1f}%")

        if alert_level != "none":
            print(f"  {color(f'⚠ ALERT: {alert_level.upper()}', dd_color)}")

    print()


def print_signal_health_section(health: dict):
    """Print signal health section."""
    print(color("SIGNAL HEALTH", "bold"))
    print("-" * 40)

    if not health:
        print("  No signal health data available")
        return

    total = health.get("total_signals", 0)
    healthy = health.get("healthy_signals", 0)
    degrading = health.get("degrading_signals", 0)
    broken = health.get("broken_signals", 0)

    print(f"  Total:     {total}")
    print(f"  Healthy:   {color(str(healthy), 'green')}")
    print(f"  Degrading: {color(str(degrading), 'yellow') if degrading else str(degrading)}")
    print(f"  Broken:    {color(str(broken), 'red') if broken else str(broken)}")

    if health.get("best_performers"):
        print(f"  Best:      {', '.join(health['best_performers'][:3])}")

    print()


def print_execution_section(execution: dict):
    """Print execution quality section."""
    print(color("EXECUTION QUALITY", "bold"))
    print("-" * 40)

    if not execution:
        print("  No execution data available")
        return

    trades = execution.get("total_trades", 0)
    avg_slip = execution.get("avg_slippage_bps", 0)
    cost = execution.get("total_slippage_cost", 0)

    good_pct = execution.get("good_fills_pct", 0)
    poor_pct = execution.get("poor_fills_pct", 0)

    slip_color = "green" if avg_slip < 10 else "yellow" if avg_slip < 20 else "red"

    print(f"  Trades:        {trades}")
    print(f"  Avg Slippage:  {color(f'{avg_slip:.1f} bps', slip_color)}")
    print(f"  Slippage Cost: ${cost:.2f}")
    print(f"  Fill Quality:  Good: {good_pct:.0f}% | Poor: {poor_pct:.0f}%")

    print()


def print_alerts_section(state: dict):
    """Print alerts section."""
    print(color("ALERTS & WARNINGS", "bold"))
    print("-" * 40)

    alerts = state.get("alerts", [])
    concentration = state.get("concentration", {})

    if not alerts and not concentration:
        print(f"  {color('✓ No active alerts', 'green')}")
        return

    # Concentration warnings
    if concentration:
        for breach in concentration.get("limit_breaches", []):
            print(f"  {color('🚨 BREACH:', 'red')} {breach}")

        for warning in concentration.get("warnings", []):
            print(f"  {color('⚠ WARNING:', 'yellow')} {warning}")

    # System alerts
    for alert in alerts[:5]:
        priority = alert.get("priority", "low")
        if priority == "high":
            print(f"  {color('⚠', 'red')} [{alert.get('alert_type')}] {alert.get('message')}")
        else:
            print(f"  [{alert.get('alert_type')}] {alert.get('message')}")

    print()


def print_market_section(state: dict):
    """Print market conditions section."""
    print(color("MARKET CONDITIONS", "bold"))
    print("-" * 40)

    market = state.get("market", {})
    sentiment = state.get("sentiment", {})

    if not market:
        print("  No market data available")
        return

    spy_change = market.get("spy_change_pct", 0)
    qqq_change = market.get("qqq_change_pct", 0)
    vix = market.get("vix", 0)
    regime = market.get("regime", "unknown")

    print(f"  SPY: {pct_color(spy_change)} | QQQ: {pct_color(qqq_change)}")
    print(f"  VIX: {vix:.1f} | Regime: {regime}")

    if sentiment:
        fg = sentiment.get("fear_greed_label", "neutral")
        overall = sentiment.get("overall_sentiment", "neutral")
        print(f"  Fear/Greed: {fg} | Sentiment: {overall}")

    print()


def render_dashboard():
    """Render the full dashboard."""
    clear_screen()
    print_header()

    # Load all data
    state = load_unified_state()
    signal_health = load_signal_health()
    execution = load_execution_quality()
    drawdown = load_drawdown_state()

    # Two-column layout simulation
    print_portfolio_section(state)
    print_market_section(state)
    print_positions_section(state)
    print_thesis_section(state)
    print_drawdown_section(drawdown)
    print_signal_health_section(signal_health)
    print_execution_section(execution)
    print_alerts_section(state)

    # Footer
    last_update = state.get("timestamp", "Unknown")
    print(color("-" * 70, "cyan"))
    print(f"  Last State Update: {last_update}")
    print(f"  Press Ctrl+C to exit")


async def run_dashboard(refresh_seconds: int = 0):
    """Run the dashboard with optional auto-refresh.

    Args:
        refresh_seconds: Refresh interval (0 = no refresh)
    """
    if refresh_seconds == 0:
        # Single render
        render_dashboard()
    else:
        # Auto-refresh loop
        try:
            while True:
                render_dashboard()
                await asyncio.sleep(refresh_seconds)
        except KeyboardInterrupt:
            print("\nDashboard exited.")


def main():
    parser = argparse.ArgumentParser(description="Unified Monitoring Dashboard")
    parser.add_argument(
        "--refresh", type=int, default=0,
        help="Refresh interval in seconds (0 = no refresh)"
    )
    args = parser.parse_args()

    asyncio.run(run_dashboard(args.refresh))


if __name__ == "__main__":
    main()
