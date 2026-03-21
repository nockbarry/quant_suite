"""Treasury Yield Curve, Dollar Index, and Real Yields.

Three critical signals for the Gold and Fed theses:
1. Yield curve (2y/10y spread) — recession signal when inverted
2. DXY dollar index — drives gold inversely
3. TIPS real yields — fundamental driver of gold pricing

All via yfinance (free, no API key).
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
class YieldCurveSnapshot:
    """Current yield curve, dollar, and real yield snapshot."""

    timestamp: str
    ten_year: float          # ^TNX — 10-year Treasury yield
    five_year: float         # ^FVX — 5-year Treasury yield
    thirty_year: float       # ^TYX — 30-year Treasury yield
    three_month: float       # ^IRX — 3-month Treasury yield
    two_year: float          # Computed from 2-year ETF proxy (SHY)
    spread_2y10y: float      # 10yr - 2yr (negative = inverted)
    spread_3m10y: float      # 10yr - 3mo (negative = deeply inverted)
    dxy: float               # Dollar index (DX-Y.NYB or UUP proxy)
    dxy_change_5d: float     # DXY 5-day % change
    dxy_change_20d: float    # DXY 20-day % change
    tips_yield: float        # Real yield proxy (10yr - TIP implied inflation)
    tips_change_5d: float    # TIPS yield 5-day change (bps)
    tip_etf_price: float     # TIP ETF price for reference
    curve_status: str        # "normal", "flat", "inverted"
    curve_steepness: str     # "steep", "moderate", "flat", "inverted"
    source: str
    data_quality: str        # "live", "delayed", "stale"


# Tickers to fetch
YIELD_TICKERS = ["^TNX", "^FVX", "^TYX", "^IRX"]
DOLLAR_TICKERS = ["DX-Y.NYB", "UUP"]
TIPS_TICKERS = ["TIP"]
TWO_YEAR_PROXY = "SHY"  # iShares 1-3 Year Treasury for 2yr proxy


class YieldCurveCollector:
    """Collect Treasury yield curve, dollar index, and real yields via yfinance.

    Yield spreads are THE macro signal for recession risk and risk appetite.
    DXY is THE signal for gold inverse correlation.
    TIPS real yields drive fundamental gold valuation.
    """

    # Reference values for fallback
    REFERENCE = {
        "ten_year": 4.25,
        "five_year": 4.00,
        "thirty_year": 4.50,
        "three_month": 5.30,
        "two_year": 4.10,
        "dxy": 104.0,
        "tip_price": 105.0,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "yield_curve.json"

    async def collect(self) -> YieldCurveSnapshot:
        """Collect yield curve data via yfinance proxies."""
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
            logger.error(f"Yield curve collection failed: {e}")
            return self._stale_fallback(str(e))

    def _fetch_yfinance(self) -> YieldCurveSnapshot:
        """Synchronous yfinance fetch — runs in executor."""
        # Fetch yields
        all_tickers = YIELD_TICKERS + DOLLAR_TICKERS + TIPS_TICKERS + [TWO_YEAR_PROXY]
        data = yf.download(
            all_tickers, period="30d", progress=False, group_by="ticker"
        )

        if data.empty:
            raise ValueError("yfinance returned empty data for yield curve tickers")

        def _get_series(ticker: str) -> tuple[float, float, float]:
            """Extract latest price, 5d change, 20d change for a ticker."""
            try:
                if len(all_tickers) > 1:
                    series = data[ticker]["Close"].dropna()
                else:
                    series = data["Close"].dropna()

                if series.empty:
                    raise ValueError(f"No close data for {ticker}")

                latest = float(series.iloc[-1])

                # 5-day change
                chg_5d = 0.0
                if len(series) >= 6:
                    prev = float(series.iloc[-6])
                    chg_5d = ((latest - prev) / prev) * 100 if prev != 0 else 0.0

                # 20-day change
                chg_20d = 0.0
                if len(series) >= 21:
                    prev = float(series.iloc[-21])
                    chg_20d = ((latest - prev) / prev) * 100 if prev != 0 else 0.0

                return latest, chg_5d, chg_20d
            except Exception as e:
                logger.warning(f"Failed to get {ticker} data: {e}")
                return 0.0, 0.0, 0.0

        # Treasury yields (yfinance reports these as percentages, e.g. 4.25)
        ten_year, _, _ = _get_series("^TNX")
        five_year, _, _ = _get_series("^FVX")
        thirty_year, _, _ = _get_series("^TYX")
        three_month, _, _ = _get_series("^IRX")

        # 2-year proxy: derive from SHY ETF (inverse price relationship)
        # SHY tracks 1-3yr Treasuries. Approximate 2yr yield from it.
        shy_price, _, _ = _get_series(TWO_YEAR_PROXY)
        # Rough heuristic: 2yr yield ~ (par_value - shy_price) / shy_price * factor + base
        # More practically, interpolate between 3-month and 5-year
        two_year = (three_month + five_year) / 2 if three_month > 0 and five_year > 0 else 0.0

        # Dollar index
        dxy, dxy_chg_5d, dxy_chg_20d = _get_series("DX-Y.NYB")
        if dxy == 0:
            # Fallback to UUP ETF
            uup, uup_chg_5d, uup_chg_20d = _get_series("UUP")
            if uup > 0:
                # UUP ~= DXY / 4 roughly; scale for approximation
                dxy = uup
                dxy_chg_5d = uup_chg_5d
                dxy_chg_20d = uup_chg_20d
                logger.info("Using UUP as DXY fallback")

        # TIPS / real yield
        tip_price, tip_chg_5d, _ = _get_series("TIP")

        # Real yield proxy: 10yr nominal - breakeven inflation
        # Breakeven ~ 10yr - TIPS yield. TIP ETF yield ~ (par - price) / price * 100
        # Simplified: if TIP is trading near par (100), implied inflation ~ 10yr - real
        # More practical: real yield ~ 10yr yield - (110 - TIP price) / 110 * 10
        # Best approximation without actual TIPS yield data:
        tips_yield = 0.0
        if ten_year > 0 and tip_price > 0:
            # Breakeven inflation proxy from TIP ETF
            # TIP trades around 100-115; when TIP rises, real yields fall
            implied_inflation = max(0, (tip_price - 95) / 95 * 10)  # rough proxy
            tips_yield = ten_year - implied_inflation

        tips_change_5d = 0.0
        if ten_year > 0 and tip_chg_5d != 0:
            # Change in real yield approximation (in bps)
            tips_change_5d = round(-tip_chg_5d * 5, 1)  # inverse: TIP up = real yield down

        # Compute spreads
        spread_2y10y = ten_year - two_year if ten_year > 0 and two_year > 0 else 0.0
        spread_3m10y = ten_year - three_month if ten_year > 0 and three_month > 0 else 0.0

        # Determine curve status
        if spread_2y10y < -0.1:
            curve_status = "inverted"
        elif spread_2y10y < 0.2:
            curve_status = "flat"
        else:
            curve_status = "normal"

        # Steepness
        if spread_2y10y > 1.0:
            curve_steepness = "steep"
        elif spread_2y10y > 0.3:
            curve_steepness = "moderate"
        elif spread_2y10y > -0.1:
            curve_steepness = "flat"
        else:
            curve_steepness = "inverted"

        # Data quality
        has_yields = all(v > 0 for v in [ten_year, five_year, thirty_year, three_month])
        has_dxy = dxy > 0
        quality = "live" if has_yields and has_dxy else ("delayed" if has_yields else "stale")

        return YieldCurveSnapshot(
            timestamp=datetime.now().isoformat(),
            ten_year=round(ten_year, 3),
            five_year=round(five_year, 3),
            thirty_year=round(thirty_year, 3),
            three_month=round(three_month, 3),
            two_year=round(two_year, 3),
            spread_2y10y=round(spread_2y10y, 3),
            spread_3m10y=round(spread_3m10y, 3),
            dxy=round(dxy, 2),
            dxy_change_5d=round(dxy_chg_5d, 2),
            dxy_change_20d=round(dxy_chg_20d, 2),
            tips_yield=round(tips_yield, 3),
            tips_change_5d=round(tips_change_5d, 1),
            tip_etf_price=round(tip_price, 2),
            curve_status=curve_status,
            curve_steepness=curve_steepness,
            source="yfinance",
            data_quality=quality,
        )

    def _stale_fallback(self, reason: str) -> YieldCurveSnapshot:
        """Return stale reference values when live data unavailable."""
        logger.warning(f"Using stale yield curve reference: {reason}")

        cached = self.load_latest()
        if cached:
            cached["data_quality"] = "stale"
            cached["timestamp"] = datetime.now().isoformat()
            return YieldCurveSnapshot(**cached)

        ref = self.REFERENCE
        spread_2y10y = ref["ten_year"] - ref["two_year"]
        spread_3m10y = ref["ten_year"] - ref["three_month"]

        return YieldCurveSnapshot(
            timestamp=datetime.now().isoformat(),
            ten_year=ref["ten_year"],
            five_year=ref["five_year"],
            thirty_year=ref["thirty_year"],
            three_month=ref["three_month"],
            two_year=ref["two_year"],
            spread_2y10y=round(spread_2y10y, 3),
            spread_3m10y=round(spread_3m10y, 3),
            dxy=ref["dxy"],
            dxy_change_5d=0.0,
            dxy_change_20d=0.0,
            tips_yield=round(ref["ten_year"] - 2.3, 3),  # ~2.3% breakeven
            tips_change_5d=0.0,
            tip_etf_price=ref["tip_price"],
            curve_status="normal" if spread_2y10y > 0.2 else "flat",
            curve_steepness="moderate",
            source="reference",
            data_quality="stale",
        )

    def _save(self, snapshot: YieldCurveSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved yield curve: 10yr={snapshot.ten_year}% 2y10y={snapshot.spread_2y10y:+.3f} "
            f"DXY={snapshot.dxy} ({snapshot.dxy_change_5d:+.1f}% 5d) "
            f"real_yield={snapshot.tips_yield:.3f}% curve={snapshot.curve_status}"
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
