"""Alternative Signal Generators - Connect unused data sources to trading signals.

This module bridges the gap between implemented data sources and actionable signals.
It provides generators for:
- Weather → Energy signals (HDD anomalies → nat gas)
- FDA Calendar → Binary event alerts
- Short Interest + Social → Squeeze candidates
- Research Insights → Actionable recommendations

Created: 2026-01-19
Based on: docs/SYSTEM_COHESION_AUDIT.md, docs/ALTERNATIVE_DATA_OPPORTUNITIES.md
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class WeatherEnergySignal:
    """Signal derived from weather anomalies."""

    timestamp: datetime
    signal_type: str  # "hdd_anomaly", "cdd_anomaly", "extreme_weather"
    direction: str  # "bullish", "bearish"
    strength: float  # 0-1
    affected_symbols: list[str]
    description: str
    hdd_zscore: Optional[float] = None
    cdd_zscore: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "direction": self.direction,
            "strength": self.strength,
            "affected_symbols": self.affected_symbols,
            "description": self.description,
            "hdd_zscore": self.hdd_zscore,
            "cdd_zscore": self.cdd_zscore,
        }


@dataclass
class FDASignal:
    """Signal for upcoming FDA binary events."""

    timestamp: datetime
    symbol: str
    company: str
    drug_name: str
    event_type: str
    event_date: datetime
    days_until: int
    approval_probability: float
    is_binary: bool
    has_positive_designations: bool
    description: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "company": self.company,
            "drug_name": self.drug_name,
            "event_type": self.event_type,
            "event_date": self.event_date.isoformat(),
            "days_until": self.days_until,
            "approval_probability": self.approval_probability,
            "is_binary": self.is_binary,
            "has_positive_designations": self.has_positive_designations,
            "description": self.description,
        }


@dataclass
class SqueezeCandidate:
    """Stock with short squeeze potential."""

    timestamp: datetime
    symbol: str
    squeeze_score: float  # 0-1, higher = more potential
    short_percent_of_float: float
    days_to_cover: float
    social_mentions_growth: Optional[float] = None  # % growth in mentions
    price_momentum_5d: Optional[float] = None  # 5-day price change %
    volume_ratio: Optional[float] = None  # Current vs average volume
    market_cap_billions: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "squeeze_score": self.squeeze_score,
            "short_percent_of_float": self.short_percent_of_float,
            "days_to_cover": self.days_to_cover,
            "social_mentions_growth": self.social_mentions_growth,
            "price_momentum_5d": self.price_momentum_5d,
            "volume_ratio": self.volume_ratio,
            "market_cap_billions": self.market_cap_billions,
            "description": self.description,
        }


@dataclass
class ResearchInsightSummary:
    """Summary of actionable research insights."""

    timestamp: datetime
    total_insights: int
    actionable_unimplemented: int
    top_insights: list[dict]  # List of insight summaries
    successful_strategies: list[dict]  # From experiments
    high_confidence_patterns: list[dict]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_insights": self.total_insights,
            "actionable_unimplemented": self.actionable_unimplemented,
            "top_insights": self.top_insights,
            "successful_strategies": self.successful_strategies,
            "high_confidence_patterns": self.high_confidence_patterns,
        }


@dataclass
class AlternativeSignals:
    """Container for all alternative signals."""

    timestamp: datetime
    weather_signals: list[WeatherEnergySignal] = field(default_factory=list)
    fda_signals: list[FDASignal] = field(default_factory=list)
    squeeze_candidates: list[SqueezeCandidate] = field(default_factory=list)
    research_insights: Optional[ResearchInsightSummary] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "weather_signals": [s.to_dict() for s in self.weather_signals],
            "fda_signals": [s.to_dict() for s in self.fda_signals],
            "squeeze_candidates": [s.to_dict() for s in self.squeeze_candidates],
            "research_insights": self.research_insights.to_dict() if self.research_insights else None,
        }


# ============================================================================
# Signal Generators
# ============================================================================

class WeatherEnergySignalGenerator:
    """Generate trading signals from weather data.

    Uses HDD (Heating Degree Days) anomalies to predict natural gas demand.

    Pattern from docs/TRADING_PATTERNS.md:
    - HDD > 2 std dev above rolling mean → Long UNG/nat gas
    - CDD > 2 std dev above rolling mean → Long utilities, short nat gas
    """

    # Symbols affected by weather
    NAT_GAS_SYMBOLS = ["UNG", "BOIL", "KOLD"]  # KOLD is inverse
    UTILITY_SYMBOLS = ["XLU", "NEE", "DUK", "SO"]
    HEATING_OIL_SYMBOLS = ["UHN"]

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (paths.scraped_data / "weather")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def generate_signals(self) -> list[WeatherEnergySignal]:
        """Generate weather-based energy signals."""
        signals = []

        try:
            from src.data.sources.alternative.weather import (
                WeatherDataSource,
                WeatherFeatureEngine,
            )

            weather = WeatherDataSource(
                include_major_cities=True,
                include_agricultural=False,
            )

            # Get historical data for energy-relevant locations
            energy_locations = ["houston", "chicago", "new_york"]

            for loc in energy_locations:
                try:
                    df = await weather.fetch_historical(
                        location_key=loc,
                        start=datetime.now() - timedelta(days=60),
                        end=datetime.now(),
                    )

                    if df.empty:
                        continue

                    # Add weather features
                    df = WeatherFeatureEngine.add_all_features(df)

                    # Check for HDD anomaly (cold snap)
                    if "hdd" in df.columns and len(df) > 30:
                        hdd_zscore = WeatherFeatureEngine.compute_weather_anomaly(
                            df["hdd"], window=30
                        ).iloc[-1]

                        if pd.notna(hdd_zscore) and hdd_zscore > 2.0:
                            signals.append(WeatherEnergySignal(
                                timestamp=datetime.now(),
                                signal_type="hdd_anomaly",
                                direction="bullish",
                                strength=min(1.0, hdd_zscore / 4.0),
                                affected_symbols=self.NAT_GAS_SYMBOLS + self.HEATING_OIL_SYMBOLS,
                                description=f"Cold snap detected at {loc}: HDD z-score {hdd_zscore:.2f}. "
                                           f"Consider long UNG/nat gas positions.",
                                hdd_zscore=hdd_zscore,
                            ))

                    # Check for CDD anomaly (heat wave)
                    if "cdd" in df.columns and len(df) > 30:
                        cdd_zscore = WeatherFeatureEngine.compute_weather_anomaly(
                            df["cdd"], window=30
                        ).iloc[-1]

                        if pd.notna(cdd_zscore) and cdd_zscore > 2.0:
                            signals.append(WeatherEnergySignal(
                                timestamp=datetime.now(),
                                signal_type="cdd_anomaly",
                                direction="bullish",
                                strength=min(1.0, cdd_zscore / 4.0),
                                affected_symbols=self.UTILITY_SYMBOLS,
                                description=f"Heat wave detected at {loc}: CDD z-score {cdd_zscore:.2f}. "
                                           f"Consider long utility positions (increased cooling demand).",
                                cdd_zscore=cdd_zscore,
                            ))

                except Exception as e:
                    logger.warning(f"Weather fetch failed for {loc}: {e}")
                    continue

            await weather.close()

        except ImportError as e:
            logger.warning(f"Weather module not available: {e}")
        except Exception as e:
            logger.error(f"Weather signal generation failed: {e}")

        return signals


class FDASignalGenerator:
    """Generate signals for upcoming FDA binary events.

    Pattern from docs/TRADING_PATTERNS.md:
    - Position 2-3 weeks before PDUFA dates
    - Use options for limited risk on binary events
    """

    def __init__(self, lookforward_days: int = 30):
        self.lookforward_days = lookforward_days

    async def generate_signals(self) -> list[FDASignal]:
        """Generate FDA binary event signals."""
        signals = []

        try:
            from src.data.sources.alternative.fda_calendar import (
                FDACalendarSource,
            )

            fda = FDACalendarSource(lookforward_days=self.lookforward_days)
            calendar = await fda.get_calendar()

            for event in calendar.upcoming:
                if event.days_until <= self.lookforward_days and event.days_until >= 0:
                    signals.append(FDASignal(
                        timestamp=datetime.now(),
                        symbol=event.symbol,
                        company=event.company,
                        drug_name=event.drug_name,
                        event_type=event.event_type,
                        event_date=event.expected_date,
                        days_until=event.days_until,
                        approval_probability=event.estimated_approval_probability,
                        is_binary=event.is_binary_event,
                        has_positive_designations=event.has_positive_designations,
                        description=f"{event.symbol}: {event.drug_name} {event.event_type} "
                                   f"in {event.days_until} days. "
                                   f"Indication: {event.indication}. "
                                   f"Est. approval: {event.estimated_approval_probability:.0%}",
                    ))

            await fda.close()

        except ImportError as e:
            logger.warning(f"FDA calendar module not available: {e}")
        except Exception as e:
            logger.error(f"FDA signal generation failed: {e}")

        return signals


class SqueezeScanner:
    """Scan for short squeeze candidates.

    Pattern from docs/TRADING_PATTERNS.md:
    - Short interest > 30% of float
    - Social mentions growth > 100% in 7 days
    - Market cap < $10B (small enough to squeeze)
    """

    # Default universe to scan
    DEFAULT_UNIVERSE = [
        # Known high short interest names (update periodically)
        "GME", "AMC", "BBBY", "KOSS", "EXPR", "NAKD",
        "SPCE", "NKLA", "RIDE", "WKHS", "GOEV",
        "CLOV", "WISH", "SOFI", "PLTR",
        "CVNA", "UPST", "AFRM", "HOOD",
    ]

    def __init__(
        self,
        min_short_pct: float = 0.15,
        min_days_to_cover: float = 3.0,
        max_market_cap_b: float = 10.0,
    ):
        self.min_short_pct = min_short_pct
        self.min_days_to_cover = min_days_to_cover
        self.max_market_cap_b = max_market_cap_b

    async def scan(
        self,
        symbols: Optional[list[str]] = None,
    ) -> list[SqueezeCandidate]:
        """Scan for squeeze candidates."""
        candidates = []
        symbols = symbols or self.DEFAULT_UNIVERSE

        try:
            from src.data.sources.alternative.short_interest import ShortInterestSource
            from src.core import Symbol

            short_source = ShortInterestSource()

            for sym in symbols:
                try:
                    data = short_source.fetch_short_interest(Symbol(sym))

                    if data is None:
                        continue

                    # Check squeeze criteria
                    if not data.is_squeeze_candidate(
                        min_short_pct=self.min_short_pct,
                        min_days_to_cover=self.min_days_to_cover,
                    ):
                        continue

                    # Calculate squeeze score
                    score = self._calculate_squeeze_score(data)

                    candidates.append(SqueezeCandidate(
                        timestamp=datetime.now(),
                        symbol=sym,
                        squeeze_score=score,
                        short_percent_of_float=data.short_percent_of_float,
                        days_to_cover=data.short_ratio,
                        description=f"{sym}: {data.short_percent_of_float:.1%} short, "
                                   f"{data.short_ratio:.1f} days to cover. "
                                   f"Squeeze score: {score:.2f}",
                    ))

                except Exception as e:
                    logger.debug(f"Failed to get short data for {sym}: {e}")
                    continue

            # Sort by squeeze score
            candidates.sort(key=lambda x: x.squeeze_score, reverse=True)

        except ImportError as e:
            logger.warning(f"Short interest module not available: {e}")
        except Exception as e:
            logger.error(f"Squeeze scan failed: {e}")

        return candidates

    def _calculate_squeeze_score(self, data) -> float:
        """Calculate squeeze potential score (0-1)."""
        score = 0.0

        # Short percent contribution (0-0.4)
        if data.short_percent_of_float > 0.50:
            score += 0.4
        elif data.short_percent_of_float > 0.30:
            score += 0.3
        elif data.short_percent_of_float > 0.20:
            score += 0.2
        elif data.short_percent_of_float > 0.15:
            score += 0.1

        # Days to cover contribution (0-0.3)
        if data.short_ratio > 10:
            score += 0.3
        elif data.short_ratio > 5:
            score += 0.2
        elif data.short_ratio > 3:
            score += 0.1

        # Short interest change contribution (0-0.3)
        if data.short_change_pct is not None:
            if data.short_change_pct > 20:
                score += 0.3  # Growing short interest
            elif data.short_change_pct > 10:
                score += 0.2
            elif data.short_change_pct > 0:
                score += 0.1

        return min(1.0, score)


class ResearchInsightsLoader:
    """Load and summarize research insights for morning briefings.

    Connects to the ResearchSessionTracker to surface:
    - Actionable, unimplemented insights
    - Successful strategies from experiments
    - High-confidence patterns
    """

    def __init__(self, tracker_dir: Optional[Path] = None):
        self.tracker_dir = tracker_dir or paths.research_tracker

    def load_summary(self, max_insights: int = 5) -> ResearchInsightSummary:
        """Load summary of research insights.

        Note: Handles the nested list format in insights.json where data is stored as
        a list of dicts, each dict containing multiple insights keyed by ID.
        """
        try:
            import json

            insights_file = self.tracker_dir / "insights.json"
            experiments_file = self.tracker_dir / "experiments.json"
            patterns_file = self.tracker_dir / "patterns.json"

            # Load insights with format handling
            insights = []
            if insights_file.exists():
                with open(insights_file) as f:
                    data = json.load(f)

                # Handle nested list format: [{id: insight, id: insight}, {id: insight}]
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for insight_id, insight_data in item.items():
                                if isinstance(insight_data, dict) and "title" in insight_data:
                                    insights.append(insight_data)
                elif isinstance(data, dict):
                    # Handle dict format: {id: insight, id: insight}
                    for insight_id, insight_data in data.items():
                        if isinstance(insight_data, dict) and "title" in insight_data:
                            insights.append(insight_data)

            # Filter actionable, unimplemented insights
            actionable = [
                i for i in insights
                if i.get("actionable", True)
                and not i.get("implemented", False)
                and i.get("confidence", 0) >= 0.3
            ]
            # Sort by confidence
            actionable.sort(key=lambda x: x.get("confidence", 0), reverse=True)

            # Load experiments
            experiments = []
            if experiments_file.exists():
                with open(experiments_file) as f:
                    exp_data = json.load(f)
                if isinstance(exp_data, dict):
                    experiments = list(exp_data.values())
                elif isinstance(exp_data, list):
                    experiments = exp_data

            # Filter successful experiments
            successful = [
                e for e in experiments
                if e.get("result") == "success"
                and (e.get("sharpe") or 0) >= 0.5
                and (e.get("p_value") or 1.0) <= 0.05
            ]
            successful.sort(key=lambda x: x.get("sharpe", 0), reverse=True)

            # Load patterns
            patterns = []
            if patterns_file.exists():
                with open(patterns_file) as f:
                    pat_data = json.load(f)
                if isinstance(pat_data, dict):
                    patterns = list(pat_data.values())

            # Filter high-confidence patterns
            high_conf_patterns = [
                p for p in patterns
                if p.get("confidence", 0) > 0.6
            ]
            high_conf_patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)

            return ResearchInsightSummary(
                timestamp=datetime.now(),
                total_insights=len(insights),
                actionable_unimplemented=len(actionable),
                top_insights=[
                    {
                        "id": i.get("id", "unknown"),
                        "title": i.get("title", "Untitled"),
                        "category": i.get("category", "unknown"),
                        "confidence": i.get("confidence", 0.5),
                        "description": (i.get("description", "")[:200] + "..."
                                       if len(i.get("description", "")) > 200
                                       else i.get("description", "")),
                    }
                    for i in actionable[:max_insights]
                ],
                successful_strategies=[
                    {
                        "strategy": e.get("strategy", "unknown"),
                        "symbol": e.get("symbol", "unknown"),
                        "sharpe": e.get("sharpe"),
                        "p_value": e.get("p_value"),
                    }
                    for e in successful[:max_insights]
                ],
                high_confidence_patterns=[
                    {
                        "name": p.get("name", "unknown"),
                        "confidence": p.get("confidence", 0),
                        "observations": p.get("observations", 0),
                    }
                    for p in high_conf_patterns[:max_insights]
                ],
            )

        except Exception as e:
            logger.error(f"Failed to load research insights: {e}")
            return ResearchInsightSummary(
                timestamp=datetime.now(),
                total_insights=0,
                actionable_unimplemented=0,
                top_insights=[],
                successful_strategies=[],
                high_confidence_patterns=[],
            )


# ============================================================================
# Main Generator
# ============================================================================

class AlternativeSignalGenerator:
    """Main class that generates all alternative signals.

    Use this in morning briefings and trade decisions to get
    signals from previously unused data sources.
    """

    def __init__(self):
        self.weather = WeatherEnergySignalGenerator()
        self.fda = FDASignalGenerator()
        self.squeeze = SqueezeScanner()
        self.research = ResearchInsightsLoader()

    async def generate_all(self) -> AlternativeSignals:
        """Generate all alternative signals."""
        logger.info("Generating alternative signals...")

        # Run generators concurrently
        weather_task = asyncio.create_task(self.weather.generate_signals())
        fda_task = asyncio.create_task(self.fda.generate_signals())
        squeeze_task = asyncio.create_task(self.squeeze.scan())

        weather_signals = await weather_task
        fda_signals = await fda_task
        squeeze_candidates = await squeeze_task

        # Research insights (sync)
        research_summary = self.research.load_summary()

        signals = AlternativeSignals(
            timestamp=datetime.now(),
            weather_signals=weather_signals,
            fda_signals=fda_signals,
            squeeze_candidates=squeeze_candidates,
            research_insights=research_summary,
        )

        logger.info(
            f"Generated {len(weather_signals)} weather signals, "
            f"{len(fda_signals)} FDA signals, "
            f"{len(squeeze_candidates)} squeeze candidates, "
            f"{research_summary.actionable_unimplemented} actionable insights"
        )

        return signals

    def save_to_state(self, signals: AlternativeSignals, output_path: Optional[Path] = None) -> None:
        """Save signals to a file for the daemon to pick up."""
        output_path = output_path or (paths.live / "alternative_signals.json")

        with open(output_path, "w") as f:
            json.dump(signals.to_dict(), f, indent=2)

        logger.info(f"Saved alternative signals to {output_path}")


# ============================================================================
# CLI
# ============================================================================

async def main():
    """CLI for testing alternative signal generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate alternative signals")
    parser.add_argument("--weather", action="store_true", help="Generate weather signals only")
    parser.add_argument("--fda", action="store_true", help="Generate FDA signals only")
    parser.add_argument("--squeeze", action="store_true", help="Generate squeeze signals only")
    parser.add_argument("--research", action="store_true", help="Load research insights only")
    parser.add_argument("--all", action="store_true", help="Generate all signals")
    parser.add_argument("--save", action="store_true", help="Save to state file")

    args = parser.parse_args()

    generator = AlternativeSignalGenerator()

    if args.weather or (not any([args.fda, args.squeeze, args.research])):
        print("\n=== Weather Signals ===")
        signals = await generator.weather.generate_signals()
        for s in signals:
            print(f"  {s.signal_type}: {s.description}")

    if args.fda or args.all:
        print("\n=== FDA Signals ===")
        signals = await generator.fda.generate_signals()
        for s in signals:
            print(f"  {s.symbol}: {s.description}")

    if args.squeeze or args.all:
        print("\n=== Squeeze Candidates ===")
        candidates = await generator.squeeze.scan()
        for c in candidates[:10]:
            print(f"  {c.symbol}: {c.description}")

    if args.research or args.all:
        print("\n=== Research Insights ===")
        summary = generator.research.load_summary()
        print(f"  Total insights: {summary.total_insights}")
        print(f"  Actionable (unimplemented): {summary.actionable_unimplemented}")
        for i in summary.top_insights[:3]:
            print(f"    - [{i['category']}] {i['title']} (conf: {i['confidence']:.2f})")

    if args.all:
        print("\n=== Full Generation ===")
        all_signals = await generator.generate_all()
        print(f"Weather: {len(all_signals.weather_signals)} signals")
        print(f"FDA: {len(all_signals.fda_signals)} signals")
        print(f"Squeeze: {len(all_signals.squeeze_candidates)} candidates")

        if args.save:
            generator.save_to_state(all_signals)
            print(f"\nSaved to {paths.live / 'alternative_signals.json'}")


if __name__ == "__main__":
    asyncio.run(main())
