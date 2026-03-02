"""Compounding Intelligence Loop — closes the feedback loop.

Makes predictions explicit, tracks accuracy, builds decision context
from track record, and updates beliefs based on outcomes.

Key components:
    DecisionContextBuilder  — assembles full context for trade decisions
    SetupScorer            — tracks performance by setup type
    BeliefUpdater          — daily belief update after prediction scoring
"""

from src.intelligence.context_builder import DecisionContextBuilder, DecisionContext
from src.intelligence.setup_types import SETUP_TYPES, REASONING_CATEGORIES
from src.intelligence.setup_scorer import SetupScorer

__all__ = [
    "DecisionContextBuilder",
    "DecisionContext",
    "SetupScorer",
    "SETUP_TYPES",
    "REASONING_CATEGORIES",
]
