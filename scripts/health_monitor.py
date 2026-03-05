#!/usr/bin/env python3
"""Athena Health Monitor — watchdog daemon for autonomous trading day.

Runs 05:55-17:05 ET. Checks every 60s:
- Is operator tmux pane alive? → Restart if dead
- Is state.json fresh? (>15 min = alert)
- Trade triggers from operator? → Launch trade-decision
- VIX > 25? → Log warning
- One-shot sessions hung? (>15 min) → Kill and log

Usage:
    python3 scripts/health_monitor.py             # Run until market close
    python3 scripts/health_monitor.py --once       # Single check
    python3 scripts/health_monitor.py --until 17:05  # Run until specific time
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
LOG_DIR = Path.home() / "quant_results" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [health] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"health_monitor_{datetime.now():%Y%m%d}.log"),
    ],
)
logger = logging.getLogger(__name__)

SCHEDULER_DIR = Path.home() / "quant_results" / "scheduler"
RESULTS_DIR = Path.home() / "quant_results"
SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
TMUX_SESSION = "athena-auto"

CHECK_INTERVAL = 60  # seconds
STATE_STALE_THRESHOLD = 15 * 60  # 15 minutes
ONESHOT_TIMEOUT = 15 * 60  # 15 minutes
OPERATOR_RESTART_COOLDOWN = 300  # 5 minutes between restart attempts

# Track state
last_operator_restart = datetime.min
running = True


def signal_handler(sig, frame):
    global running
    logger.info("Received shutdown signal, stopping...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def is_market_hours() -> bool:
    """Check if we're within market monitoring hours (5:55 AM - 5:05 PM ET)."""
    now = datetime.now()
    start = now.replace(hour=5, minute=55, second=0, microsecond=0)
    end = now.replace(hour=17, minute=5, second=0, microsecond=0)
    return start <= now <= end


def is_weekday() -> bool:
    return datetime.now().weekday() < 5


