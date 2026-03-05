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
        echo ""
        echo "$CRON_MARKER - Weekly Improvement Review"
        echo "# Weekly improvement review on Sundays at 6 PM ET"
        echo "0 18 * * 0 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/cron_weekly_improvement_review.py >> ~/quant_results/logs/weekly_review.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Daily Signal Archive"
        echo "# Archive all signals daily at 5:30 PM ET for future backtesting"
        echo "30 17 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/archive_daily_signals.py >> ~/quant_results/logs/signal_archive.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Day Trading Signal Scanner"
        echo "# Scan for day trading signals every 5 min during market hours (9:30 AM - 4 PM ET)"
        echo "*/5 9-15 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/run_day_trading_signals.py --scan --deploy-paper >> ~/quant_results/logs/day_trading_signals.log 2>&1"
        echo "# Also run at 9:31 and 9:35 for opening range signals"
        echo "31,35 9 * * 1-5 cd $(dirname $SCRIPT_DIR) && PYTHONPATH=. python3 $SCRIPT_DIR/run_day_trading_signals.py --scan --deploy-paper >> ~/quant_results/logs/day_trading_signals.log 2>&1"
    } | crontab -

    echo "Cron jobs installed. Current schedule:"
    show_cron
}

remove_cron() {
    echo "Removing trading automation cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | grep -v "signpost_monitor" | grep -v "cron_trade_wrapper" | crontab -

    echo "Cron jobs removed."
}

# --- Autonomous Claude Sessions (QUANT_SUITE_AUTO) ---

CRON_AUTO_MARKER="# QUANT_SUITE_AUTO"

show_auto() {
    echo "Autonomous Claude session cron jobs:"
    crontab -l 2>/dev/null | grep -A1 "$CRON_AUTO_MARKER" || echo "  (none installed)"
}

install_auto() {
    echo "Installing autonomous trading day cron jobs..."
    echo "These schedule Claude Code sessions throughout the trading day."
    echo ""

    # Get existing crontab (without our auto entries)
    EXISTING=$(crontab -l 2>/dev/null | grep -v "$CRON_AUTO_MARKER" | grep -v "athena_scheduler.sh" | grep -v "session_wrapper.sh" | grep -v "health_monitor.py")

    # Create new crontab with auto entries
    {
        echo "$EXISTING"
        echo ""
        echo "$CRON_AUTO_MARKER - Health Monitor Start"
        echo "# Start health monitor at 5:55 AM ET (Mon-Fri)"
        echo "55 5 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh setup >> ~/quant_results/logs/scheduler.log 2>&1 && $SCRIPT_DIR/athena_scheduler.sh monitor-start >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Morning Briefing"
        echo "# Run morning briefing at 6:30 AM ET (Mon-Fri)"
        echo "30 6 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot morning-briefing >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Operator Session Start"
        echo "# Start operator session at 8:30 AM ET (Mon-Fri)"
        echo "30 8 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh operator-start >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Morning Trade Decision"
        echo "# Run trade decision at 10:00 AM ET (Mon-Fri)"
        echo "0 10 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot trade-decision >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Afternoon Trade Decision"
        echo "# Run trade decision at 1:00 PM ET (Mon-Fri)"
        echo "0 13 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot trade-decision >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Operator Session Stop"
        echo "# Stop operator at 4:05 PM ET (Mon-Fri)"
        echo "5 16 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh operator-stop >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - EOD Review"
        echo "# Run end-of-day review at 4:30 PM ET (Mon-Fri)"
        echo "30 16 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot eod-review >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Health Monitor Stop"
        echo "# Stop health monitor at 5:10 PM ET (Mon-Fri)"
        echo "10 17 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh monitor-stop >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 8am"
        echo "# Research + thesis + theory generation at 8:00 AM ET (Mon-Fri)"
        echo "0 8 * * 1-5 $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 10am"
        echo "# Research + thesis + theory generation at 10:00 AM ET (Mon-Fri)"
        echo "0 10 * * 1-5 $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 12pm"
        echo "# Research + thesis + theory generation at 12:00 PM ET (Mon-Fri)"
        echo "0 12 * * 1-5 $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 2pm"
        echo "# Research + thesis + theory generation at 2:00 PM ET (Mon-Fri)"
        echo "0 14 * * 1-5 $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 4pm"
        echo "# Research + thesis + theory generation at 4:00 PM ET (Mon-Fri)"
        echo "0 16 * * 1-5 $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Research Theory 11pm"
        echo "# Research + thesis + theory generation at 11:00 PM ET (daily)"
        echo "0 23 * * * $SCRIPT_DIR/session_wrapper.sh research-theory >> ~/quant_results/logs/claude_research_theory.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Weekly Thesis Review"
        echo "# Weekly thesis review on Sundays at 6 PM ET"
        echo "0 18 * * 0 $SCRIPT_DIR/session_wrapper.sh thesis >> ~/quant_results/logs/claude_thesis_weekly.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Weekly Brainstorm"
        echo "# Weekly brainstorm on Sundays at 7 PM ET"
        echo "0 19 * * 0 $SCRIPT_DIR/session_wrapper.sh brainstorm >> ~/quant_results/logs/claude_brainstorm_weekly.log 2>&1"
    } | crontab -

    echo "Autonomous cron jobs installed. Current schedule:"
    show_auto
}

remove_auto() {
    echo "Removing autonomous Claude session cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_AUTO_MARKER" | grep -v "athena_scheduler.sh" | grep -v "session_wrapper.sh" | grep -v "health_monitor.py" | crontab -

    echo "Autonomous cron jobs removed."
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
    install_auto)
        install_auto
        ;;
    remove_auto)
        remove_auto
        ;;
    show_auto)
        show_auto
        ;;
    install_all)
        install_cron
        echo ""
        install_auto
        ;;
    *)
        echo "Usage: $0 {install|remove|show|install_auto|remove_auto|show_auto|install_all}"
        echo ""
        echo "Data automation (cron + Python daemons):"
        echo "  install       Install data collection cron jobs"
        echo "  remove        Remove data collection cron jobs"
        echo "  show          Show data collection cron jobs"
        echo ""
        echo "Autonomous Claude sessions (cron + tmux + Claude Code):"
        echo "  install_auto  Install autonomous trading day schedule"
        echo "  remove_auto   Remove autonomous trading day schedule"
        echo "  show_auto     Show autonomous trading day schedule"
        echo ""
        echo "Both:"
        echo "  install_all   Install data + autonomous cron jobs"
        exit 1
        ;;
esac
