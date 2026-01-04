"""
Regime Detection Module.

Provides market regime classification using volatility, trend,
correlation, and sentiment signals.
"""

from .regime_classifier import (
    MarketRegime,
    RegimeClassifier,
    RegimeIndicators,
    RegimeState,
    classify_from_market_data,
)

__all__ = [
    "MarketRegime",
    "RegimeClassifier",
    "RegimeIndicators",
    "RegimeState",
    "classify_from_market_data",
]
