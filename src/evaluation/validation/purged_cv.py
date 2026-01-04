"""Combinatorial Purged Cross-Validation (CPCV).

Implements proper cross-validation for financial time series following
"Advances in Financial Machine Learning" by Marcos Lopez de Prado.

Key concepts:
1. Purging: Remove training samples whose labels overlap with test periods
2. Embargo: Create gap after test set to prevent information leakage
3. Combinatorial: Test all n_splits choose k combinations for better statistics

The problem with standard k-fold CV in finance:
- Labels overlap (e.g., 5-day forward returns)
- Serial correlation in features
- Information leakage between train/test sets
"""

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Iterator

import numpy as np
import pandas as pd


@dataclass
class CVFold:
    """Represents a single cross-validation fold."""

    fold_id: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_timestamps: pd.DatetimeIndex | None = None
    test_timestamps: pd.DatetimeIndex | None = None

    @property
    def n_train(self) -> int:
        return len(self.train_indices)

    @property
    def n_test(self) -> int:
        return len(self.test_indices)


@dataclass
class CVResult:
    """Results from cross-validation."""

    folds: list[CVFold]
    n_paths: int  # Number of backtest paths
    n_train_avg: float
    n_test_avg: float

    # Metrics per fold
    train_metrics: list[dict[str, float]] = field(default_factory=list)
    test_metrics: list[dict[str, float]] = field(default_factory=list)

    # Aggregated predictions
    predictions: pd.Series | None = None

    def summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        summary = {
            "n_folds": len(self.folds),
            "n_paths": self.n_paths,
            "avg_train_size": self.n_train_avg,
            "avg_test_size": self.n_test_avg,
        }

        if self.test_metrics:
            # Aggregate test metrics
            for metric in self.test_metrics[0].keys():
                values = [m[metric] for m in self.test_metrics if metric in m]
                if values:
                    summary[f"{metric}_mean"] = np.mean(values)
                    summary[f"{metric}_std"] = np.std(values)

        return summary


class PurgedKFoldCV:
    """
    Purged K-Fold Cross-Validation.

    Implements purging and embargo to prevent information leakage
    in time series cross-validation.

    Purging removes training samples whose labels overlap with test periods.
    Embargo adds a gap after test periods to account for serial correlation.
    """

    def __init__(
        self,
        n_splits: int = 5,
        embargo_pct: float = 0.01,
        purge_overlap: bool = True,
    ):
        """
        Initialize purged K-fold CV.

        Args:
            n_splits: Number of folds
            embargo_pct: Fraction of data to embargo after test
            purge_overlap: Whether to purge overlapping labels
        """
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.purge_overlap = purge_overlap

    def split(
        self,
        X: pd.DataFrame,
        y: pd.Series | None = None,
        label_end_times: pd.Series | None = None,
    ) -> Iterator[CVFold]:
        """
        Generate train/test splits with purging and embargo.

        Args:
            X: Features DataFrame with DatetimeIndex
            y: Labels (optional)
            label_end_times: End time for each label (for purging overlapping labels)

        Yields:
            CVFold objects with train/test indices
        """
        n = len(X)
        indices = np.arange(n)
        timestamps = X.index if isinstance(X.index, pd.DatetimeIndex) else None

        # Calculate sizes
        fold_size = n // self.n_splits
        embargo_size = max(1, int(n * self.embargo_pct))

        for fold_idx in range(self.n_splits):
            # Define test set
            test_start = fold_idx * fold_size
            test_end = (fold_idx + 1) * fold_size if fold_idx < self.n_splits - 1 else n
            test_indices = indices[test_start:test_end]

            # Get test timestamps for purging
            if timestamps is not None:
                test_timestamps = timestamps[test_start:test_end]
                test_start_time = test_timestamps.min()
                test_end_time = test_timestamps.max()
            else:
                test_timestamps = None
                test_start_time = test_start
                test_end_time = test_end

            # Build training set with purging and embargo
            train_indices = []

            for i in indices:
                # Skip if in test set
                if test_start <= i < test_end:
                    continue

                # Apply embargo after test set
                if i >= test_end and i < test_end + embargo_size:
                    continue

                # Apply purging for overlapping labels
                if self.purge_overlap and label_end_times is not None:
                    label_end = label_end_times.iloc[i]
                    # Skip if label overlaps with test period
                    if timestamps is not None:
                        if timestamps[i] < test_end_time and label_end > test_start_time:
                            continue
                    else:
                        if i < test_end and label_end > test_start:
                            continue

                train_indices.append(i)

            train_indices = np.array(train_indices)
            train_timestamps = timestamps[train_indices] if timestamps is not None else None

            yield CVFold(
                fold_id=fold_idx,
                train_indices=train_indices,
                test_indices=test_indices,
                train_timestamps=train_timestamps,
                test_timestamps=test_timestamps,
            )

    def get_n_splits(self) -> int:
        """Get number of splits."""
        return self.n_splits


