#!/bin/bash
# Market Watch Daemon - Runs for specified hours with interval checks
# Usage: ./scripts/market_watch_daemon.sh [hours] [interval_minutes]

HOURS=${1:-7}
INTERVAL_MIN=${2:-10}
TOTAL_CYCLES=$((HOURS * 60 / INTERVAL_MIN))
INTERVAL_SEC=$((INTERVAL_MIN * 60))

QUANT_RESULTS_DIR="${QUANT_RESULTS_DIR:-$HOME/quant_results}"
LOG_DIR="$QUANT_RESULTS_DIR/logs"
LOG_FILE="$LOG_DIR/market_watch_$(date +%Y%m%d).log"
JSONL_FILE="$LOG_DIR/market_watch_$(date +%Y%m%d).jsonl"
ALERT_FILE="$LOG_DIR/market_watch_alerts.txt"

mkdir -p "$LOG_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

echo "========================================" >> "$LOG_FILE"
echo "MARKET WATCH DAEMON STARTED" >> "$LOG_FILE"
echo "$(date): Running for $HOURS hours, $TOTAL_CYCLES cycles" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

for ((cycle=1; cycle<=TOTAL_CYCLES; cycle++)); do
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    # Run monitoring check
    RESULT=$(QUANT_RESULTS_DIR="$QUANT_RESULTS_DIR" PYTHONPATH=. python3 << 'PYEOF'
import json
import os
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))
state_file = RESULTS_DIR / "live" / "state.json"

with open(state_file) as f:
    state = json.load(f)

portfolio = state.get("portfolio", {})
positions = state.get("positions", [])

# Calculate metrics
equity = portfolio.get("equity", 0)
day_pnl = portfolio.get("day_pnl", 0)
day_pnl_pct = portfolio.get("day_pnl_pct", 0)

# Energy concentration
energy_symbols = {"SLB", "HAL", "XLE", "XOP", "OIH", "ERX", "GUSH", "IEO", "BKR", "FRO", "STNG", "INSW", "DHT", "MPC", "PSX", "PBF", "CNQ", "SU", "IMO", "PBR", "WFRD"}
total_value = sum(p.get("market_value", 0) for p in positions)
energy_value = sum(p.get("market_value", 0) for p in positions if p.get("symbol") in energy_symbols)
energy_pct = (energy_value / total_value * 100) if total_value else 0

# Check alerts
alerts = []
recommendations = []

for p in positions:
    symbol = p.get("symbol")
    pnl_pct = p.get("unrealized_pnl_pct", 0)
    value = p.get("market_value", 0)

    if pnl_pct <= -12:
        alerts.append(f"CRITICAL|{symbol}|{pnl_pct:.1f}%|STOP LOSS BREACHED")
    elif pnl_pct <= -10:
        alerts.append(f"WARNING|{symbol}|{pnl_pct:.1f}%|Approaching stop loss")

    if pnl_pct >= 35:
        recommendations.append(f"TRIM|{symbol}|{pnl_pct:.1f}%|Above profit target")

if energy_pct >= 50:
    alerts.append(f"WARNING|ENERGY|{energy_pct:.1f}%|At concentration limit")

# Output JSON
output = {
    "timestamp": datetime.now().isoformat(),
    "equity": equity,
    "day_pnl": day_pnl,
    "day_pnl_pct": day_pnl_pct,
    "energy_pct": energy_pct,
    "alerts": alerts,
    "recommendations": recommendations
}
print(json.dumps(output))
PYEOF
)

    # Parse result
    EQUITY=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"equity\"]:,.0f}')")
    DAY_PNL=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"day_pnl\"]:+,.0f}')")
    DAY_PNL_PCT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"day_pnl_pct\"]:+.2f}')")
    ALERTS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['alerts']))")

    # Log cycle
    echo "[$TIMESTAMP] Cycle $cycle/$TOTAL_CYCLES | Equity: \$$EQUITY | Day: \$$DAY_PNL ($DAY_PNL_PCT%) | Alerts: $ALERTS" >> "$LOG_FILE"
    echo "$RESULT" >> "$JSONL_FILE"

    # Check for critical alerts
    CRITICAL=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print([a for a in d['alerts'] if 'CRITICAL' in a])")
    if [[ "$CRITICAL" != "[]" ]]; then
        echo "[$TIMESTAMP] $CRITICAL" >> "$ALERT_FILE"
        echo "CRITICAL ALERT at $TIMESTAMP: $CRITICAL" >> "$LOG_FILE"
    fi

    # Sleep unless last cycle
    if [[ $cycle -lt $TOTAL_CYCLES ]]; then
        sleep $INTERVAL_SEC
    fi
done

echo "========================================" >> "$LOG_FILE"
echo "MARKET WATCH DAEMON COMPLETED" >> "$LOG_FILE"
echo "$(date): Completed $TOTAL_CYCLES cycles" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
