#!/usr/bin/env python3
"""Legal and Regulatory Tracker - SCOTUS, SEC, FTC, DOJ tracking.

Monitors court cases, regulatory decisions, and enforcement actions
that can move markets.
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

# Key cases and their market impacts
TRACKED_CASES = {
    "ieepa_tariffs": {
        "name": "Learning Resources v. Trump (IEEPA Tariffs)",
        "docket": "24-1287",
        "status": "pending_decision",
        "expected_decision": "2026-01-31",
        "impact": "critical",
        "symbols_affected": ["SPY", "QQQ", "EEM", "FXI", "XLI"],
        "if_upheld": "Tariffs remain, import costs stay high, inflation pressure",
        "if_struck": "Tariffs voided, potential refunds, market rally likely",
        "keywords": ["ieepa", "tariff", "learning resources", "customs"],
    },
    "ftc_noncompete": {
        "name": "FTC Non-Compete Ban",
        "status": "enjoined",
        "impact": "high",
        "symbols_affected": ["XLK", "XLF"],
        "keywords": ["noncompete", "non-compete", "ftc", "labor mobility"],
    },
}

# Regulatory bodies to track
REGULATORY_FEEDS = {
    "sec": {
        "rss": "https://www.sec.gov/news/pressreleases.rss",
        "keywords": ["enforcement", "settlement", "fraud", "insider trading"],
        "symbols": [],  # Dynamic based on content
    },
    "doj_antitrust": {
        "rss": "https://www.justice.gov/atr/press-releases/feed",
        "keywords": ["antitrust", "merger", "monopoly", "competition"],
        "symbols": [],
    },
    "ftc": {
        "rss": "https://www.ftc.gov/news-events/news/press-releases/feed",
        "keywords": ["merger", "acquisition", "deceptive", "unfair"],
        "symbols": [],
    },
    "fed": {
        "rss": "https://www.federalreserve.gov/feeds/press_all.xml",
        "keywords": ["rate", "fomc", "monetary", "inflation", "employment"],
        "symbols": ["SPY", "TLT", "XLF"],
    },
}


@dataclass
class LegalEvent:
    """A legal/regulatory event."""
    event_id: str
    event_type: str  # ruling, filing, enforcement, announcement
    title: str
    source: str
    date: datetime
    summary: str = ""
    impact: str = "medium"
    symbols_affected: list[str] = field(default_factory=list)
    case_reference: str = ""
    url: str = ""

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "title": self.title,
            "source": self.source,
            "date": self.date.isoformat(),
            "summary": self.summary,
            "impact": self.impact,
            "symbols_affected": self.symbols_affected,
            "case_reference": self.case_reference,
            "url": self.url,
        }


@dataclass
class CaseStatus:
    """Status of a tracked legal case."""
    case_id: str
    name: str
    status: str  # pending_decision, decided, appealed, remanded
    last_update: datetime
    next_event: Optional[str] = None
    next_event_date: Optional[datetime] = None
    outcome: Optional[str] = None
    market_impact: str = ""

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "name": self.name,
            "status": self.status,
            "last_update": self.last_update.isoformat(),
            "next_event": self.next_event,
            "next_event_date": self.next_event_date.isoformat() if self.next_event_date else None,
            "outcome": self.outcome,
            "market_impact": self.market_impact,
        }


class LegalTracker:
    """Track legal and regulatory events affecting markets."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live / "legal"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    async def check_scotus_decisions(self) -> list[LegalEvent]:
        """Check SCOTUSblog for new decisions."""
        events = []
        try:
            # Fetch SCOTUSblog RSS
            response = await self.client.get(
                "https://www.scotusblog.com/feed/",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code != 200:
                return events

            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.content)

            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""

                # Check if relates to tracked cases
                text = f"{title} {desc}".lower()
                for case_id, case_info in TRACKED_CASES.items():
                    if any(kw in text for kw in case_info.get("keywords", [])):
                        events.append(LegalEvent(
                            event_id=f"scotus_{case_id}_{datetime.now().strftime('%Y%m%d')}",
                            event_type="ruling" if "decision" in text or "ruling" in text else "update",
                            title=title,
                            source="scotusblog",
                            date=datetime.now(),
                            summary=desc[:500] if desc else "",
                            impact=case_info.get("impact", "high"),
                            symbols_affected=case_info.get("symbols_affected", []),
                            case_reference=case_info.get("docket", ""),
                            url=link,
                        ))

        except Exception as e:
            logger.error(f"Error checking SCOTUS: {e}")

        return events

    async def check_regulatory_feeds(self) -> list[LegalEvent]:
        """Check regulatory agency RSS feeds."""
        events = []

        for agency, config in REGULATORY_FEEDS.items():
            try:
                response = await self.client.get(
                    config["rss"],
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if response.status_code != 200:
                    continue

                from xml.etree import ElementTree
                root = ElementTree.fromstring(response.content)

                for item in root.findall(".//item")[:10]:  # Last 10 items
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    desc = item.find("description").text if item.find("description") is not None else ""

                    text = f"{title} {desc}".lower()

                    # Check for relevant keywords
                    if any(kw in text for kw in config.get("keywords", [])):
                        # Determine impact
                        impact = "medium"
                        if any(w in text for w in ["major", "significant", "billion", "fraud"]):
                            impact = "high"
                        if any(w in text for w in ["emergency", "immediate", "halt"]):
                            impact = "critical"

                        events.append(LegalEvent(
                            event_id=f"{agency}_{datetime.now().strftime('%Y%m%d%H%M')}",
                            event_type="enforcement" if "enforcement" in text else "announcement",
                            title=title,
                            source=agency,
                            date=datetime.now(),
                            summary=desc[:500] if desc else "",
                            impact=impact,
                            symbols_affected=config.get("symbols", []),
                            url=link,
                        ))

            except Exception as e:
                logger.warning(f"Error checking {agency}: {e}")

        return events

    def get_tracked_cases(self) -> list[CaseStatus]:
        """Get status of all tracked cases."""
        statuses = []
        for case_id, case_info in TRACKED_CASES.items():
            statuses.append(CaseStatus(
                case_id=case_id,
                name=case_info["name"],
                status=case_info.get("status", "unknown"),
                last_update=datetime.now(),
                next_event="Decision expected",
                next_event_date=datetime.strptime(case_info["expected_decision"], "%Y-%m-%d") if "expected_decision" in case_info else None,
                market_impact=f"If upheld: {case_info.get('if_upheld', 'TBD')} | If struck: {case_info.get('if_struck', 'TBD')}",
            ))
        return statuses

    async def collect_all(self) -> dict:
        """Collect all legal/regulatory events."""
        scotus_events = await self.check_scotus_decisions()
        regulatory_events = await self.check_regulatory_feeds()

        all_events = scotus_events + regulatory_events

        # Save to cache
        cache_file = self.cache_dir / f"legal_{datetime.now().strftime('%Y%m%d')}.json"

        existing = []
        if cache_file.exists():
            with open(cache_file) as f:
                existing = json.load(f)

        # Add new events
        existing_ids = {e.get("event_id") for e in existing}
        new_events = [e.to_dict() for e in all_events if e.event_id not in existing_ids]

        all_data = new_events + existing

        with open(cache_file, "w") as f:
            json.dump(all_data, f, indent=2)

        # Save case statuses
        cases_file = self.cache_dir / "tracked_cases.json"
        with open(cases_file, "w") as f:
            json.dump({
                "updated_at": datetime.now().isoformat(),
                "cases": [c.to_dict() for c in self.get_tracked_cases()],
            }, f, indent=2)

        return {
            "scotus_events": len(scotus_events),
            "regulatory_events": len(regulatory_events),
            "new_events": len(new_events),
            "tracked_cases": len(TRACKED_CASES),
        }

    def get_pending_decisions(self) -> list[dict]:
        """Get cases with pending decisions."""
        pending = []
        for case_id, case_info in TRACKED_CASES.items():
            if case_info.get("status") == "pending_decision":
                pending.append({
                    "case_id": case_id,
                    "name": case_info["name"],
                    "expected": case_info.get("expected_decision"),
                    "impact": case_info.get("impact"),
                    "symbols": case_info.get("symbols_affected", []),
                })
        return pending

    def search_for_keywords(self, keywords: list[str]) -> list[dict]:
        """Search recent legal events for keywords."""
        cache_file = self.cache_dir / f"legal_{datetime.now().strftime('%Y%m%d')}.json"
        if not cache_file.exists():
            return []

        with open(cache_file) as f:
            events = json.load(f)

        matches = []
        for event in events:
            text = f"{event.get('title', '')} {event.get('summary', '')}".lower()
            if any(kw.lower() in text for kw in keywords):
                matches.append(event)

        return matches


async def main():
    """Test legal tracker."""
    tracker = LegalTracker()
    try:
        result = await tracker.collect_all()
        print(f"Collection result: {json.dumps(result, indent=2)}")

        print("\nPending decisions:")
        for case in tracker.get_pending_decisions():
            print(f"  {case['name']}: expected {case['expected']}, impact={case['impact']}")

    finally:
        await tracker.close()


if __name__ == "__main__":
    asyncio.run(main())