class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation (CPCV).

    From AFML: Instead of using each group once as test set,
    use all combinations of groups for testing. This provides
    more backtest paths and better statistical estimates.

    For n groups with k groups used for testing:
    - Number of paths = C(n, k) = n! / (k! * (n-k)!)
    - Each observation appears in same number of test/train sets
    """

    def __init__(
        self,
        n_splits: int = 5,
        n_test_groups: int = 2,
        embargo_pct: float = 0.01,
        purge_overlap: bool = True,
    ):
        """
        Initialize combinatorial purged CV.

        Args:
            n_splits: Number of groups to split data into
            n_test_groups: Number of groups to use for testing
            embargo_pct: Fraction to embargo after test groups
            purge_overlap: Whether to purge overlapping labels
        """
        self.n_splits = n_splits
        self.n_test_groups = n_test_groups
        self.embargo_pct = embargo_pct
        self.purge_overlap = purge_overlap

        # Calculate number of paths
        self._n_paths = self._comb(n_splits, n_test_groups)

    def _comb(self, n: int, k: int) -> int:
        """Calculate combination C(n, k)."""
        from math import factorial
        return factorial(n) // (factorial(k) * factorial(n - k))

    @property
    def n_paths(self) -> int:
        """Number of backtest paths."""
        return self._n_paths

    def split(
        self,
        X: pd.DataFrame,
        y: pd.Series | None = None,
        label_end_times: pd.Series | None = None,
    ) -> Iterator[CVFold]:
        """
        Generate all combinatorial train/test splits.

        Args:
            X: Features DataFrame with DatetimeIndex
            y: Labels (optional)
            label_end_times: End time for each label

        Yields:
            CVFold objects for each combination
        """
        n = len(X)
        indices = np.arange(n)
        timestamps = X.index if isinstance(X.index, pd.DatetimeIndex) else None

        # Split data into groups
        group_size = n // self.n_splits
        groups = []
        for i in range(self.n_splits):
            start = i * group_size
            end = (i + 1) * group_size if i < self.n_splits - 1 else n
            groups.append(indices[start:end])

        embargo_size = max(1, int(n * self.embargo_pct))

        # Generate all combinations of test groups
        fold_id = 0
        for test_group_indices in combinations(range(self.n_splits), self.n_test_groups):
            # Combine test groups
            test_indices = np.concatenate([groups[i] for i in test_group_indices])

            if timestamps is not None:
                test_timestamps = timestamps[test_indices]
                test_start_time = test_timestamps.min()
                test_end_time = test_timestamps.max()
            else:
                test_timestamps = None
                test_start_time = test_indices.min()
                test_end_time = test_indices.max()

            # Build training set
            train_groups = [i for i in range(self.n_splits) if i not in test_group_indices]
            train_indices_raw = np.concatenate([groups[i] for i in train_groups])

            # Apply purging and embargo
            train_indices = []
            for i in train_indices_raw:
                # Apply embargo: skip indices right after test groups
                is_embargoed = False
                for test_group_idx in test_group_indices:
                    test_group_end = groups[test_group_idx][-1]
                    if i > test_group_end and i <= test_group_end + embargo_size:
                        is_embargoed = True
                        break
                if is_embargoed:
                    continue

                # Apply purging
                if self.purge_overlap and label_end_times is not None:
                    label_end = label_end_times.iloc[i]
                    if timestamps is not None:
                        if timestamps[i] < test_end_time and label_end > test_start_time:
                            continue
                    else:
                        if i < test_end_time and label_end > test_start_time:
                            continue

                train_indices.append(i)

            train_indices = np.array(train_indices)
            train_timestamps = timestamps[train_indices] if timestamps is not None else None

            yield CVFold(
                fold_id=fold_id,
                train_indices=train_indices,
                test_indices=test_indices,
                train_timestamps=train_timestamps,
                test_timestamps=test_timestamps,
            )
            fold_id += 1

    def get_n_splits(self) -> int:
        """Get total number of combinatorial splits."""
        return self._n_paths


class TimeSeriesCV:
    """
    Time Series Cross-Validation with expanding/rolling windows.

    Respects temporal order: train always before test.
    """

    def __init__(
        self,
        n_splits: int = 5,
        gap: int = 0,
        expanding: bool = True,
        min_train_size: int | None = None,
    ):
        """
        Initialize time series CV.

        Args:
            n_splits: Number of splits
            gap: Gap between train and test (for embargo)
            expanding: If True, use expanding window; if False, use rolling
            min_train_size: Minimum training size (for rolling)
        """
        self.n_splits = n_splits
        self.gap = gap
        self.expanding = expanding
        self.min_train_size = min_train_size

    def split(
        self,
        X: pd.DataFrame,
        y: pd.Series | None = None,
        label_end_times: pd.Series | None = None,
    ) -> Iterator[CVFold]:
        """
        Generate time series train/test splits.

        Args:
            X: Features DataFrame
            y: Labels (optional)
            label_end_times: Label end times (optional)

        Yields:
            CVFold objects
        """
        n = len(X)
        indices = np.arange(n)
        timestamps = X.index if isinstance(X.index, pd.DatetimeIndex) else None

        # Calculate test fold size
        test_size = n // (self.n_splits + 1)
        if self.min_train_size is None:
            self.min_train_size = test_size

        for fold_idx in range(self.n_splits):
            # Test set position
            test_start = self.min_train_size + fold_idx * test_size + self.gap
            test_end = test_start + test_size

            if test_end > n:
                break

            test_indices = indices[test_start:test_end]

            # Training set
            if self.expanding:
                # Expanding window: all data before gap
                train_end = test_start - self.gap
                train_indices = indices[:train_end]
            else:
                # Rolling window: fixed size before gap
                train_end = test_start - self.gap
                train_start = max(0, train_end - self.min_train_size - fold_idx * test_size)
                train_indices = indices[train_start:train_end]

            train_timestamps = timestamps[train_indices] if timestamps is not None else None
            test_timestamps = timestamps[test_indices] if timestamps is not None else None

            yield CVFold(
                fold_id=fold_idx,
                train_indices=train_indices,
                test_indices=test_indices,
                train_timestamps=train_timestamps,
                test_timestamps=test_timestamps,
            )

    def get_n_splits(self) -> int:
        """Get number of splits."""
        return self.n_splits


def compute_label_end_times(
    timestamps: pd.DatetimeIndex,
    horizon: int,
) -> pd.Series:
    """
    Compute end times for labels with given horizon.

    Args:
        timestamps: Sample timestamps
        horizon: Label horizon (forward-looking period)

    Returns:
        Series mapping each timestamp to its label end time
    """
    end_times = timestamps.to_series().shift(-horizon)
    # Fill NaN at the end with max timestamp
    end_times = end_times.fillna(timestamps.max())
    return end_times


def get_train_times(
    samples: pd.DatetimeIndex,
    test_times: pd.DataFrame,
    label_end_times: pd.Series,
) -> pd.DatetimeIndex:
    """
    Get training sample times that don't overlap with test set.

    From AFML Chapter 7.

    Args:
        samples: All sample timestamps
        test_times: DataFrame with 't1' (start) and 't2' (end) of test period
        label_end_times: End time for each label

    Returns:
        Training sample timestamps
    """
    train_times = []

    for idx, row in test_times.iterrows():
        test_start = row["t1"]
        test_end = row["t2"]

        for sample_time in samples:
            label_end = label_end_times[sample_time]

            # Sample is valid for training if:
            # - Its label ends before test starts, OR
            # - Sample starts after test ends
            if label_end <= test_start or sample_time >= test_end:
                if sample_time not in train_times:
                    train_times.append(sample_time)

    return pd.DatetimeIndex(sorted(train_times))


def get_embargo_times(
    times: pd.DatetimeIndex,
    embargo_pct: float,
) -> pd.Series:
    """
    Get embargo end time for each timestamp.

    Args:
        times: Sample timestamps
        embargo_pct: Fraction of data to embargo

    Returns:
        Series mapping each time to embargo end time
    """
    step = int(len(times) * embargo_pct)
    if step == 0:
        embargo_end = pd.Series(times, index=times)
    else:
        embargo_end = pd.Series(
            times[step:].append(pd.Index([times[-1]] * step)),
            index=times
        )
    return embargo_end


class CVScorer:
    """
    Score models across CV folds.

    Handles:
    - Training model on each fold
    - Computing train/test metrics
    - Aggregating predictions
    """

    def __init__(
        self,
        model_factory: callable,
        metrics: dict[str, callable] | None = None,
    ):
        """
        Initialize CV scorer.

        Args:
            model_factory: Callable that returns a fresh model instance
            metrics: Dict of metric_name -> metric_function(y_true, y_pred)
        """
        self.model_factory = model_factory
        self.metrics = metrics or {}

    def cross_validate(
        self,
        cv: PurgedKFoldCV | CombinatorialPurgedCV | TimeSeriesCV,
        X: pd.DataFrame,
        y: pd.Series,
        label_end_times: pd.Series | None = None,
        sample_weights: pd.Series | None = None,
        return_predictions: bool = True,
    ) -> CVResult:
        """
        Perform cross-validation.

        Args:
            cv: Cross-validator object
            X: Features
            y: Labels
            label_end_times: Label end times for purging
            sample_weights: Sample weights for training
            return_predictions: Whether to aggregate OOS predictions

        Returns:
            CVResult with metrics and predictions
        """
        folds = []
        train_metrics_list = []
        test_metrics_list = []

        # For aggregating predictions
        all_predictions = pd.Series(index=X.index, dtype=float)
        prediction_counts = pd.Series(0, index=X.index)

        for fold in cv.split(X, y, label_end_times):
            # Get train/test data
            X_train = X.iloc[fold.train_indices]
            y_train = y.iloc[fold.train_indices]
            X_test = X.iloc[fold.test_indices]
            y_test = y.iloc[fold.test_indices]

            # Get sample weights if provided
            sw_train = None
            if sample_weights is not None:
                sw_train = sample_weights.iloc[fold.train_indices]

            # Train model
            model = self.model_factory()
            if sw_train is not None:
                model.fit(X_train, y_train, sample_weight=sw_train)
            else:
                model.fit(X_train, y_train)

            # Predict
            y_train_pred = model.predict(X_train)
            y_test_pred = model.predict(X_test)

            # Calculate metrics
            train_metrics = self._compute_metrics(y_train, y_train_pred)
            test_metrics = self._compute_metrics(y_test, y_test_pred)

            train_metrics_list.append(train_metrics)
            test_metrics_list.append(test_metrics)

            # Store predictions
            if return_predictions:
                test_idx = X.index[fold.test_indices]
                all_predictions.loc[test_idx] += y_test_pred
                prediction_counts.loc[test_idx] += 1

            folds.append(fold)

        # Average predictions where we have multiple
        if return_predictions:
            mask = prediction_counts > 0
            all_predictions.loc[mask] /= prediction_counts.loc[mask]
            all_predictions.loc[~mask] = np.nan
        else:
            all_predictions = None

        # Calculate averages
        n_train_avg = np.mean([f.n_train for f in folds])
        n_test_avg = np.mean([f.n_test for f in folds])
        n_paths = len(folds)

        return CVResult(
            folds=folds,
            n_paths=n_paths,
            n_train_avg=n_train_avg,
            n_test_avg=n_test_avg,
            train_metrics=train_metrics_list,
            test_metrics=test_metrics_list,
            predictions=all_predictions,
        )

    def _compute_metrics(
        self,
        y_true: pd.Series,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        """Compute all metrics."""
        results = {}
        for name, func in self.metrics.items():
            try:
                results[name] = float(func(y_true, y_pred))
            except Exception:
                results[name] = np.nan
        return results


# Convenience functions
def purged_cv(
    X: pd.DataFrame,
    y: pd.Series,
    model_factory: callable,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
    label_end_times: pd.Series | None = None,
    metrics: dict[str, callable] | None = None,
) -> CVResult:
    """
    Perform purged K-fold cross-validation.

    Args:
        X: Features DataFrame
        y: Labels Series
        model_factory: Callable returning fresh model
        n_splits: Number of folds
        embargo_pct: Embargo fraction
        label_end_times: Label end times for purging
        metrics: Metric functions

    Returns:
        CVResult
    """
    cv = PurgedKFoldCV(n_splits=n_splits, embargo_pct=embargo_pct)
    scorer = CVScorer(model_factory, metrics)
    return scorer.cross_validate(cv, X, y, label_end_times)


def combinatorial_purged_cv(
    X: pd.DataFrame,
    y: pd.Series,
    model_factory: callable,
    n_splits: int = 5,
    n_test_groups: int = 2,
    embargo_pct: float = 0.01,
    label_end_times: pd.Series | None = None,
    metrics: dict[str, callable] | None = None,
) -> CVResult:
    """
    Perform combinatorial purged cross-validation.

    Args:
        X: Features DataFrame
        y: Labels Series
        model_factory: Callable returning fresh model
        n_splits: Number of groups
        n_test_groups: Groups to use for testing
        embargo_pct: Embargo fraction
        label_end_times: Label end times
        metrics: Metric functions

    Returns:
        CVResult
    """
    cv = CombinatorialPurgedCV(
        n_splits=n_splits,
        n_test_groups=n_test_groups,
        embargo_pct=embargo_pct,
    )
    scorer = CVScorer(model_factory, metrics)
    return scorer.cross_validate(cv, X, y, label_end_times)


def cv_summary(result: CVResult) -> str:
    """
    Generate human-readable CV summary.

    Args:
        result: CVResult object

    Returns:
        Formatted summary string
    """
    summary = result.summary()

    lines = [
        "Cross-Validation Summary",
        "=" * 40,
        f"Number of folds: {summary['n_folds']}",
        f"Number of paths: {summary['n_paths']}",
        f"Avg train size: {summary['avg_train_size']:.0f}",
        f"Avg test size: {summary['avg_test_size']:.0f}",
        "",
        "Test Set Metrics:",
        "-" * 40,
    ]

    # Add metric summaries
    for key, value in summary.items():
        if key.endswith("_mean"):
            metric_name = key[:-5]
            std = summary.get(f"{metric_name}_std", 0)
            lines.append(f"  {metric_name}: {value:.4f} +/- {std:.4f}")

    return "\n".join(lines)
