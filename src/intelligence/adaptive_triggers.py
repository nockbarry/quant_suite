"""Adaptive Trigger Engine.

Evaluates market conditions, portfolio state, and system health to determine
when unscheduled sessions should fire. Extends the sentinel's trigger pattern
to heavier session types.

Trigger levels:
- ALERT: Spawn analyst session (already exists in sentinel, 5 min Sonnet)
- ELEVATED: Spawn immediate trade-decision (10 min Opus)
- CRITICAL: Spawn emergency system-review (15 min Opus)
- EMERGENCY: Spawn immediate auto-corrections + stress test

Each trigger has a cooldown to prevent spam.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    """An event that should trigger an unscheduled session."""
    trigger_id: str
    timestamp: str
    level: str  # "alert", "elevated", "critical", "emergency"
    trigger_type: str  # See TRIGGER_RULES
    description: str
    session_to_spawn: str  # "analyst", "trade-decision", "system-review", "auto-corrections"
    symbols: list[str]
    data: dict  # Supporting evidence
    cooldown_hours: float  # Don't re-trigger within this window
    fired: bool = False


# Trigger definitions with conditions and responses
TRIGGER_RULES = {
    # === PORTFOLIO TRIGGERS ===
    "portfolio_drawdown_3pct": {
        "description": "Portfolio down 3%+ today",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 4,
        "check": "portfolio_drawdown",
        "threshold": -3.0,
    },
    "portfolio_drawdown_5pct": {
        "description": "Portfolio down 5%+ today -- emergency review",
        "level": "critical",
        "session": "system-review",
        "cooldown_hours": 8,
        "check": "portfolio_drawdown",
        "threshold": -5.0,
    },
    "position_stop_hit": {
        "description": "Position hit -15% stop loss",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 1,
        "check": "position_stop",
        "threshold": -15.0,
    },

    # === MARKET TRIGGERS ===
    "vix_spike_10pct": {
        "description": "VIX spiked 10%+ in one session",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 4,
        "check": "vix_spike",
        "threshold": 10.0,
    },
    "vix_extreme_35": {
        "description": "VIX above 35 -- extreme fear",
        "level": "critical",
        "session": "trade-decision",
        "cooldown_hours": 8,
        "check": "vix_level",
        "threshold": 35.0,
    },
    "oil_crash_10pct": {
        "description": "Oil (BNO/USO) dropped 10%+ -- ceasefire signal?",
        "level": "critical",
        "session": "system-review",
        "cooldown_hours": 8,
        "check": "commodity_crash",
        "threshold": -10.0,
        "symbols": ["BNO", "USO"],
    },

    # === SIGNAL TRIGGERS ===
    "red_flag_cluster": {
        "description": "3+ red flags from cross-reference engine",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 4,
        "check": "red_flag_count",
        "threshold": 3,
    },
    "insider_selling_cluster": {
        "description": "3+ insiders selling portfolio stocks in 24h",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 8,
        "check": "insider_selling",
        "threshold": 3,
    },

    # === THESIS TRIGGERS ===
    "thesis_invalidated": {
        "description": "Thesis auto-invalidated by belief updater (conviction < 25%)",
        "level": "elevated",
        "session": "trade-decision",
        "cooldown_hours": 4,
        "check": "thesis_conviction_low",
        "threshold": 25.0,
    },
    "conviction_velocity_extreme": {
        "description": "Conviction velocity > 5pp/day on major thesis",
        "level": "alert",
        "session": "analyst",
        "cooldown_hours": 8,
        "check": "conviction_velocity",
        "threshold": 5.0,
    },
    "thesis_review_overdue": {
        "description": "Thesis review overdue by 7+ days — spawn thesis review session",
        "level": "alert",
        "session": "thesis",
        "cooldown_hours": 24,
        "check": "thesis_review_overdue",
        "threshold": 7,
    },

    # === SYSTEM TRIGGERS ===
    "crash_loop_detected": {
        "description": "Same error 5+ times in 1 hour",
        "level": "critical",
        "session": "system-review",
        "cooldown_hours": 12,
        "check": "error_frequency",
        "threshold": 5,
    },
    "ensemble_rejection_streak": {
        "description": "3+ consecutive trade decisions rejected by ensemble",
        "level": "elevated",
        "session": "system-review",
        "cooldown_hours": 24,
        "check": "ensemble_rejections",
        "threshold": 3,
    },
    "instance_divergence_extreme": {
        "description": "Instance equity spread > 15% -- one instance may be broken",
        "level": "critical",
        "session": "system-review",
        "cooldown_hours": 24,
        "check": "instance_divergence",
        "threshold": 15.0,
    },
}


class AdaptiveTriggerEngine:
    """Evaluates conditions and fires unscheduled sessions."""

    TRIGGER_LOG = paths.base / "logs" / "adaptive_triggers.jsonl"
    COOLDOWN_FILE = paths.base / "scheduler" / "trigger_cooldowns.json"

    def __init__(self):
        self.cooldowns = self._load_cooldowns()

    def evaluate_all(self) -> list[TriggerEvent]:
        """Check all trigger conditions against current state.
        Returns list of triggers that should fire."""

        triggers = []
        state = self._load_state()

        for rule_name, rule in TRIGGER_RULES.items():
            if self._in_cooldown(rule_name):
                continue

            event = self._check_rule(rule_name, rule, state)
            if event:
                triggers.append(event)

        return triggers

    def _check_rule(self, rule_name: str, rule: dict, state: dict) -> Optional[TriggerEvent]:
        """Check a single rule against current state."""
        check_type = rule["check"]
        threshold = rule["threshold"]

        try:
            if check_type == "portfolio_drawdown":
                return self._check_portfolio_drawdown(rule_name, rule, state, threshold)

            elif check_type == "position_stop":
                return self._check_position_stop(rule_name, rule, state, threshold)

            elif check_type == "vix_spike":
                return self._check_vix_spike(rule_name, rule, state, threshold)

            elif check_type == "vix_level":
                return self._check_vix_level(rule_name, rule, state, threshold)

            elif check_type == "commodity_crash":
                return self._check_commodity_crash(rule_name, rule, state, threshold)

            elif check_type == "red_flag_count":
                return self._check_red_flag_count(rule_name, rule, state, threshold)

            elif check_type == "insider_selling":
                return self._check_insider_selling(rule_name, rule, state, threshold)

            elif check_type == "thesis_conviction_low":
                return self._check_thesis_conviction_low(rule_name, rule, state, threshold)

            elif check_type == "conviction_velocity":
                return self._check_conviction_velocity(rule_name, rule, state, threshold)

            elif check_type == "thesis_review_overdue":
                return self._check_thesis_review_overdue(rule_name, rule, state, threshold)

            elif check_type == "error_frequency":
                return self._check_error_frequency(rule_name, rule, state, threshold)

            elif check_type == "ensemble_rejections":
                return self._check_ensemble_rejections(rule_name, rule, state, threshold)

            elif check_type == "instance_divergence":
                return self._check_instance_divergence(rule_name, rule, state, threshold)

        except Exception as e:
            logger.error(f"Trigger check {rule_name} failed: {e}")
            return None

        return None  # Unknown check type

    # ---- Portfolio Checks ----

    def _check_portfolio_drawdown(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check day P&L percentage against threshold."""
        portfolio = state.get("portfolio", {}).get("portfolio", {})
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)

        if day_pnl_pct is None:
            return None

        # On a split ex-date the day-P&L is untrustworthy (rebased prices) —
        # the daemon zeroes it at source, but suppress here too in case this
        # reads a snapshot written before the guard ran. Logged loudly.
        try:
            from src.data.corporate_actions import todays_splits

            splits = todays_splits()
            if splits and day_pnl_pct <= threshold:
                logger.warning(
                    f"SUPPRESSED {rule_name}: day_pnl_pct={day_pnl_pct:.2f}% on split "
                    f"ex-date for {sorted(splits)} — P&L not trustworthy today"
                )
                return None
        except Exception:
            pass

        if day_pnl_pct <= threshold:
            equity = portfolio.get("equity", 0)
            day_pnl = portfolio.get("day_pnl", 0)
            trigger = self._create_trigger(
                rule_name, rule,
                f"Day P&L: {day_pnl_pct:.2f}% (${day_pnl:,.0f} on ${equity:,.0f})"
            )
            trigger.data = {
                "day_pnl_pct": day_pnl_pct,
                "day_pnl": day_pnl,
                "equity": equity,
            }
            return trigger
        return None

    def _check_position_stop(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check if any position hit the stop loss threshold."""
        positions = state.get("portfolio", {}).get("positions", [])
        stopped_positions = []

        for pos in positions:
            unrealized_pnl_pct = pos.get("unrealized_pnl_pct", 0)
            if unrealized_pnl_pct is None:
                continue
            if unrealized_pnl_pct <= threshold:
                stopped_positions.append({
                    "symbol": pos.get("symbol", "UNK"),
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "market_value": pos.get("market_value", 0),
                    "thesis_id": pos.get("thesis_id", ""),
                })

        if stopped_positions:
            symbols = [p["symbol"] for p in stopped_positions]
            details = ", ".join(
                f"{p['symbol']} at {p['unrealized_pnl_pct']:.1f}%"
                for p in stopped_positions
            )
            trigger = self._create_trigger(
                rule_name, rule,
                f"{len(stopped_positions)} position(s) hit stop: {details}"
            )
            trigger.symbols = symbols
            trigger.data = {"stopped_positions": stopped_positions}
            return trigger
        return None

    # ---- Market Checks ----

    def _check_vix_spike(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check if VIX spiked by threshold% from stored previous value."""
        portfolio_data = state.get("portfolio", {})
        market = portfolio_data.get("market", {})
        vix = market.get("vix", 0)

        if not vix or vix == 0:
            return None

        # Load previous VIX from cooldown/state file
        prev_vix = self.cooldowns.get("_vix_prev", None)
        # Always store current VIX for next check
        self.cooldowns["_vix_prev"] = vix
        self._save_cooldowns()

        if prev_vix is None or prev_vix == 0:
            return None

        pct_change = ((vix - prev_vix) / prev_vix) * 100

        if pct_change >= threshold:
            trigger = self._create_trigger(
                rule_name, rule,
                f"VIX spiked {pct_change:.1f}% ({prev_vix:.1f} -> {vix:.1f})"
            )
            trigger.data = {
                "vix_current": vix,
                "vix_previous": prev_vix,
                "change_pct": pct_change,
            }
            return trigger
        return None

    def _check_vix_level(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check absolute VIX level."""
        portfolio_data = state.get("portfolio", {})
        market = portfolio_data.get("market", {})
        vix = market.get("vix", 0)

        if vix and vix >= threshold:
            trigger = self._create_trigger(
                rule_name, rule,
                f"VIX at {vix:.1f} (threshold: {threshold})"
            )
            trigger.data = {"vix": vix}
            return trigger
        return None

    def _check_commodity_crash(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check if commodity ETFs (BNO, USO) dropped by threshold%."""
        positions = state.get("portfolio", {}).get("positions", [])
        target_symbols = rule.get("symbols", ["BNO", "USO"])
        crashed = []

        for pos in positions:
            symbol = pos.get("symbol", "")
            if symbol in target_symbols:
                day_pnl_pct = pos.get("day_pnl_pct", 0)
                if day_pnl_pct is not None and day_pnl_pct <= threshold:
                    crashed.append({
                        "symbol": symbol,
                        "day_pnl_pct": day_pnl_pct,
                    })

        if crashed:
            details = ", ".join(
                f"{c['symbol']} {c['day_pnl_pct']:.1f}%"
                for c in crashed
            )
            trigger = self._create_trigger(
                rule_name, rule,
                f"Commodity crash: {details}"
            )
            trigger.symbols = [c["symbol"] for c in crashed]
            trigger.data = {"crashed_commodities": crashed}
            return trigger
        return None

    # ---- Signal Checks ----

    def _check_red_flag_count(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Count red flags from cross-reference alerts within last 4 hours."""
        alerts_data = state.get("alerts", {})
        alerts = []
        if isinstance(alerts_data, dict):
            alerts = alerts_data.get("alerts", [])
        elif isinstance(alerts_data, list):
            alerts = alerts_data

        cutoff = (datetime.now() - timedelta(hours=4)).isoformat()
        recent_red_flags = []

        for alert in alerts:
            if alert.get("severity") != "red_flag":
                continue
            alert_ts = alert.get("timestamp", "")
            # If no timestamp or timestamp is recent enough
            if not alert_ts or alert_ts >= cutoff:
                recent_red_flags.append({
                    "title": alert.get("title", ""),
                    "symbols": alert.get("symbols", []),
                    "type": alert.get("type", ""),
                })

        if len(recent_red_flags) >= threshold:
            all_symbols = []
            for rf in recent_red_flags:
                all_symbols.extend(rf.get("symbols", []))
            trigger = self._create_trigger(
                rule_name, rule,
                f"{len(recent_red_flags)} red flags in last 4h"
            )
            trigger.symbols = list(set(all_symbols))
            trigger.data = {"red_flags": recent_red_flags[:10]}
            return trigger
        return None

    def _check_insider_selling(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Count insider sales of portfolio stocks within 24h from SEC data."""
        sec_data = state.get("sec_insider", {})
        if not sec_data:
            return None

        # SEC insider data can be in 'alerts' or 'transactions' key
        transactions = sec_data.get("alerts", sec_data.get("transactions", []))
        if not isinstance(transactions, list):
            return None

        # Get portfolio symbols
        positions = state.get("portfolio", {}).get("positions", [])
        portfolio_symbols = {pos.get("symbol", "") for pos in positions}

        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        selling_count = 0
        selling_details = []

        for txn in transactions:
            # Check if it's a sale
            txn_type = (txn.get("transaction_type", "") or txn.get("type", "")).upper()
            if txn_type not in ("SALE", "S", "SELL"):
                continue

            symbol = txn.get("symbol", "")
            if symbol not in portfolio_symbols:
                continue

            # Check recency
            txn_date = txn.get("date", txn.get("timestamp", ""))
            if txn_date and txn_date < cutoff:
                continue

            selling_count += 1
            selling_details.append({
                "symbol": symbol,
                "insider": txn.get("insider_name", txn.get("name", "Unknown")),
                "value": txn.get("value", ""),
            })

        if selling_count >= threshold:
            symbols = list({d["symbol"] for d in selling_details})
            trigger = self._create_trigger(
                rule_name, rule,
                f"{selling_count} insider sales in portfolio stocks: "
                + ", ".join(f"{d['symbol']} ({d['insider']})" for d in selling_details[:5])
            )
            trigger.symbols = symbols
            trigger.data = {"insider_sales": selling_details}
            return trigger
        return None

    # ---- Thesis Checks ----

    def _check_thesis_conviction_low(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check for active theses with conviction below threshold."""
        # Try state.json theses first (faster, no disk I/O for YAML)
        theses = state.get("portfolio", {}).get("theses", [])
        low_conviction = []

        for thesis in theses:
            conviction = thesis.get("conviction", 100)
            status = thesis.get("status", "active")
            if status == "active" and conviction < threshold:
                low_conviction.append({
                    "name": thesis.get("name", "Unknown"),
                    "id": thesis.get("id", ""),
                    "conviction": conviction,
                })

        # Fallback: load from ThesisTracker if state didn't have theses
        if not theses:
            try:
                from src.knowledge.thesis import ThesisTracker
                tracker = ThesisTracker()
                for thesis in tracker.get_active_theses():
                    if thesis.conviction < threshold:
                        low_conviction.append({
                            "name": thesis.name,
                            "id": thesis.id,
                            "conviction": thesis.conviction,
                        })
            except Exception as e:
                logger.debug(f"ThesisTracker fallback failed: {e}")

        if low_conviction:
            details = ", ".join(
                f"{t['name']} ({t['conviction']:.0f}%)"
                for t in low_conviction
            )
            trigger = self._create_trigger(
                rule_name, rule,
                f"{len(low_conviction)} thesis below {threshold}%: {details}"
            )
            trigger.data = {"low_conviction_theses": low_conviction}
            return trigger
        return None

    def _check_thesis_review_overdue(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check for theses with reviews overdue by threshold days."""
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            overdue = []
            for thesis in tracker.get_active_theses():
                if thesis.next_review and thesis.next_review < datetime.now() - timedelta(days=threshold):
                    days_late = (datetime.now() - thesis.next_review).days
                    overdue.append({
                        "name": thesis.name,
                        "id": thesis.id,
                        "conviction": thesis.conviction,
                        "days_overdue": days_late,
                    })
            if overdue:
                details = "; ".join(
                    f"{t['name']} ({t['days_overdue']}d)" for t in overdue
                )
                trigger = self._make_trigger(
                    rule_name, rule,
                    f"{len(overdue)} theses overdue for review: {details}",
                )
                trigger.data = {"overdue_theses": overdue}
                return trigger
        except Exception as e:
            logger.debug(f"Thesis review overdue check failed: {e}")
        return None

    def _check_conviction_velocity(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check for extreme conviction velocity (pp/day) on major theses."""
        # Conviction velocity can be tracked via conviction_decay in state
        # or from the belief updater's signal_engines data
        signals_data = state.get("signals", {})
        decay_data = state.get("portfolio", {}).get("conviction_decay", [])

        # Check conviction_decay entries for rapid changes
        high_velocity = []

        for entry in decay_data if isinstance(decay_data, list) else []:
            thesis_name = entry.get("name", entry.get("thesis_name", ""))
            # conviction_decay tracks days since review and conviction
            # We look for entries with recent large changes
            velocity = abs(entry.get("velocity_ppd", 0))
            if velocity >= threshold:
                high_velocity.append({
                    "thesis": thesis_name,
                    "velocity": velocity,
                    "direction": "declining" if entry.get("velocity_ppd", 0) < 0 else "rising",
                })

        # Also check signal_engines for velocity signals
        if isinstance(signals_data, dict):
            velocity_signals = signals_data.get("conviction_velocity", [])
            if isinstance(velocity_signals, list):
                for sig in velocity_signals:
                    vel = abs(sig.get("velocity", 0))
                    if vel >= threshold:
                        thesis_name = sig.get("thesis", sig.get("name", ""))
                        if thesis_name and not any(h["thesis"] == thesis_name for h in high_velocity):
                            high_velocity.append({
                                "thesis": thesis_name,
                                "velocity": vel,
                                "direction": "declining" if sig.get("velocity", 0) < 0 else "rising",
                            })

        if high_velocity:
            details = ", ".join(
                f"{h['thesis']} ({h['direction']} {h['velocity']:.1f}pp/day)"
                for h in high_velocity
            )
            trigger = self._create_trigger(
                rule_name, rule,
                f"Extreme conviction velocity: {details}"
            )
            trigger.data = {"high_velocity_theses": high_velocity}
            return trigger
        return None

    # ---- System Checks ----

    def _check_error_frequency(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check bug monitor for crash loops (same error 5+ times in 1 hour)."""
        bugs = state.get("bugs", {})
        if not bugs:
            return None

        # bug_reports.json can have different structures
        reports = []
        if isinstance(bugs, dict):
            reports = bugs.get("reports", bugs.get("errors", bugs.get("bugs", [])))
        elif isinstance(bugs, list):
            reports = bugs

        if not isinstance(reports, list):
            return None

        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        recent_errors: dict[str, int] = {}

        for report in reports:
            ts = report.get("timestamp", report.get("time", ""))
            if ts and ts < cutoff:
                continue

            # Group by error type/message
            error_key = report.get("error_type", report.get("type", report.get("message", "unknown")))
            if len(error_key) > 100:
                error_key = error_key[:100]
            recent_errors[error_key] = recent_errors.get(error_key, 0) + 1

        # Find any error that repeated >= threshold times
        crash_loops = {k: v for k, v in recent_errors.items() if v >= threshold}

        if crash_loops:
            worst = max(crash_loops.items(), key=lambda x: x[1])
            trigger = self._create_trigger(
                rule_name, rule,
                f"Crash loop: '{worst[0][:60]}' occurred {worst[1]}x in 1h"
            )
            trigger.data = {"crash_loops": crash_loops, "total_recent_errors": sum(recent_errors.values())}
            return trigger
        return None

    def _check_ensemble_rejections(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check for consecutive trade decision rejections by ensemble."""
        # Look for recent decisions that were rejected
        ensemble_dir = paths.base / "parallel" / "ensemble"
        if not ensemble_dir.exists():
            # Also check decisions directory for rejection patterns
            decisions_dir = paths.decisions
            if not decisions_dir.exists():
                return None

            # Check recent decision files for rejection status
            rejection_streak = 0
            decision_files = sorted(decisions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

            for dec_file in decision_files[:10]:
                try:
                    with open(dec_file) as f:
                        dec = json.load(f)
                    status = dec.get("status", "")
                    if status in ("rejected", "REJECTED", "ensemble_rejected"):
                        rejection_streak += 1
                    else:
                        break  # Streak broken
                except Exception:
                    continue

            if rejection_streak >= threshold:
                trigger = self._create_trigger(
                    rule_name, rule,
                    f"{rejection_streak} consecutive decisions rejected"
                )
                trigger.data = {"rejection_streak": rejection_streak}
                return trigger
            return None

        # Check ensemble directory for rejection reports
        rejection_streak = 0
        report_files = sorted(ensemble_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

        for report_file in report_files[:10]:
            try:
                with open(report_file) as f:
                    report = json.load(f)
                outcome = report.get("outcome", report.get("result", ""))
                if outcome in ("rejected", "REJECTED", "no_consensus"):
                    rejection_streak += 1
                else:
                    break
            except Exception:
                continue

        if rejection_streak >= threshold:
            trigger = self._create_trigger(
                rule_name, rule,
                f"{rejection_streak} consecutive ensemble rejections"
            )
            trigger.data = {"rejection_streak": rejection_streak}
            return trigger
        return None

    def _check_instance_divergence(self, rule_name, rule, state, threshold) -> Optional[TriggerEvent]:
        """Check meta-observer for equity spread between instances > threshold%."""
        meta = state.get("meta", {})
        if not meta:
            return None

        # Meta report has instance equity values
        instances = meta.get("instances", meta.get("instance_equities", {}))
        if not instances:
            return None

        equities = []
        if isinstance(instances, dict):
            for inst_name, inst_data in instances.items():
                if isinstance(inst_data, dict):
                    eq = inst_data.get("equity", 0)
                elif isinstance(inst_data, (int, float)):
                    eq = inst_data
                else:
                    continue
                if eq and eq > 0:
                    equities.append((inst_name, eq))
        elif isinstance(instances, list):
            for inst in instances:
                eq = inst.get("equity", 0) if isinstance(inst, dict) else 0
                name = inst.get("name", "?") if isinstance(inst, dict) else "?"
                if eq and eq > 0:
                    equities.append((name, eq))

        if len(equities) < 2:
            return None

        equities.sort(key=lambda x: x[1])
        lowest_name, lowest_eq = equities[0]
        highest_name, highest_eq = equities[-1]

        if highest_eq == 0:
            return None

        spread_pct = ((highest_eq - lowest_eq) / highest_eq) * 100

        if spread_pct >= threshold:
            trigger = self._create_trigger(
                rule_name, rule,
                f"Instance equity spread {spread_pct:.1f}%: "
                f"{lowest_name}=${lowest_eq:,.0f} vs {highest_name}=${highest_eq:,.0f}"
            )
            trigger.data = {
                "spread_pct": spread_pct,
                "instances": {name: eq for name, eq in equities},
            }
            return trigger
        return None

    # ---- Helpers ----

    def _create_trigger(self, rule_name: str, rule: dict, description_detail: str = "") -> TriggerEvent:
        """Create a TriggerEvent from a fired rule."""
        return TriggerEvent(
            trigger_id=f"trig_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{rule_name}",
            timestamp=datetime.now().isoformat(),
            level=rule["level"],
            trigger_type=rule_name,
            description=f"{rule['description']}: {description_detail}",
            session_to_spawn=rule["session"],
            symbols=rule.get("symbols", []),
            data={},
            cooldown_hours=rule["cooldown_hours"],
        )

    def fire_trigger(self, trigger: TriggerEvent) -> bool:
        """Actually spawn the session for a trigger."""
        import subprocess

        logger.warning(f"FIRING TRIGGER [{trigger.level}]: {trigger.description}")
        logger.warning(f"  Spawning: {trigger.session_to_spawn}")

        # Spawn session via athena_scheduler.sh
        scheduler_script = Path(__file__).parent.parent.parent / "scripts" / "athena_scheduler.sh"
        result = subprocess.run(
            [str(scheduler_script), "oneshot", trigger.session_to_spawn],
            capture_output=True, text=True,
            env={**os.environ},
        )

        trigger.fired = result.returncode == 0

        if not trigger.fired:
            logger.error(f"  Spawn failed (rc={result.returncode}): {result.stderr[:200]}")

        # Set cooldown
        self._set_cooldown(trigger.trigger_type, trigger.cooldown_hours)

        # Log
        self._log_trigger(trigger)

        # Push to situation board
        self._push_to_board(trigger)

        return trigger.fired

    def _load_state(self) -> dict:
        """Load current state for trigger evaluation."""
        state = {}

        # Load state.json (primary source: portfolio, positions, market, theses)
        if paths.live_state.exists():
            try:
                with open(paths.live_state) as f:
                    full_state = json.load(f)
                state["portfolio"] = full_state
            except (json.JSONDecodeError, OSError):
                pass

        # Load cross-reference alerts
        alerts_file = paths.live / "cross_reference_alerts.json"
        if alerts_file.exists():
            try:
                with open(alerts_file) as f:
                    state["alerts"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Load bug reports
        bug_file = paths.base / "logs" / "bug_reports.json"
        if bug_file.exists():
            try:
                with open(bug_file) as f:
                    state["bugs"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Load signal engines
        signals_file = paths.live / "signal_engines.json"
        if signals_file.exists():
            try:
                with open(signals_file) as f:
                    state["signals"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Load meta-observer
        meta_file = paths.base / "parallel" / "meta_report_latest.json"
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    state["meta"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # Load SEC insider
        sec_file = paths.live / "sec_insider_alerts.json"
        if sec_file.exists():
            try:
                with open(sec_file) as f:
                    state["sec_insider"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        return state

    def _in_cooldown(self, rule_name: str) -> bool:
        """Check if this rule is in cooldown."""
        if rule_name in self.cooldowns:
            try:
                expires = datetime.fromisoformat(self.cooldowns[rule_name])
                if datetime.now() < expires:
                    return True
            except (ValueError, TypeError):
                pass
        return False

    def _set_cooldown(self, rule_name: str, hours: float):
        """Set cooldown for a rule."""
        self.cooldowns[rule_name] = (datetime.now() + timedelta(hours=hours)).isoformat()
        self._save_cooldowns()

    def _load_cooldowns(self) -> dict:
        if self.COOLDOWN_FILE.exists():
            try:
                with open(self.COOLDOWN_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_cooldowns(self):
        self.COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.COOLDOWN_FILE, "w") as f:
            json.dump(self.cooldowns, f, indent=2)

    def _log_trigger(self, trigger: TriggerEvent):
        self.TRIGGER_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(self.TRIGGER_LOG, "a") as f:
            f.write(json.dumps(asdict(trigger), default=str) + "\n")

    def _push_to_board(self, trigger: TriggerEvent):
        """Push trigger to situation board."""
        try:
            from src.swarm.situation_board import SituationBoard
            board = SituationBoard.load()
            board.add_observation(
                source="adaptive-trigger",
                obs_type="trigger",
                text=f"[{trigger.level.upper()}] {trigger.description} -> spawning {trigger.session_to_spawn}",
                symbols=trigger.symbols,
            )
            board.save()
        except Exception as e:
            logger.error(f"Failed to push trigger to board: {e}")

    def get_trigger_history(self, limit: int = 20) -> list[dict]:
        """Load recent trigger events from the log file."""
        if not self.TRIGGER_LOG.exists():
            return []

        triggers = []
        try:
            with open(self.TRIGGER_LOG) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            triggers.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass

        return triggers[-limit:]

    def get_trigger_count_24h(self) -> int:
        """Count triggers fired in the last 24 hours."""
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        count = 0
        if not self.TRIGGER_LOG.exists():
            return 0

        try:
            with open(self.TRIGGER_LOG) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", "") >= cutoff:
                            count += 1
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return count
