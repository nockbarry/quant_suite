"""C4 tests: ensemble gate, agreement-scaled sizing inputs, 90% red flag."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.decision.ensemble import DecisionEnsemble


class TestGate:
    def setup_method(self):
        self.e = DecisionEnsemble()

    def test_mandatory_at_90(self):
        run, reason = self.e.should_run_challengers({"confidence": 0.92})
        assert run and "mandatory" in reason

    def test_runs_at_gate(self):
        run, reason = self.e.should_run_challengers({"confidence": 0.80})
        assert run

    def test_skips_below_gate(self):
        run, reason = self.e.should_run_challengers({"confidence": 0.65})
        assert not run

    def test_no_calibration_gap_skip_exists(self):
        # The gap-based skip consulted the inverted decision curve — deleted.
        assert not hasattr(self.e, "_calibration_gap")
        assert not hasattr(self.e, "CALIBRATION_GAP_GATE")


class TestRedFlagDecision:
    def test_90pct_buy_clamped_and_tagged(self, monkeypatch, tmp_path):
        # create_decision at 0.92 confidence: size clamped to 3%, risk tagged.
        monkeypatch.setenv("QUANT_RESULTS_DIR", str(tmp_path))
        from src.decision.decision_logger import Action, create_decision

        d = create_decision(
            symbol="ZZRF",
            action=Action.BUY,
            confidence=0.92,
            size_pct=10.0,
            reasoning="red flag test",
            key_factors=["test"],
            risks=["market"],
            context={},
        )
        assert d.size_pct <= 3.0 + 1e-9
        assert any("red_flag_overconfidence" in r for r in d.risks)
