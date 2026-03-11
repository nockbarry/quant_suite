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
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CRON_MARKER="# QUANT_SUITE_TRADING"

show_cron() {
    echo "Current quant_suite cron jobs:"
    crontab -l 2>/dev/null | grep -A1 "$CRON_MARKER" || echo "  (none installed)"
}

install_cron() {
    echo "Installing trading automation cron jobs..."
    echo "Note: Squeeze, news, sector rotation, legal/geo are handled by collect_all_data.py"

    # Get existing crontab (without our entries)
    EXISTING=$(crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | grep -v "cron_squeeze_scan" | grep -v "cron_news_collect" | grep -v "collect_all_data" | grep -v "signpost_monitor" | grep -v "cron_trade_wrapper" | grep -v "archive_daily_signals" | grep -v "run_day_trading_signals" | grep -v "cron_weekly_improvement" | grep -v "cron_signal_digest" | grep -v "cron_market_movers" | grep -v "sector_rotation" | grep -v "legal_tracker" | grep -v "geopolitical")

    # Create new crontab — consolidated from 13 entries to 8
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
        echo "$CRON_MARKER - Master Data Collection (Quick)"
        echo "# Essential sources (news, state, signposts) every 30 min"
        echo "*/30 6-17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py --quick >> ~/quant_results/logs/collection.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Master Data Collection (Full)"
        echo "# All 13 sources (congressional, insider, finviz, WSB, prediction markets, etc.) every 2 hours"
        echo "0 6,8,10,12,14,16 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py >> ~/quant_results/logs/collection.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Signal Digest"
        echo "# Build unified signal digest every 30 min (quality-weighted, deduplicated)"
        echo "15,45 6-17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_signal_digest.py >> ~/quant_results/logs/signal_digest.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Signpost Monitor"
        echo "# Check price signposts every 10 min during market hours"
        echo "*/10 9-15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/signpost_monitor.py --alerts >> ~/quant_results/logs/signpost.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Scheduled Trades"
        echo "# Execute scheduled trades at 9:31 AM ET (1 min after open)"
        echo "31 9 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_trade_wrapper.sh >> ~/quant_results/logs/scheduled_trades.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Day Trading Signals"
        echo "# Scan for day trading signals every 5 min during market hours + opening range"
        echo "*/5 9-15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/run_day_trading_signals.py --scan --deploy-paper >> ~/quant_results/logs/day_trading_signals.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Daily Signal Archive"
        echo "# Archive all signals daily at 5:30 PM ET for backtesting"
        echo "30 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/archive_daily_signals.py >> ~/quant_results/logs/signal_archive.log 2>&1"
        echo ""
        echo "$CRON_MARKER - Weekly Improvement Review"
        echo "# Weekly improvement review on Sundays at 6 PM ET"
        echo "0 18 * * 0 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_weekly_improvement_review.py >> ~/quant_results/logs/weekly_review.log 2>&1"
    } | crontab -

    echo "Cron jobs installed (10 entries). Current schedule:"
    show_cron
}

