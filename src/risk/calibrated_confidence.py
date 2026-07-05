"""Confidence calibration — map stated confidence to empirical hit rate.

Fixes the overconfidence bug: 90%+ stated predictions hit ~35%, 80-90% hit ~37%,
but <50% and 50-60% stated are well-calibrated. Sizing keys off stated confidence,
so 95%-conviction positions get sized for 95% odds on a 40% coin-flip.

This module applies isotonic regression to the calibration bins and exposes:
    calibrate(stated) -> empirical_probability
    calibrated_max_position_pct(stated) -> float  (0-1, used by sizer)

Reads ~/quant_results/intelligence/calibration.json written by BeliefUpdater.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHED: Optional[dict] = None
_CACHE_MTIME: float = 0.0

DEFAULT_MIN_SAMPLES = 20  # Fall back to identity if a bin has fewer samples
IDENTITY_FLOOR = 0.05     # Never return <5% even if empirical is worse
IDENTITY_CEILING = 0.95   # Never return >95% (matches thesis ceiling)


def _calibration_path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "intelligence" / "calibration.json"


def _load() -> dict:
    """Load calibration file, cache by mtime."""
    global _CACHED, _CACHE_MTIME
    p = _calibration_path()
    if not p.exists():
        return {}
    mtime = p.stat().st_mtime
    if _CACHED is not None and mtime == _CACHE_MTIME:
        return _CACHED
    try:
        _CACHED = json.loads(p.read_text())
        _CACHE_MTIME = mtime
        return _CACHED
    except Exception as e:
        logger.warning(f"Failed to load calibration.json: {e}")
        return {}


def _bin_points(bins: list[dict]) -> list[tuple[float, float]]:
    """Return (predicted, actual) pairs from bins with enough samples, sorted.

    The calibration curve is empirically non-monotone in this system
    (overconfidence concentrates in the high tail), so we do NOT enforce
    monotonicity — that's the bug we're trying to surface, not hide.
    """
    pts = []
    for b in bins:
        n = b.get("n", 0)
        if n < DEFAULT_MIN_SAMPLES:
            continue
        pts.append((float(b.get("predicted", 0.5)), float(b.get("actual", 0.5))))
    pts.sort(key=lambda x: x[0])
    return pts


def calibrate(stated: float) -> float:
    """Map stated confidence (0-1) to empirical probability via isotonic interpolation.

    If calibration data is absent or thin, returns stated confidence unchanged.
    """
    stated = max(0.0, min(1.0, float(stated)))
    data = _load()
    bins = data.get("bins", [])
    if not bins:
        return stated

    points = _bin_points(bins)
    if not points:
        return stated
    if len(points) == 1:
        return max(IDENTITY_FLOOR, min(IDENTITY_CEILING, points[0][1]))

    # Linear interpolation between pooled points
    if stated <= points[0][0]:
        return max(IDENTITY_FLOOR, points[0][1])
    if stated >= points[-1][0]:
        return min(IDENTITY_CEILING, points[-1][1])

    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if x0 <= stated <= x1:
            if x1 == x0:
                return y0
            t = (stated - x0) / (x1 - x0)
            return max(IDENTITY_FLOOR, min(IDENTITY_CEILING, y0 + t * (y1 - y0)))
    return stated


def calibrated_max_position_pct(stated_confidence: float) -> float:
    """Position sizing cap as a fraction of portfolio (0-1), keyed off calibrated confidence.

    Piecewise schedule matching CLAUDE.md position sizing but using calibrated
    probability rather than stated confidence:

        calibrated >= 0.80 → 10%
        calibrated >= 0.65 → 7%
        calibrated >= 0.50 → 5%
        else              → 3%
    """
    p = calibrate(stated_confidence)
    if p >= 0.80:
        return 0.10
    if p >= 0.65:
        return 0.07
    if p >= 0.50:
        return 0.05
    return 0.03


def calibrated_conviction_pct(stated_conviction: float) -> float:
    """Apply calibration to a 0-100 thesis conviction.

    A thesis stated at 95% conviction with 35% empirical accuracy in the top bin
    will be returned as ~35, pulling sizing down to the 3% tier.
    """
    stated_frac = max(0.0, min(100.0, float(stated_conviction))) / 100.0
    return calibrate(stated_frac) * 100.0


def calibration_gap() -> Optional[float]:
    """Overall calibration error (stated - empirical) across resolved predictions, 0-1.

    Positive means overconfident. Returns None if data absent.
    """
    data = _load()
    if not data:
        return None
    err = data.get("calibration_error")
    return float(err) if err is not None else None
