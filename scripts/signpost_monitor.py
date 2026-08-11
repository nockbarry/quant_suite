#!/usr/bin/env python3
"""Signpost Monitor - Real-time price level and signpost monitoring.

Runs during market hours to check price levels and trigger alerts.
Designed to be run via cron every 5-15 minutes.

Usage:
    PYTHONPATH=. python3 scripts/signpost_monitor.py           # Full check
    PYTHONPATH=. python3 scripts/signpost_monitor.py --alerts  # Only show triggered
    PYTHONPATH=. python3 scripts/signpost_monitor.py --edit    # Edit signposts

Created: 2026-01-20 for Greenland/Tariff/Fed crisis monitoring
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import subprocess
import sys

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))


@dataclass
class PriceLevel:
    """A price level to monitor."""
    symbol: str
    level: float
    direction: str  # "above" or "below"
    description: str
    action: str
    priority: str  # "critical", "high", "medium"
    thesis: str = ""


# Default signposts - will be loaded from file if exists
DEFAULT_SIGNPOSTS = [
    # VIX levels
    PriceLevel("^VIX", 22.0, "above", "VIX > 22: Risk-off confirmed", "Let gold/defense run", "high", "VIX Mean Reversion"),
    PriceLevel("^VIX", 25.0, "above", "VIX > 25: Fear spike", "Prepare mean reversion", "critical", "VIX Mean Reversion"),
    PriceLevel("^VIX", 30.0, "above", "VIX > 30: Panic", "ACTIVATE VIX MEAN REVERSION - add SPY/SVXY", "critical", "VIX Mean Reversion"),
    PriceLevel("^VIX", 18.0, "below", "VIX < 18: Risk-on", "Consider trimming hedges", "medium", "VIX Mean Reversion"),

    # Gold levels
    PriceLevel("GDX", 103.0, "above", "GDX breakout > $103", "Gold thesis confirmed", "high", "Gold De-Dollarization"),
    PriceLevel("GLD", 440.0, "above", "GLD new high > $440", "Consider partial profits", "high", "Gold De-Dollarization"),
    PriceLevel("GLD", 425.0, "below", "GLD breakdown < $425", "Review gold thesis", "medium", "Gold De-Dollarization"),

    # Positions needing attention
    PriceLevel("CEG", 251.0, "below", "CEG < $251: -15% stop hit", "EXIT CEG position — stop loss triggered", "critical", "AI Power Infrastructure"),
    PriceLevel("CCL", 27.0, "below", "CCL < $27: Cruise collapse", "Trim cruise positions", "high", ""),
    PriceLevel("LEN", 112.0, "below", "LEN < $112: Homebuilder weak", "Review homebuilder thesis", "medium", "Homebuilder Mortgage"),

    # Market levels
    PriceLevel("SPY", 685.0, "below", "SPY < $685: Support break", "Increase defensive exposure", "critical", ""),
    PriceLevel("SPY", 700.0, "above", "SPY > $700: Breakout", "Risk-on confirmed", "high", ""),

    # Venezuela thesis
    PriceLevel("SLB", 44.0, "below", "SLB < $44: Services weak", "Review Venezuela thesis", "high", "Venezuela Energy"),
    PriceLevel("FRO", 28.0, "above", "FRO > $28: Tanker surge", "Tanker thesis working", "medium", "Venezuela Energy"),

    # Defense/Greenland
    PriceLevel("NOC", 680.0, "above", "NOC > $680: Defense surge", "Defense thesis confirmed", "medium", "Defense Spending"),
    PriceLevel("GD", 375.0, "above", "GD > $375: Defense surge", "Defense thesis confirmed", "medium", "Defense Spending"),
]


def get_signposts_file() -> Path:
    return _RESULTS_DIR / "config" / "signposts.json"


def load_signposts() -> list[PriceLevel]:
    """Load signposts from file or use defaults."""
    signposts_file = get_signposts_file()
    if signposts_file.exists():
        with open(signposts_file) as f:
            data = json.load(f)
        return [PriceLevel(**sp) for sp in data]
    return DEFAULT_SIGNPOSTS


def save_signposts(signposts: list[PriceLevel]):
    """Save signposts to file."""
    signposts_file = get_signposts_file()
    signposts_file.parent.mkdir(parents=True, exist_ok=True)
    with open(signposts_file, "w") as f:
        json.dump([asdict(sp) for sp in signposts], f, indent=2)
    print(f"Saved {len(signposts)} signposts to {signposts_file}")


def get_current_price(symbol: str) -> Optional[float]:
    """Get current price for a symbol using yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            return float(data["Close"].iloc[-1])
        # Fallback to regular price
        info = ticker.info
        return info.get("regularMarketPrice") or info.get("previousClose")
    except Exception as e:
        return None


