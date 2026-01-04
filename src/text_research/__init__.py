"""
Text Research Framework for Quantitative Alpha Discovery.

This module provides a comprehensive system for text-based alpha research:
- Point-in-time safe text corpus storage
- Multi-model embedding engine
- Text feature extraction and registration
- Text-aware backtesting with proper temporal alignment
- Online learning for daily updates

Key Design Principles:
- No lookahead bias: All operations respect point-in-time constraints
- signal_delay=1: Same-day text generates next-day trading signals
- Incremental updates: Embeddings updated daily without full recompute
"""

from .corpus import TextCorpus, TextDocument
from .embedding_engine import EmbeddingEngine
from .feature_extractor import TextFeatureExtractor
from .signal_generator import TextSignalGenerator, TextSignal
from .backtest import TextBacktester, TextBacktestResult, WalkForwardResult

__all__ = [
    # Core classes
    "TextCorpus",
    "TextDocument",
    "EmbeddingEngine",
    "TextFeatureExtractor",
    # Signal generation
    "TextSignalGenerator",
    "TextSignal",
    # Backtesting
    "TextBacktester",
    "TextBacktestResult",
    "WalkForwardResult",
]
