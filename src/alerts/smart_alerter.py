#!/usr/bin/env python3
"""Smart Alerter - Context-aware alerts with convergence detection.

Builds on AlertManager with:
- Signal convergence detection
- Context-aware deduplication
- Multi-signal confirmation
- Smart priority escalation
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import defaultdict

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """A trading signal for convergence tracking."""
    signal_type: str  # signpost, news, technical, sentiment, flow
    symbol: str
    direction: str  # bullish, bearish, neutral
    strength: float  # 0-1
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "strength": self.strength,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class Convergence:
    """A convergence event where multiple signals align."""
    convergence_id: str
    symbol: str
    direction: str
    signal_count: int
    signals: list[Signal]
    average_strength: float
    timestamp: datetime
    recommended_action: str = ""

    def to_dict(self):
        return {
            "convergence_id": self.convergence_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "signal_count": self.signal_count,
            "signals": [s.to_dict() for s in self.signals],
            "average_strength": self.average_strength,
            "timestamp": self.timestamp.isoformat(),
            "recommended_action": self.recommended_action,
        }


class SmartAlerter:
    """Context-aware alerting with convergence detection."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.base / "alerts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Signal buffer for convergence detection
        self.signal_buffer: dict[str, list[Signal]] = defaultdict(list)
        self.signal_window = timedelta(hours=2)

        # Convergence settings
        self.min_signals_for_convergence = 3
        self.min_strength_for_convergence = 0.5

        # Recent convergences (for deduplication)
        self.recent_convergences: list[Convergence] = []
        self.convergence_cooldown = timedelta(hours=4)

        # Alert callbacks
        self.on_convergence_callbacks: list = []

        self._load_state()

    def _load_state(self):
        """Load state from file."""
        state_file = self.cache_dir / "smart_alerter_state.json"
        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)

            # Restore signal buffer
            for symbol, signals in data.get("signals", {}).items():
                for s in signals:
                    self.signal_buffer[symbol].append(Signal(
                        signal_type=s["signal_type"],
                        symbol=s["symbol"],
                        direction=s["direction"],
                        strength=s["strength"],
                        timestamp=datetime.fromisoformat(s["timestamp"]),
                        source=s.get("source", ""),
                        metadata=s.get("metadata", {}),
                    ))

    def _save_state(self):
        """Save state to file."""
        state_file = self.cache_dir / "smart_alerter_state.json"
        with open(state_file, "w") as f:
            json.dump({
                "signals": {
                    symbol: [s.to_dict() for s in signals]
                    for symbol, signals in self.signal_buffer.items()
                },
                "last_update": datetime.now().isoformat(),
            }, f, indent=2)

    def add_signal(self, signal_type: str, symbol: str, direction: str,
                   strength: float, source: str = "", metadata: dict = None) -> Signal:
        """Add a signal to the buffer for convergence tracking."""
        signal = Signal(
            signal_type=signal_type,
            symbol=symbol,
            direction=direction,
            strength=min(1.0, max(0.0, strength)),
            source=source,
            metadata=metadata or {},
        )

        self.signal_buffer[symbol].append(signal)
        self._prune_old_signals()
        self._save_state()

        return signal

    def _prune_old_signals(self):
        """Remove signals older than the window."""
        cutoff = datetime.now() - self.signal_window

        for symbol in list(self.signal_buffer.keys()):
            self.signal_buffer[symbol] = [
                s for s in self.signal_buffer[symbol]
                if s.timestamp > cutoff
            ]
            if not self.signal_buffer[symbol]:
                del self.signal_buffer[symbol]

    def check_convergence(self, symbol: str) -> Optional[Convergence]:
        """Check if signals have converged for a symbol."""
        signals = self.signal_buffer.get(symbol, [])

        if len(signals) < self.min_signals_for_convergence:
            return None

        # Count directions
        directions = defaultdict(list)
        for signal in signals:
            directions[signal.direction].append(signal)

        # Find dominant direction
        for direction, dir_signals in directions.items():
            if len(dir_signals) >= self.min_signals_for_convergence:
                avg_strength = sum(s.strength for s in dir_signals) / len(dir_signals)

                if avg_strength >= self.min_strength_for_convergence:
                    # Check cooldown
                    if self._is_convergence_recent(symbol, direction):
                        return None

                    # Create convergence
                    convergence = Convergence(
                        convergence_id=f"conv_{symbol}_{datetime.now().strftime('%Y%m%d%H%M')}",
                        symbol=symbol,
                        direction=direction,
                        signal_count=len(dir_signals),
                        signals=dir_signals,
                        average_strength=avg_strength,
                        timestamp=datetime.now(),
                        recommended_action=self._get_recommended_action(symbol, direction, avg_strength),
                    )

                    self.recent_convergences.append(convergence)
                    self._save_convergence(convergence)

                    # Clear buffer for this symbol to prevent repeated triggers
                    self.signal_buffer[symbol] = []
                    self._save_state()

                    # Trigger callbacks
                    for callback in self.on_convergence_callbacks:
                        try:
                            callback(convergence)
                        except Exception as e:
                            logger.error(f"Convergence callback error: {e}")

                    return convergence

        return None

    def _is_convergence_recent(self, symbol: str, direction: str) -> bool:
        """Check if similar convergence happened recently."""
        cutoff = datetime.now() - self.convergence_cooldown

        for conv in self.recent_convergences:
            if conv.timestamp > cutoff:
                if conv.symbol == symbol and conv.direction == direction:
                    return True

        return False

    def _get_recommended_action(self, symbol: str, direction: str, strength: float) -> str:
        """Get recommended action based on convergence."""
        if strength > 0.8:
            if direction == "bullish":
                return f"STRONG BUY signal for {symbol} - consider 5% position"
            else:
                return f"STRONG SELL signal for {symbol} - consider exiting/shorting"
        elif strength > 0.6:
            if direction == "bullish":
                return f"Moderate BUY signal for {symbol} - consider 2-3% position"
            else:
                return f"Moderate SELL signal for {symbol} - consider trimming"
        else:
            return f"Weak {direction} signal for {symbol} - monitor closely"

    def _save_convergence(self, convergence: Convergence):
        """Save convergence to history file."""
        history_file = self.cache_dir / "convergence_history.json"

        history = []
        if history_file.exists():
            with open(history_file) as f:
                history = json.load(f)

        history.append(convergence.to_dict())
        history = history[-500:]  # Keep last 500

        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

    def check_all_symbols(self) -> list[Convergence]:
        """Check convergence for all symbols in buffer."""
        convergences = []

        for symbol in list(self.signal_buffer.keys()):
            conv = self.check_convergence(symbol)
            if conv:
                convergences.append(conv)

        return convergences

    def get_signal_summary(self) -> dict:
        """Get summary of current signal buffer."""
        summary = {}

        for symbol, signals in self.signal_buffer.items():
            if not signals:
                continue

            bullish = [s for s in signals if s.direction == "bullish"]
            bearish = [s for s in signals if s.direction == "bearish"]

            summary[symbol] = {
                "total_signals": len(signals),
                "bullish": len(bullish),
                "bearish": len(bearish),
                "avg_bullish_strength": sum(s.strength for s in bullish) / len(bullish) if bullish else 0,
                "avg_bearish_strength": sum(s.strength for s in bearish) / len(bearish) if bearish else 0,
                "signal_types": list(set(s.signal_type for s in signals)),
            }

        return summary

    def on_convergence(self, callback):
        """Register callback for convergence events."""
        self.on_convergence_callbacks.append(callback)

    def get_recent_convergences(self, hours: int = 24) -> list[dict]:
        """Get recent convergence events."""
        history_file = self.cache_dir / "convergence_history.json"

        if not history_file.exists():
            return []

        with open(history_file) as f:
            history = json.load(f)

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return [c for c in history if c.get("timestamp", "") > cutoff]


