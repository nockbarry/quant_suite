"""Log-odds (likelihood-ratio) belief updates — the C5 seam.

Replaces the additive +5/+2/-5/-10 conviction-nudge table with a proper
Bayesian update when ATHENA_LR_UPDATES=1. Properties the additive table
lacks:

- symmetry: evidence and its exact opposite cancel (LR * 1/LR = 1)
- saturation: the same evidence moves 50% conviction more than 90% —
  no ratchet toward the ceiling
- pooling: heterogeneous evidence (scored predictions, blind forecasts)
  multiplies in one currency instead of ad-hoc point values

The velocity cap (±5pp/run) and archetype ceiling in
belief_updater._auto_apply_suggestions stay unchanged on top of this —
the seam replaces only the evidence→delta mapping.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def logit(p: float) -> float:
    p = min(max(float(p), 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def evidence_lr(hits: int, n: int, base_rate: float = 0.5) -> float:
    """Likelihood ratio for n Bernoulli observations with `hits` successes.

    Laplace-smoothed hit rate against the base rate: LR > 1 supports the
    thesis, LR < 1 opposes. A 50% hit rate at base 0.5 returns exactly 1.
    """
    if n <= 0:
        return 1.0
    p_hat = (hits + 1) / (n + 2)
    return (p_hat / (1 - p_hat)) / (base_rate / (1 - base_rate))


def blind_forecast_lr(p_blind: float, shrink: float = 0.5) -> float:
    """LR contribution of a fresh blind forecast probability (single soft obs).

    Shrunk toward 1 — one day's forecast is one observation, not a study.
    """
    p = min(max(float(p_blind), 1e-4), 1 - 1e-4)
    return math.exp(shrink * (logit(p) - logit(0.5)))


def apply_log_odds_update(prior_pct: float, lr: float, cap_pp: float = 5.0) -> float:
    """Posterior conviction (0-100) after applying LR, capped at ±cap_pp.

    The cap here mirrors (not replaces) the belief updater's velocity cap so
    the function is safe to use standalone.
    """
    prior_pct = min(max(float(prior_pct), 1.0), 99.0)
    posterior = sigmoid(logit(prior_pct / 100.0) + math.log(max(lr, 1e-6))) * 100.0
    delta = max(-cap_pp, min(cap_pp, posterior - prior_pct))
    return prior_pct + delta
