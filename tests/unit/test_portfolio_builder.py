"""Unit tests for the declarative portfolio core (re-architecture spine).

Locks in the cap/reserve/ladder behavior the Reconciler (Phase 4) depends on.
Uses a fake thesis tracker so tests don't touch live YAML.
"""
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.portfolio.builder import TargetPortfolioBuilder
from src.portfolio.sizing import ConvictionSizer
from src.portfolio.target import CashPolicy, Reserve


@dataclass
class _FakeThesis:
    id: str
    name: str
    conviction: float
    positions: list = field(default_factory=list)


class _FakeTracker:
    def __init__(self, theses):
        self._theses = theses

    def get_active_theses(self):
        return self._theses


class TestConvictionSizer:
    def test_ladder_tiers(self):
        s = ConvictionSizer()
        assert s.thesis_budget(85) == 0.30
        assert s.thesis_budget(75) == 0.20   # 65-80 tier
        assert s.thesis_budget(55) == 0.12
        assert s.thesis_budget(40) == 0.06
        assert s.thesis_budget(20) == 0.0

    def test_vehicles_equal_weight(self):
        s = ConvictionSizer()
        w = s.vehicle_weights(0.20, ["A", "B"])
        assert w == {"A": 0.10, "B": 0.10}

    def test_vehicles_dedupe_and_empty(self):
        s = ConvictionSizer()
        assert s.vehicle_weights(0.20, ["A", "A"]) == {"A": 0.20}
        assert s.vehicle_weights(0.0, ["A"]) == {}
        assert s.vehicle_weights(0.20, []) == {}


class TestBuilderCaps:
    def test_position_cap_clips_single_vehicle(self):
        # 85% conviction, 1 vehicle -> 30% budget -> clipped to 10% position cap
        tracker = _FakeTracker([_FakeThesis("t1", "Solo", 85, ["CCJ"])])
        tp = TargetPortfolioBuilder(tracker).build(equity=100_000)
        assert tp.weights["CCJ"].weight == 0.10
        assert tp.weights["CCJ"].bounded_by == "position_cap"

    def test_sector_cap_scales_cluster(self):
        # Three tech names each wanting 10% -> 30% < 40% sector cap, untouched
        theses = [
            _FakeThesis("t1", "A", 75, ["NVDA"]),
            _FakeThesis("t2", "B", 75, ["MU"]),
            _FakeThesis("t3", "C", 75, ["AMD"]),
        ]
        tp = TargetPortfolioBuilder(_FakeTracker(theses)).build(equity=100_000)
        tech_total = sum(tp.weights[s].weight for s in ["NVDA", "MU", "AMD"])
        assert tech_total <= 0.40 + 1e-9

    def test_invested_band_ceiling(self):
        # 10 single-vehicle 85% theses in DISTINCT sectors -> 10% each = 100%,
        # no sector-cap bite -> scaled down to the 95% invested ceiling.
        tp = TargetPortfolioBuilder(_overflow_tracker()).build(equity=100_000)
        assert abs(tp.invested_pct() - 0.95) < 1e-6

    def test_position_cap_blocks_deploy_to_floor(self):
        # 7 single-vehicle theses already pinned at the 10% position cap (70%
        # total) CANNOT be grown to the 80% floor — caps bind, residual stays cash.
        theses = [
            _FakeThesis(f"t{i}", f"T{i}", 78, [sym])
            for i, sym in enumerate(["CCJ", "GLD", "MP", "LLY", "TLT", "SLB", "NOC"])
        ]
        tp = TargetPortfolioBuilder(_FakeTracker(theses)).build(equity=100_000)
        assert abs(tp.invested_pct() - 0.70) < 1e-6

    def test_deploy_to_floor_grows_subcap_positions(self):
        # 5 two-vehicle theses @55% -> 0.12 budget -> 6% each (sub-cap), 60% total.
        # Deploy-to-floor grows them pro-rata to the 80% band floor (8% each).
        pairs = [["CCJ", "GLD"], ["MP", "LLY"], ["TLT", "SLB"], ["FRO", "NOC"], ["CF", "JPM"]]
        theses = [_FakeThesis(f"t{i}", f"T{i}", 55, p) for i, p in enumerate(pairs)]
        tp = TargetPortfolioBuilder(_FakeTracker(theses)).build(equity=100_000)
        assert abs(tp.invested_pct() - 0.80) < 1e-3
        for w in tp.weights.values():
            assert w.weight <= 0.10 + 1e-9   # never breaches position cap


