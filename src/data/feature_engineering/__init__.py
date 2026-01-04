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
]
