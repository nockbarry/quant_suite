#!/usr/bin/env python3
"""Drawdown Protection System - Automatic risk reduction on losses.

Monitors portfolio drawdown and triggers protective actions.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class DrawdownState:
    """Current drawdown state."""
    timestamp: datetime
    portfolio_value: float
    peak_value: float
    drawdown_pct: float
    drawdown_dollars: float
    protection_level: str  # normal, caution, warning, critical
    positions_at_risk: list[str]
    recommended_actions: list[str]

    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_value": self.portfolio_value,
            "peak_value": self.peak_value,
            "drawdown_pct": self.drawdown_pct,
            "drawdown_dollars": self.drawdown_dollars,
            "protection_level": self.protection_level,
            "positions_at_risk": self.positions_at_risk,
            "recommended_actions": self.recommended_actions,
        }


# Drawdown thresholds and actions
PROTECTION_LEVELS = {
    "normal": {
        "threshold": 0.0,
        "max_drawdown": 5.0,
        "actions": [],
    },
    "caution": {
        "threshold": 5.0,
        "max_drawdown": 7.5,
        "actions": ["Tighten stops", "No new positions"],
    },
    "warning": {
        "threshold": 7.5,
        "max_drawdown": 10.0,
        "actions": ["Reduce position sizes by 25%", "Close weakest position"],
    },
    "critical": {
        "threshold": 10.0,
        "max_drawdown": 15.0,
        "actions": ["Reduce to 50% invested", "Close all losing positions"],
    },
    "emergency": {
        "threshold": 15.0,
        "max_drawdown": 100.0,
        "actions": ["Close all positions", "Move to 100% cash"],
    },
}


class DrawdownProtection:
    """Monitor and protect against portfolio drawdowns."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.base / "risk"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.peak_value = 0.0
        self.peak_date: Optional[datetime] = None
        self.current_level = "normal"
        self.history: list[dict] = []

        self._load_state()

    def _load_state(self):
        """Load peak and history from file."""
        state_file = self.cache_dir / "drawdown_state.json"

        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)
            self.peak_value = data.get("peak_value", 0.0)
            self.peak_date = datetime.fromisoformat(data["peak_date"]) if data.get("peak_date") else None
            self.current_level = data.get("current_level", "normal")
            self.history = data.get("history", [])[-100:]  # Keep last 100

    def _save_state(self):
        """Save state to file."""
        state_file = self.cache_dir / "drawdown_state.json"
        with open(state_file, "w") as f:
            json.dump({
                "peak_value": self.peak_value,
                "peak_date": self.peak_date.isoformat() if self.peak_date else None,
                "current_level": self.current_level,
                "history": self.history[-100:],
            }, f, indent=2)

    def update_peak(self, current_value: float) -> bool:
        """Update peak if current value is higher."""
        if current_value > self.peak_value:
            self.peak_value = current_value
            self.peak_date = datetime.now()
            self._save_state()
            return True
        return False

    def calculate_drawdown(self, current_value: float) -> tuple[float, float]:
        """Calculate current drawdown percentage and dollars."""
        if self.peak_value <= 0:
            return 0.0, 0.0

        drawdown_dollars = self.peak_value - current_value
        drawdown_pct = (drawdown_dollars / self.peak_value) * 100

        return max(0.0, drawdown_pct), max(0.0, drawdown_dollars)

    def get_protection_level(self, drawdown_pct: float) -> str:
        """Determine protection level based on drawdown."""
        for level_name in ["emergency", "critical", "warning", "caution", "normal"]:
            level = PROTECTION_LEVELS[level_name]
            if drawdown_pct >= level["threshold"]:
                return level_name
        return "normal"

    def identify_positions_at_risk(self, positions: list[dict]) -> list[str]:
        """Identify positions contributing most to drawdown."""
        # Sort by unrealized P&L (most negative first)
        losing = [p for p in positions if p.get("unrealized_pnl", 0) < 0]
        losing.sort(key=lambda p: p.get("unrealized_pnl", 0))

        return [p.get("symbol", "?") for p in losing[:5]]

    def get_recommended_actions(self, level: str, positions: list[dict]) -> list[str]:
        """Get recommended actions for current protection level."""
        base_actions = PROTECTION_LEVELS.get(level, {}).get("actions", [])
        actions = base_actions.copy()

        if level in ["warning", "critical", "emergency"]:
            # Add specific position recommendations
            at_risk = self.identify_positions_at_risk(positions)
            if at_risk:
                actions.append(f"Consider closing: {', '.join(at_risk[:3])}")

        return actions

    def assess(self, portfolio_value: float, positions: list[dict] = None) -> DrawdownState:
        """Assess current drawdown state."""
        positions = positions or []

        # Update peak if new high
        self.update_peak(portfolio_value)

        # Calculate drawdown
        drawdown_pct, drawdown_dollars = self.calculate_drawdown(portfolio_value)

        # Determine protection level
        new_level = self.get_protection_level(drawdown_pct)

        # Get positions at risk and actions
        positions_at_risk = self.identify_positions_at_risk(positions) if positions else []
        actions = self.get_recommended_actions(new_level, positions)

        # Create state
        state = DrawdownState(
            timestamp=datetime.now(),
            portfolio_value=portfolio_value,
            peak_value=self.peak_value,
            drawdown_pct=drawdown_pct,
            drawdown_dollars=drawdown_dollars,
            protection_level=new_level,
            positions_at_risk=positions_at_risk,
            recommended_actions=actions,
        )

        # Check for level change
        level_changed = new_level != self.current_level
        if level_changed:
            logger.warning(f"Drawdown protection level changed: {self.current_level} -> {new_level}")
            self.current_level = new_level

        # Record history
        self.history.append({
            "timestamp": state.timestamp.isoformat(),
            "drawdown_pct": drawdown_pct,
            "level": new_level,
        })

        self._save_state()

        return state

    def get_max_position_size(self) -> float:
        """Get maximum position size based on protection level."""
        sizes = {
            "normal": 15.0,
            "caution": 10.0,
            "warning": 7.5,
            "critical": 5.0,
            "emergency": 0.0,
        }
        return sizes.get(self.current_level, 15.0)

    def can_open_new_position(self) -> bool:
        """Check if new positions are allowed."""
        return self.current_level in ["normal"]

    def get_target_cash_pct(self) -> float:
        """Get target cash percentage based on protection level."""
        targets = {
            "normal": 10.0,
            "caution": 15.0,
            "warning": 25.0,
            "critical": 50.0,
            "emergency": 100.0,
        }
        return targets.get(self.current_level, 10.0)

    def get_status_report(self) -> str:
        """Get human-readable status report."""
        lines = [
            "Drawdown Protection Status",
            "=" * 40,
            f"Current Level: {self.current_level.upper()}",
            f"Peak Value: ${self.peak_value:,.2f}",
            f"Peak Date: {self.peak_date.strftime('%Y-%m-%d') if self.peak_date else 'N/A'}",
            "",
            "Level Thresholds:",
        ]

        for level_name, level in PROTECTION_LEVELS.items():
            marker = " <--" if level_name == self.current_level else ""
            lines.append(f"  {level_name}: >{level['threshold']:.1f}%{marker}")

        lines.extend([
            "",
            f"Max Position Size: {self.get_max_position_size():.1f}%",
            f"Target Cash: {self.get_target_cash_pct():.1f}%",
            f"Can Open New: {'Yes' if self.can_open_new_position() else 'No'}",
        ])

        return "\n".join(lines)

    def reset_peak(self, new_peak: Optional[float] = None):
        """Reset peak value (use after significant strategy change)."""
        if new_peak:
            self.peak_value = new_peak
        self.peak_date = datetime.now()
        self.current_level = "normal"
        self._save_state()
        logger.info(f"Peak reset to ${self.peak_value:,.2f}")


async def main():
    """Test drawdown protection."""
    protection = DrawdownProtection()

    # Simulate portfolio values
    test_values = [
        (100000, "Initial"),
        (105000, "New high"),
        (102000, "Small pullback"),
        (98000, "5% drawdown"),
        (95000, "Approaching warning"),
        (92000, "Warning level"),
        (88000, "Critical level"),
        (95000, "Recovery"),
        (105000, "New high again"),
    ]

    positions = [
        {"symbol": "SLB", "unrealized_pnl": -500},
        {"symbol": "CEG", "unrealized_pnl": -1200},
        {"symbol": "GLD", "unrealized_pnl": 800},
        {"symbol": "MU", "unrealized_pnl": 300},
    ]

    for value, description in test_values:
        print(f"\n{description}: ${value:,}")
        state = protection.assess(value, positions)
        print(f"  Drawdown: {state.drawdown_pct:.1f}% (${state.drawdown_dollars:,.0f})")
        print(f"  Level: {state.protection_level}")
        if state.recommended_actions:
            print(f"  Actions: {', '.join(state.recommended_actions[:2])}")

    print("\n" + protection.get_status_report())


if __name__ == "__main__":
    asyncio.run(main())
