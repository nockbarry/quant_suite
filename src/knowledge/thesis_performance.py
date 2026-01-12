"""Thesis Performance Attribution.

Tracks P&L and performance metrics by investment thesis to answer:
- "Which theses are profitable?"
- "What is the win rate per thesis?"
- "Which positions contributed most to thesis performance?"
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from src.core.paths import paths
from src.knowledge.thesis import ThesisTracker, Thesis
from src.knowledge.learnings import LearningLog, Learning
from src.decision.decision_logger import DecisionLogger, TradingDecision, DecisionStatus

logger = logging.getLogger(__name__)


@dataclass
class PositionPerformance:
    """Performance metrics for a single position within a thesis."""

    symbol: str
    num_trades: int = 0
    wins: int = 0
    losses: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_hold_days: int = 0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        """Win rate for this position."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.0

    @property
    def avg_hold_days(self) -> float:
        """Average hold days per trade."""
        return self.total_hold_days / self.num_trades if self.num_trades > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "num_trades": self.num_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_hold_days": self.total_hold_days,
            "avg_hold_days": self.avg_hold_days,
            "best_trade_pnl": self.best_trade_pnl,
            "worst_trade_pnl": self.worst_trade_pnl,
        }


@dataclass
class ThesisPerformanceMetrics:
    """Comprehensive performance metrics for an investment thesis."""

    thesis_id: str
    thesis_name: str
    thesis_status: str
    current_conviction: float

    # Overall P&L
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0

    # Trade statistics
    num_trades: int = 0
    wins: int = 0
    losses: int = 0
    scratches: int = 0

    # Timing
    avg_hold_days: float = 0.0
    total_hold_days: int = 0

    # Best/Worst
    best_trade: Optional[dict] = None
    worst_trade: Optional[dict] = None

    # Per-position breakdown
    position_performance: dict[str, PositionPerformance] = field(default_factory=dict)

    # Active positions
    positions_active: list[str] = field(default_factory=list)

    # Learnings from this thesis
    learnings_count: int = 0
    key_patterns: list[str] = field(default_factory=list)

    # Time analysis
    days_active: int = 0
    first_trade_date: Optional[datetime] = None
    last_trade_date: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        """Overall win rate for the thesis."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.0

    @property
    def total_pnl(self) -> float:
        """Total P&L (realized + unrealized)."""
        return self.total_realized_pnl + self.total_unrealized_pnl

    @property
    def avg_pnl_per_trade(self) -> float:
        """Average P&L per trade."""
        return self.total_realized_pnl / self.num_trades if self.num_trades > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "thesis_status": self.thesis_status,
            "current_conviction": self.current_conviction,
            "total_realized_pnl": self.total_realized_pnl,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_pnl": self.total_pnl,
            "num_trades": self.num_trades,
            "wins": self.wins,
            "losses": self.losses,
            "scratches": self.scratches,
            "win_rate": self.win_rate,
            "avg_hold_days": self.avg_hold_days,
            "total_hold_days": self.total_hold_days,
            "avg_pnl_per_trade": self.avg_pnl_per_trade,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "position_performance": {
                k: v.to_dict() for k, v in self.position_performance.items()
            },
            "positions_active": self.positions_active,
            "learnings_count": self.learnings_count,
            "key_patterns": self.key_patterns,
            "days_active": self.days_active,
            "first_trade_date": self.first_trade_date.isoformat() if self.first_trade_date else None,
            "last_trade_date": self.last_trade_date.isoformat() if self.last_trade_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisPerformanceMetrics":
        """Create from dictionary."""
        metrics = cls(
            thesis_id=data["thesis_id"],
            thesis_name=data["thesis_name"],
            thesis_status=data["thesis_status"],
            current_conviction=data["current_conviction"],
            total_realized_pnl=data.get("total_realized_pnl", 0.0),
            total_unrealized_pnl=data.get("total_unrealized_pnl", 0.0),
            num_trades=data.get("num_trades", 0),
            wins=data.get("wins", 0),
            losses=data.get("losses", 0),
            scratches=data.get("scratches", 0),
            avg_hold_days=data.get("avg_hold_days", 0.0),
            total_hold_days=data.get("total_hold_days", 0),
            best_trade=data.get("best_trade"),
            worst_trade=data.get("worst_trade"),
            positions_active=data.get("positions_active", []),
            learnings_count=data.get("learnings_count", 0),
            key_patterns=data.get("key_patterns", []),
            days_active=data.get("days_active", 0),
            first_trade_date=datetime.fromisoformat(data["first_trade_date"]) if data.get("first_trade_date") else None,
            last_trade_date=datetime.fromisoformat(data["last_trade_date"]) if data.get("last_trade_date") else None,
        )
        return metrics

    def get_summary(self) -> str:
        """Get a brief text summary."""
        status = "+" if self.total_pnl > 0 else "-" if self.total_pnl < 0 else "~"
        return (
            f"[{status}${abs(self.total_pnl):.0f}] {self.thesis_name}: "
            f"{self.num_trades} trades, {self.win_rate:.0%} win rate"
        )


class ThesisPerformanceTracker:
    """
    Tracks and calculates performance metrics for investment theses.

    Aggregates data from:
    - ThesisTracker (thesis definitions and conviction)
    - DecisionLogger (trading decisions linked to theses)
    - LearningLog (learnings extracted from thesis trades)
    """

    def __init__(
        self,
        thesis_dir: Optional[Path] = None,
        decisions_dir: Optional[Path] = None,
        learnings_dir: Optional[Path] = None,
    ):
        """Initialize the tracker.

        Args:
            thesis_dir: Directory containing thesis YAML files
            decisions_dir: Directory containing decision JSON files
            learnings_dir: Directory containing learning JSON files
        """
        self.thesis_tracker = ThesisTracker(thesis_dir or paths.theses)
        self.decision_logger = DecisionLogger(decisions_dir or paths.decisions)
        self.learning_log = LearningLog(learnings_dir or paths.learnings)

    def get_performance(
        self,
        thesis_id: str,
        days: int = 90,
        include_unrealized: bool = True,
    ) -> Optional[ThesisPerformanceMetrics]:
        """Calculate performance metrics for a specific thesis.

        Args:
            thesis_id: ID of the thesis to analyze
            days: Number of days of history to consider
            include_unrealized: Whether to include unrealized P&L

        Returns:
            ThesisPerformanceMetrics or None if thesis not found
        """
        thesis = self.thesis_tracker.get_thesis(thesis_id)
        if not thesis:
            logger.warning(f"Thesis {thesis_id} not found")
            return None

        # Get all decisions for this thesis
        decisions = self.decision_logger.get_decisions_by_thesis(thesis_id, days=days)

        # Get learnings linked to this thesis
        learnings = self._get_learnings_for_thesis(thesis, days)

        # Build metrics
        metrics = ThesisPerformanceMetrics(
            thesis_id=thesis.id,
            thesis_name=thesis.name,
            thesis_status=thesis.status,
            current_conviction=thesis.conviction,
            positions_active=thesis.positions,
            days_active=(datetime.now() - thesis.created).days,
        )

        # Process decisions
        self._process_decisions(metrics, decisions)

        # Process learnings
        self._process_learnings(metrics, learnings)

        return metrics

    def get_all_performance(
        self,
        days: int = 90,
        include_inactive: bool = False,
    ) -> list[ThesisPerformanceMetrics]:
        """Get performance metrics for all theses.

        Args:
            days: Number of days of history to consider
            include_inactive: Whether to include invalidated/expired theses

        Returns:
            List of ThesisPerformanceMetrics sorted by total P&L
        """
        if include_inactive:
            theses = self.thesis_tracker.get_all_theses()
        else:
            theses = self.thesis_tracker.get_active_theses()

        metrics_list = []
        for thesis in theses:
            metrics = self.get_performance(thesis.id, days=days)
            if metrics:
                metrics_list.append(metrics)

        # Sort by total P&L descending
        metrics_list.sort(key=lambda x: x.total_pnl, reverse=True)
        return metrics_list

    def get_top_performers(self, n: int = 5, days: int = 90) -> list[ThesisPerformanceMetrics]:
        """Get the top N performing theses by P&L.

        Args:
            n: Number of theses to return
            days: Number of days of history

        Returns:
            Top N theses by total P&L
        """
        all_metrics = self.get_all_performance(days=days, include_inactive=True)
        return all_metrics[:n]

    def get_worst_performers(self, n: int = 5, days: int = 90) -> list[ThesisPerformanceMetrics]:
        """Get the worst N performing theses by P&L.

        Args:
            n: Number of theses to return
            days: Number of days of history

        Returns:
            Worst N theses by total P&L
        """
        all_metrics = self.get_all_performance(days=days, include_inactive=True)
        return list(reversed(all_metrics[-n:]))

    def get_thesis_leaderboard(self, days: int = 90) -> str:
        """Generate a text leaderboard of thesis performance.

        Args:
            days: Number of days of history

        Returns:
            Markdown formatted leaderboard
        """
        all_metrics = self.get_all_performance(days=days, include_inactive=True)

        if not all_metrics:
            return "No thesis performance data available."

        lines = [
            "# Thesis Performance Leaderboard",
            "",
            f"Period: Last {days} days",
            "",
            "| Rank | Thesis | Status | P&L | Win Rate | Trades | Conviction |",
            "|------|--------|--------|-----|----------|--------|------------|",
        ]

        for i, m in enumerate(all_metrics, 1):
            pnl_str = f"${m.total_pnl:+,.0f}" if abs(m.total_pnl) >= 1 else "~$0"
            lines.append(
                f"| {i} | {m.thesis_name[:20]} | {m.thesis_status} | {pnl_str} | "
                f"{m.win_rate:.0%} | {m.num_trades} | {m.current_conviction:.0f}% |"
            )

        return "\n".join(lines)

    def get_position_attribution(self, thesis_id: str, days: int = 90) -> dict[str, PositionPerformance]:
        """Get performance breakdown by position for a thesis.

        Args:
            thesis_id: Thesis to analyze
            days: Number of days of history

        Returns:
            Dict mapping symbol to PositionPerformance
        """
        metrics = self.get_performance(thesis_id, days=days)
        if metrics:
            return metrics.position_performance
        return {}

    def compare_theses(
        self,
        thesis_ids: list[str],
        days: int = 90,
    ) -> list[ThesisPerformanceMetrics]:
        """Compare specific theses.

        Args:
            thesis_ids: List of thesis IDs to compare
            days: Number of days of history

        Returns:
            List of metrics for the specified theses
        """
        metrics_list = []
        for tid in thesis_ids:
            metrics = self.get_performance(tid, days=days)
            if metrics:
                metrics_list.append(metrics)

        metrics_list.sort(key=lambda x: x.total_pnl, reverse=True)
        return metrics_list

    def _process_decisions(
        self,
        metrics: ThesisPerformanceMetrics,
        decisions: list[TradingDecision],
    ) -> None:
        """Process decisions and update metrics."""
        for decision in decisions:
            # Track trade dates
            if metrics.first_trade_date is None or decision.timestamp < metrics.first_trade_date:
                metrics.first_trade_date = decision.timestamp
            if metrics.last_trade_date is None or decision.timestamp > metrics.last_trade_date:
                metrics.last_trade_date = decision.timestamp

            # Only count closed trades for realized P&L
            if decision.status == DecisionStatus.CLOSED and decision.realized_pnl is not None:
                metrics.num_trades += 1
                metrics.total_realized_pnl += decision.realized_pnl

                # Win/loss tracking
                if decision.realized_pnl_pct is not None:
                    if decision.realized_pnl_pct > 1.0:
                        metrics.wins += 1
                    elif decision.realized_pnl_pct < -1.0:
                        metrics.losses += 1
                    else:
                        metrics.scratches += 1

                # Hold days
                if decision.actual_hold_days:
                    metrics.total_hold_days += decision.actual_hold_days

                # Best/worst trade tracking
                trade_info = {
                    "symbol": decision.symbol,
                    "pnl": decision.realized_pnl,
                    "pnl_pct": decision.realized_pnl_pct,
                    "date": decision.timestamp.isoformat(),
                }

                if metrics.best_trade is None or decision.realized_pnl > metrics.best_trade.get("pnl", 0):
                    metrics.best_trade = trade_info
                if metrics.worst_trade is None or decision.realized_pnl < metrics.worst_trade.get("pnl", 0):
                    metrics.worst_trade = trade_info

                # Per-position tracking
                self._update_position_performance(metrics, decision)

        # Calculate averages
        if metrics.num_trades > 0:
            metrics.avg_hold_days = metrics.total_hold_days / metrics.num_trades

    def _update_position_performance(
        self,
        metrics: ThesisPerformanceMetrics,
        decision: TradingDecision,
    ) -> None:
        """Update per-position performance metrics."""
        symbol = decision.symbol

        if symbol not in metrics.position_performance:
            metrics.position_performance[symbol] = PositionPerformance(symbol=symbol)

        pos = metrics.position_performance[symbol]
        pos.num_trades += 1

        if decision.realized_pnl is not None:
            pos.realized_pnl += decision.realized_pnl

            if decision.realized_pnl > pos.best_trade_pnl:
                pos.best_trade_pnl = decision.realized_pnl
            if decision.realized_pnl < pos.worst_trade_pnl:
                pos.worst_trade_pnl = decision.realized_pnl

        if decision.realized_pnl_pct is not None:
            if decision.realized_pnl_pct > 1.0:
                pos.wins += 1
            elif decision.realized_pnl_pct < -1.0:
                pos.losses += 1

        if decision.actual_hold_days:
            pos.total_hold_days += decision.actual_hold_days

    def _process_learnings(
        self,
        metrics: ThesisPerformanceMetrics,
        learnings: list[Learning],
    ) -> None:
        """Process learnings and update metrics."""
        metrics.learnings_count = len(learnings)

        # Extract unique patterns
        patterns = set()
        for learning in learnings:
            if learning.pattern_name:
                patterns.add(learning.pattern_name)

        metrics.key_patterns = list(patterns)

    def _get_learnings_for_thesis(self, thesis: Thesis, days: int) -> list[Learning]:
        """Get learnings associated with a thesis."""
        learnings = []

        # Get learnings for all positions in the thesis
        for symbol in thesis.positions:
            symbol_learnings = self.learning_log.get_by_symbol(symbol, months_back=max(1, days // 30 + 1))
            # Filter to those with matching thesis_id
            for learning in symbol_learnings:
                if learning.thesis_id == thesis.id:
                    learnings.append(learning)

        # Deduplicate by ID
        seen_ids = set()
        unique_learnings = []
        for learning in learnings:
            if learning.id not in seen_ids:
                seen_ids.add(learning.id)
                unique_learnings.append(learning)

        return unique_learnings


def get_thesis_performance_summary(days: int = 90) -> dict:
    """Quick utility to get thesis performance summary.

    Args:
        days: Number of days of history

    Returns:
        Summary dict with top performers, worst performers, and totals
    """
    tracker = ThesisPerformanceTracker()
    all_metrics = tracker.get_all_performance(days=days, include_inactive=True)

    if not all_metrics:
        return {
            "total_theses": 0,
            "total_pnl": 0.0,
            "top_performers": [],
            "worst_performers": [],
        }

    return {
        "total_theses": len(all_metrics),
        "total_pnl": sum(m.total_pnl for m in all_metrics),
        "total_trades": sum(m.num_trades for m in all_metrics),
        "overall_win_rate": (
            sum(m.wins for m in all_metrics) /
            sum(m.wins + m.losses for m in all_metrics)
            if sum(m.wins + m.losses for m in all_metrics) > 0
            else 0.0
        ),
        "top_performers": [m.to_dict() for m in all_metrics[:3]],
        "worst_performers": [m.to_dict() for m in all_metrics[-3:] if m.total_pnl < 0],
    }
