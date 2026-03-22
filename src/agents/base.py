"""Base agent classes and types for the agent system.

# DEPRECATED: superseded by scheduler/swarm/session path
# This module is kept only because llm_agent.py inherits from these classes,
# and llm_agent.py is still imported by src/web/services/research_service.py.
# New agent work should use Claude Code's built-in Agent tool and
# .claude/agents/*.md definitions instead.

The agent system provides a unified interface for:
- Traditional trading strategies wrapped as agents
- LLM-powered analysis agents
- Ensemble agents that combine multiple signal sources
- Data scout agents for autonomous discovery

Agents communicate through signals and can be composed hierarchically.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

import pandas as pd

from ..core import Direction, Signal, SignalBundle, SignalType, Symbol

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent operational status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class AgentRole(str, Enum):
    """Agent role in the system."""

    SIGNAL_GENERATOR = "signal_generator"  # Generates trading signals
    ANALYST = "analyst"  # Provides analysis/insights
    DATA_SCOUT = "data_scout"  # Discovers data sources
    RISK_MONITOR = "risk_monitor"  # Monitors risk metrics
    COORDINATOR = "coordinator"  # Coordinates other agents
    ENSEMBLE = "ensemble"  # Aggregates signals from multiple agents


class MessageType(str, Enum):
    """Types of messages between agents."""

    SIGNAL = "signal"
    ANALYSIS = "analysis"
    DATA = "data"
    ALERT = "alert"
    QUERY = "query"
    RESPONSE = "response"
    HEARTBEAT = "heartbeat"


@dataclass
class AgentMessage:
    """Message passed between agents."""

    message_id: str = field(default_factory=lambda: str(uuid4()))
    message_type: MessageType = MessageType.SIGNAL
    sender: str = ""
    recipient: str = ""  # Empty = broadcast
    timestamp: datetime = field(default_factory=datetime.now)
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher = more important
    requires_response: bool = False
    correlation_id: str = ""  # For request-response patterns

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "priority": self.priority,
            "requires_response": self.requires_response,
            "correlation_id": self.correlation_id,
        }


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    name: str
    role: AgentRole
    enabled: bool = True
    priority: int = 1  # For signal aggregation
    weight: float = 1.0  # For weighted voting
    parameters: dict[str, Any] = field(default_factory=dict)

    # Rate limiting
    min_interval_seconds: float = 0.0  # Minimum time between runs
    max_signals_per_run: int = 100  # Max signals per execution

    # Timeouts
    timeout_seconds: float = 30.0

    # Callbacks
    on_signal: Callable[[Signal], None] | None = None
    on_error: Callable[[Exception], None] | None = None


@dataclass
class AgentState:
    """Runtime state for an agent."""

    status: AgentStatus = AgentStatus.IDLE
    last_run: datetime | None = None
    last_error: str | None = None
    signals_generated: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    run_count: int = 0
    error_count: int = 0

    def record_run(self) -> None:
        """Record a successful run."""
        self.last_run = datetime.now()
        self.run_count += 1

    def record_error(self, error: str) -> None:
        """Record an error."""
        self.last_error = error
        self.error_count += 1
        self.status = AgentStatus.ERROR


@dataclass
class AgentCapabilities:
    """Capabilities that an agent supports."""

    can_generate_signals: bool = False
    can_analyze: bool = False
    can_discover_data: bool = False
    can_aggregate: bool = False
    requires_approval: bool = False
    supports_async: bool = True
    supports_streaming: bool = False

    # Supported symbols/markets
    supported_symbols: list[Symbol] | None = None  # None = all
    supported_timeframes: list[str] | None = None

    # Data requirements
    required_data: list[str] = field(default_factory=list)
    optional_data: list[str] = field(default_factory=list)


class Agent(ABC):
    """
    Abstract base class for all agents.

    Agents are autonomous components that can:
    - Generate trading signals
    - Analyze market data
    - Discover new data sources
    - Coordinate with other agents

    Communication happens through a message bus or direct method calls.
    """

    name: str = "base_agent"
    description: str = ""
    version: str = "1.0.0"

    def __init__(
        self,
        config: AgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize agent.

        Args:
            config: Agent configuration
            **kwargs: Additional parameters
        """
        self.config = config or AgentConfig(name=self.name, role=AgentRole.SIGNAL_GENERATOR)
        self.state = AgentState()
        self._capabilities = self._define_capabilities()
        self._message_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._subscribers: list[Callable[[AgentMessage], None]] = []

    @abstractmethod
    def _define_capabilities(self) -> AgentCapabilities:
        """Define agent capabilities. Override in subclasses."""
        ...

    @property
    def capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        return self._capabilities

    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self.state.status == AgentStatus.RUNNING

    @abstractmethod
    async def run(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """
        Execute the agent's main logic.

        Args:
            data: Market data (optional, depending on agent type)
            context: Additional context information

        Returns:
            List of signals generated
        """
        ...

    async def start(self) -> None:
        """Start the agent."""
        if self.state.status == AgentStatus.RUNNING:
            logger.warning(f"Agent {self.name} already running")
            return

        self.state.status = AgentStatus.RUNNING
        logger.info(f"Agent {self.name} started")

    async def stop(self) -> None:
        """Stop the agent."""
        self.state.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.name} stopped")

    async def pause(self) -> None:
        """Pause the agent."""
        self.state.status = AgentStatus.PAUSED
        logger.info(f"Agent {self.name} paused")

    async def resume(self) -> None:
        """Resume the agent."""
        if self.state.status == AgentStatus.PAUSED:
            self.state.status = AgentStatus.RUNNING
            logger.info(f"Agent {self.name} resumed")

    def subscribe(self, callback: Callable[[AgentMessage], None]) -> None:
        """Subscribe to agent messages."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[AgentMessage], None]) -> None:
        """Unsubscribe from agent messages."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def send_message(self, message: AgentMessage) -> None:
        """Send a message to subscribers."""
        message.sender = self.name
        self.state.messages_sent += 1

        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

    async def receive_message(self, message: AgentMessage) -> AgentMessage | None:
        """
        Receive and process a message.

        Args:
            message: Incoming message

        Returns:
            Response message if required, None otherwise
        """
        self.state.messages_received += 1

        if message.requires_response:
            return await self._handle_message(message)

        # Fire and forget
        asyncio.create_task(self._handle_message(message))
        return None

    async def _handle_message(self, message: AgentMessage) -> AgentMessage | None:
        """Handle incoming message. Override for custom handling."""
        logger.debug(f"Agent {self.name} received message: {message.message_type}")
        return None

    def create_signal(
        self,
        symbol: Symbol,
        direction: Direction,
        strength: float,
        confidence: float = 0.5,
        signal_type: SignalType = SignalType.ENTRY_LONG,
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """
        Create a signal with agent name attached.

        Args:
            symbol: Asset symbol
            direction: Signal direction
            strength: Signal strength (-1 to 1)
            confidence: Confidence level (0 to 1)
            signal_type: Type of signal
            metadata: Additional metadata

        Returns:
            Signal object
        """
        self.state.signals_generated += 1

        return Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            signal_type=signal_type,
            strategy_name=self.name,
            metadata=metadata or {},
        )

    def get_state(self) -> dict[str, Any]:
        """Get agent state as dictionary."""
        return {
            "name": self.name,
            "status": self.state.status.value,
            "last_run": self.state.last_run.isoformat() if self.state.last_run else None,
            "signals_generated": self.state.signals_generated,
            "run_count": self.state.run_count,
            "error_count": self.state.error_count,
            "last_error": self.state.last_error,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, status={self.state.status.value})"


