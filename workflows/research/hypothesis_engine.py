"""
Hypothesis engine for autonomous research.

Generates testable strategy hypotheses based on:
- Past successes (what worked before)
- Data availability
- Novel combinations
- Parameter exploration
- Random exploration
"""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from typing import Any, Callable, Literal

import numpy as np

from .knowledge_base import KnowledgeBase


@dataclass
class Hypothesis:
    """A testable trading strategy hypothesis."""
    id: str
    name: str
    description: str
    strategy_type: str  # "momentum", "mean_reversion", "insider", etc.
    strategy_params: dict[str, Any]
    data_requirements: list[str]  # ["price", "insider", "sentiment"]
    symbols: list[str]
    rationale: str
    priority: float = 0.5  # 0-1, based on similarity to past successes
    source: Literal["winner_variation", "novel_combo", "param_sweep", "random"] = "random"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "strategy_type": self.strategy_type,
            "strategy_params": self.strategy_params,
            "data_requirements": self.data_requirements,
            "symbols": self.symbols,
            "rationale": self.rationale,
            "priority": self.priority,
            "source": self.source,
        }


# =============================================================================
# STRATEGY TEMPLATES
# =============================================================================

STRATEGY_TEMPLATES = {
    # Trend Following
    "sma_crossover": {
        "type": "trend",
        "description": "SMA crossover - buy when fast crosses above slow",
        "data": ["price"],
        "params": {
            "fast_period": [5, 10, 15, 20],
            "slow_period": [20, 30, 50, 100],
        },
    },
    "momentum": {
        "type": "trend",
        "description": "Price momentum - buy strong momentum, sell weak",
        "data": ["price"],
        "params": {
            "lookback": [10, 20, 40, 60],
            "threshold": [0.0, 0.02, 0.05],
        },
    },
    "breakout": {
        "type": "trend",
        "description": "Channel breakout - buy on new highs, sell on new lows",
        "data": ["price"],
        "params": {
            "lookback": [10, 20, 40],
        },
    },

    # Mean Reversion
    "rsi_reversal": {
        "type": "mean_reversion",
        "description": "RSI mean reversion - buy oversold, sell overbought",
        "data": ["price"],
        "params": {
            "period": [7, 14, 21],
            "oversold": [20, 30],
            "overbought": [70, 80],
        },
    },
    "bollinger_reversal": {
        "type": "mean_reversion",
        "description": "Bollinger band mean reversion",
        "data": ["price"],
        "params": {
            "period": [10, 20, 30],
            "num_std": [1.5, 2.0, 2.5],
        },
    },

    # Insider-based
    "insider_momentum": {
        "type": "insider",
        "description": "Buy on cluster insider buying with positive momentum",
        "data": ["price", "insider"],
        "params": {
            "insider_days": [30, 60, 90],
            "momentum_period": [10, 20],
            "require_cluster": [True, False],
        },
    },
    "insider_value": {
        "type": "insider",
        "description": "Buy on insider buying when price is below moving average",
        "data": ["price", "insider"],
        "params": {
            "insider_days": [60, 90],
            "ma_period": [50, 100, 200],
        },
    },

    # Sentiment-based
    "sentiment_momentum": {
        "type": "sentiment",
        "description": "Trade in direction of sentiment momentum",
        "data": ["price", "sentiment"],
        "params": {
            "sentiment_threshold": [0.2, 0.3, 0.5],
        },
    },
    "sentiment_reversal": {
        "type": "sentiment",
        "description": "Mean revert when sentiment is extreme",
        "data": ["price", "sentiment"],
        "params": {
            "sentiment_extreme": [0.5, 0.7],
            "rsi_confirm": [True, False],
        },
    },

    # Regime-based
    "regime_adaptive": {
        "type": "regime",
        "description": "Use momentum in expansion, mean reversion in contraction",
        "data": ["price", "economic"],
        "params": {
            "expansion_strategy": ["momentum", "breakout"],
            "contraction_strategy": ["rsi_reversal", "bollinger_reversal"],
        },
    },

    # Composite
    "multi_signal": {
        "type": "composite",
        "description": "Combine multiple signals with weighted voting",
        "data": ["price", "insider", "sentiment"],
        "params": {
            "insider_weight": [0.3, 0.4, 0.5],
            "sentiment_weight": [0.2, 0.3],
            "momentum_weight": [0.2, 0.3, 0.4],
        },
    },
}


