"""Hormuz Strait disruption tracker.

Estimates Hormuz disruption level from proxy signals:
- BNO-USO spread: Brent-WTI premium indicates Middle East risk premium
- FRO/DHT vs XLE: Tanker divergence from broad energy = route-specific disruption
- News keyword frequency: "hormuz" mentions in news_cache.json as sentiment signal
- Computed: Estimated disruption level (0-100%), confidence score

Why: 21% of global oil and 33% of global fertilizer transits Hormuz.
Direct measurement is impossible; this tracks the market-implied disruption
through proxy spreads that widen during actual chokepoint events.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import pandas as pd
except ImportError:
    pd = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class HormuzSnapshot:
    """Estimated Hormuz disruption status from proxy signals."""

    timestamp: str
    # Raw proxy prices
    bno_price: float  # Brent oil ETF
    uso_price: float  # WTI oil ETF
    fro_price: float  # Frontline tanker
    dht_price: float  # DHT tanker
    xle_price: float  # Energy sector ETF

    # Spread signals
    brent_wti_spread_pct: float  # (BNO-USO)/USO * 100 (positive = ME risk premium)
    tanker_energy_divergence: float  # Avg tanker 5d chg - XLE 5d chg
    bno_change_5d: float  # Brent 5-day change

    # News signal
    hormuz_mention_count: int  # Keyword hits in news_cache.json
    hormuz_news_score: float  # 0-1 normalized news intensity

    # Composite estimate
    disruption_level_pct: float  # 0-100% estimated disruption
    confidence: float  # 0-1 confidence in estimate
    risk_label: str  # "normal", "elevated", "high", "critical"

    source: str
    data_quality: str


# Disruption level calibration thresholds
# Based on historical Hormuz incidents: 2019 tanker seizures, 2024 Houthi attacks
_BRENT_WTI_NORMAL = 5.0  # Normal BNO-USO spread %
_BRENT_WTI_CRISIS = 15.0  # Crisis-level spread %
_TANKER_DIVERGE_NORMAL = 2.0  # Normal tanker-XLE divergence %
_TANKER_DIVERGE_CRISIS = 15.0  # Crisis tanker-XLE divergence %
_NEWS_MENTIONS_HIGH = 5  # Headlines with "hormuz" = high
_NEWS_MENTIONS_CRITICAL = 15  # Headlines with "hormuz" = critical


class HormuzTracker:
    """Track Hormuz disruption through market proxy signals.

    Three-signal composite:
    1. Brent-WTI spread: Middle East oil premium (widens with Hormuz risk)
    2. Tanker-Energy divergence: Route-specific shipping premium
    3. News keyword density: Sentiment/awareness signal

    Each signal contributes 0-33% to the disruption estimate.
    Confidence weighted by data availability.
    """

    TICKERS = ["BNO", "USO", "FRO", "DHT", "XLE"]

    REFERENCE_PRICES = {
        "BNO": 30.0,
        "USO": 70.0,
        "FRO": 20.0,
        "DHT": 12.0,
        "XLE": 85.0,
    }

    HORMUZ_KEYWORDS = [
        "hormuz", "strait of hormuz", "hormuz strait",
        "persian gulf", "kharg island", "hormuz blockade",
        "iran strait", "hormuz closure", "hormuz disruption",
    ]

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "hormuz_status.json"
        self.news_cache = paths.live / "news_cache.json"

    async def collect(self) -> HormuzSnapshot:
        """Collect Hormuz disruption estimate from all proxy signals."""
        # Collect price data and news in parallel
        price_task = self._collect_prices()
        news_result = self._scan_news()

        prices = await price_task

        # Build composite estimate
        snapshot = self._build_estimate(prices, news_result)
        self._save(snapshot)
        return snapshot

    async def _collect_prices(self) -> dict:
        """Fetch price data for proxy tickers."""
        if yf is None or pd is None:
            return {"error": "yfinance not installed"}

        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_yfinance
            )
        except Exception as e:
            logger.error(f"Hormuz price collection failed: {e}")
            return {"error": str(e)}

    def _fetch_yfinance(self) -> dict:
        """Synchronous yfinance fetch — runs in executor."""
        data = yf.download(
            self.TICKERS, period="30d", progress=False, group_by="ticker"
        )

        if data.empty:
            raise ValueError("yfinance returned empty data for Hormuz tickers")

        result = {"prices": {}, "changes_5d": {}}

        for ticker in self.TICKERS:
            try:
                if len(self.TICKERS) > 1:
                    series = data[ticker]["Close"].dropna()
                else:
                    series = data["Close"].dropna()

                if series.empty:
                    raise ValueError(f"No close data for {ticker}")

                latest = float(series.iloc[-1])
                result["prices"][ticker] = latest

                if len(series) >= 6:
                    prev_5d = float(series.iloc[-6])
                    result["changes_5d"][ticker] = ((latest - prev_5d) / prev_5d) * 100
                else:
                    result["changes_5d"][ticker] = 0.0

            except Exception as e:
                logger.warning(f"Failed to get {ticker} Hormuz data: {e}")
                result["prices"][ticker] = self.REFERENCE_PRICES.get(ticker, 0.0)
                result["changes_5d"][ticker] = 0.0

        return result

    def _scan_news(self) -> dict:
        """Scan news_cache.json for Hormuz-related keyword mentions."""
        mention_count = 0
        matching_headlines = []

        if not self.news_cache.exists():
            return {"mention_count": 0, "headlines": [], "score": 0.0}

        try:
            with open(self.news_cache) as f:
                news = json.load(f)

            for item in news.get("items", []):
                headline = (item.get("headline", "") or "").lower()
                for keyword in self.HORMUZ_KEYWORDS:
                    if keyword in headline:
                        mention_count += 1
                        matching_headlines.append(item.get("headline", ""))
                        break  # Count each headline once

            # Normalize: 0 mentions = 0, 5+ = 0.5, 15+ = 1.0
            if mention_count >= _NEWS_MENTIONS_CRITICAL:
                score = 1.0
            elif mention_count >= _NEWS_MENTIONS_HIGH:
                score = 0.5 + 0.5 * (mention_count - _NEWS_MENTIONS_HIGH) / (
                    _NEWS_MENTIONS_CRITICAL - _NEWS_MENTIONS_HIGH
                )
            elif mention_count > 0:
                score = mention_count / _NEWS_MENTIONS_HIGH * 0.5
            else:
                score = 0.0

            return {
                "mention_count": mention_count,
                "headlines": matching_headlines[:10],
                "score": min(score, 1.0),
            }
        except Exception as e:
            logger.warning(f"News scan for Hormuz failed: {e}")
            return {"mention_count": 0, "headlines": [], "score": 0.0}

    def _build_estimate(self, prices: dict, news: dict) -> HormuzSnapshot:
        """Combine all signals into disruption estimate."""
        has_error = "error" in prices

        if has_error:
            # Price data unavailable — use news only with low confidence
            return HormuzSnapshot(
                timestamp=datetime.now().isoformat(),
                bno_price=0, uso_price=0, fro_price=0, dht_price=0, xle_price=0,
                brent_wti_spread_pct=0, tanker_energy_divergence=0, bno_change_5d=0,
                hormuz_mention_count=news["mention_count"],
                hormuz_news_score=news["score"],
                disruption_level_pct=news["score"] * 33,  # News signal only = max 33%
                confidence=0.2,
                risk_label=self._label(news["score"] * 33),
                source="news_only",
                data_quality="stale",
            )

        p = prices["prices"]
        c5 = prices["changes_5d"]

        bno = p.get("BNO", 0)
        uso = p.get("USO", 0)
        fro = p.get("FRO", 0)
        dht = p.get("DHT", 0)
        xle = p.get("XLE", 0)

        # Signal 1: Brent-WTI spread (0-33%)
        brent_wti_spread = ((bno - uso) / uso * 100) if uso > 0 else 0
        spread_signal = max(0, min(1, (abs(brent_wti_spread) - _BRENT_WTI_NORMAL) / (
            _BRENT_WTI_CRISIS - _BRENT_WTI_NORMAL
        )))

        # Signal 2: Tanker-Energy divergence (0-33%)
        tanker_avg_chg = (c5.get("FRO", 0) + c5.get("DHT", 0)) / 2
        xle_chg = c5.get("XLE", 0)
        divergence = tanker_avg_chg - xle_chg
        divergence_signal = max(0, min(1, (abs(divergence) - _TANKER_DIVERGE_NORMAL) / (
            _TANKER_DIVERGE_CRISIS - _TANKER_DIVERGE_NORMAL
        )))

        # Signal 3: News intensity (0-33%)
        news_signal = news["score"]

        # Composite disruption estimate
        disruption = (spread_signal * 33 + divergence_signal * 33 + news_signal * 33)

        # Confidence: higher when all 3 signals agree
        signals = [spread_signal, divergence_signal, news_signal]
        active_signals = sum(1 for s in signals if s > 0.1)
        confidence = 0.3 + 0.7 * (active_signals / 3)  # 0.3 baseline, 1.0 if all active

        return HormuzSnapshot(
            timestamp=datetime.now().isoformat(),
            bno_price=round(bno, 2),
            uso_price=round(uso, 2),
            fro_price=round(fro, 2),
            dht_price=round(dht, 2),
            xle_price=round(xle, 2),
            brent_wti_spread_pct=round(brent_wti_spread, 2),
            tanker_energy_divergence=round(divergence, 2),
            bno_change_5d=round(c5.get("BNO", 0), 2),
            hormuz_mention_count=news["mention_count"],
            hormuz_news_score=round(news["score"], 2),
            disruption_level_pct=round(disruption, 1),
            confidence=round(confidence, 2),
            risk_label=self._label(disruption),
            source="yfinance+news",
            data_quality="live",
        )

    @staticmethod
    def _label(level: float) -> str:
        """Map disruption level to risk label."""
        if level >= 66:
            return "critical"
        elif level >= 40:
            return "high"
        elif level >= 15:
            return "elevated"
        return "normal"

    def _save(self, snapshot: HormuzSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved Hormuz snapshot: disruption={snapshot.disruption_level_pct:.0f}% "
            f"({snapshot.risk_label}), Brent-WTI spread={snapshot.brent_wti_spread_pct:+.1f}%, "
            f"tanker divergence={snapshot.tanker_energy_divergence:+.1f}%, "
            f"news mentions={snapshot.hormuz_mention_count}"
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
