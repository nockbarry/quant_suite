#!/bin/bash
# Athena Scheduler — tmux-based session manager for autonomous trading day.
#
# Manages a tmux session "athena-auto" with three windows:
#   Window 0: "operator"  — Long-running operator session
#   Window 1: "oneshot"   — Sequential one-shot sessions (briefing, trade, eod)
#   Window 2: "monitor"   — sentinel.py (or legacy health_monitor.py)
#
# Usage:
#   athena_scheduler.sh setup          — Create tmux session with all windows
#   athena_scheduler.sh operator-start — Launch operator in window 0
#   athena_scheduler.sh operator-stop  — Graceful shutdown of operator
#   athena_scheduler.sh oneshot <type>  — Run a one-shot session in window 1
#   athena_scheduler.sh sentinel-start — Start sentinel daemon in window 2
#   athena_scheduler.sh sentinel-stop  — Stop sentinel daemon
#   athena_scheduler.sh monitor-start  — Start sentinel (backward compat alias)
#   athena_scheduler.sh monitor-stop   — Stop sentinel (backward compat alias)
#   athena_scheduler.sh status         — Show all active sessions
#   athena_scheduler.sh kill-all       — Emergency stop everything

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUANT_RESULTS_DIR="${QUANT_RESULTS_DIR:-$HOME/quant_results}"
ATHENA_INSTANCE="${ATHENA_INSTANCE:-auto}"
TMUX_SESSION="athena-${ATHENA_INSTANCE}"
SCHEDULER_DIR="$QUANT_RESULTS_DIR/scheduler"
LOG_DIR="$QUANT_RESULTS_DIR/logs"

# Ensure directories exist
mkdir -p "$SCHEDULER_DIR/locks" "$SCHEDULER_DIR/completions" "$LOG_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [scheduler] $*"
    echo "$msg" >> "$LOG_DIR/scheduler.log"
    # Only print to stdout if running interactively (avoids double-write when cron
    # redirects stdout to the same scheduler.log)
    [ -t 1 ] && echo "$msg" || true
}

# --- Setup ---

cmd_setup() {
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        log "Session $TMUX_SESSION already exists"
        cmd_status
        return 0
    fi

    log "Creating tmux session: $TMUX_SESSION"

    # Create session with first window "operator"
    tmux new-session -d -s "$TMUX_SESSION" -n "operator" -x 200 -y 50

    # Create window 1: oneshot
    tmux new-window -t "$TMUX_SESSION" -n "oneshot"

    # Create window 2: monitor
    tmux new-window -t "$TMUX_SESSION" -n "monitor"

    # Set environment in all windows (unset CLAUDECODE for nested session safety)
    for win in 0 1 2; do
        tmux send-keys -t "$TMUX_SESSION:$win" "cd $PROJECT_DIR && export PYTHONPATH=$PROJECT_DIR && unset CLAUDECODE" C-m
    done

    log "tmux session $TMUX_SESSION created with 3 windows"
    cmd_status
}

# --- Operator ---

cmd_operator_start() {
    # Ensure tmux session exists
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        cmd_setup
    fi

    # Check if operator is actually running (via live process, not pane text)
    local operator_pid
    operator_pid=$(cat "$SCHEDULER_DIR/locks/operator.lock" 2>/dev/null || echo "")
    if [ -n "$operator_pid" ] && kill -0 "$operator_pid" 2>/dev/null; then
        # Process exists — check if it's stopped/zombie
        local proc_state
        proc_state=$(ps -o stat= -p "$operator_pid" 2>/dev/null || echo "")
        if echo "$proc_state" | grep -qE '^[TZ]'; then
            log "Operator process $operator_pid is stuck (state: $proc_state), killing..."
            kill -9 "$operator_pid" 2>/dev/null || true
            # Also kill child claude process
            pkill -9 -P "$operator_pid" 2>/dev/null || true
            sleep 1
            rm -f "$SCHEDULER_DIR/locks/operator.lock"
        else
            log "Operator is already running (PID $operator_pid)"
            return 0
        fi
    else
        # No valid process — clean up stale lock
        rm -f "$SCHEDULER_DIR/locks/operator.lock"
    fi

    # Respawn the operator pane if its shell is dead
    _respawn_pane_if_dead "operator"

    log "Starting operator session"

    # session_wrapper.sh handles its own logging via tee — no outer tee needed
    tmux send-keys -t "$TMUX_SESSION:operator" \
        "$SCRIPT_DIR/session_wrapper.sh operator" C-m

    # Update scheduler state
    _update_scheduler_state "operator" "running"
    log "Operator started in tmux window 0"
}

