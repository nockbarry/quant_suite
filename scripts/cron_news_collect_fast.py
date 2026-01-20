#!/usr/bin/env python3
"""Fast News Collection - 30 minute intervals.

More frequent news collection for time-sensitive trading:
- Runs every 30 minutes during market hours
- Focuses on market-moving news
- Lighter weight than full 4-hour collection

Usage:
    # Direct run
    python scripts/cron_news_collect_fast.py

    # Via cron (add to setup_cron.sh)
    */30 6-17 * * 1-5 /path/to/cron_news_collect_fast.py

Created: 2026-01-20
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Keywords for urgent news
URGENT_KEYWORDS = [
    # Market moving
    "breaking", "just in", "flash", "urgent",
    # Corporate actions
    "acquisition", "merger", "buyout", "takeover",
    "bankruptcy", "default", "restructuring",
    # Earnings
    "earnings beat", "earnings miss", "guidance",
    "revenue beat", "revenue miss",
    # Fed/Macro
    "fed", "fomc", "rate cut", "rate hike",
    "inflation", "cpi", "pce", "jobs report",
    # Regulatory
    "sec", "fda approval", "fda reject",
    "lawsuit", "investigation", "subpoena",
    # Executive
    "ceo resign", "cfo resign", "executive",
]


async def fetch_news_rss(url: str, source_name: str) -> list[dict]:
    """Fetch news from RSS feed."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Basic RSS parsing (would use feedparser in production)
            content = response.text

            items = []
            # Extract items between <item> tags
            import re
            item_pattern = re.compile(r'<item>(.*?)</item>', re.DOTALL)
            title_pattern = re.compile(r'<title>(.*?)</title>')
            link_pattern = re.compile(r'<link>(.*?)</link>')
            pubdate_pattern = re.compile(r'<pubDate>(.*?)</pubDate>')

            for match in item_pattern.finditer(content):
                item_content = match.group(1)

                title_match = title_pattern.search(item_content)
                link_match = link_pattern.search(item_content)
                pubdate_match = pubdate_pattern.search(item_content)

                if title_match:
                    title = title_match.group(1).strip()
                    # Clean CDATA
                    title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)

                    link = link_match.group(1).strip() if link_match else ""
                    pubdate = pubdate_match.group(1).strip() if pubdate_match else ""

                    items.append({
                        "title": title,
                        "link": link,
                        "pubdate": pubdate,
                        "source": source_name,
                    })

            return items

    except Exception as e:
        logger.warning(f"RSS fetch failed for {source_name}: {e}")
        return []


def check_urgent(title: str) -> tuple[bool, str]:
    """Check if headline is urgent.

    Returns:
        (is_urgent, matched_keyword)
    """
    title_lower = title.lower()
    for keyword in URGENT_KEYWORDS:
        if keyword in title_lower:
            return True, keyword
    return False, ""


def extract_symbols(title: str) -> list[str]:
    """Extract stock symbols from headline."""
    import re

    # Pattern for stock symbols (uppercase, 1-5 letters)
    # After $ sign or in parentheses
    dollar_pattern = re.compile(r'\$([A-Z]{1,5})\b')
    paren_pattern = re.compile(r'\(([A-Z]{1,5})\)')

    symbols = set()
    symbols.update(dollar_pattern.findall(title))
    symbols.update(paren_pattern.findall(title))

    return list(symbols)


async def collect_fast_news():
    """Collect news from fast sources."""
    logger.info("Starting fast news collection...")

    # RSS feeds for financial news
    feeds = [
        ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=^DJI&region=US&lang=en-US", "yahoo_finance"),
        ("https://www.investing.com/rss/news.rss", "investing_com"),
        ("https://feeds.bloomberg.com/markets/news.rss", "bloomberg"),
    ]

    all_items = []

    for url, source in feeds:
        items = await fetch_news_rss(url, source)
        all_items.extend(items)
        logger.info(f"Fetched {len(items)} items from {source}")

    # Deduplicate by title
    seen_titles = set()
    unique_items = []
    for item in all_items:
        title = item["title"].lower().strip()
        if title not in seen_titles:
            seen_titles.add(title)
            unique_items.append(item)

    # Process and categorize
    urgent_items = []
    regular_items = []

    for item in unique_items:
        is_urgent, keyword = check_urgent(item["title"])
        symbols = extract_symbols(item["title"])

        processed = {
            "timestamp": datetime.now().isoformat(),
            "headline": item["title"],
            "source": item["source"],
            "link": item.get("link", ""),
            "pubdate": item.get("pubdate", ""),
            "symbols": symbols,
            "is_urgent": is_urgent,
            "urgent_keyword": keyword,
        }

        if is_urgent:
            urgent_items.append(processed)
        else:
            regular_items.append(processed)

    # Load existing cache
    cache_path = paths.live / "news_cache.json"
    existing = {"items": [], "last_updated": None}

    if cache_path.exists():
        try:
            with open(cache_path) as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            pass

    # Keep only last 24 hours of existing items
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    existing_items = [
        i for i in existing.get("items", [])
        if i.get("timestamp", "") > cutoff
    ]

    # Merge new items (avoid duplicates)
    existing_headlines = {i["headline"].lower() for i in existing_items}

    new_urgent = [i for i in urgent_items if i["headline"].lower() not in existing_headlines]
    new_regular = [i for i in regular_items if i["headline"].lower() not in existing_headlines]

    all_news = existing_items + new_urgent + new_regular

    # Sort by timestamp
    all_news.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Keep only last 200 items
    all_news = all_news[:200]

    # Save
    output = {
        "last_updated": datetime.now().isoformat(),
        "urgent_count": len([i for i in all_news if i.get("is_urgent")]),
        "total_count": len(all_news),
        "items": all_news,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"News collection complete. "
        f"New urgent: {len(new_urgent)}, New regular: {len(new_regular)}, "
        f"Total cached: {len(all_news)}"
    )

    # Print urgent news
    if new_urgent:
        print("\n=== URGENT NEWS ===")
        for item in new_urgent[:5]:
            print(f"  [{item['urgent_keyword']}] {item['headline'][:80]}")
            if item['symbols']:
                print(f"     Symbols: {', '.join(item['symbols'])}")

    return output


def main():
    """Main entry point."""
    try:
        asyncio.run(collect_fast_news())
    except KeyboardInterrupt:
        logger.info("Collection interrupted")
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
