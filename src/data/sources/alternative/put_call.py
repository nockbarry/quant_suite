"""
Put/Call Ratio Source

Fetches put/call ratio data for sentiment analysis.
High put/call = fear (contrarian buy signal)
Low put/call = greed (contrarian sell signal)

Data Sources:
- Yahoo Finance: Options volume for SPY, QQQ
- CBOE: Total equity/index put/call ratios (if available)
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

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Historical thresholds for put/call ratio interpretation
# Based on CBOE equity put/call ratio historical data
PC_EXTREME_FEAR = 1.20      # Very high - extreme fear
PC_FEAR = 0.95              # High - fear
PC_NEUTRAL_HIGH = 0.75      # Upper neutral
PC_NEUTRAL_LOW = 0.55       # Lower neutral
PC_GREED = 0.45             # Low - greed
PC_EXTREME_GREED = 0.35     # Very low - extreme greed

# Historical average is around 0.60-0.65 for equity P/C


@dataclass
class PutCallData:
    """Put/Call ratio data with computed signals."""

    timestamp: datetime

    # Raw ratios
    total_ratio: float              # Overall put/call ratio
    equity_ratio: Optional[float] = None   # Equity-only P/C
    index_ratio: Optional[float] = None    # Index-only P/C

    # Volume data
    total_put_volume: int = 0
    total_call_volume: int = 0

    # Per-symbol ratios
    spy_ratio: Optional[float] = None
    qqq_ratio: Optional[float] = None
    iwm_ratio: Optional[float] = None

    # Historical context
    ratio_5d_avg: Optional[float] = None
    ratio_20d_avg: Optional[float] = None
    percentile_30d: float = 0.5     # Where current ratio sits in 30-day range

    # Signals
    signal: str = "neutral"         # "extreme_fear", "fear", "neutral", "greed", "extreme_greed"
    contrarian_signal: float = 0.0  # -1 (contrarian sell) to +1 (contrarian buy)
    signal_strength: float = 0.0    # 0 to 1

    # Metadata
    source: str = "yahoo_options"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_ratio": self.total_ratio,
            "equity_ratio": self.equity_ratio,
            "index_ratio": self.index_ratio,
            "total_put_volume": self.total_put_volume,
            "total_call_volume": self.total_call_volume,
            "spy_ratio": self.spy_ratio,
            "qqq_ratio": self.qqq_ratio,
            "iwm_ratio": self.iwm_ratio,
            "ratio_5d_avg": self.ratio_5d_avg,
            "ratio_20d_avg": self.ratio_20d_avg,
            "percentile_30d": self.percentile_30d,
            "signal": self.signal,
            "contrarian_signal": self.contrarian_signal,
            "signal_strength": self.signal_strength,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PutCallData":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            total_ratio=d["total_ratio"],
            equity_ratio=d.get("equity_ratio"),
            index_ratio=d.get("index_ratio"),
            total_put_volume=d.get("total_put_volume", 0),
            total_call_volume=d.get("total_call_volume", 0),
            spy_ratio=d.get("spy_ratio"),
            qqq_ratio=d.get("qqq_ratio"),
            iwm_ratio=d.get("iwm_ratio"),
            ratio_5d_avg=d.get("ratio_5d_avg"),
            ratio_20d_avg=d.get("ratio_20d_avg"),
            percentile_30d=d.get("percentile_30d", 0.5),
            signal=d.get("signal", "neutral"),
            contrarian_signal=d.get("contrarian_signal", 0.0),
            signal_strength=d.get("signal_strength", 0.0),
            source=d.get("source", "unknown"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )

    @property
    def is_extreme(self) -> bool:
        """Returns True if at extreme fear or greed levels."""
        return self.signal in ("extreme_fear", "extreme_greed")


class PutCallSource:
    """
    Fetch put/call ratio data from options markets.

    Uses Yahoo Finance options data for SPY, QQQ, IWM to calculate
    aggregate put/call ratios.
    """

    name = "put_call"

    # Symbols to analyze for aggregate P/C ratio
    SYMBOLS = ["SPY", "QQQ", "IWM"]

    # Weights for aggregate ratio (SPY most important)
    WEIGHTS = {"SPY": 0.5, "QQQ": 0.3, "IWM": 0.2}

    def __init__(
        self,
        cache_ttl_minutes: int = 60,
        cache_dir: Optional[str] = None,
    ):
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.cache_dir = cache_dir or (paths.scraped_data / "put_call")
        self._cache: dict[str, tuple[datetime, PutCallData]] = {}
        self._history: list[float] = []  # Historical ratios for percentile

    def _check_cache(self) -> Optional[PutCallData]:
        """Check if cached data is still valid."""
        cache_key = "put_call"
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug("Put/Call cache hit")
                return data
        return None

    def _update_cache(self, data: PutCallData) -> None:
        """Update cache with new data."""
        self._cache["put_call"] = (datetime.now(), data)
        self._history.append(data.total_ratio)
        # Keep last 30 readings for percentile
        if len(self._history) > 30:
            self._history = self._history[-30:]

    async def get_put_call(self, force_refresh: bool = False) -> PutCallData:
        """
        Get current put/call ratio data.

        Returns PutCallData with ratios and signals.
        """
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        if yf is None:
            raise ImportError("yfinance required: pip install yfinance")

        try:
            # Fetch options data for key ETFs
            ratios = await self._fetch_options_ratios()

            # Compute aggregate ratio
            data = self._compute_aggregate(ratios)

            # Compute signals
            data = self._compute_signals(data)

            # Update cache
            self._update_cache(data)

            return data

        except Exception as e:
            logger.error(f"Failed to fetch put/call data: {e}")
            # Return default on error
            return PutCallData(
                timestamp=datetime.now(),
                total_ratio=0.65,  # Historical average
                signal="neutral",
                source="error",
            )

    async def _fetch_options_ratios(self) -> dict:
        """Fetch options volume data for each symbol."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_options_ratios_sync)

    def _fetch_options_ratios_sync(self) -> dict:
        """Synchronous fetch of options data."""
        ratios = {}

        for symbol in self.SYMBOLS:
            try:
                ticker = yf.Ticker(symbol)

                # Get all expiration dates
                expirations = ticker.options
                if not expirations:
                    logger.warning(f"No options data for {symbol}")
                    continue

                total_put_vol = 0
                total_call_vol = 0

                # Get options for nearest 3 expirations (most liquid)
                for exp_date in expirations[:3]:
                    try:
                        chain = ticker.option_chain(exp_date)

                        # Sum put and call volumes
                        if hasattr(chain, 'puts') and not chain.puts.empty:
                            put_vol = chain.puts['volume'].sum()
                            if pd.notna(put_vol):
                                total_put_vol += int(put_vol)

                        if hasattr(chain, 'calls') and not chain.calls.empty:
                            call_vol = chain.calls['volume'].sum()
                            if pd.notna(call_vol):
                                total_call_vol += int(call_vol)

                    except Exception as e:
                        logger.debug(f"Error fetching {symbol} {exp_date}: {e}")
                        continue

                if total_call_vol > 0:
                    ratio = total_put_vol / total_call_vol
                    ratios[symbol] = {
                        "ratio": ratio,
                        "put_volume": total_put_vol,
                        "call_volume": total_call_vol,
                    }
                    logger.debug(f"{symbol} P/C ratio: {ratio:.2f}")

            except Exception as e:
                logger.warning(f"Failed to fetch options for {symbol}: {e}")
                continue

        return ratios

    def _compute_aggregate(self, ratios: dict) -> PutCallData:
        """Compute aggregate put/call ratio from individual symbols."""
        timestamp = datetime.now()

        if not ratios:
            return PutCallData(
                timestamp=timestamp,
                total_ratio=0.65,
                source="no_data",
            )

        # Weighted average ratio
        weighted_sum = 0.0
        weight_total = 0.0
        total_put_vol = 0
        total_call_vol = 0

        spy_ratio = None
        qqq_ratio = None
        iwm_ratio = None

        for symbol, data in ratios.items():
            ratio = data["ratio"]
            weight = self.WEIGHTS.get(symbol, 0.1)

            weighted_sum += ratio * weight
            weight_total += weight
            total_put_vol += data["put_volume"]
            total_call_vol += data["call_volume"]

            if symbol == "SPY":
                spy_ratio = ratio
            elif symbol == "QQQ":
                qqq_ratio = ratio
            elif symbol == "IWM":
                iwm_ratio = ratio

        total_ratio = weighted_sum / weight_total if weight_total > 0 else 0.65

        # Calculate percentile from history
        percentile = 0.5
        if self._history:
            sorted_history = sorted(self._history)
            position = sum(1 for r in sorted_history if r < total_ratio)
            percentile = position / len(sorted_history)

        return PutCallData(
            timestamp=timestamp,
            total_ratio=total_ratio,
            total_put_volume=total_put_vol,
            total_call_volume=total_call_vol,
            spy_ratio=spy_ratio,
            qqq_ratio=qqq_ratio,
            iwm_ratio=iwm_ratio,
            percentile_30d=percentile,
            source="yahoo_options",
        )

    def _compute_signals(self, data: PutCallData) -> PutCallData:
        """Compute sentiment signals from put/call ratio."""
        ratio = data.total_ratio

        # Classify signal level
        if ratio >= PC_EXTREME_FEAR:
            data.signal = "extreme_fear"
            data.contrarian_signal = 0.9  # Strong contrarian buy
            data.signal_strength = min(1.0, (ratio - PC_EXTREME_FEAR) / 0.3 + 0.7)
        elif ratio >= PC_FEAR:
            data.signal = "fear"
            data.contrarian_signal = 0.5  # Moderate contrarian buy
            data.signal_strength = (ratio - PC_FEAR) / (PC_EXTREME_FEAR - PC_FEAR) * 0.3 + 0.4
        elif ratio >= PC_NEUTRAL_LOW:
            data.signal = "neutral"
            data.contrarian_signal = 0.0
            data.signal_strength = 0.0
        elif ratio >= PC_GREED:
            data.signal = "greed"
            data.contrarian_signal = -0.5  # Moderate contrarian sell
            data.signal_strength = (PC_NEUTRAL_LOW - ratio) / (PC_NEUTRAL_LOW - PC_GREED) * 0.3 + 0.4
        else:
            data.signal = "extreme_greed"
            data.contrarian_signal = -0.9  # Strong contrarian sell
            data.signal_strength = min(1.0, (PC_GREED - ratio) / 0.15 + 0.7)

        data.last_updated = datetime.now()
        return data

    def get_signal(self) -> float:
        """
        Get the contrarian signal synchronously.

        Returns:
            Float from -1 (contrarian sell/greed) to +1 (contrarian buy/fear)
        """
        cached = self._check_cache()
        if cached:
            return cached.contrarian_signal
        return 0.0

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache.clear()


