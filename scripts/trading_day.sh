#!/bin/bash
# Trading Day Automation Script
# Manages all background processes and scheduled tasks for a trading day
#
# Usage:
#   ./trading_day.sh start     # Start all daemons, run pre-market prep
#   ./trading_day.sh stop      # Stop all daemons
#   ./trading_day.sh status    # Check status of all components
#   ./trading_day.sh premarket # Just run pre-market prep
#   ./trading_day.sh ready     # Check if system is ready for trading

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$HOME/quant_results"
LOG_DIR="$RESULTS_DIR/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

mkdir -p "$LOG_DIR"

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $1"
}

# Check if market is open (simple check)
is_market_hours() {
    local hour=$(date +%H)
    local dow=$(date +%u)

    # Weekend
    if [ "$dow" -ge 6 ]; then
        return 1
    fi

    # Pre-market: 6 AM - 9:30 AM
    # Market: 9:30 AM - 4 PM
    # After hours: 4 PM - 8 PM
    if [ "$hour" -ge 6 ] && [ "$hour" -lt 20 ]; then
        return 0
    fi

    return 1
}

run_premarket() {
    log "Running pre-market research preparation..."
    cd "$PROJECT_ROOT"

    PYTHONPATH="$PROJECT_ROOT" python scripts/research_prep.py >> "$LOG_DIR/premarket_$(date +%Y%m%d).log" 2>&1

    if [ $? -eq 0 ]; then
        log "Pre-market prep complete"
    else
        error "Pre-market prep failed - check logs"
    fi
}

update_state_now() {
    log "Updating unified state..."
    cd "$PROJECT_ROOT"

    PYTHONPATH="$PROJECT_ROOT" python -c "
import asyncio
from src.synthesis.daemon import LiveDaemon

async def update():
    daemon = LiveDaemon()
    state = await daemon.update_now()
    print(state.get_summary())

asyncio.run(update())
" 2>&1
}

start_daemons() {
    log "Starting trading day infrastructure..."

    # Start live daemon
    "$SCRIPT_DIR/daemons/live_daemon.sh" start

    # Run initial state update
    update_state_now

    log "Infrastructure started"
}

stop_daemons() {
    log "Stopping trading day infrastructure..."

    "$SCRIPT_DIR/daemons/live_daemon.sh" stop

    log "Infrastructure stopped"
}

check_status() {
    echo "=== TRADING DAY STATUS ==="
    echo ""

    # Check daemons
    echo "Daemons:"
    "$SCRIPT_DIR/daemons/live_daemon.sh" status
    echo ""

    # Check state file freshness
    echo "State File:"
    if [ -f "$RESULTS_DIR/live/state.json" ]; then
        local age_mins=$(( ($(date +%s) - $(stat -c %Y "$RESULTS_DIR/live/state.json")) / 60 ))
        if [ "$age_mins" -lt 10 ]; then
            echo -e "  ${GREEN}Fresh${NC} (updated ${age_mins}m ago)"
        elif [ "$age_mins" -lt 60 ]; then
            echo -e "  ${YELLOW}Stale${NC} (updated ${age_mins}m ago)"
        else
            echo -e "  ${RED}Old${NC} (updated ${age_mins}m ago)"
        fi
    else
        echo -e "  ${RED}Missing${NC}"
    fi
    echo ""

    # Check research files
    echo "Research Files:"
    for f in features.json signals.json alt_data.json screens.json; do
        if [ -f "$RESULTS_DIR/live/research/$f" ]; then
            echo -e "  $f: ${GREEN}OK${NC}"
        else
            echo -e "  $f: ${RED}Missing${NC}"
        fi
    done
    echo ""

    # Market hours
    echo "Market Status:"
    if is_market_hours; then
        echo -e "  ${GREEN}Market hours${NC}"
    else
        echo -e "  ${YELLOW}Outside market hours${NC}"
    fi
}

check_ready() {
    local ready=true

    echo "=== READINESS CHECK ==="
    echo ""

    # State file exists and fresh
    if [ -f "$RESULTS_DIR/live/state.json" ]; then
        local age_mins=$(( ($(date +%s) - $(stat -c %Y "$RESULTS_DIR/live/state.json")) / 60 ))
        if [ "$age_mins" -lt 30 ]; then
            echo -e "[${GREEN}OK${NC}] State file fresh (${age_mins}m)"
        else
            echo -e "[${YELLOW}WARN${NC}] State file stale (${age_mins}m)"
        fi
    else
        echo -e "[${RED}FAIL${NC}] No state file"
        ready=false
    fi

    # Daemon running
    if [ -f "/tmp/quant_live_daemon.pid" ] && kill -0 "$(cat /tmp/quant_live_daemon.pid)" 2>/dev/null; then
        echo -e "[${GREEN}OK${NC}] Live daemon running"
    else
        echo -e "[${YELLOW}WARN${NC}] Live daemon not running"
    fi

    # Research files
    local research_ok=true
    for f in features.json signals.json; do
        if [ ! -f "$RESULTS_DIR/live/research/$f" ]; then
            research_ok=false
        fi
    done
    if $research_ok; then
        echo -e "[${GREEN}OK${NC}] Research files present"
    else
        echo -e "[${YELLOW}WARN${NC}] Some research files missing"
    fi

    echo ""
    if $ready; then
        echo -e "${GREEN}System ready for trading${NC}"
        echo ""
        echo "Start Claude with:"
        echo "  claude '/morning-briefing'   # Full briefing"
        echo "  claude '/trade-decision'     # Make decisions"
        echo "  claude 'ready'               # Quick status"
    else
        echo -e "${RED}System not ready${NC}"
        echo "Run: ./trading_day.sh start"
    fi
}

case "$1" in
    start)
        start_daemons
        if is_market_hours; then
            run_premarket
        else
            warn "Outside market hours - skipping pre-market prep"
        fi
        check_ready
        ;;
    stop)
        stop_daemons
        ;;
    status)
        check_status
        ;;
    premarket)
        run_premarket
        ;;
    ready)
        check_ready
        ;;
    update)
        update_state_now
        ;;
    *)
        echo "Trading Day Automation"
        echo ""
        echo "Usage: $0 {start|stop|status|premarket|ready|update}"
        echo ""
        echo "Commands:"
        echo "  start     - Start daemons and run pre-market prep"
        echo "  stop      - Stop all daemons"
        echo "  status    - Show status of all components"
        echo "  premarket - Run pre-market research prep"
        echo "  ready     - Check if system ready for trading"
        echo "  update    - Force state.json update now"
        exit 1
        ;;
esac
