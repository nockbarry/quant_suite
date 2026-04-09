#!/usr/bin/env python3
"""Athena Sentinel — Python monitoring daemon, zero Claude tokens.

Replaces health_monitor.py. Runs every 30 seconds during market hours.
Maintains situation_board.json and triggers Analyst sessions when events
need LLM interpretation.

Reuses OperatorLoop's check methods for signal/alert detection.
Absorbs health_monitor.py's process management (restart operator, kill hung sessions).

Usage:
    python3 scripts/sentinel.py                # Run until market close
    python3 scripts/sentinel.py --once         # Single check and exit
    python3 scripts/sentinel.py --interval 15  # Override initial interval
    python3 scripts/sentinel.py --until 17:05  # Run until specific time
"""

import argparse
import json
import logging
import os
import signal as signal_mod
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))
LOG_DIR = RESULTS_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SCHEDULER_DIR = RESULTS_DIR / "scheduler"
TMUX_SESSION = f"athena-{os.environ.get('ATHENA_INSTANCE', 'auto')}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sentinel] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"sentinel_{datetime.now():%Y%m%d}.log"),
    ],
)
logger = logging.getLogger(__name__)

# Import swarm modules
from src.swarm.situation_board import SituationBoard
from src.monitoring.operator_loop import OperatorLoop
from src.intelligence.adaptive_triggers import AdaptiveTriggerEngine

# ---- Health Monitor Functions (absorbed from health_monitor.py) ----

ONESHOT_TIMEOUT = 15 * 60  # 15 minutes
OPERATOR_RESTART_COOLDOWN = 300  # 5 minutes
STATE_STALE_THRESHOLD = 15 * 60  # 15 minutes
TRADE_DECISION_COOLDOWN = 30 * 60  # 30 minutes between trade-decision launches
OPERATOR_BACKOFF_THRESHOLD = 3  # restarts before engaging backoff
OPERATOR_BACKOFF_WINDOW = 3600  # 1 hour window to count restarts
OPERATOR_BACKOFF_DELAY = 900  # 15 minute backoff when threshold hit

# Persistent cooldown file — survives sentinel restarts (fixes runaway session bug)
COOLDOWN_FILE = SCHEDULER_DIR / "sentinel_cooldowns.json"


