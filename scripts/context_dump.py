#!/usr/bin/env python3
"""Context Dump - One command to get all context for Claude sessions.

This script outputs everything Claude needs for morning briefings or research,
in a format optimized for LLM consumption. No improvised code needed.

Usage:
    PYTHONPATH=. python scripts/context_dump.py              # Full context
    PYTHONPATH=. python scripts/context_dump.py --brief      # Quick summary
    PYTHONPATH=. python scripts/context_dump.py --research   # Research-focused
"""

import argparse
import asyncio
import json
from datetime import datetime, date, timedelta
from pathlib import Path


def print_section(title: str, content: str = ""):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f" {title}")
    print('='*70)
    if content:
        print(content)


def get_state_summary() -> str:
    """Load and return unified state summary."""
    from src.synthesis.state import UnifiedState
    from src.core.paths import paths

    state = UnifiedState.load(paths.live_state)
    if not state:
        return "ERROR: No unified state found. Run: LiveDaemon().update_now()"

    age_seconds = (datetime.now() - state.timestamp).total_seconds()
    freshness = "FRESH" if age_seconds < 1800 else f"STALE ({age_seconds/60:.0f} min old)"

    return f"[{freshness}]\n\n{state.get_summary()}"


def get_calendar_summary() -> str:
    """Get upcoming calendar events."""
    from src.knowledge.market_calendar import MarketCalendar

    calendar = MarketCalendar()
    today = date.today()

    lines = []

    # Today's events
    today_events = calendar.get_events_in_range(today, today + timedelta(days=1))
    if today_events:
        lines.append("TODAY:")
        for e in today_events:
            impact = e.impact.value if hasattr(e.impact, 'value') else str(e.impact)
            lines.append(f"  [{impact.upper()}] {e.title}")
            if e.symbols_affected:
                lines.append(f"           Symbols: {', '.join(e.symbols_affected[:5])}")
    else:
        lines.append("TODAY: No scheduled events")

    # Week ahead
    week_events = calendar.get_events_in_range(today + timedelta(days=1), today + timedelta(days=7))
    if week_events:
        lines.append("\nTHIS WEEK:")
        for e in week_events[:5]:
            impact = e.impact.value if hasattr(e.impact, 'value') else str(e.impact)
            lines.append(f"  {e.date} [{impact.upper()}] {e.title}")

    # Predictions due
    due = calendar.get_predictions_due_for_review()
    if due:
        lines.append("\nPREDICTIONS DUE FOR REVIEW:")
        for p in due[:3]:
            lines.append(f"  {p.title} ({p.source})")

    return "\n".join(lines)


def get_thesis_summary() -> str:
    """Get active theses summary."""
    from src.knowledge.thesis import ThesisTracker
    from src.core.paths import paths

    tracker = ThesisTracker(paths.theses)
    theses = tracker.get_active_theses()

    lines = []
    for t in sorted(theses, key=lambda x: x.conviction, reverse=True):
        status = "⚠️ REVIEW DUE" if t.check_review_due() else ""
        lines.append(f"\n{t.name} ({t.conviction}% conviction) {status}")
        lines.append(f"  Positions: {', '.join(t.positions[:6])}")

        pending = t.get_pending_signposts()
        if pending:
            lines.append(f"  Next signpost: {pending[0].description}")

    return "\n".join(lines) if lines else "No active theses"


def get_alternative_signals() -> str:
    """Get alternative signals from state."""
    from src.core.paths import paths

    state_file = paths.live_state
    if not state_file.exists():
        return "No state file"

    with open(state_file) as f:
        state = json.load(f)

    alt = state.get("alternative_signals", {})
    if not alt:
        return "No alternative signals in state"

    lines = []

    # Weather
    weather = alt.get("weather_signals", [])
    if weather:
        lines.append("WEATHER:")
        for w in weather[:2]:
            lines.append(f"  {w.get('signal_type')}: {w.get('description', '')[:60]}...")
            if w.get('affected_symbols'):
                lines.append(f"    → {', '.join(w['affected_symbols'][:4])}")

    # FDA
    fda = alt.get("fda_signals", [])
    if fda:
        lines.append("\nFDA CALENDAR:")
        seen = set()
        for f in fda[:3]:
            key = f"{f.get('symbol')}:{f.get('drug_name')}"
            if key not in seen:
                seen.add(key)
                lines.append(f"  {f.get('symbol')}: {f.get('drug_name')} in {f.get('days_until', '?')} days")

    # Squeeze
    squeeze = alt.get("squeeze_candidates", [])
    if squeeze:
        lines.append("\nSQUEEZE WATCH:")
        for s in squeeze[:3]:
            lines.append(f"  {s.get('symbol')}: {s.get('short_percent_of_float', 0)*100:.0f}% short, score {s.get('squeeze_score', 0):.2f}")

    # Sector rotation
    sector = alt.get("sector_rotation", {})
    if sector:
        leading = sector.get("leading_sectors", [])[:3]
        lagging = sector.get("lagging_sectors", [])[:3]
        if leading or lagging:
            lines.append(f"\nSECTOR ROTATION: {sector.get('rotation_type', 'unknown')}")
            if leading:
                lines.append(f"  Leading: {', '.join(leading)}")
            if lagging:
                lines.append(f"  Lagging: {', '.join(lagging)}")

    return "\n".join(lines) if lines else "No significant signals"


