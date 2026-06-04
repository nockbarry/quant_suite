"""Unit tests for the Reconciler's pure planning logic.

Verifies the properties the live cutover depends on: at-target is a no-op,
a single weight delta produces exactly one correctly-sided order, drawdown
blocks buys but not sells, and the per-trade size cap clips large moves.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.portfolio.reconciler import Reconciler
from src.portfolio.target import CashPolicy, TargetPortfolio, TargetWeight


def _target(weights: dict[str, float], equity: float = 100_000) -> TargetPortfolio:
    return TargetPortfolio(
        weights={s: TargetWeight(s, w) for s, w in weights.items()},
        cash_policy=CashPolicy(),
        generated_at=datetime(2026, 6, 3, 9, 0, 0),
        equity_at_build=equity,
    )


PRICES = {"NVDA": 200.0, "MU": 100.0, "GLD": 250.0, "XLV": 150.0}


class TestReconcilePlan:
    def test_at_target_is_noop(self):
        # current == target -> empty plan
        tp = _target({"NVDA": 0.10})
        r = Reconciler()
        orders = r.plan(tp, current_values={"NVDA": 10_000}, equity=100_000, prices=PRICES)
        assert orders == []

    def test_single_delta_one_order(self):
        # 10% target buy ($10k) is clipped to the 5% per-trade rail ($5k = 25sh);
        # the remaining 5% is filled by the next reconcile run (gradual convergence).
        tp = _target({"NVDA": 0.10})
        r = Reconciler()
        orders = r.plan(tp, current_values={}, equity=100_000, prices=PRICES)
        assert len(orders) == 1
        o = orders[0]
        assert o.symbol == "NVDA" and o.side == "buy"
        assert o.qty == 25  # $5,000 (5% rail) / $200
        assert "partial" in o.reason
        assert o.client_order_id.startswith("recon-20260603-NVDA-b")

    def test_unbacked_position_is_sold(self):
        # XLV held but not in target -> sell to zero
        tp = _target({"NVDA": 0.10})
        r = Reconciler()
        orders = r.plan(tp, current_values={"XLV": 6_000, "NVDA": 10_000},
                        equity=100_000, prices=PRICES)
        assert len(orders) == 1
        assert orders[0].symbol == "XLV" and orders[0].side == "sell"

    def test_min_trade_threshold_skips_tiny(self):
        # target 10.1% vs current 10% -> $100 delta < $200 min -> skip
        tp = _target({"NVDA": 0.101})
        r = Reconciler(min_trade_usd=200)
        orders = r.plan(tp, current_values={"NVDA": 10_000}, equity=100_000, prices=PRICES)
        assert orders == []

    def test_drawdown_blocks_buys_allows_sells(self):
        tp = _target({"NVDA": 0.10})  # want to buy NVDA
        r = Reconciler()
        orders = r.plan(
            tp,
            current_values={"XLV": 6_000},   # XLV not in target -> sell
            equity=100_000, prices=PRICES, allow_buys=False,
        )
        sides = {o.symbol: o.side for o in orders}
        assert sides.get("XLV") == "sell"   # sell still allowed
        assert "NVDA" not in sides          # buy blocked

    def test_max_trade_cap_clips_large_move(self):
        # want 30% NVDA from zero on $100k = $30k, but max_trade 5% = $5k -> 25 sh
        tp = _target({"NVDA": 0.30})
        r = Reconciler()
        orders = r.plan(tp, current_values={}, equity=100_000, prices=PRICES)
        assert len(orders) == 1
        o = orders[0]
        assert o.qty == 25  # $5,000 / $200
        assert "partial" in o.reason

    def test_idempotent_same_plan_same_ids(self):
        tp = _target({"NVDA": 0.10, "MU": 0.08})
        r = Reconciler()
        a = r.plan(tp, current_values={}, equity=100_000, prices=PRICES)
        b = r.plan(tp, current_values={}, equity=100_000, prices=PRICES)
        assert [o.client_order_id for o in a] == [o.client_order_id for o in b]
