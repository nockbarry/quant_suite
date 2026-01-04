"""Dataset loaders for ML models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Iterator

import numpy as np
import pandas as pd
from scipy import stats

from .features import FeatureEngine


class SampleWeightMethod(str, Enum):
    """Methods for computing sample weights."""

    UNIFORM = "uniform"
    TIME_DECAY = "time_decay"
    RETURN_ATTRIBUTION = "return_attribution"
    UNIQUENESS = "uniqueness"


@dataclass
class TimeSeriesDataset:
    """
    A time-series dataset for ML training and evaluation.

    Attributes:
        X: Feature matrix
        y: Target variable
        timestamps: DatetimeIndex for alignment
        feature_names: List of feature column names
        metadata: Additional dataset information
    """

    X: np.ndarray
    y: np.ndarray
    timestamps: pd.DatetimeIndex
    feature_names: list[str]
    metadata: dict[str, Any]

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        return self.X[idx], self.y[idx]

    def to_pandas(self) -> tuple[pd.DataFrame, pd.Series]:
        """Convert to pandas DataFrame and Series."""
        X_df = pd.DataFrame(self.X, index=self.timestamps, columns=self.feature_names)
        y_series = pd.Series(self.y, index=self.timestamps, name="target")
        return X_df, y_series

    def split(
        self,
        train_ratio: float = 0.8,
    ) -> tuple["TimeSeriesDataset", "TimeSeriesDataset"]:
        """
        Split dataset into train and test sets.

        Uses time-based split (no shuffling) to avoid lookahead bias.

        Args:
            train_ratio: Proportion of data for training

        Returns:
            Tuple of (train_dataset, test_dataset)
        """
        split_idx = int(len(self) * train_ratio)

        train = TimeSeriesDataset(
            X=self.X[:split_idx],
            y=self.y[:split_idx],
            timestamps=self.timestamps[:split_idx],
            feature_names=self.feature_names,
            metadata={**self.metadata, "split": "train"},
        )

        test = TimeSeriesDataset(
            X=self.X[split_idx:],
            y=self.y[split_idx:],
            timestamps=self.timestamps[split_idx:],
            feature_names=self.feature_names,
            metadata={**self.metadata, "split": "test"},
        )

        return train, test


class DatasetBuilder:
    """
    Builder for creating ML-ready datasets from OHLCV data.

    Handles feature engineering, label creation, and train/test splitting
    with proper handling of lookahead bias.
    """

    def __init__(
        self,
        feature_engine: FeatureEngine | None = None,
    ):
        """
        Initialize dataset builder.

        Args:
            feature_engine: Feature engineering instance
        """
        self.feature_engine = feature_engine or FeatureEngine()

    def build(
        self,
        df: pd.DataFrame,
        target_horizon: int = 5,
        target_method: str = "binary",
        target_threshold: float = 0.0,
        feature_columns: list[str] | None = None,
        add_features: bool = True,
        dropna: bool = True,
    ) -> TimeSeriesDataset:
        """
        Build a dataset from OHLCV data.

        Args:
            df: OHLCV DataFrame with DatetimeIndex
            target_horizon: Forward-looking period for labels
            target_method: Label method ('binary', 'ternary', 'regression')
            target_threshold: Threshold for ternary classification
            feature_columns: Specific columns to use (None = all numeric)
            add_features: Whether to add technical indicators
            dropna: Whether to drop rows with NaN values

        Returns:
            TimeSeriesDataset ready for ML
        """
        df = df.copy()

        # Add technical indicators
        if add_features:
            df = self.feature_engine.add_all_features(df)

        # Create labels
        y = self.feature_engine.create_labels(
            df,
            horizon=target_horizon,
            method=target_method,
            threshold=target_threshold,
        )

        # Select features
        if feature_columns:
            X_df = df[feature_columns]
        else:
            # Use all numeric columns except OHLCV
            exclude = ["open", "high", "low", "close", "volume"]
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            feature_cols = [c for c in numeric_cols if c not in exclude]
            X_df = df[feature_cols]

        # Combine and drop NaN
        combined = pd.concat([X_df, y.rename("target")], axis=1)
        if dropna:
            combined = combined.dropna()

        X_df = combined.drop("target", axis=1)
        y = combined["target"]

        return TimeSeriesDataset(
            X=X_df.values,
            y=y.values,
            timestamps=X_df.index,
            feature_names=list(X_df.columns),
            metadata={
                "target_horizon": target_horizon,
                "target_method": target_method,
                "num_features": len(X_df.columns),
                "date_range": (X_df.index.min(), X_df.index.max()),
            },
        )

    def build_sequence(
        self,
        df: pd.DataFrame,
        sequence_length: int = 60,
        target_horizon: int = 5,
        target_method: str = "binary",
        feature_columns: list[str] | None = None,
    ) -> TimeSeriesDataset:
        """
        Build a sequence dataset for RNN/LSTM models.

        Args:
            df: OHLCV DataFrame
            sequence_length: Number of time steps in each sequence
            target_horizon: Forward-looking period for labels
            target_method: Label method
            feature_columns: Specific columns to use

        Returns:
            TimeSeriesDataset with 3D X array (samples, timesteps, features)
        """
        df = df.copy()
        df = self.feature_engine.add_all_features(df)

        # Create labels
        y = self.feature_engine.create_labels(
            df,
            horizon=target_horizon,
            method=target_method,
        )

        # Select features
        if feature_columns:
            X_df = df[feature_columns]
        else:
            exclude = ["open", "high", "low", "close", "volume"]
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            feature_cols = [c for c in numeric_cols if c not in exclude]
            X_df = df[feature_cols]

        # Fill NaN in features (forward fill then backward fill)
        X_df = X_df.ffill().bfill()

        # Create sequences
        X_seq = []
        y_seq = []
        timestamps = []

        for i in range(sequence_length, len(X_df) - target_horizon):
            X_seq.append(X_df.iloc[i - sequence_length : i].values)
            y_seq.append(y.iloc[i])
            timestamps.append(X_df.index[i])

        return TimeSeriesDataset(
            X=np.array(X_seq),
            y=np.array(y_seq),
            timestamps=pd.DatetimeIndex(timestamps),
            feature_names=list(X_df.columns),
            metadata={
                "sequence_length": sequence_length,
                "target_horizon": target_horizon,
                "target_method": target_method,
                "shape": (len(X_seq), sequence_length, len(X_df.columns)),
            },
        )


class WalkForwardSplitter:
    """
    Walk-forward cross-validation splitter for time series.

    Generates train/test splits that respect temporal ordering
    and avoid lookahead bias.
    """

    def __init__(
        self,
        train_size: int = 252,
        test_size: int = 63,
        step_size: int = 21,
        min_train_size: int | None = None,
        expanding: bool = False,
    ):
        """
        Initialize walk-forward splitter.

        Args:
            train_size: Number of samples in training set
            test_size: Number of samples in test set
            step_size: Number of samples to step forward
            min_train_size: Minimum training size (for expanding window)
            expanding: If True, use expanding window; if False, rolling
        """
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size
        self.min_train_size = min_train_size or train_size
        self.expanding = expanding

    def split(
        self,
        dataset: TimeSeriesDataset,
    ) -> Iterator[tuple[TimeSeriesDataset, TimeSeriesDataset]]:
        """
        Generate train/test splits.

        Args:
            dataset: The dataset to split

        Yields:
            Tuple of (train_dataset, test_dataset)
        """
        n = len(dataset)
        start = 0 if self.expanding else 0

        while True:
            if self.expanding:
                train_start = 0
                train_end = self.min_train_size + start
            else:
                train_start = start
                train_end = start + self.train_size

            test_start = train_end
            test_end = test_start + self.test_size

            if test_end > n:
                break

            train = TimeSeriesDataset(
                X=dataset.X[train_start:train_end],
                y=dataset.y[train_start:train_end],
                timestamps=dataset.timestamps[train_start:train_end],
                feature_names=dataset.feature_names,
                metadata={**dataset.metadata, "fold_type": "train"},
            )

            test = TimeSeriesDataset(
                X=dataset.X[test_start:test_end],
                y=dataset.y[test_start:test_end],
                timestamps=dataset.timestamps[test_start:test_end],
                feature_names=dataset.feature_names,
                metadata={**dataset.metadata, "fold_type": "test"},
            )

            yield train, test

            start += self.step_size

    def get_n_splits(self, n_samples: int) -> int:
        """Get the number of splits."""
        if self.expanding:
            available = n_samples - self.min_train_size - self.test_size
        else:
            available = n_samples - self.train_size - self.test_size

        if available < 0:
            return 0

        return available // self.step_size + 1


class PurgedKFold:
    """
    Purged K-Fold cross-validation for time series.

    Implements the Combinatorial Purged Cross-Validation (CPCV)
    approach from "Advances in Financial Machine Learning".
    """

    def __init__(
        self,
        n_splits: int = 5,
        embargo_pct: float = 0.01,
        purge_pct: float = 0.01,
    ):
        """
        Initialize purged K-fold splitter.

        Args:
            n_splits: Number of folds
            embargo_pct: Percentage of data to embargo after test set
            purge_pct: Percentage of data to purge before test set
        """
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.purge_pct = purge_pct

    def split(
        self,
        dataset: TimeSeriesDataset,
    ) -> Iterator[tuple[TimeSeriesDataset, TimeSeriesDataset]]:
        """
        Generate purged train/test splits.

        Args:
            dataset: The dataset to split

        Yields:
            Tuple of (train_dataset, test_dataset)
        """
        n = len(dataset)
        fold_size = n // self.n_splits
        embargo_size = int(n * self.embargo_pct)
        purge_size = int(n * self.purge_pct)

        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_splits - 1 else n

            # Training indices: all except test set, with purge and embargo
            train_indices = []

            # Before test set (with purge)
            if test_start - purge_size > 0:
                train_indices.extend(range(0, test_start - purge_size))

            # After test set (with embargo)
            if test_end + embargo_size < n:
                train_indices.extend(range(test_end + embargo_size, n))

            if not train_indices:
                continue

            train_indices = np.array(train_indices)
            test_indices = np.arange(test_start, test_end)

            train = TimeSeriesDataset(
                X=dataset.X[train_indices],
                y=dataset.y[train_indices],
                timestamps=dataset.timestamps[train_indices],
                feature_names=dataset.feature_names,
                metadata={**dataset.metadata, "fold": i, "fold_type": "train"},
            )

            test = TimeSeriesDataset(
                X=dataset.X[test_indices],
                y=dataset.y[test_indices],
                timestamps=dataset.timestamps[test_indices],
                feature_names=dataset.feature_names,
                metadata={**dataset.metadata, "fold": i, "fold_type": "test"},
            )

            yield train, test


class SampleWeighter:
    """
    Compute sample weights for ML training.

    Implements various weighting schemes from "Advances in Financial Machine Learning".
    """

    @staticmethod
    def uniform(n_samples: int) -> np.ndarray:
        """Uniform weights (all samples equal)."""
        return np.ones(n_samples) / n_samples

    @staticmethod
    def time_decay(
        timestamps: pd.DatetimeIndex,
        halflife_days: int = 252,
    ) -> np.ndarray:
        """
        Exponential time decay weights (recent samples weighted higher).

        Args:
            timestamps: Sample timestamps
            halflife_days: Half-life for decay

        Returns:
            Normalized weights array
        """
        # Days from most recent
        days_ago = (timestamps.max() - timestamps).days.values.astype(float)

        # Exponential decay
        decay_rate = np.log(2) / halflife_days
        weights = np.exp(-decay_rate * days_ago)

        return weights / weights.sum()

    @staticmethod
    def return_attribution(
        returns: np.ndarray,
        labels: np.ndarray,
    ) -> np.ndarray:
        """
        Weight samples by absolute return magnitude.

        Samples with larger price moves are more informative.

        Args:
            returns: Return values
            labels: Target labels

        Returns:
            Normalized weights array
        """
        abs_returns = np.abs(returns)
        weights = abs_returns / abs_returns.sum()
        return weights

    @staticmethod
    def uniqueness(
        timestamps: pd.DatetimeIndex,
        concurrent_labels: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Weight samples by uniqueness (inverse of concurrent labels).

        Reduces weight when multiple labels overlap in time.

        Args:
            timestamps: Sample timestamps
            concurrent_labels: Number of concurrent labels per sample

        Returns:
            Normalized weights array
        """
        if concurrent_labels is None:
            # Simple approximation: assume no overlap
            return np.ones(len(timestamps)) / len(timestamps)

        # Weight inversely proportional to concurrency
        weights = 1.0 / np.maximum(concurrent_labels, 1)
        return weights / weights.sum()

    @classmethod
    def compute_weights(
        cls,
        dataset: "TimeSeriesDataset",
        method: SampleWeightMethod = SampleWeightMethod.TIME_DECAY,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Compute sample weights for a dataset.

        Args:
            dataset: TimeSeriesDataset to weight
            method: Weighting method
            **kwargs: Method-specific parameters

        Returns:
            Sample weights array
        """
        if method == SampleWeightMethod.UNIFORM:
            return cls.uniform(len(dataset))
        elif method == SampleWeightMethod.TIME_DECAY:
            halflife = kwargs.get("halflife_days", 252)
            return cls.time_decay(dataset.timestamps, halflife)
        elif method == SampleWeightMethod.RETURN_ATTRIBUTION:
            # Need returns from metadata or compute from y
            returns = kwargs.get("returns", dataset.y)
            return cls.return_attribution(returns, dataset.y)
        elif method == SampleWeightMethod.UNIQUENESS:
            concurrent = kwargs.get("concurrent_labels")
            return cls.uniqueness(dataset.timestamps, concurrent)
        else:
            return cls.uniform(len(dataset))


class FeatureSelector:
    """
    Feature selection utilities for ML models.

    Implements various feature selection methods appropriate for
    financial time series.
    """

    @staticmethod
    def correlation_filter(
        X: np.ndarray,
        feature_names: list[str],
        threshold: float = 0.95,
    ) -> tuple[np.ndarray, list[str]]:
        """
        Remove highly correlated features.

        Args:
            X: Feature matrix
            feature_names: Feature column names
            threshold: Correlation threshold for removal

        Returns:
            Filtered X and remaining feature names
        """
        df = pd.DataFrame(X, columns=feature_names)
        corr_matrix = df.corr().abs()

        # Upper triangle mask
        upper = corr_matrix.where(
            np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        )

        # Find features to drop
        to_drop = [col for col in upper.columns if any(upper[col] > threshold)]

        remaining = [f for f in feature_names if f not in to_drop]
        return df[remaining].values, remaining

    @staticmethod
    def variance_filter(
        X: np.ndarray,
        feature_names: list[str],
        threshold: float = 0.01,
    ) -> tuple[np.ndarray, list[str]]:
        """
        Remove low variance features.

        Args:
            X: Feature matrix
            feature_names: Feature column names
            threshold: Minimum variance threshold

        Returns:
            Filtered X and remaining feature names
        """
        variances = np.var(X, axis=0)
        mask = variances > threshold

        remaining = [f for i, f in enumerate(feature_names) if mask[i]]
        return X[:, mask], remaining

    @staticmethod
    def mutual_information(
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str],
        n_features: int = 20,
        discrete_target: bool = True,
    ) -> tuple[np.ndarray, list[str], np.ndarray]:
        """
        Select features by mutual information with target.

        Args:
            X: Feature matrix
            y: Target variable
            feature_names: Feature column names
            n_features: Number of features to select
            discrete_target: Whether target is discrete (classification)

        Returns:
            Selected X, feature names, and MI scores
        """
        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

        if discrete_target:
            mi_scores = mutual_info_classif(X, y, random_state=42)
        else:
            mi_scores = mutual_info_regression(X, y, random_state=42)

        # Select top features
        top_indices = np.argsort(mi_scores)[-n_features:][::-1]

        selected_names = [feature_names[i] for i in top_indices]
        return X[:, top_indices], selected_names, mi_scores[top_indices]

    @staticmethod
    def importance_filter(
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str],
        n_features: int = 20,
        method: str = "random_forest",
    ) -> tuple[np.ndarray, list[str], np.ndarray]:
        """
        Select features by model-based importance.

        Args:
            X: Feature matrix
            y: Target variable
            feature_names: Feature column names
            n_features: Number of features to select
            method: Model type ('random_forest' or 'gradient_boosting')

        Returns:
            Selected X, feature names, and importance scores
        """
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

        if method == "random_forest":
            model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        else:
            model = GradientBoostingClassifier(n_estimators=100, random_state=42)

        model.fit(X, y)
        importances = model.feature_importances_

        top_indices = np.argsort(importances)[-n_features:][::-1]
        selected_names = [feature_names[i] for i in top_indices]

        return X[:, top_indices], selected_names, importances[top_indices]


class FeatureScaler:
    """
    Feature scaling utilities with fit/transform pattern.

    Designed for time series to avoid lookahead bias.
    """

    def __init__(self, method: str = "robust"):
        """
        Initialize scaler.

        Args:
            method: Scaling method ('standard', 'robust', 'minmax', 'rank')
        """
        self.method = method
        self._params: dict[str, Any] = {}
        self._is_fitted = False

    def fit(self, X: np.ndarray) -> "FeatureScaler":
        """
        Fit scaler parameters from training data.

        Args:
            X: Training feature matrix

        Returns:
            self
        """
        if self.method == "standard":
            self._params["mean"] = np.nanmean(X, axis=0)
            self._params["std"] = np.nanstd(X, axis=0)
            self._params["std"] = np.where(self._params["std"] == 0, 1, self._params["std"])

        elif self.method == "robust":
            self._params["median"] = np.nanmedian(X, axis=0)
            q75 = np.nanpercentile(X, 75, axis=0)
            q25 = np.nanpercentile(X, 25, axis=0)
            self._params["iqr"] = q75 - q25
            self._params["iqr"] = np.where(self._params["iqr"] == 0, 1, self._params["iqr"])

        elif self.method == "minmax":
            self._params["min"] = np.nanmin(X, axis=0)
            self._params["max"] = np.nanmax(X, axis=0)
            self._params["range"] = self._params["max"] - self._params["min"]
            self._params["range"] = np.where(self._params["range"] == 0, 1, self._params["range"])

        elif self.method == "rank":
            # Store reference distribution for rank transform
            self._params["reference"] = X.copy()

        self._is_fitted = True
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        """
        Transform features using fitted parameters.

        Args:
            X: Feature matrix to transform

        Returns:
            Transformed features
        """
        if not self._is_fitted:
            raise ValueError("Scaler not fitted. Call fit() first.")

        if self.method == "standard":
            return (X - self._params["mean"]) / self._params["std"]

        elif self.method == "robust":
            return (X - self._params["median"]) / self._params["iqr"]

        elif self.method == "minmax":
            return (X - self._params["min"]) / self._params["range"]

        elif self.method == "rank":
            # Rank transform each feature
            result = np.zeros_like(X)
            for i in range(X.shape[1]):
                ref = self._params["reference"][:, i]
                for j in range(X.shape[0]):
                    result[j, i] = stats.percentileofscore(ref, X[j, i]) / 100
            return result

        return X

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        """Fit and transform in one step."""
        return self.fit(X).transform(X)

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        """
        Inverse transform (if applicable).

        Args:
            X: Transformed features

        Returns:
            Original scale features
        """
        if not self._is_fitted:
            raise ValueError("Scaler not fitted.")

        if self.method == "standard":
            return X * self._params["std"] + self._params["mean"]

        elif self.method == "robust":
            return X * self._params["iqr"] + self._params["median"]

        elif self.method == "minmax":
            return X * self._params["range"] + self._params["min"]

        else:
            raise ValueError(f"Inverse transform not supported for {self.method}")


class PyTorchDataset:
    """
    PyTorch-compatible dataset wrapper.

    Wraps TimeSeriesDataset for use with PyTorch DataLoader.
    """

    def __init__(
        self,
        dataset: TimeSeriesDataset,
        sample_weights: np.ndarray | None = None,
    ):
        """
        Initialize PyTorch dataset.

        Args:
            dataset: TimeSeriesDataset to wrap
            sample_weights: Optional sample weights
        """
        self.dataset = dataset
        self.sample_weights = sample_weights

        # Convert to float32 for PyTorch
        self.X = dataset.X.astype(np.float32)
        self.y = dataset.y.astype(np.float32)

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        if self.sample_weights is not None:
            return self.X[idx], self.y[idx], self.sample_weights[idx]
        return self.X[idx], self.y[idx]


class SequenceDataset:
    """
    Sequence dataset for RNN/LSTM/Transformer models.

    Creates sliding window sequences from time series data.
    """

    def __init__(
        self,
        dataset: TimeSeriesDataset,
        sequence_length: int = 60,
        target_offset: int = 1,
        stride: int = 1,
    ):
        """
        Initialize sequence dataset.

        Args:
            dataset: TimeSeriesDataset to wrap
            sequence_length: Number of timesteps in each sequence
            target_offset: Offset from end of sequence to target
            stride: Step size between sequences
        """
        self.dataset = dataset
        self.sequence_length = sequence_length
        self.target_offset = target_offset
        self.stride = stride

        # Pre-compute valid indices
        self.valid_indices = list(range(
            sequence_length,
            len(dataset) - target_offset + 1,
            stride
        ))

        # Convert to float32
        self.X = dataset.X.astype(np.float32)
        self.y = dataset.y.astype(np.float32)

    def __len__(self) -> int:
        return len(self.valid_indices)

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        end_idx = self.valid_indices[idx]
        start_idx = end_idx - self.sequence_length

        X_seq = self.X[start_idx:end_idx]
        y_target = self.y[end_idx - 1 + self.target_offset]

        return X_seq, y_target

    def get_timestamps(self, idx: int) -> pd.Timestamp:
        """Get timestamp for a sequence."""
        end_idx = self.valid_indices[idx]
        return self.dataset.timestamps[end_idx - 1]


def compute_triple_barrier_labels(
    prices: pd.Series,
    horizon: int = 10,
    upper_barrier: float = 0.02,
    lower_barrier: float = -0.02,
    vertical_barrier: bool = True,
) -> pd.Series:
    """
    Compute triple-barrier labels (from AFML).

    Labels are:
    - 1: Upper barrier hit first (profit target)
    - -1: Lower barrier hit first (stop loss)
    - 0: Vertical barrier (time expiry, no barrier hit)

    Args:
        prices: Price series
        horizon: Maximum holding period (vertical barrier)
        upper_barrier: Upper barrier as return threshold
        lower_barrier: Lower barrier as return threshold
        vertical_barrier: Whether to use vertical barrier

    Returns:
        Series of labels
    """
    labels = pd.Series(index=prices.index, dtype=float)

    for i in range(len(prices) - horizon):
        entry_price = prices.iloc[i]
        future_prices = prices.iloc[i + 1:i + horizon + 1]
        future_returns = (future_prices - entry_price) / entry_price

        # Check which barrier is hit first
        upper_hit = future_returns >= upper_barrier
        lower_hit = future_returns <= lower_barrier

        if upper_hit.any() and lower_hit.any():
            # Both barriers hit - which was first?
            upper_idx = upper_hit.idxmax()
            lower_idx = lower_hit.idxmax()
            if upper_idx < lower_idx:
                labels.iloc[i] = 1
            else:
                labels.iloc[i] = -1
        elif upper_hit.any():
            labels.iloc[i] = 1
        elif lower_hit.any():
            labels.iloc[i] = -1
        elif vertical_barrier:
            # End of horizon - use final return
            final_return = future_returns.iloc[-1] if len(future_returns) > 0 else 0
            labels.iloc[i] = 1 if final_return > 0 else -1 if final_return < 0 else 0
        else:
            labels.iloc[i] = 0

    return labels


def compute_meta_labels(
    primary_model_predictions: np.ndarray,
    actual_returns: np.ndarray,
    threshold: float = 0.0,
) -> np.ndarray:
    """
    Compute meta-labels for bet sizing.

    Meta-labels indicate whether to take a trade based on primary model signal.
    1 = take the trade (primary model was correct)
    0 = skip the trade (primary model was wrong)

    Args:
        primary_model_predictions: Primary model direction predictions
        actual_returns: Actual future returns
        threshold: Return threshold for "correct" prediction

    Returns:
        Meta-label array
    """
    # Determine if primary model was correct
    predicted_direction = np.sign(primary_model_predictions)
    actual_direction = np.sign(actual_returns)

    # Meta-label: 1 if prediction direction matches actual
    meta_labels = (predicted_direction == actual_direction).astype(int)

    # Additionally filter by return magnitude
    significant_moves = np.abs(actual_returns) > threshold
    meta_labels = meta_labels * significant_moves

    return meta_labels
