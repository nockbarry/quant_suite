#!/usr/bin/env python3
"""
Venezuela/Cuba News Monitor

Monitors news for keywords relevant to our Venezuela trading thesis.
Generates alerts when important events are detected.

Usage:
    PYTHONPATH=. python scripts/monitor_venezuela_news.py
    PYTHONPATH=. python scripts/monitor_venezuela_news.py --continuous --interval 300
"""

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/home/nock/quant_results/venezuela_research/news_alerts")


# =============================================================================
# KEYWORD CONFIGURATION
# =============================================================================

@dataclass
class KeywordCategory:
    """Category of keywords to monitor."""
    name: str
    keywords: list[str]
    signal_type: str  # "bullish", "bearish", "chaos", "catalyst"
    priority: int  # 1-5, higher = more important
    affected_symbols: list[str]


# Define keyword categories for Venezuela thesis
KEYWORD_CATEGORIES = [
    # Contract/Reconstruction (Bullish for SLB/HAL)
    KeywordCategory(
        name="reconstruction_contracts",
        keywords=[
            "PDVSA contract", "Venezuela oil contract", "SLB Venezuela",
            "Schlumberger Venezuela", "Halliburton Venezuela", "Baker Hughes Venezuela",
            "oil reconstruction", "Venezuela infrastructure", "Venezuela oil investment",
            "oilfield services contract", "Venezuela drilling",
        ],
        signal_type="bullish",
        priority=5,
        affected_symbols=["SLB", "HAL", "BKR", "WFRD"],
    ),

    # Stability signals (Bullish for refiners)
    KeywordCategory(
        name="stability_signals",
        keywords=[
            "Venezuela transition", "Venezuela stability", "PDVSA production",
            "Venezuela exports resume", "crude exports", "Venezuela oil flow",
            "refinery restart", "production increase Venezuela",
        ],
        signal_type="bullish",
        priority=4,
        affected_symbols=["VLO", "PSX", "PBF", "SLB"],
    ),

    # Chaos signals (Dip buying opportunity)
    KeywordCategory(
        name="chaos_signals",
        keywords=[
            "ELN attack", "ELN retaliation", "colectivo", "Padrino",
            "Venezuela violence", "Caracas attack", "sabotage Venezuela",
            "guerrilla Venezuela", "Venezuela unrest", "Venezuela protest",
            "Venezuela resistance", "Venezuela insurgency",
        ],
        signal_type="chaos",
        priority=5,
        affected_symbols=["SLB", "VLO", "HAL", "XLE"],
    ),

    # Cuba signals (Watch for domino effect)
    KeywordCategory(
        name="cuba_signals",
        keywords=[
            "Cuba sanctions", "Cuba regime", "Rubio Cuba", "Cuba collapse",
            "Cuba oil crisis", "Havana crisis", "Cuba regime change",
            "Cuba intervention", "Cuba blockade", "Cuba economy collapse",
        ],
        signal_type="catalyst",
        priority=4,
        affected_symbols=["RCL", "NCLH", "CCL", "MAR", "HLT"],
    ),

    # China response signals
    KeywordCategory(
        name="china_response",
        keywords=[
            "China Venezuela", "China PDVSA", "Chinese refiners Venezuela",
            "China crude alternative", "China oil sanctions", "China Canada crude",
            "China heavy crude",
        ],
        signal_type="catalyst",
        priority=3,
        affected_symbols=["CNQ", "SU", "USO"],
    ),

    # Citgo/Legal signals
    KeywordCategory(
        name="citgo_legal",
        keywords=[
            "Citgo auction", "PDV Holding", "Venezuela debt", "Venezuela bonds",
            "PDVSA restructuring", "Crystallex", "ConocoPhillips Venezuela",
        ],
        signal_type="catalyst",
        priority=3,
        affected_symbols=["VLO", "PSX"],
    ),

    # Gold/Mineral signals
    KeywordCategory(
        name="minerals",
        keywords=[
            "Venezuela gold", "Orinoco mining", "Venezuela coltan",
            "Venezuela rare earth", "mining arc Venezuela", "mineral rights Venezuela",
        ],
        signal_type="bullish",
        priority=3,
        affected_symbols=["GLD", "GDX", "GOLD"],
    ),
]