class HypothesisEngine:
    """
    Generates testable strategy hypotheses.

    Uses knowledge base to prioritize promising directions
    and avoid re-testing failed ideas.
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        default_symbols: list[str] | None = None,
    ):
        self.kb = knowledge_base
        self.default_symbols = default_symbols or [
            "AAPL", "NVDA", "MSFT", "GOOGL", "AMZN",
            "META", "QQQ", "SPY", "AMD", "TSLA",
        ]

    def generate_hypotheses(
        self,
        n: int = 20,
        symbols: list[str] | None = None,
        focus_data: list[str] | None = None,
    ) -> list[Hypothesis]:
        """
        Generate n hypotheses to test.

        Allocation:
        - 40% variations of successful strategies
        - 30% novel combinations
        - 20% parameter sweeps
        - 10% random exploration
        """
        symbols = symbols or self.default_symbols
        hypotheses = []

        # 1. Variations of winners (40%)
        n_winners = int(n * 0.4)
        hypotheses.extend(
            self._variations_of_winners(n_winners, symbols)
        )

        # 2. Novel combinations (30%)
        n_novel = int(n * 0.3)
        hypotheses.extend(
            self._novel_combinations(n_novel, symbols, focus_data)
        )

        # 3. Parameter sweeps (20%)
        n_sweep = int(n * 0.2)
        hypotheses.extend(
            self._parameter_exploration(n_sweep, symbols)
        )

        # 4. Random exploration (10%)
        n_random = n - len(hypotheses)
        hypotheses.extend(
            self._random_exploration(n_random, symbols)
        )

        # Sort by priority and return top n
        hypotheses = sorted(hypotheses, key=lambda h: h.priority, reverse=True)

        # Filter out already-tested hypotheses
        untested = []
        for h in hypotheses:
            if not self.kb.was_tested(h.strategy_type, h.symbols[0], h.strategy_params):
                untested.append(h)
            if len(untested) >= n:
                break

        return untested[:n]

    def _variations_of_winners(
        self,
        n: int,
        symbols: list[str],
    ) -> list[Hypothesis]:
        """Generate variations of successful strategies."""
        hypotheses = []

        # Get successful strategies
        successes = self.kb.get_successful_strategies()
        if not successes:
            return hypotheses

        for result in successes[:min(5, len(successes))]:
            # Try on new symbols
            for symbol in symbols:
                if symbol != result.symbol:
                    h = Hypothesis(
                        id=self._generate_id(),
                        name=f"{result.strategy_name}_on_{symbol}",
                        description=f"Apply {result.strategy_name} (worked on {result.symbol}) to {symbol}",
                        strategy_type=result.strategy_name,
                        strategy_params=result.params,
                        data_requirements=["price"],
                        symbols=[symbol],
                        rationale=f"Strategy showed p={result.p_value:.3f} on {result.symbol}",
                        priority=0.8 - 0.1 * (result.p_value / 0.05),
                        source="winner_variation",
                    )
                    hypotheses.append(h)
                    if len(hypotheses) >= n:
                        return hypotheses

            # Try with parameter variations
            for param_name, param_value in result.params.items():
                if isinstance(param_value, (int, float)):
                    for multiplier in [0.5, 0.75, 1.25, 1.5]:
                        new_params = result.params.copy()
                        new_value = type(param_value)(param_value * multiplier)
                        new_params[param_name] = new_value

                        h = Hypothesis(
                            id=self._generate_id(),
                            name=f"{result.strategy_name}_{param_name}_{new_value}",
                            description=f"Vary {param_name} from {param_value} to {new_value}",
                            strategy_type=result.strategy_name,
                            strategy_params=new_params,
                            data_requirements=["price"],
                            symbols=[result.symbol],
                            rationale=f"Parameter variation of successful strategy",
                            priority=0.7,
                            source="winner_variation",
                        )
                        hypotheses.append(h)
                        if len(hypotheses) >= n:
                            return hypotheses

        return hypotheses[:n]

    def _novel_combinations(
        self,
        n: int,
        symbols: list[str],
        focus_data: list[str] | None = None,
    ) -> list[Hypothesis]:
        """Generate novel strategy-data combinations."""
        hypotheses = []

        # Get untested combinations
        templates = list(STRATEGY_TEMPLATES.items())
        random.shuffle(templates)

        for template_name, template in templates:
            # Filter by focus data if specified
            if focus_data:
                if not any(d in template["data"] for d in focus_data):
                    continue

            # Pick a random symbol
            for symbol in random.sample(symbols, min(3, len(symbols))):
                # Generate random params from template
                params = {}
                for param_name, param_options in template.get("params", {}).items():
                    params[param_name] = random.choice(param_options)

                h = Hypothesis(
                    id=self._generate_id(),
                    name=f"{template_name}_{symbol}",
                    description=template["description"],
                    strategy_type=template_name,
                    strategy_params=params,
                    data_requirements=template["data"],
                    symbols=[symbol],
                    rationale=f"Novel combination: {template['type']} strategy with {template['data']}",
                    priority=0.6 if len(template["data"]) > 1 else 0.5,
                    source="novel_combo",
                )
                hypotheses.append(h)
                if len(hypotheses) >= n:
                    return hypotheses

        return hypotheses[:n]

    def _parameter_exploration(
        self,
        n: int,
        symbols: list[str],
    ) -> list[Hypothesis]:
        """Grid search parameter exploration."""
        hypotheses = []

        # Focus on strategies that showed promise
        patterns = self.kb.get_patterns(min_confidence=0.5)

        for pattern in patterns[:3]:
            for strategy_name in pattern.strategies:
                if strategy_name not in STRATEGY_TEMPLATES:
                    continue

                template = STRATEGY_TEMPLATES[strategy_name]

                # Generate grid of parameters
                param_names = list(template.get("params", {}).keys())
                param_values = list(template.get("params", {}).values())

                if not param_names:
                    continue

                for combo in product(*param_values):
                    params = dict(zip(param_names, combo))

                    for symbol in pattern.symbols[:2]:
                        h = Hypothesis(
                            id=self._generate_id(),
                            name=f"{strategy_name}_sweep_{len(hypotheses)}",
                            description=f"Parameter sweep for {strategy_name}",
                            strategy_type=strategy_name,
                            strategy_params=params,
                            data_requirements=template["data"],
                            symbols=[symbol],
                            rationale=f"Grid search on promising strategy pattern",
                            priority=0.55,
                            source="param_sweep",
                        )
                        hypotheses.append(h)
                        if len(hypotheses) >= n:
                            return hypotheses

        return hypotheses[:n]

    def _random_exploration(
        self,
        n: int,
        symbols: list[str],
    ) -> list[Hypothesis]:
        """Generate random hypotheses for exploration."""
        hypotheses = []

        templates = list(STRATEGY_TEMPLATES.items())

        for _ in range(n):
            template_name, template = random.choice(templates)
            symbol = random.choice(symbols)

            # Random params
            params = {}
            for param_name, param_options in template.get("params", {}).items():
                params[param_name] = random.choice(param_options)

            h = Hypothesis(
                id=self._generate_id(),
                name=f"explore_{template_name}_{symbol}",
                description=f"Random exploration: {template['description']}",
                strategy_type=template_name,
                strategy_params=params,
                data_requirements=template["data"],
                symbols=[symbol],
                rationale="Random exploration for discovery",
                priority=0.3,
                source="random",
            )
            hypotheses.append(h)

        return hypotheses

    def _generate_id(self) -> str:
        """Generate unique hypothesis ID."""
        return hashlib.md5(
            f"{datetime.now().isoformat()}_{random.random()}".encode()
        ).hexdigest()[:8]

    def get_hypothesis_summary(self, hypotheses: list[Hypothesis]) -> dict:
        """Get summary statistics of generated hypotheses."""
        by_source = {}
        by_type = {}
        by_data = {}

        for h in hypotheses:
            by_source[h.source] = by_source.get(h.source, 0) + 1
            by_type[h.strategy_type] = by_type.get(h.strategy_type, 0) + 1
            for d in h.data_requirements:
                by_data[d] = by_data.get(d, 0) + 1

        return {
            "total": len(hypotheses),
            "by_source": by_source,
            "by_type": by_type,
            "by_data": by_data,
            "avg_priority": sum(h.priority for h in hypotheses) / len(hypotheses) if hypotheses else 0,
        }
