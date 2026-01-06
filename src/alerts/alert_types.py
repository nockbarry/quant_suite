"""Alert type definitions and data structures.

Defines:
- AlertType enum with 20+ alert categories
- AlertPriority enum for severity levels
- Alert dataclass for triggered alerts
- AlertRule dataclass for rule definitions
- Configuration dataclasses for different alert categories
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
import uuid


class AlertType(str, Enum):
    """Categories of alerts."""

    # Price Alerts
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    STOP_HIT = "stop_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    SUPPORT_TEST = "support_test"
    SUPPORT_BREAK = "support_break"
    RESISTANCE_TEST = "resistance_test"
    RESISTANCE_BREAK = "resistance_break"

    # Volume Alerts
    VOLUME_SPIKE = "volume_spike"
    VOLUME_DRY_UP = "volume_dry_up"

    # Options Alerts
    THETA_WARNING = "theta_warning"
    IV_SPIKE = "iv_spike"
    IV_CRUSH = "iv_crush"
    EXPIRY_WARNING = "expiry_warning"
    DELTA_WARNING = "delta_warning"

    # News Alerts
    NEWS_BREAKING = "news_breaking"
    NEWS_SENTIMENT_SHIFT = "news_sentiment_shift"
    SEC_FILING = "sec_filing"

    # Portfolio Alerts
    CONCENTRATION_HIGH = "concentration_high"
    CORRELATION_SPIKE = "correlation_spike"
    DRAWDOWN_WARNING = "drawdown_warning"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    PDT_WARNING = "pdt_warning"

    # Technical Alerts
    TREND_CHANGE = "trend_change"
    PATTERN_DETECTED = "pattern_detected"
    DIVERGENCE = "divergence"
    RSI_OVERSOLD = "rsi_oversold"
    RSI_OVERBOUGHT = "rsi_overbought"
    MACD_CROSSOVER = "macd_crossover"
    VWAP_CROSS = "vwap_cross"

    # Morning Protocol Alerts
    GAP_FADE = "gap_fade"
    SECTOR_ROTATION = "sector_rotation"


class AlertPriority(str, Enum):
    """Severity level of alerts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Alert:
    """A triggered alert."""

    id: str
    timestamp: datetime
    alert_type: AlertType
    priority: AlertPriority
    symbol: str
    message: str
    current_value: float
    threshold: float
    action_suggested: str
    acknowledged: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        alert_type: AlertType,
        priority: AlertPriority,
        symbol: str,
        message: str,
        current_value: float,
        threshold: float,
        action_suggested: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "Alert":
        """Factory method to create an alert with auto-generated ID."""
        return cls(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(),
            alert_type=alert_type,
            priority=priority,
            symbol=symbol,
            message=message,
            current_value=current_value,
            threshold=threshold,
            action_suggested=action_suggested,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "alert_type": self.alert_type.value,
            "priority": self.priority.value,
            "symbol": self.symbol,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "action_suggested": self.action_suggested,
            "acknowledged": self.acknowledged,
            "metadata": self.metadata,
        }

    def format_console(self) -> str:
        """Format for console display."""
        icons = {
            AlertPriority.CRITICAL: "\u001b[31m\u001b[1m[CRITICAL]\u001b[0m",
            AlertPriority.HIGH: "\u001b[33m\u001b[1m[HIGH]\u001b[0m",
            AlertPriority.MEDIUM: "\u001b[36m[MEDIUM]\u001b[0m",
            AlertPriority.LOW: "\u001b[37m[LOW]\u001b[0m",
        }
        icon = icons.get(self.priority, "[ALERT]")
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"{icon} {time_str} {self.symbol}: {self.message}"

    def format_slack(self) -> dict[str, Any]:
        """Format for Slack webhook."""
        colors = {
            AlertPriority.CRITICAL: "#f44336",
            AlertPriority.HIGH: "#ff9800",
            AlertPriority.MEDIUM: "#2196f3",
            AlertPriority.LOW: "#9e9e9e",
        }
        return {
            "attachments": [
                {
                    "color": colors.get(self.priority, "#808080"),
                    "title": f"{self.symbol} - {self.alert_type.value}",
                    "text": self.message,
                    "fields": [
                        {"title": "Priority", "value": self.priority.value, "short": True},
                        {"title": "Current", "value": f"{self.current_value:.2f}", "short": True},
                        {"title": "Threshold", "value": f"{self.threshold:.2f}", "short": True},
                        {"title": "Action", "value": self.action_suggested or "Monitor", "short": True},
                    ],
                    "ts": int(self.timestamp.timestamp()),
                }
            ]
        }


