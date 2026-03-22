"""Agent System for the Quant Suite.

Provides LLM agents for market analysis and signal generation.

Note: base.py, ensemble.py, strategy_agent.py, data_scout.py, and tools/
were archived to _archive/agents_legacy/ as they were superseded by
Claude Code's built-in Agent tool and .claude/agents/*.md definitions.
"""

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

__all__ = [
    "LLMModel",
    "AnalysisType",
    "LLMAgentConfig",
    "ClaudeClient",
    "LLMAnalystAgent",
    "LLMSignalAgent",
    "LLMNewsAnalystAgent",
    "create_llm_agent",
]