def get_positions_summary() -> str:
    """Get positions needing attention."""
    from src.core.paths import paths

    state_file = paths.live_state
    if not state_file.exists():
        return "No state file"

    with open(state_file) as f:
        state = json.load(f)

    positions = state.get("positions", [])
    if not positions:
        return "No positions"

    lines = []

    # Top winners
    sorted_pos = sorted(positions, key=lambda x: x.get("unrealized_pnl", 0), reverse=True)
    lines.append("TOP WINNERS (by $ P&L):")
    for p in sorted_pos[:5]:
        pnl = p.get("unrealized_pnl", 0)
        pct = p.get("unrealized_pnl_pct", 0) * 100
        lines.append(f"  {p['symbol']:8s} ${pnl:+,.0f} ({pct:+.1f}%)")

    # Losers needing attention
    losers = [p for p in positions if p.get("unrealized_pnl", 0) < -50]
    if losers:
        lines.append("\nPOSITIONS DOWN >$50:")
        for p in sorted(losers, key=lambda x: x.get("unrealized_pnl", 0))[:5]:
            pnl = p.get("unrealized_pnl", 0)
            pct = p.get("unrealized_pnl_pct", 0) * 100
            lines.append(f"  {p['symbol']:8s} ${pnl:+,.0f} ({pct:+.1f}%)")

    return "\n".join(lines)


def get_api_reference() -> str:
    """Quick API reference for common operations."""
    return """
QUICK API REFERENCE
-------------------

# Load state (always do this first)
from src.synthesis.state import UnifiedState
from src.core.paths import paths
state = UnifiedState.load(paths.live_state)
print(state.get_summary())

# Update state
from src.synthesis.daemon import LiveDaemon
state = await LiveDaemon().update_now()

# Calendar events
from src.knowledge.market_calendar import MarketCalendar
calendar = MarketCalendar()
events = calendar.get_events_in_range(start_date, end_date)
events = calendar.get_upcoming_events(days=7)

# Theses
from src.knowledge.thesis import ThesisTracker
tracker = ThesisTracker(paths.theses)
theses = tracker.get_active_theses()
pending_signposts = thesis.get_pending_signposts()
review_due = thesis.check_review_due()

# Quick trades (use CLI, don't write code)
PYTHONPATH=. python scripts/quick_trade.py buy MU 10
PYTHONPATH=. python scripts/quick_trade.py positions
"""


async def update_state_if_stale() -> bool:
    """Update state if it's stale (>30 min old)."""
    from src.synthesis.state import UnifiedState
    from src.synthesis.daemon import LiveDaemon
    from src.core.paths import paths

    state = UnifiedState.load(paths.live_state)
    if state:
        age = (datetime.now() - state.timestamp).total_seconds()
        if age < 1800:  # 30 minutes
            return False  # Already fresh

    print("Updating state (stale or missing)...")
    daemon = LiveDaemon()
    await daemon.update_now()
    print("State updated.\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Dump context for Claude sessions")
    parser.add_argument("--brief", action="store_true", help="Quick summary only")
    parser.add_argument("--research", action="store_true", help="Research-focused context")
    parser.add_argument("--no-update", action="store_true", help="Don't update stale state")
    parser.add_argument("--api", action="store_true", help="Show API reference")
    args = parser.parse_args()

    if args.api:
        print(get_api_reference())
        return

    # Update state if stale
    if not args.no_update:
        asyncio.run(update_state_if_stale())

    # Header
    print(f"\n{'#'*70}")
    print(f"# CONTEXT DUMP - {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'#'*70}")

    # State summary (always)
    print_section("UNIFIED STATE", get_state_summary())

    if args.brief:
        return

    # Calendar
    print_section("CALENDAR", get_calendar_summary())

    # Theses
    print_section("ACTIVE THESES", get_thesis_summary())

    # Alternative signals
    print_section("ALTERNATIVE SIGNALS", get_alternative_signals())

    # Positions
    print_section("POSITIONS SUMMARY", get_positions_summary())

    if args.research:
        print_section("API REFERENCE", get_api_reference())

    print("\n" + "="*70)
    print(" END CONTEXT DUMP")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
