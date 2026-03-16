"""Conviction Velocity Signal Engine.

Computes the rate of change of thesis conviction over time.
Rising conviction velocity = strengthening thesis = ADD signal.
Falling conviction velocity = weakening thesis = REDUCE signal.

Evidence:
- CF conviction +11pp in 6 days -> stock +22.8%
- AXP conviction -45pp -> continued declining
- Defense conviction -30pp -> structural underperformance
Expected IC: 0.31
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConvictionVelocitySignal:
    """Signal generated from thesis conviction rate-of-change."""

    thesis_id: str
    thesis_name: str
    symbols: list[str]
    velocity_3d: float  # pp/day over 3 days
    velocity_7d: float  # pp/day over 7 days
    acceleration: float  # change in velocity (pp/day^2)
    current_conviction: float
    signal_direction: str  # "ADD", "REDUCE", "NEUTRAL"
    signal_strength: float  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "symbols": self.symbols,
            "velocity_3d": round(self.velocity_3d, 3),
            "velocity_7d": round(self.velocity_7d, 3),
            "acceleration": round(self.acceleration, 3),
            "current_conviction": self.current_conviction,
            "signal_direction": self.signal_direction,
            "signal_strength": round(self.signal_strength, 3),
            "timestamp": self.timestamp.isoformat(),
        }


class ConvictionVelocityEngine:
    """Compute conviction velocity signals from thesis conviction history.

    Velocity is measured in percentage points per day (pp/day).
    Acceleration is the change in velocity over time (pp/day^2).

    Signal thresholds:
    - ADD:    velocity > +2 pp/day (conviction rising fast)
    - REDUCE: velocity < -3 pp/day (conviction falling fast, asymmetric for caution)
    - NEUTRAL: otherwise

    Strength is scaled by magnitude: |velocity| / 10, clamped to [0, 1].
    """

    # Thresholds for signal generation
    ADD_VELOCITY_THRESHOLD = 2.0  # pp/day
    REDUCE_VELOCITY_THRESHOLD = -3.0  # pp/day (more conservative for sells)
    MAX_SIZE_ADJUSTMENT = 0.5  # up to +/-50% position size adjustment
    MIN_HISTORY_POINTS = 2  # minimum conviction updates needed

    def __init__(self, thesis_tracker=None):
        """Initialize with optional ThesisTracker instance.

        Args:
            thesis_tracker: ThesisTracker instance. If None, creates one
                           using the default theses directory.
        """
        if thesis_tracker is not None:
            self._tracker = thesis_tracker
        else:
            self._tracker = None

    @property
    def tracker(self):
        """Lazy-load ThesisTracker to avoid circular imports."""
        if self._tracker is None:
            from src.knowledge.thesis import ThesisTracker
            self._tracker = ThesisTracker()
        return self._tracker

    def compute_velocity(self, thesis, window_days: int = 3) -> float:
        """Compute conviction velocity over a time window.

        Uses simple linear regression (least-squares slope) on conviction
        history within the window. Returns slope in pp/day.

        Args:
            thesis: Thesis object with conviction_history field
            window_days: Number of days to look back (default 3)

        Returns:
            Velocity in percentage points per day. Positive = conviction
            rising, negative = conviction falling. Returns 0.0 if
            insufficient data.
        """
        if not thesis.conviction_history:
            return 0.0

        now = datetime.now()
        cutoff = now - timedelta(days=window_days)

        # Gather data points within window
        # Each ConvictionUpdate has timestamp, old_value, new_value
        points = []
        for update in thesis.conviction_history:
            if update.timestamp >= cutoff:
                # Time in days from cutoff
                dt = (update.timestamp - cutoff).total_seconds() / 86400.0
                points.append((dt, update.new_value))

        # Add current conviction as the latest point if no recent updates
        if not points:
            # No updates in window - check if there's any history at all
            if thesis.conviction_history:
                # Use the most recent update before the window as baseline
                latest = thesis.conviction_history[-1]
                dt_latest = (latest.timestamp - cutoff).total_seconds() / 86400.0
                dt_now = (now - cutoff).total_seconds() / 86400.0
                points = [
                    (max(dt_latest, 0.0), latest.new_value),
                    (dt_now, thesis.conviction),
                ]
            else:
                return 0.0

        if len(points) < self.MIN_HISTORY_POINTS:
            # Not enough data for regression
            if len(points) == 1 and thesis.conviction != points[0][1]:
                # Single point but conviction has changed since
                dt_now = (now - cutoff).total_seconds() / 86400.0
                points.append((dt_now, thesis.conviction))
            else:
                return 0.0

        # Simple linear regression: slope = sum((x-xbar)(y-ybar)) / sum((x-xbar)^2)
        n = len(points)
        x_vals = [p[0] for p in points]
        y_vals = [p[1] for p in points]

        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator < 1e-10:
            # All updates at effectively the same time
            return 0.0

        slope = numerator / denominator
        return slope

    def _compute_acceleration(self, thesis) -> float:
        """Compute conviction acceleration (change in velocity).

        Acceleration = velocity_3d - velocity_7d (normalized).
        Positive acceleration means conviction is accelerating upward.

        Args:
            thesis: Thesis object

        Returns:
            Acceleration in pp/day^2 (approximate).
        """
        v3 = self.compute_velocity(thesis, window_days=3)
        v7 = self.compute_velocity(thesis, window_days=7)

        # Acceleration: how much faster is recent velocity vs longer-term
        return v3 - v7

    def _compute_signal_strength(self, velocity: float) -> float:
        """Convert velocity magnitude to signal strength [0, 1].

        Maps |velocity| / 10 to [0, 1], where 10 pp/day would be
        maximum strength (very rare - would mean conviction moving
        from 50% to 80% in 3 days).

        Args:
            velocity: Velocity in pp/day

        Returns:
            Signal strength between 0.0 and 1.0.
        """
        return min(abs(velocity) / 10.0, 1.0)

    def _determine_direction(self, velocity_3d: float, velocity_7d: float,
                              current_conviction: float) -> str:
        """Determine signal direction from velocity and conviction level.

        Uses 3-day velocity as primary signal with 7-day for confirmation.
        Also checks absolute conviction level - won't ADD above 95% or
        REDUCE below 20%.

        Args:
            velocity_3d: 3-day velocity in pp/day
            velocity_7d: 7-day velocity in pp/day
            current_conviction: Current conviction percentage

        Returns:
            "ADD", "REDUCE", or "NEUTRAL"
        """
        # Don't ADD if already at max conviction
        if velocity_3d >= self.ADD_VELOCITY_THRESHOLD and current_conviction <= 95:
            return "ADD"

        # Don't REDUCE if already very low conviction (let stop-loss handle)
        if velocity_3d <= self.REDUCE_VELOCITY_THRESHOLD and current_conviction >= 20:
            return "REDUCE"

        # Check for 7-day trend as weaker signal only if 3-day is close
        if velocity_7d >= self.ADD_VELOCITY_THRESHOLD * 0.8 and velocity_3d > 0 and current_conviction <= 95:
            return "ADD"

        if velocity_7d <= self.REDUCE_VELOCITY_THRESHOLD * 0.8 and velocity_3d < 0 and current_conviction >= 20:
            return "REDUCE"

        return "NEUTRAL"

    def generate_signal(self, thesis) -> Optional[ConvictionVelocitySignal]:
        """Generate a conviction velocity signal for a single thesis.

        Args:
            thesis: Thesis object with conviction_history

        Returns:
            ConvictionVelocitySignal if velocity exceeds thresholds, else None.
        """
        if thesis.status != "active":
            return None

        if not thesis.conviction_history:
            return None

        velocity_3d = self.compute_velocity(thesis, window_days=3)
        velocity_7d = self.compute_velocity(thesis, window_days=7)
        acceleration = self._compute_acceleration(thesis)

        direction = self._determine_direction(
            velocity_3d, velocity_7d, thesis.conviction
        )

        if direction == "NEUTRAL":
            return None

        strength = self._compute_signal_strength(velocity_3d)

        signal = ConvictionVelocitySignal(
            thesis_id=thesis.id,
            thesis_name=thesis.name,
            symbols=list(thesis.positions),
            velocity_3d=velocity_3d,
            velocity_7d=velocity_7d,
            acceleration=acceleration,
            current_conviction=thesis.conviction,
            signal_direction=direction,
            signal_strength=strength,
        )

        logger.info(
            f"Conviction velocity signal: {thesis.name} -> {direction} "
            f"(v3={velocity_3d:+.2f} pp/d, v7={velocity_7d:+.2f} pp/d, "
            f"conv={thesis.conviction:.0f}%, strength={strength:.2f})"
        )

        # Emit event
        try:
            from src.core.events import emit
            emit(
                "signal_detected",
                source="conviction_velocity",
                title=f"Conviction velocity {direction}: {thesis.name}",
                detail={
                    "thesis_id": thesis.id,
                    "velocity_3d": velocity_3d,
                    "velocity_7d": velocity_7d,
                    "acceleration": acceleration,
                    "conviction": thesis.conviction,
                },
                confidence=strength,
                direction="bullish" if direction == "ADD" else "bearish",
                description=f"Conviction moving {velocity_3d:+.1f} pp/day",
                detection_method="conviction_velocity",
            )
        except Exception:
            pass

        return signal

    def scan_all_theses(self) -> list[ConvictionVelocitySignal]:
        """Scan all active theses and emit velocity signals.

        Returns:
            List of ConvictionVelocitySignal for theses exceeding
            velocity thresholds. Sorted by absolute velocity (strongest first).
        """
        signals = []

        try:
            active_theses = self.tracker.get_active_theses()
        except Exception as e:
            logger.error(f"Failed to load theses: {e}")
            return signals

        for thesis in active_theses:
            try:
                signal = self.generate_signal(thesis)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.warning(f"Error computing velocity for {thesis.name}: {e}")
                continue

        # Sort by absolute velocity (strongest signals first)
        signals.sort(key=lambda s: abs(s.velocity_3d), reverse=True)

        if signals:
            logger.info(
                f"Conviction velocity scan: {len(signals)} signals from "
                f"{len(active_theses)} active theses"
            )

        return signals

    def adjust_position_size(self, base_size_pct: float, velocity: float) -> float:
        """Adjust position size based on conviction velocity.

        Scales position size up to +/-50% based on velocity.
        Rising conviction -> larger position (up to +50%).
        Falling conviction -> smaller position (down to -50%).

        The adjustment is linear between thresholds:
        - At +2 pp/day: +0% adjustment (just crossed threshold)
        - At +10 pp/day: +50% adjustment (maximum)
        - At -3 pp/day: -0% adjustment (just crossed threshold)
        - At -10 pp/day: -50% adjustment (maximum)

        Args:
            base_size_pct: Base position size as percentage (e.g., 5.0)
            velocity: Conviction velocity in pp/day

        Returns:
            Adjusted position size percentage. Always >= 0.5% (minimum
            meaningful position) and <= base_size_pct * 1.5 (max +50%).
        """
        if velocity >= self.ADD_VELOCITY_THRESHOLD:
            # Positive velocity - scale up
            excess = velocity - self.ADD_VELOCITY_THRESHOLD
            max_excess = 10.0 - self.ADD_VELOCITY_THRESHOLD  # pp/day range
            adjustment_pct = min(excess / max_excess, 1.0) * self.MAX_SIZE_ADJUSTMENT
            adjusted = base_size_pct * (1.0 + adjustment_pct)
        elif velocity <= self.REDUCE_VELOCITY_THRESHOLD:
            # Negative velocity - scale down
            excess = abs(velocity) - abs(self.REDUCE_VELOCITY_THRESHOLD)
            max_excess = 10.0 - abs(self.REDUCE_VELOCITY_THRESHOLD)
            adjustment_pct = min(excess / max_excess, 1.0) * self.MAX_SIZE_ADJUSTMENT
            adjusted = base_size_pct * (1.0 - adjustment_pct)
        else:
            # Within neutral zone
            adjusted = base_size_pct

        # Enforce minimum position size
        return max(adjusted, 0.5)