@dataclass
class AlertRule:
    """Rule definition for triggering alerts."""

    name: str
    alert_type: AlertType
    symbol: str
    check: Callable[[float], tuple[bool, float]]  # Returns (triggered, current_value)
    threshold: float
    priority: AlertPriority
    message_template: str
    action_template: str = ""
    cooldown_minutes: int = 15
    last_triggered: datetime | None = None
    enabled: bool = True

    def should_alert(self, current_value: float) -> Alert | None:
        """Check if rule should trigger an alert."""
        if not self.enabled:
            return None

        triggered, value = self.check(current_value)

        if not triggered:
            return None

        # Check cooldown
        if self.last_triggered:
            elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
            if elapsed < self.cooldown_minutes:
                return None

        self.last_triggered = datetime.now()

        return Alert.create(
            alert_type=self.alert_type,
            priority=self.priority,
            symbol=self.symbol,
            message=self.message_template.format(
                current=value,
                threshold=self.threshold,
                pct=value * 100 if abs(value) < 1 else value,
            ),
            current_value=value,
            threshold=self.threshold,
            action_suggested=self.action_template.format(
                symbol=self.symbol,
                current=value,
                threshold=self.threshold,
            ) if self.action_template else "",
        )


# Configuration dataclasses for different alert categories


@dataclass
class PriceAlertConfig:
    """Configuration for price-based alerts."""

    symbol: str
    support: float | None = None
    resistance: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    priority: AlertPriority = AlertPriority.HIGH

    def to_rules(self) -> list[AlertRule]:
        """Convert config to AlertRule instances."""
        rules = []

        if self.support is not None:
            rules.append(
                AlertRule(
                    name=f"{self.symbol}_support",
                    alert_type=AlertType.SUPPORT_BREAK,
                    symbol=self.symbol,
                    check=lambda p, s=self.support: (p < s, p),
                    threshold=self.support,
                    priority=self.priority,
                    message_template=f"{{current:.2f}} broke below support ${{threshold:.2f}}",
                    action_template="Consider trimming or setting stop",
                    cooldown_minutes=30,
                )
            )

        if self.resistance is not None:
            rules.append(
                AlertRule(
                    name=f"{self.symbol}_resistance",
                    alert_type=AlertType.RESISTANCE_BREAK,
                    symbol=self.symbol,
                    check=lambda p, r=self.resistance: (p > r, p),
                    threshold=self.resistance,
                    priority=self.priority,
                    message_template=f"{{current:.2f}} broke above resistance ${{threshold:.2f}}",
                    action_template="Consider adding or taking profit",
                    cooldown_minutes=30,
                )
            )

        if self.stop is not None:
            rules.append(
                AlertRule(
                    name=f"{self.symbol}_stop",
                    alert_type=AlertType.STOP_HIT,
                    symbol=self.symbol,
                    check=lambda p, s=self.stop: (p < s, p),
                    threshold=self.stop,
                    priority=AlertPriority.CRITICAL,
                    message_template=f"{{current:.2f}} hit stop loss ${{threshold:.2f}}",
                    action_template="Execute stop loss sell",
                    cooldown_minutes=60,
                )
            )

        if self.take_profit is not None:
            rules.append(
                AlertRule(
                    name=f"{self.symbol}_take_profit",
                    alert_type=AlertType.TAKE_PROFIT_HIT,
                    symbol=self.symbol,
                    check=lambda p, t=self.take_profit: (p > t, p),
                    threshold=self.take_profit,
                    priority=AlertPriority.HIGH,
                    message_template=f"{{current:.2f}} hit take profit ${{threshold:.2f}}",
                    action_template="Consider taking profit",
                    cooldown_minutes=60,
                )
            )

        return rules


@dataclass
class VolumeAlertConfig:
    """Configuration for volume-based alerts."""

    spike_threshold: float = 2.0  # 2x average
    dry_up_threshold: float = 0.3  # 30% of average
    priority: AlertPriority = AlertPriority.MEDIUM


@dataclass
class OptionsAlertConfig:
    """Configuration for options-based alerts."""

    theta_warning_pct: float = 5.0  # Alert if losing >5% to theta today
    expiry_warning_dte: int = 7  # Alert when <7 DTE
    iv_change_threshold: float = 20.0  # Alert on 20%+ IV change
    priority: AlertPriority = AlertPriority.HIGH


@dataclass
class PortfolioAlertConfig:
    """Configuration for portfolio-level alerts."""

    max_position_pct: float = 25.0
    max_sector_pct: float = 50.0
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    pdt_warning_threshold: int = 2  # Alert when 2 day trades remaining
    priority: AlertPriority = AlertPriority.HIGH