cmd_operator_stop() {
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        log "No tmux session found"
        return 1
    fi

    log "Stopping operator session gracefully..."

    # Send /exit to the Claude session
    tmux send-keys -t "$TMUX_SESSION:operator" "/exit" C-m

    # Wait up to 30s for graceful exit
    for i in $(seq 1 30); do
        sleep 1
        if ! tmux capture-pane -t "$TMUX_SESSION:operator" -p 2>/dev/null | grep -q "claude"; then
            log "Operator exited gracefully"
            _update_scheduler_state "operator" "stopped"
            return 0
        fi
    done

    # Force kill if still running
    log "Operator did not exit gracefully, sending Ctrl-C"
    tmux send-keys -t "$TMUX_SESSION:operator" C-c
    sleep 2
    _update_scheduler_state "operator" "stopped"
    log "Operator stopped"
}

# --- One-shot sessions ---

cmd_oneshot() {
    local SESSION_TYPE="${1:-}"
    if [ -z "$SESSION_TYPE" ]; then
        echo "Usage: athena_scheduler.sh oneshot <morning-briefing|trade-decision|eod-review|research|thesis|brainstorm|evening-research>"
        exit 1
    fi

    # Ensure tmux session exists
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        cmd_setup
    fi

    local DATE=$(date '+%Y%m%d')
    local LOG_FILE="$LOG_DIR/claude_${SESSION_TYPE}_${DATE}.log"

    # Check if the session_wrapper lock file already exists (another session running)
    local LOCK_FILE="$SCHEDULER_DIR/locks/${SESSION_TYPE}.lock"
    if [ -f "$LOCK_FILE" ]; then
        local LOCK_PID
        LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            log "Session $SESSION_TYPE already running (PID $LOCK_PID), skipping"
            return 0
        fi
    fi

    # Wait for the oneshot pane to be idle (not running a previous session)
    # This prevents tmux send-keys from being swallowed by a busy shell
    local wait_count=0
    while [ $wait_count -lt 30 ]; do
        # Check if any other oneshot session_wrapper is running
        local running_wrapper
        running_wrapper=$(pgrep -f "session_wrapper.sh" 2>/dev/null | while read wpid; do
            # Don't count the operator wrapper
            if grep -q "operator" /proc/$wpid/cmdline 2>/dev/null; then
                continue
            fi
            echo "$wpid"
        done | head -1 || true)
        if [ -z "$running_wrapper" ]; then
            break
        fi
        wait_count=$((wait_count + 1))
        if [ $wait_count -eq 1 ]; then
            log "Waiting for previous oneshot session to finish..."
        fi
        sleep 2
    done

    if [ $wait_count -ge 30 ]; then
        log "WARNING: Previous oneshot still running after 60s, proceeding anyway"
    fi

    log "Starting one-shot session: $SESSION_TYPE"

    # Respawn the oneshot pane if its shell is dead
    _respawn_pane_if_dead "oneshot"

    # session_wrapper.sh handles its own logging — no outer tee needed
    tmux send-keys -t "$TMUX_SESSION:oneshot" \
        "$SCRIPT_DIR/session_wrapper.sh $SESSION_TYPE" C-m

    _update_scheduler_state "$SESSION_TYPE" "running"
    log "One-shot session $SESSION_TYPE started in tmux window 1"
}

