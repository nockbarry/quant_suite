#!/bin/bash
# Setup cron jobs for automated trading workflow
#
# The crontab is OWNED by this script: install commands do a destructive
# rewrite of every entry matching the managed-script filters below. The live
# crontab and this file must not drift — `diff` mode verifies that and is run
# by readiness_check daily. If you hand-edit the crontab, mirror the change
# here (or accept that the next install will revert it).
#
# Usage: ./setup_cron.sh install|remove|show|install_auto|remove_auto|show_auto|install_all|diff

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUANT_RESULTS_DIR="${QUANT_RESULTS_DIR:-$HOME/quant_results}"
LOG_DIR="$QUANT_RESULTS_DIR/logs"
CRON_MARKER="# QUANT_SUITE_TRADING"
CRON_AUTO_MARKER="# QUANT_SUITE_AUTO"

# Beta A/B instance (declarative live runner). Entries emitted only if present.
BETA_DIR="$HOME/athena-beta"
BETA_RESULTS_DIR="$HOME/quant_results_beta"

# Dead-man's switch: healthchecks.io ping URL, one per host. Owner creates the
# check and writes the URL into this file; until then no ping line is emitted.
HEALTHCHECKS_URL_FILE="$QUANT_RESULTS_DIR/config/healthchecks_url"

# Every script name this file manages. Used to strip old entries before
# re-emitting and by remove commands. Keep in sync with the emit functions.
TRADING_FILTERS=(trading_day.sh cron_squeeze_scan cron_news_collect collect_all_data
    signpost_monitor cron_trade_wrapper archive_daily_signals run_day_trading_signals
    cron_weekly_improvement cron_signal_digest sector_rotation legal_tracker geopolitical)
AUTO_FILTERS=(athena_scheduler.sh session_wrapper.sh health_monitor.py sentinel.py
    cron_signal_scan.py cron_prediction_scorer cron_opinion_scorer cron_decision_quality
    cron_belief_update cron_usage_to_db cron_build_target cron_reconcile cron_realized_pnl
    cron_benchmark readiness_check.py auto_corrections.py run_prediction_markets.py
    cron_market_movers cron_thesis_maintenance cron_auto_execute run_declarative_live
    run_cross_reference run_stress_test run_bug_monitor run_meta_observer
    cron_log_cleanup cron_corporate_actions hc-ping.com)

filter_out() {
    # Read crontab on stdin, drop lines matching any pattern in "$@" plus the marker.
    local marker="$1"; shift
    local args=(-v -e "$marker")
    local p
    for p in "$@"; do args+=(-e "$p"); done
    grep "${args[@]}"
}

emit_trading_entries() {
    echo "$CRON_MARKER - Trading Day Start"
    echo "# Pre-market prep at 6:00 AM ET (Mon-Fri)"
    echo "0 6 * * 1-5 $SCRIPT_DIR/trading_day.sh start >> $LOG_DIR/cron.log 2>&1"
    echo ""
    echo "$CRON_MARKER - State Updates"
    echo "# Update state every 5 min during market hours (Mon-Fri, 6 AM - 5 PM ET)"
    echo "*/5 6-16 * * 1-5 $SCRIPT_DIR/trading_day.sh update >> $LOG_DIR/cron.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Trading Day End"
    echo "# Stop daemons after market close at 5:00 PM ET (Mon-Fri)"
    echo "0 17 * * 1-5 $SCRIPT_DIR/trading_day.sh stop >> $LOG_DIR/cron.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Pre-dawn RSS Pull"
    echo "# Close the 4h RSS gap before /morning-briefing (5:55 AM, Mon-Fri)"
    echo "55 5 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py --quick >> $LOG_DIR/collection.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Master Data Collection (Quick)"
    echo "# Essential sources (news, state, signposts) every 30 min"
    echo "*/30 6-17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py --quick >> $LOG_DIR/collection.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Master Data Collection (Full)"
    echo "# All 13 sources (congressional, insider, finviz, WSB, prediction markets, etc.) every 2 hours"
    echo "0 6,8,10,12,14,16 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/collect_all_data.py >> $LOG_DIR/collection.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Signal Digest"
    echo "# Build unified signal digest every 30 min (quality-weighted, deduplicated)"
    echo "15,45 6-17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_signal_digest.py >> $LOG_DIR/signal_digest.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Signpost Monitor"
    echo "# Check price signposts every 10 min during market hours"
    echo "*/10 9-15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/signpost_monitor.py --alerts >> $LOG_DIR/signpost.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Scheduled Trades"
    echo "# Execute scheduled trades at 9:31 AM ET (1 min after open)"
    echo "31 9 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_trade_wrapper.sh >> $LOG_DIR/scheduled_trades.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Day Trading Signals"
    echo "# Scan for day trading signals every 5 min during market hours + opening range"
    echo "*/5 9-15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/run_day_trading_signals.py --scan --deploy-paper >> $LOG_DIR/day_trading_signals.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Daily Signal Archive"
    echo "# Archive all signals daily at 5:30 PM ET for backtesting"
    echo "30 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/archive_daily_signals.py >> $LOG_DIR/signal_archive.log 2>&1"
    echo ""
    echo "$CRON_MARKER - Weekly Improvement Review"
    echo "# Weekly improvement review on Sundays at 6 PM ET"
    echo "0 18 * * 0 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/cron_weekly_improvement_review.py >> $LOG_DIR/weekly_review.log 2>&1"
}

