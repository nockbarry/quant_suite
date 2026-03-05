"""
Operator Loop Module - Core helpers for morning operator sessions.

Provides the check cycle logic for Claude's persistent operator mode:
1. Check state.json for alerts and changes
2. Review thesis signpost triggers
3. Monitor agent completions
4. Detect signal convergences
5. Generate action recommendations

Used by the operator-session skill.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """An alert requiring operator attention."""
    level: str  # "critical", "warning", "info"
    source: str  # Where the alert came from
    title: str
    message: str
    timestamp: datetime
    symbol: str | None = None
    action_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignpostTrigger:
    """A thesis signpost that has triggered."""
    thesis_id: str
    thesis_name: str
    signpost_description: str
    outcome: str  # "bullish" or "bearish"
    triggered_at: datetime
    conviction_before: int
    conviction_after: int | None = None
    action_suggestion: str | None = None


@dataclass
class AgentCompletion:
    """Record of a completed agent."""
    agent_id: str
    agent_type: str
    task: str
    status: str  # "completed", "failed"
    completed_at: datetime
    result_summary: str | None = None
    findings: list[str] = field(default_factory=list)


@dataclass
class ActionItem:
    """Recommended action for the operator."""
    priority: str  # "high", "medium", "low"
    category: str  # "thesis", "position", "research", "risk", "process"
    action: str
    reason: str
    symbol: str | None = None
    thesis_id: str | None = None


@dataclass
class OperatorObservation:
    """Complete observation from a single operator check cycle."""
    check_num: int
    timestamp: datetime
    check_duration_seconds: float

    # What was found
    alerts: list[Alert] = field(default_factory=list)
    signpost_triggers: list[SignpostTrigger] = field(default_factory=list)
    agent_completions: list[AgentCompletion] = field(default_factory=list)
    convergences: list[dict] = field(default_factory=list)
    stale_sources: list[str] = field(default_factory=list)

    # Autonomous session data ingestion
    session_updates: list[dict] = field(default_factory=list)
    thesis_changes: list[dict] = field(default_factory=list)
    new_research: list[dict] = field(default_factory=list)

    # Market state
    market_regime: str = "unknown"
    regime_change: bool = False
    portfolio_status: dict = field(default_factory=dict)

    # Recommendations
    action_items: list[ActionItem] = field(default_factory=list)
    research_suggestions: list[str] = field(default_factory=list)

    def has_urgent_items(self) -> bool:
        """Check if there are urgent items requiring attention."""
        return (
            any(a.level == "critical" for a in self.alerts) or
            any(a.priority == "high" for a in self.action_items) or
            self.regime_change
        )

    def to_dict(self) -> dict:
        return {
            "check_num": self.check_num,
            "timestamp": self.timestamp.isoformat(),
            "check_duration_seconds": round(self.check_duration_seconds, 2),
            "alerts": [
                {
                    "level": a.level,
                    "source": a.source,
                    "title": a.title,
                    "message": a.message,
                }
                for a in self.alerts
            ],
            "signpost_triggers": [
                {
                    "thesis": s.thesis_name,
                    "signpost": s.signpost_description,
                    "outcome": s.outcome,
                }
                for s in self.signpost_triggers
            ],
            "agent_completions": [
                {
                    "type": a.agent_type,
                    "task": a.task,
                    "status": a.status,
                }
                for a in self.agent_completions
            ],
            "convergences": self.convergences,
            "session_updates": self.session_updates,
            "thesis_changes": self.thesis_changes,
            "new_research": self.new_research,
            "market_regime": self.market_regime,
            "regime_change": self.regime_change,
            "action_items": [
                {
                    "priority": a.priority,
                    "category": a.category,
                    "action": a.action,
                    "reason": a.reason,
                }
                for a in self.action_items
            ],
            "has_urgent_items": self.has_urgent_items(),
        }


class OperatorLoop:
    """
    Core operator loop logic for morning sessions.

    Performs check cycles at configurable intervals, surfacing:
    - Alerts and signpost triggers
    - Agent completions
    - Signal convergences
    - Action recommendations
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.live_dir = self.results_dir / "live"
        self.logs_dir = self.results_dir / "logs"
        self.theses_dir = self.results_dir / "theses"

        # Track state between checks
        self.last_check_time: datetime | None = None
        self.last_regime: str = "unknown"
        self.check_count = 0
        self.session_start = datetime.now()

    def operator_check(self) -> OperatorObservation:
        """
        Perform a single operator check cycle.

        Returns an observation with all findings and recommendations.
        """
        start_time = datetime.now()
        self.check_count += 1

        # Load current state
        state = self._load_state()

        # Check each area
        alerts = self._check_alerts(state)
        signpost_triggers = self._check_signposts()
        agent_completions = self._get_recent_completions()
        convergences = self._check_convergences()
        stale_sources = self._check_data_freshness()

        # Check autonomous session data
        session_updates = self._check_session_updates()
        thesis_changes = self._check_thesis_changes()
        new_research = self._check_new_research()

        # Market state
        market_regime = state.get("market", {}).get("rotation_theme", "unknown")
        regime_change = market_regime != self.last_regime and self.last_regime != "unknown"
        self.last_regime = market_regime

        # Portfolio status
        portfolio_status = self._get_portfolio_status(state)

        # Generate action items (include autonomous session data)
        action_items = self._generate_action_items(
            alerts, signpost_triggers, convergences, portfolio_status, regime_change,
            thesis_changes, new_research,
        )

        # Research suggestions based on findings
        research_suggestions = self._suggest_research(
            convergences, signpost_triggers, regime_change
        )

        check_duration = (datetime.now() - start_time).total_seconds()
        self.last_check_time = datetime.now()

        observation = OperatorObservation(
            check_num=self.check_count,
            timestamp=datetime.now(),
            check_duration_seconds=check_duration,
            alerts=alerts,
            signpost_triggers=signpost_triggers,
            agent_completions=agent_completions,
            convergences=convergences,
            stale_sources=stale_sources,
            session_updates=session_updates,
            thesis_changes=thesis_changes,
            new_research=new_research,
            market_regime=market_regime,
            regime_change=regime_change,
            portfolio_status=portfolio_status,
            action_items=action_items,
            research_suggestions=research_suggestions,
        )

        # Log the observation
        self._log_observation(observation)

        # Push to SessionContext for decision context preservation
        try:
            from src.context.session_context import SessionContext
            summary_parts = []
            if observation.alerts:
                summary_parts.append(f"{len(observation.alerts)} alerts")
            if observation.convergences:
                summary_parts.append(f"{len(observation.convergences)} convergences")
            if observation.action_items:
                summary_parts.append(f"{len(observation.action_items)} action items")
            obs_summary = f"Check #{observation.check_num}: " + (", ".join(summary_parts) or "all clear")

            SessionContext.get().add_operator_observation(
                observation_summary=obs_summary,
                portfolio_snapshot=portfolio_status,
                alerts=[a.title for a in observation.alerts],
            )
        except Exception:
            pass  # Don't break operator loop if context push fails

        return observation

    def _load_state(self) -> dict:
        """Load current unified state."""
        state_file = self.live_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        return {}

    def _check_alerts(self, state: dict) -> list[Alert]:
        """Check for alerts from state and positions."""
        alerts = []
        now = datetime.now()

        # Portfolio-level alerts
        portfolio = state.get("portfolio", {})
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)
        equity = portfolio.get("equity", 0)

        if day_pnl_pct < -3:
            alerts.append(Alert(
                level="critical" if day_pnl_pct < -5 else "warning",
                source="portfolio",
                title="Significant Drawdown",
                message=f"Portfolio down {day_pnl_pct:.1f}% today (${portfolio.get('day_pnl', 0):,.0f})",
                timestamp=now,
                action_required=day_pnl_pct < -5,
            ))

        # Market-level alerts
        market = state.get("market", {})
        vix = market.get("vix", 15)
        vix_change = market.get("vix_change_pct", 0)

        if vix > 25:
            alerts.append(Alert(
                level="warning",
                source="market",
                title="Elevated VIX",
                message=f"VIX at {vix:.1f} ({vix_change:+.1f}%)",
                timestamp=now,
            ))

        if vix > 30:
            alerts.append(Alert(
                level="critical",
                source="market",
                title="High Volatility Alert",
                message=f"VIX spiked to {vix:.1f} - consider reducing exposure",
                timestamp=now,
                action_required=True,
            ))

        # Position-level alerts
        positions = state.get("positions", [])
        for pos in positions:
            symbol = pos.get("symbol", "UNK")
            pnl_pct = pos.get("unrealized_pnl_pct", 0)
            day_pnl_pct = pos.get("day_pnl_pct", 0)

            # Big losers
            if pnl_pct < -10:
                alerts.append(Alert(
                    level="warning",
                    source="position",
                    title=f"{symbol} Down Significantly",
                    message=f"{symbol} down {pnl_pct:.1f}% from cost",
                    timestamp=now,
                    symbol=symbol,
                    action_required=pnl_pct < -15,
                ))

            # Today's big movers
            if abs(day_pnl_pct) > 5:
                direction = "up" if day_pnl_pct > 0 else "down"
                alerts.append(Alert(
                    level="info",
                    source="position",
                    title=f"{symbol} Big Move",
                    message=f"{symbol} {direction} {abs(day_pnl_pct):.1f}% today",
                    timestamp=now,
                    symbol=symbol,
                ))

        return alerts

    def _check_signposts(self) -> list[SignpostTrigger]:
        """Check for recently triggered thesis signposts."""
        triggers = []

        if not self.theses_dir.exists():
            return triggers

        # Check each thesis for recent triggers
        for thesis_file in self.theses_dir.glob("*.yaml"):
            try:
                with open(thesis_file) as f:
                    thesis = yaml.safe_load(f)

                if thesis.get("status") != "active":
                    continue

                thesis_id = thesis.get("id", thesis_file.stem)
                thesis_name = thesis.get("name", "Unknown")
                conviction = thesis.get("conviction", 50)

                for signpost in thesis.get("signposts", []):
                    if signpost.get("status") == "triggered":
                        triggered_at_str = signpost.get("triggered_at", "")
                        if triggered_at_str:
                            try:
                                triggered_at = datetime.fromisoformat(triggered_at_str)
                                # Only report triggers from last 24 hours
                                if datetime.now() - triggered_at < timedelta(hours=24):
                                    triggers.append(SignpostTrigger(
                                        thesis_id=thesis_id,
                                        thesis_name=thesis_name,
                                        signpost_description=signpost.get("description", ""),
                                        outcome=signpost.get("outcome", "unknown"),
                                        triggered_at=triggered_at,
                                        conviction_before=conviction,
                                    ))
                            except ValueError:
                                continue

            except Exception as e:
                logger.debug(f"Error checking thesis {thesis_file}: {e}")

        return triggers

    def _get_recent_completions(self) -> list[AgentCompletion]:
        """Get agent completions since last check."""
        completions = []
        activity_log = self.logs_dir / "agent_activity.jsonl"

        if not activity_log.exists():
            return completions

        cutoff = self.last_check_time or (datetime.now() - timedelta(hours=1))

        try:
            with open(activity_log) as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        if record.get("type") == "agent_complete":
                            timestamp_str = record.get("timestamp", "")
                            timestamp = datetime.fromisoformat(timestamp_str)

                            if timestamp > cutoff:
                                completions.append(AgentCompletion(
                                    agent_id=record.get("agent_id", "unknown"),
                                    agent_type=record.get("agent_type", "unknown"),
                                    task=record.get("task", ""),
                                    status=record.get("status", "completed"),
                                    completed_at=timestamp,
                                    result_summary=record.get("result_summary"),
                                ))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception as e:
            logger.error(f"Error reading activity log: {e}")

        return completions

    def _check_convergences(self) -> list[dict]:
        """Check for signal convergences."""
        try:
            from src.monitoring.signal_summary import get_signal_summary
            summary = get_signal_summary()
            return [c.to_dict() for c in summary.convergences]
        except Exception as e:
            logger.error(f"Error checking convergences: {e}")
            return []

    def _check_data_freshness(self) -> list[str]:
        """Check for stale data sources."""
        try:
            from src.monitoring.data_freshness_tracker import get_data_freshness
            summary = get_data_freshness()
            return [
                name for name, status in summary.sources.items()
                if status.status == "stale"
            ]
        except Exception as e:
            logger.error(f"Error checking data freshness: {e}")
            return []

    def _get_portfolio_status(self, state: dict) -> dict:
        """Extract portfolio status from state."""
        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        total_value = portfolio.get("equity", 0)
        winners = [p for p in positions if p.get("unrealized_pnl_pct", 0) > 0]
        losers = [p for p in positions if p.get("unrealized_pnl_pct", 0) < 0]

        return {
            "equity": total_value,
            "day_pnl": portfolio.get("day_pnl", 0),
            "day_pnl_pct": portfolio.get("day_pnl_pct", 0),
            "positions": len(positions),
            "winners": len(winners),
            "losers": len(losers),
            "cash": portfolio.get("cash", 0),
        }

    def _check_session_updates(self) -> list[dict]:
        """Check for completed autonomous sessions since last check."""
        try:
            from src.monitoring.autonomous_mode import get_session_completions_since
            cutoff = self.last_check_time or (datetime.now() - timedelta(hours=1))
            return get_session_completions_since(cutoff)
        except Exception as e:
            logger.debug(f"Error checking session updates: {e}")
            return []

    def _check_thesis_changes(self) -> list[dict]:
        """Check for thesis conviction/status changes."""
        try:
            from src.monitoring.autonomous_mode import get_thesis_changes_since
            cutoff = self.last_check_time or (datetime.now() - timedelta(hours=1))
            return get_thesis_changes_since(cutoff)
        except Exception as e:
            logger.debug(f"Error checking thesis changes: {e}")
            return []

    def _check_new_research(self) -> list[dict]:
        """Check for new research results and trade triggers."""
        try:
            from src.monitoring.autonomous_mode import get_new_research_since
            cutoff = self.last_check_time or (datetime.now() - timedelta(hours=1))
            return get_new_research_since(cutoff)
        except Exception as e:
            logger.debug(f"Error checking new research: {e}")
            return []

    def _write_trade_triggers(self, convergences: list[dict]) -> None:
        """Write strong convergences as trade triggers for health monitor."""
        try:
            from src.monitoring.autonomous_mode import write_trade_trigger
            for conv in convergences:
                if conv.get("signal_count", 0) >= 4:
                    write_trade_trigger(
                        symbol=conv.get("symbol", ""),
                        direction=conv.get("direction", "unknown"),
                        signal_count=conv.get("signal_count", 0),
                        signals=conv.get("signals", []),
                        source="operator",
                    )
        except Exception as e:
            logger.debug(f"Error writing trade triggers: {e}")

    def _generate_action_items(
        self,
        alerts: list[Alert],
        signpost_triggers: list[SignpostTrigger],
        convergences: list[dict],
        portfolio_status: dict,
        regime_change: bool,
        thesis_changes: list[dict] | None = None,
        new_research: list[dict] | None = None,
    ) -> list[ActionItem]:
        """Generate action recommendations based on findings."""
        actions = []

        # Critical alerts need immediate attention
        for alert in alerts:
            if alert.action_required:
                actions.append(ActionItem(
                    priority="high",
                    category="risk",
                    action=f"Review {alert.title}",
                    reason=alert.message,
                    symbol=alert.symbol,
                ))

        # Signpost triggers may require thesis updates
        for trigger in signpost_triggers:
            if trigger.outcome == "bearish":
                actions.append(ActionItem(
                    priority="medium",
                    category="thesis",
                    action=f"Review {trigger.thesis_name} thesis",
                    reason=f"Bearish signpost triggered: {trigger.signpost_description}",
                    thesis_id=trigger.thesis_id,
                ))
            elif trigger.outcome == "bullish":
                actions.append(ActionItem(
                    priority="low",
                    category="thesis",
                    action=f"Consider adding to {trigger.thesis_name}",
                    reason=f"Bullish signpost triggered: {trigger.signpost_description}",
                    thesis_id=trigger.thesis_id,
                ))

        # Regime change requires portfolio review
        if regime_change:
            actions.append(ActionItem(
                priority="medium",
                category="portfolio",
                action="Review positions for regime change",
                reason=f"Market regime changed to {self.last_regime}",
            ))

        # Strong convergences are actionable
        for conv in convergences:
            if conv.get("signal_count", 0) >= 4:
                direction = conv.get("direction", "unknown")
                symbol = conv.get("symbol", "UNK")
                actions.append(ActionItem(
                    priority="medium",
                    category="position",
                    action=f"Evaluate {symbol} - strong {direction} convergence",
                    reason=f"{conv.get('signal_count')} signals aligned",
                    symbol=symbol,
                ))

        # Write strong convergences as trade triggers for health monitor
        self._write_trade_triggers(convergences)

        # Thesis changes from autonomous sessions
        for change in (thesis_changes or []):
            if change.get("type") == "conviction_change":
                old_c = change.get("old_conviction", 0)
                new_c = change.get("new_conviction", 0)
                priority = "high" if abs(new_c - old_c) >= 20 else "medium"
                actions.append(ActionItem(
                    priority=priority,
                    category="thesis",
                    action=f"Review {change.get('name')} conviction: {old_c}% → {new_c}%",
                    reason="Thesis conviction changed by autonomous session",
                    thesis_id=change.get("thesis_id"),
                ))
            elif change.get("type") == "new_thesis":
                actions.append(ActionItem(
                    priority="medium",
                    category="thesis",
                    action=f"Review new thesis: {change.get('name')} ({change.get('conviction')}%)",
                    reason="New thesis created by autonomous session",
                    thesis_id=change.get("thesis_id"),
                ))
            elif change.get("type") == "status_change" and change.get("new_status") == "invalidated":
                actions.append(ActionItem(
                    priority="high",
                    category="thesis",
                    action=f"Thesis invalidated: {change.get('name')}",
                    reason=f"Status changed from {change.get('old_status')} to {change.get('new_status')}",
                    thesis_id=change.get("thesis_id"),
                ))

        # Trade triggers from research/other sessions
        for item in (new_research or []):
            if item.get("type") == "trade_trigger" and not item.get("consumed"):
                actions.append(ActionItem(
                    priority="high",
                    category="position",
                    action=f"Trade trigger: {item.get('symbol')} {item.get('direction')} ({item.get('signal_count')} signals)",
                    reason=f"Convergence trigger from {item.get('source', 'autonomous session')}",
                    symbol=item.get("symbol"),
                ))

        return actions

    def _suggest_research(
        self,
        convergences: list[dict],
        signpost_triggers: list[SignpostTrigger],
        regime_change: bool,
    ) -> list[str]:
        """Suggest research agents to spawn based on findings."""
        suggestions = []

        # Research convergence opportunities
        for conv in convergences:
            symbol = conv.get("symbol", "")
            if symbol:
                suggestions.append(f"Deep dive on {symbol} - {conv.get('signal_count')} signals converging")

        # Research triggered signposts
        for trigger in signpost_triggers:
            suggestions.append(f"Thesis validation: {trigger.thesis_name} after signpost trigger")

        # Regime research
        if regime_change:
            suggestions.append(f"Regime analysis: implications of {self.last_regime} rotation")

        return suggestions[:5]  # Limit suggestions

    def _log_observation(self, obs: OperatorObservation) -> None:
        """Log observation to operator log file and ProcessEvent audit trail."""
        log_file = self.logs_dir / "operator_log.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(obs.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Error logging observation: {e}")

        # Log to ProcessEvent for web UI visibility
        try:
            from src.autonomy.provenance import log_event

            summary_parts = []
            if obs.alerts:
                summary_parts.append(f"{len(obs.alerts)} alerts")
            if obs.convergences:
                summary_parts.append(f"{len(obs.convergences)} convergences")
            if obs.action_items:
                summary_parts.append(f"{len(obs.action_items)} actions")
            if obs.session_updates:
                summary_parts.append(f"{len(obs.session_updates)} session updates")
            if obs.thesis_changes:
                summary_parts.append(f"{len(obs.thesis_changes)} thesis changes")
            obs_summary = ", ".join(summary_parts) or "all clear"

            parent_id = log_event(
                event_type="operator_check",
                source="scheduler:operator",
                severity="warning" if obs.has_urgent_items() else "info",
                title=f"Operator check #{obs.check_num}: {obs_summary}",
                detail={
                    "check_num": obs.check_num,
                    "market_regime": obs.market_regime,
                    "regime_change": obs.regime_change,
                    "alert_count": len(obs.alerts),
                    "convergence_count": len(obs.convergences),
                    "action_count": len(obs.action_items),
                    "session_updates": len(obs.session_updates),
                    "thesis_changes": len(obs.thesis_changes),
                    "portfolio": obs.portfolio_status,
                },
            )

            # Log thesis changes as child events
            for change in obs.thesis_changes:
                log_event(
                    event_type="thesis_change",
                    source="scheduler:operator",
                    title=f"Thesis {change.get('type', 'change')}: {change.get('name', '')}",
                    detail=change,
                    parent_event_id=parent_id,
                    thesis_id=change.get("thesis_id"),
                )

        except Exception:
            pass  # Don't break operator loop if provenance logging fails

    def get_session_summary(self) -> dict:
        """Get summary of current operator session."""
        duration = datetime.now() - self.session_start
        return {
            "session_start": self.session_start.isoformat(),
            "duration_minutes": duration.total_seconds() / 60,
            "checks_completed": self.check_count,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "current_regime": self.last_regime,
        }

    def format_observation(self, obs: OperatorObservation) -> str:
        """Format observation for console display."""
        lines = []
        lines.append(f"{'='*60}")
        lines.append(f"OPERATOR CHECK #{obs.check_num} - {obs.timestamp.strftime('%H:%M:%S')}")
        lines.append(f"{'='*60}")

        # Regime
        lines.append(f"\nMarket Regime: {obs.market_regime.upper()}")
        if obs.regime_change:
            lines.append("  ** REGIME CHANGE DETECTED **")

        # Alerts
        if obs.alerts:
            lines.append(f"\n--- ALERTS ({len(obs.alerts)}) ---")
            for alert in obs.alerts:
                marker = "!!" if alert.level == "critical" else "!" if alert.level == "warning" else "-"
                lines.append(f"  [{marker}] {alert.title}: {alert.message}")

        # Signpost triggers
        if obs.signpost_triggers:
            lines.append(f"\n--- SIGNPOST TRIGGERS ({len(obs.signpost_triggers)}) ---")
            for trigger in obs.signpost_triggers:
                lines.append(f"  {trigger.thesis_name}: {trigger.signpost_description} ({trigger.outcome})")

        # Agent completions
        if obs.agent_completions:
            lines.append(f"\n--- AGENT COMPLETIONS ({len(obs.agent_completions)}) ---")
            for comp in obs.agent_completions:
                lines.append(f"  [{comp.agent_type}] {comp.task[:50]}... ({comp.status})")

        # Convergences
        if obs.convergences:
            lines.append(f"\n--- CONVERGENCES ({len(obs.convergences)}) ---")
            for conv in obs.convergences:
                lines.append(f"  {conv.get('symbol')}: {conv.get('signal_count')} {conv.get('direction')} signals")

        # Autonomous session updates
        if obs.session_updates:
            lines.append(f"\n--- SESSION UPDATES ({len(obs.session_updates)}) ---")
            for update in obs.session_updates:
                status = "OK" if update.get("success") else "FAILED"
                lines.append(f"  [{status}] {update.get('session_type', 'unknown')}: {update.get('summary', '')[:80]}")
                for finding in update.get("key_findings", [])[:3]:
                    lines.append(f"        → {finding[:80]}")

        # Thesis changes
        if obs.thesis_changes:
            lines.append(f"\n--- THESIS CHANGES ({len(obs.thesis_changes)}) ---")
            for change in obs.thesis_changes:
                ctype = change.get("type", "")
                name = change.get("name", "Unknown")
                if ctype == "conviction_change":
                    lines.append(f"  {name}: {change.get('old_conviction')}% → {change.get('new_conviction')}%")
                elif ctype == "new_thesis":
                    lines.append(f"  NEW: {name} ({change.get('conviction')}%)")
                elif ctype == "status_change":
                    lines.append(f"  {name}: {change.get('old_status')} → {change.get('new_status')}")
                else:
                    lines.append(f"  {name}: {ctype}")

        # New research
        if obs.new_research:
            lines.append(f"\n--- NEW RESEARCH ({len(obs.new_research)}) ---")
            for item in obs.new_research:
                if item.get("type") == "trade_trigger":
                    lines.append(f"  !! TRIGGER: {item.get('symbol')} {item.get('direction')} ({item.get('signal_count')} signals)")
                else:
                    lines.append(f"  [{item.get('type', 'unknown')}] {item.get('title', item.get('file', ''))[:60]}")
                    if item.get("symbols"):
                        lines.append(f"        Symbols: {', '.join(item['symbols'][:5])}")

        # Action items
        if obs.action_items:
            lines.append(f"\n--- ACTION ITEMS ({len(obs.action_items)}) ---")
            for action in obs.action_items:
                priority_marker = "[HIGH]" if action.priority == "high" else "[MED]" if action.priority == "medium" else "[LOW]"
                lines.append(f"  {priority_marker} {action.action}")
                lines.append(f"         Reason: {action.reason}")

        # Stale sources
        if obs.stale_sources:
            lines.append(f"\n--- STALE DATA SOURCES ---")
            lines.append(f"  {', '.join(obs.stale_sources)}")

        # Research suggestions
        if obs.research_suggestions:
            lines.append(f"\n--- RESEARCH SUGGESTIONS ---")
            for sug in obs.research_suggestions:
                lines.append(f"  - {sug}")

        lines.append(f"\n{'='*60}")
        lines.append(f"Check completed in {obs.check_duration_seconds:.2f}s")

        return "\n".join(lines)


# Singleton instance
_operator_loop: OperatorLoop | None = None


def get_operator_loop() -> OperatorLoop:
    """Get global operator loop instance."""
    global _operator_loop
    if _operator_loop is None:
        _operator_loop = OperatorLoop()
    return _operator_loop


def run_operator_check() -> OperatorObservation:
    """Convenience function to run a single check."""
    return get_operator_loop().operator_check()