# --- Sentinel (replaces Health Monitor) ---

cmd_sentinel_start() {
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        cmd_setup
    fi

    local DATE=$(date '+%Y%m%d')
    local LOG_FILE="$LOG_DIR/sentinel_${DATE}.log"

    log "Starting sentinel daemon"

    # Kill any existing process in the monitor pane (health_monitor or old sentinel)
    tmux send-keys -t "$TMUX_SESSION:monitor" C-c 2>/dev/null || true
    sleep 2

    # Respawn the monitor pane if its shell is dead
    _respawn_pane_if_dead "monitor"

    # Sentinel has its own FileHandler — don't tee to the same file (causes double logging)
    tmux send-keys -t "$TMUX_SESSION:monitor" \
        "cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR python3 $SCRIPT_DIR/sentinel.py" C-m

    _update_scheduler_state "sentinel" "running"
    log "Sentinel started in tmux window 2"
}

cmd_sentinel_stop() {
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        log "No tmux session found"
        return 1
    fi

    log "Stopping sentinel..."
    tmux send-keys -t "$TMUX_SESSION:monitor" C-c
    sleep 2
    _update_scheduler_state "sentinel" "stopped"
    log "Sentinel stopped"
}

# Backward compatible aliases
cmd_monitor_start() { cmd_sentinel_start; }
cmd_monitor_stop() { cmd_sentinel_stop; }

# --- Status ---

cmd_status() {
    echo "=== Athena Autonomous Scheduler Status ==="
    echo ""

    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "tmux session: NOT RUNNING"
        echo ""
        echo "Run: athena_scheduler.sh setup"
        return 0
    fi

    echo "tmux session: $TMUX_SESSION (ACTIVE)"
    echo ""

    # Show each window
    for win in operator oneshot monitor; do
        echo "--- Window: $win ---"
        # Show last 3 lines of the pane
        tmux capture-pane -t "$TMUX_SESSION:$win" -p 2>/dev/null | tail -3 || echo "  (empty)"
        echo ""
    done

    # Show lock files
    echo "--- Active Locks ---"
    ls -la "$SCHEDULER_DIR/locks/"*.lock 2>/dev/null || echo "  (none)"
    echo ""

    # Show scheduler state
    if [ -f "$SCHEDULER_DIR/scheduler_state.json" ]; then
        echo "--- Scheduler State ---"
        python3 -c "
import json
with open('$SCHEDULER_DIR/scheduler_state.json') as f:
    state = json.load(f)
for k, v in state.get('sessions', {}).items():
    print(f'  {k}: {v.get(\"status\", \"unknown\")} (last: {v.get(\"last_updated\", \"never\")})')
print(f'  Health monitor: {state.get(\"health\", {}).get(\"monitor_running\", False)}')
print(f'  Operator running: {state.get(\"health\", {}).get(\"operator_running\", False)}')
" 2>/dev/null || echo "  (error reading state)"
    fi

    echo ""
    echo "--- Recent Completions ---"
    ls -lt "$SCHEDULER_DIR/completions/"*.json 2>/dev/null | head -5 || echo "  (none)"
}

# --- Kill All ---

cmd_kill_all() {
    log "EMERGENCY: Killing all autonomous sessions"

    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        # Try graceful first
        for win in operator oneshot monitor; do
            tmux send-keys -t "$TMUX_SESSION:$win" C-c 2>/dev/null || true
        done
        sleep 3

        # Kill the session
        tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
        log "tmux session killed"
    fi

    # Clean up locks
    rm -f "$SCHEDULER_DIR/locks/"*.lock 2>/dev/null || true
    rm -f "$SCHEDULER_DIR/autonomous_mode.json" 2>/dev/null || true

    _update_scheduler_state "all" "killed"
    log "All sessions killed, locks cleared"
}

# --- Helpers ---

