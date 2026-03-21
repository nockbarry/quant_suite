"""USDA Crop Reports and Planting Progress.

Critical for Fertilizer Agflation thesis — planting progress directly
affects fertilizer demand timing. Free RSS feeds.

Sources:
- USDA NASS: https://www.nass.usda.gov/
- USDA ERS: https://www.ers.usda.gov/
- USDA RSS feeds for crop reports, planting progress, grain stocks
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


# Agricultural RSS feeds (USDA direct feeds are mostly offline as of 2026;
# using industry ag publications that cover USDA reports extensively)
USDA_FEEDS = {
    "farm_progress": "https://www.farmprogress.com/rss.xml",
    "croplife": "https://www.croplife.com/feed/",
    "feedstuffs": "https://www.feedstuffs.com/rss.xml",
}

# Keywords for crop-related report filtering
CROP_KEYWORDS = [
    "planting", "crop", "grain", "corn", "soybean", "wheat", "cotton",
    "harvest", "acreage", "yield", "production", "condition",
    "stocks", "supply", "demand", "wasde", "prospective",
    "fertilizer", "nitrogen", "potash", "phosphate", "urea",
    "drought", "flood", "weather", "moisture",
]

# Categories for classification
CATEGORY_PATTERNS = {
    "planting": ["planting", "acreage", "prospective plantings", "planted"],
    "conditions": ["crop condition", "crop progress", "weekly crop", "drought"],
    "stocks": ["grain stocks", "quarterly stocks", "ending stocks"],
    "prices": ["prices received", "cost of production", "fertilizer price"],
    "production": ["production", "yield", "harvest", "wasde", "supply demand"],
    "trade": ["export", "import", "trade", "shipment"],
}

# Thesis keywords for matching
THESIS_KEYWORDS = {
    "fertilizer_agflation": [
        "fertilizer", "nitrogen", "potash", "urea", "ammonia",
        "planting", "crop", "corn", "soybean", "wheat",
        "acreage", "supply", "demand", "price",
    ],
    "iran_war_energy": [
        "fertilizer", "natural gas", "ammonia", "urea",
        "import", "supply disruption",
    ],
}


@dataclass
class USDAReport:
    """A USDA report relevant to agricultural markets."""

    title: str
    published: str
    source: str
    url: str
    category: str  # planting, conditions, stocks, prices, production, trade, other
    matched_thesis: list[str] = field(default_factory=list)
    relevance_score: float = 0.0  # 0-1 based on keyword density


@dataclass
class USDASnapshot:
    """Collection of recent USDA reports."""

    timestamp: str
    reports: list[dict]  # List of USDAReport as dicts
    total_found: int
    crop_relevant: int
    thesis_matched: int
    feeds_checked: int
    feeds_succeeded: int
    data_quality: str  # "live", "partial", "stale"


class USDACollector:
    """Collect USDA crop reports via RSS feeds.

    Monitors planting progress, crop conditions, grain stocks, and
    fertilizer-related reports. Matches to active theses (especially
    Fertilizer Agflation).
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "usda_reports.json"

    async def collect(self) -> USDASnapshot:
        """Collect USDA reports from RSS feeds."""
        all_reports = []
        feeds_succeeded = 0

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for feed_name, feed_url in USDA_FEEDS.items():
                try:
                    reports = await self._fetch_feed(client, feed_name, feed_url)
                    all_reports.extend(reports)
                    feeds_succeeded += 1
                    logger.info(f"USDA {feed_name}: {len(reports)} items")
                except Exception as e:
                    logger.warning(f"USDA {feed_name} failed: {e}")

        # Filter to crop-relevant
        crop_reports = [r for r in all_reports if r.relevance_score > 0]

        # Sort by relevance then date
        crop_reports.sort(key=lambda r: (-r.relevance_score, r.published), reverse=False)

        # Keep top 50
        crop_reports = crop_reports[:50]

        # Determine data quality
        if feeds_succeeded == 0:
            quality = "stale"
        elif feeds_succeeded < len(USDA_FEEDS) // 2:
            quality = "partial"
        else:
            quality = "live"

        thesis_matched = sum(1 for r in crop_reports if r.matched_thesis)

        snapshot = USDASnapshot(
            timestamp=datetime.now().isoformat(),
            reports=[asdict(r) for r in crop_reports],
            total_found=len(all_reports),
            crop_relevant=len(crop_reports),
            thesis_matched=thesis_matched,
            feeds_checked=len(USDA_FEEDS),
            feeds_succeeded=feeds_succeeded,
            data_quality=quality,
        )

        self._save(snapshot)
        return snapshot

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed_name: str, url: str
    ) -> list[USDAReport]:
        """Fetch and parse a single RSS feed."""
        response = await client.get(url, headers={"User-Agent": "AthenaTrader/1.0"})
        response.raise_for_status()

        reports = []
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError as e:
            logger.warning(f"XML parse error for {feed_name}: {e}")
            return []

        # Handle both RSS and Atom formats
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

            # Score relevance
            title_lower = title.lower()
            relevance = sum(1 for kw in CROP_KEYWORDS if kw in title_lower)
            relevance_score = min(relevance / 3.0, 1.0)  # Normalize to 0-1

            # Classify category
            category = "other"
            for cat_name, patterns in CATEGORY_PATTERNS.items():
                if any(p in title_lower for p in patterns):
                    category = cat_name
                    break

            # Match to theses
            matched_theses = []
            for thesis_id, keywords in THESIS_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords):
                    matched_theses.append(thesis_id)

            reports.append(USDAReport(
                title=title,
                published=pub_date,
                source=feed_name,
                url=link,
                category=category,
                matched_thesis=matched_theses,
                relevance_score=round(relevance_score, 2),
            ))

        return reports

    @staticmethod
    def _get_text(element, tag: str) -> Optional[str]:
        """Safely extract text from an XML element."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    def _save(self, snapshot: USDASnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved USDA reports: {snapshot.crop_relevant} crop-relevant "
            f"({snapshot.thesis_matched} thesis-matched) from {snapshot.feeds_succeeded} feeds"
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
