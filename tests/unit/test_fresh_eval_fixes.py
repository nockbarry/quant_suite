"""Tests for the 2026-06-09 fresh-evaluation fixes:
FIFO realized P&L, correlation clusters, event reserves, rank tilt.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.analytics.realized_pnl import Fill, fifo_realize
from src.portfolio.clusters import apply_cluster_cap, clusters_from_correlation
from src.portfolio.target import CashPolicy, TargetWeight


class TestFifoRealize:
    def _f(self, sym, side, qty, price, day):
        return Fill(sym, side, qty, price, datetime(2026, 1, day), f"{sym}-{side}-{day}")

    def test_simple_round_trip(self):
        lots = fifo_realize([
            self._f("AAA", "buy", 10, 100.0, 1),
            self._f("AAA", "sell", 10, 110.0, 20),
        ])
        assert len(lots) == 1
        l = lots[0]
        assert l.pnl == 100.0 and abs(l.pnl_pct - 10.0) < 1e-9
        assert l.hold_days == 19.0

    def test_partial_sell_fifo_order(self):
        lots = fifo_realize([
            self._f("AAA", "buy", 10, 100.0, 1),
            self._f("AAA", "buy", 10, 200.0, 2),
            self._f("AAA", "sell", 15, 210.0, 10),
        ])
        # FIFO: 10 from the $100 lot, 5 from the $200 lot
        assert [(l.qty, l.entry_price) for l in lots] == [(10, 100.0), (5, 200.0)]
        assert sum(l.pnl for l in lots) == 10 * 110 + 5 * 10

    def test_sell_without_inventory_flagged_zero_pnl(self):
        lots = fifo_realize([self._f("AAA", "sell", 5, 50.0, 1)])
        assert len(lots) == 1
        assert lots[0].buy_order_id is None and lots[0].pnl == 0.0


class TestClusters:
    def test_connected_components(self):
        corr = {("A", "B"): 0.8, ("B", "C"): 0.7, ("D", "E"): 0.2}
        clusters = clusters_from_correlation(corr, ["A", "B", "C", "D", "E"], threshold=0.6)
        assert clusters == [{"A", "B", "C"}]  # D,E uncorrelated -> singletons dropped

    def test_cluster_cap_scales_proportionally(self):
        w = {s: TargetWeight(s, 0.25) for s in ["A", "B", "C"]}
        apply_cluster_cap(w, [{"A", "B", "C"}], max_cluster_pct=0.50)
        total = sum(x.weight for x in w.values())
        assert abs(total - 0.50) < 1e-9
        assert all(x.bounded_by == "correlation_cluster" for x in w.values())

    def test_under_cap_cluster_untouched(self):
        w = {s: TargetWeight(s, 0.10) for s in ["A", "B"]}
        apply_cluster_cap(w, [{"A", "B"}], max_cluster_pct=0.50)
        assert all(x.weight == 0.10 and x.bounded_by is None for x in w.values())


class TestEventReserves:
    def test_window_and_expiry(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUANT_RESULTS_DIR", str(tmp_path))
        from src.portfolio import event_reserves as er
        # FOMC-Jun 2026-06-17, window starts Jun 12
        assert not [r for r in er.compute_event_reserves(date(2026, 6, 11))]
        active = er.compute_event_reserves(date(2026, 6, 15))
        assert any(r.name == "event:FOMC-Jun" and r.target_pct == 0.20 for r in active)
        # day after decision: reserve gone (deploys)
        assert not [r for r in er.compute_event_reserves(date(2026, 6, 18))
                    if r.name == "event:FOMC-Jun"]

    def test_manual_reserve_wins_on_collision(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUANT_RESULTS_DIR", str(tmp_path))
        from src.portfolio import event_reserves as er
        from src.portfolio.target import Reserve
        cp = CashPolicy(reserves=[
            Reserve("event:FOMC-Jun", 0.30, "manual override", date(2026, 6, 17))
        ])
        er.merge_event_reserves(cp, today=date(2026, 6, 15))
        matches = [r for r in cp.reserves if r.name == "event:FOMC-Jun"]
        assert len(matches) == 1 and matches[0].target_pct == 0.30


class TestRankTilt:
    def test_ranking_differentiates_budgets(self):
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
                # identical conviction, 2 vehicles each, enough theses that the
                # invested-band floor is reached before position caps saturate
                # (deploy-to-floor grows pro-rata, PRESERVING the tilt ratios)
                pairs = [["CCJ", "NEE"], ["GLD", "LLY"], ["TLT", "NOC"],
                         ["SLB", "CF"], ["FRO", "JPM"]]
                return [_T(f"t{i}", f"T{i}", 55, p) for i, p in enumerate(pairs, 1)]

        tp = TargetPortfolioBuilder(_Tracker()).build(
            equity=100_000, ranking=["t2", "t1", "t3", "t4", "t5"])
        # tilts 1.2/1.1/1.0/0.9/0.8 on 12% budgets = 60% total -> floor grows
        # 1.333x to 80%: vehicles 9.6% / 8.8% / 8% / 7.2% / 6.4%
        assert tp.weights["GLD"].weight > tp.weights["CCJ"].weight > tp.weights["FRO"].weight
        assert abs(tp.weights["GLD"].weight - 0.096) < 1e-3
        assert abs(tp.weights["FRO"].weight - 0.064) < 1e-3

    def test_no_ranking_means_no_tilt(self):
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
                return [_T("t1", "A", 55, ["CCJ"]), _T("t2", "B", 55, ["GLD"])]

        tp = TargetPortfolioBuilder(_Tracker()).build(equity=100_000)
        assert tp.weights["CCJ"].weight == tp.weights["GLD"].weight
