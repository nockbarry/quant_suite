"""Tests for rule-engine -> target-adjustment folding (Phase 5)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.portfolio.adjustments import compute_rule_adjustments


def test_stop_loss_breach_yields_zero_weight():
    positions = [
        {"symbol": "AAA", "unrealized_pnl_pct": -16.0},  # breach -> exit
        {"symbol": "BBB", "unrealized_pnl_pct": -14.9},  # safe
        {"symbol": "CCC", "unrealized_pnl_pct": 8.0},    # winner
    ]
    adj = compute_rule_adjustments(positions)
    assert len(adj) == 1
    assert adj[0].symbol == "AAA" and adj[0].weight == 0.0
    assert adj[0].bounded_by == "stop_loss"


def test_missing_pnl_is_skipped():
    positions = [
        {"symbol": "AAA", "unrealized_pnl_pct": None},
        {"symbol": "BBB"},
    ]
    assert compute_rule_adjustments(positions) == []


def test_exact_threshold_triggers():
    adj = compute_rule_adjustments([{"symbol": "AAA", "unrealized_pnl_pct": -15.0}])
    assert len(adj) == 1


def test_adjustment_exits_position_in_builder():
    # End-to-end: a stop-loss adjustment removes the symbol from the built target.
    from dataclasses import dataclass, field
    from src.portfolio.builder import TargetPortfolioBuilder

    @dataclass
    class _T:
        id: str
        name: str
        conviction: float
        positions: list = field(default_factory=list)

    class _Tracker:
        def get_active_theses(self):
            return [_T("t1", "A", 78, ["NVDA", "MU"])]

    adj = compute_rule_adjustments([{"symbol": "NVDA", "unrealized_pnl_pct": -20.0}])
    tp = TargetPortfolioBuilder(_Tracker()).build(equity=100_000, extra_adjustments=adj)
    assert "NVDA" not in tp.weights
    assert "MU" in tp.weights
