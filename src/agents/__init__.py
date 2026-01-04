"""Agent System for the Quant Suite.

Provides a multi-agent framework for trading:
- Strategy agents that wrap traditional and ML strategies
- LLM agents for market analysis and signal generation
- Ensemble agents for signal aggregation
- Data scout agents for alternative data discovery

Agents communicate through signals and messages, and can be composed
hierarchically for complex trading systems.
"""

from .base import (
    Agent,
    AgentCapabilities,
    AgentConfig,
    AgentFactory,
    AgentMessage,
    AgentRole,
    AgentState,
    AgentStatus,
    AnalystAgent,
    CoordinatorAgent,
    MessageType,
    SignalGeneratorAgent,
    create_agent,
)
from .data_scout import (
    ApprovalStatus,
    DataScoutAgent,
    DataSourceProposal,
    DataSourceType,
    ScoutConfig,
)
from .ensemble import (
    AggregationMethod,
    AgentPerformance,
    ConflictResolution,
    EnsembleAgent,
    EnsembleConfig,
    HierarchicalEnsemble,
    create_ensemble,
)
from .llm_agent import (
    AnalysisType,
    ClaudeClient,
    LLMAgentConfig,
    LLMAnalystAgent,
    LLMModel,
    LLMNewsAnalystAgent,
    LLMSignalAgent,
    create_llm_agent,
)
from .strategy_agent import (
    AdaptiveStrategyAgent,
    MultiStrategyAgent,
    StrategyAgent,
    StrategyAgentConfig,
    create_strategy_agent,
    wrap_strategy,
)

__all__ = [
    # Base classes
    "Agent",
    "AgentConfig",
    "AgentCapabilities",
    "AgentState",
    "AgentStatus",
    "AgentRole",
    "AgentMessage",
    "MessageType",
    "SignalGeneratorAgent",
    "AnalystAgent",
    "CoordinatorAgent",
    "AgentFactory",
    "create_agent",
    # Strategy agents
    "StrategyAgent",
    "StrategyAgentConfig",
    "MultiStrategyAgent",
    "AdaptiveStrategyAgent",
    "wrap_strategy",
    "create_strategy_agent",
    # LLM agents
    "LLMModel",
    "AnalysisType",
    "LLMAgentConfig",
    "ClaudeClient",
    "LLMAnalystAgent",
    "LLMSignalAgent",
    "LLMNewsAnalystAgent",
    "create_llm_agent",
    # Ensemble agents
    "AggregationMethod",
    "ConflictResolution",
    "EnsembleConfig",
    "EnsembleAgent",
    "HierarchicalEnsemble",
    "AgentPerformance",
    "create_ensemble",
    # Data scout
    "DataSourceType",
    "ApprovalStatus",
    "DataSourceProposal",
    "ScoutConfig",
    "DataScoutAgent",
]
