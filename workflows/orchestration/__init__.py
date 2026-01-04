"""
Orchestration Module for Multi-Agent Quant Research.

Provides parallel agent execution, result aggregation, and
research cycle management for dual-track research workflows.
"""

from .parallel_executor import (
    AgentTask,
    AgentResult,
    AgentType,
    TaskStatus,
    ParallelAgentExecutor,
    DualTrackExecutor,
    create_semiconductor_research_tasks,
    create_full_research_tasks,
)

from .result_aggregator import (
    ConsolidatedReport,
    StrategyFinding,
    NovelPattern,
    RegimeAssessment,
    FindingPriority,
    ResearchResultAggregator,
)

from .research_cycle import (
    CycleConfig,
    CycleReport,
    CycleStatus,
    ResearchFocus,
    ResearchCycleManager,
    quick_semiconductor_cycle,
    quick_tech_cycle,
    full_research_cycle,
)

__all__ = [
    # Parallel Execution
    "AgentTask",
    "AgentResult",
    "AgentType",
    "TaskStatus",
    "ParallelAgentExecutor",
    "DualTrackExecutor",
    "create_semiconductor_research_tasks",
    "create_full_research_tasks",
    # Result Aggregation
    "ConsolidatedReport",
    "StrategyFinding",
    "NovelPattern",
    "RegimeAssessment",
    "FindingPriority",
    "ResearchResultAggregator",
    # Research Cycles
    "CycleConfig",
    "CycleReport",
    "CycleStatus",
    "ResearchFocus",
    "ResearchCycleManager",
    "quick_semiconductor_cycle",
    "quick_tech_cycle",
    "full_research_cycle",
]
