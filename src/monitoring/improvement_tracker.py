"""
Improvement Tracker - Continuous improvement loop for trading operations.

Tracks suggestions for improving:
- Agent performance (efficiency, accuracy)
- Signal quality (hit rate, IC)
- Thesis management (timing, sizing)
- Process optimization (workflows, automation)

Supports weekly reviews and learning accumulation.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class ImprovementSuggestion:
    """A suggestion for improving the trading system."""
    id: str
    category: str  # "agent", "signal", "thesis", "sizing", "process", "risk"
    priority: str  # "high", "medium", "low"
    title: str
    description: str
    evidence: list[str]
    suggested_action: str
    status: str  # "pending", "in_progress", "completed", "rejected", "deferred"
    created_at: datetime
    source: str  # "auto" (weekly review), "manual", "agent"
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    impact_measured: float | None = None  # Measured improvement if implemented
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
            "impact_measured": self.impact_measured,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImprovementSuggestion":
        return cls(
            id=data["id"],
            category=data["category"],
            priority=data["priority"],
            title=data["title"],
            description=data["description"],
            evidence=data.get("evidence", []),
            suggested_action=data["suggested_action"],
            status=data["status"],
            created_at=datetime.fromisoformat(data["created_at"]),
            source=data.get("source", "manual"),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolution_notes=data.get("resolution_notes"),
            impact_measured=data.get("impact_measured"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WeeklyReviewSummary:
    """Summary from a weekly improvement review."""
    review_date: datetime
    period_start: datetime
    period_end: datetime

    # Metrics analyzed
    agent_metrics: dict[str, Any]
    signal_metrics: dict[str, Any]
    portfolio_metrics: dict[str, Any]

    # Generated suggestions
    new_suggestions: list[ImprovementSuggestion]

    # Progress on existing suggestions
    suggestions_resolved: int
    suggestions_deferred: int
    suggestions_pending: int

    # Overall assessment
    overall_trend: str  # "improving", "stable", "degrading"
    key_findings: list[str]
    next_focus_areas: list[str]

    def to_dict(self) -> dict:
        return {
            "review_date": self.review_date.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "agent_metrics": self.agent_metrics,
            "signal_metrics": self.signal_metrics,
            "portfolio_metrics": self.portfolio_metrics,
            "new_suggestions_count": len(self.new_suggestions),
            "new_suggestions": [s.to_dict() for s in self.new_suggestions],
            "suggestions_resolved": self.suggestions_resolved,
            "suggestions_deferred": self.suggestions_deferred,
            "suggestions_pending": self.suggestions_pending,
            "overall_trend": self.overall_trend,
            "key_findings": self.key_findings,
            "next_focus_areas": self.next_focus_areas,
        }


class ImprovementTracker:
    """
    Tracks improvement suggestions and conducts weekly reviews.

    File structure:
    ~/quant_results/improvements/
        suggestions.json       - All suggestions
        reviews/
            review_2026-01-19.json
            review_2026-01-12.json
    """

    CATEGORIES = ["agent", "signal", "thesis", "sizing", "process", "risk"]
    PRIORITIES = ["high", "medium", "low"]
    STATUSES = ["pending", "in_progress", "completed", "rejected", "deferred"]

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.improvements_dir = self.results_dir / "improvements"
        self.reviews_dir = self.improvements_dir / "reviews"
        self.suggestions_file = self.improvements_dir / "suggestions.json"

        # Ensure directories exist
        self.improvements_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

        # Load existing suggestions
        self.suggestions: dict[str, ImprovementSuggestion] = {}
        self._load_suggestions()

    def _load_suggestions(self) -> None:
        """Load suggestions from file."""
        if self.suggestions_file.exists():
            try:
                with open(self.suggestions_file) as f:
                    data = json.load(f)
                    for item in data.get("suggestions", []):
                        suggestion = ImprovementSuggestion.from_dict(item)
                        self.suggestions[suggestion.id] = suggestion
            except Exception as e:
                logger.error(f"Error loading suggestions: {e}")

    def _save_suggestions(self) -> None:
        """Save suggestions to file."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "suggestions": [s.to_dict() for s in self.suggestions.values()],
            }
            with open(self.suggestions_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving suggestions: {e}")

    def add_suggestion(
        self,
        category: str,
        priority: str,
        title: str,
        description: str,
        suggested_action: str,
        evidence: list[str] | None = None,
        source: str = "manual",
        metadata: dict | None = None,
    ) -> ImprovementSuggestion:
        """Add a new improvement suggestion."""
        suggestion = ImprovementSuggestion(
            id=str(uuid4())[:8],
            category=category,
            priority=priority,
            title=title,
            description=description,
            evidence=evidence or [],
            suggested_action=suggested_action,
            status="pending",
            created_at=datetime.now(),
            source=source,
            metadata=metadata or {},
        )

        self.suggestions[suggestion.id] = suggestion
        self._save_suggestions()

        logger.info(f"Added suggestion: {suggestion.title} ({suggestion.id})")
        return suggestion

    def get_suggestion(self, suggestion_id: str) -> ImprovementSuggestion | None:
        """Get a suggestion by ID."""
        return self.suggestions.get(suggestion_id)

    def get_pending(self, category: str | None = None) -> list[ImprovementSuggestion]:
        """Get pending suggestions, optionally filtered by category."""
        suggestions = [
            s for s in self.suggestions.values()
            if s.status == "pending"
        ]

        if category:
            suggestions = [s for s in suggestions if s.category == category]

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s.priority, 99))

        return suggestions

    def get_by_status(self, status: str) -> list[ImprovementSuggestion]:
        """Get suggestions by status."""
        return [s for s in self.suggestions.values() if s.status == status]

    def resolve(
        self,
        suggestion_id: str,
        resolution_notes: str,
        status: str = "completed",
        impact_measured: float | None = None,
    ) -> bool:
        """Resolve a suggestion."""
        suggestion = self.suggestions.get(suggestion_id)
        if not suggestion:
            logger.error(f"Suggestion not found: {suggestion_id}")
            return False

        suggestion.status = status
        suggestion.resolved_at = datetime.now()
        suggestion.resolution_notes = resolution_notes
        suggestion.impact_measured = impact_measured

        self._save_suggestions()
        logger.info(f"Resolved suggestion {suggestion_id}: {status}")
        return True

    def update_status(self, suggestion_id: str, status: str) -> bool:
        """Update suggestion status."""
        suggestion = self.suggestions.get(suggestion_id)
        if not suggestion:
            return False

        suggestion.status = status
        self._save_suggestions()
        return True

    def run_weekly_review(self, dry_run: bool = False) -> WeeklyReviewSummary:
        """
        Run the weekly improvement review.

        Analyzes:
        1. Agent performance (completion rate, efficiency, token usage)
        2. Signal quality (hit rate, IC, trends)
        3. Portfolio metrics (returns, drawdown, win rate)

        Generates improvement suggestions and tracks progress.
        """
        now = datetime.now()
        period_end = now
        period_start = now - timedelta(days=7)

        # Gather metrics
        agent_metrics = self._analyze_agent_performance(period_start, period_end)
        signal_metrics = self._analyze_signal_quality(period_start, period_end)
        portfolio_metrics = self._analyze_portfolio_performance(period_start, period_end)

        # Generate suggestions based on analysis
        new_suggestions = self._generate_suggestions(
            agent_metrics, signal_metrics, portfolio_metrics
        )

        # Count suggestion progress
        resolved = len([s for s in self.suggestions.values()
                       if s.status == "completed" and s.resolved_at
                       and s.resolved_at >= period_start])
        deferred = len([s for s in self.suggestions.values() if s.status == "deferred"])
        pending = len([s for s in self.suggestions.values() if s.status == "pending"])

        # Determine overall trend
        overall_trend = self._determine_trend(agent_metrics, signal_metrics, portfolio_metrics)

        # Generate findings and focus areas
        key_findings = self._generate_findings(agent_metrics, signal_metrics, portfolio_metrics)
        next_focus_areas = self._determine_focus_areas(new_suggestions)

        review = WeeklyReviewSummary(
            review_date=now,
            period_start=period_start,
            period_end=period_end,
            agent_metrics=agent_metrics,
            signal_metrics=signal_metrics,
            portfolio_metrics=portfolio_metrics,
            new_suggestions=new_suggestions,
            suggestions_resolved=resolved,
            suggestions_deferred=deferred,
            suggestions_pending=pending,
            overall_trend=overall_trend,
            key_findings=key_findings,
            next_focus_areas=next_focus_areas,
        )

        if not dry_run:
            # Save review
            review_file = self.reviews_dir / f"review_{now.strftime('%Y-%m-%d')}.json"
            with open(review_file, "w") as f:
                json.dump(review.to_dict(), f, indent=2)

            # Add new suggestions
            for suggestion in new_suggestions:
                self.suggestions[suggestion.id] = suggestion
            self._save_suggestions()

        return review

    def _analyze_agent_performance(self, start: datetime, end: datetime) -> dict:
        """Analyze agent performance over the period."""
        metrics = {
            "total_runs": 0,
            "completed": 0,
            "failed": 0,
            "completion_rate": 0.0,
            "avg_duration_seconds": 0.0,
            "by_type": {},
        }

        activity_log = self.results_dir / "logs" / "agent_activity.jsonl"
        if not activity_log.exists():
            return metrics

        try:
            runs = []
            with open(activity_log) as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                        if start <= timestamp <= end:
                            runs.append(record)
                    except (json.JSONDecodeError, ValueError):
                        continue

            if runs:
                starts = [r for r in runs if r.get("type") == "agent_start"]
                completes = [r for r in runs if r.get("type") == "agent_complete"]

                metrics["total_runs"] = len(starts)
                metrics["completed"] = len([c for c in completes if c.get("status") == "completed"])
                metrics["failed"] = len([c for c in completes if c.get("status") == "failed"])

                if metrics["total_runs"] > 0:
                    metrics["completion_rate"] = metrics["completed"] / metrics["total_runs"]

                # Aggregate by agent type
                for complete in completes:
                    agent_type = complete.get("agent_type", "unknown")
                    if agent_type not in metrics["by_type"]:
                        metrics["by_type"][agent_type] = {"count": 0, "success": 0}
                    metrics["by_type"][agent_type]["count"] += 1
                    if complete.get("status") == "completed":
                        metrics["by_type"][agent_type]["success"] += 1

        except Exception as e:
            logger.error(f"Error analyzing agent performance: {e}")

        return metrics

    def _analyze_signal_quality(self, start: datetime, end: datetime) -> dict:
        """Analyze signal quality over the period."""
        metrics = {
            "signals_generated": 0,
            "signals_acted_on": 0,
            "act_rate": 0.0,
            "by_type": {},
        }

        # Load signal health if available
        signal_health_file = self.results_dir / "live" / "signal_health.json"
        if signal_health_file.exists():
            try:
                with open(signal_health_file) as f:
                    data = json.load(f)
                    for signal_name, stats in data.get("signals", {}).items():
                        metrics["by_type"][signal_name] = {
                            "ic": stats.get("ic_overall", 0),
                            "hit_rate": stats.get("hit_rate", 0),
                        }
            except Exception as e:
                logger.error(f"Error reading signal health: {e}")

        return metrics

    def _analyze_portfolio_performance(self, start: datetime, end: datetime) -> dict:
        """Analyze portfolio performance over the period."""
        metrics = {
            "return_pct": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "trades": 0,
        }

        # Load from decisions or portfolio logs
        decisions_dir = self.results_dir / "decisions"
        if decisions_dir.exists():
            try:
                trades = []
                for file in decisions_dir.glob("*.json"):
                    with open(file) as f:
                        decision = json.load(f)
                        timestamp_str = decision.get("timestamp", "")
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str)
                            if start <= timestamp <= end:
                                trades.append(decision)
                        except ValueError:
                            continue

                metrics["trades"] = len(trades)
                if trades:
                    # Calculate win rate from decisions that have outcomes
                    with_outcomes = [t for t in trades if t.get("outcome")]
                    if with_outcomes:
                        wins = [t for t in with_outcomes if t.get("outcome", {}).get("pnl", 0) > 0]
                        metrics["win_rate"] = len(wins) / len(with_outcomes)

            except Exception as e:
                logger.error(f"Error analyzing portfolio: {e}")

        return metrics

    def _generate_suggestions(
        self,
        agent_metrics: dict,
        signal_metrics: dict,
        portfolio_metrics: dict,
    ) -> list[ImprovementSuggestion]:
        """Generate improvement suggestions based on analysis."""
        suggestions = []
        now = datetime.now()

        # Agent suggestions
        if agent_metrics.get("completion_rate", 1.0) < 0.8:
            suggestions.append(ImprovementSuggestion(
                id=str(uuid4())[:8],
                category="agent",
                priority="high",
                title="Low agent completion rate",
                description=f"Agent completion rate is {agent_metrics['completion_rate']:.0%}, below 80% target",
                evidence=[
                    f"Total runs: {agent_metrics['total_runs']}",
                    f"Completed: {agent_metrics['completed']}",
                    f"Failed: {agent_metrics['failed']}",
                ],
                suggested_action="Review failed agent logs, identify common failure patterns",
                status="pending",
                created_at=now,
                source="auto",
            ))

        # Signal suggestions
        for signal_name, stats in signal_metrics.get("by_type", {}).items():
            ic = stats.get("ic", 0)
            if ic < 0.01 and ic > -0.02:  # Near zero or slightly negative
                suggestions.append(ImprovementSuggestion(
                    id=str(uuid4())[:8],
                    category="signal",
                    priority="medium",
                    title=f"{signal_name} signal degradation",
                    description=f"Signal IC dropped to {ic:.4f}, near zero predictive power",
                    evidence=[f"IC: {ic:.4f}"],
                    suggested_action="Review signal logic, consider feature engineering or removal",
                    status="pending",
                    created_at=now,
                    source="auto",
                ))

        # Portfolio suggestions
        if portfolio_metrics.get("win_rate", 0.5) < 0.4:
            suggestions.append(ImprovementSuggestion(
                id=str(uuid4())[:8],
                category="sizing",
                priority="high",
                title="Low win rate",
                description=f"Win rate is {portfolio_metrics['win_rate']:.0%}, below 40%",
                evidence=[f"Trades: {portfolio_metrics['trades']}"],
                suggested_action="Review entry criteria, consider tighter filters or confirmation signals",
                status="pending",
                created_at=now,
                source="auto",
            ))

        if portfolio_metrics.get("max_drawdown", 0) < -0.10:
            suggestions.append(ImprovementSuggestion(
                id=str(uuid4())[:8],
                category="risk",
                priority="high",
                title="Significant drawdown",
                description=f"Max drawdown of {portfolio_metrics['max_drawdown']:.0%} exceeds 10% threshold",
                evidence=[],
                suggested_action="Review position sizing, consider tighter stop losses",
                status="pending",
                created_at=now,
                source="auto",
            ))

        return suggestions

    def _determine_trend(
        self,
        agent_metrics: dict,
        signal_metrics: dict,
        portfolio_metrics: dict,
    ) -> str:
        """Determine overall system trend."""
        scores = []

        # Agent score
        completion_rate = agent_metrics.get("completion_rate", 0.5)
        scores.append(1 if completion_rate >= 0.9 else 0 if completion_rate >= 0.7 else -1)

        # Portfolio score
        win_rate = portfolio_metrics.get("win_rate", 0.5)
        scores.append(1 if win_rate >= 0.55 else 0 if win_rate >= 0.45 else -1)

        avg_score = sum(scores) / len(scores) if scores else 0

        if avg_score > 0.3:
            return "improving"
        elif avg_score < -0.3:
            return "degrading"
        else:
            return "stable"

    def _generate_findings(
        self,
        agent_metrics: dict,
        signal_metrics: dict,
        portfolio_metrics: dict,
    ) -> list[str]:
        """Generate key findings from the review."""
        findings = []

        # Agent findings
        if agent_metrics.get("total_runs", 0) > 0:
            findings.append(
                f"Ran {agent_metrics['total_runs']} agent tasks with "
                f"{agent_metrics.get('completion_rate', 0):.0%} completion rate"
            )

        # Portfolio findings
        if portfolio_metrics.get("trades", 0) > 0:
            findings.append(
                f"Made {portfolio_metrics['trades']} trades with "
                f"{portfolio_metrics.get('win_rate', 0):.0%} win rate"
            )

        # Signal findings
        signal_count = len(signal_metrics.get("by_type", {}))
        if signal_count > 0:
            findings.append(f"Monitored {signal_count} signal types")

        return findings

    def _determine_focus_areas(self, new_suggestions: list[ImprovementSuggestion]) -> list[str]:
        """Determine focus areas based on suggestions."""
        # Count by category
        category_counts = {}
        for s in new_suggestions:
            category_counts[s.category] = category_counts.get(s.category, 0) + 1

        # High priority suggestions
        high_priority = [s for s in new_suggestions if s.priority == "high"]

        focus_areas = []

        if high_priority:
            focus_areas.append(f"Address {len(high_priority)} high-priority improvements")

        for category, count in sorted(category_counts.items(), key=lambda x: -x[1])[:3]:
            if count > 0:
                focus_areas.append(f"Review {category} ({count} suggestions)")

        return focus_areas

    def get_summary(self) -> dict:
        """Get summary of current improvement tracking status."""
        by_status = {}
        by_category = {}
        by_priority = {}

        for s in self.suggestions.values():
            by_status[s.status] = by_status.get(s.status, 0) + 1
            by_category[s.category] = by_category.get(s.category, 0) + 1
            by_priority[s.priority] = by_priority.get(s.priority, 0) + 1

        recent_resolved = [
            s for s in self.suggestions.values()
            if s.resolved_at and (datetime.now() - s.resolved_at).days < 7
        ]

        return {
            "total_suggestions": len(self.suggestions),
            "by_status": by_status,
            "by_category": by_category,
            "by_priority": by_priority,
            "recent_resolved": len(recent_resolved),
            "pending_high_priority": len([
                s for s in self.suggestions.values()
                if s.status == "pending" and s.priority == "high"
            ]),
        }


# Singleton instance
_tracker: ImprovementTracker | None = None


def get_improvement_tracker() -> ImprovementTracker:
    """Get global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = ImprovementTracker()
    return _tracker


def add_improvement(
    category: str,
    priority: str,
    title: str,
    description: str,
    suggested_action: str,
    **kwargs,
) -> ImprovementSuggestion:
    """Convenience function to add an improvement suggestion."""
    return get_improvement_tracker().add_suggestion(
        category=category,
        priority=priority,
        title=title,
        description=description,
        suggested_action=suggested_action,
        **kwargs,
    )
