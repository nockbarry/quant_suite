#!/bin/bash
# Start Market Watcher Daemon
# Usage: ./scripts/start_market_watcher.sh [interval_seconds] [duration_minutes]
#
# Examples:
#   ./scripts/start_market_watcher.sh            # 5-min checks for 1 hour
#   ./scripts/start_market_watcher.sh 120 480    # 2-min checks for 8 hours (full market day)

cd "$(dirname "$0")/.."
INTERVAL=${1:-300}
DURATION=${2:-60}

echo "Starting market watcher daemon..."
echo "  Interval: ${INTERVAL}s"
echo "  Duration: ${DURATION}m"
echo "  Log: ~/quant_results/logs/market_watch.log"
echo "  Dashboard: Agent activity will appear in unified dashboard"
echo ""

# Run in background
nohup python3 scripts/daemons/market_watcher.py "$INTERVAL" "$DURATION" > /tmp/market_watcher.out 2>&1 &
WATCHER_PID=$!

echo "Market watcher started with PID: $WATCHER_PID"
echo "To monitor: tail -f ~/quant_results/logs/market_watch.log"
echo "To stop: kill $WATCHER_PID"
echo ""
echo "PID saved to: /tmp/market_watcher.pid"
echo "$WATCHER_PID" > /tmp/market_watcher.pid
