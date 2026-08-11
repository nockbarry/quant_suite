"""Cross-session insight and research tracking.

Maintains persistent storage of:
- Research insights across sessions
- Hypothesis outcomes
- Experiment results
- Pattern observations
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrackedInsight:
    """An insight tracked across sessions."""

    id: str
    title: str
    description: str
    category: str  # 'strategy', 'feature', 'pattern', 'failure', 'market'
    tags: list[str]
    evidence: dict[str, Any]
    source_session: str
    created_at: datetime
    updated_at: datetime
    confidence: float = 0.5  # 0-1
    validated: bool = False
    actionable: bool = True
    implemented: bool = False
    related_insights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "evidence": self.evidence,
            "source_session": self.source_session,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confidence": self.confidence,
            "validated": self.validated,
            "actionable": self.actionable,
            "implemented": self.implemented,
            "related_insights": self.related_insights,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackedInsight":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            category=data["category"],
            tags=data.get("tags", []),
            evidence=data.get("evidence", {}),
            source_session=data.get("source_session", "unknown"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            confidence=data.get("confidence", 0.5),
            validated=data.get("validated", False),
            actionable=data.get("actionable", True),
            implemented=data.get("implemented", False),
            related_insights=data.get("related_insights", []),
        )


@dataclass
class ExperimentRecord:
    """Record of an experiment across sessions."""

    id: str
    strategy: str
    symbol: str
    params: dict[str, Any]
    result: str  # 'success', 'failure', 'inconclusive'
    sharpe: float | None
    p_value: float | None
    notes: str
    session_id: str
    run_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "params": self.params,
            "result": self.result,
            "sharpe": self.sharpe,
            "p_value": self.p_value,
            "notes": self.notes,
            "session_id": self.session_id,
            "run_at": self.run_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentRecord":
        return cls(
            id=data["id"],
            strategy=data["strategy"],
            symbol=data["symbol"],
            params=data.get("params", {}),
            result=data["result"],
            sharpe=data.get("sharpe"),
            p_value=data.get("p_value"),
            notes=data.get("notes", ""),
            session_id=data.get("session_id", "unknown"),
            run_at=datetime.fromisoformat(data["run_at"]),
        )


class ResearchSessionTracker:
    """
    Tracks research progress across multiple sessions.

    Provides:
    - Persistent insight storage
    - Experiment deduplication
    - Pattern recognition across sessions
    - Search and retrieval
    """

    def __init__(
        self,
        storage_dir: str | Path = "/home/nock/quant_results/research_tracker",
    ):
        """
        Initialize session tracker.

        Args:
            storage_dir: Directory for persistent storage
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.insights_file = self.storage_dir / "insights.json"
        self.experiments_file = self.storage_dir / "experiments.json"
        self.patterns_file = self.storage_dir / "patterns.json"

        self.insights: dict[str, TrackedInsight] = {}
        self.experiments: dict[str, ExperimentRecord] = {}
        self.patterns: dict[str, dict[str, Any]] = {}

        self._load()

    def _load(self) -> None:
        """Load data from storage."""
        # Load insights
        if self.insights_file.exists():
            with open(self.insights_file) as f:
                data = json.load(f)
                self.insights = {
                    k: TrackedInsight.from_dict(v) for k, v in data.items()
                }
            logger.info(f"Loaded {len(self.insights)} insights")

        # Load experiments
        if self.experiments_file.exists():
            with open(self.experiments_file) as f:
                data = json.load(f)
                self.experiments = {
                    k: ExperimentRecord.from_dict(v) for k, v in data.items()
                }
            logger.info(f"Loaded {len(self.experiments)} experiments")

        # Load patterns
        if self.patterns_file.exists():
            with open(self.patterns_file) as f:
                self.patterns = json.load(f)
            logger.info(f"Loaded {len(self.patterns)} patterns")

    def _save(self) -> None:
        """Save data to storage."""
        # Save insights
        with open(self.insights_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.insights.items()}, f, indent=2)

        # Save experiments
        with open(self.experiments_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.experiments.items()}, f, indent=2)

        # Save patterns
        with open(self.patterns_file, "w") as f:
            json.dump(self.patterns, f, indent=2)

    def log_insight(
        self,
        title: str,
        description: str,
        category: str,
        evidence: dict[str, Any],
        session_id: str = "manual",
        tags: list[str] | None = None,
        confidence: float = 0.5,
    ) -> TrackedInsight:
        """
        Log a new insight.

        Args:
            title: Insight title
            description: Detailed description
            category: Category (strategy, feature, pattern, failure, market)
            evidence: Supporting evidence
            session_id: Source session ID
            tags: Optional tags for searching
            confidence: Confidence level 0-1

        Returns:
            Created TrackedInsight
        """
        insight_id = f"insight_{len(self.insights) + 1:04d}"
        now = datetime.now()

        insight = TrackedInsight(
            id=insight_id,
            title=title,
            description=description,
            category=category,
            tags=tags or [],
            evidence=evidence,
            source_session=session_id,
            created_at=now,
            updated_at=now,
            confidence=confidence,
        )

        self.insights[insight_id] = insight
        self._save()

        logger.info(f"Logged insight: {insight_id} - {title}")
        return insight

    def log_experiment(
        self,
        strategy: str,
        symbol: str,
        params: dict[str, Any],
        result: str,
        sharpe: float | None = None,
        p_value: float | None = None,
        notes: str = "",
        session_id: str = "manual",
    ) -> ExperimentRecord:
        """
        Log an experiment result.

        Args:
            strategy: Strategy name
            symbol: Symbol tested
            params: Strategy parameters
            result: Result ('success', 'failure', 'inconclusive')
            sharpe: Sharpe ratio if available
            p_value: MCPT p-value if available
            notes: Additional notes
            session_id: Source session ID

        Returns:
            Created ExperimentRecord
        """
        exp_id = f"exp_{len(self.experiments) + 1:04d}"

        record = ExperimentRecord(
            id=exp_id,
            strategy=strategy,
            symbol=symbol,
            params=params,
            result=result,
            sharpe=sharpe,
            p_value=p_value,
            notes=notes,
            session_id=session_id,
            run_at=datetime.now(),
        )

        self.experiments[exp_id] = record
        self._save()

        logger.info(f"Logged experiment: {exp_id} - {strategy}/{symbol} -> {result}")
        return record

    def log_pattern(
        self,
        pattern_name: str,
        description: str,
        evidence: dict[str, Any],
        confidence: float = 0.5,
    ) -> None:
        """
        Log an observed pattern.

        Args:
            pattern_name: Name/identifier for pattern
            description: Pattern description
            evidence: Supporting evidence
            confidence: Confidence level
        """
        if pattern_name in self.patterns:
            # Update existing pattern
            self.patterns[pattern_name]["observations"] += 1
            self.patterns[pattern_name]["last_observed"] = datetime.now().isoformat()
            self.patterns[pattern_name]["confidence"] = min(
                1.0, self.patterns[pattern_name]["confidence"] + 0.1
            )
            self.patterns[pattern_name]["evidence"].update(evidence)
        else:
            # New pattern
            self.patterns[pattern_name] = {
                "name": pattern_name,
                "description": description,
                "evidence": evidence,
                "confidence": confidence,
                "observations": 1,
                "first_observed": datetime.now().isoformat(),
                "last_observed": datetime.now().isoformat(),
            }

        self._save()
        logger.info(f"Logged pattern: {pattern_name}")

    def search_insights(
        self,
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        min_confidence: float = 0.0,
        actionable_only: bool = False,
        unimplemented_only: bool = False,
    ) -> list[TrackedInsight]:
        """
        Search insights with filters.

        Args:
            query: Text to search in title/description
            category: Filter by category
            tags: Filter by tags (any match)
            min_confidence: Minimum confidence threshold
            actionable_only: Only actionable insights
            unimplemented_only: Only unimplemented insights

        Returns:
            List of matching insights
        """
        results = []

        for insight in self.insights.values():
            # Apply filters
            if category and insight.category != category:
                continue
            if insight.confidence < min_confidence:
                continue
            if actionable_only and not insight.actionable:
                continue
            if unimplemented_only and insight.implemented:
                continue
            if tags and not any(t in insight.tags for t in tags):
                continue
            if query:
                query_lower = query.lower()
                if query_lower not in insight.title.lower() and query_lower not in insight.description.lower():
                    continue

            results.append(insight)

        # Sort by confidence descending
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def get_experiment_history(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
        result: str | None = None,
    ) -> list[ExperimentRecord]:
        """
        Get experiment history with filters.

        Args:
            strategy: Filter by strategy
            symbol: Filter by symbol
            result: Filter by result

        Returns:
            List of matching experiments
        """
        results = []

        for exp in self.experiments.values():
            if strategy and exp.strategy != strategy:
                continue
            if symbol and exp.symbol != symbol:
                continue
            if result and exp.result != result:
                continue
            results.append(exp)

        # Sort by run date descending
        results.sort(key=lambda x: x.run_at, reverse=True)
        return results

    def has_been_tested(
        self,
        strategy: str,
        symbol: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if a strategy-symbol combination has been tested.

        Args:
            strategy: Strategy name
            symbol: Symbol
            params: Optional params to match exactly

        Returns:
            True if tested before
        """
        for exp in self.experiments.values():
            if exp.strategy == strategy and exp.symbol == symbol:
                if params is None:
                    return True
                if exp.params == params:
                    return True
        return False

    def get_successful_strategies(
        self,
        min_sharpe: float = 0.5,
        max_p_value: float = 0.05,
    ) -> list[ExperimentRecord]:
        """
        Get all successful strategies meeting criteria.

        Args:
            min_sharpe: Minimum Sharpe ratio
            max_p_value: Maximum p-value

        Returns:
            List of successful experiments
        """
        results = []
        for exp in self.experiments.values():
            if exp.result != "success":
                continue
            if exp.sharpe is not None and exp.sharpe < min_sharpe:
                continue
            if exp.p_value is not None and exp.p_value > max_p_value:
                continue
            results.append(exp)

        results.sort(key=lambda x: x.sharpe or 0, reverse=True)
        return results

    def get_failed_combinations(self) -> list[tuple[str, str]]:
        """
        Get list of failed strategy-symbol combinations.

        Returns:
            List of (strategy, symbol) tuples that failed
        """
        failed = set()
        for exp in self.experiments.values():
            if exp.result == "failure":
                failed.add((exp.strategy, exp.symbol))
        return list(failed)

    def generate_summary_report(self) -> dict[str, Any]:
        """
        Generate a summary report of all tracked data.

        Returns:
            Summary dictionary
        """
        successful = self.get_successful_strategies()
        failed = self.get_failed_combinations()

        # Category breakdown
        category_counts = {}
        for insight in self.insights.values():
            cat = insight.category
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Strategy performance
        strategy_stats = {}
        for exp in self.experiments.values():
            if exp.strategy not in strategy_stats:
                strategy_stats[exp.strategy] = {"success": 0, "failure": 0, "inconclusive": 0}
            result_key = exp.result if exp.result in ("success", "failure", "inconclusive") else "failure"
            strategy_stats[exp.strategy][result_key] += 1

        return {
            "generated_at": datetime.now().isoformat(),
            "totals": {
                "insights": len(self.insights),
                "experiments": len(self.experiments),
                "patterns": len(self.patterns),
                "successful_strategies": len(successful),
                "failed_combinations": len(failed),
            },
            "insights_by_category": category_counts,
            "strategy_stats": strategy_stats,
            "top_patterns": [
                {"name": p["name"], "confidence": p["confidence"], "observations": p["observations"]}
                for p in sorted(self.patterns.values(), key=lambda x: x["confidence"], reverse=True)[:5]
            ],
            "actionable_insights": len([i for i in self.insights.values() if i.actionable and not i.implemented]),
        }

    def mark_insight_implemented(self, insight_id: str) -> None:
        """Mark an insight as implemented."""
        if insight_id in self.insights:
            self.insights[insight_id].implemented = True
            self.insights[insight_id].updated_at = datetime.now()
            self._save()
            logger.info(f"Marked {insight_id} as implemented")

    def validate_insight(self, insight_id: str, validated: bool = True) -> None:
        """Mark an insight as validated/invalidated."""
        if insight_id in self.insights:
            self.insights[insight_id].validated = validated
            self.insights[insight_id].updated_at = datetime.now()
            self._save()
            logger.info(f"Marked {insight_id} as validated={validated}")

    def link_insights(self, insight_id1: str, insight_id2: str) -> None:
        """Link two related insights."""
        if insight_id1 in self.insights and insight_id2 in self.insights:
            if insight_id2 not in self.insights[insight_id1].related_insights:
                self.insights[insight_id1].related_insights.append(insight_id2)
            if insight_id1 not in self.insights[insight_id2].related_insights:
                self.insights[insight_id2].related_insights.append(insight_id1)
            self._save()


# Global tracker instance
_tracker: ResearchSessionTracker | None = None


def get_tracker() -> ResearchSessionTracker:
    """Get or create global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = ResearchSessionTracker()
    return _tracker
