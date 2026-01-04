"""Machine Learning Strategies.

Provides ML-based trading strategies:

Classical ML:
- XGBoostStrategy: Gradient boosted trees
- RandomForestStrategy: Bagged decision trees
- SVMStrategy: Support vector machine
- GradientBoostingStrategy: sklearn gradient boosting

Deep Learning:
- LSTMStrategy: Long short-term memory networks
- TransformerStrategy: Attention-based models
- CNNStrategy: Convolutional neural networks
- CNNLSTMStrategy: Hybrid CNN-LSTM architecture
"""

from .classical import (
    ClassicalMLStrategy,
    FeatureSet,
    GradientBoostingStrategy,
    MLModelConfig,
    PredictionTarget,
    RandomForestStrategy,
    SVMStrategy,
    XGBoostStrategy,
    create_ml_strategy,
)
from .deep_learning import (
    CNNLSTMStrategy,
    CNNStrategy,
    DeepLearningConfig,
    DeepLearningStrategy,
    LSTMStrategy,
    ModelArchitecture,
    TransformerStrategy,
    create_deep_learning_strategy,
)

__all__ = [
    # Classical ML Base
    "ClassicalMLStrategy",
    # Classical Configuration
    "MLModelConfig",
    "PredictionTarget",
    "FeatureSet",
    # Classical Strategies
    "XGBoostStrategy",
    "RandomForestStrategy",
    "SVMStrategy",
    "GradientBoostingStrategy",
    # Classical Factory
    "create_ml_strategy",
    # Deep Learning Base
    "DeepLearningStrategy",
    # Deep Learning Configuration
    "DeepLearningConfig",
    "ModelArchitecture",
    # Deep Learning Strategies
    "LSTMStrategy",
    "TransformerStrategy",
    "CNNStrategy",
    "CNNLSTMStrategy",
    # Deep Learning Factory
    "create_deep_learning_strategy",
]
