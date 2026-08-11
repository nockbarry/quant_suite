"""Blind-context probability elicitation.

The decision pipeline's verbalized confidence is anti-calibrated because it
is asked inside a context saturated with the thesis narrative. This module
elicits forecasts in a STRUCTURALLY blind way:

- universe entries are bare symbols (no thesis metadata)
- the context assembler runs in blind mode (no thesis names, no conviction,
  no held-position P&L, no conviction velocity — market facts only)
- the LLM call is a fresh Haiku subprocess (ClaudeCodeClient), so no session
  narrative can leak in

Forecasts are persisted two ways:
1. As opinions with session_type="blind_sizer" — scored nightly by
   cron_opinion_scorer into opinion_calibration.json, so the source that
   calibrates them also measures them (segmentable by session_type).
2. As a snapshot (~/quant_results/intelligence/blind_forecasts.json) read by
   ProbabilityEstimator; stale snapshots (>24h) are dropped there.

Failure is always soft: no subprocess / no parse -> no snapshot update ->
estimator renormalizes onto curve+ensemble. Never blocks target build.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HORIZON_DAYS = 10
SNAPSHOT_MAX_AGE_HOURS = 20.0   # refresh_if_due threshold (once per trading day)

# Advocacy tokens that must never appear in a blind prompt. The blindness
# regression test asserts these; keep in sync with context_assembler blind mode.
FORBIDDEN_TOKENS = ("thesis=", "held=", "cv=", "conviction")


def _snapshot_path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "intelligence" / "blind_forecasts.json"


class BlindForecaster:
    def __init__(self, snapshot_path: Optional[Path] = None, model: str = "haiku"):
        self.snapshot_path = snapshot_path or _snapshot_path()
        self.model = model

    # ---- universe / prompt --------------------------------------------

    @staticmethod
    def build_universe(theses) -> list[dict]:
        """Bare-symbol entries: thesis metadata deliberately stripped."""
        symbols = sorted({
            s for th in theses for s in (getattr(th, "positions", None) or []) if s
        })
        return [{"symbol": s} for s in symbols]

    def build_prompt(self, universe: list[dict]) -> str:
        from src.opinions.context_assembler import OpinionContextAssembler

        assembler = OpinionContextAssembler()
        context_lines, market = assembler.assemble_batch(universe, blind=True)

        for token in FORBIDDEN_TOKENS:
            if token in context_lines:
                # Fail closed: a leaky prompt reproduces the calibration bug.
                raise ValueError(f"Blind context leaked advocacy token {token!r}")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M ET")
        spy = market.get("spy_price", 0)
        spy_chg = market.get("spy_change", 0)
        vix = market.get("vix", 0)
        regime = market.get("regime", "unknown")

        return f"""PRICE FORECAST — {timestamp}

You are a price forecaster. For each of the {len(universe)} symbols below, forecast:
1. Price targets at 5d/10d/30d horizons (bull/base/bear dollar values)
2. Trend direction (bullish/bearish/neutral) and magnitude (strong/moderate/mild/flat)
3. Expected performance vs SPY over 10 days (outperform/underperform/inline and alpha %)
4. Confidence (0-1) that your DIRECTION call is correct, key driver, key risk

Base rates: over 10 days, most liquid stocks are a near coin flip on direction.
Well-calibrated forecasters rarely exceed 0.70 confidence at this horizon. State
the probability you would bet at, not your enthusiasm.

Current market: SPY ${spy:.2f} ({spy_chg:+.1f}%) | VIX {vix:.1f} | Regime: {regime}

Symbol context:
{context_lines}

Output a JSON array. Use SHORT keys:
[{{"s":"MU","t5":[108,105,100],"t10":[115,110,98],"t30":[125,115,95],"dir":"bullish","mag":"moderate","conf":0.58,"rel":"outperform","relm":3.0,"drv":"memory pricing","risk":"inventory correction"}}]

Keys: s=symbol, t5/t10/t30=[bull,base,bear prices], dir=direction, mag=magnitude, conf=confidence, rel=relative vs SPY, relm=alpha %, drv=driver, risk=risk

ONLY output the JSON array. No markdown fencing, no explanation."""

    # ---- elicitation ---------------------------------------------------

    def elicit(self, theses) -> Optional[dict[str, dict]]:
        """Run one blind capture. Returns {symbol: {dir, conf}} or None on failure."""
        universe = self.build_universe(theses)
        if not universe:
            logger.info("Blind forecast: no thesis vehicles — skipping")
            return None
        try:
            prompt = self.build_prompt(universe)
        except Exception as e:
            logger.error(f"Blind prompt build failed: {e}")
            return None

        try:
            from src.core.claude_code_client import get_client

            parsed, _resp = get_client().complete_json(
                user=prompt,
                system="You are a calibrated price forecaster. Output strict JSON only.",
                model=self.model,
            )
        except Exception as e:
            logger.warning(f"Blind forecast LLM call failed (soft): {e}")
            return None

        # complete_json returns the parsed JSON; the opinion parser wants text.
        json_text = json.dumps(parsed)
        batch_id = f"blind_{uuid.uuid4().hex[:10]}"
        forecasts: dict[str, dict] = {}
        try:
            from src.opinions.capture import OpinionCaptureEngine

            engine = OpinionCaptureEngine()
            opinions = engine.parse_response(json_text, batch_id, "blind_sizer", universe)
            if opinions:
                saved = engine.save_batch(opinions)
                logger.info(f"Blind forecast: saved {saved} opinions (batch {batch_id})")
            for op in opinions:
                sym = op.get("symbol")
                if sym:
                    forecasts[sym] = {
                        "dir": op.get("trend_direction", "neutral"),
                        "conf": op.get("trend_confidence", 0.5),
                    }
        except Exception as e:
            logger.error(f"Blind forecast parse/save failed: {e}")
            return None

        if forecasts:
            self._write_snapshot(forecasts, batch_id)
        return forecasts or None

    def _write_snapshot(self, forecasts: dict[str, dict], batch_id: str) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps({
            "generated_at": datetime.now().isoformat(),
            "batch_id": batch_id,
            "horizon_days": HORIZON_DAYS,
            "forecasts": forecasts,
        }, indent=2))

    def refresh_if_due(self, theses) -> bool:
        """Elicit once per trading day; returns True if a fresh elicitation ran."""
        try:
            if self.snapshot_path.exists():
                raw = json.loads(self.snapshot_path.read_text())
                generated = datetime.fromisoformat(raw.get("generated_at", "1970-01-01T00:00:00"))
                age_h = (datetime.now() - generated).total_seconds() / 3600
                if age_h < SNAPSHOT_MAX_AGE_HOURS:
                    logger.info(f"Blind forecasts fresh ({age_h:.1f}h) — no refresh")
                    return False
        except Exception:
            pass
        return self.elicit(theses) is not None
