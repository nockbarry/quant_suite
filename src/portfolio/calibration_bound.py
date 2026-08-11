"""Opinion-derived calibration bound for the TargetPortfolioBuilder (Phase 6).

The builder sizes off conviction; this supplies an OPTIONAL sanity ceiling so a
position can be trimmed when the short-horizon directional skill behind it is
genuinely poor. It reads the market-OPINION calibration curve
(~/quant_results/intelligence/opinion_calibration.json), NOT the inverted
decision-prediction curve in calibrated_confidence.py — feeding that one in
would reproduce the original bug (everything squashed to 3-5%).

The bound is deliberately LOOSE (floored at 5%): it only bites on real,
sustained overconfidence, never on a normally-calibrated high-conviction call.
Disabled by default; enable in cron_build_target via ATHENA_CALIBRATION_BOUND=1
after the shadow period validates it.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

MIN_BIN_COUNT = 50    # ignore thin bins
BOUND_FLOOR = 0.05    # never cap below 5% — sanity ceiling, not a squasher


def _opinion_calibration_path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "intelligence" / "opinion_calibration.json"


def _curve() -> list[tuple[float, float]]:
    """(predicted, actual_direction_rate) points from well-populated bins."""
    p = _opinion_calibration_path()
    if not p.exists():
        return []
    try:
        bins = json.loads(p.read_text()).get("bins", [])
    except Exception:
        return []
    pts = [
        (float(b["predicted_confidence"]), float(b["actual_direction_rate"]))
        for b in bins
        if b.get("count", 0) >= MIN_BIN_COUNT
        and b.get("predicted_confidence") is not None
        and b.get("actual_direction_rate") is not None
    ]
    pts.sort()
    return pts


def opinion_calibrated_prob(conviction_frac: float) -> float:
    """Map conviction (0-1) to empirical direction rate via opinion bins."""
    c = max(0.0, min(1.0, conviction_frac))
    pts = _curve()
    if not pts:
        return c  # no data -> identity
    if c <= pts[0][0]:
        return pts[0][1]
    if c >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= c <= x1 and x1 > x0:
            return y0 + (y1 - y0) * (c - x0) / (x1 - x0)
    return c


def opinion_calibration_bound(conviction_frac: float) -> float:
    """Max weight (fraction of equity) allowed for a position at this conviction.

    Loose schedule keyed off the OPINION-calibrated direction rate:
        >= 0.60 -> 0.12 (effectively unbounded vs the 10% position cap)
        >= 0.50 -> 0.10
        >= 0.40 -> 0.07
        else    -> 0.05 (floor)
    """
    p = opinion_calibrated_prob(conviction_frac)
    if p >= 0.60:
        return 0.12
    if p >= 0.50:
        return 0.10
    if p >= 0.40:
        return 0.07
    return BOUND_FLOOR


def get_calibration_bound() -> Optional[Callable[[float], float]]:
    """Return the bound callable iff ATHENA_CALIBRATION_BOUND is enabled and data exists."""
    if os.environ.get("ATHENA_CALIBRATION_BOUND", "0") != "1":
        return None
    if not _curve():
        logger.warning("Calibration bound requested but no opinion calibration data; skipping")
        return None
    return opinion_calibration_bound
