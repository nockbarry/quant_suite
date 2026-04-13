"""Shipping rate data collection.

Collects tanker and dry bulk rate proxies using:
- BDRY ETF: Breakwave Dry Bulk Shipping ETF (Baltic Dry Index proxy)
- FRO, DHT: VLCC tanker stocks as crude tanker rate proxies
- BNO ETF: Brent oil price (tanker demand driver)
- Computed: FRO-BDRY spread, BNO-BDRY ratio (oil vs dry bulk divergence)

Why: Dual chokepoint (Red Sea + Hormuz) compounds shipping costs.
Tanker rates decouple from dry bulk during geopolitical disruptions.
FRO-BDRY spread widening = tanker-specific premium from route disruption.
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
class ShippingSnapshot:
    """Current shipping rate proxy snapshot."""

    timestamp: str
    bdry_price: float  # Breakwave Dry Bulk ETF (Baltic Dry proxy)
    fro_price: float  # Frontline VLCC tanker
    dht_price: float  # DHT Holdings VLCC tanker
    bno_price: float  # Brent oil ETF
    bdry_change_5d: float  # BDRY 5-day % change
    fro_change_5d: float  # FRO 5-day % change
    dht_change_5d: float  # DHT 5-day % change
    bno_change_5d: float  # BNO 5-day % change
    fro_change_20d: float  # FRO 20-day % change
    dht_change_20d: float  # DHT 20-day % change
    tanker_avg_price: float  # Average of FRO + DHT
    tanker_bdry_spread: float  # (tanker avg 5d change) - (BDRY 5d change)
    bno_bdry_ratio: float  # BNO/BDRY (oil vs dry bulk)
    source: str
    data_quality: str  # "live", "delayed", "stale"


class ShippingRateCollector:
    """Collect shipping rate proxy data via yfinance.

    Tanker stocks (FRO, DHT) track VLCC spot rates closely.
    BDRY tracks Baltic Dry Index — dry bulk (iron ore, coal, grain).
    Divergence between tankers and dry bulk signals route-specific disruption.
    """

    TICKERS = ["BDRY", "FRO", "DHT", "BNO"]

    REFERENCE_PRICES = {
        "BDRY": 11.0,
        "FRO": 35.0,
        "DHT": 17.5,
        "BNO": 49.0,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "shipping_rates.json"

    async def collect(self) -> ShippingSnapshot:
        """Collect shipping rate data via yfinance proxies."""
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
            logger.error(f"Shipping rate collection failed: {e}")
            return self._stale_fallback(str(e))

    def _fetch_yfinance(self) -> ShippingSnapshot:
        """Synchronous yfinance fetch — runs in executor."""
        data = yf.download(
            self.TICKERS, period="30d", progress=False, group_by="ticker"
        )

        if data.empty:
            raise ValueError("yfinance returned empty data for shipping tickers")

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

        # Computed metrics
        fro_price = prices.get("FRO", 0.0)
        dht_price = prices.get("DHT", 0.0)
        bdry_price = prices.get("BDRY", 0.0)
        bno_price = prices.get("BNO", 0.0)

        tanker_avg = (fro_price + dht_price) / 2 if (fro_price + dht_price) > 0 else 0
        tanker_avg_5d_chg = (
            changes_5d.get("FRO", 0) + changes_5d.get("DHT", 0)
        ) / 2
        tanker_bdry_spread = tanker_avg_5d_chg - changes_5d.get("BDRY", 0)
        bno_bdry_ratio = bno_price / bdry_price if bdry_price > 0 else 0

        has_all = all(prices.get(t, 0) > 0 for t in self.TICKERS)
        quality = "live" if has_all else "delayed"

        return ShippingSnapshot(
            timestamp=datetime.now().isoformat(),
            bdry_price=round(bdry_price, 2),
            fro_price=round(fro_price, 2),
            dht_price=round(dht_price, 2),
            bno_price=round(bno_price, 2),
            bdry_change_5d=round(changes_5d.get("BDRY", 0.0), 2),
            fro_change_5d=round(changes_5d.get("FRO", 0.0), 2),
            dht_change_5d=round(changes_5d.get("DHT", 0.0), 2),
            bno_change_5d=round(changes_5d.get("BNO", 0.0), 2),
            fro_change_20d=round(changes_20d.get("FRO", 0.0), 2),
            dht_change_20d=round(changes_20d.get("DHT", 0.0), 2),
            tanker_avg_price=round(tanker_avg, 2),
            tanker_bdry_spread=round(tanker_bdry_spread, 2),
            bno_bdry_ratio=round(bno_bdry_ratio, 2),
            source="yfinance",
            data_quality=quality,
        )

    def _stale_fallback(self, reason: str) -> ShippingSnapshot:
        """Return stale reference prices when live data unavailable."""
        logger.warning(f"Using stale shipping reference prices: {reason}")

        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return ShippingSnapshot(**cached)

        return ShippingSnapshot(
            timestamp=datetime.now().isoformat(),
            bdry_price=self.REFERENCE_PRICES["BDRY"],
            fro_price=self.REFERENCE_PRICES["FRO"],
            dht_price=self.REFERENCE_PRICES["DHT"],
            bno_price=self.REFERENCE_PRICES["BNO"],
            bdry_change_5d=0.0,
            fro_change_5d=0.0,
            dht_change_5d=0.0,
            bno_change_5d=0.0,
            fro_change_20d=0.0,
            dht_change_20d=0.0,
            tanker_avg_price=(self.REFERENCE_PRICES["FRO"] + self.REFERENCE_PRICES["DHT"]) / 2,
            tanker_bdry_spread=0.0,
            bno_bdry_ratio=round(
                self.REFERENCE_PRICES["BNO"] / self.REFERENCE_PRICES["BDRY"], 2
            ),
            source="reference",
            data_quality="stale",
        )

    def _save(self, snapshot: ShippingSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved shipping snapshot: BDRY=${snapshot.bdry_price}, "
            f"FRO=${snapshot.fro_price} ({snapshot.fro_change_5d:+.1f}% 5d), "
            f"DHT=${snapshot.dht_price}, tanker-BDRY spread={snapshot.tanker_bdry_spread:+.1f}%"
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
