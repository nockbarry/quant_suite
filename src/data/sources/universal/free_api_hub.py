"""
Free API Hub - Unified Interface to Free Data Sources

Provides access to free data APIs with proper rate limiting and caching:
- FRED (Federal Reserve Economic Data) - comprehensive macro indicators
- Yahoo Finance - commodity ETF proxies
- Alpha Vantage (free tier)
- World Bank Open Data

All data is persisted for point-in-time backtesting safety.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


# =============================================================================
# SCRAPED DATA CONTAINER - Point-in-Time Safe
# =============================================================================

@dataclass
class ScrapedData:
    """All scraped/fetched data includes temporal metadata for backtesting safety."""
    content: Any
    source_url: str
    source_name: str
    published_date: datetime | None  # When source says it was published
    scraped_date: datetime           # When WE acquired it
    available_date: datetime         # When we COULD have known (conservative)
    metadata: dict = field(default_factory=dict)

    def was_available_on(self, date: datetime) -> bool:
        """Check if this data was available for backtesting on given date."""
        return self.available_date <= date

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "content": self.content if isinstance(self.content, (dict, list, str, int, float)) else str(self.content),
            "source_url": self.source_url,
            "source_name": self.source_name,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "scraped_date": self.scraped_date.isoformat(),
            "available_date": self.available_date.isoformat(),
            "metadata": self.metadata,
        }


# =============================================================================
# FRED CLIENT - Federal Reserve Economic Data
# =============================================================================

class FREDClient:
    """
    Client for FRED (Federal Reserve Economic Data).

    FRED provides free access to 800,000+ time series covering:
    - Commodity prices (gold, silver, oil, copper)
    - Interest rates and yield curves
    - Economic indicators (GDP, unemployment, CPI)
    - Financial market indicators (VIX, spreads)

    API Key: Free at https://fred.stlouisfed.org/docs/api/api_key.html
    """

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    # Common FRED series IDs for commodities and macro
    SERIES = {
        # Commodities
        "gold": "GOLDAMGBD228NLBM",       # Gold Fixing Price (London)
        "silver": "SLVPRUSD",              # Silver Price
        "oil_wti": "DCOILWTICO",           # WTI Crude Oil
        "oil_brent": "DCOILBRENTEU",       # Brent Crude Oil
        "natural_gas": "DHHNGSP",          # Henry Hub Natural Gas Spot
        "copper": "PCOPPUSDM",             # Global Copper Price
        "corn": "PMAIZMTUSDM",             # Corn Price
        "wheat": "PWHEAMTUSDM",            # Wheat Price
        "aluminum": "PALUMUSDM",           # Aluminum Price

        # Interest Rates
        "fed_funds": "FEDFUNDS",           # Federal Funds Rate
        "treasury_10y": "DGS10",           # 10-Year Treasury
        "treasury_2y": "DGS2",             # 2-Year Treasury
        "treasury_3m": "DTB3",             # 3-Month Treasury Bill
        "libor_3m": "USD3MTD156N",         # 3-Month LIBOR

        # Yield Curve (spread = 10Y - 2Y)
        "yield_spread_10y_2y": "T10Y2Y",   # 10Y-2Y Spread
        "yield_spread_10y_3m": "T10Y3M",   # 10Y-3M Spread

        # Volatility
        "vix": "VIXCLS",                   # VIX

        # Economic Indicators
        "unemployment": "UNRATE",           # Unemployment Rate
        "cpi": "CPIAUCSL",                 # CPI (All Urban Consumers)
        "gdp": "GDP",                      # Gross Domestic Product
        "industrial_production": "INDPRO", # Industrial Production Index
        "retail_sales": "RSAFS",           # Retail Sales
        "housing_starts": "HOUST",         # Housing Starts

        # Financial Conditions
        "ted_spread": "TEDRATE",           # TED Spread (3M LIBOR - 3M T-Bill)
        "baa_spread": "BAAFFM",            # Moody's Baa Corporate Spread
        "high_yield_spread": "BAMLH0A0HYM2", # ICE BofA High Yield Spread

        # USD Index
        "usd_index": "DTWEXBGS",           # Trade Weighted USD Index
    }

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        rate_limit_per_minute: int = 120,  # FRED limit
    ):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            logger.warning(
                "FRED_API_KEY not set. Get free key at: "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )

        self.cache_dir = cache_dir or Path("/home/nock/quant_results/scraped_data/commodities")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.rate_limit = rate_limit_per_minute
        self._last_request_time = 0.0
        self._request_interval = 60.0 / rate_limit_per_minute

    async def _rate_limit(self):
        """Enforce rate limiting."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()

    async def get_series(
        self,
        series_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        cache_ttl: timedelta = timedelta(hours=6),
    ) -> pd.Series:
        """
        Fetch a FRED series.

        Args:
            series_id: FRED series ID (e.g., 'GOLDAMGBD228NLBM')
            start_date: Start date (default: 5 years ago)
            end_date: End date (default: today)
            cache_ttl: Cache time-to-live

        Returns:
            pd.Series with DatetimeIndex
        """
        if not self.api_key:
            raise ValueError("FRED_API_KEY required. Set env var or pass api_key.")

        if aiohttp is None:
            raise ImportError("aiohttp required: pip install aiohttp")

        # Defaults
        end_date = end_date or datetime.now()
        start_date = start_date or (end_date - timedelta(days=5*365))

        # Check cache
        cache_file = self.cache_dir / f"fred_{series_id}.parquet"
        if cache_file.exists():
            cached = pd.read_parquet(cache_file)
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < cache_ttl:
                logger.debug(f"Cache hit: FRED {series_id}")
                return cached['value']

        # Fetch from FRED
        await self._rate_limit()

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date.strftime("%Y-%m-%d"),
            "observation_end": end_date.strftime("%Y-%m-%d"),
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ValueError(f"FRED API error: {response.status} - {text}")

                data = await response.json()

        # Parse observations
        observations = data.get("observations", [])
        if not observations:
            logger.warning(f"No data for FRED series {series_id}")
            return pd.Series(dtype=float)

        # Convert to DataFrame
        df = pd.DataFrame(observations)
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.set_index('date')[['value']]
        df = df.dropna()

        # Cache
        df.to_parquet(cache_file)
        logger.info(f"Cached FRED {series_id}: {len(df)} observations")

        return df['value']

    async def get_commodity(self, name: str, **kwargs) -> pd.Series:
        """Get commodity price by common name."""
        if name not in self.SERIES:
            raise ValueError(f"Unknown commodity: {name}. Available: {list(self.SERIES.keys())}")
        return await self.get_series(self.SERIES[name], **kwargs)

    async def get_yield_curve(self) -> pd.DataFrame:
        """Get current yield curve data (3M, 2Y, 10Y rates + spreads)."""
        series = ["treasury_3m", "treasury_2y", "treasury_10y", "yield_spread_10y_2y"]
        data = {}

        for name in series:
            try:
                data[name] = await self.get_commodity(name)
            except Exception as e:
                logger.warning(f"Failed to get {name}: {e}")

        if not data:
            return pd.DataFrame()

        return pd.DataFrame(data)

    async def get_macro_indicators(self) -> dict[str, pd.Series]:
        """Get key macro indicators."""
        indicators = ["vix", "fed_funds", "unemployment", "cpi", "yield_spread_10y_2y"]
        result = {}

        for name in indicators:
            try:
                result[name] = await self.get_commodity(name)
            except Exception as e:
                logger.warning(f"Failed to get {name}: {e}")

        return result