emit_auto_entries() {
    echo "$CRON_AUTO_MARKER - Sentinel Start"
    echo "# Start sentinel daemon at 5:55 AM ET (Mon-Fri)"
    echo "55 5 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh setup >> $LOG_DIR/scheduler.log 2>&1 && $SCRIPT_DIR/athena_scheduler.sh sentinel-start >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Morning Briefing"
    echo "# Run morning briefing at 6:30 AM ET (Mon-Fri)"
    echo "30 6 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot morning-briefing >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Operator Session Start"
    echo "# Start operator session at 8:30 AM ET (Mon-Fri)"
    echo "30 8 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh operator-start >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Morning Trade Decision"
    echo "# Run trade decision at 10:00 AM ET (auto-executes paper orders after)"
    echo "0 10 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot trade-decision >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Afternoon Trade Decision"
    echo "# Run trade decision at 1:00 PM ET (auto-executes paper orders after)"
    echo "0 13 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot trade-decision >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Auto-Execute Pending Decisions"
    echo "# Execute DB PENDING decisions: pre-open sweep + after each trade-decision session"
    echo "45 6 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_auto_execute.py >> $LOG_DIR/auto_execute.log 2>&1"
    echo "15 10 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_auto_execute.py >> $LOG_DIR/auto_execute.log 2>&1"
    echo "15 13 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_auto_execute.py >> $LOG_DIR/auto_execute.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Reconcile (shadow)"
    echo "# Shadow-reconcile portfolio toward target at 10:15 AM ET. Plan-only until live cutover (Phase 4b)."
    echo "15 10 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_reconcile.py --shadow >> $LOG_DIR/reconcile.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Operator Session Stop"
    echo "# Stop operator at 4:05 PM ET (Mon-Fri)"
    echo "5 16 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh operator-stop >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - EOD Review"
    echo "# Run end-of-day review at 4:30 PM ET (Mon-Fri)"
    echo "30 16 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot eod-review >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Sentinel Stop"
    echo "# Stop sentinel at 5:10 PM ET (Mon-Fri)"
    echo "10 17 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh sentinel-stop >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Market Movers Scan"
    echo "# After-close market mover scan at 5:20 PM ET (Mon-Fri)"
    echo "20 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_market_movers.py >> $LOG_DIR/market_movers.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Market Movers Midday"
    echo "# Midday market mover scan at 12:30 PM ET (Mon-Fri)"
    echo "30 12 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_market_movers.py --intraday >> $LOG_DIR/market_movers.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Auto Corrections"
    echo "# Apply mechanical corrections from cross-reference alerts and stress tests every 30 min"
    echo "25,55 9-16 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/auto_corrections.py >> $LOG_DIR/auto_corrections.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Cross-Reference Engine"
    echo "# Red-flag generation (insider divergence, failed interventions) — auto_corrections consumes this"
    echo "40 9,11,13,15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/run_cross_reference.py >> $LOG_DIR/cross_reference.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Portfolio Stress Test"
    echo "# Monte Carlo VaR + scenario analysis (Sunday 3:45 PM, before system-review; auto_corrections reads latest)"
    echo "45 15 * * 0 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/run_stress_test.py >> $LOG_DIR/stress_test.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Bug Monitor"
    echo "# Scan logs for tracebacks, categorize, propose fixes (nightly 5:50 PM Mon-Fri)"
    echo "50 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/run_bug_monitor.py >> $LOG_DIR/bug_monitor.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Meta Observer"
    echo "# Cross-instance divergence (alpha vs beta declarative A/B) — Sunday 3:50 PM"
    echo "50 15 * * 0 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/run_meta_observer.py >> $LOG_DIR/meta_observer.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Corporate Actions Cache"
    echo "# Fetch splits/dividends for held + universe symbols before any P&L or reconcile runs (5:45 AM Mon-Fri)"
    echo "45 5 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_corporate_actions.py >> $LOG_DIR/corporate_actions.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Log Cleanup"
    echo "# Rotate oversized logs, gzip, prune >60d (Sunday 3:30 PM)"
    echo "30 15 * * 0 $SCRIPT_DIR/cron_log_cleanup.sh >> $LOG_DIR/log_cleanup.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Thesis Maintenance"
    echo "# Auto-suggest theses, surface overdue reviews, fix conviction anchoring (daily 6:10 AM)"
    echo "10 6 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_thesis_maintenance.py >> $LOG_DIR/thesis_maintenance.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Target Portfolio (shadow)"
    echo "# Build shadow TargetPortfolio from beliefs, log gap vs current (daily 6:15 AM). Read-only until Phase 4."
    echo "15 6 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_build_target.py >> $LOG_DIR/build_target.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Signal Scan (Python + Prediction Markets)"
    echo "# Scan WSB, Stocktwits, prediction markets, thesis suggestions 2x/day"
    echo "# Consolidated from 6x/day (6,8,10,12,14,16) after Apr-2026 token audit."
    echo "# cron_signal_digest.py (every 30 min) is the intraday convergence radar;"
    echo "# this heavier opinion-capture scan is aligned with 10:00 and 13:00 trade-decision."
    echo "25 10,13 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_signal_scan.py >> $LOG_DIR/signal_scan.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Prediction Market Signals"
    echo "# Thesis-matched prediction market signals 2x/day (aligned with signal scan)"
    echo "30 10,13 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/run_prediction_markets.py >> $LOG_DIR/prediction_markets.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Signal Scan Claude (Morning + Afternoon)"
    echo "# LLM analysis of social signals at 10:30 AM and 2:30 PM ET (Mon-Fri)"
    echo "30 10 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot signal-scan >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Prediction Scorer"
    echo "# Score resolved predictions at 5:15 PM ET (Mon-Fri)"
    echo "15 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_prediction_scorer.py >> $LOG_DIR/prediction_scorer.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Opinion Scorer"
    echo "# Score market opinions at 5:20 PM ET (Mon-Fri)"
    echo "20 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_opinion_scorer.py >> $LOG_DIR/opinion_scorer.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Decision Quality"
    echo "# Track decision quality at 5:22 PM ET (Mon-Fri)"
    echo "22 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_decision_quality.py >> $LOG_DIR/decision_quality.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Realized P&L (nightly)"
    echo "# Rebuild realized lots from broker fills, stamp decisions (5:40 PM Mon-Fri)"
    echo "40 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_realized_pnl.py >> $LOG_DIR/realized_pnl.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Weekly Benchmark"
    echo "# Account vs SPY/QQQ/frozen-own-basket (Sunday 4:00 PM, before system-review)"
    echo "0 16 * * 0 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_benchmark.py >> $LOG_DIR/benchmark.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Usage Cost Tracker"
    echo "# Persist Claude Code token usage to session_costs at 5:25 PM ET (Mon-Fri)"
    echo "25 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_usage_to_db.py >> $LOG_DIR/usage_to_db.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Belief Updater"
    echo "# Update signal weights and calibration at 5:30 PM ET (Mon-Fri)"
    echo "30 17 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 scripts/cron_belief_update.py >> $LOG_DIR/belief_update.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Internal Review"
    echo "# Automated self-assessment at 12:00 PM and 3:00 PM ET (Mon-Fri)"
    echo "0 12 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot internal-review >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Evening Research"
    echo "# Post-market web research + news synthesis at 5:45 PM ET (Mon-Fri)"
    echo "45 17 * * 1-5 $SCRIPT_DIR/athena_scheduler.sh oneshot evening-research >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Midweek Theorist"
    echo "# Strategic thinking sessions on Tue/Thu at 6:00 PM ET"
    echo "0 18 * * 2,4 $SCRIPT_DIR/athena_scheduler.sh oneshot theorist >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Weekly Thesis + Brainstorm + Theorist"
    echo "# Weekly thesis review (6 PM), brainstorm (7 PM), theorist (8 PM) on Sundays"
    echo "0 18 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot thesis >> $LOG_DIR/scheduler.log 2>&1"
    echo "0 19 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot brainstorm >> $LOG_DIR/scheduler.log 2>&1"
    echo "0 20 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot theorist >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Weekly System Review"
    echo "# Self-evaluation: performance, thesis health, parameter review on Sundays at 4:30 PM ET"
    echo "30 16 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot system-review >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Weekly Hypothesis Generation"
    echo "# Generate testable hypotheses from accumulated data on Sundays at 5 PM ET"
    echo "0 17 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot hypothesis-gen >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Saturday Research Cycle"
    echo "# Full research cycle + backtesting on Saturdays at 2 PM ET"
    echo "0 14 * * 6 $SCRIPT_DIR/athena_scheduler.sh oneshot research >> $LOG_DIR/scheduler.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Boot Recovery"
    echo "# On WSL/system reboot, wait 30s then initialize all Athena instances"
    echo "@reboot sleep 30 && $SCRIPT_DIR/athena_scheduler.sh boot >> $LOG_DIR/boot.log 2>&1"
    echo ""
    echo "$CRON_AUTO_MARKER - Readiness Checks (Pre-Market + Intraday)"
    echo "# Pre-market readiness with auto-fix at 5:30 AM ET"
    echo "30 5 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --quick --alert >> $LOG_DIR/readiness.log 2>&1"
    echo "# Post-open check at 9:45 AM — verify operator, sentinel, state all running"
    echo "45 9 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick --alert >> $LOG_DIR/readiness.log 2>&1"
    echo "# Midday check at 12:15 PM — verify sessions ran, data fresh"
    echo "15 12 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick --alert >> $LOG_DIR/readiness.log 2>&1"
    echo "# Pre-close check at 3:45 PM — last chance to catch issues before EOD"
    echo "45 15 * * 1-5 cd $PROJECT_DIR && PYTHONPATH=. python3 $SCRIPT_DIR/readiness_check.py --fix --spawn-fixer --quick --alert >> $LOG_DIR/readiness.log 2>&1"

    if [ -d "$BETA_DIR" ]; then
        echo ""
        echo "$CRON_AUTO_MARKER - Beta Declarative Live (A/B instance)"
        echo "# Declarative builder+reconciler LIVE on the isolated beta paper account (10:15 AM Mon-Fri)"
        echo "15 10 * * 1-5 cd $BETA_DIR && ATHENA_INSTANCE=beta QUANT_RESULTS_DIR=$BETA_RESULTS_DIR PYTHONPATH=. python3 scripts/run_declarative_live.py --live >> $BETA_RESULTS_DIR/logs/declarative_live.log 2>&1"
        echo ""
        echo "$CRON_AUTO_MARKER - Beta Realized P&L (nightly)"
        echo "43 17 * * 1-5 cd $BETA_DIR && ATHENA_INSTANCE=beta QUANT_RESULTS_DIR=$BETA_RESULTS_DIR PYTHONPATH=. python3 scripts/cron_realized_pnl.py >> $BETA_RESULTS_DIR/logs/realized_pnl.log 2>&1"
    fi

    if [ -f "$HEALTHCHECKS_URL_FILE" ]; then
        local hc_url
        hc_url="$(head -1 "$HEALTHCHECKS_URL_FILE" | tr -d '[:space:]')"
        if [ -n "$hc_url" ]; then
            echo ""
            echo "$CRON_AUTO_MARKER - Dead-Man's Switch"
            echo "# Ping healthchecks.io every 5 min on trading days; missed pings alert the owner even when this host is off"
            echo "*/5 * * * 1-5 curl -fsS -m 10 --retry 3 $hc_url > /dev/null 2>&1"
        fi
    fi
}

