"""Morning Open Protocol for 9:35 AM assessment.

Compares pre-market action to actual open to detect:
- Gap fades (pre-market rally reversing)
- Gap holds (momentum continuing)
- Sector rotation signals
- Position alerts (stops, support/resistance)

Run this 5 minutes after market open to assess whether
the morning trading plan should proceed, be modified, or go defensive.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# Sector ETF mapping
SECTOR_ETFS = {
    "XLE": "Energy",
    "XLF": "Financials",
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communications",
}


@dataclass
class PreMarketVsOpen:
    """Comparison of pre-market to open prices."""

    symbol: str
    premarket_price: float
    premarket_change_pct: float
    open_price: float
    price_at_935: float
    gap_status: str  # "holding", "fading", "reversing", "extending"
    gap_fade_pct: float  # How much of pre-market gap has faded (0-100%)
    volume_vs_avg: float
    assessment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "premarket_price": self.premarket_price,
            "premarket_change_pct": self.premarket_change_pct,
            "open_price": self.open_price,
            "price_at_935": self.price_at_935,
            "gap_status": self.gap_status,
            "gap_fade_pct": self.gap_fade_pct,
            "volume_vs_avg": self.volume_vs_avg,
            "assessment": self.assessment,
        }


@dataclass
class SectorRotation:
    """Sector rotation analysis."""

    sector_etf: str
    sector_name: str
    change_pct: float
    rank: int
    relative_strength: float  # vs SPY
    flow_direction: str  # "inflow", "outflow", "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_etf": self.sector_etf,
            "sector_name": self.sector_name,
            "change_pct": self.change_pct,
            "rank": self.rank,
            "relative_strength": self.relative_strength,
            "flow_direction": self.flow_direction,
        }


@dataclass
class OpenAssessment:
    """Complete 9:35 AM assessment."""

    timestamp: datetime
    market_status: str  # "risk_on", "risk_off", "mixed"

    # Gap Analysis
    gaps: list[PreMarketVsOpen] = field(default_factory=list)
    gaps_holding: list[str] = field(default_factory=list)
    gaps_fading: list[str] = field(default_factory=list)

    # Sector Analysis
    sectors: list[SectorRotation] = field(default_factory=list)
    sector_leader: str = ""
    sector_laggard: str = ""
    our_sector_rank: int = 0
    rotation_signal: str = ""  # "into_our_sector", "out_of_our_sector", "neutral"

    # Position Alerts
    stops_hit: list[str] = field(default_factory=list)
    near_support: list[str] = field(default_factory=list)
    near_resistance: list[str] = field(default_factory=list)

    # Recommendation
    plan_status: str = "PROCEED"  # "PROCEED", "MODIFY", "DEFENSIVE"
    modifications: list[str] = field(default_factory=list)
    priority_actions: list[str] = field(default_factory=list)

    # Confidence
    confidence: float = 0.7
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "market_status": self.market_status,
            "gaps": [g.to_dict() for g in self.gaps],
            "gaps_holding": self.gaps_holding,
            "gaps_fading": self.gaps_fading,
            "sectors": [s.to_dict() for s in self.sectors],
            "sector_leader": self.sector_leader,
            "sector_laggard": self.sector_laggard,
            "our_sector_rank": self.our_sector_rank,
            "rotation_signal": self.rotation_signal,
            "stops_hit": self.stops_hit,
            "near_support": self.near_support,
            "near_resistance": self.near_resistance,
            "plan_status": self.plan_status,
            "modifications": self.modifications,
            "priority_actions": self.priority_actions,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown summary."""
        lines = [
            f"# OPEN ASSESSMENT - {self.timestamp.strftime('%H:%M:%S ET')}",
            "",
            f"**MARKET STATUS**: {self.market_status.upper()}",
            "",
            "## Gap Analysis",
        ]

        if self.gaps:
            lines.append("| Symbol | Pre-Mkt | 9:35 | Status | Fade % |")
            lines.append("|--------|---------|------|--------|--------|")
            for g in self.gaps:
                lines.append(
                    f"| {g.symbol} | {g.premarket_change_pct:+.1f}% | "
                    f"{((g.price_at_935/g.premarket_price)-1)*100:+.1f}% | "
                    f"{g.gap_status} | {g.gap_fade_pct:.0f}% |"
                )

        if self.gaps_fading:
            lines.append(f"\n**Fading**: {', '.join(self.gaps_fading)}")
        if self.gaps_holding:
            lines.append(f"**Holding**: {', '.join(self.gaps_holding)}")

        lines.extend([
            "",
            "## Sector Rotation",
            f"**Leader**: {self.sector_leader}",
            f"**Laggard**: {self.sector_laggard}",
            f"**Our Sector Rank**: #{self.our_sector_rank} of {len(self.sectors)}",
            f"**Rotation Signal**: {self.rotation_signal}",
        ])

        if self.stops_hit or self.near_support:
            lines.extend([
                "",
                "## Position Alerts",
            ])
            if self.stops_hit:
                lines.append(f"**STOPS HIT**: {', '.join(self.stops_hit)}")
            if self.near_support:
                lines.append(f"**Near Support**: {', '.join(self.near_support)}")

        lines.extend([
            "",
            f"## Recommendation: {self.plan_status}",
            f"**Confidence**: {self.confidence:.0%}",
        ])

        if self.modifications:
            lines.append("\n**Modifications**:")
            for mod in self.modifications:
                lines.append(f"- {mod}")

        if self.priority_actions:
            lines.append("\n**Priority Actions**:")
            for action in self.priority_actions:
                lines.append(f"- {action}")

        if self.notes:
            lines.extend(["", f"**Notes**: {self.notes}"])

        return "\n".join(lines)