# Convenience functions
async def get_put_call_data() -> PutCallData:
    """Get current put/call ratio data."""
    source = PutCallSource()
    try:
        return await source.get_put_call()
    finally:
        await source.close()


async def get_put_call_signal() -> float:
    """
    Get put/call contrarian signal.

    Returns:
        -1 to +1: negative = greed (contrarian sell), positive = fear (contrarian buy)
    """
    data = await get_put_call_data()
    return data.contrarian_signal


if __name__ == "__main__":
    # Test the source
    async def main():
        source = PutCallSource()
        data = await source.get_put_call()
        print(f"Timestamp: {data.timestamp}")
        print(f"Total P/C Ratio: {data.total_ratio:.2f}")
        print(f"SPY P/C: {data.spy_ratio:.2f}" if data.spy_ratio else "SPY P/C: N/A")
        print(f"QQQ P/C: {data.qqq_ratio:.2f}" if data.qqq_ratio else "QQQ P/C: N/A")
        print(f"IWM P/C: {data.iwm_ratio:.2f}" if data.iwm_ratio else "IWM P/C: N/A")
        print(f"Put Volume: {data.total_put_volume:,}")
        print(f"Call Volume: {data.total_call_volume:,}")
        print(f"Signal: {data.signal}")
        print(f"Contrarian Signal: {data.contrarian_signal:.2f}")
        print(f"Signal Strength: {data.signal_strength:.2f}")
        await source.close()

    asyncio.run(main())