def _load_cooldowns() -> dict:
    """Load cooldown timestamps from disk."""
    try:
        if COOLDOWN_FILE.exists():
            data = json.loads(COOLDOWN_FILE.read_text())
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_cooldowns(data: dict) -> None:
    """Save cooldown timestamps to disk."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_FILE.write_text(json.dumps(data))
    except OSError as e:
        logger.error(f"Failed to save cooldowns: {e}")


def _get_cooldown_time(key: str) -> datetime:
    """Get a persisted cooldown timestamp."""
    data = _load_cooldowns()
    ts = data.get(key)
    if ts:
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            pass
    return datetime.min


def _set_cooldown_time(key: str, when: datetime = None) -> None:
    """Set a persisted cooldown timestamp."""
    data = _load_cooldowns()
    data[key] = (when or datetime.now()).isoformat()
    _save_cooldowns(data)


def _get_operator_restart_count() -> int:
    """Count operator restarts within the backoff window."""
    data = _load_cooldowns()
    restarts = data.get("operator_restart_history", [])
    cutoff = (datetime.now() - timedelta(seconds=OPERATOR_BACKOFF_WINDOW)).isoformat()
    return len([t for t in restarts if t > cutoff])


def _record_operator_restart() -> None:
    """Record an operator restart for backoff tracking."""
    data = _load_cooldowns()
    restarts = data.get("operator_restart_history", [])
    restarts.append(datetime.now().isoformat())
    # Keep only last hour of history
    cutoff = (datetime.now() - timedelta(seconds=OPERATOR_BACKOFF_WINDOW)).isoformat()
    data["operator_restart_history"] = [t for t in restarts if t > cutoff]
    _save_cooldowns(data)


# Initialize from persisted state (survives restarts)
last_operator_restart = _get_cooldown_time("last_operator_restart")
last_trade_decision_launch = _get_cooldown_time("last_trade_decision_launch")


def tmux_session_exists() -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


def is_operator_alive() -> bool:
    """Check if the operator has a running claude process via lock file PID."""
    if not tmux_session_exists():
        return False

    lock_file = SCHEDULER_DIR / "locks" / "operator.lock"
    if not lock_file.exists():
        return False

    try:
        pid = int(lock_file.read_text().strip())
    except (ValueError, OSError):
        return False

    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return False
        state = result.stdout.strip()
        if state and state[0] in ("T", "Z"):
            return False
        return True
    except Exception:
        return False


def check_locks() -> list[dict]:
    """Check for stale lock files (hung sessions)."""
    lock_dir = SCHEDULER_DIR / "locks"
    if not lock_dir.exists():
        return []

    stale = []
    for lock_file in lock_dir.glob("*.lock"):
        age = time.time() - lock_file.stat().st_mtime
        session_type = lock_file.stem
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
                "pid": pid,
                "lock_file": str(lock_file),
            })
    return stale


def restart_operator() -> bool:
    """Restart the operator session via athena_scheduler.sh.

    Includes exponential backoff: if operator has been restarted 3+ times
    in the last hour, wait 15 minutes before next attempt. This prevents
    tight restart loops when the API is rate-limited or returning 500s.
    """
    global last_operator_restart
    if (datetime.now() - last_operator_restart).total_seconds() < OPERATOR_RESTART_COOLDOWN:
        logger.info("Operator restart on cooldown, skipping")
        return False

    # Backoff: if restarted too many times recently, extend cooldown
    recent_restarts = _get_operator_restart_count()
    if recent_restarts >= OPERATOR_BACKOFF_THRESHOLD:
        last_restart_age = (datetime.now() - last_operator_restart).total_seconds()
        if last_restart_age < OPERATOR_BACKOFF_DELAY:
            remaining = int(OPERATOR_BACKOFF_DELAY - last_restart_age)
            logger.warning(
                f"Operator restart backoff engaged ({recent_restarts} restarts in last hour). "
                f"Waiting {remaining}s before next attempt."
            )
            return False

    logger.warning("Restarting operator session")
    result = subprocess.run(
        [str(SCRIPTS_DIR / "athena_scheduler.sh"), "operator-start"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )
    last_operator_restart = datetime.now()
    _set_cooldown_time("last_operator_restart", last_operator_restart)
    _record_operator_restart()

    if result.returncode == 0:
        logger.info("Operator restart initiated")
        return True
    else:
        logger.error(f"Operator restart failed: {result.stderr}")
        return False


def kill_hung_session(session_type: str, pid: int | None, lock_file: str) -> None:
    """Kill a hung one-shot session."""
    logger.warning(f"Killing hung session: {session_type} (PID {pid})")
    if pid:
        try:
            os.kill(pid, signal_mod.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, signal_mod.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
    try:
        Path(lock_file).unlink(missing_ok=True)
    except Exception:
        pass
    logger.info(f"Hung session {session_type} cleaned up")


def launch_trade_decision() -> bool:
    """Launch a trade-decision session for trade triggers."""
    logger.info("Launching trade-decision session for triggers")
    result = subprocess.run(
        [str(SCRIPTS_DIR / "athena_scheduler.sh"), "oneshot", "trade-decision"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )
    if result.returncode == 0:
        logger.info("Trade-decision session launched")
        return True
    else:
        logger.error(f"Trade-decision launch failed: {result.stderr}")
        return False


def launch_analyst() -> bool:
    """Launch an analyst session for pending analyses."""
    lock_file = SCHEDULER_DIR / "locks" / "analyst.lock"
    if lock_file.exists():
        logger.info("Analyst already running, skipping")
        return False

    logger.info("Launching analyst session")
    result = subprocess.run(
        [str(SCRIPTS_DIR / "athena_scheduler.sh"), "oneshot", "analyst"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )
    if result.returncode == 0:
        logger.info("Analyst session launched")
        return True
    else:
        logger.error(f"Analyst launch failed: {result.stderr}")
        return False


def check_trade_triggers() -> list[dict]:
    """Check for unconsumed trade triggers."""
    triggers_file = SCHEDULER_DIR / "trade_triggers.json"
    if not triggers_file.exists():
        return []
    try:
        with open(triggers_file) as f:
            data = json.load(f)
        return [t for t in data.get("triggers", []) if not t.get("consumed", False)]
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


def is_market_hours() -> bool:
    now = datetime.now()
    start = now.replace(hour=5, minute=55, second=0, microsecond=0)
    end = now.replace(hour=17, minute=5, second=0, microsecond=0)
    return start <= now <= end


def is_weekday() -> bool:
    return datetime.now().weekday() < 5


# ---- Sentinel Core ----

class Sentinel:
    """Python monitoring daemon that maintains the situation board and triggers agents.

    Reuses OperatorLoop's check methods for all signal/alert detection.
    Runs at regime-adaptive intervals (10-60 seconds based on VIX).
    """

    def __init__(self, interval: int = 30):
        self.interval = interval
        self.board = SituationBoard.load_or_create()
        self.operator = OperatorLoop()
        self.last_vix: float | None = None
        self.last_convergence_symbols: set[str] = set()
        self._seen_mover_symbols: set[str] = set()
        self.last_news_count: int = 0
        self.check_count = 0
        self.logged_alert_titles: set[str] = set()  # Track which alert types have been logged
        self._last_analyst_launch: float = 0  # Cooldown: min 5 min between analyst launches
        self._analyst_trigger_keys: set[str] = set()  # Dedup triggers within a day
        self._logged_signposts_today: set[str] = set()  # Daily dedup: signpost text → logged once per day

    def run_check(self) -> dict:
        """Run a single sentinel check cycle.

        Returns dict with check results summary.
        """
        self.check_count += 1
        start = time.time()

        # Reload board (another session may have written to it)
        self.board = SituationBoard.load_or_create()

        # 1. Load state and update board market snapshot
        state = self.operator._load_state()
        self.board.update_market_snapshot(state)
        self.board.update_portfolio_alerts(state)

        # Update regime context
        regime = state.get("market", {}).get("rotation_theme", "unknown")
        vix = state.get("market", {}).get("vix", 0)
        interpretation = ""
        if vix > 30:
            interpretation = "High volatility. Crisis mode — focus on position management."
        elif vix > 25:
            interpretation = "Elevated volatility. Geopolitical/macro driven. Favors defensive."
        elif vix < 15:
            interpretation = "Low volatility. Risk-on environment."
        self.board.update_regime_context(regime, interpretation)

        # 2. Check signals via operator's existing methods
        alerts = self.operator._check_alerts(state)
        signposts = self.operator._check_signposts()
        convergences = self.operator._check_convergences()
        stale_sources = self.operator._check_data_freshness()
        social = self.operator._check_social_signals()

        # 3. Check session health
        operator_alive = is_operator_alive()
        stale_locks = check_locks()

        # 4. Check trade triggers
        trade_triggers = check_trade_triggers()

        # 5. Evaluate trigger rules for analyst
        triggers_fired = self._evaluate_triggers(
            alerts=alerts,
            signposts=signposts,
            convergences=convergences,
            social=social,
            state=state,
        )

        # 6. Queue analysis requests and spawn analyst if needed
        if triggers_fired:
            # Dedup: only queue triggers we haven't seen today
            new_triggers = []
            for trigger in triggers_fired:
                key = f"{trigger['type']}:{','.join(sorted(trigger.get('symbols', [])))}"
                if key not in self._analyst_trigger_keys:
                    self._analyst_trigger_keys.add(key)
                    new_triggers.append(trigger)

            for trigger in new_triggers:
                self.board.add_analysis_request(
                    trigger=trigger["type"],
                    context=trigger["context"],
                )
                self.board.add_observation(
                    source="sentinel",
                    obs_type="trigger",
                    text=f"[{trigger['type']}] {trigger['context'][:100]}",
                    symbols=trigger.get("symbols", []),
                )

            # Cooldown: min 5 minutes between analyst launches
            if new_triggers and (time.time() - self._last_analyst_launch) > 300:
                if launch_analyst():
                    self._last_analyst_launch = time.time()

        # 7. Handle trade triggers (from operator or other sessions)
        #    Cooldown: max 1 trade-decision launch per 30 minutes from triggers
        if trade_triggers:
            global last_trade_decision_launch
            symbols = [t.get("symbol", "") for t in trade_triggers]
            td_lock = SCHEDULER_DIR / "locks" / "trade-decision.lock"
            cooldown_ok = (datetime.now() - last_trade_decision_launch).total_seconds() > TRADE_DECISION_COOLDOWN
            if not td_lock.exists() and cooldown_ok:
                if launch_trade_decision():
                    consume_trade_triggers(symbols)
                    last_trade_decision_launch = datetime.now()
                    _set_cooldown_time("last_trade_decision_launch", last_trade_decision_launch)
            elif not cooldown_ok:
                logger.debug(f"Trade-decision on cooldown, {int(TRADE_DECISION_COOLDOWN - (datetime.now() - last_trade_decision_launch).total_seconds())}s remaining")

        # 7b. Adaptive triggers (portfolio drawdown, VIX extreme, crash loop, etc.)
        #     Respect global trade-decision cooldown for trade-decision triggers
        adaptive_triggers_fired = []
        try:
            adaptive = AdaptiveTriggerEngine()
            adaptive_events = adaptive.evaluate_all()
            for trigger in adaptive_events:
                # Skip trade-decision triggers if on global cooldown
                if trigger.session_to_spawn == "trade-decision":
                    td_lock = SCHEDULER_DIR / "locks" / "trade-decision.lock"
                    td_cooldown_ok = (datetime.now() - last_trade_decision_launch).total_seconds() > TRADE_DECISION_COOLDOWN
                    if td_lock.exists() or not td_cooldown_ok:
                        logger.info(f"ADAPTIVE TRIGGER [{trigger.level}] {trigger.description} — skipped (trade-decision on cooldown)")
                        continue
                logger.warning(f"ADAPTIVE TRIGGER: [{trigger.level}] {trigger.description}")
                adaptive.fire_trigger(trigger)
                adaptive_triggers_fired.append(trigger.trigger_type)
                if trigger.session_to_spawn == "trade-decision":
                    last_trade_decision_launch = datetime.now()
                    _set_cooldown_time("last_trade_decision_launch", last_trade_decision_launch)
        except Exception as e:
            logger.error(f"Adaptive trigger check failed: {e}", exc_info=True)

        # 8. Health actions
        # Only restart operator AFTER 8:30 AM — before that, the 8:30 cron handles
        # the initial launch. Restarting too early causes "stale task" when the
        # cron tries to launch at 8:30.
        actions_taken = []
        now_hour = datetime.now().hour
        now_min = datetime.now().minute
        operator_should_be_running = (now_hour > 8 or (now_hour == 8 and now_min >= 35))
        if not operator_alive and is_market_hours() and operator_should_be_running:
            if restart_operator():
                actions_taken.append("restarted_operator")

        for stale in stale_locks:
            kill_hung_session(stale["session_type"], stale.get("pid"), stale["lock_file"])
            actions_taken.append(f"killed_hung:{stale['session_type']}")

        # 9. Log alerts to board (only first occurrence of each alert type per session)
        for alert in alerts:
            if alert.level == "critical":
                # Always log critical alerts
                self.board.add_observation(
                    source="sentinel",
                    obs_type="alert",
                    text=f"[{alert.level}] {alert.title}: {alert.message}",
                    symbols=[alert.symbol] if alert.symbol else [],
                )
            elif alert.level == "warning" and alert.title not in self.logged_alert_titles:
                # Log warning alerts only once per sentinel session
                self.logged_alert_titles.add(alert.title)
                self.board.add_observation(
                    source="sentinel",
                    obs_type="alert",
                    text=f"[{alert.level}] {alert.title}: {alert.message}",
                    symbols=[alert.symbol] if alert.symbol else [],
                )

        # 10. Log signpost triggers to board (daily dedup — fire once per signpost text per day)
        for sp in signposts:
            sp_key = f"{sp.thesis_name}|{sp.signpost_description}|{sp.outcome}"
            if sp_key not in self._logged_signposts_today:
                self._logged_signposts_today.add(sp_key)
                self.board.add_observation(
                    source="sentinel",
                    obs_type="signpost",
                    text=f"Signpost triggered: {sp.thesis_name} — {sp.signpost_description} ({sp.outcome})",
                    thesis=sp.thesis_name,
                )

        # 11. Save board
        self.board.save()

        # 12. Update tracking state
        self.last_vix = vix
        current_convergence_symbols = {c.get("symbol", "") for c in convergences}
        self.last_convergence_symbols = current_convergence_symbols

        # 13. Adapt interval based on regime
        self._adapt_interval(state)

        # 14. Write health state (backward compat with health.json readers)
        duration = time.time() - start
        health_result = {
            "timestamp": datetime.now().isoformat(),
            "check_number": self.check_count,
            "duration_seconds": round(duration, 2),
            "interval": self.interval,
            "checks": {
                "operator": {"alive": operator_alive},
                "state_freshness": {
                    "fresh": (time.time() - (self.operator.live_dir / "state.json").stat().st_mtime < STATE_STALE_THRESHOLD)
                    if (self.operator.live_dir / "state.json").exists() else False,
                },
                "vix": {"vix": vix, "elevated": vix > 25, "critical": vix > 30},
                "convergences": len(convergences),
                "alerts": len(alerts),
                "signposts": len(signposts),
                "stale_sources": stale_sources,
                "trade_triggers": len(trade_triggers),
            },
            "triggers_fired": [t["type"] for t in triggers_fired],
            "adaptive_triggers_fired": adaptive_triggers_fired,
            "actions_taken": actions_taken,
        }

        try:
            health_file = SCHEDULER_DIR / "health.json"
            with open(health_file, "w") as f:
                json.dump(health_result, f, indent=2)
        except Exception:
            pass

        # Log summary
        summary_parts = []
        if alerts:
            summary_parts.append(f"{len(alerts)} alerts")
        if convergences:
            summary_parts.append(f"{len(convergences)} convergences")
        if signposts:
            summary_parts.append(f"{len(signposts)} signposts")
        if triggers_fired:
            summary_parts.append(f"{len(triggers_fired)} triggers fired")
        if adaptive_triggers_fired:
            summary_parts.append(f"{len(adaptive_triggers_fired)} adaptive triggers: {', '.join(adaptive_triggers_fired)}")
        if actions_taken:
            summary_parts.append(f"actions: {actions_taken}")

        if summary_parts:
            logger.info(f"Check #{self.check_count}: {', '.join(summary_parts)}")
        else:
            logger.info(f"Check #{self.check_count}: all clear (VIX={vix:.1f}, interval={self.interval}s)")

        return {
            "check": self.check_count,
            "triggers": len(triggers_fired),
            "adaptive_triggers": len(adaptive_triggers_fired),
            "alerts": len(alerts),
            "convergences": len(convergences),
            "signposts": len(signposts),
            "actions": actions_taken,
            "interval": self.interval,
        }

    def _evaluate_triggers(
        self,
        alerts: list,
        signposts: list,
        convergences: list[dict],
        social: list[dict],
        state: dict,
    ) -> list[dict]:
        """Evaluate trigger rules to decide if we need an Analyst session.

        Returns list of triggered rules with context.
        """
        fired = []
        vix = state.get("market", {}).get("vix", 0)

        # 1. New convergences (3+ signals on a symbol we haven't seen)
        for conv in convergences:
            symbol = conv.get("symbol", "")
            count = conv.get("signal_count", 0)
            if count >= 3 and symbol not in self.last_convergence_symbols:
                signals = conv.get("signals", [])
                signal_names = [s.get("source", "?") for s in signals] if isinstance(signals, list) else []
                fired.append({
                    "type": "convergence",
                    "context": f"{symbol}: {count} signals aligned ({', '.join(signal_names[:5])})",
                    "symbols": [symbol],
                })

        # 2. Signpost triggers
        for sp in signposts:
            fired.append({
                "type": "signpost_hit",
                "context": f"{sp.thesis_name}: {sp.signpost_description} ({sp.outcome})",
                "symbols": [],
            })

        # 3. Critical position alerts
        for alert in alerts:
            if alert.level == "critical" and alert.source == "position":
                fired.append({
                    "type": "position_alert",
                    "context": f"{alert.title}: {alert.message}",
                    "symbols": [alert.symbol] if alert.symbol else [],
                })

        # 4. VIX spike (>3 points from last check)
        if self.last_vix is not None and (vix - self.last_vix) > 3:
            fired.append({
                "type": "vix_spike",
                "context": f"VIX spiked from {self.last_vix:.1f} to {vix:.1f} ({vix - self.last_vix:+.1f})",
                "symbols": [],
            })

        # 5. Regime change
        current_regime = state.get("market", {}).get("rotation_theme", "unknown")
        if (self.operator.last_regime != "unknown" and
                current_regime != self.operator.last_regime):
            fired.append({
                "type": "regime_change",
                "context": f"Regime changed: {self.operator.last_regime} → {current_regime}",
                "symbols": [],
            })

        # 6. Urgent news
        try:
            news_file = RESULTS_DIR / "live" / "news_cache.json"
            if news_file.exists():
                with open(news_file) as f:
                    news_data = json.load(f)
                urgent = [
                    n for n in news_data.get("items", [])
                    if n.get("is_urgent")
                ]
                # Only fire if we have new urgent items
                if len(urgent) > self.last_news_count and self.last_news_count > 0:
                    new_urgent = urgent[:3]
                    headlines = [n.get("headline", "?")[:80] for n in new_urgent]
                    fired.append({
                        "type": "urgent_news",
                        "context": f"{len(urgent) - self.last_news_count} new urgent headlines: {'; '.join(headlines)}",
                        "symbols": [s for n in new_urgent for s in n.get("symbols", [])],
                    })
                self.last_news_count = len(urgent)
        except Exception:
            pass

        # 7. Market movers with high context + thesis alignment
        try:
            movers_file = RESULTS_DIR / "live" / "market_movers_latest.json"
            if movers_file.exists():
                with open(movers_file) as f:
                    movers_data = json.load(f)
                for mover in movers_data.get("top_context", [])[:10]:
                    sym = mover.get("symbol", "")
                    ctx = mover.get("context_score", 0)
                    thesis = mover.get("thesis_alignment")
                    if (ctx >= 0.3 and thesis
                            and sym not in self._seen_mover_symbols):
                        fired.append({
                            "type": "market_mover",
                            "context": (
                                f"{sym}: {mover.get('change_1d_pct', 0):+.1f}% day, "
                                f"ctx={ctx:.0%}, "
                                f"thesis={thesis.get('thesis_name', '?')}"
                            ),
                            "symbols": [sym],
                        })
                        self._seen_mover_symbols.add(sym)
        except Exception:
            pass

        return fired

    def _adapt_interval(self, state: dict):
        """Regime-adaptive check interval based on VIX."""
        vix = state.get("market", {}).get("vix", 15)
        if vix > 35:
            self.interval = 10  # Crisis mode
        elif vix > 25:
            self.interval = 15  # Elevated
        elif vix < 15:
            self.interval = 60  # Low vol
        else:
            self.interval = 30  # Normal


# ---- Main Loop ----

running = True


def signal_handler(sig, frame):
    global running
    logger.info("Received shutdown signal, stopping...")
    running = False


signal_mod.signal(signal_mod.SIGINT, signal_handler)
signal_mod.signal(signal_mod.SIGTERM, signal_handler)


def main():
    parser = argparse.ArgumentParser(description="Athena Sentinel")
    parser.add_argument("--once", action="store_true", help="Run single check and exit")
    parser.add_argument("--until", type=str, default="17:05", help="Run until HH:MM (default 17:05)")
    parser.add_argument("--interval", type=int, default=30, help="Initial check interval in seconds")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Athena Sentinel starting")
    logger.info(f"  Initial interval: {args.interval}s (adapts to VIX)")
    logger.info(f"  Run until: {args.until}")
    logger.info("=" * 50)

    sentinel = Sentinel(interval=args.interval)

    if args.once:
        result = sentinel.run_check()
        print(json.dumps(result, indent=2))
        return

    # Parse end time
    end_hour, end_min = map(int, args.until.split(":"))

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
            sentinel.run_check()
        except Exception as e:
            logger.error(f"Sentinel check error: {e}", exc_info=True)

        # Sleep with regime-adaptive interval
        if running:
            time.sleep(sentinel.interval)

    logger.info(f"Sentinel stopped after {sentinel.check_count} checks")


if __name__ == "__main__":
    main()