strip_trading() { filter_out "$CRON_MARKER" "${TRADING_FILTERS[@]}"; }
strip_auto() { filter_out "$CRON_AUTO_MARKER" "${AUTO_FILTERS[@]}"; }

render_full() {
    # What the crontab would look like after install_all, given the current live crontab.
    local existing
    existing=$(crontab -l 2>/dev/null | strip_trading | strip_auto)
    echo "$existing"
    echo ""
    emit_trading_entries
    echo ""
    emit_auto_entries
}

normalize() {
    # Cron entries only: no comments/blanks, sorted for set comparison.
    grep -v '^#' | grep -v '^[[:space:]]*$' | sort
}

diff_cron() {
    local live rendered
    live=$(crontab -l 2>/dev/null | normalize)
    rendered=$(render_full | normalize)
    if [ "$live" = "$rendered" ]; then
        echo "OK: live crontab matches setup_cron.sh (no drift)"
        return 0
    fi
    echo "DRIFT: live crontab differs from what setup_cron.sh would install."
    echo "Lines only in live crontab (would be DELETED by install_all):"
    comm -23 <(echo "$live") <(echo "$rendered") | sed 's/^/  - /'
    echo "Lines only in setup_cron.sh (would be ADDED by install_all):"
    comm -13 <(echo "$live") <(echo "$rendered") | sed 's/^/  + /'
    return 1
}

