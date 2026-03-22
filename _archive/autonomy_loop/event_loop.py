"""Athena Event Loop — the always-on autonomy engine.

Runs as a systemd service, checking for signals, convergences, and
trading opportunities every N minutes during market hours.

Every check cycle is logged with full provenance so the web dashboard
can show the complete decision-making process.
"""

import asyncio
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from src.autonomy.config import AutonomyConfig, load_autonomy_config
from src.autonomy.llm_decisions import LLMDecisionEngine, DecisionContext, LLMDecisionResult
from src.autonomy.executor import AutonomousExecutor
from src.autonomy.provenance import log_event, log_convergence_detected, log_trade_event, generate_id
from src.db.database import get_db, init_db
from src.db.models import AutonomyCheck, DecisionRecord, DecisionConvergence
from src.db.sync import sync_decision_to_file


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _is_market_hours(config: AutonomyConfig) -> bool:
    """Check if we're within active hours (ET)."""
    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
    except ImportError:
        # Fallback: assume UTC-5
        import time as _time
        utc_now = datetime.utcnow()
        now_et = utc_now  # approximate
    return config.event_loop.active_hours_start <= now_et.hour < config.event_loop.active_hours_end


class AthenaEventLoop:
    """Main autonomy event loop."""

    def __init__(self, config: AutonomyConfig | None = None):
        self.config = config or load_autonomy_config()
        self.llm_engine = LLMDecisionEngine(self.config.llm)
        self.executor = AutonomousExecutor(self.config.execution)
        self.running = True
        self.check_count = 0
        self._decisions_today = 0

    async def run(self):
        """Main loop — runs until stopped."""
        init_db()
        log_event("system_started", source="autonomy_loop", title="Athena autonomy loop started",
                  detail={"dry_run": self.config.execution.dry_run, "interval": self.config.event_loop.check_interval_minutes})

        print(f"[Athena] Event loop started (interval={self.config.event_loop.check_interval_minutes}m, "
              f"dry_run={self.config.execution.dry_run})")

        while self.running:
            try:
                if _is_market_hours(self.config):
                    await self.check_cycle()
                else:
                    # Outside market hours — just heartbeat
                    self._write_heartbeat(active=False)
            except Exception as e:
                log_event("system_error", source="autonomy_loop", severity="critical",
                          title=f"Check cycle error: {type(e).__name__}",
                          detail={"error": str(e)})
                print(f"[Athena] Check cycle error: {e}")

            await asyncio.sleep(self.config.event_loop.check_interval_minutes * 60)

    async def check_cycle(self):
        """One check cycle — the core of autonomy."""
        self.check_count += 1
        cycle_start = time.time()
        check_id = generate_id("chk")

        check = {
            "id": check_id,
            "check_number": self.check_count,
            "alerts_found": 0,
            "convergences_found": 0,
            "rules_triggered": 0,
            "llm_calls_made": 0,
            "trades_executed": 0,
            "actions": [],
            "errors": [],
        }

        print(f"[Athena] Check #{self.check_count} started")

        # 1. Load state
        state = self._load_state()
        if state.get("error"):
            check["errors"].append(f"State load failed: {state['error']}")
            self._save_check(check, cycle_start)
            return

        state_age = self._get_state_age()
        check["state_age_seconds"] = state_age

        portfolio = self._get_portfolio_summary(state)

        # 2. Check for alerts (price alerts, position alerts)
        alerts = self._check_alerts(state)
        check["alerts_found"] = len(alerts)
        for alert in alerts:
            log_event("alert_fired", source="autonomy_loop", symbol=alert.get("symbol"),
                      severity=alert.get("severity", "warning"),
                      title=alert.get("title", "Alert"),
                      detail=alert)

        # 3. Check signpost triggers
        triggers = self._check_signposts(state)
        for trigger in triggers:
            log_event("signpost_triggered", source="autonomy_loop",
                      thesis_id=trigger.get("thesis_id"),
                      title=f"Signpost triggered: {trigger.get('description', '')[:60]}",
                      detail=trigger)

        # 4. Check signal convergences
        convergences = self._check_convergences(state)
        check["convergences_found"] = len(convergences)

        for conv in convergences:
            conv_id = generate_id("conv")
            log_convergence_detected(
                symbol=conv.get("symbol", ""),
                signal_count=conv.get("signal_count", 0),
                weighted_score=conv.get("weighted_score", 0),
                direction=conv.get("direction", "neutral"),
                convergence_id=conv_id,
            )
            # Save convergence to DB
            self._save_convergence(conv_id, conv)

        # 5. Evaluate rules engine
        rules = self._evaluate_rules(state)
        check["rules_triggered"] = len(rules)

        # 6. For high-confidence convergences, request LLM decision
        for conv in convergences:
            if conv.get("weighted_score", 0) >= 0.6 and self._decisions_today < self.config.llm.max_decisions_per_day:
                result = self._request_llm_decision(conv, state, portfolio)
                check["llm_calls_made"] += 1

                if result and result.action in ("BUY", "SELL", "ADD", "TRIM"):
                    if result.confidence >= self.config.llm.min_confidence_for_auto:
                        # Create decision record
                        decision = self._create_decision(result, conv)
                        check["actions"].append(f"Decision: {result.action} {result.symbol} @ {result.confidence:.0%}")

                        # Execute
                        exec_result = await self.executor.execute_decision(decision, portfolio)
                        if exec_result.get("success"):
                            check["trades_executed"] += 1
                            self._decisions_today += 1

        # 7. Write heartbeat
        self._write_heartbeat(active=True)

        # Save check record
        self._save_check(check, cycle_start)
        duration_ms = int((time.time() - cycle_start) * 1000)
        print(f"[Athena] Check #{self.check_count} done in {duration_ms}ms "
              f"(alerts={check['alerts_found']}, convergences={check['convergences_found']}, "
              f"trades={check['trades_executed']})")

    def _load_state(self) -> dict:
        """Load unified state.json."""
        state_path = _results_dir() / "live" / "state.json"
        if not state_path.exists():
            return {"error": "state.json not found"}
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return {"error": str(e)}

    def _get_state_age(self) -> int:
        """How old is state.json in seconds."""
        state_path = _results_dir() / "live" / "state.json"
        if not state_path.exists():
            return -1
        return int(time.time() - state_path.stat().st_mtime)

    def _get_portfolio_summary(self, state: dict) -> dict:
        """Extract portfolio metrics from state."""
        positions = state.get("positions", [])
        total_value = sum(p.get("market_value", 0) for p in positions)
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
        day_pnl = sum(p.get("day_pnl", 0) for p in positions)

        return {
            "position_count": len(positions),
            "total_value": total_value,
            "total_pnl": total_pnl,
            "day_pnl": day_pnl,
            "day_pnl_pct": (day_pnl / total_value * 100) if total_value else 0,
        }

    def _check_alerts(self, state: dict) -> list[dict]:
        """Check for alert conditions."""
        alerts = []
        positions = state.get("positions", [])

        for pos in positions:
            pnl_pct = pos.get("unrealized_pnl_pct", 0)
            # Stop loss alert
            if pnl_pct <= -15:
                alerts.append({
                    "symbol": pos.get("symbol"),
                    "severity": "critical",
                    "title": f"STOP LOSS: {pos['symbol']} at {pnl_pct:.1f}%",
                    "type": "stop_loss",
                })
            # Large loss alert
            elif pnl_pct <= -10:
                alerts.append({
                    "symbol": pos.get("symbol"),
                    "severity": "warning",
                    "title": f"Large loss: {pos['symbol']} at {pnl_pct:.1f}%",
                    "type": "large_loss",
                })

        # VIX spike alert
        market = state.get("market", {})
        vix = market.get("vix", 0)
        if vix > 30:
            alerts.append({
                "severity": "warning",
                "title": f"VIX elevated: {vix:.1f}",
                "type": "vix_spike",
            })

        return alerts

    def _check_signposts(self, state: dict) -> list[dict]:
        """Check thesis signposts for triggers."""
        triggers = []
        theses = state.get("theses", [])
        for thesis in theses:
            if isinstance(thesis, dict) and thesis.get("next_signpost"):
                # Simple check — real implementation would use ThesisTracker
                pass
        return triggers

    def _check_convergences(self, state: dict) -> list[dict]:
        """Check for signal convergences across sources."""
        convergences = []
        signals_by_symbol: dict[str, list[dict]] = {}

        # Aggregate signals from state
        for signal in state.get("signals", []):
            symbol = signal.get("symbol", "")
            if symbol:
                signals_by_symbol.setdefault(symbol, []).append(signal)

        # Check for convergences (3+ aligned signals)
        for symbol, signals in signals_by_symbol.items():
            bullish = [s for s in signals if s.get("direction") == "bullish"]
            bearish = [s for s in signals if s.get("direction") == "bearish"]

            if len(bullish) >= 3:
                avg_confidence = sum(s.get("confidence", 0.5) for s in bullish) / len(bullish)
                convergences.append({
                    "symbol": symbol,
                    "signal_count": len(bullish),
                    "direction": "bullish",
                    "weighted_score": avg_confidence,
                    "signals": bullish,
                })
            if len(bearish) >= 3:
                avg_confidence = sum(s.get("confidence", 0.5) for s in bearish) / len(bearish)
                convergences.append({
                    "symbol": symbol,
                    "signal_count": len(bearish),
                    "direction": "bearish",
                    "weighted_score": avg_confidence,
                    "signals": bearish,
                })

        return convergences

    def _evaluate_rules(self, state: dict) -> list[dict]:
        """Evaluate rules engine for auto-actions."""
        # Placeholder — would integrate with src/execution/rules_engine.py
        return []

    def _request_llm_decision(self, convergence: dict, state: dict, portfolio: dict) -> LLMDecisionResult | None:
        """Ask the LLM to evaluate a convergence."""
        context = DecisionContext(
            trigger_type="convergence",
            trigger_id=convergence.get("id", ""),
            symbol=convergence.get("symbol", ""),
            state_summary=self._build_state_summary(state),
            signals=convergence.get("signals", []),
            convergence=convergence,
            portfolio_context=portfolio,
        )

        # Add thesis context if available
        symbol = convergence.get("symbol", "")
        for thesis in state.get("theses", []):
            if isinstance(thesis, dict) and symbol in thesis.get("positions", []):
                context.thesis_context = thesis
                break

        return self.llm_engine.make_trade_decision(context)

    def _build_state_summary(self, state: dict) -> str:
        """Build concise state summary for LLM prompt."""
        market = state.get("market", {})
        sentiment = state.get("sentiment", {})
        positions = state.get("positions", [])

        lines = [
            f"Market: SPY {market.get('spy_change_pct', 0):+.1f}%, VIX {market.get('vix', 0):.1f}, Regime: {market.get('regime', 'N/A')}",
            f"Sentiment: {sentiment.get('overall_sentiment', 'N/A')}, Fear/Greed: {sentiment.get('fear_greed_value', 0):.0f}",
            f"Portfolio: {len(positions)} positions, ${sum(p.get('market_value', 0) for p in positions):,.0f}",
        ]
        return "\n".join(lines)

    def _create_decision(self, result: LLMDecisionResult, convergence: dict) -> dict:
        """Create and save a decision record."""
        decision_id = generate_id("dec")
        decision = {
            "id": decision_id,
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": result.symbol or convergence.get("symbol", ""),
            "action": result.action,
            "confidence": result.confidence,
            "size_pct": result.size_pct,
            "reasoning": result.reasoning,
            "key_factors": result.key_factors,
            "risks": result.risks,
            "pre_mortem": result.pre_mortem,
            "setup_type": result.setup_type,
            "status": "pending",
            "llm_interaction_id": result.interaction_id,
            "convergence_id": convergence.get("id"),
            "context": {},
        }

        # Save to DB
        try:
            with get_db() as session:
                record = DecisionRecord.from_dict(decision)
                session.add(record)
            sync_decision_to_file(decision)
        except Exception as e:
            print(f"WARN: Failed to save decision: {e}")

        # Log event
        log_trade_event(
            "decision_proposed",
            decision_id=decision_id,
            symbol=decision["symbol"],
            detail={"action": result.action, "confidence": result.confidence},
        )

        return decision

    def _save_convergence(self, conv_id: str, conv: dict):
        """Save convergence to DB."""
        try:
            with get_db() as session:
                record = DecisionConvergence(
                    id=conv_id,
                    symbols=json.dumps([conv.get("symbol", "")]),
                    signal_count=conv.get("signal_count", 0),
                    weighted_score=conv.get("weighted_score", 0),
                    agent_sources=json.dumps([]),
                    direction=conv.get("direction", "neutral"),
                    detail=json.dumps(conv),
                )
                session.add(record)
        except Exception as e:
            print(f"WARN: Failed to save convergence: {e}")

    def _save_check(self, check: dict, start_time: float):
        """Save autonomy check record to DB."""
        try:
            duration_ms = int((time.time() - start_time) * 1000)
            with get_db() as session:
                record = AutonomyCheck(
                    id=check["id"],
                    timestamp=datetime.utcnow(),
                    check_number=check["check_number"],
                    duration_ms=duration_ms,
                    state_age_seconds=check.get("state_age_seconds", 0),
                    alerts_found=check["alerts_found"],
                    convergences_found=check["convergences_found"],
                    rules_triggered=check["rules_triggered"],
                    llm_calls_made=check["llm_calls_made"],
                    trades_executed=check["trades_executed"],
                    actions_taken=json.dumps(check.get("actions", [])),
                    errors=json.dumps(check.get("errors", [])),
                )
                session.add(record)
        except Exception as e:
            print(f"WARN: Failed to save check record: {e}")

    def _write_heartbeat(self, active: bool):
        """Write heartbeat for health monitoring."""
        heartbeat = {
            "service": "athena-autonomy",
            "timestamp": datetime.utcnow().isoformat(),
            "active": active,
            "check_count": self.check_count,
            "decisions_today": self._decisions_today,
            "dry_run": self.config.execution.dry_run,
        }
        try:
            health_dir = _results_dir() / "live" / "health"
            health_dir.mkdir(parents=True, exist_ok=True)
            (health_dir / "autonomy.json").write_text(json.dumps(heartbeat, indent=2))
        except Exception:
            pass

    def stop(self):
        """Gracefully stop the event loop."""
        print("[Athena] Stopping event loop...")
        self.running = False
        log_event("system_stopped", source="autonomy_loop", title="Athena autonomy loop stopped")
