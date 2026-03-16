#!/usr/bin/env python3
"""Geopolitical Event Monitor - Track regional events affecting theses.

Monitors: Greenland/Arctic, Venezuela, China/Taiwan, Middle East, Russia/Ukraine
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Regions and their market impacts
REGIONS = {
    "greenland_arctic": {
        "name": "Greenland / Arctic",
        "keywords": ["greenland", "denmark", "arctic", "rare earth", "thule", "nuuk"],
        "thesis": "Defense spending increase, rare earth supply chain",
        "symbols_bullish": ["RTX", "LMT", "NOC", "GD", "HII", "MP"],
        "symbols_bearish": [],
        "tension_level": "elevated",  # calm, elevated, high, crisis
    },
    "venezuela": {
        "name": "Venezuela / Latin America",
        "keywords": ["venezuela", "maduro", "pdvsa", "chevron", "sanctions", "guaido"],
        "thesis": "Oil services recovery, tanker demand",
        "symbols_bullish": ["SLB", "HAL", "BKR", "FRO", "STNG", "DHT", "PBR"],
        "symbols_bearish": [],
        "tension_level": "elevated",
    },
    "china_taiwan": {
        "name": "China / Taiwan",
        "keywords": ["taiwan", "tsmc", "china", "pla", "strait", "xi jinping", "semiconductor"],
        "thesis": "Semiconductor supply risk, defense",
        "symbols_bullish": ["RTX", "LMT"],  # Defense benefits
        "symbols_bearish": ["TSM", "NVDA", "AMD", "AAPL"],  # Supply chain risk
        "tension_level": "elevated",
    },
    "middle_east": {
        "name": "Middle East / Oil",
        "keywords": ["iran", "israel", "saudi", "opec", "houthi", "red sea", "strait of hormuz"],
        "thesis": "Oil supply disruption, shipping risk",
        "symbols_bullish": ["XLE", "USO", "OIH", "FRO", "STNG"],
        "symbols_bearish": ["XLY", "JETS"],
        "tension_level": "high",
    },
    "russia_ukraine": {
        "name": "Russia / Ukraine",
        "keywords": ["ukraine", "russia", "putin", "zelensky", "nato", "crimea"],
        "thesis": "Energy supply, defense spending, grain",
        "symbols_bullish": ["RTX", "LMT", "XLE", "WEAT"],
        "symbols_bearish": ["EWG"],  # Germany
        "tension_level": "high",
    },
}

# News sources for geopolitical events
GEO_SOURCES = {
    "state_dept": "https://www.state.gov/press-releases/feed/",
    "defense_gov": "https://www.defense.gov/News/",
    "reuters_world": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
}


@dataclass
class GeopoliticalEvent:
    """A geopolitical event affecting markets."""
    event_id: str
    region: str
    title: str
    source: str
    date: datetime
    summary: str = ""
    tension_change: str = "neutral"  # escalation, de-escalation, neutral
    symbols_bullish: list[str] = field(default_factory=list)
    symbols_bearish: list[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "region": self.region,
            "title": self.title,
            "source": self.source,
            "date": self.date.isoformat(),
            "summary": self.summary,
            "tension_change": self.tension_change,
            "symbols_bullish": self.symbols_bullish,
            "symbols_bearish": self.symbols_bearish,
            "url": self.url,
        }


@dataclass
class RegionStatus:
    """Current status of a geopolitical region."""
    region_id: str
    name: str
    tension_level: str
    last_event: Optional[str] = None
    last_event_date: Optional[datetime] = None
    thesis_status: str = ""
    symbols_bullish: list[str] = field(default_factory=list)
    symbols_bearish: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "region_id": self.region_id,
            "name": self.name,
            "tension_level": self.tension_level,
            "last_event": self.last_event,
            "last_event_date": self.last_event_date.isoformat() if self.last_event_date else None,
            "thesis_status": self.thesis_status,
            "symbols_bullish": self.symbols_bullish,
            "symbols_bearish": self.symbols_bearish,
        }


class GeopoliticalMonitor:
    """Monitor geopolitical events affecting market theses."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live / "geopolitical"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    def _classify_region(self, text: str) -> tuple[Optional[str], dict]:
        """Classify text into a geopolitical region."""
        text = text.lower()
        for region_id, config in REGIONS.items():
            if any(kw in text for kw in config["keywords"]):
                return region_id, config
        return None, {}

    def _determine_tension_change(self, text: str) -> str:
        """Determine if event escalates or de-escalates tension."""
        text = text.lower()
        escalation_words = ["attack", "military", "threat", "sanction", "warning", "deploy", "strike", "tension"]
        deescalation_words = ["talks", "agreement", "peace", "withdraw", "negotiate", "deal", "resolution"]

        escalation_count = sum(1 for w in escalation_words if w in text)
        deescalation_count = sum(1 for w in deescalation_words if w in text)

        if escalation_count > deescalation_count:
            return "escalation"
        elif deescalation_count > escalation_count:
            return "de-escalation"
        return "neutral"

    async def scan_news_for_events(self) -> list[GeopoliticalEvent]:
        """Scan news sources for geopolitical events."""
        events = []

        for source_name, url in GEO_SOURCES.items():
            try:
                response = await self.client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code != 200:
                    continue

                from xml.etree import ElementTree
                try:
                    root = ElementTree.fromstring(response.content)
                except:
                    continue

                for item in root.findall(".//item")[:15]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    desc = item.find("description").text if item.find("description") is not None else ""

                    text = f"{title} {desc}"
                    region_id, config = self._classify_region(text)

                    if region_id:
                        tension_change = self._determine_tension_change(text)

                        events.append(GeopoliticalEvent(
                            event_id=f"geo_{region_id}_{datetime.now().strftime('%Y%m%d%H%M')}",
                            region=region_id,
                            title=title,
                            source=source_name,
                            date=datetime.now(),
                            summary=desc[:500] if desc else "",
                            tension_change=tension_change,
                            symbols_bullish=config.get("symbols_bullish", []),
                            symbols_bearish=config.get("symbols_bearish", []),
                            url=link,
                        ))

            except Exception as e:
                logger.warning(f"Error scanning {source_name}: {e}")

        return events

    def get_region_statuses(self) -> list[RegionStatus]:
        """Get current status of all tracked regions."""
        statuses = []
        for region_id, config in REGIONS.items():
            statuses.append(RegionStatus(
                region_id=region_id,
                name=config["name"],
                tension_level=config.get("tension_level", "unknown"),
                thesis_status=config.get("thesis", ""),
                symbols_bullish=config.get("symbols_bullish", []),
                symbols_bearish=config.get("symbols_bearish", []),
            ))
        return statuses

    async def collect_all(self) -> dict:
        """Collect all geopolitical events."""
        events = await self.scan_news_for_events()

        # Save events
        cache_file = self.cache_dir / f"events_{datetime.now().strftime('%Y%m%d')}.json"

        existing = []
        if cache_file.exists():
            with open(cache_file) as f:
                existing = json.load(f)

        existing_titles = {e.get("title") for e in existing}
        new_events = [e.to_dict() for e in events if e.title not in existing_titles]

        all_data = new_events + existing

        with open(cache_file, "w") as f:
            json.dump(all_data, f, indent=2)

        # Save region statuses
        status_file = self.cache_dir / "region_status.json"
        with open(status_file, "w") as f:
            json.dump({
                "updated_at": datetime.now().isoformat(),
                "regions": [s.to_dict() for s in self.get_region_statuses()],
            }, f, indent=2)

        # Count events by region
        by_region = {}
        for event in events:
            by_region[event.region] = by_region.get(event.region, 0) + 1

        return {
            "total_events": len(events),
            "new_events": len(new_events),
            "by_region": by_region,
            "escalations": len([e for e in events if e.tension_change == "escalation"]),
        }

    def get_events_for_region(self, region_id: str, days: int = 7) -> list[dict]:
        """Get recent events for a specific region."""
        cache_file = self.cache_dir / f"events_{datetime.now().strftime('%Y%m%d')}.json"
        if not cache_file.exists():
            return []

        with open(cache_file) as f:
            events = json.load(f)

        return [e for e in events if e.get("region") == region_id]

    def get_affected_symbols(self, tension_type: str = "bullish") -> list[str]:
        """Get all symbols affected by current geopolitical situation."""
        symbols = set()
        for config in REGIONS.values():
            if config.get("tension_level") in ["elevated", "high", "crisis"]:
                if tension_type == "bullish":
                    symbols.update(config.get("symbols_bullish", []))
                else:
                    symbols.update(config.get("symbols_bearish", []))
        return list(symbols)


async def main():
    """Test geopolitical monitor."""
    monitor = GeopoliticalMonitor()
    try:
        result = await monitor.collect_all()
        print(f"Collection result: {json.dumps(result, indent=2)}")

        print("\nRegion statuses:")
        for status in monitor.get_region_statuses():
            print(f"  {status.name}: {status.tension_level}")
            print(f"    Bullish: {', '.join(status.symbols_bullish[:5])}")

        print(f"\nSymbols to watch (bullish): {monitor.get_affected_symbols('bullish')}")

    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
