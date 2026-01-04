"""ETF flows data source for sector rotation and market sentiment.

Estimates ETF fund flows from changes in shares outstanding and tracks
sector rotation patterns for trading signals.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
import numpy as np
import pandas as pd

from ....core import Symbol

logger = logging.getLogger(__name__)


class ETFCategory(str, Enum):
    """ETF category classification."""

    EQUITY_US_LARGE = "equity_us_large"
    EQUITY_US_MID = "equity_us_mid"
    EQUITY_US_SMALL = "equity_us_small"
    EQUITY_INTL_DEVELOPED = "equity_intl_developed"
    EQUITY_EMERGING = "equity_emerging"
    SECTOR_TECH = "sector_tech"
    SECTOR_HEALTHCARE = "sector_healthcare"
    SECTOR_FINANCIALS = "sector_financials"
    SECTOR_ENERGY = "sector_energy"
    SECTOR_MATERIALS = "sector_materials"
    SECTOR_INDUSTRIALS = "sector_industrials"
    SECTOR_CONSUMER_DISC = "sector_consumer_disc"
    SECTOR_CONSUMER_STAPLES = "sector_consumer_staples"
    SECTOR_UTILITIES = "sector_utilities"
    SECTOR_REAL_ESTATE = "sector_real_estate"
    SECTOR_COMM_SERVICES = "sector_comm_services"
    FIXED_INCOME = "fixed_income"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    VOLATILITY = "volatility"
    LEVERAGE = "leverage"
    INVERSE = "inverse"


# Popular ETFs by category
ETF_UNIVERSE = {
    ETFCategory.EQUITY_US_LARGE: ["SPY", "IVV", "VOO", "QQQ", "DIA"],
    ETFCategory.EQUITY_US_MID: ["IJH", "VO", "MDY"],
    ETFCategory.EQUITY_US_SMALL: ["IWM", "IJR", "VB"],
    ETFCategory.EQUITY_INTL_DEVELOPED: ["EFA", "VEA", "IEFA"],
    ETFCategory.EQUITY_EMERGING: ["EEM", "VWO", "IEMG"],
    ETFCategory.SECTOR_TECH: ["XLK", "VGT", "QQQ"],
    ETFCategory.SECTOR_HEALTHCARE: ["XLV", "VHT", "IBB"],
    ETFCategory.SECTOR_FINANCIALS: ["XLF", "VFH", "KRE"],
    ETFCategory.SECTOR_ENERGY: ["XLE", "VDE", "OIH"],
    ETFCategory.SECTOR_MATERIALS: ["XLB", "VAW"],
    ETFCategory.SECTOR_INDUSTRIALS: ["XLI", "VIS"],
    ETFCategory.SECTOR_CONSUMER_DISC: ["XLY", "VCR"],
    ETFCategory.SECTOR_CONSUMER_STAPLES: ["XLP", "VDC"],
    ETFCategory.SECTOR_UTILITIES: ["XLU", "VPU"],
    ETFCategory.SECTOR_REAL_ESTATE: ["XLRE", "VNQ", "IYR"],
    ETFCategory.SECTOR_COMM_SERVICES: ["XLC", "VOX"],
    ETFCategory.FIXED_INCOME: ["TLT", "IEF", "AGG", "BND", "LQD", "HYG", "JNK"],
    ETFCategory.COMMODITY: ["GLD", "SLV", "USO", "UNG", "DBC"],
    ETFCategory.VOLATILITY: ["VXX", "UVXY", "SVXY"],
    ETFCategory.LEVERAGE: ["TQQQ", "SOXL", "SPXL", "UPRO"],
    ETFCategory.INVERSE: ["SQQQ", "SH", "PSQ", "SPXS"],
}


@dataclass
class ETFInfo:
    """ETF metadata and current state."""

    symbol: str
    name: str
    category: ETFCategory
    aum: float  # Assets under management
    expense_ratio: float
    shares_outstanding: int
    avg_volume: int
    inception_date: datetime | None = None
    holdings_count: int | None = None
    top_holdings: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "category": self.category.value,
            "aum": self.aum,
            "expense_ratio": self.expense_ratio,
            "shares_outstanding": self.shares_outstanding,
            "avg_volume": self.avg_volume,
            "holdings_count": self.holdings_count,
        }


@dataclass
class ETFFlowData:
    """ETF flow data point."""

    symbol: str
    date: datetime
    shares_outstanding: int
    shares_change: int
    price: float
    estimated_flow: float  # Shares change * price
    volume: int
    aum: float | None = None

    @property
    def flow_pct(self) -> float:
        """Flow as percentage of AUM."""
        if self.aum and self.aum > 0:
            return (self.estimated_flow / self.aum) * 100
        return 0

    @property
    def is_inflow(self) -> bool:
        """Check if this is an inflow."""
        return self.estimated_flow > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "shares_outstanding": self.shares_outstanding,
            "shares_change": self.shares_change,
            "price": self.price,
            "estimated_flow": self.estimated_flow,
            "flow_pct": self.flow_pct,
            "volume": self.volume,
        }


@dataclass
class SectorFlowSummary:
    """Aggregated sector flow summary."""

    category: ETFCategory
    period_start: datetime
    period_end: datetime
    total_inflow: float
    total_outflow: float
    net_flow: float
    etf_flows: dict[str, float]  # Symbol -> net flow
    avg_daily_flow: float
    flow_momentum: float  # Recent vs historical flow
    rank: int | None = None  # Relative ranking among sectors

    @property
    def flow_signal(self) -> str:
        """Determine flow signal strength."""
        if self.net_flow > 0 and self.flow_momentum > 1.5:
            return "strong_inflow"
        elif self.net_flow > 0:
            return "inflow"
        elif self.net_flow < 0 and self.flow_momentum < 0.5:
            return "strong_outflow"
        elif self.net_flow < 0:
            return "outflow"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_inflow": self.total_inflow,
            "total_outflow": self.total_outflow,
            "net_flow": self.net_flow,
            "avg_daily_flow": self.avg_daily_flow,
            "flow_momentum": self.flow_momentum,
            "flow_signal": self.flow_signal,
            "rank": self.rank,
        }


@dataclass
class RotationSignal:
    """Sector rotation trading signal."""

    timestamp: datetime
    rotating_from: list[ETFCategory]
    rotating_to: list[ETFCategory]
    confidence: float
    signal_type: str  # risk_on, risk_off, sector_rotation
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "rotating_from": [c.value for c in self.rotating_from],
            "rotating_to": [c.value for c in self.rotating_to],
            "confidence": self.confidence,
            "signal_type": self.signal_type,
            **self.details,
        }


class ETFFlowEstimator:
    """
    Estimates ETF fund flows from shares outstanding changes.

    ETF shares outstanding increase when money flows in (creation)
    and decrease when money flows out (redemption).
    """

    def __init__(self):
        """Initialize flow estimator."""
        self._shares_history: dict[str, list[tuple[datetime, int]]] = {}

    def estimate_flow(
        self,
        symbol: str,
        current_shares: int,
        previous_shares: int,
        price: float,
    ) -> float:
        """
        Estimate fund flow from shares outstanding change.

        Args:
            symbol: ETF symbol
            current_shares: Current shares outstanding
            previous_shares: Previous shares outstanding
            price: Current ETF price

        Returns:
            Estimated dollar flow (positive = inflow)
        """
        shares_change = current_shares - previous_shares
        return shares_change * price

    def calculate_flow_momentum(
        self,
        recent_flows: list[float],
        historical_flows: list[float],
    ) -> float:
        """
        Calculate flow momentum (recent vs historical).

        Args:
            recent_flows: Recent daily flows (e.g., last 5 days)
            historical_flows: Historical daily flows (e.g., last 20 days)

        Returns:
            Momentum ratio (>1 = accelerating inflows)
        """
        if not recent_flows or not historical_flows:
            return 1.0

        recent_avg = np.mean(recent_flows)
        historical_avg = np.mean(historical_flows)

        if historical_avg == 0:
            return 1.0 if recent_avg == 0 else float('inf')

        return recent_avg / abs(historical_avg)


class ETFFlowSource:
    """
    ETF flow data source.

    Fetches ETF data and estimates fund flows for trading signals.
    """

    name = "etf_flows"

    def __init__(
        self,
        polygon_key: str | None = None,
        finnhub_key: str | None = None,
        cache_ttl_minutes: int = 30,
    ):
        """
        Initialize ETF flow source.

        Args:
            polygon_key: Polygon.io API key
            finnhub_key: Finnhub API key
            cache_ttl_minutes: Cache TTL
        """
        self.polygon_key = polygon_key
        self.finnhub_key = finnhub_key
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None
        self._estimator = ETFFlowEstimator()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_cache(self, key: str) -> Any | None:
        """Check cache."""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache."""
        self._cache[key] = (datetime.now(), data)

    async def fetch_etf_info(self, symbol: Symbol) -> ETFInfo | None:
        """
        Fetch ETF information.

        Args:
            symbol: ETF symbol

        Returns:
            ETFInfo or None
        """
        cache_key = f"info:{symbol}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        info = None

        if self.polygon_key:
            info = await self._fetch_polygon_info(symbol)

        if info:
            self._update_cache(cache_key, info)

        return info

    async def _fetch_polygon_info(self, symbol: Symbol) -> ETFInfo | None:
        """Fetch ETF info from Polygon."""
        client = await self._get_client()

        try:
            # Get ticker details
            url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
            resp = await client.get(url, params={"apiKey": self.polygon_key})
            resp.raise_for_status()
            data = resp.json().get("results", {})

            # Determine category from market/type
            category = self._classify_etf(symbol, data)

            return ETFInfo(
                symbol=symbol,
                name=data.get("name", symbol),
                category=category,
                aum=float(data.get("market_cap", 0) or 0),
                expense_ratio=0,  # Not in basic API
                shares_outstanding=int(data.get("share_class_shares_outstanding", 0) or 0),
                avg_volume=int(data.get("weighted_shares_outstanding", 0) or 0),
            )

        except Exception as e:
            logger.error(f"Error fetching ETF info for {symbol}: {e}")
            return None

    def _classify_etf(self, symbol: str, data: dict) -> ETFCategory:
        """Classify ETF into category."""
        # Check known ETFs first
        for category, symbols in ETF_UNIVERSE.items():
            if symbol in symbols:
                return category

        # Default classification based on name/description
        name = (data.get("name", "") + " " + data.get("description", "")).upper()

        if "TECHNOLOGY" in name or "TECH" in name:
            return ETFCategory.SECTOR_TECH
        elif "HEALTHCARE" in name or "HEALTH" in name:
            return ETFCategory.SECTOR_HEALTHCARE
        elif "FINANCIAL" in name or "BANK" in name:
            return ETFCategory.SECTOR_FINANCIALS
        elif "ENERGY" in name or "OIL" in name:
            return ETFCategory.SECTOR_ENERGY
        elif "BOND" in name or "TREASURY" in name or "FIXED" in name:
            return ETFCategory.FIXED_INCOME
        elif "GOLD" in name or "SILVER" in name or "COMMODITY" in name:
            return ETFCategory.COMMODITY
        elif "EMERGING" in name:
            return ETFCategory.EQUITY_EMERGING
        elif "INTERNATIONAL" in name or "DEVELOPED" in name:
            return ETFCategory.EQUITY_INTL_DEVELOPED
        elif "SMALL" in name:
            return ETFCategory.EQUITY_US_SMALL
        elif "MID" in name:
            return ETFCategory.EQUITY_US_MID
        else:
            return ETFCategory.EQUITY_US_LARGE

    async def fetch_flow_history(
        self,
        symbol: Symbol,
        days: int = 30,
    ) -> list[ETFFlowData]:
        """
        Fetch historical flow data for an ETF.

        Args:
            symbol: ETF symbol
            days: Number of days

        Returns:
            List of ETFFlowData
        """
        cache_key = f"flow:{symbol}:{days}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        flows = []

        if self.polygon_key:
            flows = await self._fetch_polygon_flows(symbol, days)
        else:
            # Fall back to Yahoo Finance (free, no API key)
            flows = await self._fetch_yahoo_flows(symbol, days)

        if flows:
            self._update_cache(cache_key, flows)

        return flows

    async def _fetch_yahoo_flows(
        self,
        symbol: str,
        days: int,
    ) -> list[ETFFlowData]:
        """
        Estimate ETF flows from Yahoo Finance data.

        Uses volume patterns and price changes to estimate fund flows.
        This is an estimation based on publicly available data.

        Args:
            symbol: ETF symbol
            days: Number of days

        Returns:
            List of ETFFlowData
        """
        flows = []

        try:
            import yfinance as yf

            # Fetch historical data
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days + 10)  # Extra buffer

            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"No Yahoo data for {symbol}")
                return flows

            # Get shares outstanding if available
            try:
                info = ticker.info
                current_shares = info.get("sharesOutstanding", 0)
                avg_volume = info.get("averageVolume", hist["Volume"].mean())
            except Exception:
                current_shares = 0
                avg_volume = hist["Volume"].mean()

            # Calculate flow estimates based on:
            # 1. Volume relative to average (high volume = more creation/redemption)
            # 2. Price direction (up + high volume = likely inflow)
            # 3. Daily returns

            for i in range(1, len(hist)):
                try:
                    date = hist.index[i]
                    if isinstance(date, pd.Timestamp):
                        date = date.to_pydatetime()

                    close = float(hist["Close"].iloc[i])
                    prev_close = float(hist["Close"].iloc[i - 1])
                    volume = int(hist["Volume"].iloc[i])

                    # Volume ratio (how unusual is today's volume)
                    vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0

                    # Price change
                    price_change = (close - prev_close) / prev_close if prev_close > 0 else 0

                    # Flow estimation heuristic:
                    # High volume + positive return = likely inflow
                    # High volume + negative return = likely outflow
                    # Normal volume = minimal flow

                    flow_multiplier = (vol_ratio - 1) * np.sign(price_change) if vol_ratio > 1 else 0

                    # Estimate shares created/redeemed based on volume pattern
                    # This is a rough estimate - real data would come from ETF providers
                    estimated_shares_change = int(volume * 0.001 * flow_multiplier)

                    # Dollar flow estimate
                    estimated_flow = estimated_shares_change * close

                    flows.append(ETFFlowData(
                        symbol=symbol,
                        date=date,
                        shares_outstanding=current_shares,
                        shares_change=estimated_shares_change,
                        price=close,
                        estimated_flow=estimated_flow,
                        volume=volume,
                        aum=current_shares * close if current_shares > 0 else None,
                    ))

                except Exception as e:
                    logger.debug(f"Error processing {symbol} flow data: {e}")
                    continue

            logger.info(f"Estimated {len(flows)} days of flow data for {symbol}")

        except ImportError:
            logger.warning("yfinance not installed. Install with: pip install yfinance")
        except Exception as e:
            logger.error(f"Yahoo flow fetch error for {symbol}: {e}")

        return flows

    async def _fetch_polygon_flows(
        self,
        symbol: Symbol,
        days: int,
    ) -> list[ETFFlowData]:
        """Fetch flow data from Polygon."""
        client = await self._get_client()
        flows = []

        try:
            end = datetime.now()
            start = end - timedelta(days=days)

            # Get daily aggregates
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
            resp = await client.get(url, params={"apiKey": self.polygon_key, "adjusted": "true"})
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])

            # We need shares outstanding history - estimate from volume patterns
            # In production, this would come from a proper data source
            prev_shares = None

            for bar in results:
                timestamp = datetime.fromtimestamp(bar["t"] / 1000)
                close = bar["c"]
                volume = bar["v"]

                # Estimate shares outstanding change from relative volume
                # This is a simplified heuristic
                avg_volume = sum(r["v"] for r in results) / len(results)
                vol_ratio = volume / avg_volume if avg_volume > 0 else 1

                # Assume high volume days have more creation/redemption activity
                estimated_shares = int(volume * 0.01 * (vol_ratio - 1))

                if prev_shares is not None:
                    shares_change = estimated_shares
                    estimated_flow = shares_change * close

                    flows.append(ETFFlowData(
                        symbol=symbol,
                        date=timestamp,
                        shares_outstanding=0,  # Would need proper data source
                        shares_change=shares_change,
                        price=close,
                        estimated_flow=estimated_flow,
                        volume=volume,
                    ))

                prev_shares = estimated_shares

        except Exception as e:
            logger.error(f"Error fetching flows for {symbol}: {e}")

        return flows

    async def get_sector_flows(
        self,
        category: ETFCategory,
        days: int = 20,
    ) -> SectorFlowSummary:
        """
        Get aggregated sector flows.

        Args:
            category: ETF category
            days: Lookback period

        Returns:
            SectorFlowSummary
        """
        etfs = ETF_UNIVERSE.get(category, [])
        if not etfs:
            return SectorFlowSummary(
                category=category,
                period_start=datetime.now() - timedelta(days=days),
                period_end=datetime.now(),
                total_inflow=0,
                total_outflow=0,
                net_flow=0,
                etf_flows={},
                avg_daily_flow=0,
                flow_momentum=1.0,
            )

        etf_flows = {}
        all_daily_flows = []

        for symbol in etfs[:3]:  # Limit to avoid rate limits
            try:
                flows = await self.fetch_flow_history(symbol, days)

                if flows:
                    net = sum(f.estimated_flow for f in flows)
                    etf_flows[symbol] = net
                    all_daily_flows.extend([f.estimated_flow for f in flows])

                await asyncio.sleep(0.3)

            except Exception as e:
                logger.warning(f"Error fetching flows for {symbol}: {e}")

        total_inflow = sum(f for f in etf_flows.values() if f > 0)
        total_outflow = abs(sum(f for f in etf_flows.values() if f < 0))
        net_flow = sum(etf_flows.values())

        # Calculate momentum
        if all_daily_flows:
            recent = all_daily_flows[-5:] if len(all_daily_flows) >= 5 else all_daily_flows
            historical = all_daily_flows
            flow_momentum = self._estimator.calculate_flow_momentum(recent, historical)
        else:
            flow_momentum = 1.0

        return SectorFlowSummary(
            category=category,
            period_start=datetime.now() - timedelta(days=days),
            period_end=datetime.now(),
            total_inflow=total_inflow,
            total_outflow=total_outflow,
            net_flow=net_flow,
            etf_flows=etf_flows,
            avg_daily_flow=net_flow / days if days > 0 else 0,
            flow_momentum=flow_momentum,
        )

    async def get_all_sector_flows(
        self,
        days: int = 20,
    ) -> dict[ETFCategory, SectorFlowSummary]:
        """
        Get flows for all sectors.

        Args:
            days: Lookback period

        Returns:
            Dict mapping category to flow summary
        """
        sector_categories = [
            ETFCategory.SECTOR_TECH,
            ETFCategory.SECTOR_HEALTHCARE,
            ETFCategory.SECTOR_FINANCIALS,
            ETFCategory.SECTOR_ENERGY,
            ETFCategory.SECTOR_INDUSTRIALS,
            ETFCategory.SECTOR_CONSUMER_DISC,
            ETFCategory.SECTOR_CONSUMER_STAPLES,
            ETFCategory.SECTOR_UTILITIES,
            ETFCategory.SECTOR_REAL_ESTATE,
        ]

        results = {}

        for category in sector_categories:
            try:
                summary = await self.get_sector_flows(category, days)
                results[category] = summary
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error getting sector flows for {category}: {e}")

        # Rank sectors by net flow
        sorted_sectors = sorted(results.items(), key=lambda x: x[1].net_flow, reverse=True)
        for rank, (category, summary) in enumerate(sorted_sectors, 1):
            summary.rank = rank

        return results

    async def detect_rotation(
        self,
        days: int = 20,
        threshold: float = 0.1,
    ) -> RotationSignal | None:
        """
        Detect sector rotation patterns.

        Args:
            days: Lookback period
            threshold: Flow threshold for significance

        Returns:
            RotationSignal if rotation detected
        """
        sector_flows = await self.get_all_sector_flows(days)

        if not sector_flows:
            return None

        # Find sectors with significant inflows and outflows
        inflow_sectors = []
        outflow_sectors = []

        for category, summary in sector_flows.items():
            if summary.flow_signal in ["strong_inflow", "inflow"]:
                inflow_sectors.append(category)
            elif summary.flow_signal in ["strong_outflow", "outflow"]:
                outflow_sectors.append(category)

        if not inflow_sectors and not outflow_sectors:
            return None

        # Determine rotation type
        defensive = {
            ETFCategory.SECTOR_UTILITIES,
            ETFCategory.SECTOR_CONSUMER_STAPLES,
            ETFCategory.SECTOR_HEALTHCARE,
        }
        cyclical = {
            ETFCategory.SECTOR_TECH,
            ETFCategory.SECTOR_CONSUMER_DISC,
            ETFCategory.SECTOR_INDUSTRIALS,
            ETFCategory.SECTOR_FINANCIALS,
        }

        inflow_defensive = len(set(inflow_sectors) & defensive)
        inflow_cyclical = len(set(inflow_sectors) & cyclical)
        outflow_defensive = len(set(outflow_sectors) & defensive)
        outflow_cyclical = len(set(outflow_sectors) & cyclical)

        # Risk-off: money flowing to defensive, out of cyclical
        if inflow_defensive > outflow_defensive and outflow_cyclical > inflow_cyclical:
            signal_type = "risk_off"
            confidence = min(0.9, 0.5 + 0.1 * (inflow_defensive + outflow_cyclical))
        # Risk-on: money flowing to cyclical, out of defensive
        elif inflow_cyclical > outflow_cyclical and outflow_defensive > inflow_defensive:
            signal_type = "risk_on"
            confidence = min(0.9, 0.5 + 0.1 * (inflow_cyclical + outflow_defensive))
        else:
            signal_type = "sector_rotation"
            confidence = 0.5

        return RotationSignal(
            timestamp=datetime.now(),
            rotating_from=outflow_sectors,
            rotating_to=inflow_sectors,
            confidence=confidence,
            signal_type=signal_type,
            details={
                "inflow_count": len(inflow_sectors),
                "outflow_count": len(outflow_sectors),
            },
        )

    def to_dataframe(self, flows: list[ETFFlowData]) -> pd.DataFrame:
        """Convert flows to DataFrame."""
        if not flows:
            return pd.DataFrame()

        records = [f.to_dict() for f in flows]
        df = pd.DataFrame(records)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()

        return df


