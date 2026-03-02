"""Setup type performance scorer.

Queries DecisionRecord grouped by setup_type to answer:
- Which setup types have the best win rate?
- Which should we avoid?
- Should we trade this setup type?
"""

import logging
from dataclasses import dataclass

from src.intelligence.setup_types import normalize_setup_type

logger = logging.getLogger(__name__)


@dataclass
class SetupTypePerformance:
    setup_type: str
    total_decisions: int
    wins: int
    losses: int
    win_rate: float
    avg_return_pct: float
    avg_hold_days: float
    sample_adequate: bool  # >= 10 samples


class SetupScorer:
    """Scores decision performance by setup type."""

    MIN_SAMPLES = 5
    ADEQUATE_SAMPLES = 10

    def get_performance_by_type(self, min_samples: int = 5) -> list[SetupTypePerformance]:
        """Get performance breakdown by setup type."""
        from src.db.database import get_db
        from src.db.models import DecisionRecord

        try:
            with get_db() as session:
                rows = session.query(DecisionRecord).filter(
                    DecisionRecord.realized_pnl_pct.isnot(None)
                ).all()
        except Exception as e:
            logger.warning(f"SetupScorer query failed: {e}")
            return []

        # Group by normalized setup_type
        groups: dict[str, list] = {}
        for row in rows:
            st = normalize_setup_type(row.setup_type or "")
            groups.setdefault(st, []).append(row)

        results = []
        for st, decisions in groups.items():
            if len(decisions) < min_samples:
                continue

            wins = sum(1 for d in decisions if (d.realized_pnl_pct or 0) > 0)
            losses = len(decisions) - wins
            returns = [d.realized_pnl_pct or 0 for d in decisions]
            holds = [d.actual_hold_days or d.expected_hold_days or 0 for d in decisions]

            results.append(SetupTypePerformance(
                setup_type=st,
                total_decisions=len(decisions),
                wins=wins,
                losses=losses,
                win_rate=wins / len(decisions) if decisions else 0,
                avg_return_pct=sum(returns) / len(returns) if returns else 0,
                avg_hold_days=sum(holds) / len(holds) if holds else 0,
                sample_adequate=len(decisions) >= self.ADEQUATE_SAMPLES,
            ))

        return sorted(results, key=lambda x: x.win_rate, reverse=True)

    def get_best_setups(self) -> list[str]:
        """Setup types with >60% win rate and >=10 samples."""
        perfs = self.get_performance_by_type(min_samples=self.ADEQUATE_SAMPLES)
        return [p.setup_type for p in perfs if p.win_rate > 0.6]

    def get_worst_setups(self) -> list[str]:
        """Setup types with <40% win rate."""
        perfs = self.get_performance_by_type(min_samples=self.MIN_SAMPLES)
        return [p.setup_type for p in perfs if p.win_rate < 0.4]

    def should_trade_setup(self, setup_type: str) -> tuple[bool, str]:
        """Go/no-go recommendation for a setup type."""
        st = normalize_setup_type(setup_type)
        perfs = self.get_performance_by_type(min_samples=1)
        perf = next((p for p in perfs if p.setup_type == st), None)

        if perf is None:
            return True, f"No history for '{st}' — proceed with caution"

        if perf.total_decisions < self.MIN_SAMPLES:
            return True, f"Only {perf.total_decisions} samples for '{st}' — insufficient data"

        if perf.win_rate < 0.35:
            return False, f"'{st}' has {perf.win_rate:.0%} win rate ({perf.total_decisions} trades) — AVOID"

        if perf.win_rate < 0.45:
            return True, f"'{st}' has weak {perf.win_rate:.0%} win rate — reduce size"

        if perf.win_rate >= 0.65 and perf.sample_adequate:
            return True, f"'{st}' is strong: {perf.win_rate:.0%} win rate, avg {perf.avg_return_pct:+.1f}% — YOUR BEST SETUP"

        return True, f"'{st}': {perf.win_rate:.0%} win rate over {perf.total_decisions} trades"
