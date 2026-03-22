"""Strategy agent - wraps trading strategies as agents.

Provides a unified agent interface for traditional and ML-based strategies.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from ..core import Direction, Signal, SignalType, Symbol, Timeframe
from ..strategies.base import MLStrategy, RuleBasedStrategy, Strategy
from .base import (
    Agent,
    AgentCapabilities,
    AgentConfig,
    AgentMessage,
    AgentRole,
    MessageType,
    SignalGeneratorAgent,
)

logger = logging.getLogger(__name__)


@dataclass
class StrategyAgentConfig(AgentConfig):
    """Configuration specific to strategy agents."""

    # Strategy settings
    strategy_class: type[Strategy] | None = None
    strategy_params: dict[str, Any] = field(default_factory=dict)

    # Pre-instantiated strategy (alternative to class)
    strategy_instance: Strategy | None = None

    # Execution settings
    auto_train: bool = True  # Auto-train ML strategies
    retrain_interval: int = 0  # Bars between retraining (0 = never)

    # Signal filtering
    min_confidence: float = 0.0
    min_strength: float = 0.0

    def __post_init__(self):
        if self.role is None:
            self.role = AgentRole.SIGNAL_GENERATOR


class StrategyAgent(SignalGeneratorAgent):
    """
    Agent that wraps a trading strategy.

    Provides agent interface for any Strategy subclass, allowing
    traditional and ML strategies to participate in the agent system.

    Features:
    - Automatic training for ML strategies
    - Signal filtering (confidence/strength thresholds)
    - Performance tracking
    - Async execution
    """

    name: str = "strategy_agent"
    description: str = "Trading strategy wrapped as agent"

    def __init__(
        self,
        strategy: Strategy | None = None,
        strategy_class: type[Strategy] | None = None,
        universe: list[Symbol] | None = None,
        config: StrategyAgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize strategy agent.

        Can be initialized with either:
        1. A pre-instantiated strategy
        2. A strategy class + params to instantiate

        Args:
            strategy: Pre-instantiated strategy
            strategy_class: Strategy class to instantiate
            universe: List of symbols (uses strategy universe if not provided)
            config: Agent configuration
            **kwargs: Additional parameters
        """
        # Determine strategy
        if strategy is not None:
            self._strategy = strategy
        elif strategy_class is not None:
            strategy_params = kwargs.get("strategy_params", {})
            strategy_universe = universe or kwargs.get("symbols", ["AAPL"])
            self._strategy = strategy_class(
                universe=strategy_universe,
                **strategy_params,
            )
        elif config and config.strategy_instance is not None:
            self._strategy = config.strategy_instance
        elif config and config.strategy_class is not None:
            strategy_universe = universe or kwargs.get("symbols", ["AAPL"])
            self._strategy = config.strategy_class(
                universe=strategy_universe,
                **config.strategy_params,
            )
        else:
            raise ValueError(
                "Must provide either 'strategy', 'strategy_class', "
                "or config with strategy_instance/strategy_class"
            )

        # Use strategy's universe
        effective_universe = universe or self._strategy.universe

        # Default config
        if config is None:
            config = StrategyAgentConfig(
                name=self._strategy.name,
                role=AgentRole.SIGNAL_GENERATOR,
            )

        super().__init__(universe=effective_universe, config=config, **kwargs)

        self.name = self._strategy.name
        self._training_data: pd.DataFrame | None = None
        self._bars_since_retrain = 0
        self._is_ml_strategy = isinstance(self._strategy, MLStrategy)

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_generate_signals=True,
            can_analyze=False,
            supported_symbols=self.universe,
            required_data=["ohlcv"],
        )

    @property
    def strategy(self) -> Strategy:
        """Get the wrapped strategy."""
        return self._strategy

    @property
    def is_trained(self) -> bool:
        """Check if strategy is trained (for ML strategies)."""
        return self._strategy.is_trained()

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate signals using the wrapped strategy.

        Args:
            data: Market data
            timestamp: Current timestamp

        Returns:
            List of filtered signals
        """
        timestamp = timestamp or datetime.now()

        # Auto-train ML strategies if needed
        if self._is_ml_strategy and not self.is_trained:
            if isinstance(self.config, StrategyAgentConfig) and self.config.auto_train:
                await self._train_strategy(data)

        # Check retraining interval
        if (
            self._is_ml_strategy
            and isinstance(self.config, StrategyAgentConfig)
            and self.config.retrain_interval > 0
        ):
            self._bars_since_retrain += 1
            if self._bars_since_retrain >= self.config.retrain_interval:
                await self._train_strategy(data)
                self._bars_since_retrain = 0

        # Generate signals
        try:
            signals = self._strategy.generate_signals(data, timestamp)
        except Exception as e:
            logger.error(f"Strategy {self.name} error: {e}")
            return []

        # Filter signals based on config
        filtered_signals = self._filter_signals(signals)

        return filtered_signals

    def _filter_signals(self, signals: list[Signal]) -> list[Signal]:
        """Filter signals based on configuration thresholds."""
        if not isinstance(self.config, StrategyAgentConfig):
            return signals

        filtered = []
        for signal in signals:
            # Check confidence threshold
            if signal.confidence < self.config.min_confidence:
                continue

            # Check strength threshold
            if abs(signal.strength) < self.config.min_strength:
                continue

            filtered.append(signal)

        return filtered

    async def _train_strategy(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
    ) -> dict[str, Any]:
        """Train the ML strategy."""
        if not self._is_ml_strategy:
            return {"status": "not_ml_strategy"}

        logger.info(f"Training strategy: {self.name}")

        try:
            # Run training in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(
                None,
                self._strategy.train,
                data,
            )

            logger.info(f"Strategy {self.name} trained: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Training failed for {self.name}: {e}")
            return {"status": "error", "error": str(e)}

    async def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Explicitly train the strategy.

        Args:
            data: Training data
            **kwargs: Additional training parameters

        Returns:
            Training metrics
        """
        return await self._train_strategy(data)

    def get_feature_importance(self) -> dict[str, float] | None:
        """Get feature importance for ML strategies."""
        if not self._is_ml_strategy:
            return None

        if hasattr(self._strategy, "get_feature_importance"):
            importance = self._strategy.get_feature_importance()
            return importance.to_dict() if hasattr(importance, "to_dict") else dict(importance)

        return None


