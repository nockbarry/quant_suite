"""European Gas Storage Levels (GIE AGSI).

Free API showing EU gas storage drawdown in real-time.
Directly validates the LNG Supply Disruption thesis.

Source: https://agsi.gie.eu/api
Docs: https://agsi.gie.eu/data-overview

Fallback: yfinance UNG ETF + historical storage patterns.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

try:
    import yfinance as yf
except ImportError:
    yf = None

from src.core.paths import paths

logger = logging.getLogger(__name__)

# AGSI API endpoints
AGSI_BASE_URL = "https://agsi.gie.eu/api"
AGSI_EU_URL = f"{AGSI_BASE_URL}?type=eu"

# Historical EU gas storage reference (approximate % full by month)
# Used for year-over-year comparison when API unavailable
HISTORICAL_STORAGE_PCT = {
    1: 70, 2: 55, 3: 40, 4: 35, 5: 40, 6: 55,
    7: 65, 8: 75, 9: 85, 10: 90, 11: 85, 12: 78,
}

# EU total working gas capacity (TWh) — approximate
EU_TOTAL_CAPACITY_TWH = 1100

# Average daily consumption in heating season (TWh/day)
AVG_WINTER_CONSUMPTION_TWH_DAY = 7.5
AVG_SUMMER_CONSUMPTION_TWH_DAY = 3.5


@dataclass
class GasStorageSnapshot:
    """European gas storage status."""

    timestamp: str
    eu_storage_pct: float         # % full (0-100)
    storage_volume_twh: float     # Estimated TWh in storage
    injection_withdrawal_gwh: float  # Daily net (positive = injection)
    trend: str                    # "filling", "drawing", "stable"
    yoy_comparison: float         # Difference vs same date last year (pct points)
    days_of_supply_estimate: float  # Estimated days of supply at current consumption
    ung_price: float              # UNG ETF price (nat gas proxy)
    ung_change_5d: float          # UNG 5-day % change
    ttf_proxy: float              # European gas price proxy (via UNG ratio)
    storage_risk: str             # "normal", "low", "critical"
    source: str                   # "agsi", "yfinance_fallback", "reference"
    data_quality: str             # "live", "delayed", "stale"


class EUGasStorageCollector:
    """Collect European gas storage levels.

    Primary: GIE AGSI API (free for EU aggregate data)
    Fallback: yfinance UNG + historical patterns

    EU gas storage is critical for:
    - LNG Supply Disruption thesis (validates demand for LNG)
    - Iran War Energy thesis (Hormuz disruption impacts LNG shipments)
    - Fertilizer Agflation thesis (gas = nitrogen fertilizer input)
    """

    # Reference values for stale fallback
    REFERENCE = {
        "eu_storage_pct": 50.0,
        "ung_price": 14.0,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "eu_gas_storage.json"

    async def collect(self) -> GasStorageSnapshot:
        """Collect EU gas storage data."""
        # Try AGSI API first
        try:
            snapshot = await self._fetch_agsi()
            self._save(snapshot)
            return snapshot
        except Exception as e:
            logger.warning(f"AGSI API failed: {e}, trying yfinance fallback")

        # Fallback to yfinance UNG + historical estimates
        try:
            snapshot = await self._fetch_yfinance_fallback()
            self._save(snapshot)
            return snapshot
        except Exception as e:
            logger.error(f"yfinance fallback also failed: {e}")
            return self._stale_fallback(str(e))

    async def _fetch_agsi(self) -> GasStorageSnapshot:
        """Fetch from GIE AGSI API."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                AGSI_EU_URL,
                headers={
                    "User-Agent": "AthenaTrader/1.0",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        # AGSI returns a list of daily entries
        if isinstance(data, list) and len(data) > 0:
            latest = data[0]
            storage_pct = float(latest.get("full", 0))
            injection = float(latest.get("injection", 0))  # GWh
            withdrawal = float(latest.get("withdrawal", 0))  # GWh
            net_flow = injection - withdrawal

            # Determine trend
            if net_flow > 50:
                trend = "filling"
            elif net_flow < -50:
                trend = "drawing"
            else:
                trend = "stable"

        elif isinstance(data, dict):
            # Sometimes returns dict with 'data' key
            entries = data.get("data", [])
            if entries:
                latest = entries[0]
                storage_pct = float(latest.get("full", latest.get("percentage", 0)))
                net_flow = float(latest.get("netWithdrawal", 0))
                trend = "filling" if net_flow > 0 else "drawing" if net_flow < 0 else "stable"
            else:
                raise ValueError("AGSI returned empty data")
        else:
            raise ValueError(f"Unexpected AGSI response format: {type(data)}")

        # Compute derived metrics
        storage_twh = storage_pct / 100 * EU_TOTAL_CAPACITY_TWH
        now = datetime.now()
        is_winter = now.month in (10, 11, 12, 1, 2, 3)
        daily_consumption = AVG_WINTER_CONSUMPTION_TWH_DAY if is_winter else AVG_SUMMER_CONSUMPTION_TWH_DAY
        days_of_supply = storage_twh / daily_consumption if daily_consumption > 0 else 0

        # Year-over-year
        historical_pct = HISTORICAL_STORAGE_PCT.get(now.month, 60)
        yoy_diff = storage_pct - historical_pct

        # Storage risk assessment
        if storage_pct < 30:
            storage_risk = "critical"
        elif storage_pct < 50 and is_winter:
            storage_risk = "low"
        elif storage_pct < 40:
            storage_risk = "low"
        else:
            storage_risk = "normal"

        # Also fetch UNG for gas price context
        ung_price, ung_chg_5d = await self._get_ung_price()

        return GasStorageSnapshot(
            timestamp=now.isoformat(),
            eu_storage_pct=round(storage_pct, 1),
            storage_volume_twh=round(storage_twh, 0),
            injection_withdrawal_gwh=round(net_flow, 0),
            trend=trend,
            yoy_comparison=round(yoy_diff, 1),
            days_of_supply_estimate=round(days_of_supply, 0),
            ung_price=round(ung_price, 2),
            ung_change_5d=round(ung_chg_5d, 2),
            ttf_proxy=round(ung_price * 3.5, 2),  # rough EUR/MWh proxy
            storage_risk=storage_risk,
            source="agsi",
            data_quality="live",
        )

    async def _fetch_yfinance_fallback(self) -> GasStorageSnapshot:
        """Fallback: estimate storage from UNG + historical patterns."""
        if yf is None:
            raise ValueError("yfinance not installed")

        ung_price, ung_chg_5d = await self._get_ung_price()
        if ung_price == 0:
            raise ValueError("Could not get UNG price")

        now = datetime.now()
        # Estimate storage from historical pattern
        base_storage = HISTORICAL_STORAGE_PCT.get(now.month, 60)

        # Adjust for gas price: higher UNG = lower storage (inverse)
        # If UNG is above ~14 (reference), storage likely lower
        ung_ref = self.REFERENCE["ung_price"]
        price_adj = -(ung_price - ung_ref) / ung_ref * 10  # rough adjustment
        estimated_storage = max(10, min(100, base_storage + price_adj))

        storage_twh = estimated_storage / 100 * EU_TOTAL_CAPACITY_TWH
        is_winter = now.month in (10, 11, 12, 1, 2, 3)
        daily_consumption = AVG_WINTER_CONSUMPTION_TWH_DAY if is_winter else AVG_SUMMER_CONSUMPTION_TWH_DAY
        days_of_supply = storage_twh / daily_consumption if daily_consumption > 0 else 0

        yoy_diff = estimated_storage - base_storage

        if estimated_storage < 30:
            storage_risk = "critical"
        elif estimated_storage < 50 and is_winter:
            storage_risk = "low"
        else:
            storage_risk = "normal"

        return GasStorageSnapshot(
            timestamp=now.isoformat(),
            eu_storage_pct=round(estimated_storage, 1),
            storage_volume_twh=round(storage_twh, 0),
            injection_withdrawal_gwh=0.0,  # Can't estimate from price
            trend="unknown",
            yoy_comparison=round(yoy_diff, 1),
            days_of_supply_estimate=round(days_of_supply, 0),
            ung_price=round(ung_price, 2),
            ung_change_5d=round(ung_chg_5d, 2),
            ttf_proxy=round(ung_price * 3.5, 2),
            storage_risk=storage_risk,
            source="yfinance_fallback",
            data_quality="delayed",
        )

    async def _get_ung_price(self) -> tuple[float, float]:
        """Get UNG ETF price and 5d change."""
        if yf is None:
            return 0.0, 0.0

        def _fetch():
            try:
                data = yf.download("UNG", period="10d", progress=False)
                if data.empty:
                    return 0.0, 0.0
                series = data["Close"].dropna()
                latest = float(series.iloc[-1])
                chg = 0.0
                if len(series) >= 6:
                    prev = float(series.iloc[-6])
                    chg = ((latest - prev) / prev) * 100 if prev > 0 else 0.0
                return latest, chg
            except Exception:
                return 0.0, 0.0

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    def _stale_fallback(self, reason: str) -> GasStorageSnapshot:
        """Return stale reference data."""
        logger.warning(f"Using stale EU gas storage reference: {reason}")

        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return GasStorageSnapshot(**cached)

        now = datetime.now()
        ref_storage = HISTORICAL_STORAGE_PCT.get(now.month, 60)

        return GasStorageSnapshot(
            timestamp=now.isoformat(),
            eu_storage_pct=float(ref_storage),
            storage_volume_twh=round(ref_storage / 100 * EU_TOTAL_CAPACITY_TWH, 0),
            injection_withdrawal_gwh=0.0,
            trend="unknown",
            yoy_comparison=0.0,
            days_of_supply_estimate=0.0,
            ung_price=self.REFERENCE["ung_price"],
            ung_change_5d=0.0,
            ttf_proxy=round(self.REFERENCE["ung_price"] * 3.5, 2),
            storage_risk="normal",
            source="reference",
            data_quality="stale",
        )

    def _save(self, snapshot: GasStorageSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved EU gas storage: {snapshot.eu_storage_pct}% full, "
            f"trend={snapshot.trend}, risk={snapshot.storage_risk}, "
            f"UNG=${snapshot.ung_price} ({snapshot.ung_change_5d:+.1f}% 5d)"
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
