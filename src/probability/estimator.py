"""Blend calibrated probability sources into a sizing probability.

Log-odds weighted blend of up to three sources (weights renormalized over
whichever are available), clamped to a conservative band while the layer is
young — sizing must not whipsaw on estimator noise.

    curve    (0.3): opinion_calibrated_prob(conviction) — the empirical
                    direction rate the opinion pipeline observed at this
                    stated-confidence level. The "shrinkage" prior.
    blind    (0.5): fresh-context forecast from blind_forecast.py — the
                    highest-weight source because it is structurally immune
                    to the narrative contamination that inverted the
                    decision curve.
    ensemble (0.2): challenger agreement fraction, shrunk toward 0.5 (three
                    votes is a coarse instrument).

Overconfidence rule: conviction >= 90 caps the blend at the curve prior and
red-flags the symbol. Empirically 90%+ stated resolved at ~33% — extreme
confidence is evidence of narrative capture, not edge.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.portfolio.calibration_bound import opinion_calibrated_prob
from src.probability.models import SymbolProbability

logger = logging.getLogger(__name__)

SOURCE_WEIGHTS = {"curve": 0.3, "blind": 0.5, "ensemble": 0.2}
CLAMP_LO, CLAMP_HI = 0.35, 0.75
BLIND_MAX_AGE_HOURS = 24.0
ENSEMBLE_LOOKBACK_DAYS = 7          # ~5 trading days
ENSEMBLE_SHRINK = 0.5               # agreement -> 0.5 + (a - 0.5) * SHRINK
RED_FLAG_CONVICTION = 90.0


def _blind_snapshot_path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "intelligence" / "blind_forecasts.json"


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def blend_log_odds(sources: dict[str, float]) -> float:
    """Weighted log-odds mean over available sources, weights renormalized."""
    weights = {k: SOURCE_WEIGHTS[k] for k in sources if k in SOURCE_WEIGHTS}
    total = sum(weights.values())
    if not weights or total <= 0:
        return 0.5
    z = sum(w * _logit(sources[k]) for k, w in weights.items()) / total
    return _sigmoid(z)


def effective_confidence(stated: float, agreement: Optional[float] = None) -> float:
    """Calibrated confidence for a decision/prediction record.

    Maps stated confidence through the opinion calibration curve, then blends
    in the ensemble agreement fraction (shrunk) when challengers ran. This is
    what PredictionRecord.confidence stores; the raw value goes to
    stated_confidence so both curves stay measurable.
    """
    base = opinion_calibrated_prob(max(0.0, min(1.0, stated)))
    if agreement is None:
        return base
    shrunk = 0.5 + (max(0.0, min(1.0, agreement)) - 0.5) * ENSEMBLE_SHRINK
    return _sigmoid(0.7 * _logit(base) + 0.3 * _logit(shrunk))


class ProbabilityEstimator:
    """Produces SymbolProbability estimates for thesis vehicles."""

    def __init__(
        self,
        blind_snapshot_path: Optional[Path] = None,
        blind_max_age_hours: float = BLIND_MAX_AGE_HOURS,
        ensemble_lookback_days: int = ENSEMBLE_LOOKBACK_DAYS,
    ):
        self.blind_snapshot_path = blind_snapshot_path or _blind_snapshot_path()
        self.blind_max_age_hours = blind_max_age_hours
        self.ensemble_lookback_days = ensemble_lookback_days
        self._blind_cache: Optional[dict] = None

    # ---- sources -----------------------------------------------------

    def _blind_forecasts(self) -> dict:
        """{symbol: {dir, conf}} from the latest blind snapshot, {} if stale/missing."""
        if self._blind_cache is not None:
            return self._blind_cache
        self._blind_cache = {}
        p = self.blind_snapshot_path
        try:
            if p.exists():
                raw = json.loads(p.read_text())
                generated = datetime.fromisoformat(raw.get("generated_at", "1970-01-01T00:00:00"))
                age_h = (datetime.now() - generated).total_seconds() / 3600
                if age_h <= self.blind_max_age_hours:
                    self._blind_cache = raw.get("forecasts", {}) or {}
                else:
                    logger.info(f"Blind forecasts stale ({age_h:.1f}h) — source dropped")
        except Exception as e:
            logger.warning(f"Blind snapshot unreadable: {e}")
        return self._blind_cache

    def _blind_prob(self, symbol: str) -> Optional[float]:
        """P(long thesis direction correct) from the blind forecast, if fresh.

        Theses here are long-only vehicles: a bullish blind call agrees, a
        bearish one is evidence against at the same calibrated strength.
        """
        fc = self._blind_forecasts().get(symbol)
        if not fc:
            return None
        conf = float(fc.get("conf", 0.5) or 0.5)
        direction = str(fc.get("dir", "neutral")).lower()
        calibrated = opinion_calibrated_prob(conf)
        if direction == "bullish":
            return calibrated
        if direction == "bearish":
            return 1.0 - calibrated
        return 0.5

    def _ensemble_prob(self, symbol: str) -> Optional[float]:
        """Shrunk agreement fraction from the symbol's latest ensemble run."""
        try:
            from src.db.database import get_db
            from src.db.models import DecisionRecord

            cutoff = datetime.now() - timedelta(days=self.ensemble_lookback_days)
            with get_db() as session:
                rec = (
                    session.query(DecisionRecord)
                    .filter(
                        DecisionRecord.symbol == symbol,
                        DecisionRecord.ensemble_data.isnot(None),
                        DecisionRecord.timestamp >= cutoff,
                    )
                    .order_by(DecisionRecord.timestamp.desc())
                    .first()
                )
                if rec is None:
                    return None
                data = json.loads(rec.ensemble_data)
            count = data.get("consensus_count")
            if count is None:
                return None
            agreement = float(count) / 3.0
            return 0.5 + (agreement - 0.5) * ENSEMBLE_SHRINK
        except Exception as e:
            logger.debug(f"Ensemble source unavailable for {symbol}: {e}")
            return None

    # ---- estimates ---------------------------------------------------

    def estimate(self, symbol: str, thesis) -> SymbolProbability:
        conviction = float(getattr(thesis, "conviction", 50.0) or 50.0)
        sources: dict[str, float] = {
            "curve": opinion_calibrated_prob(conviction / 100.0),
        }
        blind = self._blind_prob(symbol)
        if blind is not None:
            sources["blind"] = blind
        ens = self._ensemble_prob(symbol)
        if ens is not None:
            sources["ensemble"] = ens

        p = blend_log_odds(sources)
        p = min(max(p, CLAMP_LO), CLAMP_HI)

        red_flags: list[str] = []
        if conviction >= RED_FLAG_CONVICTION:
            # 90%+ stated conviction resolved at ~33% historically: cap at the
            # curve prior — extreme confidence never buys extra size.
            red_flags.append("stated_conf_ge_90")
            p = min(p, sources["curve"])

        return SymbolProbability(
            symbol=symbol,
            p_direction=p,
            thesis_id=getattr(thesis, "id", None),
            sources=sources,
            n_effective=len(sources),
            red_flags=red_flags,
        )

    def estimate_map(self, theses) -> dict[str, SymbolProbability]:
        """One SymbolProbability per vehicle across all theses (max-conviction wins ties)."""
        out: dict[str, SymbolProbability] = {}
        for th in theses:
            for sym in getattr(th, "positions", None) or []:
                sp = self.estimate(sym, th)
                if sym not in out or sp.p_direction > out[sym].p_direction:
                    out[sym] = sp
        return out

    def thesis_probability(self, thesis, prob_map: Optional[dict[str, SymbolProbability]] = None) -> float:
        """Mean vehicle probability for a thesis (used for the budget ladder)."""
        symbols = getattr(thesis, "positions", None) or []
        if not symbols:
            return 0.5
        probs = []
        for sym in symbols:
            sp = (prob_map or {}).get(sym) or self.estimate(sym, thesis)
            probs.append(sp.p_direction)
        return sum(probs) / len(probs)