_respawn_pane_if_dead() {
    # Check if a tmux pane's shell is still alive. If not, kill and recreate the window.
    local WINDOW_NAME="$1"

    # Get the PID of the shell process running in the pane
    local pane_pid
    pane_pid=$(tmux list-panes -t "$TMUX_SESSION:$WINDOW_NAME" -F '#{pane_pid}' 2>/dev/null || echo "")

    if [ -z "$pane_pid" ]; then
        log "Pane $WINDOW_NAME has no PID, recreating window"
    elif ! kill -0 "$pane_pid" 2>/dev/null; then
        log "Pane $WINDOW_NAME shell (PID $pane_pid) is dead, recreating window"
    else
        # Shell is alive, nothing to do
        return 0
    fi

    # Kill the old window (may fail if already gone) and recreate
    tmux kill-window -t "$TMUX_SESSION:$WINDOW_NAME" 2>/dev/null || true
    tmux new-window -t "$TMUX_SESSION" -n "$WINDOW_NAME"
    tmux send-keys -t "$TMUX_SESSION:$WINDOW_NAME" "cd $PROJECT_DIR && export PYTHONPATH=$PROJECT_DIR && unset CLAUDECODE" C-m
    sleep 0.5
    log "Respawned window: $WINDOW_NAME"
}

_update_scheduler_state() {
    local SESSION_TYPE="$1"
    local STATUS="$2"

    python3 -c "
import json
from datetime import datetime
from pathlib import Path

state_file = Path('$SCHEDULER_DIR/scheduler_state.json')
state = {'initialized': True, 'version': '1.0', 'sessions': {}, 'health': {}}
if state_file.exists():
    try:
        with open(state_file) as f:
            state = json.load(f)
    except Exception:
        pass

state.setdefault('sessions', {})
state['sessions']['$SESSION_TYPE'] = {
    'status': '$STATUS',
    'last_updated': datetime.now().isoformat(),
}
state['last_updated'] = datetime.now().isoformat()
state['today'] = datetime.now().strftime('%Y-%m-%d')

# Update health flags
if '$SESSION_TYPE' == 'operator':
    state.setdefault('health', {})['operator_running'] = ('$STATUS' == 'running')
elif '$SESSION_TYPE' == 'health_monitor':
    state.setdefault('health', {})['monitor_running'] = ('$STATUS' == 'running')
elif '$SESSION_TYPE' == 'all' and '$STATUS' == 'killed':
    state['health'] = {'monitor_running': False, 'operator_running': False}

with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null || true
}

# --- WSL Keepalive ---
# On WSL, the Linux kernel shuts down ~8s after the last process exits.
# A running tmux session keeps WSL alive. The health monitor also acts as a keepalive.

cmd_wsl_info() {
    echo "=== WSL Setup for Autonomous Trading ==="
    echo ""
    echo "WSL suspends when all Linux processes exit."
    echo "The athena-auto tmux session keeps WSL alive during the trading day."
    echo ""
    echo "To ensure WSL wakes BEFORE market hours:"
    echo ""
    echo "Option 1: Windows Task Scheduler (recommended)"
    echo "  1. Open taskschd.msc"
    echo "  2. Create Task: 'Athena WSL Wake'"
    echo "  3. Trigger: Daily 5:50 AM, weekdays only"
    echo "  4. Action: wsl -d Ubuntu -e bash -c 'echo wake >> \${QUANT_RESULTS_DIR:-\$HOME/quant_results}/logs/wsl_wake.log'"
    echo "  5. Check 'Wake the computer to run this task'"
    echo "  6. Check 'Run whether user is logged on or not'"
    echo ""
    echo "Option 2: Use the provided batch file"
    echo "  Schedule: scripts/wsl_wake.bat in Task Scheduler"
    echo ""
    echo "Option 3: Keep WSL running overnight"
    echo "  tmux new-session -d -s keepalive 'while true; do sleep 3600; done'"
    echo ""
    echo "Current WSL status:"
    echo "  Cron: $(systemctl is-active cron 2>/dev/null || echo 'unknown')"
    echo "  tmux sessions: $(tmux list-sessions 2>/dev/null | wc -l)"
    echo "  Uptime: $(uptime -p 2>/dev/null || echo 'unknown')"
}