class MorningOpenProtocol:
    """
    9:35 AM assessment protocol.

    Compares pre-market expectations to actual market open
    to determine if trading plan should proceed or be modified.
    """

    def __init__(
        self,
        watchlist: list[str],
        premarket_data: dict[str, float] | None = None,
        position_levels: dict[str, dict[str, float]] | None = None,
        our_sector: str = "XLE",
        output_dir: Path | None = None,
    ):
        """
        Initialize MorningOpenProtocol.

        Args:
            watchlist: Symbols to monitor
            premarket_data: Pre-market prices by symbol (from morning briefing)
            position_levels: Support/resistance/stop levels by symbol
            our_sector: Primary sector ETF we're exposed to
            output_dir: Directory to save assessments
        """
        self.watchlist = watchlist
        self.premarket_data = premarket_data or {}
        self.position_levels = position_levels or {}
        self.our_sector = our_sector
        self.output_dir = output_dir

    async def run_assessment(self) -> OpenAssessment:
        """
        Run the complete 9:35 AM assessment.

        Returns:
            OpenAssessment with recommendations
        """
        assessment = OpenAssessment(timestamp=datetime.now())

        # 1. Compare gaps
        assessment.gaps = await self._compare_gaps()
        assessment.gaps_holding = [g.symbol for g in assessment.gaps if g.gap_status == "holding"]
        assessment.gaps_fading = [g.symbol for g in assessment.gaps if g.gap_status in ("fading", "reversing")]

        # 2. Scan sectors
        assessment.sectors = await self._scan_sectors()
        if assessment.sectors:
            assessment.sector_leader = assessment.sectors[0].sector_name
            assessment.sector_laggard = assessment.sectors[-1].sector_name

            # Find our sector rank
            for i, s in enumerate(assessment.sectors):
                if s.sector_etf == self.our_sector:
                    assessment.our_sector_rank = i + 1
                    if i <= 3:
                        assessment.rotation_signal = "into_our_sector"
                    elif i >= len(assessment.sectors) - 3:
                        assessment.rotation_signal = "out_of_our_sector"
                    else:
                        assessment.rotation_signal = "neutral"
                    break

        # 3. Check positions
        position_alerts = await self._check_positions()
        assessment.stops_hit = position_alerts.get("stops_hit", [])
        assessment.near_support = position_alerts.get("near_support", [])
        assessment.near_resistance = position_alerts.get("near_resistance", [])

        # 4. Determine market status
        assessment.market_status = self._determine_market_status(assessment)

        # 5. Generate recommendation
        self._generate_recommendation(assessment)

        # 6. Save assessment
        if self.output_dir:
            self._save_assessment(assessment)

        return assessment

    async def _compare_gaps(self) -> list[PreMarketVsOpen]:
        """Compare pre-market prices to current prices."""
        gaps = []

        for symbol in self.watchlist:
            try:
                # Get current data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d", interval="5m")

                if hist.empty:
                    continue

                # Get prices
                today = date.today()
                today_data = hist[hist.index.date == today]

                if today_data.empty:
                    continue

                price_at_935 = float(today_data["Close"].iloc[min(1, len(today_data)-1)])
                open_price = float(today_data["Open"].iloc[0])

                # Get previous close for change calculation
                prev_close = float(ticker.info.get("previousClose", open_price))

                # Get pre-market price (if available)
                premarket_price = self.premarket_data.get(symbol, prev_close)
                premarket_change_pct = ((premarket_price / prev_close) - 1) * 100

                # Calculate gap fade
                if abs(premarket_change_pct) > 0.1:
                    current_change_pct = ((price_at_935 / prev_close) - 1) * 100
                    gap_fade_pct = (1 - (current_change_pct / premarket_change_pct)) * 100
                    gap_fade_pct = max(0, min(100, gap_fade_pct))
                else:
                    gap_fade_pct = 0

                # Determine gap status
                if gap_fade_pct < 25:
                    gap_status = "holding"
                elif gap_fade_pct < 50:
                    gap_status = "fading"
                elif gap_fade_pct < 100:
                    gap_status = "reversing"
                else:
                    gap_status = "extending" if current_change_pct * premarket_change_pct < 0 else "holding"

                # Volume analysis
                avg_volume = float(ticker.info.get("averageVolume", 1))
                current_volume = float(today_data["Volume"].sum())
                # Estimate full day volume from partial data
                minutes_elapsed = len(today_data) * 5
                if minutes_elapsed > 0:
                    estimated_full_day = (current_volume / minutes_elapsed) * 390
                    volume_vs_avg = estimated_full_day / avg_volume if avg_volume > 0 else 1.0
                else:
                    volume_vs_avg = 1.0

                # Assessment
                if gap_status == "holding":
                    assessment_text = "Gap holding, momentum intact"
                elif gap_status == "fading":
                    assessment_text = "Gap fading, monitor closely"
                elif gap_status == "reversing":
                    assessment_text = "Gap reversing, consider defensive action"
                else:
                    assessment_text = "Price extending in opposite direction"

                gaps.append(PreMarketVsOpen(
                    symbol=symbol,
                    premarket_price=premarket_price,
                    premarket_change_pct=premarket_change_pct,
                    open_price=open_price,
                    price_at_935=price_at_935,
                    gap_status=gap_status,
                    gap_fade_pct=gap_fade_pct,
                    volume_vs_avg=volume_vs_avg,
                    assessment=assessment_text,
                ))

            except Exception as e:
                logger.warning(f"Failed to analyze {symbol}: {e}")

        return gaps

    async def _scan_sectors(self) -> list[SectorRotation]:
        """Scan sector ETFs for rotation signals."""
        sectors = []

        try:
            # Get SPY for relative strength
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="1d", interval="1m")
            spy_change = 0.0
            if not spy_hist.empty:
                spy_change = ((spy_hist["Close"].iloc[-1] / spy_hist["Open"].iloc[0]) - 1) * 100

            for etf, name in SECTOR_ETFS.items():
                try:
                    ticker = yf.Ticker(etf)
                    hist = ticker.history(period="1d", interval="1m")

                    if hist.empty:
                        continue

                    change_pct = ((hist["Close"].iloc[-1] / hist["Open"].iloc[0]) - 1) * 100
                    relative_strength = change_pct - spy_change

                    # Determine flow direction
                    if relative_strength > 0.5:
                        flow = "inflow"
                    elif relative_strength < -0.5:
                        flow = "outflow"
                    else:
                        flow = "neutral"

                    sectors.append(SectorRotation(
                        sector_etf=etf,
                        sector_name=name,
                        change_pct=change_pct,
                        rank=0,  # Will be set after sorting
                        relative_strength=relative_strength,
                        flow_direction=flow,
                    ))

                except Exception as e:
                    logger.warning(f"Failed to analyze sector {etf}: {e}")

            # Sort by change and assign ranks
            sectors.sort(key=lambda x: x.change_pct, reverse=True)
            for i, s in enumerate(sectors):
                s.rank = i + 1

        except Exception as e:
            logger.error(f"Sector scan failed: {e}")

        return sectors

    async def _check_positions(self) -> dict[str, list[str]]:
        """Check positions against their levels."""
        alerts = {
            "stops_hit": [],
            "near_support": [],
            "near_resistance": [],
        }

        for symbol, levels in self.position_levels.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d", interval="1m")

                if hist.empty:
                    continue

                current_price = float(hist["Close"].iloc[-1])

                # Check stop
                stop = levels.get("stop")
                if stop and current_price < stop:
                    alerts["stops_hit"].append(f"{symbol} @ ${current_price:.2f} (stop: ${stop:.2f})")

                # Check support
                support = levels.get("support")
                if support:
                    distance_pct = ((current_price - support) / support) * 100
                    if distance_pct < 1:
                        alerts["near_support"].append(f"{symbol} @ ${current_price:.2f} (support: ${support:.2f})")

                # Check resistance
                resistance = levels.get("resistance")
                if resistance:
                    distance_pct = ((resistance - current_price) / current_price) * 100
                    if distance_pct < 1:
                        alerts["near_resistance"].append(f"{symbol} @ ${current_price:.2f} (resistance: ${resistance:.2f})")

            except Exception as e:
                logger.warning(f"Failed to check levels for {symbol}: {e}")

        return alerts

    def _determine_market_status(self, assessment: OpenAssessment) -> str:
        """Determine overall market status."""
        # Count signals
        risk_on_signals = 0
        risk_off_signals = 0

        # Gap analysis
        if len(assessment.gaps_holding) > len(assessment.gaps_fading):
            risk_on_signals += 1
        elif len(assessment.gaps_fading) > len(assessment.gaps_holding):
            risk_off_signals += 1

        # Sector rotation
        if assessment.rotation_signal == "into_our_sector":
            risk_on_signals += 1
        elif assessment.rotation_signal == "out_of_our_sector":
            risk_off_signals += 1

        # Position alerts
        if assessment.stops_hit:
            risk_off_signals += 2

        # Determine status
        if risk_on_signals > risk_off_signals:
            return "risk_on"
        elif risk_off_signals > risk_on_signals:
            return "risk_off"
        else:
            return "mixed"

    def _generate_recommendation(self, assessment: OpenAssessment) -> None:
        """Generate recommendation based on assessment."""
        # Count concerns
        concerns = 0

        # Major gap fades
        major_fades = [g for g in assessment.gaps if g.gap_fade_pct > 50]
        if len(major_fades) > len(assessment.gaps) / 2:
            concerns += 2
            assessment.modifications.append("Reduce position sizes on fading gaps")

        # Sector rotation against us
        if assessment.rotation_signal == "out_of_our_sector":
            concerns += 1
            assessment.modifications.append("Consider reducing sector exposure")

        # Stops hit
        if assessment.stops_hit:
            concerns += 2
            for stop in assessment.stops_hit:
                assessment.priority_actions.append(f"Execute stop loss: {stop}")

        # Near support
        if assessment.near_support:
            concerns += 1
            assessment.modifications.append("Tighten stops on positions near support")

        # Set plan status and confidence
        if concerns >= 3:
            assessment.plan_status = "DEFENSIVE"
            assessment.confidence = 0.3
            assessment.notes = "Multiple warning signs - reduce exposure, tighten stops"
        elif concerns >= 1:
            assessment.plan_status = "MODIFY"
            assessment.confidence = 0.5
            assessment.notes = "Some concerns - proceed with modifications"
        else:
            assessment.plan_status = "PROCEED"
            assessment.confidence = 0.7
            assessment.notes = "Market conditions support morning plan"

    def _save_assessment(self, assessment: OpenAssessment) -> None:
        """Save assessment to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.output_dir / f"open_assessment_{datetime.now().strftime('%Y-%m-%d')}.json"

        with open(filepath, "w") as f:
            json.dump(assessment.to_dict(), f, indent=2)

        # Also save markdown version
        md_path = filepath.with_suffix(".md")
        with open(md_path, "w") as f:
            f.write(assessment.to_markdown())

        logger.info(f"Saved open assessment to {filepath}")


async def run_morning_open_protocol(
    watchlist: list[str],
    premarket_data: dict[str, float] | None = None,
    position_levels: dict[str, dict[str, float]] | None = None,
    our_sector: str = "XLE",
    output_dir: Path | None = None,
) -> OpenAssessment:
    """
    Convenience function to run the morning open protocol.

    Args:
        watchlist: Symbols to monitor
        premarket_data: Pre-market prices from morning briefing
        position_levels: Support/resistance/stop levels
        our_sector: Primary sector we're exposed to
        output_dir: Directory to save results

    Returns:
        OpenAssessment with recommendations
    """
    protocol = MorningOpenProtocol(
        watchlist=watchlist,
        premarket_data=premarket_data,
        position_levels=position_levels,
        our_sector=our_sector,
        output_dir=output_dir,
    )

    return await protocol.run_assessment()