class RiskAppetiteIndicator:
    """
    Risk appetite indicator from ETF flows.

    Monitors flows between risk-on and risk-off assets.
    """

    RISK_ON_ETFS = ["SPY", "QQQ", "IWM", "HYG", "EEM"]
    RISK_OFF_ETFS = ["TLT", "GLD", "VXX", "AGG"]

    def __init__(self, flow_source: ETFFlowSource):
        """Initialize indicator."""
        self.flow_source = flow_source

    async def calculate(self, days: int = 20) -> dict[str, float]:
        """
        Calculate risk appetite indicator.

        Returns:
            Dict with indicator value and components
        """
        risk_on_flow = 0
        risk_off_flow = 0

        for symbol in self.RISK_ON_ETFS[:3]:
            try:
                flows = await self.flow_source.fetch_flow_history(symbol, days)
                risk_on_flow += sum(f.estimated_flow for f in flows)
                await asyncio.sleep(0.2)
            except Exception:
                pass

        for symbol in self.RISK_OFF_ETFS[:3]:
            try:
                flows = await self.flow_source.fetch_flow_history(symbol, days)
                risk_off_flow += sum(f.estimated_flow for f in flows)
                await asyncio.sleep(0.2)
            except Exception:
                pass

        # Calculate indicator (-1 to 1)
        total_flow = abs(risk_on_flow) + abs(risk_off_flow)

        if total_flow == 0:
            indicator = 0
        else:
            indicator = (risk_on_flow - risk_off_flow) / total_flow

        # Determine signal
        if indicator > 0.3:
            signal = "risk_on"
        elif indicator < -0.3:
            signal = "risk_off"
        else:
            signal = "neutral"

        return {
            "indicator": indicator,
            "risk_on_flow": risk_on_flow,
            "risk_off_flow": risk_off_flow,
            "signal": signal,
        }