@dataclass
class NewsAlert:
    """Alert generated from news monitoring."""
    timestamp: datetime
    title: str
    url: str
    source: str
    category: str
    signal_type: str
    priority: int
    matched_keywords: list[str]
    affected_symbols: list[str]
    snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "signal_type": self.signal_type,
            "priority": self.priority,
            "matched_keywords": self.matched_keywords,
            "affected_symbols": self.affected_symbols,
            "snippet": self.snippet,
        }


# =============================================================================
# RSS FEEDS FOR VENEZUELA/ENERGY NEWS
# =============================================================================

RSS_FEEDS = [
    # Major financial news
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/rss/"},

    # Energy-specific
    {"name": "OilPrice.com", "url": "https://oilprice.com/rss/main"},
    {"name": "Rigzone", "url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx"},

    # Latin America
    {"name": "Reuters LatAm", "url": "https://feeds.reuters.com/reuters/latAmNews"},
]


# =============================================================================
# NEWS FETCHING
# =============================================================================

async def fetch_rss_feed(feed_config: dict) -> list[dict]:
    """Fetch and parse an RSS feed."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(feed_config["url"])
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                articles = []
                for entry in feed.entries[:20]:  # Last 20 entries
                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published = datetime(*entry.updated_parsed[:6])
                    else:
                        published = datetime.now()

                    articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": feed_config["name"],
                        "published_at": published,
                        "summary": entry.get("summary", ""),
                    })
                return articles
    except Exception as e:
        logger.warning(f"Failed to fetch {feed_config['name']}: {e}")
    return []


async def fetch_all_feeds() -> list[dict]:
    """Fetch all RSS feeds concurrently."""
    tasks = [fetch_rss_feed(feed) for feed in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles = []
    for result in results:
        if isinstance(result, list):
            all_articles.extend(result)

    # Sort by date
    all_articles.sort(key=lambda x: x["published_at"], reverse=True)
    return all_articles


async def search_google_news(query: str) -> list[dict]:
    """Search Google News RSS for a query."""
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                articles = []
                for entry in feed.entries[:10]:
                    published = datetime.now()
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6])

                    articles.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": f"Google News: {query}",
                        "published_at": published,
                        "summary": entry.get("summary", ""),
                    })
                return articles
    except Exception as e:
        logger.warning(f"Failed to search Google News for '{query}': {e}")
    return []


# =============================================================================
# KEYWORD MATCHING
# =============================================================================

def match_keywords(text: str, categories: list[KeywordCategory]) -> list[tuple[KeywordCategory, list[str]]]:
    """Match text against keyword categories."""
    text_lower = text.lower()
    matches = []

    for category in categories:
        matched_keywords = []
        for keyword in category.keywords:
            if keyword.lower() in text_lower:
                matched_keywords.append(keyword)

        if matched_keywords:
            matches.append((category, matched_keywords))

    return matches


def generate_alerts(articles: list[dict], categories: list[KeywordCategory]) -> list[NewsAlert]:
    """Generate alerts from articles matching keywords."""
    alerts = []

    for article in articles:
        # Combine title and summary for matching
        text = f"{article['title']} {article.get('summary', '')}"

        matches = match_keywords(text, categories)

        for category, matched_keywords in matches:
            alert = NewsAlert(
                timestamp=article["published_at"],
                title=article["title"],
                url=article["url"],
                source=article["source"],
                category=category.name,
                signal_type=category.signal_type,
                priority=category.priority,
                matched_keywords=matched_keywords,
                affected_symbols=category.affected_symbols,
                snippet=article.get("summary", "")[:200] if article.get("summary") else None,
            )
            alerts.append(alert)

    # Sort by priority (high first), then by timestamp (newest first)
    alerts.sort(key=lambda x: (-x.priority, -x.timestamp.timestamp()))

    return alerts


# =============================================================================
# ALERT OUTPUT
# =============================================================================

def save_alerts(alerts: list[NewsAlert], output_dir: Path) -> None:
    """Save alerts to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"alerts_{timestamp}.json"

    data = [alert.to_dict() for alert in alerts]
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved {len(alerts)} alerts to {filepath}")

    # Also save latest alerts
    latest_path = output_dir / "latest_alerts.json"
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)


