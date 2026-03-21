#!/usr/bin/env python3
"""Score market reactions to news — detects failed interventions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.intelligence.market_reaction import MarketReactionScorer
from src.core.paths import paths
import json, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [market-reaction] %(message)s")
logger = logging.getLogger(__name__)

def main():
    scorer = MarketReactionScorer()

    # Load news items
    news_file = paths.live / "news_cache.json"
    if not news_file.exists():
        logger.info("No news cache found")
        return

    with open(news_file) as f:
        data = json.load(f)

    items = [i for i in data.get("items", []) if i.get("is_urgent") or i.get("symbols")]

    reactions = scorer.score_news_items(items[:20])  # Score top 20 items
    rejected = scorer.get_rejected_signals(reactions)

    logger.info(f"Scored {len(reactions)} news items, {len(rejected)} rejected signals")
    for r in rejected:
        logger.info(f"  REJECTED: {r.news_headline[:60]} (1h: {r.price_change_1h})")

    scorer.save(reactions)

if __name__ == "__main__":
    main()
