"""Base strategy interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from ..core import Direction, Signal, SignalType, Symbol, Timeframe


@dataclass
class StrategyConfig:
    """Configuration for a strategy."""

    name: str
    universe: list[Symbol]
    timeframe: Timeframe = Timeframe.DAILY
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class Strategy(ABC):
    """
    Abstract base class for all trading strategies.

    Strategies generate signals based on market data. They can be
    traditional rule-based strategies or ML-based strategies.
    """

    name: str = "base_strategy"
    description: str = ""
    version: str = "1.0.0"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        **params: Any,
    ):
        """
        Initialize strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            **params: Strategy-specific parameters
        """
        self.universe = universe
        self.timeframe = timeframe
        self.params = params
        self._is_trained = False

    @property
    def config(self) -> StrategyConfig:
        """Get strategy configuration."""
        return StrategyConfig(
            name=self.name,
            universe=self.universe,
            timeframe=self.timeframe,
            parameters=self.params,
        )

    @abstractmethod
    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate trading signals from market data.

        Args:
            data: OHLCV data - either single DataFrame or dict of DataFrames
            timestamp: Current timestamp (for live trading)

        Returns:
            List of trading signals
        """
        ...

    @abstractmethod
    def get_required_history(self) -> int:
        """
        Get the number of historical bars required.

        Returns:
            Number of bars needed for signal generation
        """
        ...

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Train the strategy (for ML strategies).

        Default implementation does nothing. Override for ML strategies.

        Args:
            data: Training data
            **kwargs: Training parameters

        Returns:
            Training metrics/results
        """
        self._is_trained = True
        return {}

    def is_trained(self) -> bool:
        """Check if strategy has been trained."""
        return self._is_trained

    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate that data has required columns.

        Args:
            data: DataFrame to validate

        Returns:
            True if data is valid
        """
        required = {"open", "high", "low", "close", "volume"}
        return required.issubset(set(data.columns.str.lower()))

    def create_signal(
        self,
        symbol: Symbol,
        direction: Direction,
        strength: float,
        confidence: float = 0.5,
        timestamp: datetime | None = None,
        signal_type: SignalType = SignalType.ENTRY_LONG,
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """
        Helper to create a signal with strategy name attached.

        Args:
            symbol: Asset symbol
            direction: Signal direction
            strength: Signal strength (-1 to 1)
            confidence: Confidence level (0 to 1)
            timestamp: Signal timestamp
            signal_type: Type of signal
            metadata: Additional metadata

        Returns:
            Signal object
        """
        return Signal(
            timestamp=timestamp or datetime.now(),
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            signal_type=signal_type,
            strategy_name=self.name,
            metadata=metadata or {},
        )

    def get_parameters(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self.params.copy()

    def set_parameters(self, **params: Any) -> None:
        """Update strategy parameters."""
        self.params.update(params)
        self._is_trained = False  # Reset training status

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, universe={len(self.universe)} symbols)"


class RuleBasedStrategy(Strategy):
    """
    Base class for traditional rule-based strategies.

    Provides common utilities for technical analysis strategies.
    """

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Rule-based strategies don't need training."""
        self._is_trained = True
        return {"status": "no_training_required"}


class MLStrategy(Strategy):
    """
    Base class for ML-based strategies.

    Provides common utilities for machine learning strategies.
    """

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        model: Any = None,
        **params: Any,
    ):
        """
        Initialize ML strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            model: Pre-trained model (optional)
            **params: Strategy-specific parameters
        """
        super().__init__(universe, timeframe, **params)
        self.model = model
        self._is_trained = model is not None

    @abstractmethod
    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare features for the ML model.

        Args:
            data: Raw OHLCV data

        Returns:
            DataFrame with features
        """
        ...

    @abstractmethod
    def predict(self, features: pd.DataFrame) -> pd.Series:
        """
        Generate predictions from features.

        Args:
            features: Feature DataFrame

        Returns:
            Series of predictions
        """
        ...

    def save_model(self, path: str) -> None:
        """Save the trained model."""
        raise NotImplementedError

    def load_model(self, path: str) -> None:
        """Load a trained model."""
        raise NotImplementedError
