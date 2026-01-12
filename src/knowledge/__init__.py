"""Knowledge Layer - Persistent Understanding.

Provides:
- Thesis tracking with signposts and conviction history
- Learning log from trade outcomes
- Knowledge base for company/sector understanding

Usage:
    from src.knowledge import ThesisTracker, LearningLog, KnowledgeBase

    # Track a thesis
    tracker = ThesisTracker()
    thesis = tracker.create_thesis(
        name="Venezuela Energy Recovery",
        summary="Sanctions relief drives oilfield services rally",
        ...
    )

    # Record a learning
    log = LearningLog()
    log.add_learning(Learning(
        decision_id="abc123",
        symbol="SLB",
        what_i_learned="Gap fades >50% often indicate thesis re-evaluation needed",
        ...
    ))

    # Access persistent knowledge
    kb = KnowledgeBase()
    slb_brief = kb.get_company("SLB")
"""

from .thesis import Thesis, Signpost, ThesisTracker, ThesisSummary
from .learnings import Learning, LearningLog, LearningSummary
from .base import CompanyBrief, SectorContext, KnowledgeBase
from .thesis_performance import (
    ThesisPerformanceMetrics,
    ThesisPerformanceTracker,
    PositionPerformance,
    get_thesis_performance_summary,
)

__all__ = [
    # Thesis
    "Thesis",
    "Signpost",
    "ThesisTracker",
    "ThesisSummary",
    # Thesis Performance
    "ThesisPerformanceMetrics",
    "ThesisPerformanceTracker",
    "PositionPerformance",
    "get_thesis_performance_summary",
    # Learnings
    "Learning",
    "LearningLog",
    "LearningSummary",
    # Knowledge Base
    "CompanyBrief",
    "SectorContext",
    "KnowledgeBase",
]