# Integration functions for existing alert manager
def create_signal_from_signpost(signpost: dict) -> dict:
    """Convert signpost trigger to signal."""
    return {
        "signal_type": "signpost",
        "symbol": signpost.get("symbol"),
        "direction": "bearish" if "below" in signpost.get("description", "").lower() else "bullish",
        "strength": 0.8 if signpost.get("priority") == "critical" else 0.6,
        "source": "signpost_monitor",
        "metadata": signpost,
    }


def create_signal_from_news(news: dict) -> dict:
    """Convert news item to signal."""
    # Simple sentiment from importance
    strength = {"critical": 0.9, "high": 0.7, "medium": 0.5, "low": 0.3}.get(
        news.get("importance", "medium"), 0.5
    )

    return {
        "signal_type": "news",
        "symbol": news.get("symbols_affected", ["SPY"])[0] if news.get("symbols_affected") else "SPY",
        "direction": "neutral",  # Would need NLP to determine
        "strength": strength,
        "source": news.get("source", "unknown"),
        "metadata": {"title": news.get("title", "")},
    }


async def main():
    """Test smart alerter."""
    alerter = SmartAlerter()

    # Register callback
    def on_conv(c):
        print(f"\n*** CONVERGENCE DETECTED ***")
        print(f"Symbol: {c.symbol}, Direction: {c.direction}")
        print(f"Signals: {c.signal_count}, Strength: {c.average_strength:.2f}")
        print(f"Action: {c.recommended_action}")

    alerter.on_convergence(on_conv)

    # Simulate signals
    test_signals = [
        ("signpost", "GLD", "bullish", 0.8, "signpost_monitor"),
        ("news", "GLD", "bullish", 0.7, "reuters"),
        ("technical", "GLD", "bullish", 0.6, "rsi_oversold"),
        ("flow", "GLD", "bullish", 0.75, "options_flow"),
    ]

    for sig_type, symbol, direction, strength, source in test_signals:
        print(f"Adding signal: {sig_type} {symbol} {direction} {strength}")
        alerter.add_signal(sig_type, symbol, direction, strength, source)
        await asyncio.sleep(0.1)

    # Check for convergence
    conv = alerter.check_convergence("GLD")

    # Get summary
    print("\nSignal Summary:")
    print(json.dumps(alerter.get_signal_summary(), indent=2))

    # Get recent convergences
    print(f"\nRecent convergences: {len(alerter.get_recent_convergences(hours=1))}")


if __name__ == "__main__":
    asyncio.run(main())
