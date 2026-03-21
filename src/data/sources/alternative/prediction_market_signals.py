"""Prediction Market Signal Pipeline.

Focused collector for thesis-relevant prediction markets.
Tracks specific markets that map to active theses, detects
probability changes, and generates trading signals.

Sources (in priority order):
1. Polymarket (gamma-api.polymarket.com) — highest liquidity
2. Manifold Markets (api.manifold.markets) — backup, community forecasting
3. Kalshi (trading-api.kalshi.com) — if API key available

Signal generation:
- Probability change > 5% in 24h = SIGNAL
- Market probability diverges from thesis conviction by 30%+ = ALERT
- New market created on thesis topic = WATCH
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from src.core.paths import paths

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Thesis → market keyword mapping (seed data)
# ──────────────────────────────────────────────────────────────────────

THESIS_MARKET_SEEDS: dict[str, list[str]] = {
    "Iran War Energy Supercycle": [
        "iran ceasefire", "iran war", "hormuz", "iran nuclear",
        "oil price", "brent crude", "iran attack", "iran strike",
    ],
    "Fed Independence Crisis": [
        "fed rate cut", "fed rate hike", "fomc", "interest rate",
        "inflation target", "recession 2026", "federal reserve",
    ],
    "Gold De-Dollarization": [
        "gold price", "dollar index", "central bank gold",
        "de-dollarization", "gold 6000", "gold 5000",
    ],
    "Fertilizer Agflation": [
        "food prices", "fertilizer", "wheat price", "famine",
        "food crisis", "grain export",
    ],
    "Venezuela Energy Recovery": [
        "venezuela", "maduro", "pdvsa", "sanctions venezuela",
        "venezuela oil", "guaido",
    ],
    "Memory HBM Supercycle": [
        "nvidia", "ai chip", "semiconductor", "hbm memory",
        "ai spending", "gpu shortage",
    ],
    "European Defense Rearm": [
        "european defense", "nato spending", "eu defense",
        "germany military", "europe rearmament",
    ],
    "Defense Spending Surge": [
        "defense spending", "military budget", "pentagon budget",
        "defense stocks",
    ],
    "AI Power Infrastructure": [
        "data center", "nuclear power", "ai electricity",
        "power demand", "hyperscaler capex",
    ],
    "Stablecoin Infrastructure": [
        "stablecoin", "genius act", "usdt", "usdc",
        "crypto regulation",
    ],
    "Copper AI Squeeze": [
        "copper price", "copper shortage", "copper deficit",
    ],
}

# Map theses to representative symbols for signal output
THESIS_SYMBOL_MAP: dict[str, list[str]] = {
    "Iran War Energy Supercycle": ["USO", "XLE", "OIH"],
    "Fed Independence Crisis": ["TLT", "GLD", "SPY"],
    "Gold De-Dollarization": ["GLD", "GDX", "GOLD"],
    "Fertilizer Agflation": ["CF", "MOS", "NTR"],
    "Venezuela Energy Recovery": ["SLB", "HAL", "PBF"],
    "Memory HBM Supercycle": ["MU", "NVDA", "SMH"],
    "European Defense Rearm": ["LMT", "RTX", "BA"],
    "Defense Spending Surge": ["LMT", "RTX", "NOC"],
    "AI Power Infrastructure": ["VST", "CEG", "NRG"],
    "Stablecoin Infrastructure": ["COIN", "SQ", "PYPL"],
    "Copper AI Squeeze": ["FCX", "COPX", "SCCO"],
}


# ──────────────────────────────────────────────────────────────────────
# Signal dataclass
# ──────────────────────────────────────────────────────────────────────

@dataclass
class PredictionMarketSignal:
    """A signal generated from prediction market data."""

    market_id: str
    source: str  # "polymarket", "manifold", "kalshi"
    question: str
    current_probability: float  # 0-1
    previous_probability: float  # 0-1 (from last scan)
    probability_change_24h: float  # percentage point change
    volume: float  # USD volume
    matched_thesis: str  # Which thesis this maps to
    matched_thesis_symbols: list[str]  # Representative symbols
    signal_type: str  # "probability_shift", "thesis_divergence", "new_market"
    signal_direction: str  # "bullish" or "bearish" for the thesis
    signal_strength: float  # 0-1
    url: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Collector
# ──────────────────────────────────────────────────────────────────────

class PredictionMarketCollector:
    """Collects and generates signals from prediction markets.

    Fetches markets from Polymarket and Manifold, matches them to active
    theses, detects probability changes, and flags thesis-market divergences.
    """

    CACHE_FILE = paths.live / "prediction_market_signals.json"
    HISTORY_FILE = paths.social / "prediction_market_history.jsonl"

    # API endpoints
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    MANIFOLD_API = "https://api.manifold.markets/v0"

    def __init__(self):
        self.previous_scan: dict[str, dict] = self._load_previous()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "QuantSuite/1.0 (research)",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Main pipeline ──────────────────────────────────────────────

    async def collect(self) -> list[PredictionMarketSignal]:
        """Full collection pipeline.

        Returns:
            List of signals sorted by strength (strongest first).
        """
        try:
            # 1. Fetch markets from all sources
            markets = await self._fetch_all_markets()
            logger.info(f"Fetched {len(markets)} raw markets")

            # 2. Match to theses
            matched = self._match_to_theses(markets)
            logger.info(f"Matched {len(matched)} markets to theses")

            # 3. Detect probability changes
            signals = self._detect_signals(matched)

            # 4. Check for thesis-market divergence
            signals.extend(self._check_thesis_divergence(matched))

            # 5. Sort by strength
            signals.sort(key=lambda s: s.signal_strength, reverse=True)

            # 6. Save
            self._save(signals, matched)

            return signals
        finally:
            await self.close()

    # ── Data fetching ──────────────────────────────────────────────

    async def _fetch_all_markets(self) -> list[dict]:
        """Fetch from all prediction market sources."""
        markets: list[dict] = []

        # Run all fetches concurrently
        poly_task = self._fetch_polymarket()
        manifold_task = self._fetch_manifold()

        poly_markets, manifold_markets = await asyncio.gather(
            poly_task, manifold_task, return_exceptions=True,
        )

        if isinstance(poly_markets, list):
            markets.extend(poly_markets)
        else:
            logger.warning(f"Polymarket fetch failed: {poly_markets}")

        if isinstance(manifold_markets, list):
            markets.extend(manifold_markets)
        else:
            logger.warning(f"Manifold fetch failed: {manifold_markets}")

        return markets

    async def _fetch_polymarket(self) -> list[dict]:
        """Fetch from Polymarket using Gamma API events endpoint.

        Strategy 1: Gamma API events (structured, includes multiple markets per event)
        Strategy 2: Gamma API markets with search terms (for thesis-specific queries)
        """
        client = await self._get_client()
        markets: list[dict] = []

        # Strategy 1: Gamma API events — active, recent, high-volume
        try:
            resp = await client.get(
                f"{self.GAMMA_API}/events",
                params={
                    "limit": 50,
                    "active": "true",
                    "closed": "false",
                },
            )
            resp.raise_for_status()
            events = resp.json()

            for event in events:
                event_title = event.get("title", "")
                event_slug = event.get("slug", "")
                # Each event can contain multiple markets
                for mkt in event.get("markets", [event]):
                    question = mkt.get("question", mkt.get("title", event_title))
                    # Extract probability from outcomePrices or tokens
                    probability = self._extract_polymarket_probability(mkt)
                    volume = float(mkt.get("volume", mkt.get("volumeNum", 0)) or 0)

                    markets.append({
                        "id": f"poly_{mkt.get('id', mkt.get('conditionId', ''))}",
                        "source": "polymarket",
                        "question": question,
                        "probability": probability,
                        "volume": volume,
                        "url": f"https://polymarket.com/event/{event_slug}",
                        "created_at": mkt.get("createdAt", mkt.get("startDate", "")),
                        "end_date": mkt.get("endDate", mkt.get("closeDate", "")),
                    })

            logger.info(f"Polymarket Gamma events: {len(markets)} markets from {len(events)} events")
        except Exception as e:
            logger.warning(f"Polymarket Gamma events failed: {e}")

        # Strategy 2: Search for thesis-relevant terms via Gamma markets endpoint
        search_terms = set()
        for keywords in THESIS_MARKET_SEEDS.values():
            # Take first 2 keywords per thesis to limit API calls
            for kw in keywords[:2]:
                search_terms.add(kw)

        for term in list(search_terms)[:15]:  # Cap at 15 searches
            try:
                resp = await client.get(
                    f"{self.GAMMA_API}/markets",
                    params={
                        "limit": 10,
                        "active": "true",
                        "closed": "false",
                        "tag": term,
                    },
                )
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list):
                        for mkt in items:
                            mid = f"poly_{mkt.get('id', mkt.get('conditionId', ''))}"
                            # Skip duplicates
                            if any(m["id"] == mid for m in markets):
                                continue
                            probability = self._extract_polymarket_probability(mkt)
                            volume = float(mkt.get("volume", mkt.get("volumeNum", 0)) or 0)
                            slug = mkt.get("slug", mkt.get("eventSlug", ""))
                            markets.append({
                                "id": mid,
                                "source": "polymarket",
                                "question": mkt.get("question", mkt.get("title", "")),
                                "probability": probability,
                                "volume": volume,
                                "url": f"https://polymarket.com/event/{slug}",
                                "created_at": mkt.get("createdAt", ""),
                                "end_date": mkt.get("endDate", ""),
                            })
            except Exception:
                pass  # Individual search failures are fine

        logger.info(f"Polymarket total: {len(markets)} markets")
        return markets

    def _extract_polymarket_probability(self, mkt: dict) -> float:
        """Extract probability from Polymarket market data.

        Tries multiple fields since the API format varies:
        - outcomePrices (JSON string "[0.65, 0.35]")
        - tokens[].price
        - probability
        - bestAsk / bestBid
        """
        # Try outcomePrices (most common in Gamma API)
        outcome_prices = mkt.get("outcomePrices")
        if outcome_prices:
            try:
                if isinstance(outcome_prices, str):
                    prices = json.loads(outcome_prices)
                else:
                    prices = outcome_prices
                if prices and len(prices) >= 1:
                    return float(prices[0])
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        # Try tokens array
        tokens = mkt.get("tokens", [])
        if tokens:
            for token in tokens:
                outcome = token.get("outcome", "")
                if outcome.lower() in ("yes", "true", "1"):
                    return float(token.get("price", 0.5))

        # Try direct probability field
        prob = mkt.get("probability")
        if prob is not None:
            return float(prob)

        # Try clobTokenIds approach (extract from order book)
        best_ask = mkt.get("bestAsk")
        best_bid = mkt.get("bestBid")
        if best_ask and best_bid:
            try:
                return (float(best_ask) + float(best_bid)) / 2
            except (ValueError, TypeError):
                pass

        return 0.5  # Default if nothing works

    async def _fetch_manifold(self) -> list[dict]:
        """Fetch from Manifold Markets with thesis-relevant searches."""
        client = await self._get_client()
        markets: list[dict] = []
        seen_ids: set[str] = set()

        # Search for each thesis topic
        search_terms = set()
        for keywords in THESIS_MARKET_SEEDS.values():
            search_terms.add(keywords[0])  # Primary keyword per thesis

        for term in search_terms:
            try:
                resp = await client.get(
                    f"{self.MANIFOLD_API}/search-markets",
                    params={
                        "term": term,
                        "limit": 10,
                        "sort": "liquidity",
                    },
                )
                if resp.status_code != 200:
                    continue

                items = resp.json()
                for item in items:
                    mid = f"manifold_{item.get('id', '')}"
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)

                    # Skip resolved markets
                    if item.get("isResolved", False):
                        continue

                    probability = float(item.get("probability", 0.5))

                    # Compute 24h change if Manifold provides it
                    prob_24h_ago = item.get("prob24HoursAgo")
                    change_24h = 0.0
                    if prob_24h_ago is not None:
                        change_24h = probability - float(prob_24h_ago)

                    volume = float(item.get("volume", 0))
                    liquidity = float(item.get("totalLiquidity", 0))

                    url = item.get("url", "")
                    if not url and item.get("slug"):
                        url = f"https://manifold.markets/{item.get('creatorUsername', '')}/{item['slug']}"

                    markets.append({
                        "id": mid,
                        "source": "manifold",
                        "question": item.get("question", ""),
                        "probability": probability,
                        "probability_change_24h": change_24h,
                        "volume": volume,
                        "liquidity": liquidity,
                        "url": url,
                        "created_at": "",
                        "end_date": "",
                    })
            except Exception as e:
                logger.debug(f"Manifold search '{term}' failed: {e}")

        logger.info(f"Manifold: {len(markets)} markets")
        return markets

    # ── Matching and signal detection ──────────────────────────────

    def _match_to_theses(self, markets: list[dict]) -> list[dict]:
        """Match markets to thesis topics using keyword matching.

        Each market can match multiple theses. Adds 'matched_theses' list
        to each market dict.
        """
        matched = []

        for market in markets:
            question_lower = market.get("question", "").lower()
            if not question_lower:
                continue

            theses_matched: list[str] = []
            for thesis_name, keywords in THESIS_MARKET_SEEDS.items():
                for kw in keywords:
                    if kw in question_lower:
                        theses_matched.append(thesis_name)
                        break  # One match per thesis is enough

            if theses_matched:
                market["matched_theses"] = theses_matched
                matched.append(market)

        return matched

    def _detect_signals(self, matched_markets: list[dict]) -> list[PredictionMarketSignal]:
        """Detect probability changes > 5% since last scan.

        Compares current probabilities against self.previous_scan to find
        significant moves.
        """
        signals = []

        for market in matched_markets:
            mid = market["id"]
            current_prob = market.get("probability", 0.5)

            # Get previous probability from last scan or from market data
            prev_prob = current_prob  # default: no change
            if mid in self.previous_scan:
                prev_prob = self.previous_scan[mid].get("probability", current_prob)

            # Also check if the market itself reports 24h change
            market_change_24h = market.get("probability_change_24h", 0)

            # Use the larger change (market-reported vs our own tracking)
            our_change = current_prob - prev_prob
            effective_change = our_change if abs(our_change) >= abs(market_change_24h) else market_change_24h

            # Skip if change is too small
            if abs(effective_change) < 0.05:
                continue

            for thesis_name in market.get("matched_theses", []):
                direction = self._infer_direction(thesis_name, market, effective_change)
                strength = self._compute_strength(
                    abs(effective_change), market.get("volume", 0),
                )
                symbols = THESIS_SYMBOL_MAP.get(thesis_name, ["SPY"])

                signals.append(PredictionMarketSignal(
                    market_id=mid,
                    source=market.get("source", "unknown"),
                    question=market.get("question", ""),
                    current_probability=current_prob,
                    previous_probability=prev_prob,
                    probability_change_24h=effective_change,
                    volume=market.get("volume", 0),
                    matched_thesis=thesis_name,
                    matched_thesis_symbols=symbols,
                    signal_type="probability_shift",
                    signal_direction=direction,
                    signal_strength=strength,
                    url=market.get("url", ""),
                ))

        return signals

    def _check_thesis_divergence(self, matched_markets: list[dict]) -> list[PredictionMarketSignal]:
        """Check where prediction market probability diverges from thesis conviction.

        Example: Polymarket "Iran ceasefire by April" at 35% means 65% war continues.
        Our Iran War thesis at 95% conviction = we think war continues even more strongly.
        Divergence = 95% - 65% = 30%. If > 30%, flag as ALERT.

        This is a blind spot warning — the market disagrees with us.
        """
        signals = []

        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            active_theses = {t.name: t for t in tracker.get_active_theses()}
        except Exception as e:
            logger.debug(f"Cannot load theses for divergence check: {e}")
            return signals

        for market in matched_markets:
            market_prob = market.get("probability", 0.5)

            for thesis_name in market.get("matched_theses", []):
                thesis = active_theses.get(thesis_name)
                if not thesis:
                    continue

                # Determine what the market probability implies for the thesis
                # Most markets are "Will X happen?" — we need to figure out
                # if YES is bullish or bearish for our thesis.
                thesis_implied_prob = self._thesis_implied_probability(
                    thesis_name, market, market_prob,
                )

                thesis_conviction = thesis.conviction / 100.0  # 0-1
                divergence = abs(thesis_conviction - thesis_implied_prob)

                if divergence < 0.30:
                    continue  # Not divergent enough

                # Direction: is the market more bullish or bearish than us?
                if thesis_implied_prob < thesis_conviction:
                    direction = "bearish"  # Market less convinced than us
                    desc = "market is less bullish than our thesis"
                else:
                    direction = "bullish"  # Market more convinced than us
                    desc = "market is more bullish than our thesis"

                # Strength scales with divergence magnitude
                strength = min(1.0, divergence / 0.50)  # max at 50% divergence
                symbols = THESIS_SYMBOL_MAP.get(thesis_name, ["SPY"])

                signals.append(PredictionMarketSignal(
                    market_id=market["id"],
                    source=market.get("source", "unknown"),
                    question=market.get("question", ""),
                    current_probability=market_prob,
                    previous_probability=market_prob,  # N/A for divergence
                    probability_change_24h=0.0,
                    volume=market.get("volume", 0),
                    matched_thesis=thesis_name,
                    matched_thesis_symbols=symbols,
                    signal_type="thesis_divergence",
                    signal_direction=direction,
                    signal_strength=strength,
                    url=market.get("url", ""),
                ))

        return signals

    # ── Helpers ────────────────────────────────────────────────────

    def _infer_direction(self, thesis_name: str, market: dict, change: float) -> str:
        """Infer whether a probability change is bullish or bearish for the thesis.

        Heuristic: for "negative" event markets (ceasefire, recession, rate cut),
        a probability INCREASE is bearish for the bullish thesis. For "positive"
        event markets (war, oil price rise, spending), probability INCREASE is bullish.
        """
        question = market.get("question", "").lower()

        # Negative-for-thesis keywords: if probability of these RISES, thesis weakens
        bearish_keywords = [
            "ceasefire", "peace", "recession", "rate cut", "rate hike",
            "decline", "crash", "drop", "fall below", "sanctions lifted",
            "de-escalat", "normalize",
        ]
        is_negative_event = any(kw in question for kw in bearish_keywords)

        if is_negative_event:
            # Probability up = thesis bearish
            return "bearish" if change > 0 else "bullish"
        else:
            # Probability up = thesis bullish
            return "bullish" if change > 0 else "bearish"

    def _thesis_implied_probability(
        self, thesis_name: str, market: dict, market_prob: float,
    ) -> float:
        """Convert market probability to implied thesis conviction.

        If the market is about a "negative" event for the thesis (e.g., ceasefire
        for Iran War thesis), then thesis_implied = 1 - market_prob.
        """
        question = market.get("question", "").lower()

        bearish_keywords = [
            "ceasefire", "peace", "recession", "rate cut",
            "decline", "crash", "drop", "fall", "de-escalat",
            "sanctions lifted", "normalize",
        ]
        is_negative_event = any(kw in question for kw in bearish_keywords)

        if is_negative_event:
            return 1.0 - market_prob
        else:
            return market_prob

    def _compute_strength(self, change_magnitude: float, volume: float) -> float:
        """Compute signal strength from probability change and volume.

        Factors:
        - Change magnitude (primary): 5% change = 0.3, 10% = 0.6, 20%+ = 1.0
        - Volume bonus: high volume markets carry more weight
        """
        # Base strength from change magnitude
        strength = min(1.0, change_magnitude / 0.20)  # Maxes at 20% change

        # Volume bonus (0 to +0.2)
        if volume >= 1_000_000:
            strength = min(1.0, strength + 0.2)
        elif volume >= 100_000:
            strength = min(1.0, strength + 0.1)
        elif volume >= 10_000:
            strength = min(1.0, strength + 0.05)

        return round(strength, 3)

    # ── Persistence ────────────────────────────────────────────────

    def _load_previous(self) -> dict[str, dict]:
        """Load previous scan for change detection.

        Returns dict of market_id -> {probability, timestamp}.
        """
        if not self.CACHE_FILE.exists():
            return {}

        try:
            with open(self.CACHE_FILE) as f:
                data = json.load(f)
            # Build lookup from matched_markets
            previous = {}
            for m in data.get("matched_markets", []):
                previous[m["id"]] = {
                    "probability": m.get("probability", 0.5),
                    "timestamp": data.get("timestamp", ""),
                }
            return previous
        except Exception as e:
            logger.debug(f"Failed to load previous scan: {e}")
            return {}

    def _save(self, signals: list[PredictionMarketSignal], matched: list[dict]) -> None:
        """Save signals and matched markets to cache file, append to history."""
        now = datetime.now().isoformat()

        # Cache file — latest snapshot
        cache_data = {
            "timestamp": now,
            "signal_count": len(signals),
            "matched_market_count": len(matched),
            "signals": [s.to_dict() for s in signals],
            "matched_markets": [
                {
                    "id": m["id"],
                    "source": m.get("source", ""),
                    "question": m.get("question", ""),
                    "probability": m.get("probability", 0.5),
                    "volume": m.get("volume", 0),
                    "matched_theses": m.get("matched_theses", []),
                    "url": m.get("url", ""),
                }
                for m in matched
            ],
            "thesis_probabilities": self._summarize_thesis_probabilities(matched),
        }

        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)

        logger.info(f"Saved {len(signals)} signals, {len(matched)} matched markets to {self.CACHE_FILE}")

        # History file — append for trend tracking (JSONL)
        self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history_entry = {
            "timestamp": now,
            "signal_count": len(signals),
            "markets": {
                m["id"]: {
                    "question": m.get("question", "")[:100],
                    "probability": m.get("probability", 0.5),
                    "source": m.get("source", ""),
                }
                for m in matched
            },
        }
        with open(self.HISTORY_FILE, "a") as f:
            f.write(json.dumps(history_entry) + "\n")

        # Trim history to last 2000 entries (~3 months at 2hr intervals)
        try:
            lines = self.HISTORY_FILE.read_text().strip().split("\n")
            if len(lines) > 2000:
                self.HISTORY_FILE.write_text("\n".join(lines[-2000:]) + "\n")
        except Exception:
            pass

    def _summarize_thesis_probabilities(self, matched: list[dict]) -> dict[str, dict]:
        """Summarize market-implied probabilities per thesis.

        For each thesis, aggregate the probabilities of all matched markets
        to create a single "market view" of the thesis.
        """
        thesis_probs: dict[str, list[float]] = {}
        thesis_markets: dict[str, list[str]] = {}

        for m in matched:
            prob = m.get("probability", 0.5)
            question = m.get("question", "").lower()

            # Invert probability for negative-event markets
            bearish_keywords = [
                "ceasefire", "peace", "recession", "rate cut",
                "decline", "crash", "drop", "de-escalat",
            ]
            is_negative = any(kw in question for kw in bearish_keywords)
            implied = 1.0 - prob if is_negative else prob

            for thesis_name in m.get("matched_theses", []):
                thesis_probs.setdefault(thesis_name, []).append(implied)
                thesis_markets.setdefault(thesis_name, []).append(
                    m.get("question", "")[:80]
                )

        summary = {}
        for thesis_name, probs in thesis_probs.items():
            avg_prob = sum(probs) / len(probs)
            summary[thesis_name] = {
                "implied_probability": round(avg_prob, 3),
                "market_count": len(probs),
                "markets": thesis_markets.get(thesis_name, [])[:5],
            }

        return summary


# ──────────────────────────────────────────────────────────────────────
# Convenience function
# ──────────────────────────────────────────────────────────────────────

async def collect_prediction_market_signals() -> list[PredictionMarketSignal]:
    """One-shot convenience function to collect prediction market signals."""
    collector = PredictionMarketCollector()
    return await collector.collect()
