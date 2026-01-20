#!/bin/bash
# Setup cron jobs for automated trading workflow
#
# This creates the following scheduled tasks:
# - 6:00 AM ET: Start daemons, run pre-market prep
# - 6:30 AM ET: Update state with fresh data
# - Every 5 min during market hours: Update state
# - 4:30 PM ET: Stop daemons
#
# Usage: ./setup_cron.sh install|remove|show

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_MARKER="# QUANT_SUITE_TRADING"

show_cron() {
    echo "Current quant_suite cron jobs:"
    crontab -l 2>/dev/null | grep -A1 "$CRON_MARKER" || echo "  (none installed)"
}

install_cron() {
    echo "Installing trading automation cron jobs..."

    # Get existing crontab (without our entries)
    EXISTING=$(crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | grep -v "cron_squeeze_scan" | grep -v "cron_news_collect")

    # Create new crontab
    {
        echo "$EXISTING"
        echo ""
        echo "$CRON_MARKER - Trading Day Start"
        echo "# Pre-market prep at 6:00 AM ET (Mon-Fri)"
        echo "0 6 * * 1-5 $SCRIPT_DIR/trading_day.sh start >> ~/quant_results/logs/cron.log 2>&1"
        echo ""
        echo "$CRON_MARKER - State Updates"
        echo "# Update state every 5 min during market hours (Mon-Fri, 6 AM - 5 PM ET)"
        echo "*/5 6-16 * * 1-5 $SCRIPT_DIR/trading_day.sh update >> ~/quant_results/logs/cron.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Trading Day End"
        echo "# Stop daemons after market close at 5:00 PM ET (Mon-Fri)"
        echo "0 17 * * 1-5 $SCRIPT_DIR/trading_day.sh stop >> ~/quant_results/logs/cron.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Squeeze Scanner"
        echo "# Daily squeeze scan at 6:30 AM ET (Mon-Fri)"
        echo "30 6 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/cron_squeeze_scan.py >> ~/quant_results/logs/squeeze_scan.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Fast News Collection"
        echo "# Fast news collection every 30 min during market hours (Mon-Fri, 6 AM - 5 PM ET)"
        echo "*/30 6-17 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/cron_news_collect_fast.py >> ~/quant_results/logs/news_fast.log 2>&1"
    } | crontab -

    echo "Cron jobs installed. Current schedule:"
    show_cron
}

remove_cron() {
    echo "Removing trading automation cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | crontab -

    echo "Cron jobs removed."
}

case "$1" in
    install)
        install_cron
        ;;
    remove)
        remove_cron
        ;;
    show)
        show_cron
        ;;
    *)
        echo "Usage: $0 {install|remove|show}"
        echo ""
        echo "This sets up automated trading workflow:"
        echo "  - 6:00 AM: Start daemons, pre-market prep"
        echo "  - Every 5 min: Update state.json"
        echo "  - 5:00 PM: Stop daemons"
        exit 1
        ;;
esac
