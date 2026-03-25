#!/bin/bash
# Session Wrapper — wraps each Claude Code invocation for autonomous operation.
#
# Handles:
# 1. Market day check (skip weekends/holidays)
# 2. Lock file acquisition (prevent duplicate sessions)
# 3. Autonomous system prompt injection via --append-system-prompt
# 4. Logging (stdout → $QUANT_RESULTS_DIR/logs/claude_{type}_{date}.log)
# 5. Post-completion: release lock, update scheduler_state.json, write completion
#
# Usage:
#   session_wrapper.sh <session-type> [extra-args...]
#
# Session types:
#   morning-briefing  — One-shot, uses -p with /morning-briefing
#   trade-decision    — One-shot, uses -p with /trade-decision
#   eod-review        — One-shot, uses -p with /eod-review
#   research          — One-shot, uses -p with /research --quick
#   thesis            — One-shot, uses -p with /thesis
#   brainstorm        — One-shot, uses -p with /brainstorm
#   operator          — Long-running, persistent loop
#   research-theory   — One-shot, thesis suggestions + theory generation

set -uo pipefail

# Ensure claude binary is on PATH (cron has minimal PATH that misses ~/.local/bin)
export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/$(ls $HOME/.nvm/versions/node/ 2>/dev/null | tail -1)/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUANT_RESULTS_DIR="${QUANT_RESULTS_DIR:-$HOME/quant_results}"
ATHENA_INSTANCE="${ATHENA_INSTANCE:-auto}"
export QUANT_RESULTS_DIR
export ATHENA_INSTANCE
SCHEDULER_DIR="$QUANT_RESULTS_DIR/scheduler"
LOG_DIR="$QUANT_RESULTS_DIR/logs"
LOCK_DIR="$SCHEDULER_DIR/locks"

mkdir -p "$SCHEDULER_DIR/completions" "$LOCK_DIR" "$LOG_DIR"

SESSION_TYPE="${1:-}"
shift 2>/dev/null || true  # Extra args after session type

if [ -z "$SESSION_TYPE" ]; then
    echo "Usage: session_wrapper.sh <session-type>"
    echo "Types: morning-briefing, trade-decision, eod-review, research, thesis, brainstorm, operator"
    exit 1
fi

DATE=$(date '+%Y%m%d')
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/claude_${SESSION_TYPE}_${DATE}.log"
LOCK_FILE="$LOCK_DIR/${SESSION_TYPE}.lock"
START_TIME=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [wrapper:${SESSION_TYPE}] $*" | tee -a "$LOG_FILE"
}

# --- Market Day Check ---

is_market_day() {
    local DOW=$(date +%u)  # 1=Mon, 7=Sun

    # Skip weekends
    if [ "$DOW" -ge 6 ]; then
        return 1
    fi

    # US market holidays for 2026 (NYSE closed)
    local TODAY=$(date '+%Y-%m-%d')
    local HOLIDAYS=(
        "2026-01-01"  # New Year's Day
        "2026-01-19"  # MLK Day
        "2026-02-16"  # Presidents' Day
        "2026-04-03"  # Good Friday
        "2026-05-25"  # Memorial Day
        "2026-06-19"  # Juneteenth
        "2026-07-03"  # Independence Day (observed)
        "2026-09-07"  # Labor Day
        "2026-11-26"  # Thanksgiving
        "2026-12-25"  # Christmas
    )

    for holiday in "${HOLIDAYS[@]}"; do
        if [ "$TODAY" = "$holiday" ]; then
            return 1
        fi
    done

    return 0
}

# Skip non-market days for trading sessions (allow research/thesis/brainstorm/research-theory/theorist on any day)
case "$SESSION_TYPE" in
    morning-briefing|trade-decision|eod-review|operator|analyst|evening-research)
        if ! is_market_day; then
            log "Not a market day, skipping $SESSION_TYPE"
            exit 0
        fi
        ;;
esac

# --- Lock Acquisition ---

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            log "Session $SESSION_TYPE already running (PID $LOCK_PID), skipping"
            exit 0
        else
            log "Stale lock found (PID $LOCK_PID dead), removing"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo $$ > "$LOCK_FILE"
    log "Lock acquired (PID $$)"
}

release_lock() {
    rm -f "$LOCK_FILE"
    log "Lock released"
}

# --- Autonomous Mode Flag ---

set_autonomous_mode() {
    cat > "$SCHEDULER_DIR/autonomous_mode.json" <<AUTOJSON
{
    "active": true,
    "session_type": "$SESSION_TYPE",
    "started_at": "$(date -Iseconds)",
    "pid": $$
}
AUTOJSON
}

