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
        echo ""
        echo "$CRON_MARKER - Signpost Monitor"
        echo "# Check price signposts every 10 min during market hours (Mon-Fri, 9:30 AM - 4 PM ET)"
        echo "*/10 9-15 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/signpost_monitor.py --alerts >> ~/quant_results/logs/signpost.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Scheduled Trades"
        echo "# Execute scheduled trades at 9:31 AM ET (1 min after open for prices to settle)"
        echo "31 9 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/cron_trade_wrapper.sh >> ~/quant_results/logs/scheduled_trades.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Master Data Collection"
        echo "# Collect from all 35+ data sources every 30 min during market hours"
        echo "*/30 6-17 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py --quick >> ~/quant_results/logs/collection.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Sector Rotation Analysis"
        echo "# Analyze sector rotation hourly during market hours"
        echo "0 7-16 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 -c 'from src.synthesis.sector_rotation import SectorRotationDetector; import asyncio; asyncio.run(SectorRotationDetector().analyze_sectors())' >> ~/quant_results/logs/sector_rotation.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Legal/Geopolitical Monitor"
        echo "# Check legal and geopolitical events every 2 hours"
        echo "0 6,8,10,12,14,16 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 -c 'from src.data.sources.alternative.legal_tracker import LegalTracker; from src.data.sources.alternative.geopolitical import GeopoliticalMonitor; import asyncio; asyncio.run(LegalTracker().collect_all()); asyncio.run(GeopoliticalMonitor().collect_all())' >> ~/quant_results/logs/legal_geo.log 2>&1"
    } | crontab -

    echo "Cron jobs installed. Current schedule:"
    show_cron
}

remove_cron() {
    echo "Removing trading automation cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | grep -v "signpost_monitor" | grep -v "cron_trade_wrapper" | crontab -

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
