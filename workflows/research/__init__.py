"""
Autonomous Quantitative Research System.

This module provides a fully autonomous research pipeline that:
1. Generates trading strategy hypotheses
2. Fetches data from multiple free sources
3. Runs MCPT validation experiments
4. Accumulates knowledge across sessions
5. Produces actionable insights

Quick Start:
    from workflows.research import run_autonomous_research

    # Run for 2 hours
    report = await run_autonomous_research(
        symbols=["AAPL", "NVDA", "AMZN", "QQQ", "SPY"],
        hours=2.0
    )
    print(f"Results: {report.session_path}")

Components:
    - DataHub: Unified data fetching with caching
    - KnowledgeBase: Persistent learning storage
    - HypothesisEngine: Strategy idea generation
    - ExperimentRunner: MCPT validation
    - AutonomousResearcher: Main orchestrator
"""

from .autonomous_loop import (
    AutonomousResearcher,
    CycleReport,
    ResearchReport,
    run_autonomous_research,
    run_research_sync,
    DEFAULT_UNIVERSE,
)
from .data_hub import (
    DataBundle,
    DataHub,
    EconomicRegime,
    InsiderSignal,
    InsiderTransaction,
    SentimentScore,
)
from .experiment_runner import (
    ExperimentResult,
    ExperimentRunner,
    StrategyExecutor,
)
from .hypothesis_engine import (
    Hypothesis,
    HypothesisEngine,
    STRATEGY_TEMPLATES,
)
from .knowledge_base import (
    Insight,
    KnowledgeBase,
    Pattern,
    StrategyResult,
)
from .experiment_schema import (
    ExperimentDefinition,
    ExperimentRegistry,
    ExperimentStatus,
    MethodologyConfig,
    ResultsSummary,
    SignificanceLevel,
    create_momentum_experiment,
    create_sentiment_experiment,
    create_alternative_data_experiment,
)
from .agent_interface import (
    ResearchKnowledgeBase,
    ExperimentProposal,
    FeatureStats,
    ResearchSummary,
)
from .research_protocol import (
    ResearchProtocol,
    ResearchPhase,
    ResearchFocus,
    ResearchHypothesis,
    ResearchInsight,
    ResearchSession,
    quick_research_prompt,
)
from .session_tracker import (
    ResearchSessionTracker,
    TrackedInsight,
    ExperimentRecord,
    get_tracker,
)

__all__ = [
    # Main entry points
    "run_autonomous_research",
    "run_research_sync",
    "AutonomousResearcher",
    # Data
    "DataHub",
    "DataBundle",
    "InsiderTransaction",
    "InsiderSignal",
    "EconomicRegime",
    "SentimentScore",
    # Knowledge
    "KnowledgeBase",
    "Insight",
    "Pattern",
    "StrategyResult",
    # Hypotheses
    "HypothesisEngine",
    "Hypothesis",
    "STRATEGY_TEMPLATES",
    # Experiments
    "ExperimentRunner",
    "ExperimentResult",
    "StrategyExecutor",
    # Reports
    "ResearchReport",
    "CycleReport",
    # Constants
    "DEFAULT_UNIVERSE",
    # Experiment Schema
    "ExperimentDefinition",
    "ExperimentRegistry",
    "ExperimentStatus",
    "MethodologyConfig",
    "ResultsSummary",
    "SignificanceLevel",
    "create_momentum_experiment",
    "create_sentiment_experiment",
    "create_alternative_data_experiment",
    # Agent Interface
    "ResearchKnowledgeBase",
    "ExperimentProposal",
    "FeatureStats",
    "ResearchSummary",
    # Research Protocol
    "ResearchProtocol",
    "ResearchPhase",
    "ResearchFocus",
    "ResearchHypothesis",
    "ResearchInsight",
    "ResearchSession",
    "quick_research_prompt",
    # Session Tracker
    "ResearchSessionTracker",
    "TrackedInsight",
    "ExperimentRecord",
    "get_tracker",
]

__version__ = "0.1.0"
