"""
Strategy Definition Schema.

Standardized strategy definitions for documentation, execution, and audit trail.
As specified in Section 3.4.2 of the Testing Suite documentation.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal
import json
import yaml

from src.core.paths import paths


class StrategyCategory(str, Enum):
    """Strategy categories from taxonomy."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    VALUE = "value"
    CARRY = "carry"
    VOLATILITY = "volatility"
    SENTIMENT = "sentiment"
    EVENT_DRIVEN = "event_driven"
    MACHINE_LEARNING = "machine_learning"
    ENSEMBLE = "ensemble"


class StrategySubcategory(str, Enum):
    """Strategy subcategories."""
    # Momentum
    TIME_SERIES_MOMENTUM = "time_series_momentum"
    CROSS_SECTIONAL_MOMENTUM = "cross_sectional_momentum"
    FACTOR_MOMENTUM = "factor_momentum"
    # Mean Reversion
    STATISTICAL_ARBITRAGE = "statistical_arbitrage"
    OVERSOLD_OVERBOUGHT = "oversold_overbought"
    PAIRS_TRADING = "pairs_trading"
    # Value
    FUNDAMENTAL_VALUE = "fundamental_value"
    DEEP_VALUE = "deep_value"
    QUALITY_ADJUSTED_VALUE = "quality_adjusted_value"
    # Carry
    DIVIDEND_CAPTURE = "dividend_capture"
    OPTIONS_PREMIUM = "options_premium"
    # Volatility
    VOL_ARBITRAGE = "vol_arbitrage"
    DISPERSION = "dispersion"
    VOL_RISK_PREMIUM = "vol_risk_premium"
    # Sentiment
    NEWS_DRIVEN = "news_driven"
    SOCIAL_SENTIMENT = "social_sentiment"
    CONTRARIAN = "contrarian"
    # Event-Driven
    EARNINGS = "earnings"
    MERGER_ARBITRAGE = "merger_arbitrage"
    INDEX_REBALANCING = "index_rebalancing"
    # Machine Learning
    SUPERVISED = "supervised"
    REINFORCEMENT = "reinforcement"
    ENSEMBLE_ML = "ensemble_ml"


class EdgeSource(str, Enum):
    """Where the alpha is expected to come from."""
    BEHAVIORAL = "behavioral"  # Investor behavior biases
    INFORMATION = "information"  # Faster/better information
    STRUCTURAL = "structural"  # Market structure inefficiencies
    RISK_PREMIUM = "risk_premium"  # Compensation for bearing risk
    LIQUIDITY = "liquidity"  # Providing liquidity
    COMPLEXITY = "complexity"  # Analyzing complex instruments
    ALTERNATIVE_DATA = "alternative_data"  # Non-traditional data sources


class ExecutionUrgency(str, Enum):
    """Order execution urgency."""
    PASSIVE = "passive"  # Post-only, capture spread
    NORMAL = "normal"  # Standard execution
    AGGRESSIVE = "aggressive"  # Take liquidity
    IMMEDIATE = "immediate"  # Market orders, emergency


@dataclass
class UniverseConfig:
    """Universe definition for strategy."""
    base: str = "US_EQUITIES"  # Base universe
    filters: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    rebalance_frequency: str = "monthly"
    min_market_cap: float | None = None
    min_adv: float | None = None  # Average daily volume
    min_price: float | None = None
    min_listing_age_days: int | None = None


@dataclass
class RiskConfig:
    """Risk management configuration."""
    stop_loss: float | None = None  # Percentage
    take_profit: float | None = None  # Percentage
    max_drawdown_exit: float = 0.15  # 15% max drawdown
    volatility_targeting: float | None = None  # Annualized vol target
    max_position_size: float = 0.05  # 5% max position
    max_sector_exposure: float = 0.25  # 25% max sector
    max_positions: int = 50


@dataclass
class PerformanceTarget:
    """Expected performance targets."""
    target_sharpe: float = 1.0
    target_max_drawdown: float = 0.15
    target_cagr: float = 0.10
    target_win_rate: float = 0.55


