"""
Data Synthesis Module

Tools for extracting and synthesizing insights from text:
- LLM-powered insight extraction
- Rule-based pattern matching
- Research idea generation
- Insight tracking and validation
"""

from .llm_extractor import (
    LLMExtractor,
    RuleBasedExtractor,
    InsightTracker,
    ExtractedInsight,
    ResearchIdea,
    SignalType,
    Direction,
    extract_from_text,
    generate_ideas_from_article,
)

__all__ = [
    "LLMExtractor",
    "RuleBasedExtractor",
    "InsightTracker",
    "ExtractedInsight",
    "ResearchIdea",
    "SignalType",
    "Direction",
    "extract_from_text",
    "generate_ideas_from_article",
]
