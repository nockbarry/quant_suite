"""Alert system for real-time trading notifications.

Provides automated monitoring and alerts for:
- Price levels (above/below, support/resistance)
- Stop losses and take profits
- Volume anomalies
- Options theta decay and IV changes
- News and breaking events
- Portfolio concentration and risk limits
- PDT compliance warnings

Usage:
    from src.alerts import AlertManager, AlertType, AlertPriority

    # Create manager with config
    manager = AlertManager("config/alerts.yaml")

    # Add dynamic alerts
    manager.add_price_alert("SLB", 43.35, "below", AlertPriority.HIGH)
    manager.add_stop_alert("VLO", 179.00)

    # Start monitoring
    await manager.start_monitoring(interval_seconds=60)
"""

from .alert_types import (
    Alert,
    AlertType,
    AlertPriority,
    AlertRule,
    PriceAlertConfig,
    VolumeAlertConfig,
    OptionsAlertConfig,
    PortfolioAlertConfig,
)
from .alert_manager import AlertManager

__all__ = [
    "Alert",
    "AlertType",
    "AlertPriority",
    "AlertRule",
    "AlertManager",
    "PriceAlertConfig",
    "VolumeAlertConfig",
    "OptionsAlertConfig",
    "PortfolioAlertConfig",
]
