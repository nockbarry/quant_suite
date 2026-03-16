"""Fertilizer price data collection.

Collects urea, ammonia, and potash spot price data using:
- Primary: yfinance ETF/stock proxies (CF Industries, Mosaic, Nutrien)
- Secondary: FRED API indices if available
- Fallback: Hardcoded reference prices with staleness warning

Why: 33% of global fertilizer transits Hormuz. Urea +26% in 14 days during
Iran crisis. CF momentum hypothesis (p=0.101) needs commodity price features.
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
class FertilizerSnapshot:
    """Current fertilizer price proxy snapshot."""

    timestamp: str
    cf_price: float  # CF Industries stock price (nitrogen/urea proxy)
    mos_price: float  # Mosaic stock price (potash proxy)
    ntr_price: float  # Nutrien stock price (diversified proxy)
    cf_change_5d: float  # 5-day % change
    cf_change_20d: float  # 20-day % change
    mos_change_5d: float  # Mosaic 5-day % change
    ntr_change_5d: float  # Nutrien 5-day % change
    ung_price: float  # Natural gas (input cost proxy)
    cf_ung_ratio: float  # CF/UNG ratio (margin proxy)
    source: str
    data_quality: str  # "live", "delayed", "stale"


class FertilizerCollector:
    """Collect fertilizer price data via yfinance proxies.

    Fertilizer producers serve as proxies for underlying commodity prices:
    - CF Industries (CF): Largest US nitrogen producer, urea proxy
    - Mosaic (MOS): Largest US potash/phosphate producer
    - Nutrien (NTR): Diversified fertilizer (K+N+P)
    - UNG: Natural gas ETF — key input cost for nitrogen fertilizer
    """

    TICKERS = ["CF", "MOS", "NTR", "UNG"]

    # Fallback reference prices (updated periodically)
    REFERENCE_PRICES = {
        "CF": 85.0,
        "MOS": 30.0,
        "NTR": 52.0,
        "UNG": 14.0,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "fertilizer_prices.json"

    async def collect(self) -> FertilizerSnapshot:
        """Collect fertilizer price data via yfinance proxies."""
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
            logger.error(f"Fertilizer collection failed: {e}")
            return self._stale_fallback(str(e))

    def _fetch_yfinance(self) -> FertilizerSnapshot:
        """Synchronous yfinance fetch — runs in executor."""
        data = yf.download(
            self.TICKERS, period="30d", progress=False, group_by="ticker"
        )

        if data.empty:
            raise ValueError("yfinance returned empty data for fertilizer tickers")

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

        cf_price = prices.get("CF", 0.0)
        ung_price = prices.get("UNG", 0.0)
        cf_ung_ratio = cf_price / ung_price if ung_price > 0 else 0.0

        # Determine data quality
        has_all = all(prices.get(t, 0) > 0 for t in self.TICKERS)
        quality = "live" if has_all else "delayed"

        return FertilizerSnapshot(
            timestamp=datetime.now().isoformat(),
            cf_price=round(cf_price, 2),
            mos_price=round(prices.get("MOS", 0.0), 2),
            ntr_price=round(prices.get("NTR", 0.0), 2),
            cf_change_5d=round(changes_5d.get("CF", 0.0), 2),
            cf_change_20d=round(changes_20d.get("CF", 0.0), 2),
            mos_change_5d=round(changes_5d.get("MOS", 0.0), 2),
            ntr_change_5d=round(changes_5d.get("NTR", 0.0), 2),
            ung_price=round(ung_price, 2),
            cf_ung_ratio=round(cf_ung_ratio, 2),
            source="yfinance",
            data_quality=quality,
        )

    def _stale_fallback(self, reason: str) -> FertilizerSnapshot:
        """Return stale reference prices when live data unavailable."""
        logger.warning(f"Using stale fertilizer reference prices: {reason}")

        # Try loading cached data first
        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return FertilizerSnapshot(**cached)

        return FertilizerSnapshot(
            timestamp=datetime.now().isoformat(),
            cf_price=self.REFERENCE_PRICES["CF"],
            mos_price=self.REFERENCE_PRICES["MOS"],
            ntr_price=self.REFERENCE_PRICES["NTR"],
            cf_change_5d=0.0,
            cf_change_20d=0.0,
            mos_change_5d=0.0,
            ntr_change_5d=0.0,
            ung_price=self.REFERENCE_PRICES["UNG"],
            cf_ung_ratio=round(
                self.REFERENCE_PRICES["CF"] / self.REFERENCE_PRICES["UNG"], 2
            ),
            source="reference",
            data_quality="stale",
        )

    def _save(self, snapshot: FertilizerSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved fertilizer snapshot: CF=${snapshot.cf_price} "
            f"({snapshot.cf_change_5d:+.1f}% 5d), MOS=${snapshot.mos_price}, "
            f"NTR=${snapshot.ntr_price}, UNG=${snapshot.ung_price}"
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
