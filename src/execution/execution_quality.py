"""Execution Quality Tracker.

Tracks and analyzes trade execution quality:
- Slippage monitoring (expected vs actual)
- Fill rate analysis
- Time-of-day patterns
- Market impact estimation

Created: 2026-01-20
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a single execution."""

    order_id: str
    timestamp: datetime
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    order_type: str  # market, limit, etc.

    # Prices
    expected_price: float  # Price when decision was made
    limit_price: Optional[float]  # If limit order
    fill_price: float  # Actual fill price

    # Timing
    decision_time: datetime  # When trade decision was made
    submit_time: datetime  # When order was submitted
    fill_time: datetime  # When order was filled

    # Computed metrics
    slippage_bps: float = 0.0  # Slippage in basis points
    latency_ms: int = 0  # Time from decision to fill
    fill_quality: str = "neutral"  # good, neutral, poor

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "expected_price": self.expected_price,
            "limit_price": self.limit_price,
            "fill_price": self.fill_price,
            "decision_time": self.decision_time.isoformat(),
            "submit_time": self.submit_time.isoformat(),
            "fill_time": self.fill_time.isoformat(),
            "slippage_bps": self.slippage_bps,
            "latency_ms": self.latency_ms,
            "fill_quality": self.fill_quality,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionRecord":
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["decision_time"] = datetime.fromisoformat(data["decision_time"])
        data["submit_time"] = datetime.fromisoformat(data["submit_time"])
        data["fill_time"] = datetime.fromisoformat(data["fill_time"])
        return cls(**data)


@dataclass
class ExecutionSummary:
    """Summary of execution quality."""

    period: str  # "daily", "weekly", "monthly"
    start_date: datetime
    end_date: datetime

    total_trades: int
    total_volume: int
    total_notional: float

    # Slippage
    avg_slippage_bps: float
    worst_slippage_bps: float
    total_slippage_cost: float  # In dollars

    # Fill quality distribution
    good_fills_pct: float
    neutral_fills_pct: float
    poor_fills_pct: float

    # Timing
    avg_latency_ms: int

    # By time of day
    best_execution_hour: int
    worst_execution_hour: int

    # By symbol
    worst_slippage_symbols: list[str]

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_trades": self.total_trades,
            "total_volume": self.total_volume,
            "total_notional": self.total_notional,
            "avg_slippage_bps": self.avg_slippage_bps,
            "worst_slippage_bps": self.worst_slippage_bps,
            "total_slippage_cost": self.total_slippage_cost,
            "good_fills_pct": self.good_fills_pct,
            "neutral_fills_pct": self.neutral_fills_pct,
            "poor_fills_pct": self.poor_fills_pct,
            "avg_latency_ms": self.avg_latency_ms,
            "best_execution_hour": self.best_execution_hour,
            "worst_execution_hour": self.worst_execution_hour,
            "worst_slippage_symbols": self.worst_slippage_symbols,
        }


