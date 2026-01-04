"""Monitoring tools for LLM agents.

Provides interfaces for real-time performance monitoring, alerts, and system status.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of alerts."""

    DRAWDOWN = "drawdown"
    LOSS_LIMIT = "loss_limit"
    VOLATILITY = "volatility"
    POSITION_SIZE = "position_size"
    CORRELATION = "correlation"
    REGIME_CHANGE = "regime_change"
    SIGNAL_QUALITY = "signal_quality"
    SYSTEM = "system"


@dataclass
class Alert:
    """Trading system alert."""

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "acknowledged": self.acknowledged,
        }


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot."""

    timestamp: datetime
    equity: float
    daily_return: float
    cumulative_return: float
    drawdown: float
    sharpe_ratio: float
    positions: dict[str, float]
    pending_orders: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": round(self.equity, 2),
            "daily_return_pct": round(self.daily_return * 100, 2),
            "cumulative_return_pct": round(self.cumulative_return * 100, 2),
            "drawdown_pct": round(self.drawdown * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "positions": {k: round(v, 4) for k, v in self.positions.items()},
            "pending_orders": self.pending_orders,
        }


class PerformanceMonitor:
    """Real-time performance monitoring."""

    def __init__(
        self,
        initial_capital: float = 100000,
        alert_manager: "AlertManager | None" = None,
    ):
        """
        Initialize performance monitor.

        Args:
            initial_capital: Starting capital
            alert_manager: Alert manager for notifications
        """
        self.initial_capital = initial_capital
        self.alert_manager = alert_manager or AlertManager()

        # Performance history
        self._equity_history: list[tuple[datetime, float]] = []
        self._returns_history: list[tuple[datetime, float]] = []
        self._positions_history: list[tuple[datetime, dict]] = []
        self._signals_history: list[tuple[datetime, dict]] = []

        # Current state
        self._current_equity = initial_capital
        self._peak_equity = initial_capital
        self._current_positions: dict[str, float] = {}
        self._pending_orders: list[dict] = []

    def update(
        self,
        equity: float | None = None,
        positions: dict[str, float] | None = None,
        signals: list[dict] | None = None,
        timestamp: datetime | None = None,
    ) -> PerformanceSnapshot:
        """
        Update monitor with current state.

        Args:
            equity: Current equity value
            positions: Current positions {symbol: quantity}
            signals: Recent signals
            timestamp: Update timestamp

        Returns:
            Current performance snapshot
        """
        timestamp = timestamp or datetime.now()

        # Update equity
        if equity is not None:
            prev_equity = self._current_equity
            self._current_equity = equity
            self._equity_history.append((timestamp, equity))

            # Calculate return
            daily_return = (equity / prev_equity - 1) if prev_equity > 0 else 0
            self._returns_history.append((timestamp, daily_return))

            # Update peak
            if equity > self._peak_equity:
                self._peak_equity = equity

        # Update positions
        if positions is not None:
            self._current_positions = positions
            self._positions_history.append((timestamp, positions.copy()))

        # Update signals
        if signals is not None:
            for signal in signals:
                self._signals_history.append((timestamp, signal))

        # Check alerts
        self._check_alerts(timestamp)

        return self.get_snapshot(timestamp)

    def get_snapshot(self, timestamp: datetime | None = None) -> PerformanceSnapshot:
        """Get current performance snapshot."""
        timestamp = timestamp or datetime.now()

        # Calculate metrics
        cumulative_return = (self._current_equity / self.initial_capital) - 1
        drawdown = (self._current_equity / self._peak_equity) - 1 if self._peak_equity > 0 else 0

        # Calculate Sharpe (rolling)
        if len(self._returns_history) > 20:
            recent_returns = [r for _, r in self._returns_history[-252:]]
            sharpe = (np.mean(recent_returns) / np.std(recent_returns)) * np.sqrt(252) \
                if np.std(recent_returns) > 0 else 0
        else:
            sharpe = 0

        return PerformanceSnapshot(
            timestamp=timestamp,
            equity=self._current_equity,
            daily_return=self._returns_history[-1][1] if self._returns_history else 0,
            cumulative_return=cumulative_return,
            drawdown=drawdown,
            sharpe_ratio=sharpe,
            positions=self._current_positions.copy(),
            pending_orders=len(self._pending_orders),
        )

    def get_performance_summary(
        self,
        period: str = "all",
    ) -> dict[str, Any]:
        """
        Get performance summary for a period.

        Args:
            period: 'day', 'week', 'month', 'ytd', 'all'

        Returns:
            Performance summary
        """
        if not self._returns_history:
            return {"error": "No performance history"}

        # Filter returns by period
        now = datetime.now()
        returns = pd.Series(
            {t: r for t, r in self._returns_history}
        ).sort_index()

        if period == "day":
            start = now - timedelta(days=1)
        elif period == "week":
            start = now - timedelta(weeks=1)
        elif period == "month":
            start = now - timedelta(days=30)
        elif period == "ytd":
            start = datetime(now.year, 1, 1)
        else:
            start = returns.index[0]

        filtered = returns[returns.index >= start]

        if len(filtered) == 0:
            return {"error": f"No data for period: {period}"}

        # Calculate metrics
        total_return = (1 + filtered).prod() - 1
        annualized = (1 + total_return) ** (252 / max(len(filtered), 1)) - 1
        volatility = filtered.std() * np.sqrt(252)
        sharpe = (filtered.mean() / filtered.std()) * np.sqrt(252) if filtered.std() > 0 else 0

        # Drawdown
        cumulative = (1 + filtered).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = ((cumulative - running_max) / running_max).min()

        return {
            "period": period,
            "start_date": filtered.index[0].strftime("%Y-%m-%d") if hasattr(filtered.index[0], "strftime") else str(filtered.index[0]),
            "end_date": filtered.index[-1].strftime("%Y-%m-%d") if hasattr(filtered.index[-1], "strftime") else str(filtered.index[-1]),
            "trading_days": len(filtered),
            "total_return_pct": round(total_return * 100, 2),
            "annualized_return_pct": round(annualized * 100, 2),
            "volatility_pct": round(volatility * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(drawdown * 100, 2),
            "win_rate_pct": round((filtered > 0).mean() * 100, 1),
            "best_day_pct": round(filtered.max() * 100, 2),
            "worst_day_pct": round(filtered.min() * 100, 2),
        }

    def get_position_summary(self) -> dict[str, Any]:
        """Get current position summary."""
        if not self._current_positions:
            return {"message": "No open positions", "positions": []}

        positions = []
        for symbol, quantity in self._current_positions.items():
            positions.append({
                "symbol": symbol,
                "quantity": quantity,
                "direction": "long" if quantity > 0 else "short",
            })

        return {
            "n_positions": len(positions),
            "positions": positions,
            "gross_exposure": sum(abs(q) for q in self._current_positions.values()),
            "net_exposure": sum(self._current_positions.values()),
        }

    def get_recent_signals(
        self,
        n: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent signals."""
        recent = self._signals_history[-n:]
        return [
            {"timestamp": t.isoformat(), **s}
            for t, s in recent
        ]

    def _check_alerts(self, timestamp: datetime) -> None:
        """Check for alert conditions."""
        snapshot = self.get_snapshot(timestamp)

        # Drawdown alert
        if snapshot.drawdown < -0.10:
            severity = AlertSeverity.CRITICAL if snapshot.drawdown < -0.20 else AlertSeverity.WARNING
            self.alert_manager.create_alert(
                AlertType.DRAWDOWN,
                severity,
                f"Drawdown alert: {snapshot.drawdown*100:.1f}%",
                timestamp,
                {"drawdown": snapshot.drawdown},
            )

        # Daily loss alert
        if snapshot.daily_return < -0.03:
            severity = AlertSeverity.CRITICAL if snapshot.daily_return < -0.05 else AlertSeverity.WARNING
            self.alert_manager.create_alert(
                AlertType.LOSS_LIMIT,
                severity,
                f"Daily loss alert: {snapshot.daily_return*100:.1f}%",
                timestamp,
                {"daily_return": snapshot.daily_return},
            )


