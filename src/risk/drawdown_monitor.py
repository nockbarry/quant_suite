"""Intraday Drawdown Monitor.

Monitors portfolio and position drawdowns in real-time:
- Portfolio high-water mark tracking
- Position-level drawdown alerts
- Intraday vs inception drawdowns
- Automatic stop-loss suggestions

Created: 2026-01-20
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class DrawdownState:
    """Current drawdown state for a position or portfolio."""

    symbol: str  # "PORTFOLIO" for portfolio-level
    current_value: float
    high_water_mark: float
    high_water_date: datetime

    current_drawdown_pct: float
    max_drawdown_pct: float  # Worst drawdown since inception
    max_drawdown_date: Optional[datetime]

    intraday_high: float
    intraday_low: float
    intraday_drawdown_pct: float

    alert_triggered: bool = False
    alert_level: str = "none"  # none, warning, critical

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_value": self.current_value,
            "high_water_mark": self.high_water_mark,
            "high_water_date": self.high_water_date.isoformat(),
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_date": self.max_drawdown_date.isoformat() if self.max_drawdown_date else None,
            "intraday_high": self.intraday_high,
            "intraday_low": self.intraday_low,
            "intraday_drawdown_pct": self.intraday_drawdown_pct,
            "alert_triggered": self.alert_triggered,
            "alert_level": self.alert_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DrawdownState":
        data["high_water_date"] = datetime.fromisoformat(data["high_water_date"])
        if data.get("max_drawdown_date"):
            data["max_drawdown_date"] = datetime.fromisoformat(data["max_drawdown_date"])
        return cls(**data)


@dataclass
class DrawdownAlert:
    """Alert for significant drawdown."""

    timestamp: datetime
    symbol: str
    alert_level: str  # warning, critical
    drawdown_pct: float
    message: str
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "alert_level": self.alert_level,
            "drawdown_pct": self.drawdown_pct,
            "message": self.message,
            "suggested_action": self.suggested_action,
        }


class DrawdownMonitor:
    """Monitor drawdowns in real-time.

    Alert thresholds:
    - Portfolio warning: 3% drawdown
    - Portfolio critical: 5% drawdown
    - Position warning: 5% drawdown
    - Position critical: 10% drawdown
    """

    # Alert thresholds
    PORTFOLIO_WARNING_PCT = 3.0
    PORTFOLIO_CRITICAL_PCT = 5.0
    POSITION_WARNING_PCT = 5.0
    POSITION_CRITICAL_PCT = 10.0

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (paths.live / "drawdown")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.state_file = self.storage_path / "drawdown_state.json"
        self.alerts_file = self.storage_path / "drawdown_alerts.json"

        self._states: dict[str, DrawdownState] = {}
        self._today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def _load_states(self):
        """Load persisted states."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                for symbol, state_dict in data.items():
                    self._states[symbol] = DrawdownState.from_dict(state_dict)
            except Exception as e:
                logger.warning(f"Failed to load drawdown states: {e}")

    def _save_states(self):
        """Save states to disk."""
        with open(self.state_file, "w") as f:
            json.dump({s: st.to_dict() for s, st in self._states.items()}, f, indent=2)

    def _reset_intraday_if_new_day(self):
        """Reset intraday tracking at start of new day."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if today_start > self._today_start:
            self._today_start = today_start
            for state in self._states.values():
                state.intraday_high = state.current_value
                state.intraday_low = state.current_value
                state.intraday_drawdown_pct = 0.0
                state.alert_triggered = False
                state.alert_level = "none"
            logger.info("Reset intraday drawdown tracking for new day")

    def update(
        self,
        symbol: str,
        current_value: float,
        is_portfolio: bool = False,
    ) -> Optional[DrawdownAlert]:
        """Update drawdown state and check for alerts.

        Args:
            symbol: Symbol or "PORTFOLIO"
            current_value: Current value (portfolio equity or position value)
            is_portfolio: True if this is portfolio-level

        Returns:
            DrawdownAlert if alert triggered, None otherwise
        """
        self._reset_intraday_if_new_day()

        now = datetime.now()
        alert = None

        if symbol not in self._states:
            # Initialize new state
            self._states[symbol] = DrawdownState(
                symbol=symbol,
                current_value=current_value,
                high_water_mark=current_value,
                high_water_date=now,
                current_drawdown_pct=0.0,
                max_drawdown_pct=0.0,
                max_drawdown_date=None,
                intraday_high=current_value,
                intraday_low=current_value,
                intraday_drawdown_pct=0.0,
            )
            self._save_states()
            return None

        state = self._states[symbol]
        state.current_value = current_value

        # Update high water mark
        if current_value > state.high_water_mark:
            state.high_water_mark = current_value
            state.high_water_date = now

        # Calculate current drawdown from HWM
        if state.high_water_mark > 0:
            state.current_drawdown_pct = (
                (state.high_water_mark - current_value) / state.high_water_mark
            ) * 100

        # Update max drawdown
        if state.current_drawdown_pct > state.max_drawdown_pct:
            state.max_drawdown_pct = state.current_drawdown_pct
            state.max_drawdown_date = now

        # Update intraday tracking
        if current_value > state.intraday_high:
            state.intraday_high = current_value
        if current_value < state.intraday_low:
            state.intraday_low = current_value

        # Calculate intraday drawdown from today's high
        if state.intraday_high > 0:
            state.intraday_drawdown_pct = (
                (state.intraday_high - current_value) / state.intraday_high
            ) * 100

        # Check for alerts
        if is_portfolio:
            warning_threshold = self.PORTFOLIO_WARNING_PCT
            critical_threshold = self.PORTFOLIO_CRITICAL_PCT
        else:
            warning_threshold = self.POSITION_WARNING_PCT
            critical_threshold = self.POSITION_CRITICAL_PCT

        new_alert_level = "none"
        if state.current_drawdown_pct >= critical_threshold:
            new_alert_level = "critical"
        elif state.current_drawdown_pct >= warning_threshold:
            new_alert_level = "warning"

        # Only alert if level increased
        alert_levels = ["none", "warning", "critical"]
        if alert_levels.index(new_alert_level) > alert_levels.index(state.alert_level):
            state.alert_level = new_alert_level
            state.alert_triggered = True

            if new_alert_level == "critical":
                suggested = "Consider reducing position size or setting stop-loss"
            else:
                suggested = "Monitor closely for further deterioration"

            alert = DrawdownAlert(
                timestamp=now,
                symbol=symbol,
                alert_level=new_alert_level,
                drawdown_pct=state.current_drawdown_pct,
                message=f"{symbol} drawdown at {state.current_drawdown_pct:.1f}% from HWM",
                suggested_action=suggested,
            )

            # Save alert
            self._save_alert(alert)

        self._save_states()
        return alert

    def _save_alert(self, alert: DrawdownAlert):
        """Save alert to history."""
        alerts = []
        if self.alerts_file.exists():
            with open(self.alerts_file) as f:
                alerts = json.load(f)

        alerts.append(alert.to_dict())

        # Keep last 100 alerts
        alerts = alerts[-100:]

        with open(self.alerts_file, "w") as f:
            json.dump(alerts, f, indent=2)

    def get_state(self, symbol: str) -> Optional[DrawdownState]:
        """Get drawdown state for symbol."""
        self._load_states()
        return self._states.get(symbol)

    def get_all_states(self) -> dict[str, DrawdownState]:
        """Get all drawdown states."""
        self._load_states()
        return self._states

    def get_portfolio_state(self) -> Optional[DrawdownState]:
        """Get portfolio drawdown state."""
        return self.get_state("PORTFOLIO")

    def get_recent_alerts(self, hours: int = 24) -> list[DrawdownAlert]:
        """Get recent alerts."""
        if not self.alerts_file.exists():
            return []

        with open(self.alerts_file) as f:
            alerts = json.load(f)

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        recent = [
            DrawdownAlert(
                timestamp=datetime.fromisoformat(a["timestamp"]),
                symbol=a["symbol"],
                alert_level=a["alert_level"],
                drawdown_pct=a["drawdown_pct"],
                message=a["message"],
                suggested_action=a["suggested_action"],
            )
            for a in alerts
            if a.get("timestamp", "") > cutoff
        ]

        return recent

    def get_summary(self) -> dict:
        """Get summary of all drawdown states."""
        self._load_states()

        if not self._states:
            return {"status": "no_data"}

        portfolio_state = self._states.get("PORTFOLIO")
        position_states = {s: st for s, st in self._states.items() if s != "PORTFOLIO"}

        # Worst position
        if position_states:
            worst_pos = max(position_states.values(), key=lambda x: x.current_drawdown_pct)
        else:
            worst_pos = None

        return {
            "timestamp": datetime.now().isoformat(),
            "portfolio": portfolio_state.to_dict() if portfolio_state else None,
            "positions_in_drawdown": len([
                s for s in position_states.values()
                if s.current_drawdown_pct > 2.0
            ]),
            "worst_position": worst_pos.symbol if worst_pos else None,
            "worst_position_drawdown_pct": worst_pos.current_drawdown_pct if worst_pos else 0.0,
            "critical_alerts": len([
                s for s in self._states.values()
                if s.alert_level == "critical"
            ]),
        }


# Convenience function
def get_drawdown_summary() -> dict:
    """Get current drawdown summary."""
    monitor = DrawdownMonitor()
    return monitor.get_summary()


if __name__ == "__main__":
    monitor = DrawdownMonitor()

    # Simulate portfolio tracking
    print("=== Drawdown Monitor Demo ===\n")

    # Initial value
    monitor.update("PORTFOLIO", 100000, is_portfolio=True)
    print("Initial: $100,000")

    # Small decline
    alert = monitor.update("PORTFOLIO", 98000, is_portfolio=True)
    print(f"After decline: $98,000 (2% drawdown)")
    if alert:
        print(f"  ALERT: {alert.message}")

    # Further decline - warning
    alert = monitor.update("PORTFOLIO", 96500, is_portfolio=True)
    print(f"Further decline: $96,500 (3.5% drawdown)")
    if alert:
        print(f"  ALERT: {alert.message}")

    # Critical level
    alert = monitor.update("PORTFOLIO", 94000, is_portfolio=True)
    print(f"Critical: $94,000 (6% drawdown)")
    if alert:
        print(f"  ALERT: {alert.message}")

    # Print summary
    print("\nSummary:")
    summary = monitor.get_summary()
    if summary.get("portfolio"):
        p = summary["portfolio"]
        print(f"  Current Drawdown: {p['current_drawdown_pct']:.1f}%")
        print(f"  Max Drawdown: {p['max_drawdown_pct']:.1f}%")
        print(f"  Intraday DD: {p['intraday_drawdown_pct']:.1f}%")
        print(f"  Alert Level: {p['alert_level']}")