remove_cron() {
    echo "Removing trading automation cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | grep -v "trading_day.sh" | grep -v "signpost_monitor" | grep -v "cron_trade_wrapper" | grep -v "collect_all_data" | grep -v "cron_signal_digest" | grep -v "archive_daily_signals" | grep -v "run_day_trading_signals" | grep -v "cron_weekly_improvement" | crontab -

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

    # Get existing crontab (without our auto entries and orphaned standalone entries)
    EXISTING=$(crontab -l 2>/dev/null | grep -v "$CRON_AUTO_MARKER" | grep -v "athena_scheduler.sh" | grep -v "session_wrapper.sh" | grep -v "health_monitor.py" | grep -v "sentinel.py" | grep -v "cron_signal_scan.py" | grep -v "cron_prediction_scorer" | grep -v "cron_belief_update" | grep -v "readiness_check.py")

    # Create new crontab — consolidated from 13 entries to 11
    {
        echo "$EXISTING"
        echo ""
        echo "$CRON_AUTO_MARKER - Sentinel Start"
        echo "# Start sentinel daemon at 5:55 AM ET (Mon-Fri)"
        echo "55 5 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh setup >> ~/quant_results/logs/scheduler.log 2>&1 && $SCRIPT_DIR/athena_scheduler.sh sentinel-start >> ~/quant_results/logs/scheduler.log 2>&1"
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
        echo "# Run trade decision at 10:00 AM ET (auto-executes paper orders after)"
        echo "0 10 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot trade-decision >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Afternoon Trade Decision"
        echo "# Run trade decision at 1:00 PM ET (auto-executes paper orders after)"
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
        echo "$CRON_AUTO_MARKER - Sentinel Stop"
        echo "# Stop sentinel at 5:10 PM ET (Mon-Fri)"
        echo "10 17 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh sentinel-stop >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Market Movers Scan"
        echo "# After-close market mover scan at 5:20 PM ET (Mon-Fri)"
        echo "20 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_market_movers.py >> ~/quant_results/logs/market_movers.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Market Movers Midday"
        echo "# Midday market mover scan at 12:30 PM ET (Mon-Fri)"
        echo "30 12 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_market_movers.py --intraday >> ~/quant_results/logs/market_movers.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Signal Scan (Python + Prediction Markets)"
        echo "# Scan WSB, Stocktwits, prediction markets, thesis suggestions every 2 hours"
        echo "0 6,8,10,12,14,16 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_signal_scan.py >> ~/quant_results/logs/signal_scan.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Signal Scan Claude (Morning + Afternoon)"
        echo "# LLM analysis of social signals at 10:30 AM and 2:30 PM ET (Mon-Fri)"
        echo "30 10,14 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot signal-scan >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Prediction Scorer"
        echo "# Score resolved predictions at 5:15 PM ET (Mon-Fri)"
        echo "15 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_prediction_scorer.py >> ~/quant_results/logs/prediction_scorer.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Belief Updater"
        echo "# Update signal weights and calibration at 5:30 PM ET (Mon-Fri)"
        echo "30 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_belief_update.py >> ~/quant_results/logs/belief_update.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Internal Review"
        echo "# Automated self-assessment at 12:00 PM and 3:00 PM ET (Mon-Fri)"
        echo "0 12,15 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot internal-review >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Evening Research"
        echo "# Post-market web research + news synthesis at 5:45 PM ET (Mon-Fri)"
        echo "45 17 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot evening-research >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Midweek Theorist"
        echo "# Strategic thinking sessions on Tue/Thu at 6:00 PM ET"
        echo "0 18 * * 2,4 $SCRIPT_DIR/athena_scheduler.sh oneshot theorist >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Weekly Thesis + Brainstorm + Theorist"
        echo "# Weekly thesis review (6 PM), brainstorm (7 PM), theorist (8 PM) on Sundays"
        echo "0 18 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot thesis >> ~/quant_results/logs/scheduler.log 2>&1"
        echo "0 19 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot brainstorm >> ~/quant_results/logs/scheduler.log 2>&1"
        echo "0 20 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot theorist >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Weekly Hypothesis Generation"
        echo "# Generate testable hypotheses from accumulated data on Sundays at 5 PM ET"
        echo "0 17 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot hypothesis-gen >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Saturday Research Cycle"
        echo "# Full research cycle + backtesting on Saturdays at 2 PM ET"
        echo "0 14 * * 6 $SCRIPT_DIR/athena_scheduler.sh oneshot research >> ~/quant_results/logs/scheduler.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Readiness Checks (Pre-Market + Intraday)"
        echo "# Pre-market readiness with auto-fix at 5:30 AM ET"
        echo "30 5 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --quick >> ~/quant_results/logs/readiness.log 2>&1"
        echo "# Post-open check at 9:45 AM — verify operator, sentinel, state all running"
        echo "45 9 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick >> ~/quant_results/logs/readiness.log 2>&1"
        echo "# Midday check at 12:15 PM — verify sessions ran, data fresh"
        echo "15 12 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick >> ~/quant_results/logs/readiness.log 2>&1"
        echo "# Pre-close check at 3:45 PM — last chance to catch issues before EOD"
        echo "45 15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick >> ~/quant_results/logs/readiness.log 2>&1"
    } | crontab -

    echo "Autonomous cron jobs installed (15 entries). Current schedule:"
    show_auto
}

remove_auto() {
    echo "Removing autonomous Claude session cron jobs..."

    crontab -l 2>/dev/null | grep -v "$CRON_AUTO_MARKER" | grep -v "athena_scheduler.sh" | grep -v "session_wrapper.sh" | grep -v "health_monitor.py" | grep -v "sentinel.py" | grep -v "cron_signal_scan.py" | grep -v "readiness_check.py" | grep -v "cron_prediction_scorer" | grep -v "cron_belief_update" | crontab -

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
