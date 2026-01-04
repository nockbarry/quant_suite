"""
Quant Suite Subagents.

Specialized agents for autonomous quant research and trading operations.

Agent Types:
- ResearchAgent: Comprehensive strategy research and testing
- CriticAgent: Safety validation and bias detection
- MonitorAgent: Portfolio and trading oversight
- BrainstormAgent: Feature and strategy ideation
- OrchestratorAgent: Coordinates multi-agent workflows
"""

from .base import AgentConfig, AgentResult
from .research import ResearchAgent
from .critic import CriticAgent
from .monitor import MonitorAgent
from .brainstorm import BrainstormAgent
from .orchestrator import OrchestratorAgent

__all__ = [
    "AgentConfig",
    "AgentResult",
    "ResearchAgent",
    "CriticAgent",
    "MonitorAgent",
    "BrainstormAgent",
    "OrchestratorAgent",
]
