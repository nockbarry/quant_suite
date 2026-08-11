"""Probability estimation layer — separates advocacy from sizing.

Thesis conviction is an advocacy/governance scalar (review cadence,
invalidation, exits). The measured decision-confidence curve is inverted
(90%+ stated → 33% actual, n=992) while the opinion pipeline is calibrated
(error 0.106, n=5,686). This package produces the calibrated probability
that SIZES positions, blending only calibrated sources:

- curve prior: conviction passed through the opinion calibration curve
- blind forecast: fresh-context LLM forecast, structurally blind to the
  thesis narrative (src/probability/blind_forecast.py)
- ensemble agreement: challenger consensus fraction, shrunk (n=3 is coarse)

Consumed by ConvictionSizer.thesis_budget_from_prob via TargetPortfolioBuilder
under ATHENA_PROB_SIZING=1 (shadow dual-compute until Phase F flips it).
"""

from src.probability.estimator import ProbabilityEstimator, effective_confidence
from src.probability.models import SymbolProbability

__all__ = ["ProbabilityEstimator", "SymbolProbability", "effective_confidence"]