async def fetch_sector_flows(
    category: ETFCategory | None = None,
    days: int = 20,
    polygon_key: str | None = None,
) -> dict[ETFCategory, SectorFlowSummary] | SectorFlowSummary:
    """
    Convenience function to fetch sector flows.

    Args:
        category: Specific category or None for all
        days: Lookback period
        polygon_key: Polygon API key

    Returns:
        SectorFlowSummary or dict of summaries
    """
    source = ETFFlowSource(polygon_key=polygon_key)

    try:
        if category:
            return await source.get_sector_flows(category, days)
        else:
            return await source.get_all_sector_flows(days)
    finally:
        await source.close()


async def detect_sector_rotation(
    days: int = 20,
    polygon_key: str | None = None,
) -> RotationSignal | None:
    """
    Detect sector rotation.

    Args:
        days: Lookback period
        polygon_key: Polygon API key

    Returns:
        RotationSignal if detected
    """
    source = ETFFlowSource(polygon_key=polygon_key)

    try:
        return await source.detect_rotation(days)
    finally:
        await source.close()


async def estimate_etf_flows(
    symbols: list[str],
    days: int = 20,
) -> pd.DataFrame:
    """
    Estimate ETF flows for a list of symbols using Yahoo Finance.

    Args:
        symbols: List of ETF symbols
        days: Lookback period

    Returns:
        DataFrame with flow estimates
    """
    source = ETFFlowSource()  # No API key needed for Yahoo

    try:
        all_flows = []

        for symbol in symbols:
            try:
                flows = await source.fetch_flow_history(symbol, days)

                for f in flows:
                    all_flows.append({
                        "symbol": f.symbol,
                        "date": f.date,
                        "price": f.price,
                        "volume": f.volume,
                        "estimated_flow": f.estimated_flow,
                        "flow_pct": f.flow_pct,
                    })

            except Exception as e:
                logger.warning(f"Error fetching flows for {symbol}: {e}")

        if not all_flows:
            return pd.DataFrame()

        df = pd.DataFrame(all_flows)
        df["date"] = pd.to_datetime(df["date"])

        return df

    finally:
        await source.close()


