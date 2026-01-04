"""
Multi-Level Holdout Structure for Backtesting.

Implements a rigorous holdout methodology to prevent overfitting:
- Burn-in: Data for feature calculation warm-up
- Development: Walk-forward training and testing
- Validation: Paper trading simulation (3-6 months)
- Final Test: Absolute holdout, used ONCE before live trading

As specified in Section 3.3.4 of the Testing Suite documentation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Iterator

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class HoldoutPeriod(str, Enum):
    """Types of holdout periods."""
    BURNIN = "burnin"
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    FINAL_TEST = "final_test"


@dataclass
class HoldoutSplit:
    """A single holdout split with date ranges."""
    period: HoldoutPeriod
    start_date: datetime
    end_date: datetime
    n_days: int
    description: str = ""

    @property
    def date_range(self) -> tuple[datetime, datetime]:
        return (self.start_date, self.end_date)

    def contains(self, date: datetime) -> bool:
        """Check if date falls within this split."""
        return self.start_date <= date <= self.end_date

    def filter_data(self, df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
        """Filter DataFrame to this period."""
        if date_col in df.columns:
            return df[(df[date_col] >= self.start_date) & (df[date_col] <= self.end_date)]
        elif isinstance(df.index, pd.DatetimeIndex):
            return df[(df.index >= self.start_date) & (df.index <= self.end_date)]
        else:
            raise ValueError(f"Cannot filter: no date column '{date_col}' and index is not DatetimeIndex")


@dataclass
class MultiLevelHoldoutConfig:
    """Configuration for multi-level holdout."""
    # Burn-in period for feature warm-up
    burnin_days: int = 252  # 1 year

    # Development period for walk-forward optimization
    development_ratio: float = 0.60  # 60% of remaining data

    # Validation period (paper trading simulation)
    validation_days: int = 126  # 6 months

    # Final test - NEVER TOUCH until ready for live
    final_test_days: int = 63  # 3 months

    # Optional: embargo between periods
    embargo_days: int = 5


@dataclass
class MultiLevelHoldout:
    """
    Multi-level holdout structure for rigorous backtesting.

    Splits data into four non-overlapping periods:
    1. Burn-in: Feature calculation warm-up
    2. Development: Walk-forward training/testing
    3. Validation: Paper trading simulation
    4. Final Test: Absolute holdout (use ONCE!)

    Example timeline:
    |-------|-----------------|----------|----------|
     Burn   Development       Validation  Final Test
     (1y)   (train/test)      (6m)        (3m)
    """

    config: MultiLevelHoldoutConfig
    splits: dict[HoldoutPeriod, HoldoutSplit] = field(default_factory=dict)
    data_start: datetime | None = None
    data_end: datetime | None = None

    # Track if final test has been used
    final_test_used: bool = False
    final_test_used_at: datetime | None = None

    def fit(self, data: pd.DataFrame, date_col: str = "date") -> "MultiLevelHoldout":
        """
        Fit the holdout structure to data.

        Args:
            data: DataFrame with date column or DatetimeIndex
            date_col: Name of date column

        Returns:
            Self with fitted splits
        """
        # Get date range
        if date_col in data.columns:
            dates = pd.to_datetime(data[date_col])
        elif isinstance(data.index, pd.DatetimeIndex):
            dates = data.index
        else:
            raise ValueError("Cannot determine date range from data")

        self.data_start = dates.min().to_pydatetime()
        self.data_end = dates.max().to_pydatetime()

        total_days = (self.data_end - self.data_start).days
        logger.info(f"Fitting holdout structure: {total_days} days from {self.data_start} to {self.data_end}")

        # Calculate split points
        # 1. Burn-in
        burnin_end = self.data_start + timedelta(days=self.config.burnin_days)

        # 2. Final test (counting backwards from end)
        final_test_start = self.data_end - timedelta(days=self.config.final_test_days)

        # 3. Validation (before final test)
        validation_start = final_test_start - timedelta(
            days=self.config.validation_days + self.config.embargo_days
        )
        validation_end = final_test_start - timedelta(days=self.config.embargo_days)

        # 4. Development (between burn-in and validation)
        development_start = burnin_end + timedelta(days=self.config.embargo_days)
        development_end = validation_start - timedelta(days=self.config.embargo_days)

        # Validate that splits don't overlap
        if development_end <= development_start:
            raise ValueError(
                f"Not enough data for holdout structure. Need at least "
                f"{self.config.burnin_days + self.config.validation_days + self.config.final_test_days + 60} days."
            )

        # Create splits
        self.splits = {
            HoldoutPeriod.BURNIN: HoldoutSplit(
                period=HoldoutPeriod.BURNIN,
                start_date=self.data_start,
                end_date=burnin_end,
                n_days=self.config.burnin_days,
                description="Feature calculation warm-up period",
            ),
            HoldoutPeriod.DEVELOPMENT: HoldoutSplit(
                period=HoldoutPeriod.DEVELOPMENT,
                start_date=development_start,
                end_date=development_end,
                n_days=(development_end - development_start).days,
                description="Walk-forward training and testing",
            ),
            HoldoutPeriod.VALIDATION: HoldoutSplit(
                period=HoldoutPeriod.VALIDATION,
                start_date=validation_start,
                end_date=validation_end,
                n_days=self.config.validation_days,
                description="Paper trading simulation period",
            ),
            HoldoutPeriod.FINAL_TEST: HoldoutSplit(
                period=HoldoutPeriod.FINAL_TEST,
                start_date=final_test_start,
                end_date=self.data_end,
                n_days=self.config.final_test_days,
                description="ABSOLUTE HOLDOUT - use ONCE before live!",
            ),
        }

        # Log the structure
        for period, split in self.splits.items():
            logger.info(
                f"  {period.value}: {split.start_date.date()} to {split.end_date.date()} "
                f"({split.n_days} days)"
            )

        return self

    def get_split(self, period: HoldoutPeriod) -> HoldoutSplit:
        """Get a specific split."""
        if period not in self.splits:
            raise ValueError(f"Split {period} not found. Did you call fit()?")
        return self.splits[period]

    def get_burnin_data(self, data: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
        """Get burn-in period data."""
        return self.get_split(HoldoutPeriod.BURNIN).filter_data(data, date_col)

    def get_development_data(self, data: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
        """Get development period data."""
        return self.get_split(HoldoutPeriod.DEVELOPMENT).filter_data(data, date_col)

    def get_validation_data(self, data: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
        """Get validation period data."""
        return self.get_split(HoldoutPeriod.VALIDATION).filter_data(data, date_col)

    def get_final_test_data(
        self,
        data: pd.DataFrame,
        date_col: str = "date",
        confirm: bool = False,
    ) -> pd.DataFrame:
        """
        Get final test period data.

        WARNING: This should only be used ONCE, right before going live!

        Args:
            data: DataFrame to filter
            date_col: Date column name
            confirm: Must be True to access final test data

        Returns:
            Filtered DataFrame

        Raises:
            ValueError: If confirm is False or final test already used
        """
        if not confirm:
            raise ValueError(
                "Final test data requires confirm=True. "
                "This should ONLY be used once before going live!"
            )

        if self.final_test_used:
            logger.warning(
                f"Final test was already used at {self.final_test_used_at}! "
                "Using it again invalidates the holdout methodology."
            )

        self.final_test_used = True
        self.final_test_used_at = datetime.now()

        return self.get_split(HoldoutPeriod.FINAL_TEST).filter_data(data, date_col)

    def get_train_test_data(
        self,
        data: pd.DataFrame,
        date_col: str = "date",
        include_validation: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get training and testing data for development.

        Args:
            data: Full DataFrame
            date_col: Date column name
            include_validation: Include validation in test set

        Returns:
            (train_data, test_data) tuple
        """
        # Training: Burn-in + Development
        burnin_split = self.get_split(HoldoutPeriod.BURNIN)
        dev_split = self.get_split(HoldoutPeriod.DEVELOPMENT)

        if date_col in data.columns:
            train_mask = (
                (data[date_col] >= burnin_split.start_date) &
                (data[date_col] <= dev_split.end_date)
            )
        else:
            train_mask = (
                (data.index >= burnin_split.start_date) &
                (data.index <= dev_split.end_date)
            )

        train_data = data[train_mask]

        # Testing: Validation (and optionally final test)
        if include_validation:
            test_data = self.get_validation_data(data, date_col)
        else:
            # Just use last portion of development
            dev_data = self.get_development_data(data, date_col)
            split_point = int(len(dev_data) * 0.8)
            test_data = dev_data.iloc[split_point:]
            train_data = data[train_mask].iloc[:len(train_data) - len(test_data)]

        return train_data, test_data

    def summary(self) -> dict[str, Any]:
        """Get summary of holdout structure."""
        return {
            "data_range": (
                self.data_start.date() if self.data_start else None,
                self.data_end.date() if self.data_end else None,
            ),
            "total_days": (self.data_end - self.data_start).days if self.data_start else 0,
            "splits": {
                period.value: {
                    "start": split.start_date.date(),
                    "end": split.end_date.date(),
                    "days": split.n_days,
                    "description": split.description,
                }
                for period, split in self.splits.items()
            },
            "final_test_used": self.final_test_used,
            "final_test_used_at": self.final_test_used_at,
        }