class ExecutionQualityTracker:
    """Track and analyze execution quality over time.

    This system:
    1. Records all executions with timing and prices
    2. Computes slippage for each trade
    3. Identifies patterns (time-of-day, symbol-specific)
    4. Generates recommendations for better execution
    """

    # Slippage thresholds (bps)
    GOOD_SLIPPAGE_THRESHOLD = 5      # < 5 bps is good
    POOR_SLIPPAGE_THRESHOLD = 25     # > 25 bps is poor

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (paths.knowledge / "execution")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.executions_file = self.storage_path / "executions.json"
        self.summary_file = self.storage_path / "execution_summary.json"

    def compute_slippage(
        self,
        expected_price: float,
        fill_price: float,
        side: str,
    ) -> float:
        """Compute slippage in basis points.

        Positive slippage = bad (paid more or sold for less)
        Negative slippage = good (paid less or sold for more)

        Args:
            expected_price: Price when decision was made
            fill_price: Actual fill price
            side: BUY or SELL

        Returns:
            Slippage in basis points
        """
        if expected_price == 0:
            return 0.0

        if side == "BUY":
            # For buys, paying more is bad (positive slippage)
            slippage = (fill_price - expected_price) / expected_price
        else:
            # For sells, receiving less is bad (positive slippage)
            slippage = (expected_price - fill_price) / expected_price

        return slippage * 10000  # Convert to bps

    def determine_fill_quality(self, slippage_bps: float) -> str:
        """Determine fill quality based on slippage."""
        if slippage_bps <= self.GOOD_SLIPPAGE_THRESHOLD:
            return "good"
        elif slippage_bps >= self.POOR_SLIPPAGE_THRESHOLD:
            return "poor"
        else:
            return "neutral"

    def record_execution(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        expected_price: float,
        fill_price: float,
        decision_time: datetime,
        submit_time: datetime,
        fill_time: datetime,
        limit_price: Optional[float] = None,
    ) -> ExecutionRecord:
        """Record a new execution.

        Args:
            All execution details

        Returns:
            ExecutionRecord with computed metrics
        """
        # Compute slippage
        slippage_bps = self.compute_slippage(expected_price, fill_price, side)
        fill_quality = self.determine_fill_quality(slippage_bps)

        # Compute latency
        latency_ms = int((fill_time - decision_time).total_seconds() * 1000)

        record = ExecutionRecord(
            order_id=order_id,
            timestamp=datetime.now(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            expected_price=expected_price,
            limit_price=limit_price,
            fill_price=fill_price,
            decision_time=decision_time,
            submit_time=submit_time,
            fill_time=fill_time,
            slippage_bps=slippage_bps,
            latency_ms=latency_ms,
            fill_quality=fill_quality,
        )

        # Load existing and append
        executions = self._load_executions()
        executions.append(record)
        self._save_executions(executions)

        logger.info(
            f"Recorded execution: {symbol} {side} {quantity} @ {fill_price:.2f} "
            f"(slippage: {slippage_bps:.1f} bps, quality: {fill_quality})"
        )

        return record

    def _load_executions(self, days: int = 90) -> list[ExecutionRecord]:
        """Load execution records."""
        if not self.executions_file.exists():
            return []

        with open(self.executions_file) as f:
            data = json.load(f)

        cutoff = datetime.now() - timedelta(days=days)
        records = []
        for item in data:
            record = ExecutionRecord.from_dict(item)
            if record.timestamp >= cutoff:
                records.append(record)

        return records

    def _save_executions(self, executions: list[ExecutionRecord]):
        """Save execution records."""
        # Keep only last 90 days
        cutoff = datetime.now() - timedelta(days=90)
        filtered = [e for e in executions if e.timestamp >= cutoff]

        with open(self.executions_file, "w") as f:
            json.dump([e.to_dict() for e in filtered], f, indent=2)

    def generate_summary(self, period: str = "weekly") -> ExecutionSummary:
        """Generate execution quality summary.

        Args:
            period: "daily", "weekly", or "monthly"

        Returns:
            ExecutionSummary with aggregated metrics
        """
        # Determine date range
        now = datetime.now()
        if period == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "weekly":
            start = now - timedelta(days=7)
        else:  # monthly
            start = now - timedelta(days=30)

        executions = self._load_executions()
        period_executions = [e for e in executions if e.timestamp >= start]

        if not period_executions:
            return ExecutionSummary(
                period=period,
                start_date=start,
                end_date=now,
                total_trades=0,
                total_volume=0,
                total_notional=0.0,
                avg_slippage_bps=0.0,
                worst_slippage_bps=0.0,
                total_slippage_cost=0.0,
                good_fills_pct=0.0,
                neutral_fills_pct=0.0,
                poor_fills_pct=0.0,
                avg_latency_ms=0,
                best_execution_hour=10,
                worst_execution_hour=15,
                worst_slippage_symbols=[],
            )

        # Basic stats
        total_trades = len(period_executions)
        total_volume = sum(e.quantity for e in period_executions)
        total_notional = sum(e.quantity * e.fill_price for e in period_executions)

        # Slippage stats
        slippages = [e.slippage_bps for e in period_executions]
        avg_slippage = sum(slippages) / len(slippages)
        worst_slippage = max(slippages)

        # Slippage cost in dollars
        total_slippage_cost = sum(
            e.quantity * e.fill_price * (e.slippage_bps / 10000)
            for e in period_executions
        )

        # Fill quality distribution
        good = len([e for e in period_executions if e.fill_quality == "good"])
        neutral = len([e for e in period_executions if e.fill_quality == "neutral"])
        poor = len([e for e in period_executions if e.fill_quality == "poor"])

        good_pct = good / total_trades * 100
        neutral_pct = neutral / total_trades * 100
        poor_pct = poor / total_trades * 100

        # Latency
        avg_latency = sum(e.latency_ms for e in period_executions) // total_trades

        # Time of day analysis
        by_hour = {}
        for e in period_executions:
            hour = e.fill_time.hour
            if hour not in by_hour:
                by_hour[hour] = []
            by_hour[hour].append(e.slippage_bps)

        hour_avg = {h: sum(s) / len(s) for h, s in by_hour.items() if s}
        if hour_avg:
            best_hour = min(hour_avg, key=hour_avg.get)
            worst_hour = max(hour_avg, key=hour_avg.get)
        else:
            best_hour = 10
            worst_hour = 15

        # Worst symbols
        by_symbol = {}
        for e in period_executions:
            if e.symbol not in by_symbol:
                by_symbol[e.symbol] = []
            by_symbol[e.symbol].append(e.slippage_bps)

        symbol_avg = {s: sum(sl) / len(sl) for s, sl in by_symbol.items() if sl}
        worst_symbols = sorted(symbol_avg.keys(), key=lambda x: symbol_avg[x], reverse=True)[:5]

        summary = ExecutionSummary(
            period=period,
            start_date=start,
            end_date=now,
            total_trades=total_trades,
            total_volume=total_volume,
            total_notional=total_notional,
            avg_slippage_bps=avg_slippage,
            worst_slippage_bps=worst_slippage,
            total_slippage_cost=total_slippage_cost,
            good_fills_pct=good_pct,
            neutral_fills_pct=neutral_pct,
            poor_fills_pct=poor_pct,
            avg_latency_ms=avg_latency,
            best_execution_hour=best_hour,
            worst_execution_hour=worst_hour,
            worst_slippage_symbols=worst_symbols,
        )

        # Save summary
        with open(self.summary_file, "w") as f:
            json.dump(summary.to_dict(), f, indent=2)

        return summary

    def get_recommendations(self, summary: ExecutionSummary) -> list[str]:
        """Generate execution improvement recommendations.

        Args:
            summary: Execution summary to analyze

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if summary.avg_slippage_bps > 15:
            recommendations.append(
                f"High average slippage ({summary.avg_slippage_bps:.1f} bps). "
                f"Consider using limit orders instead of market orders."
            )

        if summary.poor_fills_pct > 20:
            recommendations.append(
                f"Too many poor fills ({summary.poor_fills_pct:.1f}%). "
                f"Review execution timing and order types."
            )

        if summary.worst_execution_hour in [9, 10, 15, 16]:
            recommendations.append(
                f"Worst execution at hour {summary.worst_execution_hour}. "
                f"Consider avoiding trades during high volatility periods."
            )

        if summary.worst_slippage_symbols:
            recommendations.append(
                f"Symbols with poor execution: {', '.join(summary.worst_slippage_symbols)}. "
                f"Consider using limit orders or smaller position sizes."
            )

        if summary.total_slippage_cost > 100:
            recommendations.append(
                f"Total slippage cost: ${summary.total_slippage_cost:.2f}. "
                f"This represents meaningful drag on returns."
            )

        return recommendations


# Convenience function
def get_execution_summary() -> Optional[ExecutionSummary]:
    """Get latest execution summary."""
    tracker = ExecutionQualityTracker()
    if tracker.summary_file.exists():
        with open(tracker.summary_file) as f:
            data = json.load(f)
        data["start_date"] = datetime.fromisoformat(data["start_date"])
        data["end_date"] = datetime.fromisoformat(data["end_date"])
        return ExecutionSummary(**data)
    return None


if __name__ == "__main__":
    tracker = ExecutionQualityTracker()

    # Record a sample execution
    now = datetime.now()
    record = tracker.record_execution(
        order_id="test_123",
        symbol="AAPL",
        side="BUY",
        quantity=100,
        order_type="market",
        expected_price=185.50,
        fill_price=185.68,
        decision_time=now - timedelta(seconds=30),
        submit_time=now - timedelta(seconds=5),
        fill_time=now,
    )

    print(f"Recorded: {record.symbol} slippage = {record.slippage_bps:.1f} bps")

    # Generate summary
    summary = tracker.generate_summary("daily")
    print(f"\nDaily Summary:")
    print(f"  Trades: {summary.total_trades}")
    print(f"  Avg Slippage: {summary.avg_slippage_bps:.1f} bps")
    print(f"  Total Slippage Cost: ${summary.total_slippage_cost:.2f}")

    # Get recommendations
    recs = tracker.get_recommendations(summary)
    if recs:
        print("\nRecommendations:")
        for r in recs:
            print(f"  - {r}")
