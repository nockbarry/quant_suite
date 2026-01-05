"""
Autonomous Alpha Discovery Workflows

This module contains orchestrators and workflows for autonomous
alpha discovery, testing, and promotion.

Usage:
    from workflows.autonomous import AlphaHuntOrchestrator

    orchestrator = AlphaHuntOrchestrator()
    result = await orchestrator.run_cycle(focus='commodities')
"""

from .alpha_hunt_orchestrator import (
    AlphaHuntOrchestrator,
    Hypothesis,
    TestResult,
    CycleResult,
    MarketScanner,
    DataScout,
    KnowledgeQuerier,
    HypothesisGenerator,
    HypothesisTester,
    CriticValidator,
)

__all__ = [
    "AlphaHuntOrchestrator",
    "Hypothesis",
    "TestResult",
    "CycleResult",
    "MarketScanner",
    "DataScout",
    "KnowledgeQuerier",
    "HypothesisGenerator",
    "HypothesisTester",
    "CriticValidator",
]
