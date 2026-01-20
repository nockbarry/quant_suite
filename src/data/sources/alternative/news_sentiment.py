#!/usr/bin/env python3
"""News Sentiment Scorer - Score news headlines for market impact.

Uses keyword-based and rule-based sentiment analysis.
For production, could integrate with Claude API for LLM-based scoring.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Sentiment keywords with weights
BULLISH_KEYWORDS = {
    # Strong positive (0.8+)
    "surge": 0.9, "soar": 0.9, "breakout": 0.85, "breakthrough": 0.85,
    "record high": 0.9, "all-time high": 0.9, "beat": 0.8, "exceeds": 0.8,
    "upgrade": 0.8, "outperform": 0.8, "bullish": 0.85, "rally": 0.8,

    # Moderate positive (0.5-0.8)
    "rise": 0.6, "gain": 0.6, "advance": 0.6, "climb": 0.6,
    "positive": 0.5, "strong": 0.5, "growth": 0.55, "expand": 0.55,
    "recovery": 0.6, "rebound": 0.65, "improve": 0.55, "boost": 0.6,
    "buy": 0.5, "accumulate": 0.55, "upside": 0.6, "optimistic": 0.6,
}

BEARISH_KEYWORDS = {
    # Strong negative (0.8+)
    "crash": 0.95, "plunge": 0.9, "collapse": 0.9, "crisis": 0.85,
    "recession": 0.85, "bear market": 0.85, "selloff": 0.8, "sell-off": 0.8,
    "downgrade": 0.8, "underperform": 0.8, "bearish": 0.85,

    # Moderate negative (0.5-0.8)
    "fall": 0.6, "drop": 0.6, "decline": 0.6, "slide": 0.6,
    "negative": 0.5, "weak": 0.5, "slowdown": 0.55, "contraction": 0.6,
    "miss": 0.7, "disappoint": 0.65, "concern": 0.5, "risk": 0.45,
    "sell": 0.5, "reduce": 0.5, "downside": 0.6, "cautious": 0.5,
    "tariff": 0.55, "sanction": 0.55, "war": 0.6, "conflict": 0.55,
}

# Sector-specific sentiment modifiers
SECTOR_KEYWORDS = {
    "tech": ["ai", "artificial intelligence", "semiconductor", "chip", "software", "cloud"],
    "energy": ["oil", "crude", "natural gas", "drilling", "refinery", "opec"],
    "finance": ["bank", "interest rate", "fed", "loan", "credit"],
    "healthcare": ["fda", "drug", "approval", "trial", "pharma"],
    "defense": ["military", "defense", "pentagon", "contract", "weapon"],
}


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    headline: str
    score: float  # -1 (very bearish) to +1 (very bullish)
    confidence: float  # 0-1
    direction: str  # bullish, bearish, neutral
    key_terms: list[str]
    sectors_affected: list[str]
    magnitude: str  # weak, moderate, strong

    def to_dict(self):
        return {
            "headline": self.headline,
            "score": self.score,
            "confidence": self.confidence,
            "direction": self.direction,
            "key_terms": self.key_terms,
            "sectors_affected": self.sectors_affected,
            "magnitude": self.magnitude,
        }


class NewsSentimentScorer:
    """Score news headlines for sentiment and market impact."""

    def __init__(self):
        self.bullish_patterns = BULLISH_KEYWORDS
        self.bearish_patterns = BEARISH_KEYWORDS
        self.sector_keywords = SECTOR_KEYWORDS

    def score_headline(self, headline: str, summary: str = "") -> SentimentScore:
        """Score a single headline."""
        text = f"{headline} {summary}".lower()

        bullish_score = 0.0
        bearish_score = 0.0
        bullish_terms = []
        bearish_terms = []

        # Check bullish keywords
        for term, weight in self.bullish_patterns.items():
            if term in text:
                bullish_score += weight
                bullish_terms.append(term)

        # Check bearish keywords
        for term, weight in self.bearish_patterns.items():
            if term in text:
                bearish_score += weight
                bearish_terms.append(term)

        # Normalize scores
        bullish_score = min(1.0, bullish_score / 2)  # Cap at 1.0
        bearish_score = min(1.0, bearish_score / 2)

        # Calculate net sentiment (-1 to +1)
        net_score = bullish_score - bearish_score

        # Determine direction
        if net_score > 0.2:
            direction = "bullish"
        elif net_score < -0.2:
            direction = "bearish"
        else:
            direction = "neutral"

        # Calculate confidence based on number of terms found
        total_terms = len(bullish_terms) + len(bearish_terms)
        confidence = min(1.0, total_terms * 0.2)  # More terms = higher confidence

        # Determine magnitude
        abs_score = abs(net_score)
        if abs_score > 0.6:
            magnitude = "strong"
        elif abs_score > 0.3:
            magnitude = "moderate"
        else:
            magnitude = "weak"

        # Identify affected sectors
        sectors_affected = []
        for sector, keywords in self.sector_keywords.items():
            if any(kw in text for kw in keywords):
                sectors_affected.append(sector)

        return SentimentScore(
            headline=headline,
            score=net_score,
            confidence=confidence,
            direction=direction,
            key_terms=bullish_terms + bearish_terms,
            sectors_affected=sectors_affected,
            magnitude=magnitude,
        )

    def score_news_batch(self, news_items: list[dict]) -> list[SentimentScore]:
        """Score a batch of news items."""
        scores = []
        for item in news_items:
            headline = item.get("title", item.get("headline", ""))
            summary = item.get("summary", item.get("description", ""))

            if headline:
                score = self.score_headline(headline, summary)
                scores.append(score)

        return scores

    def get_market_sentiment(self, scores: list[SentimentScore]) -> dict:
        """Aggregate sentiment scores for overall market view."""
        if not scores:
            return {
                "overall_score": 0,
                "direction": "neutral",
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
            }

        bullish = [s for s in scores if s.direction == "bullish"]
        bearish = [s for s in scores if s.direction == "bearish"]
        neutral = [s for s in scores if s.direction == "neutral"]

        # Weighted average by confidence
        total_weight = sum(s.confidence for s in scores)
        if total_weight > 0:
            weighted_score = sum(s.score * s.confidence for s in scores) / total_weight
        else:
            weighted_score = 0

        # Determine overall direction
        if weighted_score > 0.15:
            overall_direction = "bullish"
        elif weighted_score < -0.15:
            overall_direction = "bearish"
        else:
            overall_direction = "neutral"

        return {
            "overall_score": weighted_score,
            "direction": overall_direction,
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "neutral_count": len(neutral),
            "strong_signals": [
                s.to_dict() for s in scores
                if s.magnitude == "strong"
            ][:5],
        }

    def get_sector_sentiment(self, scores: list[SentimentScore]) -> dict[str, dict]:
        """Get sentiment breakdown by sector."""
        sector_scores = {}

        for sector in self.sector_keywords.keys():
            sector_items = [s for s in scores if sector in s.sectors_affected]
            if sector_items:
                avg_score = sum(s.score for s in sector_items) / len(sector_items)
                sector_scores[sector] = {
                    "score": avg_score,
                    "count": len(sector_items),
                    "direction": "bullish" if avg_score > 0.15 else "bearish" if avg_score < -0.15 else "neutral",
                }

        return sector_scores


def score_recent_news():
    """Score recent news from cache."""
    news_file = Path.home() / "quant_results" / "live" / "news" / "latest.json"

    if not news_file.exists():
        print("No news cache found. Run expanded_news collector first.")
        return

    with open(news_file) as f:
        data = json.load(f)

    news_items = data.get("items", [])
    print(f"Scoring {len(news_items)} news items...")

    scorer = NewsSentimentScorer()
    scores = scorer.score_news_batch(news_items)

    # Get market sentiment
    market = scorer.get_market_sentiment(scores)
    print(f"\nMarket Sentiment: {market['direction'].upper()} ({market['overall_score']:+.2f})")
    print(f"  Bullish: {market['bullish_count']}, Bearish: {market['bearish_count']}, Neutral: {market['neutral_count']}")

    # Get sector sentiment
    print("\nSector Sentiment:")
    sector_sent = scorer.get_sector_sentiment(scores)
    for sector, data in sorted(sector_sent.items(), key=lambda x: x[1]["score"], reverse=True):
        print(f"  {sector:12s}: {data['direction']:8s} ({data['score']:+.2f}, n={data['count']})")

    # Show strong signals
    print("\nStrong Signals:")
    for score in scores:
        if score.magnitude == "strong":
            emoji = "📈" if score.direction == "bullish" else "📉"
            print(f"  {emoji} [{score.score:+.2f}] {score.headline[:70]}...")

    # Save scores
    output_file = Path.home() / "quant_results" / "live" / "news_sentiment.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "market_sentiment": market,
            "sector_sentiment": sector_sent,
            "scores": [s.to_dict() for s in scores[:100]],
        }, f, indent=2)

    print(f"\nSentiment saved to: {output_file}")


if __name__ == "__main__":
    score_recent_news()