async def get_quick_sector_snapshot() -> dict[str, Any]:
    """
    Get a quick sector flow snapshot using free data.

    Returns summary of recent sector flows estimated from Yahoo data.
    """
    source = ETFFlowSource()  # No API key needed

    try:
        # Use one representative ETF per sector
        sector_etfs = {
            "tech": "XLK",
            "healthcare": "XLV",
            "financials": "XLF",
            "energy": "XLE",
            "industrials": "XLI",
            "consumer_disc": "XLY",
            "consumer_staples": "XLP",
            "utilities": "XLU",
            "materials": "XLB",
            "real_estate": "XLRE",
        }

        results = {}

        for sector, symbol in sector_etfs.items():
            try:
                flows = await source.fetch_flow_history(symbol, 20)

                if flows:
                    net_flow = sum(f.estimated_flow for f in flows)
                    recent_flow = sum(f.estimated_flow for f in flows[-5:])
                    older_flow = sum(f.estimated_flow for f in flows[:-5]) if len(flows) > 5 else 0

                    # Momentum: compare recent vs older
                    if older_flow != 0:
                        momentum = recent_flow / abs(older_flow)
                    else:
                        momentum = 1.0 if recent_flow == 0 else float('inf')

                    results[sector] = {
                        "symbol": symbol,
                        "net_flow_20d": round(net_flow, 0),
                        "recent_flow_5d": round(recent_flow, 0),
                        "momentum": round(momentum, 2),
                        "signal": "inflow" if net_flow > 0 else "outflow" if net_flow < 0 else "neutral",
                    }

            except Exception as e:
                logger.warning(f"Error getting {sector} flow: {e}")
                results[sector] = {"error": str(e)}

        # Rank sectors
        sorted_sectors = sorted(
            [(k, v) for k, v in results.items() if "net_flow_20d" in v],
            key=lambda x: x[1]["net_flow_20d"],
            reverse=True,
        )

        for rank, (sector, _) in enumerate(sorted_sectors, 1):
            results[sector]["rank"] = rank

        # Identify rotation
        top_inflows = [s for s, v in sorted_sectors[:3] if v.get("net_flow_20d", 0) > 0]
        top_outflows = [s for s, v in sorted_sectors[-3:] if v.get("net_flow_20d", 0) < 0]

        return {
            "sectors": results,
            "top_inflows": top_inflows,
            "top_outflows": top_outflows,
            "timestamp": datetime.now().isoformat(),
        }

    finally:
        await source.close()


