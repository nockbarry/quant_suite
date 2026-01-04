"""Asset Universe Manager with metadata, categorization, and caching."""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import yfinance as yf

from .asset import Asset, Universe
from .types import AssetType, Symbol

logger = logging.getLogger(__name__)


class MarketCapTier(str, Enum):
    """Market capitalization tiers."""

    MEGA = "mega"  # > $200B
    LARGE = "large"  # $10B - $200B
    MID = "mid"  # $2B - $10B
    SMALL = "small"  # $300M - $2B
    MICRO = "micro"  # < $300M
    UNKNOWN = "unknown"

    @classmethod
    def from_market_cap(cls, market_cap: float | None) -> "MarketCapTier":
        """Classify market cap into tier."""
        if market_cap is None:
            return cls.UNKNOWN
        if market_cap >= 200_000_000_000:
            return cls.MEGA
        if market_cap >= 10_000_000_000:
            return cls.LARGE
        if market_cap >= 2_000_000_000:
            return cls.MID
        if market_cap >= 300_000_000:
            return cls.SMALL
        return cls.MICRO


class LiquidityTier(str, Enum):
    """Liquidity classification based on average daily volume."""

    HIGH = "high"  # > 5M shares/day
    MEDIUM = "medium"  # 500K - 5M shares/day
    LOW = "low"  # < 500K shares/day
    UNKNOWN = "unknown"

    @classmethod
    def from_volume(cls, avg_volume: float | None) -> "LiquidityTier":
        """Classify average volume into tier."""
        if avg_volume is None:
            return cls.UNKNOWN
        if avg_volume >= 5_000_000:
            return cls.HIGH
        if avg_volume >= 500_000:
            return cls.MEDIUM
        return cls.LOW


class StyleFactor(str, Enum):
    """Investment style factors."""

    VALUE = "value"
    GROWTH = "growth"
    MOMENTUM = "momentum"
    QUALITY = "quality"
    DIVIDEND = "dividend"
    UNKNOWN = "unknown"


