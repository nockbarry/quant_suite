"""
Agent Activity Monitor for Automated Trading Firm.

Tracks Claude Code sessions, subagent spawns, decision making,
and provides visibility into the AI orchestration layer.

This is the "mission control" for watching Claude operate the trading system.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of agents in the system."""
    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    RESEARCH_WORKER = "research_worker"
    ALPHA_DISCOVERY = "alpha_discovery"
    HYPOTHESIS = "hypothesis"
    CRITIC = "critic"
    MONITOR = "monitor"
    NEWS_ANALYST = "news_analyst"
    MACRO_RESEARCH = "macro_research"
    REGIME_DETECTOR = "regime_detector"
    DATA_ACQUISITION = "data_acquisition"
    BRAINSTORM = "brainstorm"
    CLAUDE_CODE = "claude_code"  # The main Claude Code session


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


@dataclass
class AgentActivity:
    """Record of an agent's activity."""
    agent_id: str
    agent_type: AgentType
    task: str
    started_at: datetime
    completed_at: datetime | None = None
    status: AgentStatus = AgentStatus.RUNNING
    tokens_used: int = 0
    result_summary: str = ""
    parent_agent_id: str | None = None  # For subagents
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float:
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "task": self.task,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "tokens_used": self.tokens_used,
            "result_summary": self.result_summary,
            "parent_agent_id": self.parent_agent_id,
            "error_message": self.error_message,
        }


@dataclass
class DecisionRecord:
    """Record of a trading decision made by Claude."""
    decision_id: str
    timestamp: datetime
    symbol: str
    action: str  # BUY, SELL, HOLD
    confidence: float
    reasoning: str
    agent_id: str
    thesis_id: str | None = None
    adversarial_notes: str | None = None
    pre_mortem: str | None = None
    executed: bool = False
    outcome_pnl: float | None = None

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "reasoning": self.reasoning[:200] + "..." if len(self.reasoning) > 200 else self.reasoning,
            "agent_id": self.agent_id,
            "thesis_id": self.thesis_id,
            "executed": self.executed,
            "outcome_pnl": self.outcome_pnl,
        }


@dataclass
class ResearchCycle:
    """Record of a research cycle."""
    cycle_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: AgentStatus = AgentStatus.RUNNING
    experiments_run: int = 0
    insights_found: int = 0
    strategies_validated: int = 0
    best_sharpe: float | None = None
    agents_spawned: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "experiments_run": self.experiments_run,
            "insights_found": self.insights_found,
            "strategies_validated": self.strategies_validated,
            "best_sharpe": self.best_sharpe,
            "agents_spawned": self.agents_spawned,
            "summary": self.summary,
        }


