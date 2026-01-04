"""
Experiment Templates

Pre-built experiment patterns for common research tasks.
Makes it easy to run standardized tests with proper validation.

Templates available:
- single_strategy_test: Test one strategy on one symbol
- strategy_sweep: Test one strategy across all symbols
- parameter_optimization: Optimize parameters for a winning strategy
- regime_analysis: Test strategy across market regimes
- cross_validation: Full walk-forward validation
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal

from workflows.research.knowledge_base import KnowledgeBase
from workflows.research.research_dashboard import KNOWN_STRATEGIES, DEFAULT_SYMBOLS


@dataclass
class ExperimentTemplate:
    """Template for running standardized experiments."""

    name: str
    description: str
    required_params: list[str]
    optional_params: list[str]
    validation_method: str
    estimated_time: str  # e.g., "1 min", "5 min", "30 min"

    def validate_params(self, params: dict) -> list[str]:
        """Check if required params are provided."""
        missing = [p for p in self.required_params if p not in params]
        return missing


# Available templates
EXPERIMENT_TEMPLATES = {
    "single_strategy_test": ExperimentTemplate(
        name="Single Strategy Test",
        description="Test one strategy on one symbol with MCPT validation",
        required_params=["strategy", "symbol"],
        optional_params=["params", "train_days", "test_days"],
        validation_method="mcpt",
        estimated_time="1-2 min",
    ),

    "strategy_sweep": ExperimentTemplate(
        name="Strategy Sweep",
        description="Test one strategy across all default symbols",
        required_params=["strategy"],
        optional_params=["symbols", "params", "parallel"],
        validation_method="mcpt",
        estimated_time="10-15 min",
    ),

    "symbol_sweep": ExperimentTemplate(
        name="Symbol Sweep",
        description="Test all strategies on one symbol",
        required_params=["symbol"],
        optional_params=["strategies", "parallel"],
        validation_method="mcpt",
        estimated_time="15-20 min",
    ),

    "parameter_optimization": ExperimentTemplate(
        name="Parameter Optimization",
        description="Optimize parameters for a winning strategy using walk-forward",
        required_params=["strategy", "symbol", "param_grid"],
        optional_params=["n_folds", "train_days", "test_days"],
        validation_method="walk_forward",
        estimated_time="30-60 min",
    ),

    "regime_analysis": ExperimentTemplate(
        name="Regime Analysis",
        description="Test strategy performance across market regimes",
        required_params=["strategy", "symbols"],
        optional_params=["regimes", "min_days_per_regime"],
        validation_method="regime_conditional",
        estimated_time="20-30 min",
    ),

    "cross_validation": ExperimentTemplate(
        name="Full Cross Validation",
        description="Walk-forward validation with multiple folds",
        required_params=["strategy", "symbol"],
        optional_params=["n_folds", "gap_days", "params"],
        validation_method="walk_forward",
        estimated_time="5-10 min",
    ),

    "correlation_check": ExperimentTemplate(
        name="Correlation Check",
        description="Check if strategy returns are correlated with another",
        required_params=["strategy1", "strategy2", "symbol"],
        optional_params=["lookback_days"],
        validation_method="correlation",
        estimated_time="2-3 min",
    ),

    "alpha_decay": ExperimentTemplate(
        name="Alpha Decay Analysis",
        description="Test if strategy alpha has decayed over time",
        required_params=["strategy", "symbol"],
        optional_params=["window_months", "min_periods"],
        validation_method="rolling_sharpe",
        estimated_time="3-5 min",
    ),
}


@dataclass
class ExperimentConfig:
    """Configuration for running an experiment."""

    template: str
    params: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)

    def get_template(self) -> ExperimentTemplate:
        """Get the template for this config."""
        return EXPERIMENT_TEMPLATES[self.template]

    def validate(self) -> list[str]:
        """Validate this config."""
        template = self.get_template()
        return template.validate_params(self.params)


def create_single_test(strategy: str, symbol: str, **kwargs) -> ExperimentConfig:
    """Create a single strategy test config."""
    return ExperimentConfig(
        template="single_strategy_test",
        params={"strategy": strategy, "symbol": symbol, **kwargs},
    )


def create_sweep(
    strategy: str | None = None,
    symbol: str | None = None,
    **kwargs
) -> ExperimentConfig:
    """Create a sweep experiment config."""
    if strategy:
        return ExperimentConfig(
            template="strategy_sweep",
            params={"strategy": strategy, **kwargs},
        )
    elif symbol:
        return ExperimentConfig(
            template="symbol_sweep",
            params={"symbol": symbol, **kwargs},
        )
    else:
        raise ValueError("Must specify either strategy or symbol")


def create_optimization(
    strategy: str,
    symbol: str,
    param_grid: dict[str, list],
    **kwargs
) -> ExperimentConfig:
    """Create a parameter optimization config."""
    return ExperimentConfig(
        template="parameter_optimization",
        params={
            "strategy": strategy,
            "symbol": symbol,
            "param_grid": param_grid,
            **kwargs
        },
    )


def suggest_experiments(n: int = 5) -> list[ExperimentConfig]:
    """
    Suggest experiments based on knowledge base.

    Returns list of experiment configs to run.
    """
    kb = KnowledgeBase()
    suggestions = []

    # 1. Get promising variations from successful strategies
    variations = kb.get_promising_variations(n)

    for v in variations[:3]:
        suggestions.append(ExperimentConfig(
            template="single_strategy_test",
            params={
                "strategy": v["strategy"],
                "symbol": v["symbol"],
                "params": v.get("suggested_params", {}),
            },
        ))

    # 2. Suggest sweeps for strategies that work on multiple symbols
    winning_strategies = {}
    for s in kb.successes:
        if s.strategy_name not in winning_strategies:
            winning_strategies[s.strategy_name] = 0
        winning_strategies[s.strategy_name] += 1

    multi_winners = [s for s, c in winning_strategies.items() if c >= 2]

    for strategy in multi_winners[:2]:
        # Get untested symbols for this strategy
        tested_symbols = {s.symbol for s in kb.successes if s.strategy_name == strategy}
        untested = [sym for sym in DEFAULT_SYMBOLS if sym not in tested_symbols]

        if untested:
            suggestions.append(ExperimentConfig(
                template="strategy_sweep",
                params={
                    "strategy": strategy,
                    "symbols": untested[:5],
                },
            ))

    return suggestions[:n]


def get_default_param_grid(strategy: str) -> dict[str, list]:
    """
    Get default parameter grid for a strategy.

    Returns reasonable parameter ranges for optimization.
    """
    grids = {
        "momentum_20d": {
            "lookback": [10, 15, 20, 30, 40],
            "threshold": [0.01, 0.02, 0.03, 0.05],
        },
        "momentum_60d": {
            "lookback": [40, 50, 60, 70, 80],
            "threshold": [0.01, 0.02, 0.03],
        },
        "rsi_reversal": {
            "period": [10, 14, 21, 30],
            "oversold": [25, 30, 35],
            "overbought": [65, 70, 75],
        },
        "bollinger_reversal": {
            "period": [15, 20, 25, 30],
            "num_std": [1.5, 2.0, 2.5, 3.0],
        },
        "sma_crossover": {
            "fast": [5, 10, 15, 20],
            "slow": [30, 50, 100, 200],
        },
        "macd": {
            "fast": [8, 12, 16],
            "slow": [21, 26, 30],
            "signal": [7, 9, 11],
        },
    }

    return grids.get(strategy, {"default": [1, 2, 3]})


def list_templates() -> None:
    """Print available experiment templates."""
    print("\nAvailable Experiment Templates")
    print("=" * 50)

    for name, template in EXPERIMENT_TEMPLATES.items():
        print(f"\n{name}:")
        print(f"  {template.description}")
        print(f"  Required: {', '.join(template.required_params)}")
        print(f"  Optional: {', '.join(template.optional_params)}")
        print(f"  Validation: {template.validation_method}")
        print(f"  Time: ~{template.estimated_time}")


def get_template_info(template_name: str) -> dict:
    """Get detailed info about a template."""
    if template_name not in EXPERIMENT_TEMPLATES:
        return {"error": f"Template '{template_name}' not found"}

    t = EXPERIMENT_TEMPLATES[template_name]
    return {
        "name": t.name,
        "description": t.description,
        "required_params": t.required_params,
        "optional_params": t.optional_params,
        "validation_method": t.validation_method,
        "estimated_time": t.estimated_time,
    }


if __name__ == "__main__":
    list_templates()

    print("\n\nSuggested experiments:")
    for i, exp in enumerate(suggest_experiments(3), 1):
        template = exp.get_template()
        print(f"\n{i}. {template.name}")
        print(f"   Params: {exp.params}")
