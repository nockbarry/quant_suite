"""LNG (Liquefied Natural Gas) price data collection.

Collects LNG export premium and natural gas input cost data using:
- UNG ETF: Henry Hub natural gas proxy
- LNG stock (Cheniere Energy): LNG export and terminal operator proxy
- Computed: LNG-UNG ratio (export premium), 5d/20d changes

Why: LNG export premium widens when global supply tightens (war, winter).
Cheniere (LNG) vs Henry Hub (UNG) divergence signals global vs domestic pricing.
Hormuz disruption forces LNG rerouting from Qatar, spiking Asian premiums.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
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
class LNGSnapshot:
    """Current LNG price proxy snapshot."""

    timestamp: str
    ung_price: float  # UNG ETF (Henry Hub natural gas proxy)
    lng_price: float  # Cheniere Energy stock (LNG export proxy)
    ung_change_5d: float  # UNG 5-day % change
    ung_change_20d: float  # UNG 20-day % change
    lng_change_5d: float  # LNG 5-day % change
    lng_change_20d: float  # LNG 20-day % change
    lng_ung_ratio: float  # LNG/UNG (export premium proxy)
    lng_ung_ratio_change_5d: float  # 5-day change in ratio
    source: str
    data_quality: str  # "live", "delayed", "stale"


class LNGCollector:
    """Collect LNG price data via yfinance.

    Cheniere Energy (LNG) is the largest US LNG exporter. Its stock
    captures global LNG pricing dynamics. UNG tracks Henry Hub (domestic).
    The LNG/UNG ratio rising = global premium widening vs domestic.
    """

    TICKERS = ["UNG", "LNG"]

    REFERENCE_PRICES = {
        "UNG": 14.0,
        "LNG": 200.0,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "lng_prices.json"

    async def collect(self) -> LNGSnapshot:
        """Collect LNG price data via yfinance proxies."""
        if yf is None or pd is None:
            logger.warning("yfinance or pandas not installed, using stale fallback")
            return self._stale_fallback("yfinance not installed")

        try:
            snapshot = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_yfinance
            )
            self._save(snapshot)
            return snapshot
        except Exception as e:
            logger.error(f"LNG collection failed: {e}")
            return self._stale_fallback(str(e))

    def _fetch_yfinance(self) -> LNGSnapshot:
        """Synchronous yfinance fetch — runs in executor."""
        data = yf.download(
            self.TICKERS, period="30d", progress=False, group_by="ticker"
        )

        if data.empty:
            raise ValueError("yfinance returned empty data for LNG tickers")

        prices = {}
        changes_5d = {}
        changes_20d = {}

        for ticker in self.TICKERS:
            try:
                if len(self.TICKERS) > 1:
                    series = data[ticker]["Close"].dropna()
                else:
                    series = data["Close"].dropna()

                if series.empty:
                    raise ValueError(f"No close data for {ticker}")

                latest = float(series.iloc[-1])
                prices[ticker] = latest

                # 5-day change
                if len(series) >= 6:
                    prev_5d = float(series.iloc[-6])
                    changes_5d[ticker] = ((latest - prev_5d) / prev_5d) * 100
                else:
                    changes_5d[ticker] = 0.0

                # 20-day change
                if len(series) >= 21:
                    prev_20d = float(series.iloc[-21])
                    changes_20d[ticker] = ((latest - prev_20d) / prev_20d) * 100
                else:
                    changes_20d[ticker] = 0.0

            except Exception as e:
                logger.warning(f"Failed to get {ticker} data: {e}")
                prices[ticker] = self.REFERENCE_PRICES.get(ticker, 0.0)
                changes_5d[ticker] = 0.0
                changes_20d[ticker] = 0.0

        ung_price = prices.get("UNG", 0.0)
        lng_price = prices.get("LNG", 0.0)

        # Current ratio
        lng_ung_ratio = lng_price / ung_price if ung_price > 0 else 0.0

        # 5-day ratio change (approximate from individual changes)
        # If UNG was x and LNG was y, ratio was y/x
        # New ratio = y*(1+lng_chg) / (x*(1+ung_chg)) = (y/x) * (1+lng_chg)/(1+ung_chg)
        lng_chg = changes_5d.get("LNG", 0.0) / 100
        ung_chg = changes_5d.get("UNG", 0.0) / 100
        if (1 + ung_chg) != 0:
            ratio_multiplier = (1 + lng_chg) / (1 + ung_chg)
            ratio_change_5d = (ratio_multiplier - 1) * 100
        else:
            ratio_change_5d = 0.0

        has_all = all(prices.get(t, 0) > 0 for t in self.TICKERS)
        quality = "live" if has_all else "delayed"

        return LNGSnapshot(
            timestamp=datetime.now().isoformat(),
            ung_price=round(ung_price, 2),
            lng_price=round(lng_price, 2),
            ung_change_5d=round(changes_5d.get("UNG", 0.0), 2),
            ung_change_20d=round(changes_20d.get("UNG", 0.0), 2),
            lng_change_5d=round(changes_5d.get("LNG", 0.0), 2),
            lng_change_20d=round(changes_20d.get("LNG", 0.0), 2),
            lng_ung_ratio=round(lng_ung_ratio, 2),
            lng_ung_ratio_change_5d=round(ratio_change_5d, 2),
            source="yfinance",
            data_quality=quality,
        )

    def _stale_fallback(self, reason: str) -> LNGSnapshot:
        """Return stale reference prices when live data unavailable."""
        logger.warning(f"Using stale LNG reference prices: {reason}")

        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return LNGSnapshot(**cached)

        return LNGSnapshot(
            timestamp=datetime.now().isoformat(),
            ung_price=self.REFERENCE_PRICES["UNG"],
            lng_price=self.REFERENCE_PRICES["LNG"],
            ung_change_5d=0.0,
            ung_change_20d=0.0,
            lng_change_5d=0.0,
            lng_change_20d=0.0,
            lng_ung_ratio=round(
                self.REFERENCE_PRICES["LNG"] / self.REFERENCE_PRICES["UNG"], 2
            ),
            lng_ung_ratio_change_5d=0.0,
            source="reference",
            data_quality="stale",
        )

    def _save(self, snapshot: LNGSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved LNG snapshot: UNG=${snapshot.ung_price} "
            f"({snapshot.ung_change_5d:+.1f}% 5d), LNG=${snapshot.lng_price} "
            f"({snapshot.lng_change_5d:+.1f}% 5d), ratio={snapshot.lng_ung_ratio:.1f}"
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
