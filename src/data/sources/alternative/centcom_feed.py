"""US CENTCOM Press Releases.

RSS feed from US Central Command — covers Iran war military operations.
Would have caught the Marines deployment and Kharg Island discussions.

Source: https://www.centcom.mil/MEDIA/PRESS-RELEASES/
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import httpx

from src.core.paths import paths

logger = logging.getLogger(__name__)


# CENTCOM and military RSS feeds
MILITARY_FEEDS = {
    "centcom": "https://www.centcom.mil/MEDIA/PRESS-RELEASES/RSS/",
    "dod_news": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945",
    "dod_releases": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=9&Site=945",
}

# Urgency keywords — if matched, flag as urgent
URGENT_KEYWORDS = [
    "strike", "strikes", "operation", "casualties", "deployment",
    "hormuz", "strait", "attack", "attacked", "missile",
    "airstrike", "air strike", "naval", "fleet", "carrier",
    "iran", "iranian", "irgc", "houthi", "hezbollah",
    "killed", "destroyed", "intercepted", "shot down",
    "escalation", "retaliation", "retaliatory",
    "nuclear", "enrichment", "centrifuge",
]

# Iran/war thesis keywords for matching
WAR_KEYWORDS = [
    "iran", "iranian", "iraq", "syria", "yemen", "houthi",
    "persian gulf", "gulf of oman", "red sea", "hormuz",
    "centcom", "military", "navy", "marine", "forces",
    "sanctions", "embargo", "blockade",
    "oil", "crude", "tanker", "shipping",
    "kharg", "bandar", "basra", "fujairah",
]

# Thesis matching
THESIS_KEYWORDS = {
    "iran_war_energy": [
        "iran", "hormuz", "tanker", "oil", "crude", "persian gulf",
        "houthi", "red sea", "strait", "blockade", "naval",
    ],
    "defense_spending": [
        "deployment", "military", "forces", "operation", "mission",
        "nato", "coalition", "defense", "troops",
    ],
    "dual_chokepoint": [
        "red sea", "hormuz", "houthi", "shipping", "tanker",
        "bab al-mandab", "suez",
    ],
}


@dataclass
class CentcomAlert:
    """A CENTCOM / DoD press release."""

    title: str
    published: str
    source: str
    url: str
    is_urgent: bool
    urgent_keywords: list[str] = field(default_factory=list)
    matched_thesis: list[str] = field(default_factory=list)
    relevance_score: float = 0.0


@dataclass
class CentcomSnapshot:
    """Collection of recent CENTCOM alerts."""

    timestamp: str
    alerts: list[dict]  # List of CentcomAlert as dicts
    total_found: int
    urgent_count: int
    thesis_matched: int
    feeds_checked: int
    feeds_succeeded: int
    data_quality: str  # "live", "partial", "stale"


class CentcomCollector:
    """Collect CENTCOM military operations press releases via RSS.

    Monitors US Central Command for military operation announcements,
    deployments, strikes, and escalation signals relevant to the Iran
    war thesis and defense spending thesis.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "centcom_alerts.json"

    async def collect(self) -> CentcomSnapshot:
        """Collect CENTCOM and DoD press releases."""
        all_alerts = []
        feeds_succeeded = 0

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for feed_name, feed_url in MILITARY_FEEDS.items():
                try:
                    alerts = await self._fetch_feed(client, feed_name, feed_url)
                    all_alerts.extend(alerts)
                    feeds_succeeded += 1
                    logger.info(f"CENTCOM {feed_name}: {len(alerts)} items")
                except Exception as e:
                    logger.warning(f"CENTCOM {feed_name} failed: {e}")

        # Sort by urgency then relevance
        all_alerts.sort(
            key=lambda a: (-int(a.is_urgent), -a.relevance_score),
        )

        # Keep top 50
        all_alerts = all_alerts[:50]

        urgent_count = sum(1 for a in all_alerts if a.is_urgent)
        thesis_matched = sum(1 for a in all_alerts if a.matched_thesis)

        if feeds_succeeded == 0:
            quality = "stale"
        elif feeds_succeeded < len(MILITARY_FEEDS) // 2:
            quality = "partial"
        else:
            quality = "live"

        snapshot = CentcomSnapshot(
            timestamp=datetime.now().isoformat(),
            alerts=[asdict(a) for a in all_alerts],
            total_found=len(all_alerts),
            urgent_count=urgent_count,
            thesis_matched=thesis_matched,
            feeds_checked=len(MILITARY_FEEDS),
            feeds_succeeded=feeds_succeeded,
            data_quality=quality,
        )

        self._save(snapshot)
        return snapshot

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed_name: str, url: str
    ) -> list[CentcomAlert]:
        """Fetch and parse a single RSS feed."""
        response = await client.get(url, headers={"User-Agent": "AthenaTrader/1.0"})
        response.raise_for_status()

        alerts = []
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError as e:
            logger.warning(f"XML parse error for {feed_name}: {e}")
            return []

        items = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

        for item in items:
            title = self._get_text(item, "title") or self._get_text(
                item, "{http://www.w3.org/2005/Atom}title"
            )
            link = self._get_text(item, "link") or ""
            if not link:
                link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                if link_elem is not None:
                    link = link_elem.get("href", "")

            pub_date = (
                self._get_text(item, "pubDate")
                or self._get_text(item, "{http://www.w3.org/2005/Atom}updated")
                or ""
            )

            if not title:
                continue

            title_lower = title.lower()

            # Check urgency
            matched_urgent = [kw for kw in URGENT_KEYWORDS if kw in title_lower]
            is_urgent = len(matched_urgent) > 0

            # Relevance scoring
            war_matches = sum(1 for kw in WAR_KEYWORDS if kw in title_lower)
            relevance_score = min(war_matches / 3.0, 1.0)

            # Thesis matching
            matched_theses = []
            for thesis_id, keywords in THESIS_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords):
                    matched_theses.append(thesis_id)

            alerts.append(CentcomAlert(
                title=title,
                published=pub_date,
                source=feed_name,
                url=link,
                is_urgent=is_urgent,
                urgent_keywords=matched_urgent[:5],
                matched_thesis=matched_theses,
                relevance_score=round(relevance_score, 2),
            ))

        return alerts

    @staticmethod
    def _get_text(element, tag: str) -> Optional[str]:
        """Safely extract text from an XML element."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    def _save(self, snapshot: CentcomSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved CENTCOM alerts: {snapshot.total_found} total, "
            f"{snapshot.urgent_count} urgent, {snapshot.thesis_matched} thesis-matched"
        )

    def load_latest(self) -> Optional[dict]:
        """Load most recent cached snapshot."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return None
        return None
