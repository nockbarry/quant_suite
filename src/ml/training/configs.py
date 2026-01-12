"""ML Training Configurations.

Defines model configurations, target types, and universe specifications
for systematic ML model training.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelType(str, Enum):
    """Supported model types."""
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    ELASTIC_NET = "elastic_net"
    RIDGE = "ridge"
    LASSO = "lasso"
    SVM = "svm"
    LSTM = "lstm"
    TRANSFORMER = "transformer"


class TargetType(str, Enum):
    """Target variable types."""
    CLASSIFICATION = "classification"  # Binary up/down
    MULTICLASS = "multiclass"  # Multiple classes
    REGRESSION = "regression"  # Continuous returns


class FeatureSetType(str, Enum):
    """Feature set types."""
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    FLOW = "flow"
    ALTERNATIVE = "alternative"
    LATENT = "latent"
    ALL = "all"


@dataclass
class TargetConfig:
    """Configuration for target variable."""
    name: str
    target_type: TargetType
    horizon: int  # Days ahead to predict
    threshold: float = 0.0  # For classification (above/below)
    description: str = ""


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    model_type: ModelType
    hyperparams: dict[str, Any] = field(default_factory=dict)
    requires_scaling: bool = True
    supports_gpu: bool = False


@dataclass
class TrainingConfig:
    """Full training configuration."""
    name: str
    target: TargetConfig
    models: list[ModelConfig]
    feature_sets: list[FeatureSetType]
    train_days: int = 252  # Training window
    test_days: int = 63  # Test window
    gap_days: int = 5  # Gap between train/test
    min_samples: int = 500  # Minimum training samples
    n_cv_splits: int = 5  # Number of CV splits
    mcpt_permutations: int = 1000  # MCPT permutations


# =============================================================================
# PREDEFINED TARGETS
# =============================================================================


TARGETS = {
    "direction_1d": TargetConfig(
        name="direction_1d",
        target_type=TargetType.CLASSIFICATION,
        horizon=1,
        threshold=0.0,
        description="Binary up/down next day",
    ),
    "direction_5d": TargetConfig(
        name="direction_5d",
        target_type=TargetType.CLASSIFICATION,
        horizon=5,
        threshold=0.0,
        description="Binary up/down next week",
    ),
    "return_5d": TargetConfig(
        name="return_5d",
        target_type=TargetType.REGRESSION,
        horizon=5,
        description="5-day forward return",
    ),
    "return_20d": TargetConfig(
        name="return_20d",
        target_type=TargetType.REGRESSION,
        horizon=20,
        description="20-day forward return",
    ),
    "vol_regime": TargetConfig(
        name="vol_regime",
        target_type=TargetType.MULTICLASS,
        horizon=5,
        description="Volatility regime (low/normal/high)",
    ),
    "drawdown_risk": TargetConfig(
        name="drawdown_risk",
        target_type=TargetType.CLASSIFICATION,
        horizon=20,
        threshold=-0.05,  # 5% drawdown
        description="Probability of 5%+ drawdown",
    ),
}


# =============================================================================
# PREDEFINED MODEL CONFIGS
# =============================================================================


MODELS = {
    "xgboost": ModelConfig(
        model_type=ModelType.XGBOOST,
        hyperparams={
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "random_state": 42,
        },
        requires_scaling=False,
        supports_gpu=True,
    ),
    "lightgbm": ModelConfig(
        model_type=ModelType.LIGHTGBM,
        hyperparams={
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "random_state": 42,
            "verbose": -1,
        },
        requires_scaling=False,
        supports_gpu=True,
    ),
    "random_forest": ModelConfig(
        model_type=ModelType.RANDOM_FOREST,
        hyperparams={
            "n_estimators": 100,
            "max_depth": 10,
            "min_samples_split": 20,
            "min_samples_leaf": 10,
            "max_features": "sqrt",
            "random_state": 42,
            "n_jobs": -1,
        },
        requires_scaling=False,
    ),
    "gradient_boosting": ModelConfig(
        model_type=ModelType.GRADIENT_BOOSTING,
        hyperparams={
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.05,
            "min_samples_split": 20,
            "min_samples_leaf": 10,
            "subsample": 0.8,
            "random_state": 42,
        },
        requires_scaling=False,
    ),
    "elastic_net": ModelConfig(
        model_type=ModelType.ELASTIC_NET,
        hyperparams={
            "alpha": 1.0,
            "l1_ratio": 0.5,
            "max_iter": 1000,
            "random_state": 42,
        },
        requires_scaling=True,
    ),
    "ridge": ModelConfig(
        model_type=ModelType.RIDGE,
        hyperparams={
            "alpha": 1.0,
            "random_state": 42,
        },
        requires_scaling=True,
    ),
    "svm": ModelConfig(
        model_type=ModelType.SVM,
        hyperparams={
            "C": 1.0,
            "kernel": "rbf",
            "probability": True,
            "random_state": 42,
        },
        requires_scaling=True,
    ),
}


# =============================================================================
# FULL TRAINING CONFIGS
# =============================================================================


MODEL_CONFIGS = {
    "direction_1d_ensemble": TrainingConfig(
        name="direction_1d_ensemble",
        target=TARGETS["direction_1d"],
        models=[MODELS["xgboost"], MODELS["lightgbm"], MODELS["random_forest"]],
        feature_sets=[FeatureSetType.TECHNICAL, FeatureSetType.SENTIMENT, FeatureSetType.FLOW],
    ),
    "direction_5d_full": TrainingConfig(
        name="direction_5d_full",
        target=TARGETS["direction_5d"],
        models=[MODELS["xgboost"], MODELS["lightgbm"]],
        feature_sets=[FeatureSetType.ALL],
    ),
    "return_5d_regression": TrainingConfig(
        name="return_5d_regression",
        target=TARGETS["return_5d"],
        models=[MODELS["xgboost"], MODELS["lightgbm"], MODELS["elastic_net"]],
        feature_sets=[FeatureSetType.ALL],
    ),
    "vol_regime_classifier": TrainingConfig(
        name="vol_regime_classifier",
        target=TARGETS["vol_regime"],
        models=[MODELS["xgboost"], MODELS["random_forest"]],
        feature_sets=[FeatureSetType.TECHNICAL, FeatureSetType.LATENT],
    ),
    "drawdown_risk_classifier": TrainingConfig(
        name="drawdown_risk_classifier",
        target=TARGETS["drawdown_risk"],
        models=[MODELS["xgboost"], MODELS["lightgbm"]],
        feature_sets=[FeatureSetType.TECHNICAL, FeatureSetType.SENTIMENT],
    ),
}


# =============================================================================
# UNIVERSE CONFIGURATIONS
# =============================================================================


UNIVERSE_CONFIGS = {
    "mega_cap": {
        "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
        "description": "Mega-cap tech leaders",
    },
    "sp500_tech": {
        "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
                    "AVGO", "AMD", "CRM", "ORCL", "ADBE", "CSCO", "INTC"],
        "description": "S&P 500 Technology sector",
    },
    "sp500_financials": {
        "symbols": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK",
                    "SCHW", "AXP", "USB"],
        "description": "S&P 500 Financials sector",
    },
    "sp500_healthcare": {
        "symbols": ["UNH", "JNJ", "LLY", "MRK", "ABBV", "PFE",
                    "TMO", "ABT", "DHR", "BMY"],
        "description": "S&P 500 Healthcare sector",
    },
    "sp500_energy": {
        "symbols": ["XOM", "CVX", "SLB", "COP", "EOG", "MPC",
                    "PSX", "VLO", "OXY", "HAL"],
        "description": "S&P 500 Energy sector",
    },
    "sp500_consumer": {
        "symbols": ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX",
                    "LOW", "TGT", "TJX", "CMG"],
        "description": "S&P 500 Consumer Discretionary",
    },
    "major_etfs": {
        "symbols": ["SPY", "QQQ", "IWM", "DIA", "XLE", "XLF",
                    "XLK", "XLV", "XLI", "XLP"],
        "description": "Major sector ETFs",
    },
    "high_volume": {
        "symbols": ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD",
                    "AMZN", "META", "GOOGL", "MSFT"],
        "description": "Highest volume symbols",
    },
}


def get_all_symbols() -> list[str]:
    """Get all unique symbols across all universes."""
    all_symbols = set()
    for config in UNIVERSE_CONFIGS.values():
        all_symbols.update(config["symbols"])
    return sorted(list(all_symbols))


def get_training_config(name: str) -> TrainingConfig:
    """Get a training configuration by name."""
    if name not in MODEL_CONFIGS:
        raise ValueError(f"Unknown training config: {name}")
    return MODEL_CONFIGS[name]


def get_universe_symbols(name: str) -> list[str]:
    """Get symbols for a universe."""
    if name not in UNIVERSE_CONFIGS:
        raise ValueError(f"Unknown universe: {name}")
    return UNIVERSE_CONFIGS[name]["symbols"]
