"""Walk-Forward Validation for Time Series ML.

Implements proper time-series cross-validation with:
- Expanding or rolling training windows
- Gap between train and test to prevent lookahead
- Purging of overlapping samples
- Embargo periods for realistic evaluation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardSplit:
    """Single walk-forward split."""
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_dates: tuple[datetime, datetime] | None = None
    test_dates: tuple[datetime, datetime] | None = None


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""
    fold: int
    train_size: int
    test_size: int
    train_score: float
    test_score: float
    predictions: np.ndarray
    actuals: np.ndarray
    feature_importance: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class WalkForwardSplitter:
    """
    Walk-forward time series splitter.

    Implements proper time-series cross-validation that respects
    the temporal order of data and prevents lookahead bias.

    Parameters:
        train_size: Number of samples in training window
        test_size: Number of samples in test window
        gap: Number of samples between train and test (embargo)
        expanding: If True, use expanding window; if False, use rolling window
        n_splits: Number of folds (if None, use maximum possible)

    Example:
        ```python
        splitter = WalkForwardSplitter(
            train_size=252,  # 1 year training
            test_size=63,    # 1 quarter test
            gap=5,           # 1 week gap
            n_splits=5,      # 5 folds
        )

        for train_idx, test_idx in splitter.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            # Train and evaluate...
        ```
    """

    def __init__(
        self,
        train_size: int = 252,
        test_size: int = 63,
        gap: int = 5,
        expanding: bool = False,
        n_splits: Optional[int] = None,
    ):
        self.train_size = train_size
        self.test_size = test_size
        self.gap = gap
        self.expanding = expanding
        self.n_splits = n_splits

    def get_n_splits(self, X: Optional[np.ndarray] = None) -> int:
        """Get number of splits."""
        if self.n_splits is not None:
            return self.n_splits
        if X is None:
            raise ValueError("X is required when n_splits is not set")

        n_samples = len(X)
        min_required = self.train_size + self.gap + self.test_size

        if n_samples < min_required:
            return 0

        # Maximum possible splits
        remaining = n_samples - min_required
        max_splits = remaining // self.test_size + 1

        return max_splits

    def split(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None,
        groups: Optional[np.ndarray] = None,
    ) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
        """
        Generate indices for train/test splits.

        Args:
            X: Features array or DataFrame
            y: Target array (unused, for sklearn compatibility)
            groups: Group labels (unused, for sklearn compatibility)

        Yields:
            Tuple of (train_indices, test_indices)
        """
        n_samples = len(X)
        n_splits = self.get_n_splits(X)

        if n_splits == 0:
            logger.warning(
                f"Not enough samples ({n_samples}) for walk-forward with "
                f"train={self.train_size}, test={self.test_size}, gap={self.gap}"
            )
            return

        for fold in range(n_splits):
            split = self._get_split_indices(n_samples, fold, n_splits)

            train_indices = np.arange(split.train_start, split.train_end)
            test_indices = np.arange(split.test_start, split.test_end)

            yield train_indices, test_indices

    def get_splits_info(self, X: np.ndarray) -> list[WalkForwardSplit]:
        """
        Get detailed information about all splits.

        Args:
            X: Features array or DataFrame

        Returns:
            List of WalkForwardSplit objects with split details
        """
        n_samples = len(X)
        n_splits = self.get_n_splits(X)
        splits = []

        # Get dates if DataFrame with DatetimeIndex
        dates = None
        if isinstance(X, pd.DataFrame) and isinstance(X.index, pd.DatetimeIndex):
            dates = X.index

        for fold in range(n_splits):
            split = self._get_split_indices(n_samples, fold, n_splits)

            if dates is not None:
                split.train_dates = (dates[split.train_start], dates[split.train_end - 1])
                split.test_dates = (dates[split.test_start], dates[split.test_end - 1])

            splits.append(split)

        return splits

    def _get_split_indices(
        self,
        n_samples: int,
        fold: int,
        n_splits: int,
    ) -> WalkForwardSplit:
        """Calculate indices for a single fold."""
        if self.expanding:
            # Expanding window: training always starts at 0
            train_start = 0
            test_end_offset = n_samples - (n_splits - fold - 1) * self.test_size
            test_end = min(test_end_offset, n_samples)
            test_start = test_end - self.test_size
            train_end = test_start - self.gap
        else:
            # Rolling window: fixed training size
            test_end_offset = n_samples - (n_splits - fold - 1) * self.test_size
            test_end = min(test_end_offset, n_samples)
            test_start = test_end - self.test_size
            train_end = test_start - self.gap
            train_start = max(0, train_end - self.train_size)

        return WalkForwardSplit(
            fold=fold,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        )


class PurgedKFold:
    """
    Purged K-Fold cross-validation for time series.

    Implements the purged K-fold from "Advances in Financial Machine Learning"
    by de Prado. Removes samples that overlap with test data to prevent
    lookahead bias.

    Parameters:
        n_splits: Number of folds
        purge_gap: Number of samples to purge before and after test
        embargo_pct: Percentage of train data to embargo after test
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge_gap: int = 5,
        embargo_pct: float = 0.01,
    ):
        self.n_splits = n_splits
        self.purge_gap = purge_gap
        self.embargo_pct = embargo_pct

    def split(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None,
        groups: Optional[np.ndarray] = None,
    ) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
        """
        Generate purged train/test splits.

        Args:
            X: Features array
            y: Target array (unused)
            groups: Group labels (unused)

        Yields:
            Tuple of (train_indices, test_indices)
        """
        n_samples = len(X)
        fold_size = n_samples // self.n_splits
        embargo_size = int(n_samples * self.embargo_pct)

        for fold in range(self.n_splits):
            test_start = fold * fold_size
            test_end = test_start + fold_size
            if fold == self.n_splits - 1:
                test_end = n_samples

            # Purge: remove samples that overlap with test
            purge_start = max(0, test_start - self.purge_gap)
            purge_end = min(n_samples, test_end + self.purge_gap + embargo_size)

            # Training indices: everything except purged region
            train_indices = np.concatenate([
                np.arange(0, purge_start),
                np.arange(purge_end, n_samples),
            ])

            test_indices = np.arange(test_start, test_end)

            yield train_indices, test_indices


def compute_sample_weights(
    returns: pd.Series,
    span: int = 60,
) -> pd.Series:
    """
    Compute sample weights based on uniqueness of information.

    Samples with more unique information (less overlap with others)
    get higher weights. Based on de Prado's average uniqueness.

    Args:
        returns: Return series
        span: Lookback for computing uniqueness

    Returns:
        Series of sample weights
    """
    # Compute concurrent labels (simplified)
    # In practice, would use label timestamps for proper concurrency

    # Use inverse of volatility as proxy for uniqueness
    vol = returns.rolling(span).std()
    vol_normalized = vol / vol.mean()

    # Higher vol = less unique (more noise) = lower weight
    weights = 1 / (1 + vol_normalized)

    # Normalize to mean 1
    weights = weights / weights.mean()

    return weights.fillna(1)
