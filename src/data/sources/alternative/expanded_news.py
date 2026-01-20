#!/usr/bin/env python3
"""Expanded News Sources - 15+ RSS feeds for comprehensive coverage.

Covers: Major outlets, sector-specific, Fed/policy, international, legal/regulatory.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

# Comprehensive RSS feed collection
RSS_FEEDS = {
    # Major Financial News
    "yahoo_finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,AAPL,MSFT,GOOGL,AMZN,META,NVDA&region=US&lang=en-US",
    "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
    "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "cnbc_top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",

    # Sector-Specific
    "oilprice": "https://oilprice.com/rss/main",
    "mining_com": "https://www.mining.com/feed/",
    "fierce_pharma": "https://www.fiercepharma.com/rss/xml",
    "techcrunch": "https://techcrunch.com/feed/",
    "the_block_crypto": "https://www.theblock.co/rss.xml",

    # Fed/Policy/Government
    "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",
    "treasury_press": "https://home.treasury.gov/system/files/136/press-rss.xml",
    "sec_news": "https://www.sec.gov/news/pressreleases.rss",

    # Legal/Regulatory
    "scotusblog": "https://www.scotusblog.com/feed/",
    "law360_securities": "https://www.law360.com/rss/securities",

    # International
    "ft_markets": "https://www.ft.com/markets?format=rss",
    "reuters_world": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
    "scmp_economy": "https://www.scmp.com/rss/91/feed",  # South China Morning Post
}

# Keywords for filtering/categorization
CATEGORY_KEYWORDS = {
    "fed_policy": ["fed", "fomc", "interest rate", "powell", "monetary policy", "rate cut", "rate hike"],
    "tariffs": ["tariff", "ieepa", "trade war", "customs", "import duty", "trade policy"],
    "geopolitical": ["greenland", "denmark", "venezuela", "sanctions", "china", "taiwan", "russia", "ukraine"],
    "earnings": ["earnings", "revenue", "eps", "beat", "miss", "guidance", "outlook"],
    "macro": ["gdp", "inflation", "cpi", "ppi", "jobs", "unemployment", "payrolls", "retail sales"],
    "sector_energy": ["oil", "crude", "natural gas", "opec", "drilling", "refinery"],
    "sector_tech": ["ai", "artificial intelligence", "semiconductor", "chip", "cloud", "data center"],
    "sector_defense": ["defense", "military", "pentagon", "nato", "weapons", "contractor"],
    "legal": ["supreme court", "scotus", "ruling", "lawsuit", "antitrust", "regulation"],
}

# Symbols affected by keywords
KEYWORD_SYMBOLS = {
    "fed_policy": ["SPY", "QQQ", "TLT", "XLF"],
    "tariffs": ["SPY", "EEM", "FXI", "XLI"],
    "greenland": ["RTX", "LMT", "NOC", "GD"],
    "venezuela": ["SLB", "HAL", "FRO", "STNG", "PBR"],
    "oil": ["XLE", "USO", "OIH", "SLB", "XOM", "CVX"],
    "semiconductor": ["SMH", "NVDA", "AMD", "TSM", "INTC"],
    "defense": ["ITA", "RTX", "LMT", "NOC", "GD"],
}


@dataclass
class NewsItem:
    """Enhanced news item with categorization."""
    title: str
    source: str
    url: str
    published: datetime
    summary: str = ""
    categories: list[str] = field(default_factory=list)
    symbols_affected: list[str] = field(default_factory=list)
    importance: str = "medium"  # low, medium, high, critical
    sentiment: float = 0.0  # -1 to 1

    def to_dict(self):
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published": self.published.isoformat(),
            "summary": self.summary,
            "categories": self.categories,
            "symbols_affected": self.symbols_affected,
            "importance": self.importance,
            "sentiment": self.sentiment,
            "hash": self.hash,
        }

    @property
    def hash(self) -> str:
        return hashlib.md5(f"{self.title}{self.url}".encode()).hexdigest()[:12]


class ExpandedNewsCollector:
    """Collect news from 15+ RSS sources with categorization."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path.home() / "quant_results" / "live" / "news"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    async def fetch_feed(self, name: str, url: str) -> list[NewsItem]:
        """Fetch and parse a single RSS feed."""
        items = []
        try:
            response = await self.client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
            })
            if response.status_code != 200:
                logger.warning(f"Feed {name} returned {response.status_code}")
                return []

            root = ElementTree.fromstring(response.content)

            # Handle both RSS and Atom formats
            for item in root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                title_elem = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                link_elem = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
                pub_elem = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")
                desc_elem = item.find("description") or item.find("{http://www.w3.org/2005/Atom}summary")

                if title_elem is None:
                    continue

                title = title_elem.text or ""
                url = link_elem.get("href") if link_elem is not None and link_elem.text is None else (link_elem.text if link_elem is not None else "")
                summary = desc_elem.text[:500] if desc_elem is not None and desc_elem.text else ""

                # Parse date
                pub_date = datetime.now()
                if pub_elem is not None and pub_elem.text:
                    try:
                        from email.utils import parsedate_to_datetime
                        pub_date = parsedate_to_datetime(pub_elem.text)
                    except:
                        pass

                # Categorize
                categories, symbols, importance = self._categorize(title, summary)

                items.append(NewsItem(
                    title=title,
                    source=name,
                    url=url,
                    published=pub_date,
                    summary=summary,
                    categories=categories,
                    symbols_affected=symbols,
                    importance=importance,
                ))

        except Exception as e:
            logger.error(f"Error fetching {name}: {e}")

        return items

    def _categorize(self, title: str, summary: str) -> tuple[list[str], list[str], str]:
        """Categorize news based on keywords."""
        text = f"{title} {summary}".lower()
        categories = []
        symbols = set()
        importance = "medium"

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                categories.append(category)
                # Add affected symbols
                for kw, syms in KEYWORD_SYMBOLS.items():
                    if kw in text:
                        symbols.update(syms)

        # Determine importance
        critical_keywords = ["breaking", "urgent", "supreme court", "fed decision", "rate", "crash", "surge"]
        high_keywords = ["earnings", "guidance", "tariff", "sanction", "regulation"]

        if any(kw in text for kw in critical_keywords):
            importance = "critical"
        elif any(kw in text for kw in high_keywords):
            importance = "high"
        elif not categories:
            importance = "low"

        return categories, list(symbols), importance

    async def collect_all(self, feeds: Optional[dict] = None) -> list[NewsItem]:
        """Collect from all RSS feeds in parallel."""
        feeds = feeds or RSS_FEEDS
        tasks = [self.fetch_feed(name, url) for name, url in feeds.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        # Deduplicate by hash
        seen = set()
        unique_items = []
        for item in all_items:
            if item.hash not in seen:
                seen.add(item.hash)
                unique_items.append(item)

        # Sort by published date
        unique_items.sort(key=lambda x: x.published, reverse=True)

        return unique_items

    async def collect_and_save(self) -> dict:
        """Collect all news and save to cache."""
        items = await self.collect_all()

        # Save to daily file
        today = datetime.now().strftime("%Y%m%d")
        cache_file = self.cache_dir / f"news_{today}.json"

        # Load existing
        existing = []
        if cache_file.exists():
            with open(cache_file) as f:
                existing = json.load(f)

        # Merge and dedupe
        existing_hashes = {item.get("hash") for item in existing}
        new_items = [item.to_dict() for item in items if item.hash not in existing_hashes]

        all_items = new_items + existing
        all_items = all_items[:500]  # Keep last 500

        with open(cache_file, "w") as f:
            json.dump(all_items, f, indent=2)

        # Also save latest for quick access
        latest_file = self.cache_dir / "latest.json"
        with open(latest_file, "w") as f:
            json.dump({
                "updated_at": datetime.now().isoformat(),
                "count": len(all_items),
                "new_count": len(new_items),
                "items": all_items[:100],
            }, f, indent=2)

        logger.info(f"Collected {len(new_items)} new items from {len(RSS_FEEDS)} feeds")

        return {
            "total": len(all_items),
            "new": len(new_items),
            "sources": len(RSS_FEEDS),
            "critical": len([i for i in items if i.importance == "critical"]),
            "high": len([i for i in items if i.importance == "high"]),
        }

    def get_critical_news(self, hours: int = 4) -> list[dict]:
        """Get critical/high importance news from last N hours."""
        latest_file = self.cache_dir / "latest.json"
        if not latest_file.exists():
            return []

        with open(latest_file) as f:
            data = json.load(f)

        cutoff = datetime.now().timestamp() - (hours * 3600)
        critical = []

        for item in data.get("items", []):
            if item.get("importance") in ["critical", "high"]:
                try:
                    pub = datetime.fromisoformat(item["published"]).timestamp()
                    if pub > cutoff:
                        critical.append(item)
                except:
                    pass

        return critical

    def search_news(self, keywords: list[str], hours: int = 24) -> list[dict]:
        """Search recent news for keywords."""
        latest_file = self.cache_dir / "latest.json"
        if not latest_file.exists():
            return []

        with open(latest_file) as f:
            data = json.load(f)

        matches = []
        for item in data.get("items", []):
            text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            if any(kw.lower() in text for kw in keywords):
                matches.append(item)

        return matches


async def main():
    """Test news collection."""
    collector = ExpandedNewsCollector()
    try:
        result = await collector.collect_and_save()
        print(f"Collection result: {json.dumps(result, indent=2)}")

        critical = collector.get_critical_news(hours=24)
        print(f"\nCritical/High news ({len(critical)}):")
        for item in critical[:5]:
            print(f"  [{item['importance']}] {item['title'][:80]}")

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