class AgentActivityMonitor:
    """
    Monitors and tracks all agent activity in the trading system.

    Provides visibility into:
    - Active Claude Code sessions
    - Subagent spawns and completions
    - Decision making flow
    - Research cycle progress
    - Token usage and efficiency
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.logs_dir = self.results_dir / "logs"
        self.activity_log = self.logs_dir / "agent_activity.jsonl"

        # In-memory state
        self._activities: dict[str, AgentActivity] = {}
        self._decisions: list[DecisionRecord] = []
        self._research_cycles: dict[str, ResearchCycle] = {}
        self._token_usage: dict[str, int] = {}  # By agent type

        # Session tracking
        self._session_start: datetime | None = None
        self._session_id: str | None = None

        # Load recent history
        self._load_recent_history()

    def _load_recent_history(self) -> None:
        """Load recent activity from log file."""
        if not self.activity_log.exists():
            return

        try:
            cutoff = datetime.now() - timedelta(hours=24)
            with open(self.activity_log) as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                        if timestamp > cutoff:
                            # Reconstruct activity
                            if record.get("type") == "activity":
                                self._activities[record["agent_id"]] = AgentActivity(
                                    agent_id=record["agent_id"],
                                    agent_type=AgentType(record["agent_type"]),
                                    task=record.get("task", ""),
                                    started_at=datetime.fromisoformat(record["started_at"]),
                                    completed_at=datetime.fromisoformat(record["completed_at"]) if record.get("completed_at") else None,
                                    status=AgentStatus(record.get("status", "completed")),
                                    tokens_used=record.get("tokens_used", 0),
                                )
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        except Exception as e:
            logger.error(f"Error loading activity history: {e}")

    def start_session(self, session_id: str | None = None) -> str:
        """Start a new Claude Code session."""
        self._session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._session_start = datetime.now()

        # Create root activity
        self._activities[self._session_id] = AgentActivity(
            agent_id=self._session_id,
            agent_type=AgentType.CLAUDE_CODE,
            task="Claude Code session",
            started_at=self._session_start,
        )

        logger.info(f"Started session: {self._session_id}")
        return self._session_id

    def start_agent(
        self,
        agent_type: AgentType,
        task: str,
        parent_agent_id: str | None = None,
    ) -> str:
        """Record start of an agent/subagent — writes to DB via write_api."""
        # Write to DB as primary store
        try:
            from src.db.write_api import athena_db
            agent_id = athena_db.start_agent_run(
                agent_type=agent_type.value,
                task=task,
                parent_run_id=parent_agent_id or self._session_id,
            )
        except Exception as e:
            logger.warning(f"DB agent start failed: {e}")
            agent_id = f"{agent_type.value}_{datetime.now().strftime('%H%M%S')}"

        # In-memory cache
        self._activities[agent_id] = AgentActivity(
            agent_id=agent_id,
            agent_type=agent_type,
            task=task,
            started_at=datetime.now(),
            parent_agent_id=parent_agent_id or self._session_id,
        )

        # Append-only audit log
        self._log_activity("agent_start", self._activities[agent_id])
        return agent_id

    def complete_agent(
        self,
        agent_id: str,
        result_summary: str = "",
        tokens_used: int = 0,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """Record completion of an agent — writes to DB via write_api."""
        # Write to DB as primary store
        try:
            from src.db.write_api import athena_db
            if success:
                athena_db.complete_agent_run(agent_id, result_summary, tokens_used=tokens_used)
            else:
                athena_db.fail_agent_run(agent_id, error_message or "")
        except Exception as e:
            logger.warning(f"DB agent complete failed: {e}")

        # Update in-memory cache
        if agent_id not in self._activities:
            logger.warning(f"Unknown agent_id: {agent_id}")
            return

        activity = self._activities[agent_id]
        activity.completed_at = datetime.now()
        activity.status = AgentStatus.COMPLETED if success else AgentStatus.FAILED
        activity.result_summary = result_summary
        activity.tokens_used = tokens_used
        activity.error_message = error_message

        # Track token usage by type
        agent_type = activity.agent_type.value
        self._token_usage[agent_type] = self._token_usage.get(agent_type, 0) + tokens_used

        # Append-only audit log
        self._log_activity("agent_complete", activity)

    def record_decision(
        self,
        symbol: str,
        action: str,
        confidence: float,
        reasoning: str,
        agent_id: str | None = None,
        thesis_id: str | None = None,
        adversarial_notes: str | None = None,
        pre_mortem: str | None = None,
    ) -> str:
        """Record a trading decision."""
        decision_id = f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"

        decision = DecisionRecord(
            decision_id=decision_id,
            timestamp=datetime.now(),
            symbol=symbol,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            agent_id=agent_id or self._session_id or "unknown",
            thesis_id=thesis_id,
            adversarial_notes=adversarial_notes,
            pre_mortem=pre_mortem,
        )

        self._decisions.append(decision)
        self._log_activity("decision", decision)

        return decision_id

    def start_research_cycle(self, cycle_id: str | None = None) -> str:
        """Start a research cycle."""
        cycle_id = cycle_id or f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self._research_cycles[cycle_id] = ResearchCycle(
            cycle_id=cycle_id,
            started_at=datetime.now(),
        )

        self._log_activity("research_start", self._research_cycles[cycle_id])
        return cycle_id

    def update_research_cycle(
        self,
        cycle_id: str,
        experiments_run: int | None = None,
        insights_found: int | None = None,
        strategies_validated: int | None = None,
        best_sharpe: float | None = None,
        agent_spawned: str | None = None,
    ) -> None:
        """Update research cycle progress."""
        if cycle_id not in self._research_cycles:
            return

        cycle = self._research_cycles[cycle_id]
        if experiments_run is not None:
            cycle.experiments_run = experiments_run
        if insights_found is not None:
            cycle.insights_found = insights_found
        if strategies_validated is not None:
            cycle.strategies_validated = strategies_validated
        if best_sharpe is not None:
            cycle.best_sharpe = best_sharpe
        if agent_spawned:
            cycle.agents_spawned.append(agent_spawned)

    def complete_research_cycle(
        self,
        cycle_id: str,
        summary: str = "",
        success: bool = True,
    ) -> None:
        """Complete a research cycle."""
        if cycle_id not in self._research_cycles:
            return

        cycle = self._research_cycles[cycle_id]
        cycle.completed_at = datetime.now()
        cycle.status = AgentStatus.COMPLETED if success else AgentStatus.FAILED
        cycle.summary = summary

        self._log_activity("research_complete", cycle)

    def _log_activity(self, event_type: str, data: Any) -> None:
        """Log activity to file."""
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)

            record = {
                "timestamp": datetime.now().isoformat(),
                "type": event_type,
                **data.to_dict(),
            }

            with open(self.activity_log, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Error logging activity: {e}")

    def get_active_agents(self) -> list[AgentActivity]:
        """Get currently active agents."""
        return [
            a for a in self._activities.values()
            if a.status == AgentStatus.RUNNING
        ]

    def get_recent_decisions(self, n: int = 10) -> list[DecisionRecord]:
        """Get recent trading decisions."""
        return self._decisions[-n:]

    def get_active_research_cycle(self) -> ResearchCycle | None:
        """Get the currently active research cycle."""
        for cycle in self._research_cycles.values():
            if cycle.status == AgentStatus.RUNNING:
                return cycle
        return None

    def get_session_summary(self) -> dict:
        """Get summary of current session."""
        if not self._session_start:
            return {"status": "no_active_session"}

        duration = (datetime.now() - self._session_start).total_seconds()

        completed = [a for a in self._activities.values() if a.status == AgentStatus.COMPLETED]
        failed = [a for a in self._activities.values() if a.status == AgentStatus.FAILED]
        running = self.get_active_agents()

        return {
            "session_id": self._session_id,
            "started_at": self._session_start.isoformat(),
            "duration_minutes": round(duration / 60, 1),
            "agents": {
                "completed": len(completed),
                "failed": len(failed),
                "running": len(running),
            },
            "decisions_made": len([d for d in self._decisions if d.timestamp > self._session_start]),
            "total_tokens": sum(self._token_usage.values()),
            "tokens_by_agent": self._token_usage,
            "active_agents": [a.to_dict() for a in running],
        }

    def get_agent_efficiency(self) -> dict:
        """Get agent efficiency metrics."""
        by_type: dict[str, dict] = {}

        for activity in self._activities.values():
            if activity.status != AgentStatus.COMPLETED:
                continue

            agent_type = activity.agent_type.value
            if agent_type not in by_type:
                by_type[agent_type] = {
                    "count": 0,
                    "total_duration": 0,
                    "total_tokens": 0,
                    "failures": 0,
                }

            by_type[agent_type]["count"] += 1
            by_type[agent_type]["total_duration"] += activity.duration_seconds
            by_type[agent_type]["total_tokens"] += activity.tokens_used

        # Add failure counts
        for activity in self._activities.values():
            if activity.status == AgentStatus.FAILED:
                agent_type = activity.agent_type.value
                if agent_type in by_type:
                    by_type[agent_type]["failures"] += 1

        # Calculate averages
        for agent_type, stats in by_type.items():
            count = stats["count"]
            if count > 0:
                stats["avg_duration_seconds"] = round(stats["total_duration"] / count, 1)
                stats["avg_tokens"] = round(stats["total_tokens"] / count, 0)
                stats["success_rate"] = round((count - stats["failures"]) / (count + stats["failures"]) * 100 if count + stats["failures"] > 0 else 100, 1)

        return by_type

    def get_decision_quality(self) -> dict:
        """Get decision quality metrics."""
        if not self._decisions:
            return {"status": "no_decisions"}

        # Group by outcome
        executed = [d for d in self._decisions if d.executed]
        with_outcome = [d for d in executed if d.outcome_pnl is not None]

        if not with_outcome:
            return {
                "total_decisions": len(self._decisions),
                "executed": len(executed),
                "awaiting_outcome": len(executed) - len(with_outcome),
            }

        profitable = [d for d in with_outcome if d.outcome_pnl > 0]

        return {
            "total_decisions": len(self._decisions),
            "executed": len(executed),
            "with_outcome": len(with_outcome),
            "profitable": len(profitable),
            "win_rate": round(len(profitable) / len(with_outcome) * 100, 1),
            "avg_pnl": round(sum(d.outcome_pnl for d in with_outcome) / len(with_outcome), 2),
            "total_pnl": round(sum(d.outcome_pnl for d in with_outcome), 2),
            "by_confidence": self._group_decisions_by_confidence(with_outcome),
        }

    def _group_decisions_by_confidence(self, decisions: list[DecisionRecord]) -> dict:
        """Group decision outcomes by confidence level."""
        groups = {
            "high_90+": [],
            "good_75-90": [],
            "moderate_60-75": [],
            "low_<60": [],
        }

        for d in decisions:
            if d.confidence >= 0.90:
                groups["high_90+"].append(d.outcome_pnl)
            elif d.confidence >= 0.75:
                groups["good_75-90"].append(d.outcome_pnl)
            elif d.confidence >= 0.60:
                groups["moderate_60-75"].append(d.outcome_pnl)
            else:
                groups["low_<60"].append(d.outcome_pnl)

        return {
            k: {
                "count": len(v),
                "avg_pnl": round(sum(v) / len(v), 2) if v else 0,
                "win_rate": round(sum(1 for x in v if x > 0) / len(v) * 100, 1) if v else 0,
            }
            for k, v in groups.items()
        }

    def to_dict(self) -> dict:
        """Export full monitor state."""
        return {
            "session": self.get_session_summary(),
            "active_agents": [a.to_dict() for a in self.get_active_agents()],
            "recent_decisions": [d.to_dict() for d in self.get_recent_decisions()],
            "active_research": self.get_active_research_cycle().to_dict() if self.get_active_research_cycle() else None,
            "agent_efficiency": self.get_agent_efficiency(),
            "decision_quality": self.get_decision_quality(),
        }


# Singleton instance for global access
_monitor: AgentActivityMonitor | None = None


def get_agent_monitor() -> AgentActivityMonitor:
    """Get the global agent monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = AgentActivityMonitor()
    return _monitor


# Convenience functions for use in skills/agents
def log_agent_start(agent_type: str, task: str) -> str:
    """Log start of an agent."""
    return get_agent_monitor().start_agent(
        AgentType(agent_type) if agent_type in [e.value for e in AgentType] else AgentType.ORCHESTRATOR,
        task
    )


def log_agent_complete(agent_id: str, summary: str = "", tokens: int = 0, success: bool = True) -> None:
    """Log completion of an agent."""
    get_agent_monitor().complete_agent(agent_id, summary, tokens, success)


def log_decision(
    symbol: str,
    action: str,
    confidence: float,
    reasoning: str,
    thesis_id: str | None = None,
) -> str:
    """Log a trading decision."""
    return get_agent_monitor().record_decision(
        symbol, action, confidence, reasoning, thesis_id=thesis_id
    )
