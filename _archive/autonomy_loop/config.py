"""Autonomy layer configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class EventLoopConfig:
    check_interval_minutes: int = 3
    active_hours_start: int = 6  # ET
    active_hours_end: int = 17  # ET


@dataclass
class ExecutionConfig:
    authority: str = "thesis_only"  # thesis_only, rules_only, full
    max_daily_trades: int = 10
    max_daily_loss_pct: float = 3.0
    max_single_trade_pct: float = 5.0
    dry_run: bool = True


@dataclass
class LLMConfig:
    model: str = "claude-sonnet-4-20250514"
    max_decisions_per_day: int = 20
    min_confidence_for_auto: float = 0.75
    log_full_prompts: bool = True
    max_tokens: int = 4096


@dataclass
class AlertConfig:
    telegram_enabled: bool = False
    alert_on_every_trade: bool = True
    quiet_hours_start: int = 22
    quiet_hours_end: int = 6


@dataclass
class ProvenanceConfig:
    log_level: str = "full"  # full, summary, minimal
    retain_days: int = 365


@dataclass
class AutonomyConfig:
    event_loop: EventLoopConfig = field(default_factory=EventLoopConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    provenance: ProvenanceConfig = field(default_factory=ProvenanceConfig)


def load_autonomy_config() -> AutonomyConfig:
    """Load config from config/autonomy.yaml with env var overrides."""
    config = AutonomyConfig()

    config_path = Path(__file__).parents[2] / "config" / "autonomy.yaml"
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}

        el = data.get("event_loop", {})
        config.event_loop.check_interval_minutes = el.get("check_interval_minutes", 3)
        hours = el.get("active_hours", [6, 17])
        config.event_loop.active_hours_start = hours[0] if len(hours) > 0 else 6
        config.event_loop.active_hours_end = hours[1] if len(hours) > 1 else 17

        ex = data.get("execution", {})
        config.execution.authority = ex.get("authority", "thesis_only")
        config.execution.max_daily_trades = ex.get("max_daily_trades", 10)
        config.execution.max_daily_loss_pct = ex.get("max_daily_loss_pct", 3.0)
        config.execution.max_single_trade_pct = ex.get("max_single_trade_pct", 5.0)
        config.execution.dry_run = ex.get("dry_run", True)

        llm = data.get("llm", {})
        config.llm.model = llm.get("model", "claude-sonnet-4-20250514")
        config.llm.max_decisions_per_day = llm.get("max_decisions_per_day", 20)
        config.llm.min_confidence_for_auto = llm.get("min_confidence_for_auto", 0.75)
        config.llm.log_full_prompts = llm.get("log_full_prompts", True)

        al = data.get("alerts", {})
        config.alerts.telegram_enabled = al.get("telegram_enabled", False)
        config.alerts.alert_on_every_trade = al.get("alert_on_every_trade", True)
        qh = al.get("quiet_hours", [22, 6])
        config.alerts.quiet_hours_start = qh[0] if len(qh) > 0 else 22
        config.alerts.quiet_hours_end = qh[1] if len(qh) > 1 else 6

        prov = data.get("provenance", {})
        config.provenance.log_level = prov.get("log_level", "full")
        config.provenance.retain_days = prov.get("retain_days", 365)

    # Environment overrides
    if os.environ.get("ATHENA_DRY_RUN"):
        config.execution.dry_run = os.environ["ATHENA_DRY_RUN"].lower() in ("1", "true", "yes")
    if os.environ.get("ATHENA_CHECK_INTERVAL"):
        config.event_loop.check_interval_minutes = int(os.environ["ATHENA_CHECK_INTERVAL"])

    return config
