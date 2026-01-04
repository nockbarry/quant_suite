"""
Unified Strategy Specification

Provides a common format for strategies across research and production.
Enables seamless promotion from experiment results to production config.

Usage:
    # From experiment
    spec = StrategySpec.from_experiment(experiment_result)

    # To YAML config
    yaml_str = spec.to_yaml()

    # From production config
    spec = StrategySpec.from_config(strategy_def)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

import yaml


@dataclass
class ValidationResults:
    """Results from strategy validation."""

    sharpe: float = 0.0
    p_value: float = 1.0
    validated_on: str = ""
    validation_date: str = ""
    train_sharpe: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    validation_method: str = "mcpt"

    def is_significant(self) -> bool:
        """Check if validation results are statistically significant."""
        return self.p_value < 0.05

    def meets_promotion_criteria(
        self,
        min_sharpe: float = 0.5,
        max_p_value: float = 0.05,
        min_trades: int = 10,
    ) -> bool:
        """Check if results meet promotion criteria."""
        return (
            self.sharpe >= min_sharpe
            and self.p_value <= max_p_value
            and self.total_trades >= min_trades
        )


@dataclass
class RiskConfig:
    """Risk management configuration."""

    max_position_pct: float = 0.25
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    min_hold_days: int = 2
    max_hold_days: int = 20
    max_drawdown_pct: float = 0.15
    daily_loss_limit_pct: float = 0.05

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RiskConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})

    @classmethod
    def conservative(cls) -> "RiskConfig":
        """Conservative risk settings for budget traders."""
        return cls(
            max_position_pct=0.15,
            stop_loss_pct=0.04,
            take_profit_pct=0.08,
            min_hold_days=2,
            max_hold_days=10,
            max_drawdown_pct=0.10,
            daily_loss_limit_pct=0.03,
        )

    @classmethod
    def moderate(cls) -> "RiskConfig":
        """Moderate risk settings."""
        return cls(
            max_position_pct=0.20,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            min_hold_days=2,
            max_hold_days=15,
        )


@dataclass
class ScheduleConfig:
    """Scheduling configuration."""

    signal_days: list[str] = field(default_factory=lambda: [
        "monday", "tuesday", "wednesday", "thursday", "friday"
    ])
    execute_days: list[str] = field(default_factory=lambda: [
        "monday", "tuesday", "wednesday", "thursday", "friday"
    ])
    signal_time: str = "07:00"
    execution_time: str = "09:35"
    timezone: str = "America/New_York"


@dataclass
class StrategySpec:
    """
    Unified strategy specification.

    Used across research, validation, and production.
    """

    # Identity
    name: str
    class_name: str
    description: str = ""

    # Trading configuration
    universe: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    # Validation
    validation: ValidationResults = field(default_factory=ValidationResults)

    # Risk management
    risk: RiskConfig = field(default_factory=RiskConfig)

    # Scheduling
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    # Metadata
    enabled: bool = True
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""  # "experiment", "manual", "promoted"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "class_name": self.class_name,
            "description": self.description,
            "universe": self.universe,
            "features": self.features,
            "parameters": self.parameters,
            "validation": asdict(self.validation),
            "risk": asdict(self.risk),
            "schedule": asdict(self.schedule),
            "enabled": self.enabled,
            "version": self.version,
            "created_at": self.created_at,
            "source": self.source,
        }

    def to_yaml(self) -> str:
        """
        Convert to YAML format for validated_strategies.yaml.

        Returns YAML string ready to be appended to config file.
        """
        config_key = self.name.lower().replace(" ", "_").replace("-", "_")

        yaml_dict = {
            config_key: {
                "enabled": self.enabled,
                "class": self.class_name,
                "description": self.description,
                "validation": {
                    "sharpe": round(self.validation.sharpe, 2),
                    "p_value": round(self.validation.p_value, 4),
                    "validated_on": self.validation.validated_on,
                    "validation_date": self.validation.validation_date,
                },
                "universe": self.universe,
                "features": self.features,
                "parameters": self.parameters,
                "risk": {
                    "max_position_pct": self.risk.max_position_pct,
                    "stop_loss_pct": self.risk.stop_loss_pct,
                    "take_profit_pct": self.risk.take_profit_pct,
                    "min_hold_days": self.risk.min_hold_days,
                    "max_hold_days": self.risk.max_hold_days,
                },
                "schedule": {
                    "signal_days": self.schedule.signal_days,
                    "execute_days": self.schedule.execute_days,
                },
            }
        }

        return yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategySpec":
        """Create from dictionary."""
        validation = ValidationResults(**d.get("validation", {}))
        risk = RiskConfig.from_dict(d.get("risk", {}))
        schedule = ScheduleConfig(**d.get("schedule", {})) if "schedule" in d else ScheduleConfig()

        return cls(
            name=d.get("name", ""),
            class_name=d.get("class_name", ""),
            description=d.get("description", ""),
            universe=d.get("universe", []),
            features=d.get("features", []),
            parameters=d.get("parameters", {}),
            validation=validation,
            risk=risk,
            schedule=schedule,
            enabled=d.get("enabled", True),
            version=d.get("version", "1.0"),
            created_at=d.get("created_at", datetime.now().isoformat()),
            source=d.get("source", ""),
        )

    @classmethod
    def from_experiment(
        cls,
        strategy_name: str,
        symbol: str,
        params: dict,
        train_sharpe: float,
        val_sharpe: float,
        p_value: float,
        features: list[str] = None,
        class_name: str = None,
        session_id: str = None,
    ) -> "StrategySpec":
        """
        Create StrategySpec from experiment results.

        Args:
            strategy_name: Name of the strategy
            symbol: Primary symbol validated on
            params: Strategy parameters
            train_sharpe: Training Sharpe ratio
            val_sharpe: Validation Sharpe ratio
            p_value: MCPT p-value
            features: Required features (inferred if not provided)
            class_name: Strategy class name (inferred if not provided)
            session_id: Research session ID

        Returns:
            StrategySpec ready for promotion
        """
        # Infer class name if not provided
        if class_name is None:
            class_name = "".join(
                word.title() for word in strategy_name.replace("-", "_").split("_")
            ) + "Strategy"

        # Infer features from strategy name
        if features is None:
            features = _infer_features(strategy_name)

        validation = ValidationResults(
            sharpe=val_sharpe,
            p_value=p_value,
            validated_on=symbol,
            validation_date=datetime.now().strftime("%Y-%m-%d"),
            train_sharpe=train_sharpe,
            validation_method="mcpt",
        )

        return cls(
            name=strategy_name,
            class_name=class_name,
            description=f"Validated on {symbol} (Sharpe={val_sharpe:.2f}, p={p_value:.4f})",
            universe=[symbol],
            features=features,
            parameters=params,
            validation=validation,
            risk=RiskConfig.conservative(),
            source=f"experiment_{session_id}" if session_id else "experiment",
        )

    @classmethod
    def from_config(cls, config_key: str, config_dict: dict) -> "StrategySpec":
        """
        Create StrategySpec from validated_strategies.yaml config entry.

        Args:
            config_key: Strategy key in config (e.g., "insider_technical")
            config_dict: Strategy configuration dictionary

        Returns:
            StrategySpec instance
        """
        val = config_dict.get("validation", {})
        validation = ValidationResults(
            sharpe=val.get("sharpe", 0.0),
            p_value=val.get("p_value", 1.0),
            validated_on=val.get("validated_on", ""),
            validation_date=val.get("validation_date", ""),
        )

        risk_dict = config_dict.get("risk", {})
        risk = RiskConfig.from_dict(risk_dict)

        sched = config_dict.get("schedule", {})
        schedule = ScheduleConfig(
            signal_days=sched.get("signal_days", ["monday", "tuesday", "wednesday", "thursday", "friday"]),
            execute_days=sched.get("execute_days", ["monday", "tuesday", "wednesday", "thursday", "friday"]),
        )

        return cls(
            name=config_key,
            class_name=config_dict.get("class", config_key.title().replace("_", "") + "Strategy"),
            description=config_dict.get("description", ""),
            universe=config_dict.get("universe", []),
            features=config_dict.get("features", []),
            parameters=config_dict.get("parameters", {}),
            validation=validation,
            risk=risk,
            schedule=schedule,
            enabled=config_dict.get("enabled", True),
            source="config",
        )

    @classmethod
    def from_knowledge_base_result(cls, result) -> "StrategySpec":
        """
        Create StrategySpec from a KnowledgeBase StrategyResult.

        Args:
            result: StrategyResult from knowledge base

        Returns:
            StrategySpec instance
        """
        return cls.from_experiment(
            strategy_name=result.strategy_name,
            symbol=result.symbol,
            params=result.params,
            train_sharpe=result.train_sharpe,
            val_sharpe=result.val_sharpe,
            p_value=result.p_value,
            session_id=result.session_id,
        )

    def merge_universe(self, symbols: list[str]) -> "StrategySpec":
        """
        Create new spec with expanded universe.

        Args:
            symbols: Additional symbols to include

        Returns:
            New StrategySpec with merged universe
        """
        new_universe = list(set(self.universe + symbols))
        return StrategySpec(
            name=self.name,
            class_name=self.class_name,
            description=self.description,
            universe=sorted(new_universe),
            features=self.features,
            parameters=self.parameters,
            validation=self.validation,
            risk=self.risk,
            schedule=self.schedule,
            enabled=self.enabled,
            version=self.version,
            created_at=self.created_at,
            source=self.source,
        )


def _infer_features(strategy_name: str) -> list[str]:
    """Infer required features from strategy name."""
    name_lower = strategy_name.lower()

    features = ["returns"]  # Always needed

    if "rsi" in name_lower:
        features.extend(["rsi", "mean_reversion"])
    if "bollinger" in name_lower or "bb" in name_lower:
        features.append("bollinger_bands")
    if "momentum" in name_lower:
        features.extend(["momentum", "trend_features"])
    if "volatility" in name_lower or "vol" in name_lower:
        features.extend(["volatility", "atr"])
    if "macd" in name_lower:
        features.append("macd")
    if "volume" in name_lower:
        features.append("volume_features")
    if "insider" in name_lower or "technical" in name_lower:
        features.extend(["rsi", "bollinger_bands", "volume_features"])
    if "breakout" in name_lower:
        features.extend(["atr", "volume_features"])
    if "reversal" in name_lower or "mean_reversion" in name_lower:
        features.append("mean_reversion")

    return list(set(features))


def load_all_specs_from_config(config_path: str = None) -> list[StrategySpec]:
    """
    Load all strategies from validated_strategies.yaml as StrategySpecs.

    Args:
        config_path: Path to config file (uses default if None)

    Returns:
        List of StrategySpec instances
    """
    from pathlib import Path

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "strategies" / "validated_strategies.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return []

    with open(config_path) as f:
        config = yaml.safe_load(f)

    specs = []
    for key, strategy_config in config.get("strategies", {}).items():
        specs.append(StrategySpec.from_config(key, strategy_config))

    return specs