@dataclass
class StrategyDefinition:
    """
    Standardized strategy definition for documentation and execution.

    As specified in Section 3.4.2 of the Testing Suite documentation.
    All strategies should be defined using this schema for:
    - Consistent documentation
    - Automated validation
    - Audit trail
    - Research knowledge base integration
    """

    # Identification
    strategy_id: str
    name: str
    version: str
    author: str  # Can be "agent" or human name
    created_date: datetime
    updated_date: datetime | None = None

    # Classification
    category: StrategyCategory = StrategyCategory.MOMENTUM
    subcategory: StrategySubcategory | None = None
    asset_classes: list[str] = field(default_factory=lambda: ["equities"])

    # Universe
    universe: UniverseConfig = field(default_factory=UniverseConfig)

    # Signal Generation
    features_used: list[str] = field(default_factory=list)
    signal_logic: str = ""  # Description or code reference
    signal_frequency: str = "daily"  # daily, intraday, weekly
    lookback_period: int = 252  # Days of history needed

    # Portfolio Construction
    position_sizing_method: str = "equal_weight"
    rebalance_frequency: str = "monthly"
    long_only: bool = True

    # Risk Management
    risk: RiskConfig = field(default_factory=RiskConfig)

    # Execution
    order_type: str = "LIMIT"  # MARKET, LIMIT, etc.
    execution_algo: str = "TWAP"  # TWAP, VWAP, etc.
    urgency: ExecutionUrgency = ExecutionUrgency.NORMAL

    # Hypothesis - WHY this should work
    hypothesis: str = ""  # Why this should work
    edge_source: EdgeSource = EdgeSource.BEHAVIORAL
    expected_decay: str = ""  # How quickly edge might decay
    market_conditions: str = ""  # When strategy works best

    # Dependencies
    data_requirements: list[str] = field(default_factory=list)
    feature_dependencies: list[str] = field(default_factory=list)
    external_apis: list[str] = field(default_factory=list)

    # Performance Targets
    performance_targets: PerformanceTarget = field(default_factory=PerformanceTarget)

    # Validation Results (filled after testing)
    validation: dict[str, Any] = field(default_factory=dict)

    # Metadata
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    related_strategies: list[str] = field(default_factory=list)

    # Status
    status: Literal["draft", "testing", "paper", "live", "retired"] = "draft"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums to strings
        data["category"] = self.category.value
        if self.subcategory:
            data["subcategory"] = self.subcategory.value
        data["edge_source"] = self.edge_source.value
        data["urgency"] = self.urgency.value
        # Convert datetime
        data["created_date"] = self.created_date.isoformat()
        if self.updated_date:
            data["updated_date"] = self.updated_date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyDefinition":
        """Create from dictionary."""
        # Convert strings back to enums
        if "category" in data and isinstance(data["category"], str):
            data["category"] = StrategyCategory(data["category"])
        if "subcategory" in data and data["subcategory"]:
            data["subcategory"] = StrategySubcategory(data["subcategory"])
        if "edge_source" in data and isinstance(data["edge_source"], str):
            data["edge_source"] = EdgeSource(data["edge_source"])
        if "urgency" in data and isinstance(data["urgency"], str):
            data["urgency"] = ExecutionUrgency(data["urgency"])
        # Convert datetime strings
        if "created_date" in data and isinstance(data["created_date"], str):
            data["created_date"] = datetime.fromisoformat(data["created_date"])
        if "updated_date" in data and isinstance(data["updated_date"], str):
            data["updated_date"] = datetime.fromisoformat(data["updated_date"])
        # Convert nested configs
        if "universe" in data and isinstance(data["universe"], dict):
            data["universe"] = UniverseConfig(**data["universe"])
        if "risk" in data and isinstance(data["risk"], dict):
            data["risk"] = RiskConfig(**data["risk"])
        if "performance_targets" in data and isinstance(data["performance_targets"], dict):
            data["performance_targets"] = PerformanceTarget(**data["performance_targets"])
        return cls(**data)

    def to_yaml(self) -> str:
        """Export to YAML format."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "StrategyDefinition":
        """Load from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    def save(self, path: Path | str) -> None:
        """Save strategy definition to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix == ".yaml" or path.suffix == ".yml":
            path.write_text(self.to_yaml())
        else:
            path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path | str) -> "StrategyDefinition":
        """Load strategy definition from file."""
        path = Path(path)
        content = path.read_text()

        if path.suffix == ".yaml" or path.suffix == ".yml":
            return cls.from_yaml(content)
        else:
            return cls.from_dict(json.loads(content))

    def validate(self) -> list[str]:
        """
        Validate strategy definition.

        Returns list of validation errors (empty if valid).
        """
        errors = []

        # Required fields
        if not self.strategy_id:
            errors.append("strategy_id is required")
        if not self.name:
            errors.append("name is required")
        if not self.hypothesis:
            errors.append("hypothesis is required - explain why this should work")

        # Sensible defaults
        if self.risk.max_position_size > 0.20:
            errors.append(f"max_position_size {self.risk.max_position_size} > 20% is very concentrated")
        if self.risk.max_drawdown_exit > 0.30:
            errors.append(f"max_drawdown_exit {self.risk.max_drawdown_exit} > 30% is very aggressive")

        # Feature requirements
        if not self.features_used:
            errors.append("features_used should list required features")

        # Performance targets sanity
        if self.performance_targets.target_sharpe > 3.0:
            errors.append(f"target_sharpe {self.performance_targets.target_sharpe} > 3.0 is unrealistic")

        return errors


class StrategyRegistry:
    """
    Registry for managing strategy definitions.

    Provides:
    - Persistence of strategy definitions
    - Query interface
    - Version tracking
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else paths.base / "strategies"
        self.path.mkdir(parents=True, exist_ok=True)
        self._strategies: dict[str, StrategyDefinition] = {}
        self._load()

    def _load(self) -> None:
        """Load all strategies from disk."""
        for file_path in self.path.glob("*.yaml"):
            try:
                strategy = StrategyDefinition.load(file_path)
                self._strategies[strategy.strategy_id] = strategy
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")

    def register(self, strategy: StrategyDefinition, overwrite: bool = False) -> None:
        """
        Register a strategy definition.

        Args:
            strategy: Strategy definition to register
            overwrite: Whether to overwrite existing
        """
        if strategy.strategy_id in self._strategies and not overwrite:
            raise ValueError(f"Strategy {strategy.strategy_id} already exists. Use overwrite=True to update.")

        # Validate before saving
        errors = strategy.validate()
        if errors:
            raise ValueError(f"Strategy validation failed: {errors}")

        # Update timestamp
        if strategy.strategy_id in self._strategies:
            strategy.updated_date = datetime.now()

        # Save to disk
        file_path = self.path / f"{strategy.strategy_id}.yaml"
        strategy.save(file_path)

        # Update in-memory cache
        self._strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> StrategyDefinition | None:
        """Get a strategy by ID."""
        return self._strategies.get(strategy_id)

    def list_strategies(
        self,
        category: StrategyCategory | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
    ) -> list[StrategyDefinition]:
        """
        List strategies with optional filters.

        Args:
            category: Filter by category
            status: Filter by status (draft, testing, paper, live, retired)
            tags: Filter by tags (any match)
        """
        results = list(self._strategies.values())

        if category:
            results = [s for s in results if s.category == category]
        if status:
            results = [s for s in results if s.status == status]
        if tags:
            results = [s for s in results if any(t in s.tags for t in tags)]

        return sorted(results, key=lambda s: s.name)

    def get_by_edge_source(self, edge_source: EdgeSource) -> list[StrategyDefinition]:
        """Get strategies by edge source."""
        return [s for s in self._strategies.values() if s.edge_source == edge_source]

    def get_live_strategies(self) -> list[StrategyDefinition]:
        """Get all live strategies."""
        return self.list_strategies(status="live")

    def retire(self, strategy_id: str, reason: str = "") -> None:
        """Retire a strategy."""
        strategy = self.get(strategy_id)
        if strategy:
            strategy.status = "retired"
            strategy.notes += f"\nRetired: {reason}"
            strategy.updated_date = datetime.now()
            self.register(strategy, overwrite=True)

    def summary(self) -> dict[str, Any]:
        """Get registry summary."""
        by_status = {}
        by_category = {}

        for s in self._strategies.values():
            by_status[s.status] = by_status.get(s.status, 0) + 1
            by_category[s.category.value] = by_category.get(s.category.value, 0) + 1

        return {
            "total_strategies": len(self._strategies),
            "by_status": by_status,
            "by_category": by_category,
            "live_count": by_status.get("live", 0),
        }