class DevelopmentSplitter:
    """
    Walk-forward splitter for the development period.

    Works within the development holdout to generate train/test folds.
    """

    def __init__(
        self,
        train_period_days: int = 504,  # 2 years
        test_period_days: int = 63,  # 3 months
        embargo_days: int = 5,
        step_days: int = 21,  # Move forward 1 month between folds
        min_train_samples: int = 252,
    ):
        self.train_period = train_period_days
        self.test_period = test_period_days
        self.embargo = embargo_days
        self.step = step_days
        self.min_train_samples = min_train_samples

    def split(
        self,
        data: pd.DataFrame,
        date_col: str = "date",
    ) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Generate walk-forward train/test splits.

        Args:
            data: DataFrame with date column
            date_col: Name of date column

        Yields:
            (train_data, test_data) tuples
        """
        if date_col in data.columns:
            dates = pd.to_datetime(data[date_col])
            data = data.set_index(date_col)
            data.index = pd.to_datetime(data.index)
        elif isinstance(data.index, pd.DatetimeIndex):
            dates = data.index
        else:
            raise ValueError("Cannot determine dates from data")

        min_date = dates.min()
        max_date = dates.max()

        # Starting point: after minimum training period
        current_train_end = min_date + timedelta(days=self.train_period)

        while current_train_end + timedelta(days=self.embargo + self.test_period) <= max_date:
            # Define train period
            train_start = max(min_date, current_train_end - timedelta(days=self.train_period))
            train_end = current_train_end

            # Define test period
            test_start = train_end + timedelta(days=self.embargo)
            test_end = test_start + timedelta(days=self.test_period)

            # Filter data
            train_data = data[(data.index >= train_start) & (data.index <= train_end)]
            test_data = data[(data.index >= test_start) & (data.index <= test_end)]

            if len(train_data) >= self.min_train_samples and len(test_data) > 0:
                yield train_data.reset_index(), test_data.reset_index()

            # Move forward
            current_train_end += timedelta(days=self.step)

    def get_n_splits(
        self,
        data: pd.DataFrame,
        date_col: str = "date",
    ) -> int:
        """Get number of splits that will be generated."""
        return sum(1 for _ in self.split(data, date_col))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_holdout_structure(
    data: pd.DataFrame,
    date_col: str = "date",
    burnin_days: int = 252,
    validation_days: int = 126,
    final_test_days: int = 63,
) -> MultiLevelHoldout:
    """
    Create a multi-level holdout structure from data.

    Args:
        data: DataFrame with date column
        date_col: Name of date column
        burnin_days: Days for burn-in period
        validation_days: Days for validation period
        final_test_days: Days for final test period

    Returns:
        Fitted MultiLevelHoldout
    """
    config = MultiLevelHoldoutConfig(
        burnin_days=burnin_days,
        validation_days=validation_days,
        final_test_days=final_test_days,
    )
    holdout = MultiLevelHoldout(config=config)
    return holdout.fit(data, date_col)


def validate_holdout_usage(holdout: MultiLevelHoldout) -> list[str]:
    """
    Validate proper usage of holdout structure.

    Returns list of warnings/errors.
    """
    issues = []

    if holdout.final_test_used:
        issues.append(
            f"WARNING: Final test was used at {holdout.final_test_used_at}. "
            "Any further use invalidates the holdout methodology."
        )

    # Check that we have enough data in each period
    for period, split in holdout.splits.items():
        if split.n_days < 21:
            issues.append(
                f"WARNING: {period.value} period has only {split.n_days} days. "
                "Consider using more data or adjusting holdout configuration."
            )

    return issues