class MultiStrategyAgent(SignalGeneratorAgent):
    """
    Agent that runs multiple strategies and aggregates their signals.

    Useful for strategy ensembles without using the full ensemble agent.
    """

    name: str = "multi_strategy_agent"
    description: str = "Runs multiple strategies and aggregates signals"

    def __init__(
        self,
        strategies: list[Strategy],
        universe: list[Symbol] | None = None,
        aggregation_method: str = "weighted_mean",
        config: AgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize multi-strategy agent.

        Args:
            strategies: List of strategies to run
            universe: List of symbols (union of all strategy universes if not provided)
            aggregation_method: How to aggregate signals ('mean', 'weighted_mean', 'vote')
            config: Agent configuration
            **kwargs: Additional parameters
        """
        self._strategies = strategies
        self._aggregation_method = aggregation_method

        # Determine universe from strategies if not provided
        if universe is None:
            universe = list(set(
                sym for strategy in strategies
                for sym in strategy.universe
            ))

        super().__init__(universe=universe, config=config, **kwargs)

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_generate_signals=True,
            can_aggregate=True,
            supported_symbols=self.universe,
        )

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate and aggregate signals from all strategies.

        Args:
            data: Market data
            timestamp: Current timestamp

        Returns:
            Aggregated signals
        """
        timestamp = timestamp or datetime.now()

        # Collect signals from all strategies
        all_signals: dict[Symbol, list[Signal]] = {}

        for strategy in self._strategies:
            try:
                signals = strategy.generate_signals(data, timestamp)
                for signal in signals:
                    if signal.symbol not in all_signals:
                        all_signals[signal.symbol] = []
                    all_signals[signal.symbol].append(signal)
            except Exception as e:
                logger.error(f"Strategy {strategy.name} error: {e}")

        # Aggregate signals by symbol
        aggregated_signals = []
        for symbol, signals in all_signals.items():
            aggregated = self._aggregate_symbol_signals(symbol, signals, timestamp)
            if aggregated is not None:
                aggregated_signals.append(aggregated)

        return aggregated_signals

    def _aggregate_symbol_signals(
        self,
        symbol: Symbol,
        signals: list[Signal],
        timestamp: datetime,
    ) -> Signal | None:
        """Aggregate signals for a single symbol."""
        if not signals:
            return None

        if self._aggregation_method == "mean":
            strength = sum(s.strength for s in signals) / len(signals)
            confidence = sum(s.confidence for s in signals) / len(signals)

        elif self._aggregation_method == "weighted_mean":
            total_confidence = sum(s.confidence for s in signals)
            if total_confidence == 0:
                return None
            strength = sum(s.strength * s.confidence for s in signals) / total_confidence
            confidence = total_confidence / len(signals)

        elif self._aggregation_method == "vote":
            # Majority vote on direction
            long_votes = sum(1 for s in signals if s.direction == Direction.LONG)
            short_votes = sum(1 for s in signals if s.direction == Direction.SHORT)

            if long_votes > short_votes:
                strength = long_votes / len(signals)
            elif short_votes > long_votes:
                strength = -short_votes / len(signals)
            else:
                return None  # Tie - no signal

            confidence = max(long_votes, short_votes) / len(signals)

        else:
            raise ValueError(f"Unknown aggregation method: {self._aggregation_method}")

        # Determine direction from strength
        if strength > 0:
            direction = Direction.LONG
            signal_type = SignalType.ENTRY_LONG
        elif strength < 0:
            direction = Direction.SHORT
            signal_type = SignalType.ENTRY_SHORT
        else:
            return None

        return self.create_signal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            signal_type=signal_type,
            metadata={
                "aggregation_method": self._aggregation_method,
                "n_strategies": len(signals),
                "strategy_names": [s.strategy_name for s in signals],
            },
        )