show_cron() {
    echo "Current quant_suite cron jobs:"
    crontab -l 2>/dev/null | grep -A1 "$CRON_MARKER" || echo "  (none installed)"
}

show_auto() {
    echo "Autonomous Claude session cron jobs:"
    crontab -l 2>/dev/null | grep -A1 "$CRON_AUTO_MARKER" || echo "  (none installed)"
}

backup_crontab() {
    local backup="$QUANT_RESULTS_DIR/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
    crontab -l 2>/dev/null > "$backup" && echo "Crontab backed up to $backup"
}

install_cron() {
    echo "Installing trading automation cron jobs..."
    backup_crontab
    {
        crontab -l 2>/dev/null | strip_trading
        echo ""
        emit_trading_entries
    } | crontab -
    echo "Trading cron jobs installed. Current schedule:"
    show_cron
}

remove_cron() {
    echo "Removing trading automation cron jobs..."
    backup_crontab
    crontab -l 2>/dev/null | strip_trading | crontab -
    echo "Cron jobs removed."
}

install_auto() {
    echo "Installing autonomous trading day cron jobs..."
    backup_crontab
    {
        crontab -l 2>/dev/null | strip_auto
        echo ""
        emit_auto_entries
    } | crontab -
    echo "Autonomous cron jobs installed. Current schedule:"
    show_auto
}

remove_auto() {
    echo "Removing autonomous Claude session cron jobs..."
    backup_crontab
    crontab -l 2>/dev/null | strip_auto | crontab -
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
    diff)
        diff_cron
        ;;
    *)
        echo "Usage: $0 {install|remove|show|install_auto|remove_auto|show_auto|install_all|diff}"
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
        echo "  diff          Compare live crontab vs what install_all would produce (exit 1 on drift)"
        exit 1
        ;;
esac