def create_momentum_strategy_definition(
    strategy_id: str,
    name: str,
    lookback_period: int = 252,
    skip_recent: int = 21,
    **kwargs,
) -> StrategyDefinition:
    """
    Factory function for creating momentum strategy definitions.

    Args:
        strategy_id: Unique identifier
        name: Display name
        lookback_period: Momentum lookback in days
        skip_recent: Days to skip (avoid reversal)
    """
    return StrategyDefinition(
        strategy_id=strategy_id,
        name=name,
        version="1.0.0",
        author=kwargs.get("author", "system"),
        created_date=datetime.now(),
        category=StrategyCategory.MOMENTUM,
        subcategory=StrategySubcategory.CROSS_SECTIONAL_MOMENTUM,
        features_used=[
            f"returns_{lookback_period}d",
            f"returns_{skip_recent}d",
            "volatility_21d",
        ],
        signal_logic=f"Rank stocks by {lookback_period}-{skip_recent} day momentum, long top quintile",
        lookback_period=lookback_period,
        hypothesis="Past winners continue to outperform due to behavioral biases (anchoring, slow information diffusion)",
        edge_source=EdgeSource.BEHAVIORAL,
        expected_decay="Medium - alpha has decayed but still present in mid-caps",
        market_conditions="Works best in trending markets, struggles in reversals",
        **kwargs,
    )


