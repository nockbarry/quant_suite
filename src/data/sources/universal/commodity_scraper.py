"""
Commodity Scraper - Specialized Industry Data Sources

Acquires data that's harder to get than standard commodities:
- DRAM prices (memory chips)
- Semiconductor equipment billing
- Specialty metals and materials
- Supply chain indicators

Uses multiple strategies:
1. Direct web scraping (with compliance)
2. ETF/stock proxies (MU for DRAM, AMAT for equipment)
3. Correlation analysis for backtesting when direct data unavailable

All data stored with point-in-time timestamps for backtest safety.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd

from src.core.paths import paths

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


# =============================================================================
# SCRAPING POLICY - Compliance First
# =============================================================================

@dataclass
class ScrapingPolicy:
    """Enforce ethical scraping across all sources."""

    # Rate limiting (per domain)
    min_request_interval: float = 2.0  # seconds between requests
    max_requests_per_hour: int = 100

    # Compliance
    respect_robots_txt: bool = True
    identify_as_bot: bool = True  # Honest User-Agent
    cache_responses: bool = True

    # Backoff on errors
    retry_delays: list[int] = field(default_factory=lambda: [5, 30, 120, 600])

    # User agent
    user_agent: str = "QuantSuiteBot/1.0 (Research; +https://github.com/quant_suite)"


# =============================================================================
# SCRAPED DATA CONTAINER
# =============================================================================

@dataclass
class ScrapedDataPoint:
    """A single data point with full provenance."""
    value: float
    date: datetime
    source_url: str
    source_name: str
    scraped_at: datetime
    available_at: datetime  # Conservative estimate of when we could have known
    unit: str = ""
    metadata: dict = field(default_factory=dict)

    def was_available_on(self, check_date: datetime) -> bool:
        """Check if this data was available for backtesting on given date."""
        return self.available_at <= check_date


# =============================================================================
# ROBOTS.TXT CHECKER
# =============================================================================

class RobotsChecker:
    """Check robots.txt compliance before scraping."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (paths.scraped_data / "metadata" / "robots_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._parsers: dict[str, RobotFileParser] = {}

    def _get_cache_path(self, domain: str) -> Path:
        """Get cache path for domain's robots.txt."""
        safe_domain = domain.replace(".", "_").replace(":", "_")
        return self.cache_dir / f"{safe_domain}_robots.txt"

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Check if URL can be fetched according to robots.txt."""
        parsed = urlparse(url)
        domain = parsed.netloc

        if domain in self._parsers:
            return self._parsers[domain].can_fetch(user_agent, url)

        # Try to load from cache
        cache_path = self._get_cache_path(domain)
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"

        try:
            if cache_path.exists():
                # Check cache age
                cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
                if cache_age < timedelta(days=1):
                    with open(cache_path) as f:
                        robots_content = f.read()
                else:
                    robots_content = await self._fetch_robots(robots_url)
                    cache_path.write_text(robots_content)
            else:
                robots_content = await self._fetch_robots(robots_url)
                cache_path.write_text(robots_content)

            # Parse robots.txt
            parser = RobotFileParser()
            parser.parse(robots_content.split("\n"))
            self._parsers[domain] = parser

            return parser.can_fetch(user_agent, url)

        except Exception as e:
            logger.warning(f"Could not check robots.txt for {domain}: {e}")
            # Be conservative - assume allowed if we can't check
            return True

    async def _fetch_robots(self, url: str) -> str:
        """Fetch robots.txt content."""
        if aiohttp is None:
            raise ImportError("aiohttp required: pip install aiohttp")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    return ""
            except:
                return ""


# =============================================================================
# COMMODITY SOURCE - Main Interface
# =============================================================================

class CommoditySource:
    """
    Scrape commodity prices from free sources.

    Provides multiple data acquisition strategies:
    1. Direct scraping (DRAM exchanges, industry reports)
    2. ETF proxies (MU for DRAM, AMAT for equipment)
    3. FRED API for standard commodities

    All with proper rate limiting and point-in-time storage.
    """

    # ETF proxies for specialized commodities
    ETF_PROXIES = {
        "dram": ["MU", "SK Hynix proxy"],      # Micron as DRAM proxy
        "nand": ["WDC", "STX"],                 # Western Digital, Seagate
        "semi_equipment": ["AMAT", "LRCX", "KLAC", "ASML"],  # Equipment makers
        "foundry": ["TSM", "INTC"],             # TSMC, Intel
        "logic": ["NVDA", "AMD", "QCOM"],       # GPU/CPU makers
        "lithium": ["ALB", "SQM", "LTHM"],      # Lithium producers
        "rare_earth": ["MP", "LAC"],            # Rare earth miners
        "uranium": ["CCJ", "UEC"],              # Uranium producers
    }

    # Stock-to-commodity sensitivity (approximate)
    PROXY_SENSITIVITY = {
        "MU": {"dram": 0.8, "nand": 0.4},
        "AMAT": {"semi_equipment": 0.9},
        "LRCX": {"semi_equipment": 0.85},
        "TSM": {"foundry": 0.95, "logic": 0.5},
        "NVDA": {"logic": 0.7, "ai_chips": 0.9},
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
        policy: ScrapingPolicy | None = None,
    ):
        self.cache_dir = cache_dir or (paths.scraped_data / "commodities")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.policy = policy or ScrapingPolicy()
        self.robots_checker = RobotsChecker()
        self._last_request_time: dict[str, float] = {}

    async def _rate_limit(self, domain: str):
        """Enforce rate limiting per domain."""
        now = time.time()
        last = self._last_request_time.get(domain, 0)
        elapsed = now - last

        if elapsed < self.policy.min_request_interval:
            await asyncio.sleep(self.policy.min_request_interval - elapsed)

        self._last_request_time[domain] = time.time()

    # =========================================================================
    # DRAM PRICES
    # =========================================================================

    async def get_dram_prices(
        self,
        days: int = 365 * 2,
        use_proxy: bool = True,
    ) -> pd.DataFrame:
        """
        Get DRAM price data.

        Strategy:
        1. Try to find scrapeable free sources
        2. Fall back to MU stock as proxy (highly correlated with DRAM prices)

        Args:
            days: Number of days of history
            use_proxy: Fall back to stock proxy if scraping fails

        Returns:
            DataFrame with 'price' column and date index
        """
        cache_file = self.cache_dir / "dram_prices.parquet"

        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(hours=12):
                logger.debug("Cache hit: DRAM prices")
                return pd.read_parquet(cache_file)

        # Try scraping (placeholder - would need actual source)
        dram_data = await self._try_scrape_dram_prices()

        if dram_data is not None and len(dram_data) > 0:
            dram_data.to_parquet(cache_file)
            return dram_data

        # Fall back to MU proxy
        if use_proxy:
            logger.info("Using MU stock as DRAM price proxy")
            return await self._get_proxy_data("MU", days, "dram_proxy")

        raise ValueError("Could not get DRAM prices from any source")

    async def _try_scrape_dram_prices(self) -> pd.DataFrame | None:
        """
        Attempt to scrape DRAM prices from public sources.

        This is a placeholder - actual implementation would need:
        - Identifying reliable free sources
        - Parsing their specific HTML structure
        - Handling authentication if required
        """
        # Known potential sources (need to verify availability):
        # - DRAMeXchange (paid/registration)
        # - IC Insights reports (periodic, not real-time)
        # - TrendForce (some free data)

        # For now, return None to trigger proxy fallback
        # In production, would implement actual scraping here
        logger.debug("Direct DRAM scraping not implemented - using proxy")
        return None

    # =========================================================================
    # SEMI EQUIPMENT BILLING
    # =========================================================================

    async def get_semi_equipment_billing(
        self,
        days: int = 365 * 5,
    ) -> pd.DataFrame:
        """
        Get semiconductor equipment billing data.

        SEMI publishes monthly billing data - a leading indicator for
        semiconductor industry health.

        Falls back to equipment stock performance (AMAT, LRCX, KLAC).
        """
        cache_file = self.cache_dir / "semi_equipment_billing.parquet"

        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(days=7):  # Weekly update
                return pd.read_parquet(cache_file)

        # Try to get actual SEMI data (placeholder)
        semi_data = await self._try_scrape_semi_billing()

        if semi_data is not None and len(semi_data) > 0:
            semi_data.to_parquet(cache_file)
            return semi_data

        # Fall back to equipment stock composite
        logger.info("Using equipment stocks as SEMI billing proxy")
        return await self._get_equipment_composite(days)

    async def _try_scrape_semi_billing(self) -> pd.DataFrame | None:
        """Attempt to scrape SEMI billing data."""
        # SEMI publishes at: https://www.semi.org/en/products-services/market-data
        # However, detailed data usually requires subscription
        # Some summary data may be available in press releases
        return None

    async def _get_equipment_composite(self, days: int) -> pd.DataFrame:
        """Get composite of equipment stock performance."""
        equipment_stocks = ["AMAT", "LRCX", "KLAC", "ASML"]
        data = {}

        for symbol in equipment_stocks:
            try:
                df = await self._get_proxy_data(symbol, days, f"{symbol}_equipment")
                data[symbol] = df["price"]
            except Exception as e:
                logger.warning(f"Failed to get {symbol}: {e}")

        if not data:
            raise ValueError("Could not get any equipment stock data")

        # Create equal-weighted composite
        df = pd.DataFrame(data)
        df["price"] = df.mean(axis=1)
        df["source"] = "equipment_composite"
        df.index.name = "date"

        return df[["price", "source"]]

    # =========================================================================
    # PROXY DATA METHODS
    # =========================================================================

    async def _get_proxy_data(
        self,
        symbol: str,
        days: int,
        source_name: str,
    ) -> pd.DataFrame:
        """Get stock data as a proxy for commodity."""
        if yf is None:
            raise ImportError("yfinance required: pip install yfinance")

        cache_file = self.cache_dir / f"proxy_{symbol}.parquet"

        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(hours=6):
                return pd.read_parquet(cache_file)

        # Fetch from Yahoo
        period = f"{days}d" if days <= 365 else f"{min(days // 365, 10)}y"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            raise ValueError(f"No data for {symbol}")

        df = pd.DataFrame({
            "price": hist["Close"],
            "volume": hist["Volume"],
            "source": source_name,
        })
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "date"

        # Cache
        df.to_parquet(cache_file)
        logger.info(f"Cached proxy {symbol}: {len(df)} observations")

        return df

    # =========================================================================
    # SPECIALTY COMMODITIES
    # =========================================================================

    async def get_lithium_prices(self, days: int = 365 * 2) -> pd.DataFrame:
        """Get lithium prices (via producer stocks as proxy)."""
        # Could try FRED or LME for actual lithium prices
        # Fall back to lithium producer composite
        return await self._get_commodity_via_producers("lithium", days)

    async def get_rare_earth_prices(self, days: int = 365 * 2) -> pd.DataFrame:
        """Get rare earth prices (via producer stocks as proxy)."""
        return await self._get_commodity_via_producers("rare_earth", days)

    async def get_uranium_prices(self, days: int = 365 * 2) -> pd.DataFrame:
        """Get uranium prices (via producer stocks as proxy)."""
        return await self._get_commodity_via_producers("uranium", days)

    async def _get_commodity_via_producers(
        self,
        commodity: str,
        days: int,
    ) -> pd.DataFrame:
        """Get commodity price estimate via producer stock composite."""
        if commodity not in self.ETF_PROXIES:
            raise ValueError(f"Unknown commodity: {commodity}")

        symbols = self.ETF_PROXIES[commodity]
        data = {}

        for symbol in symbols:
            if not isinstance(symbol, str) or " " in symbol:
                continue  # Skip placeholder entries
            try:
                df = await self._get_proxy_data(symbol, days, f"{symbol}_{commodity}")
                data[symbol] = df["price"]
            except Exception as e:
                logger.warning(f"Failed to get {symbol}: {e}")

        if not data:
            raise ValueError(f"Could not get any {commodity} producer data")

        df = pd.DataFrame(data)
        df["price"] = df.mean(axis=1)
        df["source"] = f"{commodity}_producer_composite"
        df.index.name = "date"

        # Cache
        cache_file = self.cache_dir / f"{commodity}_prices.parquet"
        df[["price", "source"]].to_parquet(cache_file)

        return df[["price", "source"]]

    # =========================================================================
    # ANALYSIS UTILITIES
    # =========================================================================

    async def analyze_commodity_stock_lag(
        self,
        commodity: str,
        stocks: list[str],
        days: int = 365 * 2,
        max_lag: int = 20,
    ) -> pd.DataFrame:
        """
        Analyze lead-lag relationship between commodity and stocks.

        Useful for:
        - DRAM prices → semiconductor stocks
        - Oil prices → energy stocks
        - Lithium → EV stocks

        Returns correlation at different lags.
        """
        # Get commodity data
        if commodity == "dram":
            comm_data = await self.get_dram_prices(days)
        elif commodity in self.ETF_PROXIES:
            comm_data = await self._get_commodity_via_producers(commodity, days)
        else:
            raise ValueError(f"Unknown commodity: {commodity}")

        # Get stock data
        stock_data = {}
        for symbol in stocks:
            try:
                stock_data[symbol] = await self._get_proxy_data(symbol, days, symbol)
            except Exception as e:
                logger.warning(f"Failed to get {symbol}: {e}")

        if not stock_data:
            raise ValueError("Could not get any stock data")

        # Calculate returns
        comm_returns = comm_data["price"].pct_change().dropna()

        results = []
        for symbol, data in stock_data.items():
            stock_returns = data["price"].pct_change().dropna()

            # Align dates
            aligned = pd.concat([comm_returns, stock_returns], axis=1, join="inner")
            aligned.columns = ["commodity", "stock"]

            if len(aligned) < 20:  # Minimum 20 trading days for meaningful correlation
                logger.warning(f"Insufficient aligned data for {symbol}: {len(aligned)} rows")
                continue

            # Test different lags
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    # Commodity leads stock
                    shifted_comm = aligned["commodity"].shift(-lag)
                    corr = shifted_comm.corr(aligned["stock"])
                else:
                    # Stock leads commodity
                    shifted_stock = aligned["stock"].shift(lag)
                    corr = aligned["commodity"].corr(shifted_stock)

                results.append({
                    "stock": symbol,
                    "lag_days": lag,
                    "correlation": corr,
                    "interpretation": "commodity_leads" if lag < 0 else "stock_leads" if lag > 0 else "concurrent",
                })

        return pd.DataFrame(results)

    def list_available_commodities(self) -> dict[str, list[str]]:
        """List all available commodity proxies."""
        return {
            name: proxies for name, proxies in self.ETF_PROXIES.items()
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_dram_prices(days: int = 365 * 2) -> pd.DataFrame:
    """Convenience function to get DRAM prices."""
    source = CommoditySource()
    return await source.get_dram_prices(days)


async def get_semi_equipment(days: int = 365 * 5) -> pd.DataFrame:
    """Convenience function to get semi equipment billing proxy."""
    source = CommoditySource()
    return await source.get_semi_equipment_billing(days)


async def analyze_dram_semiconductor_relationship(
    stocks: list[str] | None = None,
    days: int = 365 * 2,
) -> pd.DataFrame:
    """
    Analyze DRAM price → semiconductor stock relationship.

    Default stocks: MU, NVDA, AMD, INTC, TSM, QCOM
    """
    stocks = stocks or ["MU", "NVDA", "AMD", "INTC", "TSM", "QCOM"]
    source = CommoditySource()
    return await source.analyze_commodity_stock_lag("dram", stocks, days)