def get_etf_flow_features(flows: list[ETFFlowData]) -> dict[str, float]:
    """
    Extract features from ETF flow data for ML strategies.

    Args:
        flows: List of ETFFlowData

    Returns:
        Dictionary of features
    """
    if not flows:
        return {
            "net_flow": 0,
            "flow_momentum": 1.0,
            "flow_volatility": 0,
            "inflow_days_pct": 0.5,
            "avg_daily_flow": 0,
        }

    daily_flows = [f.estimated_flow for f in flows]

    net_flow = sum(daily_flows)
    avg_flow = np.mean(daily_flows)
    flow_std = np.std(daily_flows) if len(daily_flows) > 1 else 0

    # Momentum: recent 5 days vs previous
    recent = daily_flows[-5:] if len(daily_flows) >= 5 else daily_flows
    older = daily_flows[:-5] if len(daily_flows) > 5 else [0]

    recent_avg = np.mean(recent)
    older_avg = np.mean(older)

    if older_avg != 0:
        momentum = recent_avg / abs(older_avg)
    else:
        momentum = 1.0

    # Inflow days percentage
    inflow_days = sum(1 for f in daily_flows if f > 0)
    inflow_pct = inflow_days / len(daily_flows) if daily_flows else 0.5

    return {
        "net_flow": round(net_flow, 2),
        "flow_momentum": round(momentum, 4),
        "flow_volatility": round(flow_std, 2),
        "inflow_days_pct": round(inflow_pct, 4),
        "avg_daily_flow": round(avg_flow, 2),
    }
