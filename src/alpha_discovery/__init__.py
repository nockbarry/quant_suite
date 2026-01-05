"""
Alpha Discovery Module

Tools for finding market inefficiencies and opportunities:
- Market scanning for inefficiencies
- Opportunity ranking and prioritization
- Research suggestion generation
"""

from .market_scanner import (
    MarketScanner,
    MarketScanResult,
    InefficiencySignal,
    InefficiencyType,
    quick_scan,
    get_opportunities,
)

__all__ = [
    "MarketScanner",
    "MarketScanResult",
    "InefficiencySignal",
    "InefficiencyType",
    "quick_scan",
    "get_opportunities",
]
