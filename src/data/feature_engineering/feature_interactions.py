"""Feature interaction generator.

Automatically generates interaction features by combining existing features
using mathematical operations (multiplication, division, difference, ratio).
"""

import logging
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class InteractionFeature:
    """Definition of an interaction feature."""

    name: str
    feature_a: str
    feature_b: str
    operation: str  # 'multiply', 'divide', 'subtract', 'ratio', 'zscore_diff'
    description: str = ""
    ic_score: float | None = None  # Information coefficient if computed
    stable: bool | None = None  # Stability flag if tested

    def __hash__(self):
        return hash((self.name, self.feature_a, self.feature_b, self.operation))


@dataclass
class InteractionResult:
    """Result of interaction feature analysis."""

    features_created: list[InteractionFeature]
    features_df: pd.DataFrame
    ic_scores: dict[str, float] = field(default_factory=dict)
    top_features: list[str] = field(default_factory=list)


class FeatureInteractionGenerator:
    """
    Generates interaction features from existing features.

    Supports:
    - Multiplication (A * B): Captures joint effects
    - Division (A / B): Ratios and normalizations
    - Subtraction (A - B): Differences and spreads
    - Ratio ((A - B) / (A + B)): Normalized difference
    - Z-score difference: Standardized comparison
    """

    OPERATIONS = {
        "multiply": lambda a, b: a * b,
        "divide": lambda a, b: a / (b + 1e-8),  # Avoid division by zero
        "subtract": lambda a, b: a - b,
        "ratio": lambda a, b: (a - b) / (np.abs(a) + np.abs(b) + 1e-8),
        "zscore_diff": lambda a, b: (
            (a - a.mean()) / (a.std() + 1e-8) -
            (b - b.mean()) / (b.std() + 1e-8)
        ),
    }

    # Common meaningful interaction patterns
    MEANINGFUL_PAIRS = [
        # Momentum interactions
        ("rsi", "volume_change", "multiply"),  # RSI with volume confirmation
        ("macd", "volume_change", "multiply"),  # MACD with volume
        ("momentum", "volatility", "divide"),  # Risk-adjusted momentum

        # Volatility interactions
        ("bollinger_width", "volume_zscore", "multiply"),  # Volatility breakout
        ("atr", "volume_change", "multiply"),  # Volatility with volume

        # Sentiment interactions
        ("news_sentiment", "volume_change", "multiply"),  # Sentiment with confirmation
        ("social_sentiment", "momentum", "multiply"),  # Social + price agreement

        # Technical cross-signals
        ("rsi", "bollinger_pct_b", "subtract"),  # Overbought divergence
        ("momentum", "rsi", "subtract"),  # Momentum-RSI divergence

        # Ratio features
        ("close", "sma_20", "ratio"),  # Price relative to SMA
        ("volume", "avg_volume", "ratio"),  # Volume spike
    ]

    def __init__(
        self,
        operations: list[str] | None = None,
        exclude_pairs: list[tuple[str, str]] | None = None,
        min_ic: float = 0.02,
    ):
        """
        Initialize interaction generator.

        Args:
            operations: List of operations to use (default: all)
            exclude_pairs: Feature pairs to exclude
            min_ic: Minimum IC to keep feature
        """
        self.operations = operations or list(self.OPERATIONS.keys())
        self.exclude_pairs = set(exclude_pairs or [])
        self.min_ic = min_ic

    def _get_operation_func(self, operation: str) -> Callable:
        """Get the operation function."""
        if operation not in self.OPERATIONS:
            raise ValueError(f"Unknown operation: {operation}")
        return self.OPERATIONS[operation]

    def _create_interaction_name(
        self,
        feature_a: str,
        feature_b: str,
        operation: str,
    ) -> str:
        """Create name for interaction feature."""
        op_symbols = {
            "multiply": "x",
            "divide": "div",
            "subtract": "minus",
            "ratio": "ratio",
            "zscore_diff": "zdiff",
        }
        return f"{feature_a}_{op_symbols.get(operation, operation)}_{feature_b}"

    def generate_interactions(
        self,
        df: pd.DataFrame,
        feature_columns: list[str] | None = None,
        operations: list[str] | None = None,
        max_interactions: int = 100,
    ) -> InteractionResult:
        """
        Generate all pairwise interaction features.

        Args:
            df: DataFrame with features
            feature_columns: Columns to use (default: all numeric)
            operations: Operations to apply (default: self.operations)
            max_interactions: Maximum number of interactions to generate

        Returns:
            InteractionResult with new features
        """
        operations = operations or self.operations

        # Get feature columns
        if feature_columns is None:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
            # Exclude common non-feature columns
            exclude = {"open", "high", "low", "close", "volume", "adj_close"}
            feature_columns = [c for c in feature_columns if c not in exclude]

        logger.info(f"Generating interactions for {len(feature_columns)} features")

        interactions = []
        new_columns = {}

        # Generate all pairs
        for feature_a, feature_b in combinations(feature_columns, 2):
            if (feature_a, feature_b) in self.exclude_pairs:
                continue
            if (feature_b, feature_a) in self.exclude_pairs:
                continue

            for operation in operations:
                if len(interactions) >= max_interactions:
                    break

                name = self._create_interaction_name(feature_a, feature_b, operation)
                func = self._get_operation_func(operation)

                try:
                    values = func(df[feature_a], df[feature_b])

                    # Skip if too many NaN or constant
                    if values.isna().mean() > 0.5:
                        continue
                    if values.std() < 1e-8:
                        continue

                    new_columns[name] = values
                    interactions.append(InteractionFeature(
                        name=name,
                        feature_a=feature_a,
                        feature_b=feature_b,
                        operation=operation,
                        description=f"{feature_a} {operation} {feature_b}",
                    ))

                except Exception as e:
                    logger.debug(f"Failed to compute {name}: {e}")

        # Create result DataFrame
        result_df = pd.DataFrame(new_columns, index=df.index)

        logger.info(f"Generated {len(interactions)} interaction features")

        return InteractionResult(
            features_created=interactions,
            features_df=result_df,
        )

    def generate_meaningful_interactions(
        self,
        df: pd.DataFrame,
    ) -> InteractionResult:
        """
        Generate only meaningful/curated interaction features.

        Uses predefined meaningful pairs that have domain relevance.

        Args:
            df: DataFrame with features

        Returns:
            InteractionResult with curated features
        """
        interactions = []
        new_columns = {}

        for feature_a, feature_b, operation in self.MEANINGFUL_PAIRS:
            if feature_a not in df.columns or feature_b not in df.columns:
                continue

            name = self._create_interaction_name(feature_a, feature_b, operation)
            func = self._get_operation_func(operation)

            try:
                values = func(df[feature_a], df[feature_b])
                new_columns[name] = values
                interactions.append(InteractionFeature(
                    name=name,
                    feature_a=feature_a,
                    feature_b=feature_b,
                    operation=operation,
                    description=f"Meaningful: {feature_a} {operation} {feature_b}",
                ))
            except Exception as e:
                logger.debug(f"Failed to compute {name}: {e}")

        result_df = pd.DataFrame(new_columns, index=df.index)

        return InteractionResult(
            features_created=interactions,
            features_df=result_df,
        )

    def rank_by_ic(
        self,
        interaction_result: InteractionResult,
        forward_returns: pd.Series,
        top_n: int = 20,
    ) -> InteractionResult:
        """
        Rank interaction features by information coefficient.

        Args:
            interaction_result: Result from generate_interactions
            forward_returns: Forward returns to correlate with
            top_n: Number of top features to select

        Returns:
            Updated InteractionResult with IC scores and rankings
        """
        ic_scores = {}

        for col in interaction_result.features_df.columns:
            feature = interaction_result.features_df[col]
            # Align indices
            aligned_returns = forward_returns.reindex(feature.index)
            valid_mask = ~(feature.isna() | aligned_returns.isna())

            if valid_mask.sum() < 30:
                continue

            # Compute Spearman IC
            ic = feature[valid_mask].corr(aligned_returns[valid_mask], method="spearman")
            ic_scores[col] = ic

        # Sort by absolute IC
        sorted_features = sorted(ic_scores.items(), key=lambda x: abs(x[1]), reverse=True)
        top_features = [f[0] for f in sorted_features[:top_n]]

        # Update interaction features with IC scores
        for interaction in interaction_result.features_created:
            if interaction.name in ic_scores:
                interaction.ic_score = ic_scores[interaction.name]

        interaction_result.ic_scores = ic_scores
        interaction_result.top_features = top_features

        logger.info(f"Top 5 by IC: {sorted_features[:5]}")

        return interaction_result

    def auto_discover_interactions(
        self,
        df: pd.DataFrame,
        forward_returns: pd.Series,
        max_interactions: int = 200,
        top_n: int = 20,
        min_ic: float = 0.02,
    ) -> pd.DataFrame:
        """
        Automatically discover and select best interaction features.

        Args:
            df: DataFrame with features
            forward_returns: Forward returns for IC calculation
            max_interactions: Maximum interactions to try
            top_n: Number of top features to keep
            min_ic: Minimum absolute IC to include

        Returns:
            DataFrame with top interaction features
        """
        # Generate all interactions
        result = self.generate_interactions(df, max_interactions=max_interactions)

        # Rank by IC
        result = self.rank_by_ic(result, forward_returns, top_n=top_n)

        # Filter by minimum IC
        selected_features = [
            f for f in result.top_features
            if abs(result.ic_scores.get(f, 0)) >= min_ic
        ]

        if not selected_features:
            logger.warning("No interaction features met the minimum IC threshold")
            return pd.DataFrame()

        return result.features_df[selected_features]