def tmux_session_exists() -> bool:
    """Check if the athena-auto tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


def is_operator_alive() -> bool:
    """Check if the operator has a running claude process.

    Uses the lock file PID and process state rather than tmux pane
    inspection, which is unreliable (pane shows 'sh' even when claude
    is running as a child process).
    """
    if not tmux_session_exists():
        return False

    # Check lock file for operator PID
    lock_file = SCHEDULER_DIR / "locks" / "operator.lock"
    if not lock_file.exists():
        return False

    try:
        pid = int(lock_file.read_text().strip())
    except (ValueError, OSError):
        return False

    # Check if process is alive and not stopped/zombie
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        state = result.stdout.strip()
        # T = stopped, Z = zombie — these are dead
        if state and state[0] in ("T", "Z"):
            return False
        return True
    except Exception:
        return False


def check_state_freshness() -> dict:
    """Check if state.json is fresh."""
    state_file = RESULTS_DIR / "live" / "state.json"
    if not state_file.exists():
        return {"fresh": False, "age_seconds": None, "error": "state.json missing"}

    age = time.time() - state_file.stat().st_mtime
    return {
        "fresh": age < STATE_STALE_THRESHOLD,
        "age_seconds": int(age),
        "age_minutes": round(age / 60, 1),
    }


def check_vix() -> dict:
    """Check current VIX from state.json."""
    state_file = RESULTS_DIR / "live" / "state.json"
    if not state_file.exists():
        return {"vix": None}

    try:
        with open(state_file) as f:
            state = json.load(f)
        vix = state.get("market", {}).get("vix", 0)
        return {"vix": vix, "elevated": vix > 25, "critical": vix > 30}
    except Exception:
        return {"vix": None}


def check_trade_triggers() -> list[dict]:
    """Check for unconsumed trade triggers."""
    triggers_file = SCHEDULER_DIR / "trade_triggers.json"
    if not triggers_file.exists():
        return []

    try:
        with open(triggers_file) as f:
            data = json.load(f)

        unconsumed = [
            t for t in data.get("triggers", [])
            if not t.get("consumed", False)
        ]
        return unconsumed
    except Exception:
        return []


def consume_trade_triggers(symbols: list[str]) -> None:
    """Mark trade triggers as consumed."""
    triggers_file = SCHEDULER_DIR / "trade_triggers.json"
    if not triggers_file.exists():
        return

    try:
        with open(triggers_file) as f:
            data = json.load(f)

        for trigger in data.get("triggers", []):
            if trigger.get("symbol") in symbols:
                trigger["consumed"] = True
                trigger["consumed_at"] = datetime.now().isoformat()

        data["last_checked"] = datetime.now().isoformat()
        with open(triggers_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error consuming triggers: {e}")


def check_locks() -> list[dict]:
    """Check for stale lock files (sessions that may be hung)."""
    lock_dir = SCHEDULER_DIR / "locks"
    if not lock_dir.exists():
        return []

    stale = []
    for lock_file in lock_dir.glob("*.lock"):
        age = time.time() - lock_file.stat().st_mtime
        session_type = lock_file.stem

        # Operator lock is expected to be long-lived
        if session_type == "operator":
            continue

        if age > ONESHOT_TIMEOUT:
            pid = None
            try:
                pid = int(lock_file.read_text().strip())
            except Exception:
                pass

            stale.append({
                "session_type": session_type,
                "age_seconds": int(age),
                "age_minutes": round(age / 60, 1),
                "pid": pid,
                "lock_file": str(lock_file),
            })
    return stale


def restart_operator() -> bool:
    """Restart the operator session."""
    global last_operator_restart

    # Cooldown check
    if (datetime.now() - last_operator_restart).total_seconds() < OPERATOR_RESTART_COOLDOWN:
        logger.info("Operator restart on cooldown, skipping")
        return False

    logger.warning("Restarting operator session")

    # Write handoff context from last operator log
    _write_handoff()

    # Launch via scheduler
    result = subprocess.run(
        [str(SCRIPTS_DIR / "athena_scheduler.sh"), "operator-start"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )

    last_operator_restart = datetime.now()

    if result.returncode == 0:
        logger.info("Operator restart initiated")
        return True
    else:
        logger.error(f"Operator restart failed: {result.stderr}")
        return False


def launch_trade_decision() -> bool:
    """Launch a trade-decision session for trade triggers."""
    logger.info("Launching trade-decision session for triggers")

    result = subprocess.run(
        [str(SCRIPTS_DIR / "athena_scheduler.sh"), "oneshot", "trade-decision"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )

    if result.returncode == 0:
        logger.info("Trade-decision session launched")
        return True
    else:
        logger.error(f"Trade-decision launch failed: {result.stderr}")
        return False


def kill_hung_session(session_type: str, pid: int | None, lock_file: str) -> None:
    """Kill a hung one-shot session."""
    logger.warning(f"Killing hung session: {session_type} (PID {pid})")

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass

    # Remove lock
    try:
        Path(lock_file).unlink(missing_ok=True)
    except Exception:
        pass

    logger.info(f"Hung session {session_type} cleaned up")


def _write_handoff() -> None:
    """Write handoff context from operator log for restart."""
    handoff_file = SCHEDULER_DIR / "handoff.json"
    operator_log = RESULTS_DIR / "logs" / "operator_log.jsonl"
    session_file = RESULTS_DIR / "live" / "operator_session.json"

    handoff = {
        "reason": "operator_crash_recovery",
        "timestamp": datetime.now().isoformat(),
        "last_observations": [],
        "session_context": {},
    }

    # Read last few operator observations
    if operator_log.exists():
        try:
            lines = operator_log.read_text().strip().split("\n")
            for line in lines[-5:]:
                try:
                    handoff["last_observations"].append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass

    # Read session state
    if session_file.exists():
        try:
            with open(session_file) as f:
                handoff["session_context"] = json.load(f)
        except Exception:
            pass

    try:
        with open(handoff_file, "w") as f:
            json.dump(handoff, f, indent=2)
        logger.info("Handoff context written")
    except Exception as e:
        logger.error(f"Error writing handoff: {e}")


def update_health_state(check_result: dict) -> None:
    """Write health check result to health.json."""
    health_file = SCHEDULER_DIR / "health.json"
    try:
        with open(health_file, "w") as f:
            json.dump(check_result, f, indent=2)
    except Exception:
        pass


def run_health_check() -> dict:
    """Run a single health check cycle."""
    logger.info("Running health check...")
    result = {
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "actions_taken": [],
    }

    # 1. Check operator status
    operator_alive = is_operator_alive()
    result["checks"]["operator"] = {"alive": operator_alive}

    if not operator_alive and is_market_hours():
        logger.warning("Operator is dead during market hours")
        if restart_operator():
            result["actions_taken"].append("restarted_operator")

    # 2. Check state.json freshness
    state_status = check_state_freshness()
    result["checks"]["state_freshness"] = state_status

    if not state_status.get("fresh", True):
        logger.warning(f"state.json is stale ({state_status.get('age_minutes', '?')} min old)")

    # 3. Check VIX
    vix_status = check_vix()
    result["checks"]["vix"] = vix_status

    if vix_status.get("critical"):
        logger.warning(f"CRITICAL: VIX at {vix_status['vix']}")
    elif vix_status.get("elevated"):
        logger.info(f"VIX elevated at {vix_status['vix']}")

    # 4. Check trade triggers
    triggers = check_trade_triggers()
    result["checks"]["trade_triggers"] = {"count": len(triggers)}

    if triggers:
        symbols = [t.get("symbol", "") for t in triggers]
        logger.info(f"Trade triggers found: {symbols}")

        # Check if a trade-decision session is already running
        td_lock = SCHEDULER_DIR / "locks" / "trade-decision.lock"
        if not td_lock.exists():
            if launch_trade_decision():
                consume_trade_triggers(symbols)
                result["actions_taken"].append(f"launched_trade_decision:{','.join(symbols)}")
        else:
            logger.info("Trade-decision already running, skipping trigger launch")

    # 5. Check for hung sessions
    stale_locks = check_locks()
    result["checks"]["hung_sessions"] = stale_locks

    for stale in stale_locks:
        kill_hung_session(
            stale["session_type"],
            stale.get("pid"),
            stale["lock_file"],
        )
        result["actions_taken"].append(f"killed_hung:{stale['session_type']}")

    # Update health state file
    update_health_state(result)

    actions = result["actions_taken"]
    if actions:
        logger.info(f"Actions taken: {actions}")
    else:
        logger.info("Health check complete - all OK")

    return result


def main():
    parser = argparse.ArgumentParser(description="Athena Health Monitor")
    parser.add_argument("--once", action="store_true", help="Run single check and exit")
    parser.add_argument("--until", type=str, default="17:05", help="Run until HH:MM (default 17:05)")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="Check interval in seconds")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Athena Health Monitor starting")
    logger.info(f"  Check interval: {args.interval}s")
    logger.info(f"  Run until: {args.until}")
    logger.info("=" * 50)

    if args.once:
        result = run_health_check()
        print(json.dumps(result, indent=2))
        return

    # Parse end time
    end_hour, end_min = map(int, args.until.split(":"))

    check_count = 0
    while running:
        now = datetime.now()

        # Check if past end time
        end_time = now.replace(hour=end_hour, minute=end_min, second=0)
        if now > end_time:
            logger.info(f"Past {args.until}, shutting down")
            break

        # Skip weekends
        if not is_weekday():
            logger.info("Weekend, sleeping 1 hour")
            time.sleep(3600)
            continue

        try:
            run_health_check()
            check_count += 1
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)

        # Sleep until next check
        if running:
            time.sleep(args.interval)

    logger.info(f"Health monitor stopped after {check_count} checks")


if __name__ == "__main__":
    main()
