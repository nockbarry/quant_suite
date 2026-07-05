"""Blind-context elicitation tests (C3).

The load-bearing property is BLINDNESS: the prompt that produces the sizing
probability must not contain thesis names, conviction, or position status.
That is asserted here against a synthetic state where every leak channel is
populated — not assumed.
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from src.opinions.context_assembler import OpinionContextAssembler
from src.probability.blind_forecast import FORBIDDEN_TOKENS, BlindForecaster


@dataclass
class _FakeThesis:
    id: str
    name: str
    conviction: float
    positions: list = field(default_factory=list)


def _assembler_with_leaky_state() -> OpinionContextAssembler:
    """Assembler whose loaded state would leak advocacy through every channel."""
    a = OpinionContextAssembler()
    a._load_all()  # populate defaults, then override the leak channels
    a._state = {
        "watchlist_signals": {"NVDA": {"current_price": 200.0, "rsi": 55.0}},
        "positions": [{"symbol": "NVDA", "unrealized_pnl_pct": 25.6, "weight_pct": 8.2}],
    }
    a._conv_velocity = {"NVDA": {"direction": "ADD", "velocity_3d": 2.5, "symbols": ["NVDA"]}}
    return a


LEAKY_UNIVERSE = [{
    "symbol": "NVDA",
    "thesis_name": "NVIDIA AI Compute",
    "thesis_id": "t1",
    "conviction": 92,
}]


class TestBlindContext:
    def test_default_mode_leaks_prove_the_channels_exist(self):
        # Sanity check on the fixture: without blind=True these channels DO
        # appear — otherwise the blindness assertions below prove nothing.
        a = _assembler_with_leaky_state()
        line = a._symbol_context(LEAKY_UNIVERSE[0], blind=False)
        assert "thesis=" in line
        assert "held=" in line
        assert "cv=" in line

    def test_blind_mode_strips_advocacy(self):
        a = _assembler_with_leaky_state()
        line = a._symbol_context(LEAKY_UNIVERSE[0], blind=True)
        for token in ("thesis=", "held=", "cv="):
            assert token not in line, f"blind context leaked {token!r}: {line}"
        # market facts survive
        assert "$200.00" in line
        assert "RSI=55" in line

    def test_bare_universe_has_no_thesis_metadata(self):
        uni = BlindForecaster.build_universe([
            _FakeThesis("t1", "NVIDIA AI Compute", 92, ["NVDA", "TSM"]),
            _FakeThesis("t2", "Gold", 60, ["GLD"]),
        ])
        assert uni == [{"symbol": "GLD"}, {"symbol": "NVDA"}, {"symbol": "TSM"}]

    def test_build_prompt_fails_closed_on_leak(self, monkeypatch):
        bf = BlindForecaster()

        class _LeakyAssembler:
            def assemble_batch(self, universe, blind=False):
                return "NVDA: $200 thesis=NVIDIA AI@92%", {}

        import src.opinions.context_assembler as ca_mod
        monkeypatch.setattr(ca_mod, "OpinionContextAssembler", lambda: _LeakyAssembler())
        with pytest.raises(ValueError, match="advocacy token"):
            bf.build_prompt([{"symbol": "NVDA"}])


class TestElicitPlumbing:
    def test_elicit_soft_failure_returns_none(self, tmp_path, monkeypatch):
        bf = BlindForecaster(snapshot_path=tmp_path / "blind.json")
        monkeypatch.setattr(bf, "build_prompt", lambda u: "PROMPT")

        import src.core.claude_code_client as ccc

        class _DeadClient:
            def complete_json(self, **kw):
                raise RuntimeError("no binary")

        monkeypatch.setattr(ccc, "get_client", lambda: _DeadClient())
        theses = [_FakeThesis("t1", "AI", 80, ["NVDA"])]
        assert bf.elicit(theses) is None
        assert not (tmp_path / "blind.json").exists()

    def test_refresh_skips_when_fresh(self, tmp_path):
        snap = tmp_path / "blind.json"
        from datetime import datetime
        snap.write_text(json.dumps({
            "generated_at": datetime.now().isoformat(),
            "forecasts": {"NVDA": {"dir": "bullish", "conf": 0.6}},
        }))
        bf = BlindForecaster(snapshot_path=snap)
        assert bf.refresh_if_due([_FakeThesis("t1", "AI", 80, ["NVDA"])]) is False