class PolynomialFeatureGenerator:
    """
    Generate polynomial features (squares, cubes).

    Useful for capturing non-linear relationships.
    """

    def __init__(self, degree: int = 2):
        """
        Initialize polynomial generator.

        Args:
            degree: Maximum polynomial degree
        """
        self.degree = degree

    def generate(
        self,
        df: pd.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Generate polynomial features.

        Args:
            df: DataFrame with features
            feature_columns: Columns to transform

        Returns:
            DataFrame with polynomial features
        """
        if feature_columns is None:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
            exclude = {"open", "high", "low", "close", "volume"}
            feature_columns = [c for c in feature_columns if c not in exclude]

        new_columns = {}

        for col in feature_columns:
            for deg in range(2, self.degree + 1):
                new_name = f"{col}_pow{deg}"
                new_columns[new_name] = df[col] ** deg

        return pd.DataFrame(new_columns, index=df.index)


class LaggedFeatureGenerator:
    """
    Generate lagged versions of features.

    Captures temporal dependencies.
    """

    def __init__(self, lags: list[int] | None = None):
        """
        Initialize lag generator.

        Args:
            lags: List of lag periods (default: [1, 5, 10, 20])
        """
        self.lags = lags or [1, 5, 10, 20]

    def generate(
        self,
        df: pd.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Generate lagged features.

        Args:
            df: DataFrame with features
            feature_columns: Columns to lag

        Returns:
            DataFrame with lagged features
        """
        if feature_columns is None:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()
            exclude = {"open", "high", "low", "close", "volume"}
            feature_columns = [c for c in feature_columns if c not in exclude]

        new_columns = {}

        for col in feature_columns:
            for lag in self.lags:
                new_name = f"{col}_lag{lag}"
                new_columns[new_name] = df[col].shift(lag)

        return pd.DataFrame(new_columns, index=df.index)

    def generate_momentum(
        self,
        df: pd.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Generate momentum (change) features.

        Args:
            df: DataFrame with features
            feature_columns: Columns to compute momentum for

        Returns:
            DataFrame with momentum features
        """
        if feature_columns is None:
            feature_columns = df.select_dtypes(include=[np.number]).columns.tolist()

        new_columns = {}

        for col in feature_columns:
            for lag in self.lags:
                # Absolute change
                new_columns[f"{col}_change{lag}"] = df[col] - df[col].shift(lag)
                # Percent change
                new_columns[f"{col}_pctchg{lag}"] = df[col].pct_change(periods=lag)

        return pd.DataFrame(new_columns, index=df.index)