clear_autonomous_mode() {
    rm -f "$SCHEDULER_DIR/autonomous_mode.json"
}

# --- Write Completion Record ---

write_completion() {
    local SUCCESS="$1"
    local EXIT_CODE="$2"
    local END_TIME=$(date +%s)
    local DURATION=$((END_TIME - START_TIME))

    # Check if Claude already wrote an enriched completion record during this session.
    # If so, skip the fallback to avoid overwriting with empty key_findings/symbols.
    local EXISTING
    EXISTING=$(ls -t "$SCHEDULER_DIR/completions/${SESSION_TYPE}_"*.json 2>/dev/null | head -1)
    if [ -n "$EXISTING" ]; then
        local EXISTING_TIME
        EXISTING_TIME=$(stat -c %Y "$EXISTING" 2>/dev/null || echo 0)
        if [ "$EXISTING_TIME" -gt "$START_TIME" ]; then
            # Verify it has actual findings (not just an empty shell)
            local HAS_FINDINGS
            HAS_FINDINGS=$(python3 -c "
import json, sys
with open('$EXISTING') as f:
    r = json.load(f)
print('yes' if r.get('key_findings') else 'no')
" 2>/dev/null || echo "no")
            if [ "$HAS_FINDINGS" = "yes" ]; then
                log "Enriched completion record exists, skipping fallback"
                return
            fi
        fi
    fi

    # Use smart completion to extract findings from actual session outputs
    log "Running smart completion fallback for $SESSION_TYPE"
    cd "$PROJECT_DIR" && PYTHONPATH="$PROJECT_DIR" python3 \
        "$SCRIPT_DIR/smart_completion.py" \
        "$SESSION_TYPE" \
        "$START_TIME" \
        "$LOG_FILE" \
        2>&1 | tee -a "$LOG_FILE" || true
}

# --- Update Scheduler State ---

update_state() {
    local STATUS="$1"
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
    'pid': $$,
}
state['last_updated'] = datetime.now().isoformat()

with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null || true
}

# --- Cleanup on exit ---

cleanup() {
    local EXIT_CODE=$?
    log "Session ending (exit code: $EXIT_CODE)"

    clear_autonomous_mode
    release_lock

    # Update situation board with session completion
    PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load_or_create()
board.add_observation('$SESSION_TYPE', 'session_complete', 'Session $SESSION_TYPE completed (exit=$EXIT_CODE)')
board.save()
" 2>/dev/null || true

    if [ $EXIT_CODE -eq 0 ]; then
        write_completion "True" "$EXIT_CODE"
        update_state "completed"
        # Log success to ProcessEvent
        PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.autonomy.provenance import log_event
log_event('session_completed', source='scheduler:$SESSION_TYPE', title='Session completed: $SESSION_TYPE')
" 2>/dev/null || true
    else
        write_completion "False" "$EXIT_CODE"
        update_state "failed"
        # Log failure to ProcessEvent
        PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.autonomy.provenance import log_event
log_event('session_failed', source='scheduler:$SESSION_TYPE', severity='warning', title='Session failed: $SESSION_TYPE (exit $EXIT_CODE)')
" 2>/dev/null || true
    fi

    log "Cleanup complete"
}

trap cleanup EXIT

# --- Build Autonomous System Prompt ---

