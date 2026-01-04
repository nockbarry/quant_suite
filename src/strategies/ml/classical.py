"""Classical Machine Learning Strategies.

Implements tree-based and kernel-based ML strategies for trading:
- XGBoost (gradient boosted trees)
- Random Forest (bagged decision trees)
- Support Vector Machine (kernel-based classifier)

Based on "Advances in Financial Machine Learning" by de Prado.
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ...data.features import FeatureEngine
from ..base import MLStrategy


class PredictionTarget(str, Enum):
    """Target variable type for ML models."""

    BINARY = "binary"  # Up/down classification
    TERNARY = "ternary"  # Up/neutral/down
    REGRESSION = "regression"  # Continuous returns


class FeatureSet(str, Enum):
    """Predefined feature sets."""

    MINIMAL = "minimal"  # Returns + volatility only
    STANDARD = "standard"  # Standard technical indicators
    FULL = "full"  # All available features
    CUSTOM = "custom"  # User-defined features


@dataclass
class MLModelConfig:
    """Configuration for ML model training."""

    target: PredictionTarget = PredictionTarget.BINARY
    horizon: int = 5  # Prediction horizon in bars
    feature_set: FeatureSet = FeatureSet.STANDARD
    threshold: float = 0.0  # For ternary classification
    lookback: int = 252  # History required for features
    min_train_samples: int = 500  # Minimum training samples
    feature_columns: list[str] | None = None  # For custom features

    # Model hyperparameters (overridden by strategy)
    hyperparams: dict[str, Any] = field(default_factory=dict)


class ClassicalMLStrategy(MLStrategy, ABC):
    """
    Base class for classical ML strategies.

    Provides common functionality for tree-based and kernel-based models:
    - Feature preparation with configurable feature sets
    - Label generation with multiple target types
    - Model persistence (save/load)
    - Probability calibration
    """

    name: str = "classical_ml"
    description: str = "Classical ML trading strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: MLModelConfig | None = None,
        model: Any = None,
        scaler: Any = None,
        **params: Any,
    ):
        """
        Initialize classical ML strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            config: ML model configuration
            model: Pre-trained model (optional)
            scaler: Pre-fitted scaler (optional)
            **params: Additional parameters
        """
        super().__init__(universe, timeframe, model=model, **params)
        self.config = config or MLModelConfig()
        self.scaler = scaler
        self.feature_columns: list[str] = []
        self._feature_engine = FeatureEngine()

        # Probability threshold for signals
        self.signal_threshold = params.get("signal_threshold", 0.55)
        self.confidence_scaling = params.get("confidence_scaling", 2.0)

    def get_required_history(self) -> int:
        """Get required historical bars for feature computation."""
        return max(self.config.lookback, 252)

    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare features for ML model.

        Args:
            data: Raw OHLCV data

        Returns:
            DataFrame with computed features
        """
        if self.config.feature_set == FeatureSet.MINIMAL:
            features = self._prepare_minimal_features(data)
        elif self.config.feature_set == FeatureSet.STANDARD:
            features = self._prepare_standard_features(data)
        elif self.config.feature_set == FeatureSet.FULL:
            features = self._prepare_full_features(data)
        elif self.config.feature_set == FeatureSet.CUSTOM:
            if self.config.feature_columns:
                features = data[self.config.feature_columns].copy()
            else:
                raise ValueError("Custom feature set requires feature_columns")
        else:
            features = self._prepare_standard_features(data)

        # Store feature columns for inference
        if not self.feature_columns:
            self.feature_columns = list(features.columns)

        # Handle missing values
        features = features.ffill().bfill()

        # Scale features if scaler is fitted
        if self.scaler is not None:
            try:
                scaled_values = self.scaler.transform(features)
                features = pd.DataFrame(
                    scaled_values,
                    index=features.index,
                    columns=features.columns
                )
            except Exception:
                pass  # Use unscaled if transform fails

        return features

    def _prepare_minimal_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare minimal feature set (returns + volatility)."""
        df = data.copy()
        df = self._feature_engine.add_returns(df, periods=[1, 5, 10, 21])
        df = self._feature_engine.add_volatility(df, windows=[5, 10, 21])

        # Select only the feature columns
        feature_cols = [c for c in df.columns if any(
            c.startswith(p) for p in ["return_", "log_return", "volatility_", "parkinson"]
        )]

        return df[feature_cols]

    def _prepare_standard_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare standard feature set (technical indicators)."""
        df = data.copy()
        df = self._feature_engine.add_returns(df, periods=[1, 5, 10, 21])
        df = self._feature_engine.add_volatility(df, windows=[5, 10, 21])
        df = self._feature_engine.add_moving_averages(df, windows=[5, 10, 20, 50])
        df = self._feature_engine.add_momentum_indicators(df)
        df = self._feature_engine.add_volume_indicators(df)

        # Add relative features (price vs MAs)
        for ma in [5, 10, 20, 50]:
            if f"sma_{ma}" in df.columns:
                df[f"price_vs_sma_{ma}"] = df["close"] / df[f"sma_{ma}"] - 1

        # Exclude OHLCV columns
        exclude_cols = {"open", "high", "low", "close", "volume", "adj_close"}
        feature_cols = [c for c in df.columns if c.lower() not in exclude_cols]

        return df[feature_cols]

    def _prepare_full_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare full feature set (all available)."""
        df = self._feature_engine.add_all_features(data)

        # Exclude OHLCV columns
        exclude_cols = {"open", "high", "low", "close", "volume", "adj_close"}
        feature_cols = [c for c in df.columns if c.lower() not in exclude_cols]

        return df[feature_cols]

    def _prepare_labels(self, data: pd.DataFrame) -> pd.Series:
        """Prepare target labels for training."""
        return self._feature_engine.create_labels(
            data,
            horizon=self.config.horizon,
            method=self.config.target.value,
            threshold=self.config.threshold,
        )

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """
        Generate predictions from features.

        Args:
            features: Feature DataFrame

        Returns:
            Series with predictions (probabilities for classification)
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")

        # Ensure feature alignment
        if self.feature_columns:
            missing = set(self.feature_columns) - set(features.columns)
            if missing:
                for col in missing:
                    features[col] = 0
            features = features[self.feature_columns]

        # Handle NaN values
        features = features.ffill().bfill().fillna(0)

        # Get predictions
        if self.config.target == PredictionTarget.REGRESSION:
            predictions = self.model.predict(features)
        else:
            # Classification: get probability of positive class
            if hasattr(self.model, "predict_proba"):
                proba = self.model.predict_proba(features)
                if proba.shape[1] == 2:
                    predictions = proba[:, 1]  # Binary: P(up)
                else:
                    # Ternary: weighted prediction
                    predictions = (proba[:, 2] - proba[:, 0])  # P(up) - P(down)
            else:
                predictions = self.model.predict(features)

        return pd.Series(predictions, index=features.index)

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate trading signals from market data.

        Args:
            data: OHLCV data - single DataFrame or dict per symbol
            timestamp: Current timestamp

        Returns:
            List of trading signals
        """
        signals = []
        timestamp = timestamp or datetime.now()

        # Handle both single DataFrame and dict of DataFrames
        if isinstance(data, pd.DataFrame):
            data_dict = {self.universe[0]: data}
        else:
            data_dict = data

        for symbol, df in data_dict.items():
            if symbol not in self.universe:
                continue

            if not self.validate_data(df):
                continue

            try:
                # Prepare features and predict
                features = self.prepare_features(df)

                if len(features) == 0:
                    continue

                # Get latest prediction
                predictions = self.predict(features)
                latest_pred = predictions.iloc[-1]

                # Generate signal based on prediction
                signal = self._prediction_to_signal(
                    symbol, latest_pred, timestamp
                )
                if signal is not None:
                    signals.append(signal)

            except Exception as e:
                # Log error but continue with other symbols
                continue

        return signals

    def _prediction_to_signal(
        self,
        symbol: Symbol,
        prediction: float,
        timestamp: datetime,
    ) -> Signal | None:
        """Convert model prediction to trading signal."""

        if self.config.target == PredictionTarget.REGRESSION:
            # Regression: use predicted return directly
            if abs(prediction) < self.config.threshold:
                return None

            direction = Direction.LONG if prediction > 0 else Direction.SHORT
            strength = min(abs(prediction) * self.confidence_scaling, 1.0)
            confidence = min(abs(prediction) * 10, 1.0)  # Scale for confidence

        else:
            # Classification: use probability threshold
            if self.config.target == PredictionTarget.BINARY:
                # prediction is P(up)
                if prediction > self.signal_threshold:
                    direction = Direction.LONG
                    strength = (prediction - 0.5) * 2  # Scale to [-1, 1]
                    confidence = prediction
                elif prediction < (1 - self.signal_threshold):
                    direction = Direction.SHORT
                    strength = (0.5 - prediction) * 2
                    confidence = 1 - prediction
                else:
                    return None
            else:
                # Ternary: prediction is P(up) - P(down)
                if prediction > self.signal_threshold - 0.5:
                    direction = Direction.LONG
                    strength = min(prediction, 1.0)
                    confidence = (prediction + 1) / 2  # Scale to [0, 1]
                elif prediction < -(self.signal_threshold - 0.5):
                    direction = Direction.SHORT
                    strength = max(prediction, -1.0)
                    confidence = (-prediction + 1) / 2
                else:
                    return None

        signal_type = (
            SignalType.ENTRY_LONG if direction == Direction.LONG
            else SignalType.ENTRY_SHORT
        )

        return self.create_signal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            timestamp=timestamp,
            signal_type=signal_type,
            metadata={
                "model": self.name,
                "prediction": float(prediction),
                "target": self.config.target.value,
                "horizon": self.config.horizon,
            }
        )

    def _fit_scaler(self, features: pd.DataFrame) -> None:
        """Fit feature scaler."""
        try:
            from sklearn.preprocessing import RobustScaler
            self.scaler = RobustScaler()
            self.scaler.fit(features)
        except ImportError:
            self.scaler = None

    def save_model(self, path: str) -> None:
        """
        Save trained model and metadata.

        Args:
            path: Path to save model
        """
        if self.model is None:
            raise ValueError("No model to save")

        model_data = {
            "model": self.model,
            "scaler": self.scaler,
            "config": self.config,
            "feature_columns": self.feature_columns,
            "params": self.params,
            "name": self.name,
        }

        joblib.dump(model_data, path)

    def load_model(self, path: str) -> None:
        """
        Load trained model and metadata.

        Args:
            path: Path to load model from
        """
        model_data = joblib.load(path)

        self.model = model_data["model"]
        self.scaler = model_data.get("scaler")
        self.config = model_data.get("config", self.config)
        self.feature_columns = model_data.get("feature_columns", [])
        self.params = model_data.get("params", {})
        self._is_trained = True


class XGBoostStrategy(ClassicalMLStrategy):
    """
    XGBoost-based trading strategy.

    Gradient boosted trees are effective for financial prediction due to:
    - Handling of non-linear relationships
    - Robustness to outliers
    - Built-in feature importance
    - Regularization to prevent overfitting
    """

    name: str = "xgboost_strategy"
    description: str = "Trading strategy using XGBoost gradient boosted trees"

    DEFAULT_PARAMS = {
        "n_estimators": 100,
        "max_depth": 5,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,  # L1 regularization
        "reg_lambda": 1.0,  # L2 regularization
        "min_child_weight": 5,
        "gamma": 0.1,  # Min loss reduction for split
        "random_state": 42,
    }

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: MLModelConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        super().__init__(universe, timeframe, config=config, model=model, **params)

        # Merge default params with provided params
        self.model_params = {**self.DEFAULT_PARAMS}
        if self.config.hyperparams:
            self.model_params.update(self.config.hyperparams)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        sample_weights: pd.Series | None = None,
        validation_data: tuple[pd.DataFrame, pd.Series] | None = None,
        early_stopping_rounds: int = 20,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Train XGBoost model.

        Args:
            data: Training data (single DataFrame or dict per symbol)
            sample_weights: Optional sample weights
            validation_data: Optional (X_val, y_val) for early stopping
            early_stopping_rounds: Rounds for early stopping
            **kwargs: Additional training parameters

        Returns:
            Training metrics
        """
        try:
            import xgboost as xgb
        except ImportError:
            raise ImportError("XGBoost not installed. Run: pip install xgboost")

        # Combine data if multiple symbols
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            # Reset index to avoid duplicates
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Align features and labels
        valid_idx = features.index.intersection(labels.dropna().index)
        X = features.loc[valid_idx]
        y = labels.loc[valid_idx]

        if len(X) < self.config.min_train_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {self.config.min_train_samples}"
            )

        # Fit scaler
        self._fit_scaler(X)
        if self.scaler is not None:
            X_scaled = pd.DataFrame(
                self.scaler.transform(X),
                index=X.index,
                columns=X.columns
            )
        else:
            X_scaled = X

        # Prepare sample weights
        if sample_weights is not None:
            sw = sample_weights.loc[valid_idx].values
        else:
            sw = None

        # Create model
        if self.config.target == PredictionTarget.REGRESSION:
            self.model = xgb.XGBRegressor(**self.model_params)
        else:
            self.model_params["objective"] = (
                "binary:logistic" if self.config.target == PredictionTarget.BINARY
                else "multi:softprob"
            )
            if self.config.target == PredictionTarget.TERNARY:
                self.model_params["num_class"] = 3
            self.model = xgb.XGBClassifier(**self.model_params)

        # Train with optional early stopping
        fit_params = {"sample_weight": sw}

        if validation_data is not None:
            X_val, y_val = validation_data
            if self.scaler is not None:
                X_val = pd.DataFrame(
                    self.scaler.transform(X_val),
                    index=X_val.index,
                    columns=X_val.columns
                )
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["verbose"] = False

        self.model.fit(X_scaled, y, **fit_params)
        self._is_trained = True

        # Compute training metrics
        train_pred = self.model.predict(X_scaled)

        metrics = self._compute_training_metrics(y, train_pred)
        metrics["n_samples"] = len(X)
        metrics["n_features"] = len(self.feature_columns)

        # Feature importance
        if hasattr(self.model, "feature_importances_"):
            importance = pd.Series(
                self.model.feature_importances_,
                index=self.feature_columns
            ).sort_values(ascending=False)
            metrics["top_features"] = importance.head(10).to_dict()

        return metrics

    def _compute_training_metrics(
        self,
        y_true: pd.Series,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        """Compute training performance metrics."""
        metrics = {}

        if self.config.target == PredictionTarget.REGRESSION:
            # Regression metrics
            metrics["mse"] = float(np.mean((y_true - y_pred) ** 2))
            metrics["rmse"] = float(np.sqrt(metrics["mse"]))
            metrics["mae"] = float(np.mean(np.abs(y_true - y_pred)))

            # Direction accuracy
            direction_true = np.sign(y_true)
            direction_pred = np.sign(y_pred)
            metrics["direction_accuracy"] = float(
                np.mean(direction_true == direction_pred)
            )
        else:
            # Classification metrics
            if self.config.target == PredictionTarget.BINARY:
                pred_class = (y_pred > 0.5).astype(int)
            else:
                pred_class = y_pred

            metrics["accuracy"] = float(np.mean(y_true == pred_class))

            # Per-class metrics
            for cls in np.unique(y_true):
                mask = y_true == cls
                metrics[f"accuracy_class_{cls}"] = float(
                    np.mean(pred_class[mask] == cls)
                )

        return metrics

    def get_feature_importance(self) -> pd.Series:
        """Get feature importance from trained model."""
        if self.model is None:
            raise ValueError("Model not trained")

        if hasattr(self.model, "feature_importances_"):
            return pd.Series(
                self.model.feature_importances_,
                index=self.feature_columns
            ).sort_values(ascending=False)

        return pd.Series(dtype=float)


class RandomForestStrategy(ClassicalMLStrategy):
    """
    Random Forest-based trading strategy.

    Bagged decision trees offer:
    - Reduced variance through averaging
    - OOB (out-of-bag) error estimation
    - Robustness to overfitting
    - Parallel training
    """

    name: str = "random_forest_strategy"
    description: str = "Trading strategy using Random Forest ensemble"

    DEFAULT_PARAMS = {
        "n_estimators": 200,
        "max_depth": 8,
        "min_samples_split": 20,
        "min_samples_leaf": 10,
        "max_features": "sqrt",
        "bootstrap": True,
        "oob_score": True,
        "n_jobs": -1,
        "random_state": 42,
        "class_weight": "balanced",
    }

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: MLModelConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        super().__init__(universe, timeframe, config=config, model=model, **params)

        self.model_params = {**self.DEFAULT_PARAMS}
        if self.config.hyperparams:
            self.model_params.update(self.config.hyperparams)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        sample_weights: pd.Series | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Train Random Forest model.

        Args:
            data: Training data
            sample_weights: Optional sample weights
            **kwargs: Additional parameters

        Returns:
            Training metrics
        """
        try:
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        except ImportError:
            raise ImportError("scikit-learn not installed. Run: pip install scikit-learn")

        # Combine data if needed
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Align
        valid_idx = features.index.intersection(labels.dropna().index)
        X = features.loc[valid_idx]
        y = labels.loc[valid_idx]

        if len(X) < self.config.min_train_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {self.config.min_train_samples}"
            )

        # Fit scaler
        self._fit_scaler(X)
        if self.scaler is not None:
            X_scaled = pd.DataFrame(
                self.scaler.transform(X),
                index=X.index,
                columns=X.columns
            )
        else:
            X_scaled = X

        # Sample weights
        sw = sample_weights.loc[valid_idx].values if sample_weights is not None else None

        # Create model
        model_params = self.model_params.copy()
        if self.config.target == PredictionTarget.REGRESSION:
            # Remove classification-specific params
            model_params.pop("class_weight", None)
            self.model = RandomForestRegressor(**model_params)
        else:
            self.model = RandomForestClassifier(**model_params)

        # Train
        self.model.fit(X_scaled, y, sample_weight=sw)
        self._is_trained = True

        # Metrics
        train_pred = self.model.predict(X_scaled)
        metrics = self._compute_training_metrics(y, train_pred)
        metrics["n_samples"] = len(X)
        metrics["n_features"] = len(self.feature_columns)

        # OOB score
        if hasattr(self.model, "oob_score_"):
            metrics["oob_score"] = self.model.oob_score_

        # Feature importance
        if hasattr(self.model, "feature_importances_"):
            importance = pd.Series(
                self.model.feature_importances_,
                index=self.feature_columns
            ).sort_values(ascending=False)
            metrics["top_features"] = importance.head(10).to_dict()

        return metrics

    def _compute_training_metrics(
        self,
        y_true: pd.Series,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        """Compute training performance metrics."""
        metrics = {}

        if self.config.target == PredictionTarget.REGRESSION:
            metrics["mse"] = float(np.mean((y_true - y_pred) ** 2))
            metrics["rmse"] = float(np.sqrt(metrics["mse"]))
            metrics["mae"] = float(np.mean(np.abs(y_true - y_pred)))
            direction_true = np.sign(y_true)
            direction_pred = np.sign(y_pred)
            metrics["direction_accuracy"] = float(
                np.mean(direction_true == direction_pred)
            )
        else:
            metrics["accuracy"] = float(np.mean(y_true == y_pred))
            for cls in np.unique(y_true):
                mask = y_true == cls
                metrics[f"accuracy_class_{cls}"] = float(
                    np.mean(y_pred[mask] == cls)
                )

        return metrics

    def get_feature_importance(self) -> pd.Series:
        """Get feature importance from trained model."""
        if self.model is None:
            raise ValueError("Model not trained")

        return pd.Series(
            self.model.feature_importances_,
            index=self.feature_columns
        ).sort_values(ascending=False)


class SVMStrategy(ClassicalMLStrategy):
    """
    Support Vector Machine-based trading strategy.

    SVMs excel at:
    - Finding optimal decision boundaries
    - Working well with high-dimensional data
    - Kernel trick for non-linear patterns
    - Margin maximization for robustness
    """

    name: str = "svm_strategy"
    description: str = "Trading strategy using Support Vector Machine"

    DEFAULT_PARAMS = {
        "C": 1.0,
        "kernel": "rbf",
        "gamma": "scale",
        "probability": True,  # Enable probability estimates
        "class_weight": "balanced",
        "random_state": 42,
        "cache_size": 500,
        "max_iter": 5000,
    }

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: MLModelConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        super().__init__(universe, timeframe, config=config, model=model, **params)

        self.model_params = {**self.DEFAULT_PARAMS}
        if self.config.hyperparams:
            self.model_params.update(self.config.hyperparams)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        sample_weights: pd.Series | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Train SVM model.

        Args:
            data: Training data
            sample_weights: Optional sample weights
            **kwargs: Additional parameters

        Returns:
            Training metrics
        """
        try:
            from sklearn.svm import SVC, SVR
        except ImportError:
            raise ImportError("scikit-learn not installed. Run: pip install scikit-learn")

        # Combine data
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Align
        valid_idx = features.index.intersection(labels.dropna().index)
        X = features.loc[valid_idx]
        y = labels.loc[valid_idx]

        if len(X) < self.config.min_train_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {self.config.min_train_samples}"
            )

        # Feature scaling is critical for SVM
        self._fit_scaler(X)
        if self.scaler is not None:
            X_scaled = pd.DataFrame(
                self.scaler.transform(X),
                index=X.index,
                columns=X.columns
            )
        else:
            X_scaled = X

        # Sample weights
        sw = sample_weights.loc[valid_idx].values if sample_weights is not None else None

        # Create model
        model_params = self.model_params.copy()
        if self.config.target == PredictionTarget.REGRESSION:
            # SVR doesn't support class_weight
            model_params.pop("class_weight", None)
            model_params.pop("probability", None)
            self.model = SVR(**model_params)
        else:
            self.model = SVC(**model_params)

        # Train
        self.model.fit(X_scaled, y, sample_weight=sw)
        self._is_trained = True

        # Metrics
        train_pred = self.model.predict(X_scaled)
        metrics = self._compute_training_metrics(y, train_pred)
        metrics["n_samples"] = len(X)
        metrics["n_features"] = len(self.feature_columns)

        # Support vector info
        if hasattr(self.model, "n_support_"):
            metrics["n_support_vectors"] = int(sum(self.model.n_support_))

        return metrics

    def _compute_training_metrics(
        self,
        y_true: pd.Series,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        """Compute training performance metrics."""
        metrics = {}

        if self.config.target == PredictionTarget.REGRESSION:
            metrics["mse"] = float(np.mean((y_true - y_pred) ** 2))
            metrics["rmse"] = float(np.sqrt(metrics["mse"]))
            metrics["mae"] = float(np.mean(np.abs(y_true - y_pred)))
            direction_true = np.sign(y_true)
            direction_pred = np.sign(y_pred)
            metrics["direction_accuracy"] = float(
                np.mean(direction_true == direction_pred)
            )
        else:
            metrics["accuracy"] = float(np.mean(y_true == y_pred))
            for cls in np.unique(y_true):
                mask = y_true == cls
                metrics[f"accuracy_class_{cls}"] = float(
                    np.mean(y_pred[mask] == cls)
                )

        return metrics


class GradientBoostingStrategy(ClassicalMLStrategy):
    """
    Gradient Boosting (sklearn) strategy.

    Alternative to XGBoost using sklearn's implementation.
    Good for comparison and when XGBoost is not available.
    """

    name: str = "gradient_boosting_strategy"
    description: str = "Trading strategy using sklearn Gradient Boosting"

    DEFAULT_PARAMS = {
        "n_estimators": 100,
        "max_depth": 5,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "min_samples_split": 20,
        "min_samples_leaf": 10,
        "max_features": "sqrt",
        "random_state": 42,
    }

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: MLModelConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        super().__init__(universe, timeframe, config=config, model=model, **params)

        self.model_params = {**self.DEFAULT_PARAMS}
        if self.config.hyperparams:
            self.model_params.update(self.config.hyperparams)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        sample_weights: pd.Series | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Train Gradient Boosting model."""
        try:
            from sklearn.ensemble import (
                GradientBoostingClassifier,
                GradientBoostingRegressor,
            )
        except ImportError:
            raise ImportError("scikit-learn not installed. Run: pip install scikit-learn")

        # Combine data
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Align
        valid_idx = features.index.intersection(labels.dropna().index)
        X = features.loc[valid_idx]
        y = labels.loc[valid_idx]

        if len(X) < self.config.min_train_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {self.config.min_train_samples}"
            )

        # Fit scaler
        self._fit_scaler(X)
        if self.scaler is not None:
            X_scaled = pd.DataFrame(
                self.scaler.transform(X),
                index=X.index,
                columns=X.columns
            )
        else:
            X_scaled = X

        # Sample weights
        sw = sample_weights.loc[valid_idx].values if sample_weights is not None else None

        # Create model
        if self.config.target == PredictionTarget.REGRESSION:
            self.model = GradientBoostingRegressor(**self.model_params)
        else:
            self.model = GradientBoostingClassifier(**self.model_params)

        # Train
        self.model.fit(X_scaled, y, sample_weight=sw)
        self._is_trained = True

        # Metrics
        train_pred = self.model.predict(X_scaled)
        metrics = self._compute_training_metrics(y, train_pred)
        metrics["n_samples"] = len(X)
        metrics["n_features"] = len(self.feature_columns)

        # Feature importance
        if hasattr(self.model, "feature_importances_"):
            importance = pd.Series(
                self.model.feature_importances_,
                index=self.feature_columns
            ).sort_values(ascending=False)
            metrics["top_features"] = importance.head(10).to_dict()

        return metrics

    def _compute_training_metrics(
        self,
        y_true: pd.Series,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        """Compute training performance metrics."""
        metrics = {}

        if self.config.target == PredictionTarget.REGRESSION:
            metrics["mse"] = float(np.mean((y_true - y_pred) ** 2))
            metrics["rmse"] = float(np.sqrt(metrics["mse"]))
            metrics["mae"] = float(np.mean(np.abs(y_true - y_pred)))
            direction_true = np.sign(y_true)
            direction_pred = np.sign(y_pred)
            metrics["direction_accuracy"] = float(
                np.mean(direction_true == direction_pred)
            )
        else:
            metrics["accuracy"] = float(np.mean(y_true == y_pred))

        return metrics


# Convenience factory function
def create_ml_strategy(
    model_type: str,
    universe: list[Symbol],
    config: MLModelConfig | None = None,
    **params: Any,
) -> ClassicalMLStrategy:
    """
    Factory function to create ML strategies.

    Args:
        model_type: One of 'xgboost', 'random_forest', 'svm', 'gradient_boosting'
        universe: List of symbols
        config: Model configuration
        **params: Additional parameters

    Returns:
        Instantiated strategy
    """
    strategies = {
        "xgboost": XGBoostStrategy,
        "random_forest": RandomForestStrategy,
        "svm": SVMStrategy,
        "gradient_boosting": GradientBoostingStrategy,
    }

    if model_type not in strategies:
        raise ValueError(
            f"Unknown model type: {model_type}. "
            f"Available: {list(strategies.keys())}"
        )

    return strategies[model_type](universe, config=config, **params)
