"""Traditional rule-based strategies."""

from .factor_models import (
    CrossSectionalMomentumStrategy,
    FactorScore,
    FactorType,
    LowVolatilityStrategy,
    MultiFactorStrategy,
    QualityStrategy,
    ShortTermReversalStrategy,
    ValueStrategy,
    calculate_factor_exposures,
    construct_factor_portfolio,
)
from .mean_reversion import (
    BollingerBandMeanReversion,
    PairsTradingStrategy,
    RSIMeanReversion,
)
from .trend_following import (
    BreakoutStrategy,
    MomentumStrategy,
    MovingAverageCrossover,
    TrendStrengthStrategy,
)

__all__ = [
    # Trend following
    "MovingAverageCrossover",
    "BreakoutStrategy",
    "TrendStrengthStrategy",
    "MomentumStrategy",
    # Mean reversion
    "BollingerBandMeanReversion",
    "PairsTradingStrategy",
    "RSIMeanReversion",
    # Factor models
    "FactorType",
    "FactorScore",
    "CrossSectionalMomentumStrategy",
    "ValueStrategy",
    "LowVolatilityStrategy",
    "QualityStrategy",
    "ShortTermReversalStrategy",
    "MultiFactorStrategy",
    "calculate_factor_exposures",
    "construct_factor_portfolio",
]