build_autonomous_prompt() {
    local SESSION_TYPE="$1"
    local TIMEOUT="${2:-15}"

    local BASE_PROMPT
    BASE_PROMPT=$(cat <<BASEPROMPT
AUTONOMOUS MODE: You are running as a scheduled autonomous session.
Do NOT ask the user questions — there is no human present.
Complete all steps independently. Save outputs to standard paths.
Log errors and continue with remaining steps.
Execution authority: FULL (execute any trade within risk limits, no human approval needed).
Max runtime: ${TIMEOUT} minutes. Be efficient with tokens.
If you encounter errors reading files or connecting to services, log the error and continue.
INSTANCE: ${ATHENA_INSTANCE} | RESULTS_DIR: ${QUANT_RESULTS_DIR}
IMPORTANT: Always use 'from src.core.paths import paths' for file paths. The paths module respects QUANT_RESULTS_DIR=${QUANT_RESULTS_DIR} which is set in your environment. Do NOT use Path.home() / "quant_results" directly.
BASEPROMPT
)

    # Session-specific instructions
    local SESSION_PROMPT=""
    case "$SESSION_TYPE" in
        operator)
            SESSION_PROMPT=$(cat <<OPPROMPT

OPERATOR LOOP: You MUST implement a persistent monitoring loop.
1. Run operator_check() immediately
2. Review state.news_events and state.news_urgency_alerts for thesis-matched news
3. Check for auto-generated thesis suggestions via ThesisSuggester
4. Sleep for the configured interval (1-5 minutes)
5. REPEAT from step 1 until timeout or market close (4:05 PM ET)
Do NOT exit after a single check. Keep looping. Use bash sleep between checks.
Write trade triggers to scheduler/trade_triggers.json when 4+ signals converge.
OPPROMPT
)
            ;;
    esac

    # All sessions should write enriched completion records
    local COMPLETION_PROMPT
    COMPLETION_PROMPT=$(cat <<COMPPROMPT

COMPLETION LOGGING: Before exiting, write an enriched completion record:
\`\`\`python
from src.monitoring.autonomous_mode import write_session_completion
write_session_completion(
    session_type="${SESSION_TYPE}",
    success=True,
    summary="<2-3 sentence summary of what you did>",
    key_findings=["<finding 1>", "<finding 2>"],
    symbols=["<symbols you analyzed>"],
)
\`\`\`
COMPPROMPT
)

    echo "${BASE_PROMPT}${SESSION_PROMPT}${COMPLETION_PROMPT}"
}

# --- Session Type Configuration ---

get_timeout() {
    case "$SESSION_TYPE" in
        morning-briefing)  echo 15 ;;
        trade-decision)    echo 10 ;;
        eod-review)        echo 15 ;;
        research)          echo 20 ;;
        thesis)            echo 10 ;;
        brainstorm)        echo 15 ;;
        signal-scan)       echo 15 ;;
        research-theory)   echo 15 ;;
        internal-review)   echo 10 ;;
        analyst)           echo 5 ;;
        theorist)          echo 15 ;;
        evening-research)  echo 20 ;;
        hypothesis-gen)    echo 15 ;;
        research-queue)    echo 30 ;;
        system-review)     echo 30 ;;
        operator)          echo 480 ;;  # 8 hours
        *)                 echo 15 ;;
    esac
}

get_model() {
    # Model tier policy:
    #   opus   — primary instance trade decisions, weekly strategic reviews
    #   sonnet — beta/gamma instances, research, monitoring, analysis, synthesis
    # Beta/gamma use sonnet for trade-decision to save ~$1,200/month while still
    # providing independent comparison signals for the parallel experiment.
    case "$SESSION_TYPE" in
        trade-decision)
            if [ "$ATHENA_INSTANCE" = "auto" ] || [ -z "$ATHENA_INSTANCE" ]; then
                echo "opus"
            else
                echo "sonnet"
            fi
            ;;
        system-review)     echo "opus" ;;
        theorist)          echo "opus" ;;
        *)                 echo "sonnet" ;;
    esac
}

get_fallback_model() {
    # When the primary model hits a rate limit, fall back to this
    echo "sonnet"
}

get_skill_prompt() {
    case "$SESSION_TYPE" in
        morning-briefing)  echo "/morning-briefing" ;;
        trade-decision)    echo "/trade-decision" ;;
        eod-review)        echo "/eod-review" ;;
        research)          echo "/research --quick" ;;
        thesis)            echo "/thesis" ;;
        brainstorm)        echo "/brainstorm" ;;
        signal-scan)       echo "/social-signals" ;;
        research-theory)   echo "/social-signals" ;;
        internal-review)   echo "/internal-review" ;;
        analyst)           echo "/analyst" ;;
        theorist)          echo "/theorist" ;;
        evening-research)  echo "/evening-research" ;;
        hypothesis-gen)    echo "/hypothesis-gen" ;;
        research-queue)    echo "/research-queue" ;;
        system-review)     echo "/system-review" ;;
        *)                 echo "" ;;
    esac
}

# --- Main Execution ---

acquire_lock
set_autonomous_mode
update_state "running"

# Log session start to ProcessEvent audit trail
PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.autonomy.provenance import log_event
log_event('session_started', source='scheduler:$SESSION_TYPE', title='Session started: $SESSION_TYPE')
" 2>/dev/null || true

TIMEOUT=$(get_timeout)
MODEL=$(get_model)
FALLBACK_MODEL=$(get_fallback_model)
SKILL_PROMPT=$(get_skill_prompt)
AUTO_PROMPT=$(build_autonomous_prompt "$SESSION_TYPE" "$TIMEOUT")

# --- Inject Swarm Context ---
# Append situation board and strategic context summaries to the system prompt
# so every Claude session starts with awareness of today's events and multi-day patterns.

SWARM_CONTEXT=""
if [ -f "$QUANT_RESULTS_DIR/scheduler/situation_board.json" ]; then
    SWARM_CONTEXT=$(PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
print(board.get_summary())
" 2>/dev/null || echo "")
fi

STRATEGIC_CONTEXT=""
if [ -f "$QUANT_RESULTS_DIR/scheduler/strategic_context.json" ]; then
    STRATEGIC_CONTEXT=$(PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
print(ctx.get_summary())
" 2>/dev/null || echo "")
fi

if [ -n "$SWARM_CONTEXT" ]; then
    AUTO_PROMPT="${AUTO_PROMPT} SITUATION BOARD (today so far): ${SWARM_CONTEXT}"
fi
if [ -n "$STRATEGIC_CONTEXT" ]; then
    AUTO_PROMPT="${AUTO_PROMPT} STRATEGIC CONTEXT (multi-day): ${STRATEGIC_CONTEXT}"
fi

log "Starting $SESSION_TYPE session (model=$MODEL, timeout=${TIMEOUT}m)"

cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR"

# WSL / nested session fix: unset CLAUDECODE to allow launching from within
# another Claude session or from environments that inherit the variable.
unset CLAUDECODE 2>/dev/null || true

# Write system prompt to temp file, then read as single line to avoid
# shell expansion issues with newlines and special characters in --append-system-prompt
PROMPT_FILE=$(mktemp /tmp/athena_prompt_XXXXXX.txt)
printf '%s' "$AUTO_PROMPT" | tr '\n' ' ' > "$PROMPT_FILE"

# --- Run Claude with model fallback ---
# If the primary model fails (rate limit / overloaded), retry with the fallback model.

run_claude_with_fallback() {
    local PROMPT="$1"
    local CURRENT_MODEL="$MODEL"
    local EXIT_CODE=0

    log "Attempting with model=$CURRENT_MODEL"

    # Capture both stdout and stderr so we can detect rate limit errors
    local TMPOUT=$(mktemp /tmp/athena_claude_XXXXXX.out)

    timeout --foreground "${TIMEOUT}m" claude \
        --model "$CURRENT_MODEL" \
        --dangerously-skip-permissions \
        --append-system-prompt "$(cat "$PROMPT_FILE")" \
        -p "$PROMPT" \
        2>&1 | tee -a "$LOG_FILE" "$TMPOUT" || EXIT_CODE=$?

    # Check for rate limit / overloaded errors
    if [ $EXIT_CODE -ne 0 ] && [ "$CURRENT_MODEL" != "$FALLBACK_MODEL" ]; then
        if grep -qi "rate.limit\|overloaded\|capacity\|too many\|429\|529\|limit.*reset" "$TMPOUT" 2>/dev/null; then
            log "WARNING: $CURRENT_MODEL hit rate limit (exit=$EXIT_CODE), retrying with $FALLBACK_MODEL"
            rm -f "$TMPOUT"

            timeout --foreground "${TIMEOUT}m" claude \
                --model "$FALLBACK_MODEL" \
                --dangerously-skip-permissions \
                --append-system-prompt "$(cat "$PROMPT_FILE")" \
                -p "$PROMPT" \
                2>&1 | tee -a "$LOG_FILE" || true

            rm -f "$TMPOUT"
            return 0
        fi
    fi

    rm -f "$TMPOUT"
    return 0
}

if [ "$SESSION_TYPE" = "operator" ]; then
    # Operator is long-running — runs with -p but the autonomous prompt
    # instructs Claude to implement a persistent monitoring loop with sleep
    # between checks. The 8-hour timeout acts as the outer boundary.
    # Use unique timestamp suffix to prevent Claude from detecting "stale task"
    # when a previous operator session completed earlier the same day.
    log "Launching operator session (persistent loop via autonomous prompt)"

    run_claude_with_fallback "/operator-session --active --session=$(date +%s)"

    log "Operator session ended"
else
    # One-shot sessions use -p for non-interactive execution
    log "Launching one-shot: $SKILL_PROMPT"

    run_claude_with_fallback "$SKILL_PROMPT"

    log "One-shot session completed"

    # Run ensemble before auto-execute for trade-decision sessions
    if [ "$SESSION_TYPE" = "trade-decision" ]; then
        log "Running decision ensemble before auto-execute..."
        cd "$PROJECT_DIR" && PYTHONPATH="$PROJECT_DIR" python3 scripts/run_ensemble.py >> "$LOG_DIR/ensemble.log" 2>&1 || true
    fi

    # Auto-execute pending decisions after trade-decision sessions (paper only)
    if [ "$SESSION_TYPE" = "trade-decision" ]; then
        log "Auto-executing pending paper decisions"
        PYTHONPATH="$PROJECT_DIR" python3 "$SCRIPT_DIR/cron_auto_execute.py" \
            2>&1 | tee -a "$LOG_FILE" || true
    fi
fi

rm -f "$PROMPT_FILE" 2>/dev/null

log "Session $SESSION_TYPE finished"