def _overflow_tracker():
    # Each symbol is in a distinct sector so the sector cap never scales them.
    syms = ["CCJ", "GLD", "MP", "LLY", "TLT", "SLB", "FRO", "NOC", "CF", "JPM"]
    return _FakeTracker([_FakeThesis(f"t{i}", f"T{i}", 85, [s]) for i, s in enumerate(syms)])


class TestReserves:
    def _tracker(self):
        return _overflow_tracker()

    def test_active_reserve_lowers_invested(self):
        cp = CashPolicy(reserves=[
            Reserve("FOMC", 0.25, "rate decision", date.today() + timedelta(days=10))
        ])
        tp = TargetPortfolioBuilder(self._tracker(), cash_policy=cp).build(
            equity=100_000, today=date.today()
        )
        assert abs(tp.invested_pct() - 0.70) < 1e-6  # 0.95 ceiling - 0.25 reserve

    def test_expired_reserve_auto_deploys(self):
        cp = CashPolicy(reserves=[
            Reserve("Old", 0.25, "past", date.today() - timedelta(days=1))
        ])
        tp = TargetPortfolioBuilder(self._tracker(), cash_policy=cp).build(
            equity=100_000, today=date.today()
        )
        assert abs(tp.invested_pct() - 0.95) < 1e-6


class TestExtraAdjustments:
    def test_zero_weight_adjustment_exits_position(self):
        from src.portfolio.target import TargetWeight
        tracker = _FakeTracker([_FakeThesis("t1", "A", 75, ["NVDA", "MU"])])
        tp = TargetPortfolioBuilder(tracker).build(
            equity=100_000,
            extra_adjustments=[TargetWeight("NVDA", 0.0, source="rule_adjustment")],
        )
        assert "NVDA" not in tp.weights
        assert "MU" in tp.weights


class TestClusterCap:
    def test_cluster_capped_at_30pct(self):
        # Four names in one correlation cluster, each wanting 10% (40% total,
        # in distinct sectors so the sector cap can't catch it) -> scaled to
        # the 30% cluster budget: one cluster is one bet.
        theses = [
            _FakeThesis("t1", "Uranium", 85, ["CCJ"]),
            _FakeThesis("t2", "Gold", 85, ["GLD"]),
            _FakeThesis("t3", "RareEarth", 85, ["MP"]),
            _FakeThesis("t4", "RareEarthETF", 85, ["REMX"]),
        ]
        cluster = [{"CCJ", "GLD", "MP", "REMX"}]
        tp = TargetPortfolioBuilder(_FakeTracker(theses)).build(
            equity=100_000, correlation_clusters=cluster,
        )
        total = sum(tp.weights[s].weight for s in ["CCJ", "GLD", "MP", "REMX"])
        assert total <= 0.30 + 1e-9
        # each name scaled below its 10% position cap — proves the cluster
        # cap (not the position cap) did the final clipping
        assert all(tp.weights[s].weight < 0.10 - 1e-9
                   for s in ["CCJ", "GLD", "MP", "REMX"])

    def test_cluster_cap_config_override(self):
        from src.risk.limits import RiskLimitsConfig

        theses = [
            _FakeThesis("t1", "A", 85, ["CCJ"]),
            _FakeThesis("t2", "B", 85, ["GLD"]),
        ]
        cfg = RiskLimitsConfig(max_cluster_pct=0.12)
        tp = TargetPortfolioBuilder(_FakeTracker(theses), config=cfg).build(
            equity=100_000, correlation_clusters=[{"CCJ", "GLD"}],
        )
        assert sum(tp.weights[s].weight for s in ["CCJ", "GLD"]) <= 0.12 + 1e-9