@dataclass
class AssetMetadata:
    """Extended metadata for an asset."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    market_cap_tier: MarketCapTier = MarketCapTier.UNKNOWN
    avg_volume: float | None = None
    liquidity_tier: LiquidityTier = LiquidityTier.UNKNOWN
    price: float | None = None
    beta: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    style_factors: list[StyleFactor] = field(default_factory=list)
    last_updated: datetime | None = None

    def is_budget_eligible(
        self,
        min_price: float = 1.0,
        max_price: float = 100.0,
        min_volume: float = 200_000,
        min_market_cap: float = 500_000_000,
        max_market_cap: float = 10_000_000_000,
    ) -> bool:
        """Check if asset meets budget trading criteria."""
        if self.price is None or self.avg_volume is None or self.market_cap is None:
            return False
        return (
            min_price <= self.price <= max_price
            and self.avg_volume >= min_volume
            and min_market_cap <= self.market_cap <= max_market_cap
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "market_cap_tier": self.market_cap_tier.value,
            "avg_volume": self.avg_volume,
            "liquidity_tier": self.liquidity_tier.value,
            "price": self.price,
            "beta": self.beta,
            "pe_ratio": self.pe_ratio,
            "pb_ratio": self.pb_ratio,
            "dividend_yield": self.dividend_yield,
            "profit_margin": self.profit_margin,
            "revenue_growth": self.revenue_growth,
            "style_factors": [sf.value for sf in self.style_factors],
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class UniverseFilters:
    """Filters for universe screening."""

    min_price: float | None = None
    max_price: float | None = None
    min_volume: float | None = None
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    market_cap_tiers: list[MarketCapTier] | None = None
    liquidity_tiers: list[LiquidityTier] | None = None
    sectors: list[str] | None = None
    exclude_sectors: list[str] | None = None
    style_factors: list[StyleFactor] | None = None
    budget_eligible_only: bool = False


class UniverseManager:
    """
    Manages asset universes with metadata, categorization, and caching.

    Features:
    - Fetches metadata from yfinance
    - Caches data in SQLite with configurable TTL
    - Classifies assets by market cap, liquidity, and style
    - Filters universes by multiple criteria
    - Parses ETF holdings for universe construction
    """

    DEFAULT_CACHE_PATH = Path.home() / ".quant_cache" / "universe_metadata.db"
    DEFAULT_TTL_HOURS = 24

    def __init__(
        self,
        cache_path: Path | str | None = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        """
        Initialize universe manager.

        Args:
            cache_path: Path to SQLite cache database
            ttl_hours: Time-to-live for cached data in hours
        """
        self.cache_path = Path(cache_path) if cache_path else self.DEFAULT_CACHE_PATH
        self.ttl = timedelta(hours=ttl_hours)
        self._init_cache()

    def _init_cache(self) -> None:
        """Initialize SQLite cache database."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_metadata (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    industry TEXT,
                    market_cap REAL,
                    market_cap_tier TEXT,
                    avg_volume REAL,
                    liquidity_tier TEXT,
                    price REAL,
                    beta REAL,
                    pe_ratio REAL,
                    pb_ratio REAL,
                    dividend_yield REAL,
                    profit_margin REAL,
                    revenue_growth REAL,
                    style_factors TEXT,
                    last_updated TEXT
                )
            """)
            conn.commit()

    def get_metadata(
        self,
        symbol: Symbol,
        force_refresh: bool = False,
    ) -> AssetMetadata:
        """
        Get metadata for a symbol, using cache if available.

        Args:
            symbol: Stock symbol
            force_refresh: Force fetch from yfinance even if cached

        Returns:
            AssetMetadata for the symbol
        """
        if not force_refresh:
            cached = self._get_cached(symbol)
            if cached is not None:
                return cached

        return self._fetch_and_cache(symbol)

    def get_metadata_batch(
        self,
        symbols: list[Symbol],
        force_refresh: bool = False,
    ) -> dict[Symbol, AssetMetadata]:
        """
        Get metadata for multiple symbols efficiently.

        Args:
            symbols: List of stock symbols
            force_refresh: Force fetch from yfinance

        Returns:
            Dict mapping symbols to their metadata
        """
        result: dict[Symbol, AssetMetadata] = {}
        to_fetch: list[Symbol] = []

        if not force_refresh:
            for symbol in symbols:
                cached = self._get_cached(symbol)
                if cached is not None:
                    result[symbol] = cached
                else:
                    to_fetch.append(symbol)
        else:
            to_fetch = symbols

        if to_fetch:
            fetched = self._fetch_batch(to_fetch)
            result.update(fetched)

        return result

    def _get_cached(self, symbol: Symbol) -> AssetMetadata | None:
        """Get metadata from cache if not expired."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM asset_metadata WHERE symbol = ?",
                (symbol,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        last_updated = datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None
        if last_updated is None or datetime.now() - last_updated > self.ttl:
            return None

        style_factors_str = row["style_factors"] or ""
        style_factors = [
            StyleFactor(sf) for sf in style_factors_str.split(",") if sf
        ]

        return AssetMetadata(
            symbol=row["symbol"],
            name=row["name"],
            sector=row["sector"],
            industry=row["industry"],
            market_cap=row["market_cap"],
            market_cap_tier=MarketCapTier(row["market_cap_tier"]) if row["market_cap_tier"] else MarketCapTier.UNKNOWN,
            avg_volume=row["avg_volume"],
            liquidity_tier=LiquidityTier(row["liquidity_tier"]) if row["liquidity_tier"] else LiquidityTier.UNKNOWN,
            price=row["price"],
            beta=row["beta"],
            pe_ratio=row["pe_ratio"],
            pb_ratio=row["pb_ratio"],
            dividend_yield=row["dividend_yield"],
            profit_margin=row["profit_margin"],
            revenue_growth=row["revenue_growth"],
            style_factors=style_factors,
            last_updated=last_updated,
        )

    def _fetch_and_cache(self, symbol: Symbol) -> AssetMetadata:
        """Fetch metadata from yfinance and cache it."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            metadata = self._parse_yfinance_info(symbol, info)
            self._cache_metadata(metadata)
            return metadata
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {symbol}: {e}")
            return AssetMetadata(symbol=symbol, last_updated=datetime.now())

    def _fetch_batch(self, symbols: list[Symbol]) -> dict[Symbol, AssetMetadata]:
        """Fetch metadata for multiple symbols."""
        result: dict[Symbol, AssetMetadata] = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                metadata = self._parse_yfinance_info(symbol, info)
                self._cache_metadata(metadata)
                result[symbol] = metadata
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for {symbol}: {e}")
                result[symbol] = AssetMetadata(symbol=symbol, last_updated=datetime.now())

        return result

    def _parse_yfinance_info(self, symbol: str, info: dict) -> AssetMetadata:
        """Parse yfinance info dict into AssetMetadata."""
        market_cap = info.get("marketCap")
        avg_volume = info.get("averageVolume")

        pe_ratio = info.get("trailingPE")
        pb_ratio = info.get("priceToBook")
        dividend_yield = info.get("dividendYield")
        profit_margin = info.get("profitMargins")
        revenue_growth = info.get("revenueGrowth")

        style_factors = self._classify_style_factors(
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield,
            profit_margin=profit_margin,
            revenue_growth=revenue_growth,
        )

        return AssetMetadata(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=market_cap,
            market_cap_tier=MarketCapTier.from_market_cap(market_cap),
            avg_volume=avg_volume,
            liquidity_tier=LiquidityTier.from_volume(avg_volume),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            beta=info.get("beta"),
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield,
            profit_margin=profit_margin,
            revenue_growth=revenue_growth,
            style_factors=style_factors,
            last_updated=datetime.now(),
        )

    def _classify_style_factors(
        self,
        pe_ratio: float | None,
        pb_ratio: float | None,
        dividend_yield: float | None,
        profit_margin: float | None,
        revenue_growth: float | None,
    ) -> list[StyleFactor]:
        """Classify asset into style factors based on fundamentals."""
        factors = []

        # Value: Low P/E and low P/B
        if pe_ratio is not None and pb_ratio is not None:
            if pe_ratio < 15 and pb_ratio < 2:
                factors.append(StyleFactor.VALUE)

        # Growth: High revenue growth
        if revenue_growth is not None and revenue_growth > 0.15:
            factors.append(StyleFactor.GROWTH)

        # Quality: High profit margin
        if profit_margin is not None and profit_margin > 0.15:
            factors.append(StyleFactor.QUALITY)

        # Dividend: High dividend yield
        if dividend_yield is not None and dividend_yield > 0.02:
            factors.append(StyleFactor.DIVIDEND)

        return factors if factors else [StyleFactor.UNKNOWN]

    def _cache_metadata(self, metadata: AssetMetadata) -> None:
        """Save metadata to cache."""
        style_factors_str = ",".join(sf.value for sf in metadata.style_factors)

        with sqlite3.connect(self.cache_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO asset_metadata
                (symbol, name, sector, industry, market_cap, market_cap_tier,
                 avg_volume, liquidity_tier, price, beta, pe_ratio, pb_ratio,
                 dividend_yield, profit_margin, revenue_growth, style_factors, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.symbol,
                metadata.name,
                metadata.sector,
                metadata.industry,
                metadata.market_cap,
                metadata.market_cap_tier.value,
                metadata.avg_volume,
                metadata.liquidity_tier.value,
                metadata.price,
                metadata.beta,
                metadata.pe_ratio,
                metadata.pb_ratio,
                metadata.dividend_yield,
                metadata.profit_margin,
                metadata.revenue_growth,
                style_factors_str,
                metadata.last_updated.isoformat() if metadata.last_updated else None,
            ))
            conn.commit()

    def filter_universe(
        self,
        symbols: list[Symbol],
        filters: UniverseFilters,
    ) -> list[Symbol]:
        """
        Filter symbols based on criteria.

        Args:
            symbols: List of symbols to filter
            filters: Filtering criteria

        Returns:
            List of symbols matching all criteria
        """
        metadata_map = self.get_metadata_batch(symbols)
        result = []

        for symbol, meta in metadata_map.items():
            if self._matches_filters(meta, filters):
                result.append(symbol)

        return result

    def _matches_filters(self, meta: AssetMetadata, filters: UniverseFilters) -> bool:
        """Check if metadata matches all filters."""
        # Budget eligibility check
        if filters.budget_eligible_only and not meta.is_budget_eligible():
            return False

        # Price filters
        if filters.min_price is not None and (meta.price is None or meta.price < filters.min_price):
            return False
        if filters.max_price is not None and (meta.price is None or meta.price > filters.max_price):
            return False

        # Volume filter
        if filters.min_volume is not None and (meta.avg_volume is None or meta.avg_volume < filters.min_volume):
            return False

        # Market cap filters
        if filters.min_market_cap is not None and (meta.market_cap is None or meta.market_cap < filters.min_market_cap):
            return False
        if filters.max_market_cap is not None and (meta.market_cap is None or meta.market_cap > filters.max_market_cap):
            return False

        # Tier filters
        if filters.market_cap_tiers and meta.market_cap_tier not in filters.market_cap_tiers:
            return False
        if filters.liquidity_tiers and meta.liquidity_tier not in filters.liquidity_tiers:
            return False

        # Sector filters
        if filters.sectors and meta.sector not in filters.sectors:
            return False
        if filters.exclude_sectors and meta.sector in filters.exclude_sectors:
            return False

        # Style factor filter
        if filters.style_factors:
            if not any(sf in meta.style_factors for sf in filters.style_factors):
                return False

        return True

    def create_filtered_universe(
        self,
        name: str,
        source_symbols: list[Symbol],
        filters: UniverseFilters,
    ) -> Universe:
        """
        Create a new universe by filtering source symbols.

        Args:
            name: Name for the new universe
            source_symbols: Symbols to filter
            filters: Filtering criteria

        Returns:
            Universe containing matching assets
        """
        filtered_symbols = self.filter_universe(source_symbols, filters)
        metadata_map = self.get_metadata_batch(filtered_symbols)

        assets = []
        for symbol in filtered_symbols:
            meta = metadata_map.get(symbol)
            if meta:
                asset = Asset(
                    symbol=symbol,
                    asset_type=AssetType.EQUITY,
                    name=meta.name,
                    sector=meta.sector,
                    industry=meta.industry,
                    metadata={
                        "market_cap": meta.market_cap,
                        "market_cap_tier": meta.market_cap_tier.value,
                        "liquidity_tier": meta.liquidity_tier.value,
                        "price": meta.price,
                    },
                )
                assets.append(asset)

        return Universe(name=name, assets=assets)

    def get_budget_universe(
        self,
        source_symbols: list[Symbol],
        name: str = "budget_picks",
    ) -> Universe:
        """
        Create a universe of budget-friendly stocks.

        Criteria:
        - Market cap: $500M - $10B (small/mid cap)
        - Price: $1 - $100
        - Volume: > 200k shares/day

        Args:
            source_symbols: Symbols to filter
            name: Name for the universe

        Returns:
            Universe of budget-eligible stocks
        """
        filters = UniverseFilters(
            min_price=1.0,
            max_price=100.0,
            min_volume=200_000,
            min_market_cap=500_000_000,
            max_market_cap=10_000_000_000,
        )
        return self.create_filtered_universe(name, source_symbols, filters)

    def from_etf(self, etf_symbol: str) -> list[Symbol]:
        """
        Get holdings from an ETF.

        Args:
            etf_symbol: ETF ticker (e.g., "SPY", "QQQ", "IWM")

        Returns:
            List of constituent symbols
        """
        try:
            etf = yf.Ticker(etf_symbol)

            # Try to get holdings from yfinance
            # Note: yfinance may not always have holdings data
            holdings = getattr(etf, "holdings", None)
            if holdings is not None and len(holdings) > 0:
                return list(holdings.index)

            # Fallback: Use predefined lists for common ETFs
            return self._get_etf_fallback(etf_symbol)
        except Exception as e:
            logger.warning(f"Failed to get ETF holdings for {etf_symbol}: {e}")
            return self._get_etf_fallback(etf_symbol)

    def _get_etf_fallback(self, etf_symbol: str) -> list[Symbol]:
        """Get predefined holdings for common ETFs."""
        from .asset import SP500_TOP_50

        fallbacks = {
            "SPY": SP500_TOP_50,
            "QQQ": [
                "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "AVGO",
                "TSLA", "COST", "ADBE", "PEP", "CSCO", "NFLX", "AMD", "TMUS",
                "CMCSA", "TXN", "INTC", "INTU", "AMGN", "HON", "QCOM", "AMAT",
                "ISRG", "BKNG", "SBUX", "VRTX", "GILD", "ADI",
            ],
            "IWM": [
                # Russell 2000 top holdings (sample)
                "SMCI", "SAIA", "ENPH", "GNRC", "MTDR", "TMDX", "CROX",
                "DOCS", "CABO", "ONTO", "LSCC", "RMBS", "KYMR", "CVLT",
                "CALM", "CRVL", "SFBS", "SHAK", "MOD", "STEP",
            ],
        }
        return fallbacks.get(etf_symbol.upper(), [])

    def get_sector_breakdown(self, symbols: list[Symbol]) -> dict[str, list[Symbol]]:
        """Get symbols grouped by sector."""
        metadata_map = self.get_metadata_batch(symbols)
        breakdown: dict[str, list[Symbol]] = {}

        for symbol, meta in metadata_map.items():
            sector = meta.sector or "Unknown"
            if sector not in breakdown:
                breakdown[sector] = []
            breakdown[sector].append(symbol)

        return breakdown

    def get_market_cap_breakdown(self, symbols: list[Symbol]) -> dict[MarketCapTier, list[Symbol]]:
        """Get symbols grouped by market cap tier."""
        metadata_map = self.get_metadata_batch(symbols)
        breakdown: dict[MarketCapTier, list[Symbol]] = {}

        for symbol, meta in metadata_map.items():
            tier = meta.market_cap_tier
            if tier not in breakdown:
                breakdown[tier] = []
            breakdown[tier].append(symbol)

        return breakdown

    def clear_cache(self) -> None:
        """Clear all cached metadata."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute("DELETE FROM asset_metadata")
            conn.commit()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.cache_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM asset_metadata")
            total = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM asset_metadata WHERE last_updated > ?",
                ((datetime.now() - self.ttl).isoformat(),),
            )
            valid = cursor.fetchone()[0]

        return {
            "total_cached": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
            "cache_path": str(self.cache_path),
            "ttl_hours": self.ttl.total_seconds() / 3600,
        }