class AdaptiveStrategyAgent(StrategyAgent):
    """
    Strategy agent that adapts parameters based on regime or performance.

    Can switch between strategies or adjust parameters based on
    market conditions or recent performance.
    """

    name: str = "adaptive_strategy_agent"
    description: str = "Adapts strategy parameters based on conditions"

    def __init__(
        self,
        strategies: dict[str, Strategy],
        regime_detector: Any | None = None,
        performance_window: int = 20,
        config: StrategyAgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize adaptive strategy agent.

        Args:
            strategies: Dict mapping regime/mode names to strategies
            regime_detector: Optional regime detection model
            performance_window: Window for rolling performance evaluation
            config: Agent configuration
            **kwargs: Additional parameters
        """
        self._strategies_dict = strategies
        self._regime_detector = regime_detector
        self._performance_window = performance_window
        self._current_regime = "default"
        self._performance_history: list[float] = []

        # Default to first strategy
        default_strategy = list(strategies.values())[0]
        super().__init__(strategy=default_strategy, config=config, **kwargs)

    def _detect_regime(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
    ) -> str:
        """Detect current market regime."""
        if self._regime_detector is None:
            return "default"

        # Use regime detector if available
        if hasattr(self._regime_detector, "predict"):
            try:
                if isinstance(data, dict):
                    sample_data = list(data.values())[0]
                else:
                    sample_data = data

                regime = self._regime_detector.predict(sample_data)
                return str(regime)
            except Exception as e:
                logger.warning(f"Regime detection failed: {e}")

        return "default"

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate signals using regime-appropriate strategy."""

        # Detect regime and switch strategy if needed
        new_regime = self._detect_regime(data)
        if new_regime != self._current_regime:
            if new_regime in self._strategies_dict:
                self._strategy = self._strategies_dict[new_regime]
                self._current_regime = new_regime
                logger.info(f"Switched to regime: {new_regime}")

        # Generate signals with current strategy
        return await super().generate_signals(data, timestamp)


def wrap_strategy(
    strategy: Strategy,
    min_confidence: float = 0.0,
    min_strength: float = 0.0,
    auto_train: bool = True,
) -> StrategyAgent:
    """
    Convenience function to wrap a strategy as an agent.

    Args:
        strategy: Strategy to wrap
        min_confidence: Minimum signal confidence
        min_strength: Minimum signal strength
        auto_train: Auto-train ML strategies

    Returns:
        StrategyAgent wrapping the strategy
    """
    config = StrategyAgentConfig(
        name=strategy.name,
        role=AgentRole.SIGNAL_GENERATOR,
        min_confidence=min_confidence,
        min_strength=min_strength,
        auto_train=auto_train,
    )

    return StrategyAgent(strategy=strategy, config=config)


def create_strategy_agent(
    strategy_class: type[Strategy],
    universe: list[Symbol],
    strategy_params: dict[str, Any] | None = None,
    **agent_params: Any,
) -> StrategyAgent:
    """
    Factory function to create a strategy agent.

    Args:
        strategy_class: Strategy class to instantiate
        universe: List of symbols
        strategy_params: Parameters for the strategy
        **agent_params: Parameters for the agent

    Returns:
        Configured StrategyAgent
    """
    config = StrategyAgentConfig(
        name=strategy_class.name if hasattr(strategy_class, "name") else strategy_class.__name__,
        role=AgentRole.SIGNAL_GENERATOR,
        strategy_class=strategy_class,
        strategy_params=strategy_params or {},
        **{k: v for k, v in agent_params.items() if k in StrategyAgentConfig.__dataclass_fields__},
    )

    return StrategyAgent(
        strategy_class=strategy_class,
        universe=universe,
        config=config,
        strategy_params=strategy_params or {},
    )
