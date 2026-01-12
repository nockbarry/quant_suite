"""ML Training Pipeline.

End-to-end pipeline for training ML models with proper validation:
1. Load point-in-time features
2. Create targets
3. Walk-forward cross-validation
4. MCPT statistical significance testing
5. Model registration and persistence

Based on "Advances in Financial Machine Learning" by de Prado.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from .configs import (
    ModelConfig,
    TrainingConfig,
    TargetConfig,
    TargetType,
    FeatureSetType,
    ModelType,
    MODELS,
)
from .walk_forward import WalkForwardSplitter, WalkForwardResult

logger = logging.getLogger(__name__)


@dataclass
class MCPTResult:
    """Monte Carlo Permutation Test result."""
    observed_metric: float
    permuted_metrics: list[float]
    p_value: float
    n_permutations: int
    metric_name: str = "sharpe"

    @property
    def is_significant(self) -> bool:
        """Check if result is statistically significant at 0.05."""
        return self.p_value < 0.05

    def __repr__(self) -> str:
        return f"MCPTResult(metric={self.observed_metric:.3f}, p={self.p_value:.4f})"


@dataclass
class TrainedModel:
    """A trained model with metadata."""
    model: Any
    scaler: Optional[StandardScaler]
    config: ModelConfig
    feature_columns: list[str]
    target_config: TargetConfig
    train_date: datetime = field(default_factory=datetime.now)
    metrics: dict[str, float] = field(default_factory=dict)
    mcpt_result: Optional[MCPTResult] = None
    model_id: str = ""

    def __post_init__(self):
        if not self.model_id:
            timestamp = self.train_date.strftime("%Y%m%d_%H%M%S")
            self.model_id = f"{self.config.model_type.value}_{self.target_config.name}_{timestamp}"

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Make predictions."""
        X_prepared = self._prepare_features(X)
        return self.model.predict(X_prepared)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities (for classifiers)."""
        X_prepared = self._prepare_features(X)
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X_prepared)
        return self.predict(X)

    def _prepare_features(self, X: pd.DataFrame) -> np.ndarray:
        """Prepare features for prediction."""
        # Select and order columns
        X_selected = X[self.feature_columns].copy()

        # Handle missing values
        X_selected = X_selected.ffill().bfill().fillna(0)

        # Scale if needed
        if self.scaler is not None:
            X_selected = self.scaler.transform(X_selected)

        return X_selected

    def save(self, path: Path) -> None:
        """Save model to disk."""
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path / f"{self.model_id}.joblib")
        logger.info(f"Saved model to {path / self.model_id}.joblib")

    @classmethod
    def load(cls, path: Path) -> "TrainedModel":
        """Load model from disk."""
        return joblib.load(path)


@dataclass
class TrainingResult:
    """Result of training run."""
    model: TrainedModel
    cv_results: list[WalkForwardResult]
    mcpt_result: MCPTResult
    feature_importance: dict[str, float]
    metadata: dict = field(default_factory=dict)

    @property
    def is_significant(self) -> bool:
        """Check if model is statistically significant."""
        return self.mcpt_result.is_significant

    @property
    def mean_test_score(self) -> float:
        """Mean test score across folds."""
        return np.mean([r.test_score for r in self.cv_results])


class MLTrainingPipeline:
    """
    End-to-end ML training pipeline.

    Example usage:
        ```python
        pipeline = MLTrainingPipeline()

        # Train a single model
        result = await pipeline.train_model(
            model_config=MODELS["xgboost"],
            target_config=TARGETS["direction_5d"],
            symbols=["AAPL", "MSFT"],
            feature_sets=["technical", "sentiment"],
        )

        if result.is_significant:
            result.model.save(Path("models/"))

        # Train all models in a config
        results = await pipeline.train_from_config(
            config=MODEL_CONFIGS["direction_5d_full"],
            symbols=["SPY", "QQQ"],
        )
        ```
    """

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.models_dir = models_dir or Path("~/quant_results/models").expanduser()
        self.cache_dir = cache_dir or Path("~/quant_results/cache").expanduser()
        self.models_dir.mkdir(parents=True, exist_ok=True)

    async def train_model(
        self,
        model_config: ModelConfig,
        target_config: TargetConfig,
        X: pd.DataFrame,
        y: pd.Series,
        train_days: int = 252,
        test_days: int = 63,
        gap_days: int = 5,
        n_permutations: int = 1000,
    ) -> TrainingResult:
        """
        Train a single model with walk-forward validation and MCPT.

        Args:
            model_config: Model configuration
            target_config: Target configuration
            X: Features DataFrame
            y: Target Series
            train_days: Training window size
            test_days: Test window size
            gap_days: Gap between train and test
            n_permutations: MCPT permutations

        Returns:
            TrainingResult with model, metrics, and significance
        """
        logger.info(
            f"Training {model_config.model_type.value} for {target_config.name}"
        )

        # Prepare features
        X_clean = X.ffill().bfill().fillna(0)
        feature_columns = list(X_clean.columns)

        # Scale if needed
        scaler = None
        if model_config.requires_scaling:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_clean)
        else:
            X_scaled = X_clean.values

        # Walk-forward validation
        splitter = WalkForwardSplitter(
            train_size=train_days,
            test_size=test_days,
            gap=gap_days,
        )

        cv_results = []
        all_predictions = []
        all_actuals = []

        for fold, (train_idx, test_idx) in enumerate(splitter.split(X_scaled)):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y.iloc[train_idx].values, y.iloc[test_idx].values

            # Create and train model
            model = self._create_model(model_config, target_config)
            model.fit(X_train, y_train)

            # Evaluate
            if target_config.target_type == TargetType.CLASSIFICATION:
                train_score = model.score(X_train, y_train)
                test_score = model.score(X_test, y_test)
                predictions = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else model.predict(X_test)
            else:
                train_score = self._compute_r2(y_train, model.predict(X_train))
                test_score = self._compute_r2(y_test, model.predict(X_test))
                predictions = model.predict(X_test)

            all_predictions.extend(predictions)
            all_actuals.extend(y_test)

            # Feature importance
            feature_importance = self._get_feature_importance(model, feature_columns)

            cv_results.append(WalkForwardResult(
                fold=fold,
                train_size=len(train_idx),
                test_size=len(test_idx),
                train_score=train_score,
                test_score=test_score,
                predictions=predictions,
                actuals=y_test,
                feature_importance=feature_importance,
            ))

            logger.info(
                f"  Fold {fold + 1}: train={train_score:.3f}, test={test_score:.3f}"
            )

        # Final model on all data
        final_model = self._create_model(model_config, target_config)
        final_model.fit(X_scaled, y.values)

        # MCPT validation
        all_predictions = np.array(all_predictions)
        all_actuals = np.array(all_actuals)
        mcpt_result = self._run_mcpt(
            all_predictions, all_actuals,
            n_permutations=n_permutations,
            target_type=target_config.target_type,
        )

        logger.info(f"  MCPT p-value: {mcpt_result.p_value:.4f}")

        # Create trained model
        trained_model = TrainedModel(
            model=final_model,
            scaler=scaler,
            config=model_config,
            feature_columns=feature_columns,
            target_config=target_config,
            metrics={
                "mean_train_score": np.mean([r.train_score for r in cv_results]),
                "mean_test_score": np.mean([r.test_score for r in cv_results]),
                "mcpt_p_value": mcpt_result.p_value,
            },
            mcpt_result=mcpt_result,
        )

        # Aggregate feature importance
        agg_importance = self._aggregate_feature_importance(cv_results)

        return TrainingResult(
            model=trained_model,
            cv_results=cv_results,
            mcpt_result=mcpt_result,
            feature_importance=agg_importance,
        )

    async def train_from_config(
        self,
        config: TrainingConfig,
        X: pd.DataFrame,
        y: pd.Series,
    ) -> list[TrainingResult]:
        """
        Train all models defined in a training config.

        Args:
            config: Training configuration
            X: Features DataFrame
            y: Target Series

        Returns:
            List of TrainingResults for each model
        """
        results = []

        for model_config in config.models:
            try:
                result = await self.train_model(
                    model_config=model_config,
                    target_config=config.target,
                    X=X,
                    y=y,
                    train_days=config.train_days,
                    test_days=config.test_days,
                    gap_days=config.gap_days,
                    n_permutations=config.mcpt_permutations,
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Failed to train {model_config.model_type.value}: {e}"
                )

        return results

    def _create_model(
        self,
        config: ModelConfig,
        target_config: TargetConfig,
    ) -> Any:
        """Create a model instance from config."""
        if config.model_type == ModelType.XGBOOST:
            import xgboost as xgb
            if target_config.target_type == TargetType.CLASSIFICATION:
                return xgb.XGBClassifier(**config.hyperparams)
            elif target_config.target_type == TargetType.MULTICLASS:
                params = {**config.hyperparams, "objective": "multi:softprob"}
                return xgb.XGBClassifier(**params)
            else:
                return xgb.XGBRegressor(**config.hyperparams)

        elif config.model_type == ModelType.LIGHTGBM:
            import lightgbm as lgb
            if target_config.target_type == TargetType.CLASSIFICATION:
                return lgb.LGBMClassifier(**config.hyperparams)
            elif target_config.target_type == TargetType.MULTICLASS:
                params = {**config.hyperparams, "objective": "multiclass"}
                return lgb.LGBMClassifier(**params)
            else:
                return lgb.LGBMRegressor(**config.hyperparams)

        elif config.model_type == ModelType.RANDOM_FOREST:
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
            if target_config.target_type in [TargetType.CLASSIFICATION, TargetType.MULTICLASS]:
                return RandomForestClassifier(**config.hyperparams)
            else:
                return RandomForestRegressor(**config.hyperparams)

        elif config.model_type == ModelType.GRADIENT_BOOSTING:
            from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
            if target_config.target_type in [TargetType.CLASSIFICATION, TargetType.MULTICLASS]:
                return GradientBoostingClassifier(**config.hyperparams)
            else:
                return GradientBoostingRegressor(**config.hyperparams)

        elif config.model_type == ModelType.ELASTIC_NET:
            from sklearn.linear_model import ElasticNet, LogisticRegression
            if target_config.target_type == TargetType.CLASSIFICATION:
                return LogisticRegression(
                    penalty="elasticnet",
                    solver="saga",
                    l1_ratio=config.hyperparams.get("l1_ratio", 0.5),
                    **{k: v for k, v in config.hyperparams.items() if k != "l1_ratio"}
                )
            else:
                return ElasticNet(**config.hyperparams)

        elif config.model_type == ModelType.RIDGE:
            from sklearn.linear_model import Ridge, RidgeClassifier
            if target_config.target_type == TargetType.CLASSIFICATION:
                return RidgeClassifier(**config.hyperparams)
            else:
                return Ridge(**config.hyperparams)

        elif config.model_type == ModelType.SVM:
            from sklearn.svm import SVC, SVR
            if target_config.target_type == TargetType.CLASSIFICATION:
                return SVC(**config.hyperparams)
            else:
                return SVR(**{k: v for k, v in config.hyperparams.items() if k != "probability"})

        else:
            raise ValueError(f"Unsupported model type: {config.model_type}")

    def _run_mcpt(
        self,
        predictions: np.ndarray,
        actuals: np.ndarray,
        n_permutations: int = 1000,
        target_type: TargetType = TargetType.CLASSIFICATION,
    ) -> MCPTResult:
        """
        Run Monte Carlo Permutation Test.

        Tests if the prediction skill is statistically significant.
        """
        # Compute observed metric
        if target_type == TargetType.CLASSIFICATION:
            # Use accuracy for classification
            observed = np.mean(np.round(predictions) == actuals)
            metric_name = "accuracy"
        else:
            # Use correlation for regression
            observed = np.corrcoef(predictions, actuals)[0, 1]
            if np.isnan(observed):
                observed = 0.0
            metric_name = "correlation"

        # Permutation test
        permuted_metrics = []
        for _ in range(n_permutations):
            # Shuffle actuals
            shuffled = np.random.permutation(actuals)
            if target_type == TargetType.CLASSIFICATION:
                perm_metric = np.mean(np.round(predictions) == shuffled)
            else:
                perm_metric = np.corrcoef(predictions, shuffled)[0, 1]
                if np.isnan(perm_metric):
                    perm_metric = 0.0
            permuted_metrics.append(perm_metric)

        # P-value: proportion of permutations >= observed
        p_value = np.mean([p >= observed for p in permuted_metrics])

        return MCPTResult(
            observed_metric=observed,
            permuted_metrics=permuted_metrics,
            p_value=p_value,
            n_permutations=n_permutations,
            metric_name=metric_name,
        )

    def _compute_r2(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Compute R-squared."""
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        if ss_tot == 0:
            return 0.0
        return 1 - (ss_res / ss_tot)

    def _get_feature_importance(
        self,
        model: Any,
        feature_columns: list[str],
    ) -> dict[str, float]:
        """Get feature importance from model."""
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "coef_"):
            importances = np.abs(model.coef_).flatten()
            if len(importances) != len(feature_columns):
                return {}
        else:
            return {}

        return dict(zip(feature_columns, importances))

    def _aggregate_feature_importance(
        self,
        cv_results: list[WalkForwardResult],
    ) -> dict[str, float]:
        """Aggregate feature importance across folds."""
        all_importances: dict[str, list[float]] = {}

        for result in cv_results:
            for feature, importance in result.feature_importance.items():
                if feature not in all_importances:
                    all_importances[feature] = []
                all_importances[feature].append(importance)

        # Average across folds
        return {
            feature: np.mean(importances)
            for feature, importances in all_importances.items()
        }


