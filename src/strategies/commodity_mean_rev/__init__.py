"""
Commodity Mean-Reversion Strategy Module

Strategies that trade mean-reversion on commodity ETFs.

VALIDATED Results (2026-01-05 - Walk-Forward + MCPT):
- Natural Gas (UNG): Sharpe 1.37, p=0.003, OOS 2.02 (ALL OOS POSITIVE)
- Oil (USO): Sharpe 2.29, p=0.002, OOS 2.85
- Copper (CPER): Sharpe 3.15, p=0.023, OOS 1.97

NOT VALIDATED (negative OOS in current regime):
- Silver (SLV), Platinum (PPLT), Gold (GLD)

Usage:
    from src.strategies.commodity_mean_rev import (
        CommodityMeanRevStrategy,
        CommodityMeanRevConfig,
        create_natural_gas_strategy,  # BEST - all OOS positive
        create_oil_strategy,
        create_copper_strategy,
        create_validated_commodities_strategy,
        analyze_commodity_zscore,
    )

    # Quick start with Natural Gas (best performer)
    strategy = create_natural_gas_strategy()
    signals = strategy.generate_signals(data)

    # Or use all validated commodities
    strategy = create_validated_commodities_strategy()
"""

from .commodity_mean_rev_strategy import (
    CommodityMeanRevStrategy,
    CommodityMeanRevConfig,
    CommodityMeanRevSignal,
    CommodityMeanRevFeatureGenerator,
    # VALIDATED strategies (use these)
    create_natural_gas_strategy,
    create_oil_strategy,
    create_copper_strategy,
    create_validated_commodities_strategy,
    create_energy_strategy,
    # Legacy (NOT VALIDATED - use with caution)
    create_silver_strategy,
    create_platinum_strategy,
    # Utilities
    analyze_commodity_zscore,
)

__all__ = [
    "CommodityMeanRevStrategy",
    "CommodityMeanRevConfig",
    "CommodityMeanRevSignal",
    "CommodityMeanRevFeatureGenerator",
    # VALIDATED strategies
    "create_natural_gas_strategy",
    "create_oil_strategy",
    "create_copper_strategy",
    "create_validated_commodities_strategy",
    "create_energy_strategy",
    # Legacy (NOT VALIDATED)
    "create_silver_strategy",
    "create_platinum_strategy",
    # Utilities
    "analyze_commodity_zscore",
]
