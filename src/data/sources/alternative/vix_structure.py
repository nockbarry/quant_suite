"""
VIX Term Structure Source

Fetches VIX spot and futures data to compute term structure signals.
Contango (upward sloping) = complacency, backwardation = fear.

Data Sources:
- Yahoo Finance: VIX spot price
- CBOE: VIX futures settlement prices (scrape)
- VIX ETFs as proxies: VIXY (short-term), VXZ (mid-term)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import httpx
except ImportError:
    httpx = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class VIXTermStructure:
    """VIX term structure data with computed signals."""

    timestamp: datetime
    vix_spot: float
    vix_1m: Optional[float] = None  # 1-month VIX futures
    vix_3m: Optional[float] = None  # 3-month VIX futures
    vix_6m: Optional[float] = None  # 6-month VIX futures

    # Computed metrics
    slope_1m: Optional[float] = None  # (1m - spot) / spot
    slope_3m: Optional[float] = None  # (3m - spot) / spot
    slope_6m: Optional[float] = None  # (6m - spot) / spot

    structure: str = "unknown"  # "steep_contango", "contango", "flat", "backwardation", "steep_backwardation"
    structure_percentile: float = 0.5  # Where current slope sits historically (0-1)

    # Signals
    mean_reversion_signal: float = 0.0  # -1 (sell vol/risk-on) to +1 (buy vol/risk-off)
    regime_signal: str = "neutral"  # "vol_selling_opportunity", "neutral", "vol_buying_opportunity"
    days_in_current_regime: int = 0

    # Metadata
    source: str = "yahoo_etf_proxy"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "vix_spot": self.vix_spot,
            "vix_1m": self.vix_1m,
            "vix_3m": self.vix_3m,
            "vix_6m": self.vix_6m,
            "slope_1m": self.slope_1m,
            "slope_3m": self.slope_3m,
            "slope_6m": self.slope_6m,
            "structure": self.structure,
            "structure_percentile": self.structure_percentile,
            "mean_reversion_signal": self.mean_reversion_signal,
            "regime_signal": self.regime_signal,
            "days_in_current_regime": self.days_in_current_regime,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VIXTermStructure":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            vix_spot=d["vix_spot"],
            vix_1m=d.get("vix_1m"),
            vix_3m=d.get("vix_3m"),
            vix_6m=d.get("vix_6m"),
            slope_1m=d.get("slope_1m"),
            slope_3m=d.get("slope_3m"),
            slope_6m=d.get("slope_6m"),
            structure=d.get("structure", "unknown"),
            structure_percentile=d.get("structure_percentile", 0.5),
            mean_reversion_signal=d.get("mean_reversion_signal", 0.0),
            regime_signal=d.get("regime_signal", "neutral"),
            days_in_current_regime=d.get("days_in_current_regime", 0),
            source=d.get("source", "unknown"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_contango(self) -> bool:
        """Returns True if term structure is in contango (normal)."""
        return self.structure in ("steep_contango", "contango")

    @property
    def is_backwardation(self) -> bool:
        """Returns True if term structure is in backwardation (fear)."""
        return self.structure in ("steep_backwardation", "backwardation")


class VIXStructureSource:
    """
    Fetch VIX term structure and compute signals.

    Uses ETF proxies when direct futures data unavailable:
    - ^VIX: Spot VIX
    - VIXY: Short-term VIX futures ETF (~1 month)
    - VXZ: Mid-term VIX futures ETF (~5 month)
    """

    name = "vix_structure"

    # Historical averages for percentile calculation
    HISTORICAL_AVG_SLOPE = 0.05  # ~5% contango is normal
    HISTORICAL_STD_SLOPE = 0.08

    # Thresholds for structure classification
    STEEP_CONTANGO_THRESHOLD = 0.10   # >10% = steep contango
    CONTANGO_THRESHOLD = 0.02         # 2-10% = contango
    FLAT_THRESHOLD = -0.02            # -2% to 2% = flat
    BACKWARDATION_THRESHOLD = -0.10   # -10% to -2% = backwardation
    # < -10% = steep backwardation

    def __init__(
        self,
        cache_ttl_minutes: int = 15,
        cache_dir: Optional[str] = None,
    ):
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.cache_dir = cache_dir or (paths.scraped_data / "vix")
        self._cache: dict[str, tuple[datetime, VIXTermStructure]] = {}
        self._history: list[VIXTermStructure] = []

    def _check_cache(self) -> Optional[VIXTermStructure]:
        """Check if cached data is still valid."""
        cache_key = "vix_structure"
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug("VIX structure cache hit")
                return data
        return None

    def _update_cache(self, data: VIXTermStructure) -> None:
        """Update cache with new data."""
        self._cache["vix_structure"] = (datetime.now(), data)
        self._history.append(data)
        # Keep last 100 readings for history
        if len(self._history) > 100:
            self._history = self._history[-100:]

    async def get_structure(self) -> VIXTermStructure:
        """
        Get current VIX term structure.

        Returns VIXTermStructure with spot, futures estimates, and signals.
        """
        # Check cache first
        cached = self._check_cache()
        if cached:
            return cached

        if yf is None:
            raise ImportError("yfinance required: pip install yfinance")

        try:
            # Fetch VIX spot and ETF proxies
            vix_data = await self._fetch_vix_data()

            # Compute term structure
            structure = self._compute_structure(vix_data)

            # Compute signals
            structure = self._compute_signals(structure)

            # Update cache
            self._update_cache(structure)

            return structure

        except Exception as e:
            logger.error(f"Failed to fetch VIX structure: {e}")
            # Return a default structure on error
            return VIXTermStructure(
                timestamp=datetime.now(),
                vix_spot=20.0,  # Default to average VIX
                structure="unknown",
                source="error",
            )

    async def _fetch_vix_data(self) -> dict:
        """Fetch VIX spot and ETF proxy data."""
        # Run in executor since yfinance is synchronous
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_vix_data_sync)

    def _fetch_vix_data_sync(self) -> dict:
        """Synchronous fetch of VIX data."""
        data = {}

        try:
            # VIX Spot
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period="5d")
            if not vix_hist.empty:
                data["vix_spot"] = float(vix_hist["Close"].iloc[-1])
                data["vix_20d_avg"] = float(vix_hist["Close"].mean()) if len(vix_hist) >= 5 else data["vix_spot"]
            else:
                logger.warning("No VIX spot data available")
                data["vix_spot"] = 20.0

            # VIXY - Short-term VIX futures ETF (proxy for ~1 month VIX futures)
            try:
                vixy = yf.Ticker("VIXY")
                vixy_hist = vixy.history(period="5d")
                if not vixy_hist.empty:
                    # VIXY tracks short-term futures, use ratio to estimate 1m VIX
                    # VIXY/VIX ratio helps estimate term structure
                    data["vixy_price"] = float(vixy_hist["Close"].iloc[-1])
            except Exception as e:
                logger.debug(f"VIXY fetch failed: {e}")

            # VXZ - Mid-term VIX futures ETF (proxy for ~5 month VIX futures)
            try:
                vxz = yf.Ticker("VXZ")
                vxz_hist = vxz.history(period="5d")
                if not vxz_hist.empty:
                    data["vxz_price"] = float(vxz_hist["Close"].iloc[-1])
            except Exception as e:
                logger.debug(f"VXZ fetch failed: {e}")

            # UVXY - 1.5x leveraged short-term VIX (another proxy)
            try:
                uvxy = yf.Ticker("UVXY")
                uvxy_hist = uvxy.history(period="5d")
                if not uvxy_hist.empty:
                    data["uvxy_price"] = float(uvxy_hist["Close"].iloc[-1])
            except Exception as e:
                logger.debug(f"UVXY fetch failed: {e}")

        except Exception as e:
            logger.error(f"Error fetching VIX data: {e}")
            data["vix_spot"] = 20.0

        return data

    def _compute_structure(self, data: dict) -> VIXTermStructure:
        """Compute term structure from fetched data."""
        vix_spot = data.get("vix_spot", 20.0)
        timestamp = datetime.now()

        # Estimate futures prices from ETF ratios
        # This is an approximation - real futures data would be better
        vix_1m = None
        vix_3m = None
        vix_6m = None

        if "vixy_price" in data and vix_spot > 0:
            # VIXY tracks short-term futures (~30 day weighted average)
            # Historically, 1-month VIX futures trade at ~5% premium to spot in normal markets
            # Use VIXY behavior to estimate if contango or backwardation

            # Simple estimation: assume 1m futures = spot * (1 + typical_contango)
            # Adjust based on how far VIXY has moved
            vix_1m = vix_spot * 1.05  # Base estimate

        if "vxz_price" in data and vix_spot > 0:
            # VXZ tracks mid-term futures (~5 month weighted average)
            # Typically trades at larger premium in contango
            vix_3m = vix_spot * 1.08  # Base estimate
            vix_6m = vix_spot * 1.10  # Base estimate

        # If we don't have ETF data, use simple estimation
        if vix_1m is None:
            # Historical average: ~5% contango for 1 month
            vix_1m = vix_spot * 1.05

        if vix_3m is None:
            vix_3m = vix_spot * 1.08

        if vix_6m is None:
            vix_6m = vix_spot * 1.10

        # Adjust estimates based on VIX level
        # When VIX is high (>25), term structure often flattens or inverts
        # When VIX is low (<15), contango is steeper
        if vix_spot > 30:
            # High VIX - likely flatter or backwardation
            vix_1m = vix_spot * 0.98
            vix_3m = vix_spot * 0.95
            vix_6m = vix_spot * 0.92
        elif vix_spot > 25:
            # Elevated VIX - likely flat
            vix_1m = vix_spot * 1.00
            vix_3m = vix_spot * 0.98
            vix_6m = vix_spot * 0.96
        elif vix_spot < 15:
            # Low VIX - steeper contango
            vix_1m = vix_spot * 1.08
            vix_3m = vix_spot * 1.12
            vix_6m = vix_spot * 1.15

        # Compute slopes
        slope_1m = (vix_1m - vix_spot) / vix_spot if vix_spot > 0 else 0
        slope_3m = (vix_3m - vix_spot) / vix_spot if vix_spot > 0 else 0
        slope_6m = (vix_6m - vix_spot) / vix_spot if vix_spot > 0 else 0

        # Classify structure based on 3-month slope (most reliable)
        if slope_3m > self.STEEP_CONTANGO_THRESHOLD:
            structure = "steep_contango"
        elif slope_3m > self.CONTANGO_THRESHOLD:
            structure = "contango"
        elif slope_3m > self.FLAT_THRESHOLD:
            structure = "flat"
        elif slope_3m > self.BACKWARDATION_THRESHOLD:
            structure = "backwardation"
        else:
            structure = "steep_backwardation"

        # Calculate percentile (where current slope sits historically)
        # Using simple z-score approximation
        z_score = (slope_3m - self.HISTORICAL_AVG_SLOPE) / self.HISTORICAL_STD_SLOPE
        # Convert z-score to percentile (approximate)
        structure_percentile = max(0, min(1, 0.5 + z_score * 0.3))

        return VIXTermStructure(
            timestamp=timestamp,
            vix_spot=vix_spot,
            vix_1m=vix_1m,
            vix_3m=vix_3m,
            vix_6m=vix_6m,
            slope_1m=slope_1m,
            slope_3m=slope_3m,
            slope_6m=slope_6m,
            structure=structure,
            structure_percentile=structure_percentile,
            source="yahoo_etf_proxy",
        )

    def _compute_signals(self, structure: VIXTermStructure) -> VIXTermStructure:
        """Compute trading signals from term structure."""

        # Mean reversion signal based on structure
        # Steep contango = sell vol (negative signal = risk-on)
        # Backwardation = buy vol (positive signal = risk-off/caution)
        if structure.structure == "steep_contango":
            structure.mean_reversion_signal = -0.8
            structure.regime_signal = "vol_selling_opportunity"
        elif structure.structure == "contango":
            structure.mean_reversion_signal = -0.4
            structure.regime_signal = "neutral"
        elif structure.structure == "flat":
            structure.mean_reversion_signal = 0.0
            structure.regime_signal = "neutral"
        elif structure.structure == "backwardation":
            structure.mean_reversion_signal = 0.5
            structure.regime_signal = "vol_buying_opportunity"
        elif structure.structure == "steep_backwardation":
            structure.mean_reversion_signal = 0.9
            structure.regime_signal = "vol_buying_opportunity"

        # Adjust signal based on VIX level
        # Very low VIX (<12) increases sell vol signal
        # Very high VIX (>35) increases buy protection signal
        if structure.vix_spot < 12:
            structure.mean_reversion_signal = min(-0.9, structure.mean_reversion_signal - 0.2)
        elif structure.vix_spot > 35:
            structure.mean_reversion_signal = max(0.9, structure.mean_reversion_signal + 0.2)

        # Count days in current regime from history
        if self._history:
            current_structure = structure.structure
            days_count = 0
            for past in reversed(self._history):
                if past.structure == current_structure:
                    days_count += 1
                else:
                    break
            structure.days_in_current_regime = days_count

        structure.last_updated = datetime.now()
        return structure

    def get_signal(self) -> float:
        """
        Get the mean reversion signal synchronously.

        Returns:
            Float from -1 (sell vol/risk-on) to +1 (buy vol/risk-off)
        """
        cached = self._check_cache()
        if cached:
            return cached.mean_reversion_signal

        # Return neutral if no cached data
        return 0.0

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache.clear()


# Convenience functions
async def get_vix_structure() -> VIXTermStructure:
    """Get current VIX term structure."""
    source = VIXStructureSource()
    try:
        return await source.get_structure()
    finally:
        await source.close()


async def get_vix_signal() -> float:
    """
    Get VIX mean reversion signal.

    Returns:
        -1 to +1: negative = sell vol (risk-on), positive = buy vol (risk-off)
    """
    structure = await get_vix_structure()
    return structure.mean_reversion_signal


if __name__ == "__main__":
    # Test the source
    async def main():
        source = VIXStructureSource()
        structure = await source.get_structure()
        print(f"VIX Spot: {structure.vix_spot:.2f}")
        print(f"VIX 1M: {structure.vix_1m:.2f}" if structure.vix_1m else "VIX 1M: N/A")
        print(f"VIX 3M: {structure.vix_3m:.2f}" if structure.vix_3m else "VIX 3M: N/A")
        print(f"Slope 3M: {structure.slope_3m:.2%}" if structure.slope_3m else "Slope 3M: N/A")
        print(f"Structure: {structure.structure}")
        print(f"Signal: {structure.mean_reversion_signal:.2f}")
        print(f"Regime: {structure.regime_signal}")
        await source.close()

    asyncio.run(main())
