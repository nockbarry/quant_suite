"""Feature engineering and storage for quantitative analysis."""

from .feature_store import FeatureStore, FeatureMetadata, FeatureVersion
from .feature_registry import (
    FeatureDefinition,
    FeatureCategory,
    FEATURE_REGISTRY,
    FeatureComputer,
    get_feature_definition,
    list_features_by_category,
)
from .feature_stability import (
    FeatureStabilityMonitor,
    FeatureStabilityReport,
    PortfolioStabilityReport,
)
from .feature_interactions import (
    FeatureInteractionGenerator,
    InteractionFeature,
    InteractionResult,
    PolynomialFeatureGenerator,
    LaggedFeatureGenerator,
)
from .feature_discovery import (
    FeatureDiscoveryEngine,
    FeatureDomain,
    FeatureIdea,
    FeatureGap,
    suggest_features_for_symbol,
)
from .technical_enhanced import (
    EnhancedTechnicalFeatures,
    compute_momentum_alignment,
    compute_momentum_divergence,
    compute_volatility_regime_features,
    compute_volatility_breakout,
    compute_cross_asset_sensitivity,
    compute_sector_correlation,
    compute_signal_confirmation,
)
from .alternative_features import (
    AlternativeDataFeatures,
    compute_congressional_features,
    compute_insider_features,
    compute_options_flow_features,
    compute_sentiment_features,
    compute_event_features,
)
from .latent_knowledge_features import (
    LatentKnowledgeFeatures,
    compute_sector_lead_signal,
    compute_calendar_features,
    compute_gap_features,
    compute_vix_features,
    compute_cross_asset_features,
    compute_earnings_pattern_features,
    SECTOR_LEAD_RELATIONSHIPS,
)

__all__ = [
    # Feature Store
    "FeatureStore",
    "FeatureMetadata",
    "FeatureVersion",
    # Feature Registry
    "FeatureDefinition",
    "FeatureCategory",
    "FEATURE_REGISTRY",
    "FeatureComputer",
    "get_feature_definition",
    "list_features_by_category",
    # Feature Stability
    "FeatureStabilityMonitor",
    "FeatureStabilityReport",
    "PortfolioStabilityReport",
    # Feature Interactions
    "FeatureInteractionGenerator",
    "InteractionFeature",
    "InteractionResult",
    "PolynomialFeatureGenerator",
    "LaggedFeatureGenerator",
    # Feature Discovery
    "FeatureDiscoveryEngine",
    "FeatureDomain",
    "FeatureIdea",
    "FeatureGap",
    "suggest_features_for_symbol",
    # Enhanced Technical Features
    "EnhancedTechnicalFeatures",
    "compute_momentum_alignment",
    "compute_momentum_divergence",
    "compute_volatility_regime_features",
    "compute_volatility_breakout",
    "compute_cross_asset_sensitivity",
    "compute_sector_correlation",
    "compute_signal_confirmation",
    # Alternative Data Features
    "AlternativeDataFeatures",
    "compute_congressional_features",
    "compute_insider_features",
    "compute_options_flow_features",
    "compute_sentiment_features",
    "compute_event_features",
    # Latent Knowledge Features
    "LatentKnowledgeFeatures",
    "compute_sector_lead_signal",
    "compute_calendar_features",
    "compute_gap_features",
    "compute_vix_features",
    "compute_cross_asset_features",
    "compute_earnings_pattern_features",
    "SECTOR_LEAD_RELATIONSHIPS",
]