def print_alerts(alerts: list[NewsAlert]) -> None:
    """Print alerts in a readable format."""
    if not alerts:
        print("\nNo matching news alerts found.")
        return

    print("\n" + "=" * 70)
    print("VENEZUELA NEWS ALERTS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Group by signal type
    by_signal = {}
    for alert in alerts:
        if alert.signal_type not in by_signal:
            by_signal[alert.signal_type] = []
        by_signal[alert.signal_type].append(alert)

    signal_order = ["bullish", "catalyst", "chaos", "bearish"]
    signal_emoji = {
        "bullish": "[BULLISH]",
        "catalyst": "[CATALYST]",
        "chaos": "[CHAOS/DIP]",
        "bearish": "[BEARISH]",
    }

    for signal in signal_order:
        if signal not in by_signal:
            continue

        print(f"\n{signal_emoji.get(signal, signal.upper())}")
        print("-" * 70)

        for alert in by_signal[signal][:5]:  # Top 5 per category
            priority_stars = "*" * alert.priority
            symbols = ", ".join(alert.affected_symbols)
            print(f"\n  {priority_stars} [{alert.category}] ({symbols})")
            print(f"  {alert.title[:80]}")
            print(f"  Keywords: {', '.join(alert.matched_keywords)}")
            print(f"  Source: {alert.source} | {alert.timestamp.strftime('%Y-%m-%d %H:%M')}")
            if alert.snippet:
                print(f"  {alert.snippet[:100]}...")

    # Summary
    print("\n" + "=" * 70)
    print("ALERT SUMMARY")
    print("=" * 70)
    print(f"Total alerts: {len(alerts)}")
    for signal, alert_list in by_signal.items():
        print(f"  {signal}: {len(alert_list)}")

    # Affected symbols summary
    all_symbols = set()
    for alert in alerts:
        all_symbols.update(alert.affected_symbols)
    print(f"\nAffected symbols: {', '.join(sorted(all_symbols))}")


# =============================================================================
# MAIN MONITORING LOOP
# =============================================================================

async def run_scan() -> list[NewsAlert]:
    """Run a single news scan."""
    logger.info("Fetching news from RSS feeds...")
    articles = await fetch_all_feeds()
    logger.info(f"Fetched {len(articles)} articles from RSS feeds")

    # Also search for specific Venezuela-related queries
    search_queries = [
        "Venezuela oil",
        "Venezuela Maduro",
        "PDVSA",
        "Cuba crisis",
        "ELN Colombia",
    ]

    for query in search_queries:
        logger.info(f"Searching Google News for: {query}")
        search_results = await search_google_news(query)
        articles.extend(search_results)
        await asyncio.sleep(1)  # Rate limit

    logger.info(f"Total articles to scan: {len(articles)}")

    # Generate alerts
    alerts = generate_alerts(articles, KEYWORD_CATEGORIES)
    logger.info(f"Generated {len(alerts)} alerts")

    return alerts


async def continuous_monitor(interval_seconds: int = 300) -> None:
    """Run continuous monitoring loop."""
    logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")

    seen_urls = set()

    while True:
        try:
            alerts = await run_scan()

            # Filter to new alerts only
            new_alerts = [a for a in alerts if a.url not in seen_urls]
            for alert in alerts:
                seen_urls.add(alert.url)

            if new_alerts:
                print(f"\n*** {len(new_alerts)} NEW ALERTS ***")
                print_alerts(new_alerts)
                save_alerts(new_alerts, OUTPUT_DIR)
            else:
                logger.info("No new alerts")

            # Keep seen_urls from growing too large
            if len(seen_urls) > 10000:
                seen_urls.clear()

        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

        logger.info(f"Sleeping for {interval_seconds} seconds...")
        await asyncio.sleep(interval_seconds)


async def main():
    parser = argparse.ArgumentParser(description="Monitor Venezuela/Cuba news")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous monitoring",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Scan interval in seconds (default: 300)",
    )
    args = parser.parse_args()

    if args.continuous:
        await continuous_monitor(args.interval)
    else:
        # Single scan
        alerts = await run_scan()
        print_alerts(alerts)
        if alerts:
            save_alerts(alerts, OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
