"""Alert manager for real-time monitoring and notifications.

Provides:
- Configurable alert rules from YAML
- Dynamic alert creation for prices, stops, etc.
- Continuous monitoring loop
- Multiple output channels (console, file, Slack)
- Cooldown management to prevent spam
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
import yfinance as yf

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

# Import AlertChannel from existing monitoring infrastructure
from ..execution.monitoring.dashboard import AlertChannel, ConsoleChannel, FileChannel, SlackChannel

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages alert rules, monitoring, and notifications.

    Features:
    - Load configuration from YAML
    - Add dynamic alerts at runtime
    - Continuous price monitoring
    - Multiple notification channels
    - Cooldown management
    - Alert history and acknowledgement
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        channels: list[AlertChannel] | None = None,
        output_dir: Path | None = None,
    ):
        """
        Initialize AlertManager.

        Args:
            config_path: Path to alerts.yaml configuration
            channels: Alert output channels (default: console + file)
            output_dir: Directory for alert files
        """
        self.config_path = Path(config_path) if config_path else None
        self.output_dir = output_dir

        # Rules and alerts
        self.rules: list[AlertRule] = []
        self.alerts: list[Alert] = []
        self._price_cache: dict[str, tuple[datetime, float]] = {}
        self._cache_ttl = timedelta(seconds=30)

        # Monitoring state
        self._running = False
        self._task: asyncio.Task | None = None

        # Channels
        self.channels = channels or [ConsoleChannel()]
        if output_dir:
            self.channels.append(FileChannel(output_dir / f"alerts_{datetime.now().strftime('%Y-%m-%d')}.json"))

        # Load config if provided
        if self.config_path and self.config_path.exists():
            self._load_config()

        # Configuration objects
        self.volume_config = VolumeAlertConfig()
        self.options_config = OptionsAlertConfig()
        self.portfolio_config = PortfolioAlertConfig()

    def _load_config(self) -> None:
        """Load alert configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)

            alerts_config = config.get("alerts", {})

            # Load price alerts
            price_alerts = alerts_config.get("price_alerts", {})
            for symbol, levels in price_alerts.items():
                if isinstance(levels, dict):
                    price_config = PriceAlertConfig(
                        symbol=symbol,
                        support=levels.get("support"),
                        resistance=levels.get("resistance"),
                        stop=levels.get("stop"),
                        take_profit=levels.get("take_profit"),
                    )
                    self.rules.extend(price_config.to_rules())

            # Load volume config
            volume_config = alerts_config.get("volume", {})
            self.volume_config = VolumeAlertConfig(
                spike_threshold=volume_config.get("spike_threshold", 2.0),
                dry_up_threshold=volume_config.get("dry_up_threshold", 0.3),
            )

            # Load options config
            options_config = alerts_config.get("options", {})
            self.options_config = OptionsAlertConfig(
                theta_warning_pct=options_config.get("theta_warning_pct", 5.0),
                expiry_warning_dte=options_config.get("expiry_warning_dte", 7),
                iv_change_threshold=options_config.get("iv_change_threshold", 20.0),
            )

            # Load portfolio config
            portfolio_config = alerts_config.get("portfolio", {})
            self.portfolio_config = PortfolioAlertConfig(
                max_position_pct=portfolio_config.get("max_position_pct", 25.0),
                max_sector_pct=portfolio_config.get("max_sector_pct", 50.0),
                max_daily_loss_pct=portfolio_config.get("max_daily_loss_pct", 5.0),
                pdt_warning_threshold=portfolio_config.get("pdt_warning_threshold", 2),
            )

            logger.info(f"Loaded {len(self.rules)} alert rules from {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to load alert config: {e}")

    def add_price_alert(
        self,
        symbol: str,
        level: float,
        direction: str,
        priority: AlertPriority = AlertPriority.HIGH,
        cooldown_minutes: int = 15,
    ) -> AlertRule:
        """
        Add a dynamic price alert.

        Args:
            symbol: Stock symbol
            level: Price level to monitor
            direction: "above" or "below"
            priority: Alert priority
            cooldown_minutes: Minutes between repeated alerts

        Returns:
            Created AlertRule
        """
        if direction.lower() == "above":
            alert_type = AlertType.PRICE_ABOVE
            check = lambda p, l=level: (p > l, p)
            msg = f"{{current:.2f}} crossed above ${level:.2f}"
        else:
            alert_type = AlertType.PRICE_BELOW
            check = lambda p, l=level: (p < l, p)
            msg = f"{{current:.2f}} crossed below ${level:.2f}"

        rule = AlertRule(
            name=f"{symbol}_{direction}_{level}",
            alert_type=alert_type,
            symbol=symbol,
            check=check,
            threshold=level,
            priority=priority,
            message_template=msg,
            cooldown_minutes=cooldown_minutes,
        )

        self.rules.append(rule)
        logger.info(f"Added price alert: {symbol} {direction} ${level}")
        return rule

    def add_stop_alert(
        self,
        symbol: str,
        stop_price: float,
        cooldown_minutes: int = 60,
    ) -> AlertRule:
        """
        Add a stop loss alert.

        Args:
            symbol: Stock symbol
            stop_price: Stop loss price
            cooldown_minutes: Minutes between repeated alerts

        Returns:
            Created AlertRule
        """
        rule = AlertRule(
            name=f"{symbol}_stop_{stop_price}",
            alert_type=AlertType.STOP_HIT,
            symbol=symbol,
            check=lambda p, s=stop_price: (p < s, p),
            threshold=stop_price,
            priority=AlertPriority.CRITICAL,
            message_template=f"{{current:.2f}} hit stop loss ${stop_price:.2f}",
            action_template="Execute stop loss sell",
            cooldown_minutes=cooldown_minutes,
        )

        self.rules.append(rule)
        logger.info(f"Added stop alert: {symbol} @ ${stop_price}")
        return rule

    def add_support_alert(
        self,
        symbol: str,
        support_level: float,
        cooldown_minutes: int = 30,
    ) -> AlertRule:
        """Add a support level break alert."""
        rule = AlertRule(
            name=f"{symbol}_support_{support_level}",
            alert_type=AlertType.SUPPORT_BREAK,
            symbol=symbol,
            check=lambda p, s=support_level: (p < s, p),
            threshold=support_level,
            priority=AlertPriority.HIGH,
            message_template=f"{{current:.2f}} broke support ${support_level:.2f}",
            action_template="Consider trimming position",
            cooldown_minutes=cooldown_minutes,
        )

        self.rules.append(rule)
        logger.info(f"Added support alert: {symbol} @ ${support_level}")
        return rule

    def add_resistance_alert(
        self,
        symbol: str,
        resistance_level: float,
        cooldown_minutes: int = 30,
    ) -> AlertRule:
        """Add a resistance level break alert."""
        rule = AlertRule(
            name=f"{symbol}_resistance_{resistance_level}",
            alert_type=AlertType.RESISTANCE_BREAK,
            symbol=symbol,
            check=lambda p, r=resistance_level: (p > r, p),
            threshold=resistance_level,
            priority=AlertPriority.HIGH,
            message_template=f"{{current:.2f}} broke resistance ${resistance_level:.2f}",
            action_template="Consider adding to position",
            cooldown_minutes=cooldown_minutes,
        )

        self.rules.append(rule)
        return rule

    def remove_alert(self, rule_name: str) -> bool:
        """Remove an alert rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"Removed alert rule: {rule_name}")
                return True
        return False

    def disable_alert(self, rule_name: str) -> bool:
        """Disable an alert rule by name."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"Disabled alert rule: {rule_name}")
                return True
        return False

    def enable_alert(self, rule_name: str) -> bool:
        """Enable an alert rule by name."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"Enabled alert rule: {rule_name}")
                return True
        return False

    async def _get_price(self, symbol: str) -> float | None:
        """Get current price for a symbol with caching."""
        # Check cache
        if symbol in self._price_cache:
            cached_time, cached_price = self._price_cache[symbol]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_price

        # Fetch fresh price
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="1m")
            if len(hist) > 0:
                price = float(hist["Close"].iloc[-1])
                self._price_cache[symbol] = (datetime.now(), price)
                return price
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")

        return None

    async def check_all(self) -> list[Alert]:
        """
        Check all alert rules against current prices.

        Returns:
            List of triggered alerts
        """
        triggered = []

        # Get unique symbols
        symbols = set(rule.symbol for rule in self.rules if rule.enabled)

        # Fetch prices
        prices = {}
        for symbol in symbols:
            price = await self._get_price(symbol)
            if price is not None:
                prices[symbol] = price

        # Check each rule
        for rule in self.rules:
            if not rule.enabled:
                continue

            price = prices.get(rule.symbol)
            if price is None:
                continue

            alert = rule.should_alert(price)
            if alert:
                triggered.append(alert)
                self.alerts.append(alert)
                await self._send_alert(alert)

        return triggered

    async def _send_alert(self, alert: Alert) -> None:
        """Send alert through all channels."""
        for channel in self.channels:
            try:
                await channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel.__class__.__name__}: {e}")

    async def start_monitoring(self, interval_seconds: int = 60) -> None:
        """
        Start continuous monitoring loop.

        Args:
            interval_seconds: Seconds between checks
        """
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(interval_seconds))
        logger.info(f"Started alert monitoring (interval: {interval_seconds}s)")

    async def stop_monitoring(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped alert monitoring")

    async def _monitor_loop(self, interval_seconds: int) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                alerts = await self.check_all()
                if alerts:
                    logger.info(f"Triggered {len(alerts)} alerts")
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(5)

    def get_active_alerts(self) -> list[Alert]:
        """Get all unacknowledged alerts."""
        return [a for a in self.alerts if not a.acknowledged]

    def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False

    def acknowledge_all(self) -> int:
        """Acknowledge all active alerts. Returns count."""
        count = 0
        for alert in self.alerts:
            if not alert.acknowledged:
                alert.acknowledged = True
                count += 1
        return count

    def get_alerts_today(self) -> list[Alert]:
        """Get all alerts from today."""
        today = datetime.now().date()
        return [a for a in self.alerts if a.timestamp.date() == today]

    def get_alerts_by_symbol(self, symbol: str) -> list[Alert]:
        """Get all alerts for a specific symbol."""
        return [a for a in self.alerts if a.symbol == symbol]

    def get_alerts_by_type(self, alert_type: AlertType) -> list[Alert]:
        """Get all alerts of a specific type."""
        return [a for a in self.alerts if a.alert_type == alert_type]

    def get_rules(self) -> list[dict[str, Any]]:
        """Get all configured rules."""
        return [
            {
                "name": r.name,
                "type": r.alert_type.value,
                "symbol": r.symbol,
                "threshold": r.threshold,
                "priority": r.priority.value,
                "enabled": r.enabled,
                "cooldown_minutes": r.cooldown_minutes,
                "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None,
            }
            for r in self.rules
        ]

    def save_alerts(self, path: Path | None = None) -> None:
        """Save all alerts to JSON file."""
        output_path = path or (self.output_dir / f"alerts_{datetime.now().strftime('%Y-%m-%d')}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump([a.to_dict() for a in self.alerts], f, indent=2)

        logger.info(f"Saved {len(self.alerts)} alerts to {output_path}")

    def add_channel(self, channel: AlertChannel) -> None:
        """Add an alert channel."""
        self.channels.append(channel)

    def print_status(self) -> None:
        """Print current alert system status."""
        print("\n" + "=" * 60)
        print("ALERT SYSTEM STATUS")
        print("=" * 60)

        print(f"\nRules: {len(self.rules)} configured")
        print(f"  Enabled: {sum(1 for r in self.rules if r.enabled)}")
        print(f"  Disabled: {sum(1 for r in self.rules if not r.enabled)}")

        print(f"\nAlerts: {len(self.alerts)} total")
        print(f"  Today: {len(self.get_alerts_today())}")
        print(f"  Unacknowledged: {len(self.get_active_alerts())}")

        print(f"\nChannels: {len(self.channels)}")
        for ch in self.channels:
            print(f"  - {ch.__class__.__name__}")

        print(f"\nMonitoring: {'ACTIVE' if self._running else 'STOPPED'}")
        print("=" * 60 + "\n")

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        active = self.get_active_alerts()
        today = self.get_alerts_today()

        lines = [
            f"ALERT SUMMARY - {datetime.now().strftime('%H:%M:%S ET')}",
            "=" * 50,
            f"Active Rules: {len(self.rules)}",
            f"Alerts Today: {len(today)}",
            f"Unacknowledged: {len(active)}",
        ]

        if active:
            lines.append("\nACTIVE ALERTS:")
            for alert in active[-5:]:  # Last 5
                lines.append(f"  {alert.format_console()}")

        return "\n".join(lines)
