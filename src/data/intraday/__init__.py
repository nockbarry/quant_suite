"""
Intraday data analysis module.

Provides:
- Candle pattern recognition and interpretation
- Intraday feature engineering (VWAP, ORB, volume profile)
- Multi-timeframe analysis
"""

from .candle_analysis import (
    CandlePattern,
    PatternBias,
    PatternStrength,
    CandleMetrics,
    PatternMatch,
    CandleInterpretation,
    CandlePatternRecognizer,
    CandleInterpreter,
)

from .feature_engine import (
    MarketSession,
    ORBSignal,
    VWAPData,
    OpeningRangeData,
    VolumeProfileData,
    IntradayMomentum,
    IntradayFeatures,
    IntradayFeatureEngine,
)

__all__ = [
    # Candle analysis
    "CandlePattern",
    "PatternBias",
    "PatternStrength",
    "CandleMetrics",
    "PatternMatch",
    "CandleInterpretation",
    "CandlePatternRecognizer",
    "CandleInterpreter",
    # Feature engine
    "MarketSession",
    "ORBSignal",
    "VWAPData",
    "OpeningRangeData",
    "VolumeProfileData",
    "IntradayMomentum",
    "IntradayFeatures",
    "IntradayFeatureEngine",
]
