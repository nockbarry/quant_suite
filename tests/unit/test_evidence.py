"""C5 tests: log-odds evidence updates — symmetry, saturation, caps."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.intelligence.evidence import (
    apply_log_odds_update, blind_forecast_lr, evidence_lr,
)


class TestEvidenceLR:
    def test_coinflip_is_neutral(self):
        assert abs(evidence_lr(5, 10) - 1.0) < 1e-9

    def test_symmetry(self):
        # k hits and k misses out of n are exact reciprocals
        assert abs(evidence_lr(8, 10) * evidence_lr(2, 10) - 1.0) < 1e-9

    def test_no_evidence_is_neutral(self):
        assert evidence_lr(0, 0) == 1.0


class TestApplyUpdate:
    def test_saturation_near_ceiling(self):
        # Identical evidence moves mid conviction more than high conviction
        lr = evidence_lr(9, 10)
        mid_delta = apply_log_odds_update(50, lr, cap_pp=50) - 50
        high_delta = apply_log_odds_update(90, lr, cap_pp=50) - 90
        assert mid_delta > high_delta > 0

    def test_velocity_cap(self):
        lr = evidence_lr(20, 20)  # overwhelming
        assert apply_log_odds_update(50, lr, cap_pp=5) == 55

    def test_lr_and_inverse_cancel(self):
        lr = evidence_lr(8, 10)
        up = apply_log_odds_update(60, lr, cap_pp=50)
        back = apply_log_odds_update(up, 1 / lr, cap_pp=50)
        assert abs(back - 60) < 0.01

    def test_negative_evidence_reduces(self):
        assert apply_log_odds_update(70, evidence_lr(2, 10)) < 70


class TestBlindLR:
    def test_neutral_forecast_is_neutral(self):
        assert abs(blind_forecast_lr(0.5) - 1.0) < 1e-9

    def test_shrunk_below_full_odds(self):
        # A 0.7 forecast contributes less than the full odds ratio
        full = (0.7 / 0.3) / 1.0
        assert 1.0 < blind_forecast_lr(0.7) < full
