"""Ensemble agent for multi-agent signal aggregation.

Provides various methods for combining signals from multiple agents:
- Simple averaging
- Weighted voting
- Confidence-weighted aggregation
- Bayesian combination
- Stacking (meta-learner)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..core import Direction, Signal, SignalBundle, SignalType, Symbol
from .base import (
    Agent,
    AgentCapabilities,
    AgentConfig,
    AgentMessage,
    AgentRole,
    AgentState,
    CoordinatorAgent,
    MessageType,
    SignalGeneratorAgent,
)

logger = logging.getLogger(__name__)


class AggregationMethod(str, Enum):
    """Methods for aggregating signals from multiple agents."""

    MEAN = "mean"  # Simple average
    WEIGHTED_MEAN = "weighted_mean"  # Weighted by agent weight
    CONFIDENCE_WEIGHTED = "confidence_weighted"  # Weighted by signal confidence
    VOTE = "vote"  # Majority voting
    WEIGHTED_VOTE = "weighted_vote"  # Weighted majority voting
    MAX_CONFIDENCE = "max_confidence"  # Take signal with highest confidence
    BAYESIAN = "bayesian"  # Bayesian combination
    CONSENSUS = "consensus"  # Only signal if all agents agree


class ConflictResolution(str, Enum):
    """How to handle conflicting signals."""

    IGNORE = "ignore"  # No signal if conflict
    MAJORITY = "majority"  # Follow majority
    WEIGHTED = "weighted"  # Use weights to resolve
    ABSTAIN = "abstain"  # Abstain and log conflict


@dataclass
class EnsembleConfig(AgentConfig):
    """Configuration for ensemble agent."""

    aggregation_method: AggregationMethod = AggregationMethod.CONFIDENCE_WEIGHTED
    conflict_resolution: ConflictResolution = ConflictResolution.WEIGHTED

    # Thresholds
    min_agreement: float = 0.5  # Minimum fraction of agents that must agree
    min_combined_confidence: float = 0.3  # Minimum combined confidence
    min_agents_required: int = 2  # Minimum agents that must signal

    # Agent weights (name -> weight)
    agent_weights: dict[str, float] = field(default_factory=dict)

    # Performance tracking
    track_agent_performance: bool = True
    performance_window: int = 100  # Signals to consider for performance

    def __post_init__(self):
        if self.role is None:
            self.role = AgentRole.ENSEMBLE


@dataclass
class AgentPerformance:
    """Track agent performance for adaptive weighting."""

    agent_name: str
    signal_count: int = 0
    correct_signals: int = 0
    total_return: float = 0.0
    recent_signals: list[dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """Signal accuracy."""
        if self.signal_count == 0:
            return 0.5  # Prior
        return self.correct_signals / self.signal_count

    @property
    def information_coefficient(self) -> float:
        """Information coefficient (correlation with returns)."""
        if len(self.recent_signals) < 10:
            return 0.0

        predictions = [s["strength"] for s in self.recent_signals if "strength" in s]
        returns = [s["return"] for s in self.recent_signals if "return" in s]

        if len(predictions) < 10 or len(returns) < 10:
            return 0.0

        return float(np.corrcoef(predictions[:len(returns)], returns)[0, 1])


class EnsembleAgent(SignalGeneratorAgent):
    """
    Ensemble agent that aggregates signals from multiple agents.

    Features:
    - Multiple aggregation methods
    - Conflict resolution strategies
    - Performance-based adaptive weighting
    - Consensus requirements
    """

    name: str = "ensemble_agent"
    description: str = "Aggregates signals from multiple agents"

    def __init__(
        self,
        agents: list[Agent],
        universe: list[Symbol] | None = None,
        config: EnsembleConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize ensemble agent.

        Args:
            agents: List of agents to aggregate
            universe: List of symbols (union of agent universes if not provided)
            config: Ensemble configuration
            **kwargs: Additional parameters
        """
        self._agents = {agent.name: agent for agent in agents}

        # Determine universe
        if universe is None:
            universe = list(set(
                sym for agent in agents
                if hasattr(agent, "universe")
                for sym in agent.universe
            ))

        config = config or EnsembleConfig(name="ensemble_agent")
        super().__init__(universe=universe, config=config, **kwargs)

        self._ensemble_config: EnsembleConfig = config  # type: ignore

        # Initialize weights
        self._weights: dict[str, float] = {}
        for agent in agents:
            self._weights[agent.name] = config.agent_weights.get(
                agent.name, agent.config.weight if hasattr(agent.config, "weight") else 1.0
            )

        # Performance tracking
        self._performance: dict[str, AgentPerformance] = {
            agent.name: AgentPerformance(agent_name=agent.name)
            for agent in agents
        }

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_generate_signals=True,
            can_aggregate=True,
            supported_symbols=self.universe,
        )

    @property
    def agents(self) -> list[Agent]:
        """Get all agents in ensemble."""
        return list(self._agents.values())

    def add_agent(self, agent: Agent, weight: float = 1.0) -> None:
        """Add an agent to the ensemble."""
        self._agents[agent.name] = agent
        self._weights[agent.name] = weight
        self._performance[agent.name] = AgentPerformance(agent_name=agent.name)
        logger.info(f"Added agent to ensemble: {agent.name}")

    def remove_agent(self, name: str) -> None:
        """Remove an agent from the ensemble."""
        if name in self._agents:
            del self._agents[name]
            del self._weights[name]
            del self._performance[name]
            logger.info(f"Removed agent from ensemble: {name}")

    def set_weight(self, agent_name: str, weight: float) -> None:
        """Set weight for an agent."""
        if agent_name in self._weights:
            self._weights[agent_name] = weight

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate aggregated signals from all agents.

        Args:
            data: Market data
            timestamp: Current timestamp

        Returns:
            Aggregated signals
        """
        timestamp = timestamp or datetime.now()

        # Collect signals from all agents
        agent_signals = await self._collect_agent_signals(data, timestamp)

        # Aggregate by symbol
        aggregated_signals = []
        for symbol in self.universe:
            symbol_signals = self._get_symbol_signals(symbol, agent_signals)

            if len(symbol_signals) < self._ensemble_config.min_agents_required:
                continue

            signal = self._aggregate_signals(symbol, symbol_signals, timestamp)
            if signal is not None:
                aggregated_signals.append(signal)

        return aggregated_signals

    async def _collect_agent_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime,
    ) -> dict[str, list[Signal]]:
        """Collect signals from all agents concurrently."""
        results: dict[str, list[Signal]] = {}

        # Run agents concurrently
        tasks = []
        agent_names = []

        for name, agent in self._agents.items():
            if hasattr(agent, "generate_signals"):
                tasks.append(agent.run(data))
                agent_names.append(name)

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(agent_names, completed):
            if isinstance(result, Exception):
                logger.error(f"Agent {name} failed: {result}")
                results[name] = []
            else:
                results[name] = result

        return results

    def _get_symbol_signals(
        self,
        symbol: Symbol,
        agent_signals: dict[str, list[Signal]],
    ) -> list[tuple[str, Signal]]:
        """Get all signals for a symbol with agent names."""
        symbol_signals = []

        for agent_name, signals in agent_signals.items():
            for signal in signals:
                if signal.symbol == symbol:
                    symbol_signals.append((agent_name, signal))

        return symbol_signals

    def _aggregate_signals(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Aggregate signals for a symbol using configured method."""

        method = self._ensemble_config.aggregation_method

        if method == AggregationMethod.MEAN:
            return self._aggregate_mean(symbol, signals, timestamp)
        elif method == AggregationMethod.WEIGHTED_MEAN:
            return self._aggregate_weighted_mean(symbol, signals, timestamp)
        elif method == AggregationMethod.CONFIDENCE_WEIGHTED:
            return self._aggregate_confidence_weighted(symbol, signals, timestamp)
        elif method == AggregationMethod.VOTE:
            return self._aggregate_vote(symbol, signals, timestamp)
        elif method == AggregationMethod.WEIGHTED_VOTE:
            return self._aggregate_weighted_vote(symbol, signals, timestamp)
        elif method == AggregationMethod.MAX_CONFIDENCE:
            return self._aggregate_max_confidence(symbol, signals, timestamp)
        elif method == AggregationMethod.CONSENSUS:
            return self._aggregate_consensus(symbol, signals, timestamp)
        else:
            return self._aggregate_confidence_weighted(symbol, signals, timestamp)

    def _aggregate_mean(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Simple mean of signal strengths."""
        if not signals:
            return None

        strengths = [s.strength for _, s in signals]
        confidences = [s.confidence for _, s in signals]

        mean_strength = sum(strengths) / len(strengths)
        mean_confidence = sum(confidences) / len(confidences)

        return self._create_aggregated_signal(
            symbol, mean_strength, mean_confidence, signals, timestamp
        )

    def _aggregate_weighted_mean(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Weighted mean using agent weights."""
        if not signals:
            return None

        total_weight = sum(self._weights.get(name, 1.0) for name, _ in signals)
        if total_weight == 0:
            return None

        weighted_strength = sum(
            s.strength * self._weights.get(name, 1.0)
            for name, s in signals
        ) / total_weight

        weighted_confidence = sum(
            s.confidence * self._weights.get(name, 1.0)
            for name, s in signals
        ) / total_weight

        return self._create_aggregated_signal(
            symbol, weighted_strength, weighted_confidence, signals, timestamp
        )

    def _aggregate_confidence_weighted(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Weight by signal confidence."""
        if not signals:
            return None

        total_confidence = sum(s.confidence for _, s in signals)
        if total_confidence == 0:
            return None

        weighted_strength = sum(
            s.strength * s.confidence for _, s in signals
        ) / total_confidence

        # Average confidence, weighted by agent weight
        total_weight = sum(self._weights.get(name, 1.0) for name, _ in signals)
        if total_weight > 0:
            avg_confidence = sum(
                s.confidence * self._weights.get(name, 1.0)
                for name, s in signals
            ) / total_weight
        else:
            avg_confidence = sum(s.confidence for _, s in signals) / len(signals)

        return self._create_aggregated_signal(
            symbol, weighted_strength, avg_confidence, signals, timestamp
        )

    def _aggregate_vote(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Majority voting."""
        if not signals:
            return None

        long_votes = sum(1 for _, s in signals if s.direction == Direction.LONG)
        short_votes = sum(1 for _, s in signals if s.direction == Direction.SHORT)
        total = len(signals)

        # Check minimum agreement
        max_votes = max(long_votes, short_votes)
        if max_votes / total < self._ensemble_config.min_agreement:
            return None

        if long_votes > short_votes:
            strength = long_votes / total
            direction = Direction.LONG
        elif short_votes > long_votes:
            strength = -short_votes / total
            direction = Direction.SHORT
        else:
            # Handle tie
            return self._handle_conflict(symbol, signals, timestamp)

        confidence = max_votes / total

        return self._create_aggregated_signal(
            symbol, strength, confidence, signals, timestamp, direction=direction
        )

    def _aggregate_weighted_vote(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Weighted majority voting."""
        if not signals:
            return None

        long_weight = sum(
            self._weights.get(name, 1.0)
            for name, s in signals
            if s.direction == Direction.LONG
        )
        short_weight = sum(
            self._weights.get(name, 1.0)
            for name, s in signals
            if s.direction == Direction.SHORT
        )
        total_weight = long_weight + short_weight

        if total_weight == 0:
            return None

        if long_weight > short_weight:
            strength = long_weight / total_weight
            confidence = strength
            direction = Direction.LONG
        elif short_weight > long_weight:
            strength = -short_weight / total_weight
            confidence = -strength
            direction = Direction.SHORT
        else:
            return self._handle_conflict(symbol, signals, timestamp)

        return self._create_aggregated_signal(
            symbol, strength, confidence, signals, timestamp, direction=direction
        )

    def _aggregate_max_confidence(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Take signal with highest confidence."""
        if not signals:
            return None

        best_name, best_signal = max(signals, key=lambda x: x[1].confidence)

        return self._create_aggregated_signal(
            symbol,
            best_signal.strength,
            best_signal.confidence,
            signals,
            timestamp,
            direction=best_signal.direction,
        )

    def _aggregate_consensus(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Only signal if all agents agree on direction."""
        if not signals:
            return None

        directions = set(s.direction for _, s in signals)
        if len(directions) > 1:
            return None  # No consensus

        direction = directions.pop()
        strengths = [s.strength for _, s in signals]
        confidences = [s.confidence for _, s in signals]

        return self._create_aggregated_signal(
            symbol,
            sum(strengths) / len(strengths),
            sum(confidences) / len(confidences),
            signals,
            timestamp,
            direction=direction,
        )

    def _handle_conflict(
        self,
        symbol: Symbol,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
    ) -> Signal | None:
        """Handle conflicting signals."""
        resolution = self._ensemble_config.conflict_resolution

        if resolution == ConflictResolution.IGNORE:
            logger.debug(f"Conflict for {symbol}, ignoring")
            return None

        elif resolution == ConflictResolution.MAJORITY:
            # Already tried in vote, fall back to weighted
            return self._aggregate_weighted_mean(symbol, signals, timestamp)

        elif resolution == ConflictResolution.WEIGHTED:
            return self._aggregate_weighted_mean(symbol, signals, timestamp)

        elif resolution == ConflictResolution.ABSTAIN:
            logger.info(f"Conflict for {symbol}, abstaining")
            # Send conflict notification
            asyncio.create_task(self.send_message(AgentMessage(
                message_type=MessageType.ALERT,
                payload={
                    "type": "conflict",
                    "symbol": symbol,
                    "agents": [name for name, _ in signals],
                },
            )))
            return None

        return None

    def _create_aggregated_signal(
        self,
        symbol: Symbol,
        strength: float,
        confidence: float,
        signals: list[tuple[str, Signal]],
        timestamp: datetime,
        direction: Direction | None = None,
    ) -> Signal | None:
        """Create the aggregated signal."""

        # Check minimum confidence
        if confidence < self._ensemble_config.min_combined_confidence:
            return None

        # Determine direction from strength if not provided
        if direction is None:
            if strength > 0:
                direction = Direction.LONG
            elif strength < 0:
                direction = Direction.SHORT
            else:
                return None

        signal_type = (
            SignalType.ENTRY_LONG if direction == Direction.LONG
            else SignalType.ENTRY_SHORT
        )

        # Clamp values
        strength = max(-1.0, min(1.0, strength))
        confidence = max(0.0, min(1.0, confidence))

        return self.create_signal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            signal_type=signal_type,
            metadata={
                "aggregation_method": self._ensemble_config.aggregation_method.value,
                "n_agents": len(signals),
                "agent_signals": {
                    name: {"strength": s.strength, "confidence": s.confidence}
                    for name, s in signals
                },
            },
        )

    def update_performance(
        self,
        agent_name: str,
        signal: Signal,
        actual_return: float,
    ) -> None:
        """
        Update agent performance tracking.

        Args:
            agent_name: Name of the agent
            signal: Signal that was generated
            actual_return: Actual return after signal
        """
        if agent_name not in self._performance:
            return

        perf = self._performance[agent_name]
        perf.signal_count += 1
        perf.total_return += actual_return

        # Check if signal was correct
        correct = (signal.strength > 0 and actual_return > 0) or \
                  (signal.strength < 0 and actual_return < 0)
        if correct:
            perf.correct_signals += 1

        # Track recent signals
        perf.recent_signals.append({
            "timestamp": signal.timestamp.isoformat(),
            "strength": signal.strength,
            "return": actual_return,
        })

        # Keep only recent history
        window = self._ensemble_config.performance_window
        if len(perf.recent_signals) > window:
            perf.recent_signals = perf.recent_signals[-window:]

    def get_agent_performance(self) -> dict[str, dict[str, float]]:
        """Get performance metrics for all agents."""
        return {
            name: {
                "accuracy": perf.accuracy,
                "signal_count": perf.signal_count,
                "total_return": perf.total_return,
                "ic": perf.information_coefficient,
            }
            for name, perf in self._performance.items()
        }

    def adapt_weights_from_performance(self) -> None:
        """Adapt agent weights based on performance."""
        for name, perf in self._performance.items():
            if perf.signal_count < 10:
                continue  # Not enough data

            # Weight by accuracy and IC
            accuracy_weight = perf.accuracy
            ic_weight = (perf.information_coefficient + 1) / 2  # Normalize to 0-1

            # Combined weight
            new_weight = 0.5 * accuracy_weight + 0.5 * ic_weight

            # Smooth update
            current = self._weights.get(name, 1.0)
            self._weights[name] = 0.8 * current + 0.2 * new_weight

        logger.info(f"Updated weights: {self._weights}")


class HierarchicalEnsemble(EnsembleAgent):
    """
    Hierarchical ensemble with multiple layers of aggregation.

    First layer: Groups of agents (e.g., by strategy type)
    Second layer: Aggregation of group signals
    """

    name: str = "hierarchical_ensemble"
    description: str = "Multi-layer hierarchical signal aggregation"

    def __init__(
        self,
        agent_groups: dict[str, list[Agent]],
        group_weights: dict[str, float] | None = None,
        universe: list[Symbol] | None = None,
        config: EnsembleConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize hierarchical ensemble.

        Args:
            agent_groups: Dict mapping group names to lists of agents
            group_weights: Weights for each group
            universe: List of symbols
            config: Ensemble configuration
            **kwargs: Additional parameters
        """
        self._agent_groups = agent_groups
        self._group_weights = group_weights or {name: 1.0 for name in agent_groups}

        # Flatten agents for parent class
        all_agents = [
            agent for agents in agent_groups.values()
            for agent in agents
        ]

        super().__init__(agents=all_agents, universe=universe, config=config, **kwargs)

        # Create sub-ensembles for each group
        self._group_ensembles: dict[str, EnsembleAgent] = {}
        for group_name, agents in agent_groups.items():
            group_config = EnsembleConfig(
                name=f"{group_name}_ensemble",
                aggregation_method=self._ensemble_config.aggregation_method,
            )
            self._group_ensembles[group_name] = EnsembleAgent(
                agents=agents,
                universe=self.universe,
                config=group_config,
            )

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """Generate hierarchically aggregated signals."""
        timestamp = timestamp or datetime.now()

        # First layer: Get signals from each group
        group_signals: dict[str, list[Signal]] = {}

        for group_name, ensemble in self._group_ensembles.items():
            signals = await ensemble.generate_signals(data, timestamp)
            group_signals[group_name] = signals

        # Second layer: Aggregate group signals
        aggregated_signals = []

        for symbol in self.universe:
            symbol_group_signals = []

            for group_name, signals in group_signals.items():
                for signal in signals:
                    if signal.symbol == symbol:
                        # Weight signal by group weight
                        weighted_signal = Signal(
                            timestamp=signal.timestamp,
                            symbol=signal.symbol,
                            direction=signal.direction,
                            strength=signal.strength * self._group_weights.get(group_name, 1.0),
                            confidence=signal.confidence,
                            signal_type=signal.signal_type,
                            strategy_name=group_name,
                            metadata=signal.metadata,
                        )
                        symbol_group_signals.append((group_name, weighted_signal))

            if symbol_group_signals:
                final_signal = self._aggregate_signals(
                    symbol, symbol_group_signals, timestamp
                )
                if final_signal is not None:
                    aggregated_signals.append(final_signal)

        return aggregated_signals


# Factory function
def create_ensemble(
    agents: list[Agent],
    method: AggregationMethod = AggregationMethod.CONFIDENCE_WEIGHTED,
    weights: dict[str, float] | None = None,
    **kwargs: Any,
) -> EnsembleAgent:
    """
    Convenience function to create an ensemble agent.

    Args:
        agents: List of agents to include
        method: Aggregation method
        weights: Optional agent weights
        **kwargs: Additional configuration

    Returns:
        Configured EnsembleAgent
    """
    config = EnsembleConfig(
        name="ensemble",
        role=AgentRole.ENSEMBLE,
        aggregation_method=method,
        agent_weights=weights or {},
        **{k: v for k, v in kwargs.items() if k in EnsembleConfig.__dataclass_fields__},
    )

    return EnsembleAgent(agents=agents, config=config)
