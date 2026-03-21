"""TSMC Monthly Revenue Tracker.

TSMC publishes monthly revenue on the 10th of each month.
Leading indicator for semiconductor cycle (HBM thesis).

Source: https://www.tsmc.com/english/investorRelations/monthly_revenue
Fallback: yfinance TSM stock + SEMI booking data
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

try:
    import yfinance as yf
except ImportError:
    yf = None

from src.core.paths import paths

logger = logging.getLogger(__name__)

# TSMC IR page URL
TSMC_IR_URL = "https://www.tsmc.com/english/investorRelations/monthly_revenue"

# Historical monthly revenue reference (TWD billions, approximate)
# Updated from public filings — used for YoY comparison
HISTORICAL_REVENUE_TWD_B = {
    # (year, month): revenue_TWD_billions
    (2025, 1): 293.3,
    (2025, 2): 260.0,
    (2025, 3): 295.0,
    (2025, 4): 236.0,
    (2025, 5): 229.6,
    (2025, 6): 207.9,
    (2025, 7): 256.9,
    (2025, 8): 250.9,
    (2025, 9): 260.1,
    (2025, 10): 263.5,
    (2025, 11): 276.1,
    (2025, 12): 290.0,
}

# TSM stock ticker
TSM_TICKER = "TSM"


@dataclass
class TSMCRevenueSnapshot:
    """TSMC monthly revenue tracking snapshot."""

    timestamp: str
    latest_month: str  # "2026-02" format
    latest_revenue_twd_b: float  # Revenue in TWD billions (0 if not yet available)
    yoy_growth_pct: float  # Year-over-year growth %
    mom_growth_pct: float  # Month-over-month growth %
    revenue_trend: str  # "accelerating", "decelerating", "stable", "unknown"
    tsm_price: float  # TSM ADR price
    tsm_change_5d: float  # TSM 5-day % change
    tsm_change_20d: float  # TSM 20-day % change
    tsm_52w_high: float  # 52-week high
    tsm_pct_from_high: float  # % from 52-week high
    next_revenue_date: str  # Expected date of next revenue announcement
    is_revenue_day: bool  # True if today is around the 10th (revenue release)
    semi_cycle_signal: str  # "expansion", "peak", "contraction", "trough"
    source: str  # "tsmc_ir", "yfinance", "reference"
    data_quality: str  # "live", "delayed", "stale"


class TSMCRevenueCollector:
    """Track TSMC monthly revenue as semiconductor cycle indicator.

    TSMC is the world's largest foundry. Their monthly revenue is a
    leading indicator for:
    - Memory/HBM Supercycle thesis (TSMC supplies advanced packaging)
    - AI Power Infrastructure thesis (TSMC fabs for AI chips)
    - TSMC Arizona Expansion thesis (capex validation)
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.live
        self.cache_file = self.cache_dir / "tsmc_revenue.json"

    async def collect(self) -> TSMCRevenueSnapshot:
        """Collect TSMC revenue data."""
        # Try to scrape TSMC IR page
        latest_revenue = 0.0
        latest_month = ""
        source = "reference"

        try:
            latest_month, latest_revenue = await self._scrape_tsmc_ir()
            if latest_revenue > 0:
                source = "tsmc_ir"
        except Exception as e:
            logger.warning(f"TSMC IR scrape failed: {e}")

        # Always get TSM stock data
        tsm_data = await self._get_tsm_stock()

        # Compute metrics
        now = datetime.now()

        if not latest_month:
            # Estimate: revenue for previous month (released ~10th of current)
            if now.day >= 10:
                latest_month = f"{now.year}-{now.month:02d}"
            else:
                prev_month = now.month - 1 if now.month > 1 else 12
                prev_year = now.year if now.month > 1 else now.year - 1
                latest_month = f"{prev_year}-{prev_month:02d}"

        # YoY comparison
        yoy_growth = 0.0
        if latest_revenue > 0:
            try:
                parts = latest_month.split("-")
                last_year_key = (int(parts[0]) - 1, int(parts[1]))
                last_year_rev = HISTORICAL_REVENUE_TWD_B.get(last_year_key, 0)
                if last_year_rev > 0:
                    yoy_growth = ((latest_revenue - last_year_rev) / last_year_rev) * 100
            except (ValueError, IndexError):
                pass

        # MoM comparison
        mom_growth = 0.0
        if latest_revenue > 0:
            try:
                parts = latest_month.split("-")
                month = int(parts[1])
                year = int(parts[0])
                prev_month = month - 1 if month > 1 else 12
                prev_year = year if month > 1 else year - 1
                prev_key = (prev_year, prev_month)
                prev_rev = HISTORICAL_REVENUE_TWD_B.get(prev_key, 0)
                if prev_rev > 0:
                    mom_growth = ((latest_revenue - prev_rev) / prev_rev) * 100
            except (ValueError, IndexError):
                pass

        # Revenue trend
        if yoy_growth > 30:
            revenue_trend = "accelerating"
        elif yoy_growth > 10:
            revenue_trend = "stable"
        elif yoy_growth > 0:
            revenue_trend = "decelerating"
        elif yoy_growth < -10:
            revenue_trend = "contraction"
        elif latest_revenue == 0:
            revenue_trend = "unknown"
        else:
            revenue_trend = "decelerating"

        # Semi cycle signal (based on TSM stock + revenue trend)
        tsm_pct_from_high = tsm_data.get("pct_from_high", 0)
        if yoy_growth > 20 and tsm_pct_from_high > -10:
            semi_cycle = "expansion"
        elif yoy_growth > 20 and tsm_pct_from_high < -20:
            semi_cycle = "peak"  # Revenue strong but stock falling
        elif yoy_growth < 0:
            semi_cycle = "contraction"
        elif yoy_growth < 10 and tsm_pct_from_high < -30:
            semi_cycle = "trough"
        else:
            semi_cycle = "expansion"

        # Next revenue date (10th of next month)
        if now.day < 10:
            next_date = f"{now.year}-{now.month:02d}-10"
        else:
            next_month = now.month + 1 if now.month < 12 else 1
            next_year = now.year if now.month < 12 else now.year + 1
            next_date = f"{next_year}-{next_month:02d}-10"

        is_revenue_day = 8 <= now.day <= 12

        snapshot = TSMCRevenueSnapshot(
            timestamp=now.isoformat(),
            latest_month=latest_month,
            latest_revenue_twd_b=round(latest_revenue, 1),
            yoy_growth_pct=round(yoy_growth, 1),
            mom_growth_pct=round(mom_growth, 1),
            revenue_trend=revenue_trend,
            tsm_price=tsm_data.get("price", 0),
            tsm_change_5d=tsm_data.get("change_5d", 0),
            tsm_change_20d=tsm_data.get("change_20d", 0),
            tsm_52w_high=tsm_data.get("high_52w", 0),
            tsm_pct_from_high=round(tsm_pct_from_high, 1),
            next_revenue_date=next_date,
            is_revenue_day=is_revenue_day,
            semi_cycle_signal=semi_cycle,
            source=source,
            data_quality="live" if source == "tsmc_ir" else "delayed",
        )

        self._save(snapshot)
        return snapshot

    async def _scrape_tsmc_ir(self) -> tuple[str, float]:
        """Try to scrape TSMC IR page for latest monthly revenue."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                TSMC_IR_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()
            text = response.text

        # Look for revenue data in the page
        # TSMC typically shows a table with monthly figures in TWD
        # Pattern: "January 2026" followed by a number
        import re

        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]

        latest_month = ""
        latest_value = 0.0

        for i, month_name in enumerate(months, 1):
            # Look for patterns like "January 2026  293,345" (revenue in TWD millions)
            pattern = rf"{month_name}\s+(\d{{4}})\s*[\n\r]*\s*([\d,]+)"
            matches = re.findall(pattern, text, re.IGNORECASE)
            for year_str, value_str in matches:
                try:
                    year = int(year_str)
                    value = float(value_str.replace(",", ""))
                    month_str = f"{year}-{i:02d}"
                    # Convert TWD millions to TWD billions
                    value_b = value / 1000
                    if value_b > latest_value or month_str > latest_month:
                        latest_month = month_str
                        latest_value = value_b
                except ValueError:
                    continue

        if latest_value > 0:
            return latest_month, latest_value
        raise ValueError("Could not parse revenue from TSMC IR page")

    async def _get_tsm_stock(self) -> dict:
        """Get TSM stock price and metrics."""
        if yf is None:
            return {"price": 0, "change_5d": 0, "change_20d": 0, "high_52w": 0, "pct_from_high": 0}

        def _fetch():
            try:
                data = yf.download(TSM_TICKER, period="1y", progress=False)
                if data.empty:
                    return {"price": 0, "change_5d": 0, "change_20d": 0, "high_52w": 0, "pct_from_high": 0}

                close = data["Close"].dropna()
                if close.empty:
                    return {"price": 0, "change_5d": 0, "change_20d": 0, "high_52w": 0, "pct_from_high": 0}

                latest = float(close.iloc[-1])
                high_52w = float(close.max())
                pct_from_high = ((latest - high_52w) / high_52w) * 100 if high_52w > 0 else 0

                chg_5d = 0.0
                if len(close) >= 6:
                    prev = float(close.iloc[-6])
                    chg_5d = ((latest - prev) / prev) * 100 if prev > 0 else 0

                chg_20d = 0.0
                if len(close) >= 21:
                    prev = float(close.iloc[-21])
                    chg_20d = ((latest - prev) / prev) * 100 if prev > 0 else 0

                return {
                    "price": round(latest, 2),
                    "change_5d": round(chg_5d, 2),
                    "change_20d": round(chg_20d, 2),
                    "high_52w": round(high_52w, 2),
                    "pct_from_high": pct_from_high,
                }
            except Exception as e:
                logger.warning(f"TSM stock fetch failed: {e}")
                return {"price": 0, "change_5d": 0, "change_20d": 0, "high_52w": 0, "pct_from_high": 0}

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    def _save(self, snapshot: TSMCRevenueSnapshot) -> None:
        """Persist snapshot to JSON cache."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(asdict(snapshot), f, indent=2)
        logger.info(
            f"Saved TSMC revenue: {snapshot.latest_month} "
            f"TWD {snapshot.latest_revenue_twd_b}B "
            f"(YoY {snapshot.yoy_growth_pct:+.1f}%), "
            f"TSM=${snapshot.tsm_price} ({snapshot.tsm_change_5d:+.1f}% 5d), "
            f"cycle={snapshot.semi_cycle_signal}"
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
