#!/usr/bin/env python3
"""
Geopolitical Event Tracker

Tracks geopolitical events, their market implications, and historical analogues.
Designed for event-driven trading strategies.

Usage:
    from workflows.research.geopolitical_tracker import GeopoliticalTracker, GeopoliticalEvent

    tracker = GeopoliticalTracker()
    tracker.add_event(event)
    tracker.update_scenario_probability("VEN_2026", "prolonged_reconstruction", 0.45)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path("/home/nock/quant_results/geopolitical_events")


class EventType(Enum):
    """Types of geopolitical events."""
    REGIME_CHANGE = "regime_change"
    MILITARY_ACTION = "military_action"
    SANCTIONS = "sanctions"
    ELECTION = "election"
    TRADE_WAR = "trade_war"
    CIVIL_UNREST = "civil_unrest"
    NATURAL_DISASTER = "natural_disaster"
    CURRENCY_CRISIS = "currency_crisis"
    TERRORISM = "terrorism"
    DIPLOMATIC = "diplomatic"


@dataclass
class HistoricalAnalogue:
    """Historical event used as reference for current event."""
    name: str
    date: str
    event_type: str
    market_reaction: dict[str, float]  # asset -> % change
    recovery_days: int
    key_lessons: list[str]


@dataclass
class ScenarioProbability:
    """Probability-weighted scenario for event outcome."""
    name: str
    probability: float  # 0-1
    description: str
    market_impact: dict[str, float]  # asset -> expected % change
    timeframe_days: int
    key_triggers: list[str]


@dataclass
class GeopoliticalEvent:
    """Represents a tracked geopolitical event."""
    id: str
    name: str
    date: datetime
    event_type: EventType
    region: str
    description: str
    affected_assets: list[str]
    scenarios: list[ScenarioProbability]
    historical_analogues: list[HistoricalAnalogue]
    catalyst_keywords: list[str]  # For news monitoring
    status: str = "active"  # "active", "resolved", "monitoring"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "date": self.date.isoformat(),
            "event_type": self.event_type.value,
            "region": self.region,
            "description": self.description,
            "affected_assets": self.affected_assets,
            "scenarios": [
                {
                    "name": s.name,
                    "probability": s.probability,
                    "description": s.description,
                    "market_impact": s.market_impact,
                    "timeframe_days": s.timeframe_days,
                    "key_triggers": s.key_triggers,
                }
                for s in self.scenarios
            ],
            "historical_analogues": [
                {
                    "name": a.name,
                    "date": a.date,
                    "event_type": a.event_type,
                    "market_reaction": a.market_reaction,
                    "recovery_days": a.recovery_days,
                    "key_lessons": a.key_lessons,
                }
                for a in self.historical_analogues
            ],
            "catalyst_keywords": self.catalyst_keywords,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "notes": self.notes,
        }


class GeopoliticalTracker:
    """Tracks and analyzes geopolitical events for trading."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events: dict[str, GeopoliticalEvent] = {}
        self._load_events()

    def _load_events(self) -> None:
        """Load events from storage."""
        events_file = self.data_dir / "events.json"
        if events_file.exists():
            try:
                with open(events_file) as f:
                    data = json.load(f)
                for event_data in data:
                    event = self._dict_to_event(event_data)
                    self.events[event.id] = event
                logger.info(f"Loaded {len(self.events)} geopolitical events")
            except Exception as e:
                logger.warning(f"Failed to load events: {e}")

    def _save_events(self) -> None:
        """Save events to storage."""
        events_file = self.data_dir / "events.json"
        data = [e.to_dict() for e in self.events.values()]
        with open(events_file, "w") as f:
            json.dump(data, f, indent=2)

    def _dict_to_event(self, data: dict) -> GeopoliticalEvent:
        """Convert dict back to GeopoliticalEvent."""
        scenarios = [
            ScenarioProbability(
                name=s["name"],
                probability=s["probability"],
                description=s["description"],
                market_impact=s["market_impact"],
                timeframe_days=s["timeframe_days"],
                key_triggers=s["key_triggers"],
            )
            for s in data.get("scenarios", [])
        ]

        analogues = [
            HistoricalAnalogue(
                name=a["name"],
                date=a["date"],
                event_type=a["event_type"],
                market_reaction=a["market_reaction"],
                recovery_days=a["recovery_days"],
                key_lessons=a["key_lessons"],
            )
            for a in data.get("historical_analogues", [])
        ]

        return GeopoliticalEvent(
            id=data["id"],
            name=data["name"],
            date=datetime.fromisoformat(data["date"]),
            event_type=EventType(data["event_type"]),
            region=data["region"],
            description=data["description"],
            affected_assets=data["affected_assets"],
            scenarios=scenarios,
            historical_analogues=analogues,
            catalyst_keywords=data.get("catalyst_keywords", []),
            status=data.get("status", "active"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            notes=data.get("notes", []),
        )

    def add_event(self, event: GeopoliticalEvent) -> None:
        """Add a new geopolitical event."""
        self.events[event.id] = event
        self._save_events()
        logger.info(f"Added geopolitical event: {event.id} - {event.name}")

    def update_scenario_probability(
        self, event_id: str, scenario_name: str, new_probability: float
    ) -> None:
        """Update probability for a specific scenario."""
        if event_id not in self.events:
            raise ValueError(f"Event {event_id} not found")

        event = self.events[event_id]
        total_probability = 0

        for scenario in event.scenarios:
            if scenario.name == scenario_name:
                scenario.probability = new_probability
            total_probability += scenario.probability

        # Normalize if needed (warn if significantly off)
        if abs(total_probability - 1.0) > 0.1:
            logger.warning(f"Scenario probabilities sum to {total_probability:.2f}, not 1.0")

        event.updated_at = datetime.now()
        self._save_events()

    def add_note(self, event_id: str, note: str) -> None:
        """Add a timestamped note to an event."""
        if event_id not in self.events:
            raise ValueError(f"Event {event_id} not found")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.events[event_id].notes.append(f"[{timestamp}] {note}")
        self.events[event_id].updated_at = datetime.now()
        self._save_events()

    def get_active_events(self) -> list[GeopoliticalEvent]:
        """Get all active events."""
        return [e for e in self.events.values() if e.status == "active"]

    def get_events_by_asset(self, symbol: str) -> list[GeopoliticalEvent]:
        """Get events affecting a specific asset."""
        return [e for e in self.events.values() if symbol in e.affected_assets]

    def get_expected_impact(self, symbol: str) -> dict[str, float]:
        """Calculate probability-weighted expected impact for a symbol."""
        total_impact = 0
        active_events = self.get_events_by_asset(symbol)

        if not active_events:
            return {"expected_return": 0, "events": 0}

        for event in active_events:
            if event.status != "active":
                continue

            for scenario in event.scenarios:
                if symbol in scenario.market_impact:
                    total_impact += scenario.probability * scenario.market_impact[symbol]

        return {
            "expected_return": total_impact,
            "events": len(active_events),
        }

    def print_event_summary(self, event_id: str) -> None:
        """Print detailed summary of an event."""
        if event_id not in self.events:
            print(f"Event {event_id} not found")
            return

        event = self.events[event_id]

        print("\n" + "=" * 70)
        print(f"GEOPOLITICAL EVENT: {event.name}")
        print("=" * 70)
        print(f"ID: {event.id}")
        print(f"Date: {event.date.strftime('%Y-%m-%d')}")
        print(f"Type: {event.event_type.value}")
        print(f"Region: {event.region}")
        print(f"Status: {event.status}")
        print(f"\nDescription:\n{event.description}")

        print(f"\nAffected Assets: {', '.join(event.affected_assets)}")
        print(f"Catalyst Keywords: {', '.join(event.catalyst_keywords)}")

        print("\n" + "-" * 70)
        print("SCENARIOS")
        print("-" * 70)
        for scenario in sorted(event.scenarios, key=lambda x: -x.probability):
            print(f"\n{scenario.name} ({scenario.probability:.0%})")
            print(f"  {scenario.description}")
            print(f"  Timeframe: {scenario.timeframe_days} days")
            print(f"  Market Impact:")
            for asset, impact in scenario.market_impact.items():
                print(f"    {asset}: {impact:+.0%}")
            print(f"  Triggers: {', '.join(scenario.key_triggers)}")

        if event.historical_analogues:
            print("\n" + "-" * 70)
            print("HISTORICAL ANALOGUES")
            print("-" * 70)
            for analogue in event.historical_analogues:
                print(f"\n{analogue.name} ({analogue.date})")
                print(f"  Type: {analogue.event_type}")
                print(f"  Recovery: {analogue.recovery_days} days")
                print(f"  Market Reaction:")
                for asset, change in analogue.market_reaction.items():
                    print(f"    {asset}: {change:+.0%}")
                print(f"  Lessons: {'; '.join(analogue.key_lessons)}")

        if event.notes:
            print("\n" + "-" * 70)
            print("NOTES")
            print("-" * 70)
            for note in event.notes[-5:]:  # Last 5 notes
                print(f"  {note}")


def create_venezuela_event() -> GeopoliticalEvent:
    """Create the Venezuela/Maduro capture event."""
    return GeopoliticalEvent(
        id="VEN_2026_MADURO_CAPTURE",
        name="US Capture of Venezuelan President Maduro",
        date=datetime(2026, 1, 3),
        event_type=EventType.REGIME_CHANGE,
        region="Latin America",
        description=(
            "US military captured Venezuelan President Nicolas Maduro in 'Operation Absolute Resolve'. "
            "First major US regime change in Latin America since Panama 1989. "
            "Trump stated US will 'run' Venezuela. Major implications for oil markets, "
            "oilfield services, and regional stability."
        ),
        affected_assets=[
            "SLB", "HAL", "BKR", "WFRD",  # Oilfield services
            "VLO", "PSX", "PBF",  # Refiners
            "FRO", "STNG",  # Tankers
            "GLD", "GDX",  # Gold
            "CNQ", "SU",  # Canadian heavy crude
            "XLE", "USO",  # Energy sector
            "RCL", "NCLH", "CCL",  # Cruise lines (Cuba play)
            "MAR", "HLT",  # Hotels (Cuba play)
        ],
        scenarios=[
            ScenarioProbability(
                name="prolonged_reconstruction",
                probability=0.40,
                description="Gradual stabilization with periodic chaos. US stays committed. "
                            "Oilfield services benefit from reconstruction contracts.",
                market_impact={
                    "SLB": 0.30, "HAL": 0.25, "VLO": 0.20, "FRO": 0.15,
                    "GLD": 0.10, "XLE": 0.05,
                },
                timeframe_days=365,
                key_triggers=[
                    "PDVSA contract announcement",
                    "SLB Venezuela news",
                    "US commitment reaffirmed",
                ],
            ),
            ScenarioProbability(
                name="libya_style_chaos",
                probability=0.35,
                description="ELN attacks, colectivo resistance, fragmented control. "
                            "Creates vol spikes but doesn't derail reconstruction thesis.",
                market_impact={
                    "SLB": 0.15, "HAL": 0.10, "VLO": 0.10, "FRO": 0.20,
                    "GLD": 0.25, "XLE": -0.05,
                },
                timeframe_days=365,
                key_triggers=[
                    "ELN attack", "Colectivo violence", "Sabotage news",
                    "US casualty", "Security concerns",
                ],
            ),
            ScenarioProbability(
                name="smooth_transition",
                probability=0.25,
                description="Surprisingly smooth transition. Oil production recovers quickly. "
                            "Bearish for oil prices long-term but bullish for refiners.",
                market_impact={
                    "SLB": 0.15, "HAL": 0.10, "VLO": 0.30, "FRO": 0.10,
                    "GLD": -0.05, "USO": -0.15,
                },
                timeframe_days=180,
                key_triggers=[
                    "Peaceful protests", "Opposition cooperation",
                    "Military support for transition",
                ],
            ),
        ],
        historical_analogues=[
            HistoricalAnalogue(
                name="Panama 1989 (Operation Just Cause)",
                date="1989-12-20",
                event_type="regime_change",
                market_reaction={"SPY": 0.01, "oil": 0.02, "defense": 0.05},
                recovery_days=7,
                key_lessons=[
                    "Quick operation limits market impact",
                    "Small country = minimal global effect",
                    "Pre-existing US presence helped",
                ],
            ),
            HistoricalAnalogue(
                name="Iraq 2003 (Operation Iraqi Freedom)",
                date="2003-03-20",
                event_type="military_action",
                market_reaction={"SPY": -0.053, "oil": 0.10, "oilfield_services": 0.40},
                recovery_days=16,
                key_lessons=[
                    "Initial stocks decline, then recover",
                    "Oilfield services major winners",
                    "Reconstruction contracts dwarf war costs",
                    "KBR secured $39.5B in contracts",
                ],
            ),
            HistoricalAnalogue(
                name="Libya 2011 (NATO Intervention)",
                date="2011-03-19",
                event_type="military_action",
                market_reaction={"oil": 0.20, "SPY": -0.05, "emerging_markets": -0.10},
                recovery_days=0,  # Never recovered to pre-intervention levels
                key_lessons=[
                    "Production never recovered",
                    "Chaos persisted for years",
                    "Multiple factions = no stability",
                    "NATO left quickly after regime fell",
                ],
            ),
        ],
        catalyst_keywords=[
            "PDVSA", "Venezuela oil", "Maduro", "SLB Venezuela",
            "Schlumberger Venezuela", "Halliburton Venezuela",
            "ELN attack", "colectivo", "Venezuela violence",
            "Cuba sanctions", "Rubio Cuba", "Venezuela reconstruction",
        ],
        status="active",
    )


def main():
    """Initialize tracker with Venezuela event."""
    tracker = GeopoliticalTracker()

    # Add Venezuela event if not exists
    event = create_venezuela_event()
    if event.id not in tracker.events:
        tracker.add_event(event)

    # Print summary
    tracker.print_event_summary(event.id)

    # Show expected impacts
    print("\n" + "=" * 70)
    print("EXPECTED IMPACTS BY SYMBOL")
    print("=" * 70)

    symbols = ["SLB", "VLO", "HAL", "FRO", "GLD"]
    for symbol in symbols:
        impact = tracker.get_expected_impact(symbol)
        print(f"{symbol}: {impact['expected_return']:+.1%} expected return ({impact['events']} active events)")


if __name__ == "__main__":
    main()
