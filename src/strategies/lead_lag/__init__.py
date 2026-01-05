"""
Lead-Lag Strategy Module

Strategies that exploit cross-asset predictive relationships.

Example: DRAM prices lead semiconductor stocks by 18 days.

Usage:
    from src.strategies.lead_lag import (
        LeadLagStrategy,
        LeadLagConfig,
        create_dram_semiconductor_strategy,
        analyze_lead_lag_relationship,
    )

    # Quick start with pre-configured DRAM strategy
    strategy = create_dram_semiconductor_strategy()
    signals = strategy.generate_signals(data)

    # Or customize
    config = LeadLagConfig(
        leader_symbol='GLD',
        target_symbols=['GDX', 'NEM'],
        lag_days=5,
    )
    strategy = LeadLagStrategy(config=config)
"""

from .lead_lag_strategy import (
    LeadLagStrategy,
    LeadLagConfig,
    LeadLagSignal,
    LeadLagFeatureGenerator,
    create_dram_semiconductor_strategy,
    analyze_lead_lag_relationship,
)

__all__ = [
    "LeadLagStrategy",
    "LeadLagConfig",
    "LeadLagSignal",
    "LeadLagFeatureGenerator",
    "create_dram_semiconductor_strategy",
    "analyze_lead_lag_relationship",
]
