"""Machine Learning Module for Quantitative Trading.

This module provides:
- Training pipelines with walk-forward validation
- Model configurations for different targets
- MCPT validation for statistical significance
- Model serving for production signals
"""

from .training.pipeline import (
    MLTrainingPipeline,
    TrainingResult,
    TrainedModel,
    MCPTResult,
    create_target,
    create_features_and_target,
)
from .training.configs import (
    ModelConfig,
    TrainingConfig,
    TargetConfig,
    MODEL_CONFIGS,
    UNIVERSE_CONFIGS,
    MODELS,
    TARGETS,
    ModelType,
    TargetType,
    FeatureSetType,
    get_all_symbols,
    get_training_config,
    get_universe_symbols,
)
from .training.walk_forward import (
    WalkForwardSplitter,
    WalkForwardResult,
    PurgedKFold,
    compute_sample_weights,
)
from .serving.model_server import (
    ModelServer,
    ModelRegistry,
    PredictionResult,
)

__all__ = [
    # Training Pipeline
    "MLTrainingPipeline",
    "TrainingResult",
    "TrainedModel",
    "MCPTResult",
    "create_target",
    "create_features_and_target",
    # Configs
    "ModelConfig",
    "TrainingConfig",
    "TargetConfig",
    "MODEL_CONFIGS",
    "UNIVERSE_CONFIGS",
    "MODELS",
    "TARGETS",
    "ModelType",
    "TargetType",
    "FeatureSetType",
    "get_all_symbols",
    "get_training_config",
    "get_universe_symbols",
    # Walk Forward
    "WalkForwardSplitter",
    "WalkForwardResult",
    "PurgedKFold",
    "compute_sample_weights",
    # Model Serving
    "ModelServer",
    "ModelRegistry",
    "PredictionResult",
]