class SignalGeneratorAgent(Agent):
    """
    Base class for agents that generate trading signals.

    This is the most common agent type - wraps strategies, ML models,
    or LLM analysis to produce signals.
    """

    def __init__(
        self,
        universe: list[Symbol],
        config: AgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize signal generator agent.

        Args:
            universe: List of symbols to generate signals for
            config: Agent configuration
            **kwargs: Additional parameters
        """
        # Set universe BEFORE calling super().__init__ since _define_capabilities needs it
        self.universe = universe
        super().__init__(config=config, **kwargs)

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_generate_signals=True,
            supported_symbols=self.universe if hasattr(self, "universe") else None,
        )

    @abstractmethod
    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate trading signals from data.

        Args:
            data: Market data
            timestamp: Current timestamp

        Returns:
            List of signals
        """
        ...

    async def run(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """Execute signal generation."""
        if data is None:
            logger.warning(f"Agent {self.name}: No data provided")
            return []

        try:
            self.state.status = AgentStatus.RUNNING
            signals = await self.generate_signals(data)
            self.state.record_run()

            # Notify subscribers
            if signals:
                await self.send_message(AgentMessage(
                    message_type=MessageType.SIGNAL,
                    payload={"signals": [s.to_dict() for s in signals]},
                ))

            return signals

        except Exception as e:
            self.state.record_error(str(e))
            logger.error(f"Agent {self.name} error: {e}")

            if self.config.on_error:
                self.config.on_error(e)

            return []

        finally:
            self.state.status = AgentStatus.IDLE


class AnalystAgent(Agent):
    """
    Base class for agents that provide analysis without direct signals.

    Analyst agents examine data, produce insights, and may influence
    other agents' decisions through advisory messages.
    """

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_analyze=True,
            can_generate_signals=False,
        )

    @abstractmethod
    async def analyze(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        query: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze data and return insights.

        Args:
            data: Market data to analyze
            query: Optional specific question to answer

        Returns:
            Analysis results
        """
        ...

    async def run(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """Execute analysis (returns empty signals)."""
        if data is None:
            return []

        try:
            query = context.get("query") if context else None
            analysis = await self.analyze(data, query)

            # Send analysis as message
            await self.send_message(AgentMessage(
                message_type=MessageType.ANALYSIS,
                payload={"analysis": analysis},
            ))

            self.state.record_run()

        except Exception as e:
            self.state.record_error(str(e))
            logger.error(f"Agent {self.name} error: {e}")

        return []  # Analyst agents don't generate signals directly


class CoordinatorAgent(Agent):
    """
    Base class for agents that coordinate other agents.

    Coordinators manage agent lifecycles, route messages,
    and orchestrate multi-agent workflows.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        **kwargs: Any,
    ):
        super().__init__(config=config, **kwargs)
        self._managed_agents: dict[str, Agent] = {}

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_aggregate=True,
        )

    def register_agent(self, agent: Agent) -> None:
        """Register an agent to be managed."""
        self._managed_agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")

    def unregister_agent(self, name: str) -> None:
        """Unregister a managed agent."""
        if name in self._managed_agents:
            del self._managed_agents[name]
            logger.info(f"Unregistered agent: {name}")

    def get_agent(self, name: str) -> Agent | None:
        """Get a managed agent by name."""
        return self._managed_agents.get(name)

    @property
    def agents(self) -> list[Agent]:
        """Get all managed agents."""
        return list(self._managed_agents.values())

    async def run_all(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, list[Signal]]:
        """
        Run all managed agents.

        Args:
            data: Market data
            context: Additional context

        Returns:
            Dict mapping agent names to their signals
        """
        results = {}

        # Run agents concurrently
        tasks = []
        for agent in self._managed_agents.values():
            if agent.config.enabled:
                tasks.append(self._run_agent(agent, data, context))

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for agent, result in zip(self._managed_agents.values(), completed):
            if isinstance(result, Exception):
                logger.error(f"Agent {agent.name} failed: {result}")
                results[agent.name] = []
            else:
                results[agent.name] = result

        return results

    async def _run_agent(
        self,
        agent: Agent,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None,
        context: dict[str, Any] | None,
    ) -> list[Signal]:
        """Run a single agent with timeout."""
        try:
            return await asyncio.wait_for(
                agent.run(data, context),
                timeout=agent.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(f"Agent {agent.name} timed out")
            return []

    async def run(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """Run coordinator (runs all managed agents)."""
        results = await self.run_all(data, context)

        # Flatten all signals
        all_signals = []
        for signals in results.values():
            all_signals.extend(signals)

        self.state.record_run()
        return all_signals


# Type alias for agent factory functions
AgentFactory = Callable[[AgentConfig], Agent]


def create_agent(
    agent_type: str,
    config: AgentConfig,
    registry: dict[str, AgentFactory] | None = None,
) -> Agent:
    """
    Factory function to create agents.

    Args:
        agent_type: Type of agent to create
        config: Agent configuration
        registry: Optional custom registry of agent factories

    Returns:
        Instantiated agent
    """
    # Default registry - will be populated by submodules
    default_registry: dict[str, AgentFactory] = {}

    registry = registry or default_registry

    if agent_type not in registry:
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available: {list(registry.keys())}"
        )

    return registry[agent_type](config)