def create_mean_reversion_strategy_definition(
    strategy_id: str,
    name: str,
    lookback_period: int = 20,
    **kwargs,
) -> StrategyDefinition:
    """Factory function for creating mean reversion strategy definitions."""
    return StrategyDefinition(
        strategy_id=strategy_id,
        name=name,
        version="1.0.0",
        author=kwargs.get("author", "system"),
        created_date=datetime.now(),
        category=StrategyCategory.MEAN_REVERSION,
        subcategory=StrategySubcategory.OVERSOLD_OVERBOUGHT,
        features_used=[
            "rsi_14",
            "bollinger_pctb_20",
            "distance_from_ma_20",
        ],
        signal_logic=f"Buy oversold (RSI<30), sell overbought (RSI>70)",
        lookback_period=lookback_period,
        hypothesis="Short-term overreaction to news/events creates mean reversion opportunities",
        edge_source=EdgeSource.BEHAVIORAL,
        expected_decay="Low - fundamental behavioral bias",
        market_conditions="Works best in ranging markets, fails in strong trends",
        **kwargs,
    )


def create_sentiment_strategy_definition(
    strategy_id: str,
    name: str,
    sentiment_sources: list[str] | None = None,
    **kwargs,
) -> StrategyDefinition:
    """Factory function for creating sentiment strategy definitions."""
    sources = sentiment_sources or ["news", "reddit", "twitter"]

    return StrategyDefinition(
        strategy_id=strategy_id,
        name=name,
        version="1.0.0",
        author=kwargs.get("author", "system"),
        created_date=datetime.now(),
        category=StrategyCategory.SENTIMENT,
        subcategory=StrategySubcategory.SOCIAL_SENTIMENT,
        features_used=[
            f"{source}_sentiment_score" for source in sources
        ] + [
            f"{source}_sentiment_momentum" for source in sources
        ],
        signal_logic="Aggregate sentiment across sources, trade in direction of sentiment shift",
        hypothesis="Sentiment shifts precede price moves; crowd wisdom contains information",
        edge_source=EdgeSource.ALTERNATIVE_DATA,
        expected_decay="High - as more traders use sentiment, edge decays quickly",
        market_conditions="Works in retail-driven names; less effective in institutionally-dominated",
        data_requirements=sources,
        external_apis=["news_api", "reddit_api"] if "reddit" in sources else ["news_api"],
        **kwargs,
    )
