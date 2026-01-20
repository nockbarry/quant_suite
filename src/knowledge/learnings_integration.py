"""Learning Integration - Link learnings to trade decisions.

Connects learnings extracted from EOD reviews to:
- Past decisions (what went wrong/right)
- Future decisions (apply learnings)
- Active theses (track pattern performance)

Created: 2026-01-20
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class LinkedLearning:
    """A learning linked to specific decisions."""

    learning_id: str
    content: str
    category: str  # "entry", "exit", "sizing", "timing", "thesis", "other"
    outcome: str  # "win", "loss", "neutral"

    # Links
    decision_ids: list[str] = field(default_factory=list)
    thesis_ids: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)

    # Metrics
    confidence: float = 0.5
    times_applied: int = 0
    times_successful: int = 0

    created: datetime = field(default_factory=datetime.now)
    last_applied: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "learning_id": self.learning_id,
            "content": self.content,
            "category": self.category,
            "outcome": self.outcome,
            "decision_ids": self.decision_ids,
            "thesis_ids": self.thesis_ids,
            "symbols": self.symbols,
            "confidence": self.confidence,
            "times_applied": self.times_applied,
            "times_successful": self.times_successful,
            "created": self.created.isoformat(),
            "last_applied": self.last_applied.isoformat() if self.last_applied else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinkedLearning":
        data["created"] = datetime.fromisoformat(data["created"])
        if data.get("last_applied"):
            data["last_applied"] = datetime.fromisoformat(data["last_applied"])
        return cls(**data)


@dataclass
class ApplicableLearning:
    """A learning that may apply to a current situation."""

    learning: LinkedLearning
    relevance_score: float  # 0-1
    reason: str
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            "learning": self.learning.to_dict(),
            "relevance_score": self.relevance_score,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
        }


class LearningsIntegration:
    """Integrate learnings with decision-making process.

    This system:
    1. Links learnings to past decisions
    2. Surfaces relevant learnings for current decisions
    3. Tracks learning application success
    4. Updates learning confidence based on outcomes
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (paths.knowledge / "linked_learnings")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.learnings_file = self.storage_path / "linked_learnings.json"

    def _load_learnings(self) -> dict[str, LinkedLearning]:
        """Load all linked learnings."""
        if not self.learnings_file.exists():
            return {}

        with open(self.learnings_file) as f:
            data = json.load(f)

        return {
            lid: LinkedLearning.from_dict(ldata)
            for lid, ldata in data.items()
        }

    def _save_learnings(self, learnings: dict[str, LinkedLearning]):
        """Save linked learnings."""
        with open(self.learnings_file, "w") as f:
            json.dump({lid: l.to_dict() for lid, l in learnings.items()}, f, indent=2)

    def add_learning(
        self,
        content: str,
        category: str,
        outcome: str,
        decision_ids: list[str] = None,
        thesis_ids: list[str] = None,
        symbols: list[str] = None,
        confidence: float = 0.5,
    ) -> LinkedLearning:
        """Add a new linked learning.

        Args:
            content: What was learned
            category: Type of learning
            outcome: Whether the original decision worked
            decision_ids: Related decision IDs
            thesis_ids: Related thesis IDs
            symbols: Related symbols
            confidence: Initial confidence (0-1)

        Returns:
            Created LinkedLearning
        """
        learning_id = f"learn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        learning = LinkedLearning(
            learning_id=learning_id,
            content=content,
            category=category,
            outcome=outcome,
            decision_ids=decision_ids or [],
            thesis_ids=thesis_ids or [],
            symbols=symbols or [],
            confidence=confidence,
        )

        learnings = self._load_learnings()
        learnings[learning_id] = learning
        self._save_learnings(learnings)

        logger.info(f"Added learning: {learning_id} - {content[:50]}...")

        return learning

    def link_decision(self, learning_id: str, decision_id: str):
        """Link a learning to a decision."""
        learnings = self._load_learnings()
        if learning_id in learnings:
            if decision_id not in learnings[learning_id].decision_ids:
                learnings[learning_id].decision_ids.append(decision_id)
            self._save_learnings(learnings)

    def link_thesis(self, learning_id: str, thesis_id: str):
        """Link a learning to a thesis."""
        learnings = self._load_learnings()
        if learning_id in learnings:
            if thesis_id not in learnings[learning_id].thesis_ids:
                learnings[learning_id].thesis_ids.append(thesis_id)
            self._save_learnings(learnings)

    def get_applicable_learnings(
        self,
        symbol: Optional[str] = None,
        thesis_id: Optional[str] = None,
        action: Optional[str] = None,  # "buy", "sell", "hold"
        context: Optional[dict] = None,
    ) -> list[ApplicableLearning]:
        """Get learnings applicable to a current decision.

        Args:
            symbol: Symbol being traded
            thesis_id: Thesis driving the decision
            action: Proposed action
            context: Additional context

        Returns:
            List of applicable learnings with relevance scores
        """
        learnings = self._load_learnings()
        applicable = []

        for learning in learnings.values():
            relevance = 0.0
            reasons = []

            # Symbol match
            if symbol and symbol in learning.symbols:
                relevance += 0.3
                reasons.append(f"Previously learned on {symbol}")

            # Thesis match
            if thesis_id and thesis_id in learning.thesis_ids:
                relevance += 0.3
                reasons.append("Linked to this thesis")

            # Category match (entry/exit matches action)
            if action:
                if action.lower() == "buy" and learning.category == "entry":
                    relevance += 0.2
                    reasons.append("Entry-related learning")
                elif action.lower() == "sell" and learning.category == "exit":
                    relevance += 0.2
                    reasons.append("Exit-related learning")
                elif learning.category == "sizing":
                    relevance += 0.1
                    reasons.append("Sizing-related learning")

            # Boost for high confidence learnings
            relevance += learning.confidence * 0.2

            # Boost for frequently successful learnings
            if learning.times_applied > 0:
                success_rate = learning.times_successful / learning.times_applied
                relevance += success_rate * 0.2

            # Skip low relevance
            if relevance < 0.2:
                continue

            # Generate suggested action
            if learning.outcome == "loss" and "don't" not in learning.content.lower():
                suggested = f"Caution: This learning was from a loss - {learning.content[:50]}"
            elif learning.outcome == "win":
                suggested = f"Apply this pattern: {learning.content[:50]}"
            else:
                suggested = f"Consider: {learning.content[:50]}"

            applicable.append(ApplicableLearning(
                learning=learning,
                relevance_score=min(1.0, relevance),
                reason="; ".join(reasons) if reasons else "General applicability",
                suggested_action=suggested,
            ))

        # Sort by relevance
        applicable.sort(key=lambda x: x.relevance_score, reverse=True)

        return applicable[:5]  # Top 5

    def record_application(
        self,
        learning_id: str,
        decision_id: str,
        was_successful: bool,
    ):
        """Record that a learning was applied to a decision.

        Args:
            learning_id: Learning that was applied
            decision_id: Decision it was applied to
            was_successful: Whether the decision worked out
        """
        learnings = self._load_learnings()

        if learning_id not in learnings:
            return

        learning = learnings[learning_id]
        learning.times_applied += 1
        if was_successful:
            learning.times_successful += 1
        learning.last_applied = datetime.now()

        # Link to decision
        if decision_id not in learning.decision_ids:
            learning.decision_ids.append(decision_id)

        # Update confidence based on track record
        if learning.times_applied >= 3:
            success_rate = learning.times_successful / learning.times_applied
            # Bayesian update toward success rate
            learning.confidence = 0.6 * learning.confidence + 0.4 * success_rate

        self._save_learnings(learnings)

        logger.info(
            f"Recorded learning application: {learning_id} -> {decision_id} "
            f"(success: {was_successful}, confidence: {learning.confidence:.2f})"
        )

    def get_learning_stats(self) -> dict:
        """Get statistics about learnings."""
        learnings = self._load_learnings()

        if not learnings:
            return {"total": 0}

        # By category
        by_category = {}
        for l in learnings.values():
            by_category[l.category] = by_category.get(l.category, 0) + 1

        # By outcome
        by_outcome = {}
        for l in learnings.values():
            by_outcome[l.outcome] = by_outcome.get(l.outcome, 0) + 1

        # Success rate
        total_applied = sum(l.times_applied for l in learnings.values())
        total_successful = sum(l.times_successful for l in learnings.values())
        success_rate = total_successful / total_applied if total_applied > 0 else 0

        # Most valuable learnings (high confidence, frequently successful)
        sorted_learnings = sorted(
            learnings.values(),
            key=lambda x: x.confidence * (x.times_successful + 1),
            reverse=True,
        )

        return {
            "total": len(learnings),
            "by_category": by_category,
            "by_outcome": by_outcome,
            "total_applications": total_applied,
            "overall_success_rate": success_rate,
            "top_learnings": [
                {"id": l.learning_id, "content": l.content[:80], "confidence": l.confidence}
                for l in sorted_learnings[:5]
            ],
        }


