"""Market Reaction Scorer.

When the market moves AGAINST a headline, that's more informative than confirmation.
- Bullish news + price drops = market rejection (bearish signal)
- Bearish news + price rallies = failed intervention (bullish signal)

Example from this week: Bessent announced 140M Iranian oil barrel release (bearish for oil).
Oil rallied +3.26%. The market rejected the intervention. This is a strong bullish signal.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

# --- Direction inference keywords ---

BULLISH_KEYWORDS = [
    "surge", "surges", "surging", "rally", "rallies", "rallying",
    "beat", "beats", "beating", "soar", "soars", "soaring",
    "jump", "jumps", "jumping", "gain", "gains", "gaining",
    "rise", "rises", "rising", "boom", "booms", "booming",
    "record high", "all-time high", "ath", "breakout", "upgrade",
    "upside", "bullish", "recovery", "rebound", "rebounds",
    "spike", "spikes", "spiking", "outperform",
    "strong", "stronger", "strongest", "expand", "expansion",
    "approve", "approved", "approval", "buy", "buying",
]

BEARISH_KEYWORDS = [
    "crash", "crashes", "crashing", "plunge", "plunges", "plunging",
    "miss", "misses", "missing", "drop", "drops", "dropping",
    "fall", "falls", "falling", "sink", "sinks", "sinking",
    "decline", "declines", "declining", "tumble", "tumbles",
    "sell", "selloff", "sell-off", "dump", "dumps", "dumping",
    "downgrade", "cut", "cuts", "cutting", "slash", "slashes",
    "weak", "weaker", "weakest", "collapse", "collapses",
    "release", "releases",  # supply release = bearish for commodities
    "sanction", "sanctions", "tariff", "tariffs", "ban", "bans",
    "fear", "fears", "warning", "warns", "recession",
    "layoff", "layoffs", "shutdown", "default", "bankruptcy",
]

# Minimum price change (%) to classify as confirmed/rejected vs neutral
SIGNIFICANCE_THRESHOLD = 0.5


@dataclass
class MarketReaction:
    """A scored market reaction to a news headline."""

    news_headline: str
    news_timestamp: str
    news_direction: str  # "bullish", "bearish", "neutral"
    symbols_checked: list[str]
    reaction: str  # "confirmed", "rejected", "neutral"
    price_change_1h: dict[str, float] = field(default_factory=dict)  # symbol -> pct change
    price_change_4h: dict[str, float] = field(default_factory=dict)
    rejection_strength: float = 0.0  # 0-1
    analysis: str = ""

    def to_dict(self) -> dict:
        return {
            "news_headline": self.news_headline,
            "news_timestamp": self.news_timestamp,
            "news_direction": self.news_direction,
            "symbols_checked": self.symbols_checked,
            "reaction": self.reaction,
            "price_change_1h": self.price_change_1h,
            "price_change_4h": self.price_change_4h,
            "rejection_strength": round(self.rejection_strength, 3),
            "analysis": self.analysis,
            "scored_at": datetime.now().isoformat(),
        }


class MarketReactionScorer:
    """Score market reactions to news headlines.

    Reads news items, checks price changes via yfinance, and classifies
    whether the market confirmed or rejected each headline's expected direction.
    """

    def __init__(self, lookback_hours: int = 8):
        self.lookback_hours = lookback_hours

    def score_news_items(self, news_items: list[dict]) -> list[MarketReaction]:
        """Score a list of news items from news_cache.json.

        Args:
            news_items: List of dicts with keys: headline, timestamp/pubdate, symbols

        Returns:
            List of MarketReaction results for items that had scoreable symbols
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.lookback_hours)
        reactions = []

        for item in news_items:
            # Parse timestamp
            ts_str = item.get("timestamp") or item.get("pubdate", "")
            if not ts_str:
                continue
            try:
                news_ts = datetime.fromisoformat(ts_str)
                if news_ts.tzinfo is None:
                    news_ts = news_ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            # Only score recent items
            if news_ts < cutoff:
                continue

            headline = item.get("headline", "")
            if not headline:
                continue

            # Need symbols to check price
            symbols = item.get("symbols", [])
            if not symbols:
                # Try to get symbols from thesis_matches
                thesis_matches = item.get("thesis_matches", {})
                for _tid, match in thesis_matches.items():
                    # thesis_matches don't have symbols directly, skip
                    pass
                if not symbols:
                    continue

            # Infer expected direction from headline
            direction = self._infer_news_direction(headline)
            if direction == "neutral":
                continue

            # Get price changes
            changes_1h = self._get_price_changes(symbols, hours=1)
            changes_4h = self._get_price_changes(symbols, hours=4)

            if not changes_1h and not changes_4h:
                continue

            # Classify reaction
            reaction, strength, analysis = self._classify_reaction(
                direction, changes_1h, changes_4h, headline
            )

            reactions.append(MarketReaction(
                news_headline=headline,
                news_timestamp=ts_str,
                news_direction=direction,
                symbols_checked=symbols,
                reaction=reaction,
                price_change_1h=changes_1h,
                price_change_4h=changes_4h,
                rejection_strength=strength,
                analysis=analysis,
            ))

        return reactions

    def _get_price_changes(self, symbols: list[str], hours: int) -> dict[str, float]:
        """Get percentage price change over last N hours for each symbol.

        Uses yfinance batch download for efficiency.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed, cannot score market reactions")
            return {}

        changes = {}
        period = "1d" if hours <= 8 else "5d"
        interval = "5m" if hours <= 4 else "15m"

        try:
            tickers_str = " ".join(symbols)
            data = yf.download(
                tickers_str,
                period=period,
                interval=interval,
                progress=False,
                threads=True,
            )

            if data.empty:
                return {}

            # Handle single vs multi-ticker response
            if len(symbols) == 1:
                close = data.get("Close")
                if close is not None and len(close) >= 2:
                    # Get change over last N hours worth of bars
                    bars_per_hour = 12 if interval == "5m" else 4
                    lookback = min(bars_per_hour * hours, len(close) - 1)
                    if lookback > 0:
                        current = float(close.iloc[-1])
                        past = float(close.iloc[-lookback])
                        if past > 0:
                            changes[symbols[0]] = round(
                                ((current - past) / past) * 100, 3
                            )
            else:
                close = data.get("Close")
                if close is not None:
                    for sym in symbols:
                        if sym not in close.columns:
                            continue
                        col = close[sym].dropna()
                        if len(col) < 2:
                            continue
                        bars_per_hour = 12 if interval == "5m" else 4
                        lookback = min(bars_per_hour * hours, len(col) - 1)
                        if lookback > 0:
                            current = float(col.iloc[-1])
                            past = float(col.iloc[-lookback])
                            if past > 0:
                                changes[sym] = round(
                                    ((current - past) / past) * 100, 3
                                )
        except Exception as e:
            logger.warning(f"yfinance price fetch failed for {symbols}: {e}")

        return changes

    def _infer_news_direction(self, headline: str) -> str:
        """Infer the expected market direction from a headline using keyword matching.

        Returns "bullish", "bearish", or "neutral".
        """
        headline_lower = headline.lower()
        bullish_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in headline_lower)
        bearish_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in headline_lower)

        if bullish_hits > bearish_hits and bullish_hits >= 1:
            return "bullish"
        elif bearish_hits > bullish_hits and bearish_hits >= 1:
            return "bearish"
        return "neutral"

    def _classify_reaction(
        self,
        expected_direction: str,
        changes_1h: dict[str, float],
        changes_4h: dict[str, float],
        headline: str,
    ) -> tuple[str, float, str]:
        """Classify whether the market confirmed or rejected the headline.

        Returns:
            (reaction, rejection_strength, analysis)
        """
        # Average price change across symbols (prefer 4h for more signal)
        avg_1h = _mean(list(changes_1h.values())) if changes_1h else 0.0
        avg_4h = _mean(list(changes_4h.values())) if changes_4h else 0.0

        # Use 4h if available, otherwise 1h
        primary_change = avg_4h if changes_4h else avg_1h
        timeframe = "4h" if changes_4h else "1h"

        # Check if change is significant
        if abs(primary_change) < SIGNIFICANCE_THRESHOLD:
            return "neutral", 0.0, f"Price change {primary_change:+.2f}% ({timeframe}) below significance threshold"

        # Determine if market moved with or against headline
        if expected_direction == "bullish":
            if primary_change > SIGNIFICANCE_THRESHOLD:
                return "confirmed", 0.0, f"Bullish news confirmed: price {primary_change:+.2f}% ({timeframe})"
            else:
                strength = min(abs(primary_change) / 3.0, 1.0)
                symbols = list(changes_4h.keys() or changes_1h.keys())
                return (
                    "rejected",
                    strength,
                    f"REJECTION: Bullish headline but {', '.join(symbols)} fell {primary_change:+.2f}% ({timeframe}). "
                    f"Market disagrees with '{headline[:60]}...'",
                )
        elif expected_direction == "bearish":
            if primary_change < -SIGNIFICANCE_THRESHOLD:
                return "confirmed", 0.0, f"Bearish news confirmed: price {primary_change:+.2f}% ({timeframe})"
            else:
                strength = min(abs(primary_change) / 3.0, 1.0)
                symbols = list(changes_4h.keys() or changes_1h.keys())
                return (
                    "rejected",
                    strength,
                    f"REJECTION: Bearish headline but {', '.join(symbols)} rose {primary_change:+.2f}% ({timeframe}). "
                    f"Failed intervention / market shrugged off '{headline[:60]}...'",
                )

        return "neutral", 0.0, "Could not classify"

    def get_rejected_signals(self, reactions: list[MarketReaction]) -> list[MarketReaction]:
        """Filter for rejected reactions only (the most valuable signals)."""
        return [r for r in reactions if r.reaction == "rejected"]

    def save(self, reactions: list[MarketReaction]) -> Path:
        """Save reactions to market_reactions.json."""
        output_path = paths.live / "market_reactions.json"
        data = {
            "scored_at": datetime.now().isoformat(),
            "total": len(reactions),
            "rejected_count": sum(1 for r in reactions if r.reaction == "rejected"),
            "confirmed_count": sum(1 for r in reactions if r.reaction == "confirmed"),
            "neutral_count": sum(1 for r in reactions if r.reaction == "neutral"),
            "reactions": [r.to_dict() for r in reactions],
        }
        try:
            output_path.write_text(json.dumps(data, indent=2))
            logger.info(f"Saved {len(reactions)} market reactions to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save market reactions: {e}")
        return output_path

    def run(self) -> list[MarketReaction]:
        """Convenience: load news_cache.json, score, and save."""
        news_path = paths.live / "news_cache.json"
        if not news_path.exists():
            logger.warning("No news_cache.json found")
            return []

        try:
            cache = json.loads(news_path.read_text())
            items = cache.get("items", [])
        except Exception as e:
            logger.error(f"Failed to read news_cache.json: {e}")
            return []

        reactions = self.score_news_items(items)
        self.save(reactions)
        return reactions


def _mean(values: list[float]) -> float:
    """Safe mean calculation."""
    if not values:
        return 0.0
    return sum(values) / len(values)
