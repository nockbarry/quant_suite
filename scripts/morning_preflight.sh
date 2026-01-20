#!/bin/bash
# Morning Preflight - One command to set up for trading day
#
# Usage: ./scripts/morning_preflight.sh [--quick|--full]
#
# This script:
# 1. Updates unified state
# 2. Runs alternative signal scan
# 3. Checks calendar
# 4. Dumps full context for Claude
#
# Run this INSTEAD of writing custom Python code in Claude sessions.

set -e
cd "$(dirname "$0")/.."

MODE="${1:---full}"

echo "========================================"
echo " MORNING PREFLIGHT - $(date '+%Y-%m-%d %H:%M ET')"
echo "========================================"
echo ""

# Check if market day
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -gt 5 ]; then
    echo "⚠️  Weekend - markets closed"
fi

# Step 1: Update unified state
echo "→ Updating unified state..."
PYTHONPATH=. python3 -c "
import asyncio
from src.synthesis.daemon import LiveDaemon

async def update():
    daemon = LiveDaemon()
    state = await daemon.update_now()
    print(f'  ✓ State updated: {len(state.positions)} positions, \${state.portfolio.equity:,.0f} equity')

asyncio.run(update())
" 2>&1 | grep -v "^WARNING\|^FRED API"

# Step 2: Generate alternative signals (skip if quick mode)
if [ "$MODE" != "--quick" ]; then
    echo ""
    echo "→ Generating alternative signals..."
    PYTHONPATH=. python3 -m src.synthesis.alternative_signals --all 2>&1 | tail -5
fi

# Step 3: Check calendar
echo ""
echo "→ Calendar check..."
PYTHONPATH=. python3 -c "
from src.knowledge.market_calendar import MarketCalendar
from datetime import date, timedelta

calendar = MarketCalendar()
today = date.today()

# Today
events = calendar.get_events_in_range(today, today + timedelta(days=1))
if events:
    for e in events:
        impact = e.impact.value if hasattr(e.impact, 'value') else str(e.impact)
        print(f'  TODAY [{impact.upper()}]: {e.title}')
else:
    print('  No events today')

# Tomorrow
events = calendar.get_events_in_range(today + timedelta(days=1), today + timedelta(days=2))
if events:
    for e in events[:2]:
        impact = e.impact.value if hasattr(e.impact, 'value') else str(e.impact)
        print(f'  TOMORROW [{impact.upper()}]: {e.title}')
"

# Step 4: Quick portfolio summary
echo ""
echo "→ Portfolio summary..."
PYTHONPATH=. python3 -c "
import json
from pathlib import Path

state_file = Path.home() / 'quant_results' / 'live' / 'state.json'
with open(state_file) as f:
    state = json.load(f)

port = state['portfolio']
positions = state['positions']
winners = len([p for p in positions if p.get('unrealized_pnl', 0) > 0])
losers = len(positions) - winners

print(f'  Equity: \${port[\"equity\"]:,.0f}')
print(f'  Day P&L: \${port.get(\"day_pnl\", 0):+,.0f}')
print(f'  Positions: {len(positions)} ({winners} winners, {losers} losers)')

# Top loser
if positions:
    worst = min(positions, key=lambda x: x.get('unrealized_pnl', 0))
    if worst.get('unrealized_pnl', 0) < -50:
        print(f'  ⚠️  Worst: {worst[\"symbol\"]} \${worst[\"unrealized_pnl\"]:+,.0f}')
"

# Step 5: Theses due for review
echo ""
echo "→ Theses status..."
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
theses = tracker.get_active_theses()

review_due = [t for t in theses if t.check_review_due()]
if review_due:
    print(f'  ⚠️  {len(review_due)} theses due for review:')
    for t in review_due[:3]:
        print(f'      - {t.name} ({t.conviction}%)')
else:
    print(f'  ✓ {len(theses)} active theses, none due for review')
"

echo ""
echo "========================================"
echo " PREFLIGHT COMPLETE"
echo "========================================"
echo ""
echo "Next: Run 'PYTHONPATH=. python scripts/context_dump.py' for full context"
echo "      Or start Claude session with '/morning-briefing'"
echo ""
