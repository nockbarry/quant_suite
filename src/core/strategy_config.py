"""
Strategy Configuration Loader.

Loads strategy definitions from YAML config files with:
- Strategy parameters
- Universe definitions
- Feature requirements
- Schedule configuration
- Risk parameters
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScheduleConfig:
    """Schedule configuration for a strategy or global."""
    timezone: str = "America/New_York"
    signal_time: str = "07:00"
    execution_time: str = "09:35"
    eod_time: str = "16:05"
    signal_days: list[str] = field(default_factory=lambda: [
        "monday", "tuesday", "wednesday", "thursday", "friday"
    ])
    execute_days: list[str] = field(default_factory=lambda: [
        "monday", "tuesday", "wednesday", "thursday", "friday"
    ])


@dataclass
class RiskConfig:
    """Risk parameters for a strategy."""
    max_position_pct: float = 0.25
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    min_hold_days: int = 2
    max_hold_days: int = 20


@dataclass
class ValidationInfo:
    """Strategy validation results."""
    sharpe: float = 0.0
    p_value: float = 1.0
    validated_on: str = ""
    validation_date: str = ""


@dataclass
class StrategyDefinition:
    """Complete strategy definition from config."""
    name: str
    enabled: bool
    class_name: str
    description: str
    universe: list[str]
    features: list[str]
    parameters: dict[str, Any]
    risk: RiskConfig
    schedule: ScheduleConfig
    validation: ValidationInfo

    @property
    def is_validated(self) -> bool:
        """Check if strategy has significant validation."""
        return self.validation.p_value < 0.05


@dataclass
class PDTConfig:
    """Pattern Day Trader configuration."""
    enabled: bool = True
    max_day_trades: int = 3
    rolling_window_days: int = 5
    min_hold_days: int = 2
    account_threshold: float = 25000.0


@dataclass
class AlertConfig:
    """Alert thresholds."""
    max_drawdown_warning: float = 0.10
    max_drawdown_critical: float = 0.15
    daily_loss_warning: float = 0.03
    daily_loss_critical: float = 0.05
    console: bool = True
    slack_webhook: str = ""
    email: str = ""


@dataclass
class StrategyConfigBundle:
    """Complete configuration bundle."""
    strategies: dict[str, StrategyDefinition]
    defaults: dict[str, Any]
    schedule: ScheduleConfig
    pdt: PDTConfig
    alerts: AlertConfig

    def get_enabled_strategies(self) -> list[StrategyDefinition]:
        """Get all enabled strategies."""
        return [s for s in self.strategies.values() if s.enabled]

    def get_all_symbols(self) -> set[str]:
        """Get unique symbols across all enabled strategies."""
        symbols = set()
        for strategy in self.get_enabled_strategies():
            symbols.update(strategy.universe)
        return symbols

    def get_all_features(self) -> set[str]:
        """Get unique features across all enabled strategies."""
        features = set()
        for strategy in self.get_enabled_strategies():
            features.update(strategy.features)
        return features


class StrategyConfigLoader:
    """Load and manage strategy configurations."""

    def __init__(self, config_dir: Path | str | None = None):
        """
        Initialize config loader.

        Args:
            config_dir: Path to config directory (default: config/strategies/)
        """
        if config_dir is None:
            # Default to project config directory
            config_dir = Path(__file__).parent.parent.parent / "config" / "strategies"
        self.config_dir = Path(config_dir)

    def load(self, config_file: str = "validated_strategies.yaml") -> StrategyConfigBundle:
        """
        Load strategy configuration from YAML file.

        Args:
            config_file: Name of config file to load

        Returns:
            StrategyConfigBundle with all configuration
        """
        config_path = self.config_dir / config_file

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return self._get_default_config()

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        return self._parse_config(raw)

    def _parse_config(self, raw: dict) -> StrategyConfigBundle:
        """Parse raw YAML into config bundle."""
        # Parse defaults
        defaults = raw.get("defaults", {})

        # Parse global schedule
        schedule_raw = raw.get("schedule", {})
        schedule = ScheduleConfig(
            timezone=schedule_raw.get("timezone", "America/New_York"),
            signal_time=schedule_raw.get("signal_generation", {}).get("time", "07:00"),
            execution_time=schedule_raw.get("execution", {}).get("time", "09:35"),
            eod_time=schedule_raw.get("eod_snapshot", {}).get("time", "16:05"),
            signal_days=schedule_raw.get("signal_generation", {}).get(
                "days", ["monday", "tuesday", "wednesday", "thursday", "friday"]
            ),
            execute_days=schedule_raw.get("execution", {}).get(
                "days", ["monday", "tuesday", "wednesday", "thursday", "friday"]
            ),
        )

        # Parse PDT config
        pdt_raw = raw.get("pdt", {})
        pdt = PDTConfig(
            enabled=pdt_raw.get("enabled", True),
            max_day_trades=pdt_raw.get("max_day_trades", 3),
            rolling_window_days=pdt_raw.get("rolling_window_days", 5),
            min_hold_days=pdt_raw.get("min_hold_days", 2),
            account_threshold=pdt_raw.get("account_threshold", 25000.0),
        )

        # Parse alerts
        monitoring = raw.get("monitoring", {})
        alerts_raw = monitoring.get("alerts", {})
        channels = alerts_raw.get("channels", {})
        alerts = AlertConfig(
            max_drawdown_warning=alerts_raw.get("max_drawdown_warning", 0.10),
            max_drawdown_critical=alerts_raw.get("max_drawdown_critical", 0.15),
            daily_loss_warning=alerts_raw.get("daily_loss_warning", 0.03),
            daily_loss_critical=alerts_raw.get("daily_loss_critical", 0.05),
            console=channels.get("console", True),
            slack_webhook=channels.get("slack_webhook", ""),
            email=channels.get("email", ""),
        )

        # Parse strategies
        strategies = {}
        for name, strat_raw in raw.get("strategies", {}).items():
            strategies[name] = self._parse_strategy(name, strat_raw, defaults, schedule)

        return StrategyConfigBundle(
            strategies=strategies,
            defaults=defaults,
            schedule=schedule,
            pdt=pdt,
            alerts=alerts,
        )

    def _parse_strategy(
        self,
        name: str,
        raw: dict,
        defaults: dict,
        global_schedule: ScheduleConfig,
    ) -> StrategyDefinition:
        """Parse a single strategy definition."""
        # Risk config with defaults
        risk_raw = raw.get("risk", {})
        risk = RiskConfig(
            max_position_pct=risk_raw.get("max_position_pct", defaults.get("max_position_pct", 0.25)),
            stop_loss_pct=risk_raw.get("stop_loss_pct", 0.05),
            take_profit_pct=risk_raw.get("take_profit_pct", 0.10),
            min_hold_days=risk_raw.get("min_hold_days", 2),
            max_hold_days=risk_raw.get("max_hold_days", 20),
        )

        # Schedule with fallback to global
        sched_raw = raw.get("schedule", {})
        schedule = ScheduleConfig(
            timezone=global_schedule.timezone,
            signal_time=global_schedule.signal_time,
            execution_time=global_schedule.execution_time,
            eod_time=global_schedule.eod_time,
            signal_days=sched_raw.get("signal_days", global_schedule.signal_days),
            execute_days=sched_raw.get("execute_days", global_schedule.execute_days),
        )

        # Validation info
        val_raw = raw.get("validation", {})
        validation = ValidationInfo(
            sharpe=val_raw.get("sharpe", 0.0),
            p_value=val_raw.get("p_value", 1.0),
            validated_on=val_raw.get("validated_on", ""),
            validation_date=val_raw.get("validation_date", ""),
        )

        return StrategyDefinition(
            name=name,
            enabled=raw.get("enabled", True),
            class_name=raw.get("class", f"{name.title().replace('_', '')}Strategy"),
            description=raw.get("description", ""),
            universe=raw.get("universe", []),
            features=raw.get("features", []),
            parameters=raw.get("parameters", {}),
            risk=risk,
            schedule=schedule,
            validation=validation,
        )

    def _get_default_config(self) -> StrategyConfigBundle:
        """Get default configuration when no file exists."""
        return StrategyConfigBundle(
            strategies={},
            defaults={
                "min_signal_strength": 0.3,
                "min_signal_confidence": 0.5,
                "max_position_pct": 0.25,
            },
            schedule=ScheduleConfig(),
            pdt=PDTConfig(),
            alerts=AlertConfig(),
        )


def load_strategy_config(
    config_file: str = "validated_strategies.yaml",
    config_dir: Path | str | None = None,
) -> StrategyConfigBundle:
    """
    Convenience function to load strategy config.

    Args:
        config_file: Name of config file
        config_dir: Path to config directory

    Returns:
        StrategyConfigBundle
    """
    loader = StrategyConfigLoader(config_dir)
    return loader.load(config_file)
