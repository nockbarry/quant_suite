"""Unit tests for the corporate-action guard (split detection + freezes)."""
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import src.data.corporate_actions as ca
from src.data.corporate_actions import SplitEvent, detect_share_discontinuity
from src.portfolio.reconciler import Reconciler
from src.portfolio.target import CashPolicy, TargetPortfolio, TargetWeight


class TestDiscontinuity:
    def test_forward_split_detected(self):
        # CRWD failure mode: 7 shares -> 28 overnight, no order
        hits = detect_share_discontinuity({"CRWD": 7}, {"CRWD": 28})
        assert hits == {"CRWD": 4.0}

    def test_reverse_split_detected(self):
        hits = detect_share_discontinuity({"XYZ": 100}, {"XYZ": 10})
        assert hits == {"XYZ": 1 / 10}

    def test_normal_trading_not_flagged(self):
        # An add of a few shares is not a split
        assert detect_share_discontinuity({"NVDA": 42}, {"NVDA": 48}) == {}
        # unchanged
        assert detect_share_discontinuity({"MU": 10}, {"MU": 10}) == {}

    def test_new_and_closed_positions_ignored(self):
        assert detect_share_discontinuity({}, {"NEW": 50}) == {}
        assert detect_share_discontinuity({"GONE": 50}, {}) == {}


class TestTodaysSplits:
    def _write_cache(self, tmp_path, monkeypatch, events):
        cache = tmp_path / "corporate_actions.json"
        cache.write_text(json.dumps({
            "fetched_at": datetime.now().isoformat(),
            "events": [e.to_dict() for e in events],
        }))
        monkeypatch.setattr(ca, "CACHE_FILE", cache)

    def test_today_filtering(self, tmp_path, monkeypatch):
        today = date.today().isoformat()
        self._write_cache(tmp_path, monkeypatch, [
            SplitEvent("CRWD", 4.0, today, "forward_split"),
            SplitEvent("OLD", 2.0, "2026-01-02", "forward_split"),
        ])
        splits = ca.todays_splits()
        assert set(splits) == {"CRWD"}
        assert splits["CRWD"].ratio == 4.0

    def test_missing_cache_degrades_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ca, "CACHE_FILE", tmp_path / "nope.json")
        assert ca.todays_splits() == {}

    def test_guard_kill_switch(self, tmp_path, monkeypatch):
        today = date.today().isoformat()
        self._write_cache(tmp_path, monkeypatch, [SplitEvent("CRWD", 4.0, today, "forward_split")])
        monkeypatch.setenv("ATHENA_CA_GUARD", "0")
        assert ca.todays_splits() == {}


class TestReconcilerFreeze:
    def test_split_symbol_frozen_others_trade(self, tmp_path, monkeypatch):
        today = date.today().isoformat()
        cache = tmp_path / "corporate_actions.json"
        cache.write_text(json.dumps({
            "fetched_at": datetime.now().isoformat(),
            "events": [SplitEvent("CRWD", 4.0, today, "forward_split").to_dict()],
        }))
        monkeypatch.setattr(ca, "CACHE_FILE", cache)

        tp = TargetPortfolio(
            weights={
                "CRWD": TargetWeight("CRWD", 0.05),
                "NVDA": TargetWeight("NVDA", 0.05),
            },
            cash_policy=CashPolicy(),
            generated_at=datetime(2026, 7, 2, 9, 0, 0),
            equity_at_build=100_000,
        )
        orders = Reconciler().plan(
            tp, current_values={}, equity=100_000,
            prices={"CRWD": 160.0, "NVDA": 200.0},
        )
        symbols = {o.symbol for o in orders}
        assert "CRWD" not in symbols  # frozen on ex-date
        assert "NVDA" in symbols      # unaffected symbols still reconcile
