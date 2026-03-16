#!/bin/bash
# Install cron entries for a named Athena instance
# Usage: ./scripts/install_instance_cron.sh <instance_name>
#   e.g.: ./scripts/install_instance_cron.sh beta

set -euo pipefail

INSTANCE="${1:?Usage: $0 <instance_name>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$HOME/quant_results_${INSTANCE}"
LOG_DIR="$RESULTS_DIR/logs"
MARKER="QUANT_SUITE_${INSTANCE^^}"  # e.g., QUANT_SUITE_BETA

# Env prefix for all cron commands
ENV="QUANT_RESULTS_DIR=$RESULTS_DIR ATHENA_INSTANCE=$INSTANCE"

# Verify instance exists
if [ ! -d "$RESULTS_DIR" ]; then
    echo "ERROR: Instance '$INSTANCE' not found at $RESULTS_DIR"
    echo "Create it first: ./scripts/instance_launcher.sh create $INSTANCE <api_key> <secret_key>"
    exit 1
fi

mkdir -p "$LOG_DIR"

# Strip existing entries for this instance
crontab -l 2>/dev/null | sed "/# ${MARKER}/,/# END ${MARKER}/d" | crontab -

# Build new cron block
# Instance schedule is LIGHTER than default:
# - No 8-hour operator (costs too much for 3 instances)
# - Morning briefing + 2 trade decisions + EOD review = core loop
# - Signal scan shared from default (reads same data)
# - No separate sentinel (shares default's market data)
# - Staggered times to avoid Claude capacity contention

# Stagger: beta starts 5 min after default, gamma 10 min after
case "$INSTANCE" in
    beta)  OFFSET=5 ;;
    gamma) OFFSET=10 ;;
    *)     OFFSET=0 ;;
esac

BRIEFING_MIN=$((35 + OFFSET))   # 6:35 or 6:40 (default is 6:30)
TRADE1_MIN=$((5 + OFFSET))      # 10:05 or 10:10 (default is 10:00)
TRADE2_MIN=$((5 + OFFSET))      # 13:05 or 13:10 (default is 13:00)
EOD_MIN=$((35 + OFFSET))        # 16:35 or 16:40 (default is 16:30)

CRON_BLOCK="
# ${MARKER} - Instance ${INSTANCE} Automated Trading
# Morning Briefing (staggered +${OFFSET}min from default)
${BRIEFING_MIN} 6 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot morning-briefing >> ${LOG_DIR}/scheduler.log 2>&1

# Trade Decision AM (staggered)
${TRADE1_MIN} 10 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot trade-decision >> ${LOG_DIR}/scheduler.log 2>&1

# Trade Decision PM (staggered)
${TRADE2_MIN} 13 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot trade-decision >> ${LOG_DIR}/scheduler.log 2>&1

# EOD Review (staggered)
${EOD_MIN} 16 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot eod-review >> ${LOG_DIR}/scheduler.log 2>&1

# State daemon update every 5 min during market hours
*/5 6-17 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 -c \"from src.synthesis.daemon import LiveDaemon; LiveDaemon().update_now()\" >> ${LOG_DIR}/daemon.log 2>&1

# Prediction scorer at 5:15 PM
15 17 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/cron_prediction_scorer.py >> ${LOG_DIR}/prediction_scorer.log 2>&1

# Belief updater at 5:30 PM
30 17 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/cron_belief_update.py >> ${LOG_DIR}/belief_update.log 2>&1

# Auto-execute after trade decisions (10 min after each trade-decision)
$((TRADE1_MIN + 10)) 10 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/cron_auto_execute.py >> ${LOG_DIR}/auto_execute.log 2>&1
$((TRADE2_MIN + 10)) 13 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/cron_auto_execute.py >> ${LOG_DIR}/auto_execute.log 2>&1

# Ensemble check before auto-execute (5 min after trade-decision)
$((TRADE1_MIN + 5)) 10 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/run_ensemble.py >> ${LOG_DIR}/ensemble.log 2>&1
$((TRADE2_MIN + 5)) 13 * * 1-5 cd ${PROJECT_DIR} && ${ENV} PYTHONPATH=. python3 scripts/run_ensemble.py >> ${LOG_DIR}/ensemble.log 2>&1

# Sunday: thesis + hypothesis-gen (staggered)
$((0 + OFFSET)) 17 * * 0 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot hypothesis-gen >> ${LOG_DIR}/scheduler.log 2>&1
$((0 + OFFSET)) 18 * * 0 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot thesis >> ${LOG_DIR}/scheduler.log 2>&1

# Saturday: research cycle (staggered)
$((0 + OFFSET)) 14 * * 6 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh oneshot research >> ${LOG_DIR}/scheduler.log 2>&1

# tmux setup at 5:55 AM (ensures session exists)
55 5 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh setup >> ${LOG_DIR}/scheduler.log 2>&1

# Health check every 5 min during market hours
*/5 6-17 * * 1-5 ${ENV} ${SCRIPT_DIR}/athena_scheduler.sh health-check >> ${LOG_DIR}/health.log 2>&1
# END ${MARKER}
"

# Install
(crontab -l 2>/dev/null; echo "$CRON_BLOCK") | crontab -

echo "Installed cron for instance '$INSTANCE' (marker: $MARKER)"
echo "  Briefing: 6:${BRIEFING_MIN} AM"
echo "  Trade 1:  10:$(printf '%02d' $TRADE1_MIN) AM"
echo "  Trade 2:  1:$(printf '%02d' $TRADE2_MIN) PM"
echo "  EOD:      4:$(printf '%02d' $EOD_MIN) PM"
echo "  Entries:  $(crontab -l | grep -c "$MARKER") cron entries"
echo ""
echo "Verify with: crontab -l | grep '$MARKER'"
