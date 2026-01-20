"""Signal Health Tracking System.

Monitors the health and predictive power of trading signals:
- Information Coefficient (IC) tracking
- IC decay over time
- Signal coverage
- Regime-specific performance

Created: 2026-01-20
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class SignalHealthMetrics:
    """Health metrics for a single signal."""

    signal_name: str
    last_updated: datetime

    # IC (Information Coefficient) metrics
    ic_overall: float  # Rank correlation with forward returns
    ic_30d: float      # IC over last 30 days
    ic_stability: float  # Std dev of rolling IC
    ic_decay_rate: float  # How quickly IC decays with horizon

    # Coverage metrics
    coverage_pct: float  # % of days with signal
    avg_magnitude: float  # Average signal strength
    turnover_pct: float  # % of days signal changes direction

    # Hit rate
    hit_rate_1d: float  # % of times signal direction matches 1d return
    hit_rate_5d: float  # % of times signal direction matches 5d return

    # Status
    status: str = "healthy"  # healthy, degrading, broken
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "signal_name": self.signal_name,
            "last_updated": self.last_updated.isoformat(),
            "ic_overall": self.ic_overall,
            "ic_30d": self.ic_30d,
            "ic_stability": self.ic_stability,
            "ic_decay_rate": self.ic_decay_rate,
            "coverage_pct": self.coverage_pct,
            "avg_magnitude": self.avg_magnitude,
            "turnover_pct": self.turnover_pct,
            "hit_rate_1d": self.hit_rate_1d,
            "hit_rate_5d": self.hit_rate_5d,
            "status": self.status,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalHealthMetrics":
        data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        return cls(**data)


@dataclass
class SignalHealthReport:
    """Aggregated health report for all signals."""

    timestamp: datetime
    total_signals: int
    healthy_signals: int
    degrading_signals: int
    broken_signals: int

    best_performers: list[str]  # Top 5 by IC
    worst_performers: list[str]  # Bottom 5 by IC

    signal_metrics: dict[str, SignalHealthMetrics]

    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_signals": self.total_signals,
            "healthy_signals": self.healthy_signals,
            "degrading_signals": self.degrading_signals,
            "broken_signals": self.broken_signals,
            "best_performers": self.best_performers,
            "worst_performers": self.worst_performers,
            "signal_metrics": {k: v.to_dict() for k, v in self.signal_metrics.items()},
            "recommendations": self.recommendations,
        }


class SignalHealthTracker:
    """Track and monitor signal health over time.

    This system:
    1. Computes IC for each signal vs forward returns
    2. Tracks IC stability and decay
    3. Identifies degrading or broken signals
    4. Provides recommendations for signal usage
    """

    IC_HEALTHY_THRESHOLD = 0.02     # IC > 2% is healthy
    IC_DEGRADING_THRESHOLD = 0.01   # IC 1-2% is degrading
    IC_BROKEN_THRESHOLD = 0.005     # IC < 0.5% is broken

    STABILITY_THRESHOLD = 0.05  # IC std dev > 5% is unstable
    COVERAGE_THRESHOLD = 0.50   # Signal should cover >50% of days

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (paths.knowledge / "signal_health")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.history_file = self.storage_path / "signal_history.json"
        self.metrics_file = self.storage_path / "signal_metrics.json"

    def compute_ic(
        self,
        signal_values: pd.Series,
        forward_returns: pd.Series,
    ) -> float:
        """Compute Information Coefficient (Spearman rank correlation).

        Args:
            signal_values: Signal values (higher = more bullish)
            forward_returns: Forward returns to predict

        Returns:
            IC as float (-1 to 1)
        """
        # Align and dropna
        combined = pd.DataFrame({
            "signal": signal_values,
            "returns": forward_returns,
        }).dropna()

        if len(combined) < 30:
            return 0.0

        # Spearman rank correlation
        ic = combined["signal"].corr(combined["returns"], method="spearman")
        return ic if not np.isnan(ic) else 0.0

    def compute_rolling_ic(
        self,
        signal_values: pd.Series,
        forward_returns: pd.Series,
        window: int = 30,
    ) -> pd.Series:
        """Compute rolling IC over time."""
        combined = pd.DataFrame({
            "signal": signal_values,
            "returns": forward_returns,
        }).dropna()

        # Rolling Spearman correlation
        # Note: rolling.corr() doesn't support method param, so we use apply
        def spearman_corr(x):
            if len(x) < 2:
                return np.nan
            signal_window = x["signal"].values
            returns_window = x["returns"].values
            from scipy import stats
            corr, _ = stats.spearmanr(signal_window, returns_window)
            return corr

        rolling_ic = combined.rolling(window).apply(
            lambda x: spearman_corr(pd.DataFrame({"signal": x[:len(x)//2], "returns": x[len(x)//2:]})),
            raw=False
        )

        # Simpler approach: use Pearson on ranks
        combined_ranked = combined.rank()
        rolling_ic = combined_ranked["signal"].rolling(window).corr(combined_ranked["returns"])

        return rolling_ic

    def compute_ic_decay(
        self,
        signal_values: pd.Series,
        prices: pd.Series,
        horizons: list[int] = None,
    ) -> dict[int, float]:
        """Compute IC at different forward horizons.

        Args:
            signal_values: Signal values
            prices: Price series
            horizons: List of forward days to check

        Returns:
            Dict mapping horizon to IC
        """
        if horizons is None:
            horizons = [1, 2, 5, 10, 20]

        decay = {}
        for h in horizons:
            forward_returns = prices.pct_change(h).shift(-h)
            decay[h] = self.compute_ic(signal_values, forward_returns)

        return decay

    def evaluate_signal(
        self,
        signal_name: str,
        signal_values: pd.Series,
        prices: pd.Series,
    ) -> SignalHealthMetrics:
        """Evaluate health of a single signal.

        Args:
            signal_name: Name of the signal
            signal_values: Historical signal values
            prices: Corresponding price series

        Returns:
            SignalHealthMetrics with full evaluation
        """
        warnings = []

        # Forward returns
        fwd_1d = prices.pct_change(1).shift(-1)
        fwd_5d = prices.pct_change(5).shift(-5)

        # IC calculations
        ic_overall = self.compute_ic(signal_values, fwd_5d)

        # 30-day IC
        rolling_ic = self.compute_rolling_ic(signal_values, fwd_5d, window=30)
        ic_30d = rolling_ic.iloc[-1] if not rolling_ic.empty else 0.0

        # IC stability (std of rolling IC)
        ic_stability = rolling_ic.std() if not rolling_ic.empty else 0.0

        # IC decay
        decay = self.compute_ic_decay(signal_values, prices)
        if decay.get(1, 0) != 0:
            ic_decay_rate = (decay.get(1, 0) - decay.get(20, 0)) / decay.get(1, 0)
        else:
            ic_decay_rate = 0.0

        # Coverage
        non_null = signal_values.notna().sum()
        coverage_pct = non_null / len(signal_values) if len(signal_values) > 0 else 0.0

        # Magnitude
        avg_magnitude = signal_values.abs().mean()

        # Turnover
        direction = np.sign(signal_values)
        changes = (direction != direction.shift(1)).sum()
        turnover_pct = changes / len(signal_values) if len(signal_values) > 0 else 0.0

        # Hit rates
        combined_1d = pd.DataFrame({
            "signal": np.sign(signal_values),
            "returns": np.sign(fwd_1d),
        }).dropna()
        hit_rate_1d = (combined_1d["signal"] == combined_1d["returns"]).mean()

        combined_5d = pd.DataFrame({
            "signal": np.sign(signal_values),
            "returns": np.sign(fwd_5d),
        }).dropna()
        hit_rate_5d = (combined_5d["signal"] == combined_5d["returns"]).mean()

        # Determine status
        if ic_overall >= self.IC_HEALTHY_THRESHOLD:
            status = "healthy"
        elif ic_overall >= self.IC_DEGRADING_THRESHOLD:
            status = "degrading"
            warnings.append(f"IC below healthy threshold ({ic_overall:.3f} < {self.IC_HEALTHY_THRESHOLD})")
        else:
            status = "broken"
            warnings.append(f"IC below minimum threshold ({ic_overall:.3f})")

        # Additional warnings
        if ic_stability > self.STABILITY_THRESHOLD:
            warnings.append(f"Unstable IC (std={ic_stability:.3f})")

        if coverage_pct < self.COVERAGE_THRESHOLD:
            warnings.append(f"Low coverage ({coverage_pct:.1%})")

        if ic_decay_rate > 0.5:
            warnings.append(f"Rapid IC decay ({ic_decay_rate:.1%})")

        return SignalHealthMetrics(
            signal_name=signal_name,
            last_updated=datetime.now(),
            ic_overall=ic_overall,
            ic_30d=ic_30d if not np.isnan(ic_30d) else 0.0,
            ic_stability=ic_stability if not np.isnan(ic_stability) else 0.0,
            ic_decay_rate=ic_decay_rate,
            coverage_pct=coverage_pct,
            avg_magnitude=avg_magnitude if not np.isnan(avg_magnitude) else 0.0,
            turnover_pct=turnover_pct,
            hit_rate_1d=hit_rate_1d if not np.isnan(hit_rate_1d) else 0.5,
            hit_rate_5d=hit_rate_5d if not np.isnan(hit_rate_5d) else 0.5,
            status=status,
            warnings=warnings,
        )

    def generate_report(self, metrics: dict[str, SignalHealthMetrics]) -> SignalHealthReport:
        """Generate aggregate health report.

        Args:
            metrics: Dict of signal name to metrics

        Returns:
            SignalHealthReport with aggregated stats
        """
        healthy = [m for m in metrics.values() if m.status == "healthy"]
        degrading = [m for m in metrics.values() if m.status == "degrading"]
        broken = [m for m in metrics.values() if m.status == "broken"]

        # Sort by IC
        sorted_by_ic = sorted(metrics.values(), key=lambda x: x.ic_overall, reverse=True)
        best = [m.signal_name for m in sorted_by_ic[:5]]
        worst = [m.signal_name for m in sorted_by_ic[-5:]]

        # Generate recommendations
        recommendations = []

        if broken:
            recommendations.append(
                f"Consider removing or rebuilding {len(broken)} broken signals: "
                f"{', '.join(m.signal_name for m in broken)}"
            )

        if degrading:
            recommendations.append(
                f"Monitor {len(degrading)} degrading signals: "
                f"{', '.join(m.signal_name for m in degrading)}"
            )

        # Check for regime sensitivity
        for m in metrics.values():
            if m.ic_stability > 0.1:
                recommendations.append(
                    f"Signal '{m.signal_name}' may be regime-sensitive (IC std={m.ic_stability:.2f})"
                )

        return SignalHealthReport(
            timestamp=datetime.now(),
            total_signals=len(metrics),
            healthy_signals=len(healthy),
            degrading_signals=len(degrading),
            broken_signals=len(broken),
            best_performers=best,
            worst_performers=worst,
            signal_metrics=metrics,
            recommendations=recommendations,
        )

    def save_report(self, report: SignalHealthReport):
        """Save health report to file."""
        with open(self.metrics_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"Saved signal health report to {self.metrics_file}")

    def load_latest_report(self) -> Optional[SignalHealthReport]:
        """Load most recent health report."""
        if not self.metrics_file.exists():
            return None

        with open(self.metrics_file) as f:
            data = json.load(f)

        # Reconstruct
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["signal_metrics"] = {
            k: SignalHealthMetrics.from_dict(v)
            for k, v in data["signal_metrics"].items()
        }
        return SignalHealthReport(**data)


# Convenience function
def check_signal_health() -> Optional[SignalHealthReport]:
    """Load and return latest signal health report."""
    tracker = SignalHealthTracker()
    return tracker.load_latest_report()


if __name__ == "__main__":
    # Demo with synthetic data
    import numpy as np

    tracker = SignalHealthTracker()

    # Create synthetic signal and prices
    np.random.seed(42)
    n = 252
    dates = pd.date_range(end=datetime.now(), periods=n, freq="D")

    # Synthetic price (random walk with drift)
    returns = np.random.randn(n) * 0.01 + 0.0003  # ~7% annual return
    prices = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)

    # Synthetic signal (momentum-like, somewhat predictive)
    momentum = prices.pct_change(20)
    signal = momentum + np.random.randn(n) * 0.01  # Add noise
    signal = pd.Series(signal, index=dates)

    print("=== Signal Health Demo ===")
    metrics = tracker.evaluate_signal("momentum_20d", signal, prices)
    print(f"\nSignal: {metrics.signal_name}")
    print(f"Status: {metrics.status}")
    print(f"IC Overall: {metrics.ic_overall:.3f}")
    print(f"IC 30d: {metrics.ic_30d:.3f}")
    print(f"IC Stability: {metrics.ic_stability:.3f}")
    print(f"Hit Rate 5d: {metrics.hit_rate_5d:.1%}")
    print(f"Coverage: {metrics.coverage_pct:.1%}")
    if metrics.warnings:
        print(f"Warnings: {', '.join(metrics.warnings)}")
