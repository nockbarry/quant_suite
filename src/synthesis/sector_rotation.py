#!/usr/bin/env python3
"""Sector Rotation Detector - Identify sector leadership changes.

Monitors relative strength and rotation patterns across sectors.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

# Sector characteristics for rotation analysis
SECTOR_CYCLE = {
    # Early cycle (recovery)
    "early": ["XLF", "XLY", "XLI", "XLB"],
    # Mid cycle (expansion)
    "mid": ["XLK", "XLC", "XLI"],
    # Late cycle (slowdown)
    "late": ["XLE", "XLV", "XLP"],
    # Recession (contraction)
    "recession": ["XLU", "XLP", "XLV", "XLRE"],
}

# Risk classification
RISK_ON_SECTORS = ["XLK", "XLY", "XLF", "XLI", "XLB"]
RISK_OFF_SECTORS = ["XLU", "XLP", "XLV", "XLRE"]


@dataclass
class SectorStrength:
    """Relative strength for a sector."""
    symbol: str
    name: str
    return_1d: float
    return_5d: float
    return_20d: float
    rs_vs_spy: float  # Relative strength vs SPY
    momentum_score: float  # Composite momentum
    rank: int = 0

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "name": self.name,
            "return_1d": self.return_1d,
            "return_5d": self.return_5d,
            "return_20d": self.return_20d,
            "rs_vs_spy": self.rs_vs_spy,
            "momentum_score": self.momentum_score,
            "rank": self.rank,
        }


@dataclass
class RotationSignal:
    """A sector rotation signal."""
    timestamp: datetime
    rotation_type: str  # risk_on, risk_off, sector_specific
    from_sectors: list[str]
    to_sectors: list[str]
    strength: float  # 0-1
    cycle_phase: str  # early, mid, late, recession
    recommended_actions: list[str]

    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "rotation_type": self.rotation_type,
            "from_sectors": self.from_sectors,
            "to_sectors": self.to_sectors,
            "strength": self.strength,
            "cycle_phase": self.cycle_phase,
            "recommended_actions": self.recommended_actions,
        }


class SectorRotationDetector:
    """Detect sector rotation and leadership changes."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live / "sectors"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.sector_data: dict[str, SectorStrength] = {}
        self.history: list[dict] = []

    async def fetch_sector_data(self) -> dict[str, pd.DataFrame]:
        """Fetch price data for all sector ETFs."""
        data = {}
        symbols = list(SECTOR_ETFS.keys()) + ["SPY"]

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="60d")
                if not df.empty:
                    data[symbol] = df
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

        return data

    def calculate_returns(self, df: pd.DataFrame) -> dict:
        """Calculate various return periods."""
        if len(df) < 2:
            return {"1d": 0, "5d": 0, "20d": 0}

        close = df["Close"]

        return_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
        return_5d = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
        return_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0

        return {
            "1d": return_1d,
            "5d": return_5d,
            "20d": return_20d,
        }

    def calculate_relative_strength(self, sector_df: pd.DataFrame, spy_df: pd.DataFrame) -> float:
        """Calculate relative strength vs SPY."""
        if len(sector_df) < 20 or len(spy_df) < 20:
            return 0.0

        # 20-day ratio
        sector_return = sector_df["Close"].iloc[-1] / sector_df["Close"].iloc[-20] - 1
        spy_return = spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-20] - 1

        return (sector_return - spy_return) * 100

    async def analyze_sectors(self) -> list[SectorStrength]:
        """Analyze all sectors and rank by strength."""
        data = await self.fetch_sector_data()

        if "SPY" not in data:
            logger.error("SPY data not available")
            return []

        spy_df = data["SPY"]
        strengths = []

        for symbol, name in SECTOR_ETFS.items():
            if symbol not in data:
                continue

            df = data[symbol]
            returns = self.calculate_returns(df)
            rs_vs_spy = self.calculate_relative_strength(df, spy_df)

            # Composite momentum score (weighted average)
            momentum = (
                returns["1d"] * 0.2 +
                returns["5d"] * 0.3 +
                returns["20d"] * 0.3 +
                rs_vs_spy * 0.2
            )

            strengths.append(SectorStrength(
                symbol=symbol,
                name=name,
                return_1d=returns["1d"],
                return_5d=returns["5d"],
                return_20d=returns["20d"],
                rs_vs_spy=rs_vs_spy,
                momentum_score=momentum,
            ))

        # Rank by momentum
        strengths.sort(key=lambda x: x.momentum_score, reverse=True)
        for i, s in enumerate(strengths):
            s.rank = i + 1

        # Cache results
        self.sector_data = {s.symbol: s for s in strengths}

        return strengths

    def detect_rotation(self, strengths: list[SectorStrength]) -> Optional[RotationSignal]:
        """Detect if rotation is occurring."""
        if not strengths:
            return None

        # Get top and bottom sectors
        top_3 = [s.symbol for s in strengths[:3]]
        bottom_3 = [s.symbol for s in strengths[-3:]]

        # Determine rotation type
        top_risk_on = sum(1 for s in top_3 if s in RISK_ON_SECTORS)
        top_risk_off = sum(1 for s in top_3 if s in RISK_OFF_SECTORS)

        if top_risk_on >= 2:
            rotation_type = "risk_on"
        elif top_risk_off >= 2:
            rotation_type = "risk_off"
        else:
            rotation_type = "sector_specific"

        # Determine cycle phase
        cycle_phase = self._determine_cycle_phase(top_3)

        # Calculate strength of rotation
        top_momentum = np.mean([s.momentum_score for s in strengths[:3]])
        bottom_momentum = np.mean([s.momentum_score for s in strengths[-3:]])
        rotation_strength = min(1.0, max(0.0, (top_momentum - bottom_momentum) / 10))

        # Generate recommendations
        recommendations = self._get_recommendations(rotation_type, top_3, bottom_3, cycle_phase)

        signal = RotationSignal(
            timestamp=datetime.now(),
            rotation_type=rotation_type,
            from_sectors=bottom_3,
            to_sectors=top_3,
            strength=rotation_strength,
            cycle_phase=cycle_phase,
            recommended_actions=recommendations,
        )

        # Save to history
        self.history.append(signal.to_dict())
        self._save_state()

        return signal

    def _determine_cycle_phase(self, top_sectors: list[str]) -> str:
        """Determine market cycle phase based on leading sectors."""
        for phase, sectors in SECTOR_CYCLE.items():
            matches = sum(1 for s in top_sectors if s in sectors)
            if matches >= 2:
                return phase
        return "mid"  # Default

    def _get_recommendations(self, rotation_type: str, top: list[str],
                            bottom: list[str], cycle: str) -> list[str]:
        """Generate trading recommendations."""
        recs = []

        if rotation_type == "risk_on":
            recs.append("Market favoring growth - consider adding to tech, discretionary")
            recs.append(f"Reduce exposure to: {', '.join(SECTOR_ETFS.get(s, s) for s in bottom[:2])}")
        elif rotation_type == "risk_off":
            recs.append("Defensive rotation - consider utilities, staples, healthcare")
            recs.append("Reduce exposure to cyclicals")

        if cycle == "late":
            recs.append("Late cycle indicators - be cautious, consider taking profits")
        elif cycle == "recession":
            recs.append("Recession signals - defensive positioning recommended")
        elif cycle == "early":
            recs.append("Early cycle recovery - aggressive positioning may be warranted")

        return recs

    def _save_state(self):
        """Save current state to file."""
        state_file = self.cache_dir / "rotation_state.json"

        with open(state_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "sectors": {k: v.to_dict() for k, v in self.sector_data.items()},
                "history": self.history[-50:],
            }, f, indent=2)

    def get_sector_rankings(self) -> str:
        """Get human-readable sector rankings."""
        if not self.sector_data:
            return "No sector data available"

        lines = ["Sector Rankings (by momentum)", "=" * 50]

        sorted_sectors = sorted(
            self.sector_data.values(),
            key=lambda x: x.momentum_score,
            reverse=True
        )

        for s in sorted_sectors:
            arrow = "↑" if s.momentum_score > 0 else "↓"
            lines.append(
                f"{s.rank:2d}. {s.symbol:5s} {s.name:25s} "
                f"{arrow} {s.momentum_score:+.2f} (RS: {s.rs_vs_spy:+.2f})"
            )

        return "\n".join(lines)

    def get_risk_assessment(self) -> dict:
        """Get overall market risk assessment based on rotation."""
        if not self.sector_data:
            return {"risk_level": "unknown"}

        sorted_sectors = sorted(
            self.sector_data.values(),
            key=lambda x: x.momentum_score,
            reverse=True
        )

        top_3 = [s.symbol for s in sorted_sectors[:3]]
        risk_on_leading = sum(1 for s in top_3 if s in RISK_ON_SECTORS)

        if risk_on_leading >= 2:
            risk_level = "risk_on"
            stance = "Aggressive"
        elif risk_on_leading == 0:
            risk_level = "risk_off"
            stance = "Defensive"
        else:
            risk_level = "neutral"
            stance = "Balanced"

        return {
            "risk_level": risk_level,
            "stance": stance,
            "leading_sectors": top_3,
            "lagging_sectors": [s.symbol for s in sorted_sectors[-3:]],
        }


async def main():
    """Test sector rotation detector."""
    detector = SectorRotationDetector()

    print("Analyzing sectors...")
    strengths = await detector.analyze_sectors()

    print("\n" + detector.get_sector_rankings())

    signal = detector.detect_rotation(strengths)
    if signal:
        print(f"\nRotation Signal:")
        print(f"  Type: {signal.rotation_type}")
        print(f"  Phase: {signal.cycle_phase}")
        print(f"  Strength: {signal.strength:.2f}")
        print(f"  Leading: {signal.to_sectors}")
        print(f"  Lagging: {signal.from_sectors}")
        print(f"  Recommendations:")
        for rec in signal.recommended_actions:
            print(f"    - {rec}")

    risk = detector.get_risk_assessment()
    print(f"\nRisk Assessment: {risk['stance']} ({risk['risk_level']})")


if __name__ == "__main__":
    asyncio.run(main())
