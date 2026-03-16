"""
Signal Quality Tracker - Track which signals lead to good trades.

Measures:
- Hit rate: % of signals that were profitable when acted on
- IC (Information Coefficient): Correlation between signal and outcome
- Average P&L when signal is followed
- Trend over time (improving, stable, degrading)

Used by the improvement tracker for weekly reviews.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.paths import paths
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SignalQuality:
    """Quality metrics for a single signal type."""
    signal_type: str
    total_signals: int  # Total signals generated
    acted_on: int  # How many were acted on (trades made)
    profitable: int  # How many were profitable
    hit_rate: float  # % profitable when acted on
    avg_pnl: float  # Average P&L when acted on
    avg_pnl_pct: float  # Average P&L % when acted on
    ic: float  # Information coefficient
    trend: str  # "improving", "stable", "degrading"
    last_updated: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "total_signals": self.total_signals,
            "acted_on": self.acted_on,
            "profitable": self.profitable,
            "hit_rate": self.hit_rate,
            "avg_pnl": self.avg_pnl,
            "avg_pnl_pct": self.avg_pnl_pct,
            "ic": self.ic,
            "trend": self.trend,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalQuality":
        return cls(
            signal_type=data["signal_type"],
            total_signals=data["total_signals"],
            acted_on=data["acted_on"],
            profitable=data["profitable"],
            hit_rate=data["hit_rate"],
            avg_pnl=data["avg_pnl"],
            avg_pnl_pct=data["avg_pnl_pct"],
            ic=data["ic"],
            trend=data["trend"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SignalOutcome:
    """Record of a signal and its outcome."""
    signal_type: str
    symbol: str
    direction: str  # "bullish" or "bearish"
    signal_strength: float
    signal_timestamp: datetime
    acted_on: bool
    trade_timestamp: datetime | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    hold_days: int | None = None

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "signal_strength": self.signal_strength,
            "signal_timestamp": self.signal_timestamp.isoformat(),
            "acted_on": self.acted_on,
            "trade_timestamp": self.trade_timestamp.isoformat() if self.trade_timestamp else None,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "hold_days": self.hold_days,
        }


class SignalQualityTracker:
    """
    Tracks signal quality over time.

    File structure:
    ~/quant_results/signal_quality/
        quality.json         - Current quality metrics by signal type
        outcomes.jsonl       - Individual signal outcomes log
    """

    SIGNAL_TYPES = [
        "technical",
        "congressional",
        "insider",
        "options",
        "squeeze",
        "sentiment",
        "social",
    ]

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.quality_dir = self.results_dir / "signal_quality"
        self.quality_file = self.quality_dir / "quality.json"
        self.outcomes_file = self.quality_dir / "outcomes.jsonl"

        # Ensure directory exists
        self.quality_dir.mkdir(parents=True, exist_ok=True)

        # Load current quality metrics
        self.quality: dict[str, SignalQuality] = {}
        self._load_quality()

    def _load_quality(self) -> None:
        """Load quality metrics from file."""
        if self.quality_file.exists():
            try:
                with open(self.quality_file) as f:
                    data = json.load(f)
                    for item in data.get("signals", []):
                        quality = SignalQuality.from_dict(item)
                        self.quality[quality.signal_type] = quality
            except Exception as e:
                logger.error(f"Error loading quality metrics: {e}")

    def _save_quality(self) -> None:
        """Save quality metrics to file."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "signals": [q.to_dict() for q in self.quality.values()],
            }
            with open(self.quality_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving quality metrics: {e}")

    def log_outcome(
        self,
        signal_type: str,
        symbol: str,
        direction: str,
        signal_strength: float,
        acted_on: bool,
        pnl: float | None = None,
        pnl_pct: float | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        hold_days: int | None = None,
    ) -> SignalOutcome:
        """Log a signal outcome."""
        outcome = SignalOutcome(
            signal_type=signal_type,
            symbol=symbol,
            direction=direction,
            signal_strength=signal_strength,
            signal_timestamp=datetime.now(),
            acted_on=acted_on,
            trade_timestamp=datetime.now() if acted_on else None,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
        )

        # Append to outcomes file
        try:
            with open(self.outcomes_file, "a") as f:
                f.write(json.dumps(outcome.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Error logging outcome: {e}")

        return outcome

    def calculate_quality(self, days: int = 30) -> dict[str, SignalQuality]:
        """Calculate quality metrics for all signal types."""
        cutoff = datetime.now() - timedelta(days=days)

        # Load outcomes
        outcomes: list[SignalOutcome] = []
        if self.outcomes_file.exists():
            try:
                with open(self.outcomes_file) as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            timestamp = datetime.fromisoformat(data["signal_timestamp"])
                            if timestamp >= cutoff:
                                # Create outcome object
                                outcomes.append(SignalOutcome(
                                    signal_type=data["signal_type"],
                                    symbol=data["symbol"],
                                    direction=data["direction"],
                                    signal_strength=data["signal_strength"],
                                    signal_timestamp=timestamp,
                                    acted_on=data["acted_on"],
                                    pnl=data.get("pnl"),
                                    pnl_pct=data.get("pnl_pct"),
                                ))
                        except (json.JSONDecodeError, ValueError, KeyError):
                            continue
            except Exception as e:
                logger.error(f"Error reading outcomes: {e}")

        # Group by signal type
        by_type: dict[str, list[SignalOutcome]] = {}
        for outcome in outcomes:
            if outcome.signal_type not in by_type:
                by_type[outcome.signal_type] = []
            by_type[outcome.signal_type].append(outcome)

        # Calculate metrics for each type
        quality_metrics = {}
        for signal_type, type_outcomes in by_type.items():
            total = len(type_outcomes)
            acted = [o for o in type_outcomes if o.acted_on]
            profitable = [o for o in acted if o.pnl and o.pnl > 0]

            hit_rate = len(profitable) / len(acted) if acted else 0
            avg_pnl = np.mean([o.pnl for o in acted if o.pnl]) if acted else 0
            avg_pnl_pct = np.mean([o.pnl_pct for o in acted if o.pnl_pct]) if acted else 0

            # Calculate IC (simplified - signal strength vs outcome)
            ic = 0.0
            if len(acted) >= 5:
                strengths = [o.signal_strength for o in acted if o.pnl is not None]
                pnls = [o.pnl for o in acted if o.pnl is not None]
                if len(strengths) == len(pnls) and len(strengths) > 0:
                    try:
                        ic = float(np.corrcoef(strengths, pnls)[0, 1])
                        if np.isnan(ic):
                            ic = 0.0
                    except:
                        ic = 0.0

            # Determine trend (compare to previous if available)
            trend = "stable"
            if signal_type in self.quality:
                prev = self.quality[signal_type]
                if hit_rate > prev.hit_rate + 0.05:
                    trend = "improving"
                elif hit_rate < prev.hit_rate - 0.05:
                    trend = "degrading"

            quality_metrics[signal_type] = SignalQuality(
                signal_type=signal_type,
                total_signals=total,
                acted_on=len(acted),
                profitable=len(profitable),
                hit_rate=hit_rate,
                avg_pnl=avg_pnl,
                avg_pnl_pct=avg_pnl_pct,
                ic=ic,
                trend=trend,
                last_updated=datetime.now(),
            )

        # Update stored quality
        self.quality = quality_metrics
        self._save_quality()

        return quality_metrics

    def get_quality(self, signal_type: str) -> SignalQuality | None:
        """Get quality metrics for a signal type."""
        return self.quality.get(signal_type)

    def get_best_signals(self, min_samples: int = 10) -> list[SignalQuality]:
        """Get signals with best hit rate (with sufficient samples)."""
        signals = [
            q for q in self.quality.values()
            if q.acted_on >= min_samples
        ]
        return sorted(signals, key=lambda q: q.hit_rate, reverse=True)

    def get_degrading_signals(self) -> list[SignalQuality]:
        """Get signals with degrading quality."""
        return [q for q in self.quality.values() if q.trend == "degrading"]

    def get_summary(self) -> dict:
        """Get summary of signal quality across all types."""
        if not self.quality:
            return {
                "total_types": 0,
                "avg_hit_rate": 0,
                "best_signal": None,
                "worst_signal": None,
                "degrading": [],
            }

        hit_rates = [q.hit_rate for q in self.quality.values() if q.acted_on > 0]

        best = max(self.quality.values(), key=lambda q: q.hit_rate) if self.quality else None
        worst = min(self.quality.values(), key=lambda q: q.hit_rate) if self.quality else None

        return {
            "total_types": len(self.quality),
            "avg_hit_rate": np.mean(hit_rates) if hit_rates else 0,
            "best_signal": best.signal_type if best else None,
            "best_hit_rate": best.hit_rate if best else 0,
            "worst_signal": worst.signal_type if worst else None,
            "worst_hit_rate": worst.hit_rate if worst else 0,
            "degrading": [q.signal_type for q in self.get_degrading_signals()],
            "improving": [q.signal_type for q in self.quality.values() if q.trend == "improving"],
        }


# Singleton instance
_tracker: SignalQualityTracker | None = None


def get_signal_quality_tracker() -> SignalQualityTracker:
    """Get global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = SignalQualityTracker()
    return _tracker


def log_signal_outcome(
    signal_type: str,
    symbol: str,
    direction: str,
    signal_strength: float,
    acted_on: bool,
    **kwargs,
) -> SignalOutcome:
    """Convenience function to log a signal outcome."""
    return get_signal_quality_tracker().log_outcome(
        signal_type=signal_type,
        symbol=symbol,
        direction=direction,
        signal_strength=signal_strength,
        acted_on=acted_on,
        **kwargs,
    )


def log_decision_signals(
    symbol: str,
    direction: str,
    signals: dict[str, float],
    acted_on: bool = True,
    threshold: float = 0.3,
) -> list[SignalOutcome]:
    """
    Log all signals that influenced a trading decision.

    Args:
        symbol: Stock symbol
        direction: "bullish" or "bearish"
        signals: Dict mapping signal names to strengths (0-1)
        acted_on: Whether we traded on these signals
        threshold: Minimum strength to log (default 0.3)

    Returns:
        List of logged SignalOutcome objects

    Example:
        signals = {
            'composite_score': 0.65,
            'swing_signal': 0.72,
            'insider_signal': 0.65,
        }
        log_decision_signals("SLB", "bullish", signals)
    """
    signal_type_map = {
        'composite_score': 'technical',
        'swing_signal': 'technical',
        'momentum_signal': 'technical',
        'mean_reversion_signal': 'technical',
        'insider_signal': 'insider',
        'insider_score': 'insider',
        'congressional_signal': 'congressional',
        'congressional_score': 'congressional',
        'options_flow': 'options',
        'options_signal': 'options',
        'short_squeeze_score': 'squeeze',
        'squeeze_signal': 'squeeze',
        'sentiment_score': 'sentiment',
        'sentiment_signal': 'sentiment',
        'social_score': 'social',
        'social_signal': 'social',
        'technical_bias': 'technical',
    }

    outcomes = []
    tracker = get_signal_quality_tracker()

    for signal_name, strength in signals.items():
        # Skip if below threshold or not a recognized signal
        if signal_name not in signal_type_map:
            continue
        if not isinstance(strength, (int, float)) or strength < threshold:
            continue

        signal_type = signal_type_map[signal_name]
        outcome = tracker.log_outcome(
            signal_type=signal_type,
            symbol=symbol,
            direction=direction,
            signal_strength=float(strength),
            acted_on=acted_on,
        )
        outcomes.append(outcome)

    return outcomes
