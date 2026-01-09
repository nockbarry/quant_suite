#!/bin/bash
# Live Daemon - Updates state.json every 5 minutes during market hours
# Usage: ./live_daemon.sh start|stop|status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
PID_FILE="/tmp/quant_live_daemon.pid"
LOG_FILE="$HOME/quant_results/logs/live_daemon.log"

mkdir -p "$(dirname "$LOG_FILE")"

start_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Daemon already running (PID: $(cat "$PID_FILE"))"
        return 1
    fi

    echo "Starting live daemon..."
    cd "$PROJECT_ROOT"

    nohup python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from src.synthesis.daemon import LiveDaemon

async def run():
    daemon = LiveDaemon()
    await daemon.start(interval_minutes=5)
    while True:
        await asyncio.sleep(60)

asyncio.run(run())
" >> "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    echo "Daemon started (PID: $!)"
}

stop_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping daemon (PID: $PID)..."
            kill "$PID"
            rm "$PID_FILE"
            echo "Daemon stopped"
        else
            echo "Daemon not running, cleaning up PID file"
            rm "$PID_FILE"
        fi
    else
        echo "No PID file found"
    fi
}

status_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Daemon running (PID: $(cat "$PID_FILE"))"
        echo "Last state update:"
        ls -la ~/quant_results/live/state.json 2>/dev/null || echo "  No state file"
    else
        echo "Daemon not running"
    fi
}

case "$1" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    status)
        status_daemon
        ;;
    restart)
        stop_daemon
        sleep 2
        start_daemon
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
