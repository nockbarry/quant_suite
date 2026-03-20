#!/usr/bin/env python3
"""OFAC/Treasury press release monitor.

Checks for sanctions changes, general licenses, and enforcement actions
relevant to portfolio theses (Iran, Venezuela, Russia, China).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from src.core.paths import paths

logger = logging.getLogger(__name__)

# RSS sources
OFAC_RSS_URL = "https://home.treasury.gov/system/files/126/ofac_rss.xml"
TREASURY_PRESS_URL = "https://home.treasury.gov/system/files/press-releases/rss.xml"

# Country-to-thesis mapping
COUNTRY_THESIS_MAP = {
    "iran": {
        "theses": ["Iran War Energy Supercycle"],
        "symbols": ["USO", "XLE", "BNO", "XOM", "CVX", "SLB", "HAL"],
    },
    "venezuela": {
        "theses": ["Venezuela Energy Recovery"],
        "symbols": ["SLB", "HAL", "PBR", "FRO", "STNG", "DHT"],
    },
    "russia": {
        "theses": ["Dual Chokepoint Shipping", "Fertilizer Agflation"],
        "symbols": ["FRO", "STNG", "DHT", "CF", "MOS", "NTR"],
    },
    "china": {
        "theses": ["Rare Earth Independence", "Copper AI Squeeze"],
        "symbols": ["MP", "FSLR", "FCX", "SCCO"],
    },
    "cuba": {
        "theses": [],
        "symbols": [],
    },
    "north korea": {
        "theses": [],
        "symbols": ["RTX", "LMT", "NOC"],
    },
    "myanmar": {
        "theses": [],
        "symbols": [],
    },
}

# Keywords for classifying action type
ACTION_KEYWORDS = {
    "general_license": [
        "general license", "gl-", "license no.", "authoriz",
        "license amendment", "specific license",
    ],
    "sanctions_addition": [
        "designat", "added to", "specially designated",
        "blocked", "sdnlist", "sanctions list",
    ],
    "sanctions_removal": [
        "delisted", "removed from", "unblocked", "lifted",
        "waiver", "exemption", "suspended sanctions",
    ],
    "enforcement": [
        "penalty", "fine", "settlement", "violation",
        "enforcement", "civil monetary", "forfeiture",
    ],
}


@dataclass
class TreasuryAlert:
    """A single OFAC/Treasury alert parsed from RSS."""

    title: str
    source: str  # "ofac" or "treasury_press"
    published: str
    url: str
    summary: str = ""
    matched_countries: list[str] = field(default_factory=list)
    matched_theses: list[str] = field(default_factory=list)
    matched_symbols: list[str] = field(default_factory=list)
    action_type: str = "press_release"
    importance: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "published": self.published,
            "url": self.url,
            "summary": self.summary,
            "matched_countries": self.matched_countries,
            "matched_theses": self.matched_theses,
            "matched_symbols": self.matched_symbols,
            "action_type": self.action_type,
            "importance": self.importance,
        }


class TreasuryMonitor:
    """Monitor OFAC RSS and Treasury press releases for sanctions changes.

    Matches alerts to portfolio-relevant countries and theses.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Athena Research athena-research@protonmail.com",
                    "Accept": "application/xml, application/rss+xml, text/xml",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def collect(self) -> list[TreasuryAlert]:
        """Collect alerts from all Treasury/OFAC sources.

        Returns:
            Combined list of TreasuryAlert from OFAC + press releases,
            sorted by relevance (matched items first).
        """
        ofac_alerts = await self._fetch_ofac_rss()
        press_alerts = await self._fetch_treasury_press()

        all_alerts = ofac_alerts + press_alerts

        # Sort: matched alerts first (by number of matches), then by date
        all_alerts.sort(
            key=lambda a: (-len(a.matched_theses), -len(a.matched_countries)),
        )

        self._save(all_alerts)
        return all_alerts

    async def _fetch_ofac_rss(self) -> list[TreasuryAlert]:
        """Fetch and parse the OFAC RSS feed."""
        client = await self._get_client()
        alerts: list[TreasuryAlert] = []

        try:
            resp = await client.get(OFAC_RSS_URL)
            if resp.status_code != 200:
                logger.warning(f"OFAC RSS returned {resp.status_code}")
                return []

            alerts = self._parse_rss(resp.content, source="ofac")
            logger.info(f"OFAC RSS: {len(alerts)} items parsed")

        except Exception as e:
            logger.error(f"OFAC RSS fetch failed: {e}")

        return alerts

    async def _fetch_treasury_press(self) -> list[TreasuryAlert]:
        """Fetch and parse Treasury press releases RSS."""
        client = await self._get_client()
        alerts: list[TreasuryAlert] = []

        try:
            resp = await client.get(TREASURY_PRESS_URL)
            if resp.status_code != 200:
                logger.warning(f"Treasury press RSS returned {resp.status_code}")
                return []

            alerts = self._parse_rss(resp.content, source="treasury_press")
            logger.info(f"Treasury press RSS: {len(alerts)} items parsed")

        except Exception as e:
            logger.error(f"Treasury press RSS fetch failed: {e}")

        return alerts

    def _parse_rss(self, content: bytes, source: str) -> list[TreasuryAlert]:
        """Parse RSS/Atom XML content into TreasuryAlert list."""
        alerts: list[TreasuryAlert] = []

        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as e:
            logger.error(f"XML parse error for {source}: {e}")
            return []

        # Handle RSS 2.0 format (<item>) and Atom format (<entry>)
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items:
            # RSS 2.0 tags
            title_el = item.find("title")
            if title_el is None:
                title_el = item.find("{http://www.w3.org/2005/Atom}title")

            link_el = item.find("link")
            if link_el is None:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")

            pub_el = item.find("pubDate")
            if pub_el is None:
                pub_el = item.find("{http://www.w3.org/2005/Atom}published")
            if pub_el is None:
                pub_el = item.find("{http://www.w3.org/2005/Atom}updated")

            desc_el = item.find("description")
            if desc_el is None:
                desc_el = item.find("{http://www.w3.org/2005/Atom}summary")

            if title_el is None:
                continue

            title = title_el.text or ""
            url = ""
            if link_el is not None:
                url = link_el.get("href") or link_el.text or ""

            published = ""
            if pub_el is not None and pub_el.text:
                try:
                    from email.utils import parsedate_to_datetime

                    dt = parsedate_to_datetime(pub_el.text)
                    published = dt.isoformat()
                except Exception:
                    published = pub_el.text

            summary = ""
            if desc_el is not None and desc_el.text:
                summary = desc_el.text[:500]

            # Match to portfolio
            countries, theses, symbols = self._match_to_portfolio(title, summary)
            action_type = self._classify_action(title, summary)
            importance = self._assess_importance(countries, theses, action_type)

            alerts.append(
                TreasuryAlert(
                    title=title,
                    source=source,
                    published=published,
                    url=url,
                    summary=summary,
                    matched_countries=countries,
                    matched_theses=theses,
                    matched_symbols=symbols,
                    action_type=action_type,
                    importance=importance,
                )
            )

        return alerts

    def _match_to_portfolio(
        self, title: str, summary: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Match alert text to portfolio-relevant countries, theses, symbols."""
        text = f"{title} {summary}".lower()
        countries: list[str] = []
        theses: set[str] = set()
        symbols: set[str] = set()

        for country, mapping in COUNTRY_THESIS_MAP.items():
            if country in text:
                countries.append(country)
                theses.update(mapping["theses"])
                symbols.update(mapping["symbols"])

        return countries, sorted(theses), sorted(symbols)

    def _classify_action(self, title: str, summary: str) -> str:
        """Classify the type of Treasury/OFAC action."""
        text = f"{title} {summary}".lower()

        for action_type, keywords in ACTION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return action_type

        return "press_release"

    def _assess_importance(
        self,
        countries: list[str],
        theses: list[str],
        action_type: str,
    ) -> str:
        """Assess importance of the alert based on portfolio relevance."""
        if not countries:
            return "low"

        # High-value countries for portfolio
        critical_countries = {"iran", "venezuela"}
        has_critical = any(c in critical_countries for c in countries)

        if has_critical and action_type in (
            "general_license",
            "sanctions_removal",
            "sanctions_addition",
        ):
            return "critical"

        if theses and action_type != "press_release":
            return "high"

        if countries:
            return "medium"

        return "low"

    def _save(self, alerts: list[TreasuryAlert]) -> None:
        """Save alerts to disk."""
        out_path = paths.live / "treasury_alerts.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        matched = [a for a in alerts if a.matched_countries]

        try:
            with open(out_path, "w") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "total_alerts": len(alerts),
                        "portfolio_relevant": len(matched),
                        "alerts": [a.to_dict() for a in alerts],
                    },
                    f,
                    indent=2,
                    default=str,
                )
            logger.info(
                f"Saved Treasury alerts: {len(alerts)} total, "
                f"{len(matched)} portfolio-relevant -> {out_path}"
            )
        except Exception as e:
            logger.error(f"Failed to save Treasury alerts: {e}")

    @staticmethod
    def load_latest() -> dict | None:
        """Load the latest saved Treasury alerts."""
        path = paths.live / "treasury_alerts.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load Treasury alerts: {e}")
            return None


async def main():
    """Test Treasury monitor."""
    monitor = TreasuryMonitor()
    try:
        alerts = await monitor.collect()
        print(f"Collected {len(alerts)} alerts")
        for a in alerts[:5]:
            print(f"  [{a.importance}] {a.action_type}: {a.title[:80]}")
            if a.matched_countries:
                print(f"    Countries: {a.matched_countries}, Theses: {a.matched_theses}")
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
