"""Trading strategies."""

from .alternative import (
    BEARISH_PATTERNS,
    BULLISH_PATTERNS,
    EmbeddingMomentumStrategy,
    NewsSentimentStrategy,
    NewsSimilarityStrategy,
    SemanticPatternStrategy,
    SemanticSignal,
    SentimentAnalyzer,
    SentimentMomentumStrategy,
    SentimentScore,
    aggregate_sentiment_scores,
)
from .base import MLStrategy, RuleBasedStrategy, Strategy, StrategyConfig
from .definition import (
    StrategyDefinition,
    StrategyRegistry,
    StrategyCategory,
    StrategySubcategory,
    EdgeSource,
    ExecutionUrgency,
    UniverseConfig,
    RiskConfig,
    PerformanceTarget,
    create_momentum_strategy_definition,
    create_mean_reversion_strategy_definition,
    create_sentiment_strategy_definition,
)
from .traditional.factor_models import (
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
from .traditional.mean_reversion import (
    BollingerBandMeanReversion,
    PairsTradingStrategy,
    RSIMeanReversion,
)
from .traditional.trend_following import (
    BreakoutStrategy,
    MomentumStrategy,
    MovingAverageCrossover,
    TrendStrengthStrategy,
)

__all__ = [
    # Base
    "Strategy",
    "StrategyConfig",
    "RuleBasedStrategy",
    "MLStrategy",
    # Strategy Definition Schema
    "StrategyDefinition",
    "StrategyRegistry",
    "StrategyCategory",
    "StrategySubcategory",
    "EdgeSource",
    "ExecutionUrgency",
    "UniverseConfig",
    "RiskConfig",
    "PerformanceTarget",
    "create_momentum_strategy_definition",
    "create_mean_reversion_strategy_definition",
    "create_sentiment_strategy_definition",
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
    # Sentiment
    "SentimentAnalyzer",
    "SentimentScore",
    "NewsSentimentStrategy",
    "SentimentMomentumStrategy",
    "aggregate_sentiment_scores",
    # Embeddings
    "SemanticSignal",
    "SemanticPatternStrategy",
    "NewsSimilarityStrategy",
    "EmbeddingMomentumStrategy",
    "BULLISH_PATTERNS",
    "BEARISH_PATTERNS",
]
