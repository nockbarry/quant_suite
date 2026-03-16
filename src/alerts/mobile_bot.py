#!/usr/bin/env python3
"""Mobile Alert Bot - Telegram and Discord integration for real-time alerts.

Sends trading alerts to mobile devices via Telegram or Discord webhooks.

Setup:
1. Telegram: Create bot via @BotFather, get token, start chat, get chat_id
2. Discord: Create webhook URL in server settings

Configuration in ~/quant_results/config/mobile_alerts.yaml:
    telegram:
      enabled: true
      bot_token: "YOUR_BOT_TOKEN"
      chat_id: "YOUR_CHAT_ID"
    discord:
      enabled: true
      webhook_url: "YOUR_WEBHOOK_URL"
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

import httpx
import yaml

from src.core.paths import paths

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class MobileAlert:
    """Alert to send to mobile devices."""
    title: str
    message: str
    level: AlertLevel
    symbols: list[str]
    action_required: str = ""
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_telegram_message(self) -> str:
        """Format for Telegram."""
        emoji = {
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.HIGH: "⚠️",
            AlertLevel.MEDIUM: "📊",
            AlertLevel.LOW: "ℹ️",
        }.get(self.level, "📌")

        msg = f"{emoji} *{self.title}*\n\n"
        msg += f"{self.message}\n"

        if self.symbols:
            msg += f"\n*Symbols:* {', '.join(self.symbols)}"

        if self.action_required:
            msg += f"\n\n*Action:* {self.action_required}"

        msg += f"\n\n_{self.timestamp.strftime('%H:%M:%S ET')}_"

        return msg

    def to_discord_embed(self) -> dict:
        """Format for Discord."""
        color = {
            AlertLevel.CRITICAL: 0xFF0000,
            AlertLevel.HIGH: 0xFFA500,
            AlertLevel.MEDIUM: 0x0000FF,
            AlertLevel.LOW: 0x808080,
        }.get(self.level, 0x808080)

        embed = {
            "title": f"{self.level.value.upper()}: {self.title}",
            "description": self.message,
            "color": color,
            "timestamp": self.timestamp.isoformat(),
            "fields": [],
        }

        if self.symbols:
            embed["fields"].append({
                "name": "Symbols",
                "value": ", ".join(self.symbols),
                "inline": True,
            })

        if self.action_required:
            embed["fields"].append({
                "name": "Action Required",
                "value": self.action_required,
                "inline": False,
            })

        return embed


class MobileAlertBot:
    """Send alerts to Telegram and Discord."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or paths.base / "config" / "mobile_alerts.yaml"
        self.config = self._load_config()
        self.client = httpx.AsyncClient(timeout=30)

        # Rate limiting
        self.last_alert_time: dict[str, datetime] = {}
        self.min_interval_seconds = 60  # Don't spam same alert

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}

        # Create default config
        default_config = {
            "telegram": {
                "enabled": False,
                "bot_token": "YOUR_BOT_TOKEN_HERE",
                "chat_id": "YOUR_CHAT_ID_HERE",
            },
            "discord": {
                "enabled": False,
                "webhook_url": "YOUR_WEBHOOK_URL_HERE",
            },
            "settings": {
                "min_level": "medium",  # Only send medium+ alerts
                "quiet_hours": {"start": 22, "end": 6},  # 10pm-6am
                "rate_limit_seconds": 60,
            }
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)

        logger.info(f"Created default config at {self.config_path}")
        return default_config

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    def _should_send(self, alert: MobileAlert) -> bool:
        """Check if alert should be sent (rate limiting, quiet hours, level)."""
        # Check minimum level
        min_level = self.config.get("settings", {}).get("min_level", "medium")
        level_order = ["low", "medium", "high", "critical"]
        if level_order.index(alert.level.value) < level_order.index(min_level):
            return False

        # Check quiet hours (unless critical)
        if alert.level != AlertLevel.CRITICAL:
            quiet = self.config.get("settings", {}).get("quiet_hours", {})
            hour = datetime.now().hour
            start = quiet.get("start", 22)
            end = quiet.get("end", 6)

            if start > end:  # Spans midnight
                if hour >= start or hour < end:
                    logger.debug("Skipping alert during quiet hours")
                    return False
            elif start <= hour < end:
                logger.debug("Skipping alert during quiet hours")
                return False

        # Check rate limiting
        key = f"{alert.title}:{','.join(alert.symbols)}"
        last_time = self.last_alert_time.get(key)
        if last_time:
            elapsed = (datetime.now() - last_time).total_seconds()
            min_interval = self.config.get("settings", {}).get("rate_limit_seconds", 60)
            if elapsed < min_interval:
                logger.debug(f"Rate limiting alert: {key}")
                return False

        self.last_alert_time[key] = datetime.now()
        return True

    async def send_telegram(self, alert: MobileAlert) -> bool:
        """Send alert to Telegram."""
        config = self.config.get("telegram", {})
        if not config.get("enabled"):
            return False

        token = config.get("bot_token", "")
        chat_id = config.get("chat_id", "")

        if not token or not chat_id or "YOUR_" in token:
            logger.debug("Telegram not configured")
            return False

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = await self.client.post(url, json={
                "chat_id": chat_id,
                "text": alert.to_telegram_message(),
                "parse_mode": "Markdown",
            })

            if response.status_code == 200:
                logger.info(f"Telegram alert sent: {alert.title}")
                return True
            else:
                logger.error(f"Telegram error: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def send_discord(self, alert: MobileAlert) -> bool:
        """Send alert to Discord."""
        config = self.config.get("discord", {})
        if not config.get("enabled"):
            return False

        webhook_url = config.get("webhook_url", "")
        if not webhook_url or "YOUR_" in webhook_url:
            logger.debug("Discord not configured")
            return False

        try:
            response = await self.client.post(webhook_url, json={
                "embeds": [alert.to_discord_embed()],
            })

            if response.status_code in [200, 204]:
                logger.info(f"Discord alert sent: {alert.title}")
                return True
            else:
                logger.error(f"Discord error: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return False

    async def send_alert(self, alert: MobileAlert) -> dict:
        """Send alert to all configured channels."""
        if not self._should_send(alert):
            return {"sent": False, "reason": "filtered"}

        results = {
            "telegram": await self.send_telegram(alert),
            "discord": await self.send_discord(alert),
        }

        results["sent"] = any(results.values())
        return results

    # Convenience methods for common alert types

    async def signpost_alert(self, symbol: str, level: float, price: float,
                            description: str, action: str):
        """Send signpost triggered alert."""
        alert = MobileAlert(
            title=f"Signpost: {symbol}",
            message=f"{description}\nPrice: ${price:.2f} (level: ${level:.2f})",
            level=AlertLevel.CRITICAL if "EXIT" in action.upper() else AlertLevel.HIGH,
            symbols=[symbol],
            action_required=action,
        )
        return await self.send_alert(alert)

    async def trade_alert(self, action: str, symbol: str, qty: int,
                         price: float, reason: str):
        """Send trade execution alert."""
        alert = MobileAlert(
            title=f"Trade: {action} {qty} {symbol}",
            message=f"{action} {qty} shares @ ${price:.2f}\n{reason}",
            level=AlertLevel.HIGH,
            symbols=[symbol],
        )
        return await self.send_alert(alert)

    async def convergence_alert(self, symbol: str, direction: str,
                               signal_count: int, strength: float):
        """Send signal convergence alert."""
        alert = MobileAlert(
            title=f"Convergence: {symbol}",
            message=f"{signal_count} signals aligned {direction}\nStrength: {strength:.0%}",
            level=AlertLevel.CRITICAL,
            symbols=[symbol],
            action_required=f"Review {symbol} for {direction} opportunity",
        )
        return await self.send_alert(alert)

    async def drawdown_alert(self, level: str, drawdown_pct: float,
                            actions: list[str]):
        """Send drawdown protection alert."""
        alert = MobileAlert(
            title=f"Drawdown: {level.upper()}",
            message=f"Portfolio drawdown: {drawdown_pct:.1f}%",
            level=AlertLevel.CRITICAL if level in ["critical", "emergency"] else AlertLevel.HIGH,
            symbols=[],
            action_required="\n".join(actions[:3]),
        )
        return await self.send_alert(alert)

    async def market_alert(self, title: str, message: str, symbols: list[str] = None):
        """Send general market alert."""
        alert = MobileAlert(
            title=title,
            message=message,
            level=AlertLevel.MEDIUM,
            symbols=symbols or [],
        )
        return await self.send_alert(alert)


# Integration with existing alert system
async def send_mobile_alert(title: str, message: str, level: str = "medium",
                           symbols: list[str] = None, action: str = ""):
    """Convenience function to send a mobile alert."""
    bot = MobileAlertBot()
    try:
        alert = MobileAlert(
            title=title,
            message=message,
            level=AlertLevel(level),
            symbols=symbols or [],
            action_required=action,
        )
        return await bot.send_alert(alert)
    finally:
        await bot.close()


async def main():
    """Test mobile alerts."""
    bot = MobileAlertBot()

    print(f"Config loaded from: {bot.config_path}")
    print(f"Telegram enabled: {bot.config.get('telegram', {}).get('enabled')}")
    print(f"Discord enabled: {bot.config.get('discord', {}).get('enabled')}")

    # Test alert
    alert = MobileAlert(
        title="Test Alert",
        message="This is a test alert from Project Athena",
        level=AlertLevel.HIGH,
        symbols=["SPY", "QQQ"],
        action_required="No action needed - just testing",
    )

    print(f"\nTelegram message:\n{alert.to_telegram_message()}")
    print(f"\nDiscord embed:\n{json.dumps(alert.to_discord_embed(), indent=2)}")

    # Uncomment to actually send:
    # result = await bot.send_alert(alert)
    # print(f"\nSend result: {result}")

    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
