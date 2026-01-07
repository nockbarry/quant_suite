"""Learning Log - Extract and persist learnings from trades.

Tracks:
- What happened in the trade
- What was learned
- How it changes approach
- Pattern extraction for future reference

Learnings are stored monthly in ~/quant_results/learnings/
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import json
import uuid
import logging

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class Learning:
    """A learning extracted from a trade outcome."""

    id: str
    created: datetime

    # Link to decision
    decision_id: str
    symbol: str
    action: str  # BUY, SELL, etc.

    # Outcome
    outcome: str  # win, loss, scratch
    pnl_pct: float
    hold_days: int

    # The learning itself
    what_happened: str
    what_i_learned: str
    how_this_changes_approach: str

    # Pattern extraction
    pattern_name: Optional[str] = None
    pattern_description: Optional[str] = None
    pattern_setup: Optional[str] = None
    pattern_typical_outcome: Optional[str] = None
    pattern_action: Optional[str] = None

    # Tags for retrieval
    tags: list[str] = field(default_factory=list)

    # Metadata
    thesis_id: Optional[str] = None
    confidence_at_entry: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created": self.created.isoformat(),
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "action": self.action,
            "outcome": self.outcome,
            "pnl_pct": self.pnl_pct,
            "hold_days": self.hold_days,
            "what_happened": self.what_happened,
            "what_i_learned": self.what_i_learned,
            "how_this_changes_approach": self.how_this_changes_approach,
            "pattern_name": self.pattern_name,
            "pattern_description": self.pattern_description,
            "pattern_setup": self.pattern_setup,
            "pattern_typical_outcome": self.pattern_typical_outcome,
            "pattern_action": self.pattern_action,
            "tags": self.tags,
            "thesis_id": self.thesis_id,
            "confidence_at_entry": self.confidence_at_entry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Learning":
        return cls(
            id=data["id"],
            created=datetime.fromisoformat(data["created"]),
            decision_id=data["decision_id"],
            symbol=data["symbol"],
            action=data["action"],
            outcome=data["outcome"],
            pnl_pct=data["pnl_pct"],
            hold_days=data["hold_days"],
            what_happened=data["what_happened"],
            what_i_learned=data["what_i_learned"],
            how_this_changes_approach=data["how_this_changes_approach"],
            pattern_name=data.get("pattern_name"),
            pattern_description=data.get("pattern_description"),
            pattern_setup=data.get("pattern_setup"),
            pattern_typical_outcome=data.get("pattern_typical_outcome"),
            pattern_action=data.get("pattern_action"),
            tags=data.get("tags", []),
            thesis_id=data.get("thesis_id"),
            confidence_at_entry=data.get("confidence_at_entry"),
        )

    def get_summary(self) -> str:
        """Get a brief summary of this learning."""
        outcome_emoji = "+" if self.outcome == "win" else "-" if self.outcome == "loss" else "~"
        return f"[{outcome_emoji}{self.pnl_pct:+.1f}%] {self.symbol}: {self.what_i_learned[:100]}"


@dataclass
class LearningSummary:
    """Lightweight summary for unified state."""

    id: str
    date: str
    symbol: str
    outcome: str
    pnl_pct: float
    key_learning: str
    tags: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "symbol": self.symbol,
            "outcome": self.outcome,
            "pnl_pct": self.pnl_pct,
            "key_learning": self.key_learning,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningSummary":
        return cls(
            id=data["id"],
            date=data["date"],
            symbol=data["symbol"],
            outcome=data["outcome"],
            pnl_pct=data["pnl_pct"],
            key_learning=data["key_learning"],
            tags=data["tags"],
        )


class LearningLog:
    """
    Manages trade learnings stored as monthly JSON files.

    Files: ~/quant_results/learnings/2026-01.json
    """

    def __init__(self, learnings_dir: Optional[Path] = None):
        """Initialize learning log.

        Args:
            learnings_dir: Directory for learning files.
                          Defaults to paths.learnings.
        """
        self.learnings_dir = learnings_dir or paths.learnings
        self.learnings_dir.mkdir(parents=True, exist_ok=True)

    def add_learning(self, learning: Learning) -> str:
        """
        Add a new learning.

        Args:
            learning: Learning to add.

        Returns:
            Learning ID.
        """
        month_file = self._get_month_file(learning.created)
        learnings = self._load_file(month_file)
        learnings.append(learning.to_dict())
        self._save_file(month_file, learnings)

        logger.info(f"Added learning: {learning.get_summary()}")
        return learning.id

    def create_learning(
        self,
        decision_id: str,
        symbol: str,
        action: str,
        outcome: str,
        pnl_pct: float,
        hold_days: int,
        what_happened: str,
        what_i_learned: str,
        how_this_changes_approach: str,
        pattern_name: Optional[str] = None,
        pattern_description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        thesis_id: Optional[str] = None,
        confidence_at_entry: Optional[float] = None,
    ) -> Learning:
        """
        Create and add a new learning.

        Args:
            decision_id: ID of the original trading decision
            symbol: Symbol traded
            action: Action taken (BUY, SELL, etc.)
            outcome: win, loss, or scratch
            pnl_pct: Realized P&L percentage
            hold_days: Days position was held
            what_happened: Description of what occurred
            what_i_learned: Key insight gained
            how_this_changes_approach: How to apply this going forward
            pattern_name: Optional pattern name for categorization
            pattern_description: Optional pattern details
            tags: Optional tags for retrieval
            thesis_id: Optional linked thesis
            confidence_at_entry: Confidence level when trade was entered

        Returns:
            Created Learning object.
        """
        learning = Learning(
            id=str(uuid.uuid4())[:8],
            created=datetime.now(),
            decision_id=decision_id,
            symbol=symbol,
            action=action,
            outcome=outcome,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            what_happened=what_happened,
            what_i_learned=what_i_learned,
            how_this_changes_approach=how_this_changes_approach,
            pattern_name=pattern_name,
            pattern_description=pattern_description,
            tags=tags or [],
            thesis_id=thesis_id,
            confidence_at_entry=confidence_at_entry,
        )

        self.add_learning(learning)
        return learning

    def get_recent(self, days: int = 30) -> list[Learning]:
        """
        Get learnings from recent days.

        Args:
            days: Number of days to look back.

        Returns:
            List of Learning objects, newest first.
        """
        learnings = []
        now = datetime.now()

        # Determine which monthly files to check
        months_to_check = set()
        for i in range(days):
            date = now - timedelta(days=i)
            months_to_check.add(date.strftime("%Y-%m"))

        # Load from each month
        for month in months_to_check:
            month_file = self.learnings_dir / f"{month}.json"
            for data in self._load_file(month_file):
                learning = Learning.from_dict(data)
                # Filter by date
                if (now - learning.created).days <= days:
                    learnings.append(learning)

        # Sort by date, newest first
        learnings.sort(key=lambda x: x.created, reverse=True)
        return learnings

    def get_by_symbol(self, symbol: str, months_back: int = 6) -> list[Learning]:
        """
        Get all learnings for a symbol.

        Args:
            symbol: Symbol to search for.
            months_back: How many months to search.

        Returns:
            List of Learning objects for that symbol.
        """
        learnings = []
        now = datetime.now()

        for i in range(months_back):
            month = (now - timedelta(days=i*30)).strftime("%Y-%m")
            month_file = self.learnings_dir / f"{month}.json"
            for data in self._load_file(month_file):
                if data["symbol"] == symbol:
                    learnings.append(Learning.from_dict(data))

        learnings.sort(key=lambda x: x.created, reverse=True)
        return learnings

    def get_by_tag(self, tag: str, months_back: int = 6) -> list[Learning]:
        """
        Get learnings with a specific tag.

        Args:
            tag: Tag to search for.
            months_back: How many months to search.

        Returns:
            List of Learning objects with that tag.
        """
        learnings = []
        now = datetime.now()

        for i in range(months_back):
            month = (now - timedelta(days=i*30)).strftime("%Y-%m")
            month_file = self.learnings_dir / f"{month}.json"
            for data in self._load_file(month_file):
                if tag in data.get("tags", []):
                    learnings.append(Learning.from_dict(data))

        learnings.sort(key=lambda x: x.created, reverse=True)
        return learnings

    def get_by_pattern(self, pattern_name: str, months_back: int = 12) -> list[Learning]:
        """
        Get learnings with a specific pattern.

        Args:
            pattern_name: Pattern name to search for.
            months_back: How many months to search.

        Returns:
            List of Learning objects with that pattern.
        """
        learnings = []
        now = datetime.now()

        for i in range(months_back):
            month = (now - timedelta(days=i*30)).strftime("%Y-%m")
            month_file = self.learnings_dir / f"{month}.json"
            for data in self._load_file(month_file):
                if data.get("pattern_name") == pattern_name:
                    learnings.append(Learning.from_dict(data))

        learnings.sort(key=lambda x: x.created, reverse=True)
        return learnings

    def get_patterns(self) -> dict[str, list[Learning]]:
        """
        Get all learnings grouped by pattern.

        Returns:
            Dict mapping pattern_name to list of learnings.
        """
        patterns: dict[str, list[Learning]] = {}

        for filepath in self.learnings_dir.glob("*.json"):
            for data in self._load_file(filepath):
                pattern = data.get("pattern_name")
                if pattern:
                    if pattern not in patterns:
                        patterns[pattern] = []
                    patterns[pattern].append(Learning.from_dict(data))

        return patterns

    def get_summaries(self, limit: int = 10) -> list[LearningSummary]:
        """Get lightweight summaries of recent learnings."""
        learnings = self.get_recent(days=30)[:limit]
        return [
            LearningSummary(
                id=l.id,
                date=l.created.strftime("%Y-%m-%d"),
                symbol=l.symbol,
                outcome=l.outcome,
                pnl_pct=l.pnl_pct,
                key_learning=l.what_i_learned[:100],
                tags=l.tags,
            )
            for l in learnings
        ]

    def get_statistics(self, days: int = 90) -> dict:
        """
        Get learning statistics.

        Args:
            days: Period to analyze.

        Returns:
            Statistics dict.
        """
        learnings = self.get_recent(days)

        if not learnings:
            return {"total": 0}

        wins = [l for l in learnings if l.outcome == "win"]
        losses = [l for l in learnings if l.outcome == "loss"]

        # Tag frequency
        tag_counts: dict[str, int] = {}
        for l in learnings:
            for tag in l.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "total": len(learnings),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(learnings) if learnings else 0,
            "avg_win_pnl": sum(l.pnl_pct for l in wins) / len(wins) if wins else 0,
            "avg_loss_pnl": sum(l.pnl_pct for l in losses) / len(losses) if losses else 0,
            "patterns_identified": len(set(l.pattern_name for l in learnings if l.pattern_name)),
            "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        }

    def _get_month_file(self, dt: datetime) -> Path:
        """Get the monthly file path for a date."""
        return self.learnings_dir / f"{dt.strftime('%Y-%m')}.json"

    def _load_file(self, filepath: Path) -> list[dict]:
        """Load learnings from a file."""
        if not filepath.exists():
            return []

        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return []

    def _save_file(self, filepath: Path, learnings: list[dict]) -> None:
        """Save learnings to a file."""
        with open(filepath, "w") as f:
            json.dump(learnings, f, indent=2)


def extract_learning_from_decision(
    decision: Any,
    what_happened: str,
    what_i_learned: str,
    how_this_changes_approach: str,
    pattern_name: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Learning:
    """
    Helper to extract a Learning from a closed TradingDecision.

    Args:
        decision: A TradingDecision object with outcome recorded
        what_happened: Description of what occurred
        what_i_learned: Key insight
        how_this_changes_approach: Future application
        pattern_name: Optional pattern category
        tags: Optional tags

    Returns:
        Learning object (not yet saved).
    """
    # Determine outcome
    if decision.realized_pnl_pct is None:
        outcome = "scratch"
        pnl = 0.0
    elif decision.realized_pnl_pct > 1.0:
        outcome = "win"
        pnl = decision.realized_pnl_pct
    elif decision.realized_pnl_pct < -1.0:
        outcome = "loss"
        pnl = decision.realized_pnl_pct
    else:
        outcome = "scratch"
        pnl = decision.realized_pnl_pct

    return Learning(
        id=str(uuid.uuid4())[:8],
        created=datetime.now(),
        decision_id=decision.id,
        symbol=decision.symbol,
        action=decision.action.value if hasattr(decision.action, 'value') else str(decision.action),
        outcome=outcome,
        pnl_pct=pnl,
        hold_days=decision.actual_hold_days or 0,
        what_happened=what_happened,
        what_i_learned=what_i_learned,
        how_this_changes_approach=how_this_changes_approach,
        pattern_name=pattern_name,
        tags=tags or [],
        thesis_id=getattr(decision, 'thesis_id', None),
        confidence_at_entry=decision.confidence,
    )
