"""
Regime Detection Module.

Provides market regime classification using volatility, trend,
correlation, and sentiment signals.

Two approaches available:
1. RegimeClassifier - General regime detection using VIX, ADX, correlation
2. EmpiricalRegimeClassifier - Based on empirical analysis of 470+ strategies

Use EmpiricalRegimeClassifier for strategy selection based on our backtesting.
"""

from .regime_classifier import (
    # General regime classification
    MarketRegime,
    RegimeClassifier,
    RegimeIndicators,
    RegimeState,
    classify_from_market_data,
    # Empirical regime classification (from mid/small cap analysis)
    VolatilityTrendRegime,
    EmpiricalRegimeState,
    EmpiricalRegimeClassifier,
    StrategyRecommendation,
    EMPIRICAL_REGIME_PERFORMANCE,
    MIDCAP_ALPHA_UNIVERSE,
    get_symbols_for_regime,
)

__all__ = [
    # General
    "MarketRegime",
    "RegimeClassifier",
    "RegimeIndicators",
    "RegimeState",
    "classify_from_market_data",
    # Empirical
    "VolatilityTrendRegime",
    "EmpiricalRegimeState",
    "EmpiricalRegimeClassifier",
    "StrategyRecommendation",
    "EMPIRICAL_REGIME_PERFORMANCE",
    "MIDCAP_ALPHA_UNIVERSE",
    "get_symbols_for_regime",
]