# --- Health Check (WSL persistence) ---

cmd_health_check() {
    # Called by cron every 5 minutes during market hours.
    # Ensures tmux, sentinel, and operator are alive.
    # Recovers from WSL suspends that kill background processes.

    # 1. Check tmux session
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        log "HEALTH: tmux session missing, recreating..."
        cmd_setup
    fi

    # 2. Check sentinel PID (only during market hours 6 AM - 5 PM ET)
    local hour
    hour=$(TZ="America/New_York" date +%H)
    if [ "$hour" -ge 6 ] && [ "$hour" -lt 17 ]; then
        local sentinel_pid=""
        if [ -f "$SCHEDULER_DIR/locks/sentinel.lock" ]; then
            sentinel_pid=$(cat "$SCHEDULER_DIR/locks/sentinel.lock" 2>/dev/null)
        fi
        if [ -n "$sentinel_pid" ] && ! kill -0 "$sentinel_pid" 2>/dev/null; then
            log "HEALTH: sentinel dead (PID $sentinel_pid), restarting..."
            rm -f "$SCHEDULER_DIR/locks/sentinel.lock"
            cmd_sentinel_start
        fi
    fi

    # 3. Check operator (only between 9 AM and 4 PM ET)
    if [ "$hour" -ge 9 ] && [ "$hour" -lt 16 ]; then
        local op_lock="$SCHEDULER_DIR/locks/operator.lock"
        if [ -f "$op_lock" ]; then
            local op_pid
            op_pid=$(cat "$op_lock" 2>/dev/null)
            if [ -n "$op_pid" ] && ! kill -0 "$op_pid" 2>/dev/null; then
                log "HEALTH: operator dead (PID $op_pid), cleaning up..."
                rm -f "$op_lock"
                # Don't auto-restart operator — let the next cron fire handle it
            fi
        fi
    fi

    log "HEALTH: check complete"
}

# --- Main ---

case "${1:-}" in
    setup)
        cmd_setup
        ;;
    operator-start)
        cmd_operator_start
        ;;
    operator-stop)
        cmd_operator_stop
        ;;
    oneshot)
        cmd_oneshot "${2:-}"
        ;;
    sentinel-start)
        cmd_sentinel_start
        ;;
    sentinel-stop)
        cmd_sentinel_stop
        ;;
    monitor-start)
        cmd_monitor_start
        ;;
    monitor-stop)
        cmd_monitor_stop
        ;;
    status)
        cmd_status
        ;;
    kill-all)
        cmd_kill_all
        ;;
    wsl-info)
        cmd_wsl_info
        ;;
    health-check)
        cmd_health_check
        ;;
    *)
        echo "Athena Autonomous Scheduler"
        echo ""
        echo "Usage: $0 <command> [args]"
        echo ""
        echo "Commands:"
        echo "  setup           Create tmux session with all windows"
        echo "  operator-start  Launch operator in window 0"
        echo "  operator-stop   Graceful shutdown of operator"
        echo "  oneshot <type>  Run one-shot session (morning-briefing, trade-decision, analyst, etc.)"
        echo "  sentinel-start  Start sentinel daemon in window 2"
        echo "  sentinel-stop   Stop sentinel daemon"
        echo "  monitor-start   Start sentinel (backward compat alias)"
        echo "  monitor-stop    Stop sentinel (backward compat alias)"
        echo "  status          Show all active sessions"
        echo "  kill-all        Emergency stop everything"
        echo "  wsl-info        WSL setup instructions for autonomous trading"
        echo "  health-check    Check and recover tmux, sentinel, operator (for cron)"
        exit 1
        ;;
esac