# =============================================================================
# TARGET CREATION FUNCTIONS
# =============================================================================


def create_target(
    df: pd.DataFrame,
    target_config: TargetConfig,
) -> pd.Series:
    """
    Create target variable from price data.

    Args:
        df: OHLCV DataFrame
        target_config: Target configuration

    Returns:
        Series with target values
    """
    close = df["close"]
    horizon = target_config.horizon

    # Forward returns
    forward_returns = close.shift(-horizon) / close - 1

    if target_config.target_type == TargetType.CLASSIFICATION:
        # Binary classification
        target = (forward_returns > target_config.threshold).astype(int)

    elif target_config.target_type == TargetType.MULTICLASS:
        # Multi-class (e.g., volatility regime)
        if target_config.name == "vol_regime":
            # Volatility regime classification
            vol = close.pct_change().rolling(20).std() * np.sqrt(252)
            vol_pct = vol.rolling(252).rank(pct=True)
            target = pd.cut(
                vol_pct,
                bins=[0, 0.25, 0.75, 1.0],
                labels=[0, 1, 2],  # Low, Normal, High
            ).astype(float)
        else:
            # Default to tercile classification
            target = pd.cut(
                forward_returns,
                bins=[-np.inf, -0.01, 0.01, np.inf],
                labels=[0, 1, 2],  # Down, Neutral, Up
            ).astype(float)

    else:  # Regression
        target = forward_returns

    return target.dropna()


def create_features_and_target(
    df: pd.DataFrame,
    feature_computer: Any,
    target_config: TargetConfig,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Create features and aligned target.

    Args:
        df: OHLCV DataFrame
        feature_computer: FeatureComputer instance
        target_config: Target configuration

    Returns:
        Tuple of (features DataFrame, target Series)
    """
    # Compute features
    features = feature_computer.compute_all_technical(df)

    # Create target
    target = create_target(df, target_config)

    # Align indices
    common_idx = features.index.intersection(target.index)
    features = features.loc[common_idx]
    target = target.loc[common_idx]

    # Drop rows with any NaN
    mask = features.notna().all(axis=1) & target.notna()
    features = features[mask]
    target = target[mask]

    return features, target