# Convenience functions
def get_learnings_for_decision(
    symbol: str,
    action: str,
    thesis_id: Optional[str] = None,
) -> list[ApplicableLearning]:
    """Get applicable learnings for a trade decision."""
    integration = LearningsIntegration()
    return integration.get_applicable_learnings(
        symbol=symbol,
        action=action,
        thesis_id=thesis_id,
    )


def record_learning(
    content: str,
    category: str,
    outcome: str,
    symbols: list[str] = None,
    decision_id: str = None,
) -> LinkedLearning:
    """Quick function to record a learning."""
    integration = LearningsIntegration()
    return integration.add_learning(
        content=content,
        category=category,
        outcome=outcome,
        symbols=symbols or [],
        decision_ids=[decision_id] if decision_id else [],
    )


if __name__ == "__main__":
    integration = LearningsIntegration()

    # Add sample learnings
    print("=== Learning Integration Demo ===\n")

    l1 = integration.add_learning(
        content="Entering on thesis strength beats entering on price weakness",
        category="entry",
        outcome="win",
        symbols=["SLB", "HAL"],
        thesis_ids=["venezuela_thesis"],
        confidence=0.7,
    )
    print(f"Added: {l1.content[:50]}...")

    l2 = integration.add_learning(
        content="Don't add to position when thesis signpost is pending",
        category="sizing",
        outcome="loss",
        symbols=["MU"],
        confidence=0.6,
    )
    print(f"Added: {l2.content[:50]}...")

    # Get applicable learnings
    print("\n--- Applicable Learnings for SLB BUY ---")
    applicable = integration.get_applicable_learnings(
        symbol="SLB",
        action="buy",
        thesis_id="venezuela_thesis",
    )

    for a in applicable:
        print(f"  [{a.relevance_score:.2f}] {a.learning.content[:60]}")
        print(f"       Reason: {a.reason}")

    # Show stats
    print("\n--- Stats ---")
    stats = integration.get_learning_stats()
    print(f"Total Learnings: {stats['total']}")
    print(f"By Category: {stats['by_category']}")
