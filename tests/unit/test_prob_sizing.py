"""Unit tests for the probability sizing layer (C2).

Covers: prob ladder monotonicity, flag-off regression (identical to legacy
conviction sizing), red-flag capping at 90%+ conviction, source
renormalization when sources are missing, clamps, and effective_confidence
monotonicity.
"""
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import src.probability.estimator as est_mod
from src.portfolio.builder import TargetPortfolioBuilder
from src.portfolio.sizing import ConvictionSizer
from src.probability.estimator import (
    CLAMP_HI, CLAMP_LO, ProbabilityEstimator, blend_log_odds, effective_confidence,
)


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


def _estimator(tmp_path, forecasts=None, generated_at=None) -> ProbabilityEstimator:
    """Estimator with a controlled blind snapshot and no DB (ensemble -> None)."""
    snap = tmp_path / "blind_forecasts.json"
    if forecasts is not None:
        snap.write_text(json.dumps({
            "generated_at": (generated_at or datetime.now()).isoformat(),
            "forecasts": forecasts,
        }))
    e = ProbabilityEstimator(blind_snapshot_path=snap)
    e._ensemble_prob = lambda symbol: None  # no DB in unit tests
    return e


class TestProbLadder:
    def test_monotone(self):
        s = ConvictionSizer()
        budgets = [s.thesis_budget_from_prob(p) for p in (0.40, 0.50, 0.54, 0.58, 0.62, 0.75)]
        assert budgets == sorted(budgets)
        assert budgets[0] == 0.0
        assert budgets[-1] == 0.30

    def test_below_coinflip_gets_nothing(self):
        assert ConvictionSizer().thesis_budget_from_prob(0.49) == 0.0


class TestBlend:
    def test_missing_sources_renormalize(self):
        # single source == that source's value
        assert abs(blend_log_odds({"curve": 0.60}) - 0.60) < 1e-9
        # equal-value sources blend to the same value regardless of count
        assert abs(blend_log_odds({"curve": 0.60, "blind": 0.60}) - 0.60) < 1e-9
        # no sources -> indifference
        assert blend_log_odds({}) == 0.5

    def test_blind_outweighs_curve(self):
        p = blend_log_odds({"curve": 0.50, "blind": 0.70})
        assert 0.60 < p < 0.70  # pulled well toward blind (weight 0.5 vs 0.3)


class TestEstimator:
    def test_clamped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: 0.99)
        e = _estimator(tmp_path, forecasts={"NVDA": {"dir": "bullish", "conf": 0.95}})
        sp = e.estimate("NVDA", _FakeThesis("t1", "AI", 80, ["NVDA"]))
        assert CLAMP_LO <= sp.p_direction <= CLAMP_HI

    def test_red_flag_at_90_caps_at_curve(self, tmp_path, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob",
                            lambda c: 0.55 if c < 0.85 else 0.55)
        e = _estimator(tmp_path, forecasts={"NVDA": {"dir": "bullish", "conf": 0.80}})
        sp = e.estimate("NVDA", _FakeThesis("t1", "AI", 92, ["NVDA"]))
        assert "stated_conf_ge_90" in sp.red_flags
        assert sp.p_direction <= sp.sources["curve"] + 1e-9

    def test_bearish_blind_is_evidence_against(self, tmp_path, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: max(0.3, min(0.7, c)))
        e = _estimator(tmp_path, forecasts={"GLD": {"dir": "bearish", "conf": 0.65}})
        bear = e.estimate("GLD", _FakeThesis("t1", "Gold", 70, ["GLD"]))
        e2 = _estimator(tmp_path / "x", forecasts=None)
        no_blind = e2.estimate("GLD", _FakeThesis("t1", "Gold", 70, ["GLD"]))
        assert bear.p_direction < no_blind.p_direction

    def test_stale_blind_dropped(self, tmp_path):
        e = _estimator(tmp_path, forecasts={"MU": {"dir": "bullish", "conf": 0.9}},
                       generated_at=datetime(2020, 1, 1))
        sp = e.estimate("MU", _FakeThesis("t1", "HBM", 70, ["MU"]))
        assert "blind" not in sp.sources


class TestBuilderIntegration:
    def _theses(self):
        return [
            _FakeThesis("t1", "AI", 80, ["NVDA"]),
            _FakeThesis("t2", "Gold", 65, ["GLD"]),
        ]

    def test_flag_off_identical_to_legacy(self, tmp_path):
        e = _estimator(tmp_path, forecasts={"NVDA": {"dir": "bullish", "conf": 0.6}})
        pm = e.estimate_map(self._theses())
        b = TargetPortfolioBuilder(_FakeTracker(self._theses()))
        legacy = b.build(equity=100_000, prob_sizing=False)
        with_map_off = b.build(equity=100_000, prob_map=pm, prob_sizing=False)
        assert {s: w.weight for s, w in legacy.weights.items()} == \
               {s: w.weight for s, w in with_map_off.weights.items()}
        assert all(w.sizing_mode == "conviction" for w in with_map_off.weights.values())

    def test_prob_sizing_uses_ladder_and_stamps_provenance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: 0.63)
        e = _estimator(tmp_path, forecasts={"NVDA": {"dir": "bullish", "conf": 0.7}})
        pm = e.estimate_map(self._theses())
        b = TargetPortfolioBuilder(_FakeTracker(self._theses()))
        tp = b.build(equity=100_000, prob_map=pm, prob_sizing=True)
        nvda = tp.weights["NVDA"]
        assert nvda.sizing_mode == "probability"
        assert nvda.p_calibrated is not None
        # p=0.63 (clamped/blended >=0.62 tier) -> 30% thesis budget -> clipped to 10% pos cap
        assert nvda.weight <= 0.10 + 1e-9

    def test_low_conviction_ineligible_under_prob_sizing(self, tmp_path, monkeypatch):
        # Even a great calibrated probability can't size a sub-35 conviction
        # thesis: conviction stays the governance gate.
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: 0.70)
        theses = [_FakeThesis("t1", "Dead", 20, ["XYZ"])]
        e = _estimator(tmp_path, forecasts={"XYZ": {"dir": "bullish", "conf": 0.9}})
        pm = e.estimate_map(theses)
        tp = TargetPortfolioBuilder(_FakeTracker(theses)).build(
            equity=100_000, prob_map=pm, prob_sizing=True)
        assert "XYZ" not in tp.weights


class TestEffectiveConfidence:
    def test_monotone_in_agreement(self, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: 0.55)
        lo = effective_confidence(0.8, agreement=1 / 3)
        mid = effective_confidence(0.8, agreement=2 / 3)
        hi = effective_confidence(0.8, agreement=1.0)
        assert lo < mid < hi

    def test_no_agreement_is_pure_curve(self, monkeypatch):
        monkeypatch.setattr(est_mod, "opinion_calibrated_prob", lambda c: 0.42)
        assert effective_confidence(0.9) == 0.42