def check_signposts(signposts: list[PriceLevel], alerts_only: bool = False) -> list[dict]:
    """Check all signposts and return triggered ones."""
    triggered = []
    price_cache = {}

    if not alerts_only:
        print(f"\nChecking {len(signposts)} signposts at {datetime.now().strftime('%H:%M:%S')}...")
        print("-" * 70)

    for sp in signposts:
        if sp.symbol not in price_cache:
            price_cache[sp.symbol] = get_current_price(sp.symbol)

        price = price_cache[sp.symbol]
        if price is None:
            if not alerts_only:
                print(f"  ⚠️  {sp.symbol}: Could not get price")
            continue

        # Check if triggered
        is_triggered = False
        if sp.direction == "above" and price > sp.level:
            is_triggered = True
        elif sp.direction == "below" and price < sp.level:
            is_triggered = True

        if is_triggered:
            triggered.append({
                "symbol": sp.symbol,
                "price": price,
                "level": sp.level,
                "direction": sp.direction,
                "description": sp.description,
                "action": sp.action,
                "priority": sp.priority,
                "thesis": sp.thesis,
                "timestamp": datetime.now().isoformat(),
            })

            priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(sp.priority, "⚪")
            print(f"\n{priority_icon} TRIGGERED [{sp.priority.upper()}]")
            print(f"   {sp.description}")
            print(f"   Price: ${price:.2f} (level: ${sp.level:.2f})")
            print(f"   ACTION: {sp.action}")
            if sp.thesis:
                print(f"   Thesis: {sp.thesis}")

        elif not alerts_only:
            dist = abs(price - sp.level) / sp.level * 100
            status = "↑" if sp.direction == "above" else "↓"
            print(f"  ⚪ {sp.symbol:6s} ${price:7.2f} {status} ${sp.level:.2f} ({dist:4.1f}% away)")

    return triggered


def save_alerts(triggered: list[dict]):
    """Save triggered alerts to file."""
    alerts_dir = _RESULTS_DIR / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)

    alerts_file = alerts_dir / f"alerts_{datetime.now().strftime('%Y%m%d')}.json"

    existing = []
    if alerts_file.exists():
        try:
            with open(alerts_file) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, ValueError):
            existing = []

    # Add new alerts (avoid duplicates)
    for alert in triggered:
        is_duplicate = any(
            ex["symbol"] == alert["symbol"] and ex["description"] == alert["description"]
            for ex in existing[-20:]
        )
        if not is_duplicate:
            existing.append(alert)

    with open(alerts_file, "w") as f:
        json.dump(existing, f, indent=2)

    return alerts_file


def get_market_snapshot() -> dict:
    """Get quick market snapshot."""
    symbols = ["SPY", "QQQ", "^VIX", "GLD", "TLT"]
    snapshot = {}

    for sym in symbols:
        price = get_current_price(sym)
        if price:
            snapshot[sym] = price

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Monitor price signposts")
    parser.add_argument("--alerts", action="store_true", help="Only show triggered alerts")
    parser.add_argument("--snapshot", action="store_true", help="Quick market snapshot")
    parser.add_argument("--save-defaults", action="store_true", help="Save default signposts to file")
    parser.add_argument("--list", action="store_true", help="List all signposts")
    args = parser.parse_args()

    print("=" * 70)
    print(f" SIGNPOST MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 70)

    if args.snapshot:
        print("\nMARKET SNAPSHOT:")
        for sym, price in get_market_snapshot().items():
            print(f"  {sym}: ${price:.2f}")
        return

    if args.save_defaults:
        save_signposts(DEFAULT_SIGNPOSTS)
        return

    signposts = load_signposts()

    if args.list:
        print(f"\n{len(signposts)} active signposts:")
        for sp in signposts:
            direction = ">" if sp.direction == "above" else "<"
            print(f"  [{sp.priority:8s}] {sp.symbol:6s} {direction} ${sp.level:.2f} - {sp.description}")
        return

    triggered = check_signposts(signposts, args.alerts)

    if triggered:
        print("\n" + "=" * 70)
        print(f" {len(triggered)} ALERTS TRIGGERED")
        print("=" * 70)
        alerts_file = save_alerts(triggered)
        print(f"\nAlerts saved to: {alerts_file}")

        # Send notification (desktop)
        try:
            for alert in triggered:
                if alert["priority"] == "critical":
                    subprocess.run([
                        "notify-send",
                        f"🔴 {alert['symbol']} Alert",
                        alert['action'],
                    ], capture_output=True)
        except:
            pass

    else:
        if not args.alerts:
            print("\n✓ No signposts triggered")

    print("")


if __name__ == "__main__":
    main()
