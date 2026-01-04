"""Alternative data strategies using sentiment, embeddings, and quantitative techniques."""

from .contrarian import (
    InverseSentimentStrategy,
    ManufacturedSentimentDetector,
    ManufacturedSentimentStrategy,
    SentimentDivergenceStrategy,
    SentimentExtreme,
    SentimentExtremesStrategy,
    SentimentHistory,
    calculate_contrarian_metrics,
)
from .correlation import (
    BreakdownType,
    CorrelationBreakdownDetector,
    CorrelationBreakdownStrategy,
    CorrelationMatrix,
    CorrelationPair,
    CorrelationRegime,
    DispersionStrategy,
    calculate_dynamic_correlation,
    test_correlation_stability,
)
from .embeddings import (
    BEARISH_PATTERNS,
    BULLISH_PATTERNS,
    EmbeddingMomentumStrategy,
    NewsSimilarityStrategy,
    SemanticPatternStrategy,
    SemanticSignal,
)
from .renaissance import (
    AutocorrelationAnalyzer,
    CointegrationResult,
    CointegrationTester,
    KalmanHedgeRatioEstimator,
    LeadLagAnalyzer,
    LeadLagResult,
    LeadLagStrategy,
    OrderFlowEstimator,
    OrderFlowStrategy,
    RegimeConditionalStrategy,
    RegimeDetector,
    RegimeState,
    StatisticalArbitrageStrategy,
)
from .sentiment import (
    NewsSentimentStrategy,
    SentimentAnalyzer,
    SentimentMomentumStrategy,
    SentimentScore,
    aggregate_sentiment_scores,
)
from .sec_alpha import (
    SECFilingAlpha,
    FilingAlphaSignal,
    FilingFeatures,
    FilingSignal,
    get_filing_signal,
)
from .narrative_momentum import (
    NarrativeMomentum,
    NarrativeMomentumSignal,
    NarrativeFeatures,
    NarrativeSignal,
    NarrativeEnsemble,
    get_narrative_signal,
)
from .composite_alternative import (
    CompositeAlternative,
    CompositeAlternativeSignal,
    CompositeFeatures,
    CompositeSignal,
    AdaptiveComposite,
    get_composite_signal,
    get_top_picks,
)

__all__ = [
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
    # Contrarian
    "SentimentHistory",
    "SentimentExtreme",
    "ManufacturedSentimentDetector",
    "InverseSentimentStrategy",
    "SentimentDivergenceStrategy",
    "ManufacturedSentimentStrategy",
    "SentimentExtremesStrategy",
    "calculate_contrarian_metrics",
    # Renaissance-style techniques
    "CointegrationTester",
    "CointegrationResult",
    "KalmanHedgeRatioEstimator",
    "StatisticalArbitrageStrategy",
    "LeadLagAnalyzer",
    "LeadLagResult",
    "LeadLagStrategy",
    "RegimeDetector",
    "RegimeState",
    "RegimeConditionalStrategy",
    "OrderFlowEstimator",
    "OrderFlowStrategy",
    "AutocorrelationAnalyzer",
    # Correlation breakdown
    "CorrelationRegime",
    "BreakdownType",
    "CorrelationPair",
    "CorrelationMatrix",
    "CorrelationBreakdownDetector",
    "CorrelationBreakdownStrategy",
    "DispersionStrategy",
    "calculate_dynamic_correlation",
    "test_correlation_stability",
    # SEC Filing Alpha
    "SECFilingAlpha",
    "FilingAlphaSignal",
    "FilingFeatures",
    "FilingSignal",
    "get_filing_signal",
    # Narrative Momentum
    "NarrativeMomentum",
    "NarrativeMomentumSignal",
    "NarrativeFeatures",
    "NarrativeSignal",
    "NarrativeEnsemble",
    "get_narrative_signal",
    # Composite Alternative
    "CompositeAlternative",
    "CompositeAlternativeSignal",
    "CompositeFeatures",
    "CompositeSignal",
    "AdaptiveComposite",
    "get_composite_signal",
    "get_top_picks",
]
