"""Tests for the opinion-derived calibration bound (Phase 6).

Key property: unlike the inverted decision-prediction curve, this bound never
squashes a normally-calibrated high-conviction position — it is floored at 5%
and only bites on genuine, sustained overconfidence.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.portfolio import calibration_bound as cb


def test_bound_is_floored(monkeypatch):
    # Even with awful calibration, the bound never goes below the 5% floor.
    monkeypatch.setattr(cb, "_curve", lambda: [(0.5, 0.10), (0.9, 0.10)])
    assert cb.opinion_calibration_bound(0.95) == cb.BOUND_FLOOR


def test_high_skill_allows_full_size(monkeypatch):
    # 70-80% predicted -> ~73% actual (real opinion data) => unbounded vs 10% cap.
    monkeypatch.setattr(cb, "_curve", lambda: [(0.5, 0.51), (0.72, 0.73)])
    assert cb.opinion_calibration_bound(0.75) == 0.12


def test_identity_without_data(monkeypatch):
    monkeypatch.setattr(cb, "_curve", lambda: [])
    assert cb.opinion_calibrated_prob(0.8) == 0.8


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ATHENA_CALIBRATION_BOUND", raising=False)
    assert cb.get_calibration_bound() is None


def test_enabled_returns_callable(monkeypatch):
    monkeypatch.setenv("ATHENA_CALIBRATION_BOUND", "1")
    monkeypatch.setattr(cb, "_curve", lambda: [(0.5, 0.51), (0.72, 0.73)])
    bound = cb.get_calibration_bound()
    assert callable(bound)