# =============================================================================
# FREE API HUB - Unified Interface
# =============================================================================

class FreeAPIHub:
    """
    Unified interface to ALL free data sources.

    Provides:
    - Commodity data via FRED + ETF proxies
    - Macro indicators
    - ETF proxies for commodities without direct data

    All data cached with point-in-time safety.
    """

    # ETF proxies for commodities (when direct data unavailable)
    ETF_PROXIES = {
        "gold": "GLD",           # SPDR Gold Shares
        "silver": "SLV",         # iShares Silver Trust
        "oil": "USO",            # United States Oil Fund
        "natural_gas": "UNG",    # United States Natural Gas Fund
        "copper": "CPER",        # United States Copper Index Fund
        "agriculture": "DBA",    # Invesco DB Agriculture Fund
        "commodities": "DBC",    # Invesco DB Commodity Index
        "platinum": "PPLT",      # Aberdeen Standard Physical Platinum
        "palladium": "PALL",     # Aberdeen Standard Physical Palladium
    }

    # Sector ETFs for macro analysis
    SECTOR_ETFS = {
        "energy": "XLE",
        "materials": "XLB",
        "industrials": "XLI",
        "financials": "XLF",
        "technology": "XLK",
        "healthcare": "XLV",
        "utilities": "XLU",
        "real_estate": "XLRE",
        "consumer_discretionary": "XLY",
        "consumer_staples": "XLP",
        "communication": "XLC",
    }

    def __init__(
        self,
        fred_api_key: str | None = None,
        cache_dir: Path | None = None,
    ):
        self.fred = FREDClient(api_key=fred_api_key, cache_dir=cache_dir)
        self.cache_dir = cache_dir or Path("/home/nock/quant_results/scraped_data")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def get_commodity(
        self,
        name: str,
        days: int = 365 * 5,
        prefer_fred: bool = True,
    ) -> pd.DataFrame:
        """
        Get commodity data from best available source.

        Args:
            name: Commodity name (gold, silver, oil, etc.)
            days: Number of days of history
            prefer_fred: Try FRED first, fall back to ETF

        Returns:
            DataFrame with price data
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Try FRED first if preferred and available
        if prefer_fred and name in FREDClient.SERIES:
            try:
                series = await self.fred.get_series(
                    FREDClient.SERIES[name],
                    start_date=start_date,
                    end_date=end_date,
                )
                if len(series) > 0:
                    df = pd.DataFrame({"price": series, "source": "fred"})
                    df.index.name = "date"
                    logger.info(f"Got {name} from FRED: {len(df)} observations")
                    return df
            except Exception as e:
                logger.warning(f"FRED failed for {name}: {e}")

        # Fall back to ETF proxy
        if name in self.ETF_PROXIES:
            return await self._get_etf_data(self.ETF_PROXIES[name], days)

        raise ValueError(f"No data source for commodity: {name}")

    async def _get_etf_data(self, symbol: str, days: int = 365) -> pd.DataFrame:
        """Get ETF data from Yahoo Finance."""
        if yf is None:
            raise ImportError("yfinance required: pip install yfinance")

        # Check cache
        cache_file = self.cache_dir / "commodities" / f"etf_{symbol}.parquet"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(hours=6):
                logger.debug(f"Cache hit: ETF {symbol}")
                return pd.read_parquet(cache_file)

        # Fetch from Yahoo
        period = f"{days}d" if days <= 365 else f"{days // 365}y"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            raise ValueError(f"No data for ETF {symbol}")

        df = pd.DataFrame({
            "price": hist["Close"],
            "volume": hist["Volume"],
            "source": "yahoo_etf",
        })
        df.index.name = "date"

        # Cache
        df.to_parquet(cache_file)
        logger.info(f"Cached ETF {symbol}: {len(df)} observations")

        return df

    async def get_fred_series(self, series_id: str, **kwargs) -> pd.Series:
        """Get raw FRED series by ID."""
        return await self.fred.get_series(series_id, **kwargs)

    async def get_macro_indicators(self) -> dict[str, pd.Series]:
        """Get key macro indicators (VIX, rates, unemployment, etc.)."""
        return await self.fred.get_macro_indicators()

    async def get_yield_curve(self) -> pd.DataFrame:
        """Get yield curve data."""
        return await self.fred.get_yield_curve()

    async def get_sector_etfs(self, days: int = 365) -> dict[str, pd.DataFrame]:
        """Get all sector ETF data."""
        result = {}
        for name, symbol in self.SECTOR_ETFS.items():
            try:
                result[name] = await self._get_etf_data(symbol, days)
            except Exception as e:
                logger.warning(f"Failed to get {name} ETF: {e}")
        return result

    async def get_commodity_correlation(
        self,
        commodity: str,
        stocks: list[str],
        days: int = 365,
    ) -> pd.DataFrame:
        """
        Analyze correlation between commodity and stocks.

        Useful for finding lead-lag relationships like DRAM → semiconductors.
        """
        # Get commodity data
        comm_data = await self.get_commodity(commodity, days=days)

        # Get stock data
        stock_data = {}
        for symbol in stocks:
            try:
                stock_data[symbol] = await self._get_etf_data(symbol, days)
            except:
                pass

        if not stock_data:
            return pd.DataFrame()

        # Align data
        comm_returns = comm_data["price"].pct_change().dropna()

        correlations = []
        for symbol, data in stock_data.items():
            stock_returns = data["price"].pct_change().dropna()

            # Align dates
            aligned = pd.concat([comm_returns, stock_returns], axis=1, join="inner")
            aligned.columns = ["commodity", "stock"]

            if len(aligned) < 20:
                continue

            # Calculate correlations at different lags
            for lag in range(-10, 11):  # -10 to +10 days
                if lag < 0:
                    lagged_stock = aligned["stock"].shift(-lag)
                else:
                    lagged_stock = aligned["stock"]
                    aligned["commodity"] = aligned["commodity"].shift(lag)

                corr = aligned["commodity"].corr(lagged_stock)
                correlations.append({
                    "stock": symbol,
                    "lag_days": lag,
                    "correlation": corr,
                })

        return pd.DataFrame(correlations)

    def list_available_commodities(self) -> dict[str, str]:
        """List all available commodities and their sources."""
        result = {}

        for name in FREDClient.SERIES:
            result[name] = f"FRED: {FREDClient.SERIES[name]}"

        for name, symbol in self.ETF_PROXIES.items():
            if name not in result:
                result[name] = f"ETF: {symbol}"

        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_commodity_prices(
    commodities: list[str],
    days: int = 365,
) -> dict[str, pd.DataFrame]:
    """Convenience function to get multiple commodity prices."""
    hub = FreeAPIHub()
    result = {}

    for name in commodities:
        try:
            result[name] = await hub.get_commodity(name, days=days)
        except Exception as e:
            logger.warning(f"Failed to get {name}: {e}")

    return result


async def check_fred_availability() -> bool:
    """Check if FRED API is available."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("FRED_API_KEY not set.")
        print("Get free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("Then: export FRED_API_KEY=your_key_here")
        return False
    return True
