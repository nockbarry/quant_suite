#!/bin/bash
# Wrapper script for scheduled trade execution via cron
# Runs at market open (9:31 AM ET) to execute conditional trades

# Configuration
PROJECT_DIR="/home/nock/projects/quant_suite"
LOG_DIR="$HOME/quant_results/logs"
PYTHON_PATH="/usr/bin/python3"  # Adjust if using venv

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Set up environment
export PYTHONPATH="$PROJECT_DIR"
cd "$PROJECT_DIR"

# Log start
echo "========================================" >> "$LOG_DIR/cron_trades.log"
echo "Cron trade execution started: $(date)" >> "$LOG_DIR/cron_trades.log"

# Check if it's a trading day (Mon-Fri, not a holiday)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -gt 5 ]; then
    echo "Weekend - skipping" >> "$LOG_DIR/cron_trades.log"
    exit 0
fi

# Run the scheduled trades script
# Remove --execute flag for dry run mode (safer default)
# Add --execute when ready for live trading
# Load trades from today's file if it exists, otherwise use defaults
TRADE_FILE="trades_$(date +%Y%m%d).json"
if [ -f "$HOME/quant_results/scheduled_trades/$TRADE_FILE" ]; then
    # LIVE EXECUTION ENABLED
    $PYTHON_PATH "$PROJECT_DIR/scripts/scheduled_trades.py" --trades "$TRADE_FILE" --execute 2>&1 | tee -a "$LOG_DIR/cron_trades.log"
else
    echo "No trade file for today ($TRADE_FILE), skipping" >> "$LOG_DIR/cron_trades.log"
fi

# Log completion
echo "Cron trade execution completed: $(date)" >> "$LOG_DIR/cron_trades.log"
echo "========================================" >> "$LOG_DIR/cron_trades.log"
