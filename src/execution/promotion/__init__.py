"""Strategy Promotion Pipeline.

Manages the lifecycle of trading strategies from backtest to live trading.
"""

from .pipeline import (
    PromotionStage,
    PromotionCandidate,
    PromotionPipeline,
    PromotionGates,
    get_promotion_summary,
)

__all__ = [
    "PromotionStage",
    "PromotionCandidate",
    "PromotionPipeline",
    "PromotionGates",
    "get_promotion_summary",
]