class AlertManager:
    """Manages trading system alerts."""

    def __init__(
        self,
        max_alerts: int = 1000,
        alert_callbacks: list[Callable[[Alert], None]] | None = None,
    ):
        """
        Initialize alert manager.

        Args:
            max_alerts: Maximum alerts to store
            alert_callbacks: Callbacks for new alerts
        """
        self.max_alerts = max_alerts
        self._alerts: list[Alert] = []
        self._callbacks = alert_callbacks or []

        # Alert thresholds
        self.thresholds = {
            "drawdown_warning": -0.10,
            "drawdown_critical": -0.20,
            "daily_loss_warning": -0.03,
            "daily_loss_critical": -0.05,
            "volatility_spike": 2.0,  # Multiple of normal
            "position_concentration": 0.25,  # Max single position
        }

    def create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        timestamp: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> Alert:
        """Create and store an alert."""
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=timestamp or datetime.now(),
            details=details or {},
        )

        self._alerts.append(alert)

        # Trim if needed
        if len(self._alerts) > self.max_alerts:
            self._alerts = self._alerts[-self.max_alerts:]

        # Call callbacks
        for callback in self._callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        return alert

    def get_alerts(
        self,
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        since: datetime | None = None,
        unacknowledged_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get filtered alerts.

        Args:
            severity: Filter by severity
            alert_type: Filter by type
            since: Filter by timestamp
            unacknowledged_only: Only unacknowledged alerts

        Returns:
            List of matching alerts
        """
        filtered = self._alerts

        if severity:
            filtered = [a for a in filtered if a.severity == severity]

        if alert_type:
            filtered = [a for a in filtered if a.alert_type == alert_type]

        if since:
            filtered = [a for a in filtered if a.timestamp >= since]

        if unacknowledged_only:
            filtered = [a for a in filtered if not a.acknowledged]

        return [a.to_dict() for a in filtered]

    def acknowledge_alert(self, index: int) -> bool:
        """Acknowledge an alert by index."""
        if 0 <= index < len(self._alerts):
            self._alerts[index].acknowledged = True
            return True
        return False

    def get_alert_summary(self) -> dict[str, Any]:
        """Get alert summary."""
        by_severity = {}
        by_type = {}

        for alert in self._alerts:
            sev = alert.severity.value
            typ = alert.alert_type.value

            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_type[typ] = by_type.get(typ, 0) + 1

        unacknowledged = sum(1 for a in self._alerts if not a.acknowledged)

        return {
            "total_alerts": len(self._alerts),
            "unacknowledged": unacknowledged,
            "by_severity": by_severity,
            "by_type": by_type,
            "recent": [a.to_dict() for a in self._alerts[-5:]],
        }

    def check_risk_limits(
        self,
        equity: float,
        positions: dict[str, float],
        daily_pnl: float,
    ) -> list[Alert]:
        """
        Check risk limits and generate alerts.

        Args:
            equity: Current equity
            positions: Current positions
            daily_pnl: Daily P&L

        Returns:
            List of triggered alerts
        """
        alerts = []
        timestamp = datetime.now()

        # Daily loss limit
        if equity > 0 and daily_pnl / equity < self.thresholds["daily_loss_critical"]:
            alerts.append(self.create_alert(
                AlertType.LOSS_LIMIT,
                AlertSeverity.CRITICAL,
                f"Critical daily loss: {daily_pnl/equity*100:.1f}%",
                timestamp,
                {"daily_pnl": daily_pnl, "equity": equity},
            ))
        elif equity > 0 and daily_pnl / equity < self.thresholds["daily_loss_warning"]:
            alerts.append(self.create_alert(
                AlertType.LOSS_LIMIT,
                AlertSeverity.WARNING,
                f"Daily loss warning: {daily_pnl/equity*100:.1f}%",
                timestamp,
            ))

        # Position concentration
        if positions and equity > 0:
            for symbol, value in positions.items():
                concentration = abs(value) / equity
                if concentration > self.thresholds["position_concentration"]:
                    alerts.append(self.create_alert(
                        AlertType.POSITION_SIZE,
                        AlertSeverity.WARNING,
                        f"Position concentration: {symbol} is {concentration*100:.1f}% of portfolio",
                        timestamp,
                        {"symbol": symbol, "concentration": concentration},
                    ))

        return alerts


class SystemStatusMonitor:
    """Monitor overall system health."""

    def __init__(self):
        """Initialize system monitor."""
        self._component_status: dict[str, dict] = {}
        self._last_heartbeats: dict[str, datetime] = {}
        self._error_counts: dict[str, int] = {}

    def register_component(self, name: str, **metadata) -> None:
        """Register a system component."""
        self._component_status[name] = {
            "status": "unknown",
            "metadata": metadata,
            "last_update": None,
        }

    def update_component(
        self,
        name: str,
        status: str,
        message: str | None = None,
    ) -> None:
        """Update component status."""
        if name not in self._component_status:
            self.register_component(name)

        self._component_status[name].update({
            "status": status,
            "message": message,
            "last_update": datetime.now(),
        })
        self._last_heartbeats[name] = datetime.now()

    def record_error(self, component: str, error: str) -> None:
        """Record component error."""
        self._error_counts[component] = self._error_counts.get(component, 0) + 1
        self.update_component(component, "error", error)

    def get_status(self) -> dict[str, Any]:
        """Get overall system status."""
        now = datetime.now()

        # Check for stale components
        stale_threshold = timedelta(minutes=5)
        stale_components = []

        for name, last_hb in self._last_heartbeats.items():
            if now - last_hb > stale_threshold:
                stale_components.append(name)

        # Determine overall status
        statuses = [c.get("status", "unknown") for c in self._component_status.values()]

        if "error" in statuses or stale_components:
            overall = "degraded"
        elif all(s == "healthy" for s in statuses):
            overall = "healthy"
        else:
            overall = "unknown"

        return {
            "overall_status": overall,
            "timestamp": now.isoformat(),
            "components": {
                name: {
                    "status": info["status"],
                    "message": info.get("message"),
                    "last_update": info["last_update"].isoformat() if info["last_update"] else None,
                }
                for name, info in self._component_status.items()
            },
            "stale_components": stale_components,
            "error_counts": self._error_counts,
        }


# Convenience functions
def get_live_performance(
    monitor: PerformanceMonitor,
    period: str = "day",
) -> dict[str, Any]:
    """
    Get live performance metrics.

    Args:
        monitor: Performance monitor instance
        period: Time period

    Returns:
        Performance metrics
    """
    snapshot = monitor.get_snapshot()
    summary = monitor.get_performance_summary(period)

    return {
        "success": True,
        "data": {
            "current": snapshot.to_dict(),
            "period_summary": summary,
        },
    }


def get_position_summary(monitor: PerformanceMonitor) -> dict[str, Any]:
    """Get current position summary."""
    return {
        "success": True,
        "data": monitor.get_position_summary(),
    }


def check_risk_limits(
    alert_manager: AlertManager,
    equity: float,
    positions: dict[str, float],
    daily_pnl: float,
) -> dict[str, Any]:
    """
    Check risk limits and return any alerts.

    Args:
        alert_manager: Alert manager
        equity: Current equity
        positions: Current positions
        daily_pnl: Daily P&L

    Returns:
        Risk check results
    """
    alerts = alert_manager.check_risk_limits(equity, positions, daily_pnl)

    return {
        "success": True,
        "data": {
            "n_alerts": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
            "risk_status": "critical" if any(a.severity == AlertSeverity.CRITICAL for a in alerts)
                else "warning" if alerts else "ok",
        },
    }


def get_recent_signals(
    monitor: PerformanceMonitor,
    n: int = 10,
) -> dict[str, Any]:
    """Get recent trading signals."""
    return {
        "success": True,
        "data": {
            "signals": monitor.get_recent_signals(n),
        },
    }


def get_system_status(
    system_monitor: SystemStatusMonitor,
) -> dict[str, Any]:
    """Get overall system status."""
    return {
        "success": True,
        "data": system_monitor.get_status(),
    }
