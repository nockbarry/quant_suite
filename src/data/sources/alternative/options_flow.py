"""Options flow data source for unusual options activity.

Analyzes put/call ratios, unusual volume, and whale activity for trading signals.
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


class OptionType(str, Enum):
    """Option contract type."""

    CALL = "call"
    PUT = "put"


class UnusualActivityType(str, Enum):
    """Types of unusual options activity."""

    SWEEP = "sweep"  # Aggressive multi-exchange fill
    BLOCK = "block"  # Large single transaction
    SPLIT = "split"  # Large order split across time
    GOLDEN_SWEEP = "golden_sweep"  # Sweep on ask with large premium


@dataclass
class OptionContract:
    """Single options contract data."""

    symbol: str
    underlying: str
    option_type: OptionType
    strike: float
    expiration: datetime
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None

    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Calculate spread as percentage of mid."""
        mid = self.mid_price
        return (self.spread / mid * 100) if mid > 0 else 0

    @property
    def days_to_expiry(self) -> int:
        """Days until expiration."""
        return max(0, (self.expiration - datetime.now()).days)

    @property
    def is_itm(self) -> bool:
        """Check if in-the-money (requires underlying price)."""
        return False  # Would need underlying price

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "option_type": self.option_type.value,
            "strike": self.strike,
            "expiration": self.expiration.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last_price": self.last_price,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
            "days_to_expiry": self.days_to_expiry,
        }


@dataclass
class UnusualActivity:
    """Unusual options activity alert."""

    underlying: str
    option_type: OptionType
    strike: float
    expiration: datetime
    activity_type: UnusualActivityType
    volume: int
    open_interest: int
    premium: float  # Total $ traded
    spot_price: float
    timestamp: datetime
    sentiment: str  # bullish, bearish, neutral
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def volume_oi_ratio(self) -> float:
        """Volume to open interest ratio."""
        return self.volume / self.open_interest if self.open_interest > 0 else float('inf')

    @property
    def is_unusual(self) -> bool:
        """Check if activity meets unusual threshold."""
        return self.volume_oi_ratio > 1.5 or self.premium > 100_000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "underlying": self.underlying,
            "option_type": self.option_type.value,
            "strike": self.strike,
            "expiration": self.expiration.isoformat(),
            "activity_type": self.activity_type.value,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "premium": self.premium,
            "spot_price": self.spot_price,
            "timestamp": self.timestamp.isoformat(),
            "sentiment": self.sentiment,
            "volume_oi_ratio": self.volume_oi_ratio,
            **self.metadata,
        }


@dataclass
class OptionsFlowSummary:
    """Aggregated options flow summary for a symbol."""

    symbol: str
    timestamp: datetime
    total_call_volume: int
    total_put_volume: int
    total_call_premium: float
    total_put_premium: float
    put_call_ratio: float
    put_call_oi_ratio: float
    unusual_activity_count: int
    bullish_flow_pct: float
    bearish_flow_pct: float
    net_premium: float  # Call premium - Put premium
    largest_trades: list[UnusualActivity] = field(default_factory=list)

    @property
    def sentiment_score(self) -> float:
        """Calculate overall sentiment from -1 (bearish) to 1 (bullish)."""
        if self.bullish_flow_pct + self.bearish_flow_pct == 0:
            return 0
        return (self.bullish_flow_pct - self.bearish_flow_pct) / 100

    @property
    def is_contrarian_signal(self) -> bool:
        """Check if put/call ratio suggests contrarian opportunity."""
        # High P/C ratio (>1.5) historically bullish, low (<0.5) bearish
        return self.put_call_ratio > 1.5 or self.put_call_ratio < 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "total_call_volume": self.total_call_volume,
            "total_put_volume": self.total_put_volume,
            "total_call_premium": self.total_call_premium,
            "total_put_premium": self.total_put_premium,
            "put_call_ratio": self.put_call_ratio,
            "put_call_oi_ratio": self.put_call_oi_ratio,
            "unusual_activity_count": self.unusual_activity_count,
            "bullish_flow_pct": self.bullish_flow_pct,
            "bearish_flow_pct": self.bearish_flow_pct,
            "net_premium": self.net_premium,
            "sentiment_score": self.sentiment_score,
        }


class OptionsFlowAnalyzer:
    """Analyzes options flow data for trading signals."""

    def __init__(
        self,
        unusual_volume_threshold: float = 2.0,
        unusual_premium_threshold: float = 100_000,
        sweep_detection: bool = True,
    ):
        """
        Initialize options flow analyzer.

        Args:
            unusual_volume_threshold: Volume/OI ratio for unusual activity
            unusual_premium_threshold: Minimum premium for unusual activity
            sweep_detection: Enable sweep detection heuristics
        """
        self.unusual_volume_threshold = unusual_volume_threshold
        self.unusual_premium_threshold = unusual_premium_threshold
        self.sweep_detection = sweep_detection

    def analyze_chain(
        self,
        contracts: list[OptionContract],
        underlying_price: float,
    ) -> OptionsFlowSummary:
        """
        Analyze an options chain for flow signals.

        Args:
            contracts: List of option contracts
            underlying_price: Current underlying price

        Returns:
            OptionsFlowSummary with aggregated metrics
        """
        if not contracts:
            return OptionsFlowSummary(
                symbol="",
                timestamp=datetime.now(),
                total_call_volume=0,
                total_put_volume=0,
                total_call_premium=0,
                total_put_premium=0,
                put_call_ratio=1.0,
                put_call_oi_ratio=1.0,
                unusual_activity_count=0,
                bullish_flow_pct=50,
                bearish_flow_pct=50,
                net_premium=0,
            )

        symbol = contracts[0].underlying
        calls = [c for c in contracts if c.option_type == OptionType.CALL]
        puts = [c for c in contracts if c.option_type == OptionType.PUT]

        total_call_volume = sum(c.volume for c in calls)
        total_put_volume = sum(c.volume for c in puts)
        total_call_oi = sum(c.open_interest for c in calls)
        total_put_oi = sum(c.open_interest for c in puts)

        # Estimate premium traded (volume * mid price * 100)
        total_call_premium = sum(c.volume * c.mid_price * 100 for c in calls)
        total_put_premium = sum(c.volume * c.mid_price * 100 for c in puts)

        # Calculate ratios
        put_call_ratio = (
            total_put_volume / total_call_volume
            if total_call_volume > 0
            else float('inf')
        )
        put_call_oi_ratio = (
            total_put_oi / total_call_oi
            if total_call_oi > 0
            else float('inf')
        )

        # Detect unusual activity
        unusual = self._detect_unusual_activity(contracts, underlying_price)

        # Calculate flow sentiment
        bullish_premium = sum(
            u.premium for u in unusual if u.sentiment == "bullish"
        )
        bearish_premium = sum(
            u.premium for u in unusual if u.sentiment == "bearish"
        )
        total_unusual_premium = bullish_premium + bearish_premium

        bullish_pct = (
            bullish_premium / total_unusual_premium * 100
            if total_unusual_premium > 0
            else 50
        )
        bearish_pct = (
            bearish_premium / total_unusual_premium * 100
            if total_unusual_premium > 0
            else 50
        )

        return OptionsFlowSummary(
            symbol=symbol,
            timestamp=datetime.now(),
            total_call_volume=total_call_volume,
            total_put_volume=total_put_volume,
            total_call_premium=total_call_premium,
            total_put_premium=total_put_premium,
            put_call_ratio=put_call_ratio,
            put_call_oi_ratio=put_call_oi_ratio,
            unusual_activity_count=len(unusual),
            bullish_flow_pct=bullish_pct,
            bearish_flow_pct=bearish_pct,
            net_premium=total_call_premium - total_put_premium,
            largest_trades=sorted(unusual, key=lambda x: x.premium, reverse=True)[:10],
        )

    def _detect_unusual_activity(
        self,
        contracts: list[OptionContract],
        underlying_price: float,
    ) -> list[UnusualActivity]:
        """Detect unusual options activity."""
        unusual = []

        for contract in contracts:
            premium = contract.volume * contract.mid_price * 100

            # Check if unusual
            vol_oi_ratio = (
                contract.volume / contract.open_interest
                if contract.open_interest > 0
                else float('inf')
            )

            is_unusual = (
                vol_oi_ratio > self.unusual_volume_threshold
                or premium > self.unusual_premium_threshold
            )

            if not is_unusual:
                continue

            # Determine activity type
            if premium > 500_000 and vol_oi_ratio > 3:
                activity_type = UnusualActivityType.GOLDEN_SWEEP
            elif vol_oi_ratio > 5:
                activity_type = UnusualActivityType.SWEEP
            elif contract.volume > 1000:
                activity_type = UnusualActivityType.BLOCK
            else:
                activity_type = UnusualActivityType.SPLIT

            # Determine sentiment
            if contract.option_type == OptionType.CALL:
                # Call buying at/above ask is bullish
                sentiment = "bullish"
            else:
                # Put buying at/above ask is bearish (unless protective)
                if contract.strike < underlying_price * 0.9:
                    sentiment = "bearish"
                else:
                    sentiment = "neutral"  # Could be hedge

            unusual.append(UnusualActivity(
                underlying=contract.underlying,
                option_type=contract.option_type,
                strike=contract.strike,
                expiration=contract.expiration,
                activity_type=activity_type,
                volume=contract.volume,
                open_interest=contract.open_interest,
                premium=premium,
                spot_price=underlying_price,
                timestamp=datetime.now(),
                sentiment=sentiment,
            ))

        return unusual

    def calculate_gamma_exposure(
        self,
        contracts: list[OptionContract],
        underlying_price: float,
    ) -> dict[str, float]:
        """
        Calculate gamma exposure (GEX) at various price levels.

        GEX indicates where market makers need to hedge, creating support/resistance.

        Args:
            contracts: Options chain
            underlying_price: Current price

        Returns:
            Dict of price levels to gamma exposure
        """
        gex_by_strike: dict[float, float] = {}

        for contract in contracts:
            if contract.gamma is None or contract.open_interest == 0:
                continue

            strike = contract.strike
            # GEX = gamma * OI * 100 * spot^2 / 100
            gex = contract.gamma * contract.open_interest * 100 * (underlying_price ** 2) / 100

            # Calls add positive gamma, puts add negative (for MM)
            if contract.option_type == OptionType.PUT:
                gex = -gex

            gex_by_strike[strike] = gex_by_strike.get(strike, 0) + gex

        return gex_by_strike


class OptionsFlowSource:
    """
    Options flow data source.

    Fetches options data from various providers for flow analysis.
    """

    name = "options_flow"

    def __init__(
        self,
        tradier_token: str | None = None,
        polygon_key: str | None = None,
        cache_ttl_minutes: int = 5,
    ):
        """
        Initialize options flow data source.

        Args:
            tradier_token: Tradier API token
            polygon_key: Polygon.io API key
            cache_ttl_minutes: Cache TTL
        """
        self.tradier_token = tradier_token
        self.polygon_key = polygon_key
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None
        self._analyzer = OptionsFlowAnalyzer()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_cache(self, key: str) -> Any | None:
        """Check if cached data is valid."""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                return data
        return None

    def _update_cache(self, key: str, data: Any) -> None:
        """Update cache."""
        self._cache[key] = (datetime.now(), data)

    async def fetch_options_chain(
        self,
        symbol: Symbol,
        expiration: datetime | None = None,
    ) -> list[OptionContract]:
        """
        Fetch options chain for a symbol.

        Args:
            symbol: Underlying symbol
            expiration: Specific expiration date (optional)

        Returns:
            List of OptionContract objects
        """
        cache_key = f"chain:{symbol}:{expiration}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        contracts = []

        # Try providers in order of preference
        if self.tradier_token:
            contracts = await self._fetch_tradier_chain(symbol, expiration)
        elif self.polygon_key:
            contracts = await self._fetch_polygon_chain(symbol, expiration)
        else:
            # Fall back to Yahoo Finance (free, no API key needed)
            contracts = await self._fetch_yahoo_chain(symbol, expiration)

        if contracts:
            self._update_cache(cache_key, contracts)

        return contracts

    async def _fetch_yahoo_chain(
        self,
        symbol: str,
        expiration: datetime | None = None,
    ) -> list[OptionContract]:
        """
        Fetch options chain from Yahoo Finance (free, no API key).

        Args:
            symbol: Underlying symbol
            expiration: Specific expiration date (optional)

        Returns:
            List of OptionContract objects
        """
        contracts = []

        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)

            # Get available expiration dates
            try:
                available_exps = ticker.options
            except Exception:
                logger.warning(f"No options available for {symbol}")
                return contracts

            if not available_exps:
                return contracts

            # Select expirations to fetch
            if expiration:
                exp_str = expiration.strftime("%Y-%m-%d")
                if exp_str in available_exps:
                    expirations_to_fetch = [exp_str]
                else:
                    # Find closest expiration
                    expirations_to_fetch = [available_exps[0]]
            else:
                # Get first 4 expirations for broader coverage
                expirations_to_fetch = available_exps[:4]

            # Get underlying price for moneyness calculation
            try:
                underlying_price = ticker.fast_info.get("lastPrice", 0) or ticker.info.get("regularMarketPrice", 0)
            except Exception:
                underlying_price = 0

            for exp_str in expirations_to_fetch:
                try:
                    chain = ticker.option_chain(exp_str)

                    # Parse expiration date
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d")

                    # Process calls
                    for _, row in chain.calls.iterrows():
                        try:
                            contracts.append(OptionContract(
                                symbol=row.get("contractSymbol", f"{symbol}_{exp_str}_C"),
                                underlying=symbol,
                                option_type=OptionType.CALL,
                                strike=float(row["strike"]),
                                expiration=exp_date,
                                bid=float(row.get("bid", 0) or 0),
                                ask=float(row.get("ask", 0) or 0),
                                last_price=float(row.get("lastPrice", 0) or 0),
                                volume=int(row.get("volume", 0) or 0),
                                open_interest=int(row.get("openInterest", 0) or 0),
                                implied_volatility=float(row.get("impliedVolatility", 0) or 0),
                                delta=None,  # Yahoo doesn't provide Greeks
                                gamma=None,
                                theta=None,
                                vega=None,
                            ))
                        except Exception as e:
                            logger.debug(f"Error parsing Yahoo call option: {e}")

                    # Process puts
                    for _, row in chain.puts.iterrows():
                        try:
                            contracts.append(OptionContract(
                                symbol=row.get("contractSymbol", f"{symbol}_{exp_str}_P"),
                                underlying=symbol,
                                option_type=OptionType.PUT,
                                strike=float(row["strike"]),
                                expiration=exp_date,
                                bid=float(row.get("bid", 0) or 0),
                                ask=float(row.get("ask", 0) or 0),
                                last_price=float(row.get("lastPrice", 0) or 0),
                                volume=int(row.get("volume", 0) or 0),
                                open_interest=int(row.get("openInterest", 0) or 0),
                                implied_volatility=float(row.get("impliedVolatility", 0) or 0),
                                delta=None,
                                gamma=None,
                                theta=None,
                                vega=None,
                            ))
                        except Exception as e:
                            logger.debug(f"Error parsing Yahoo put option: {e}")

                except Exception as e:
                    logger.warning(f"Error fetching Yahoo chain for {symbol} {exp_str}: {e}")

            logger.info(f"Fetched {len(contracts)} options for {symbol} from Yahoo Finance")

        except ImportError:
            logger.warning("yfinance not installed. Install with: pip install yfinance")
        except Exception as e:
            logger.error(f"Yahoo options fetch error for {symbol}: {e}")

        return contracts

    async def _fetch_tradier_chain(
        self,
        symbol: Symbol,
        expiration: datetime | None,
    ) -> list[OptionContract]:
        """Fetch chain from Tradier."""
        client = await self._get_client()
        contracts = []

        try:
            headers = {
                "Authorization": f"Bearer {self.tradier_token}",
                "Accept": "application/json",
            }

            # Get expirations if not specified
            if expiration is None:
                exp_url = f"https://api.tradier.com/v1/markets/options/expirations"
                resp = await client.get(
                    exp_url,
                    params={"symbol": symbol},
                    headers=headers,
                )
                resp.raise_for_status()
                exp_data = resp.json()
                expirations = exp_data.get("expirations", {}).get("date", [])[:4]
            else:
                expirations = [expiration.strftime("%Y-%m-%d")]

            # Fetch chain for each expiration
            for exp_str in expirations:
                chain_url = "https://api.tradier.com/v1/markets/options/chains"
                resp = await client.get(
                    chain_url,
                    params={
                        "symbol": symbol,
                        "expiration": exp_str,
                        "greeks": "true",
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                chain_data = resp.json()

                for opt in chain_data.get("options", {}).get("option", []):
                    try:
                        exp_date = datetime.strptime(opt["expiration_date"], "%Y-%m-%d")
                        opt_type = OptionType.CALL if opt["option_type"] == "call" else OptionType.PUT

                        contracts.append(OptionContract(
                            symbol=opt["symbol"],
                            underlying=opt["underlying"],
                            option_type=opt_type,
                            strike=float(opt["strike"]),
                            expiration=exp_date,
                            bid=float(opt.get("bid", 0)),
                            ask=float(opt.get("ask", 0)),
                            last_price=float(opt.get("last", 0)),
                            volume=int(opt.get("volume", 0)),
                            open_interest=int(opt.get("open_interest", 0)),
                            implied_volatility=opt.get("greeks", {}).get("mid_iv"),
                            delta=opt.get("greeks", {}).get("delta"),
                            gamma=opt.get("greeks", {}).get("gamma"),
                            theta=opt.get("greeks", {}).get("theta"),
                            vega=opt.get("greeks", {}).get("vega"),
                        ))
                    except Exception as e:
                        logger.debug(f"Error parsing option: {e}")

        except Exception as e:
            logger.error(f"Tradier options fetch error: {e}")

        return contracts

    async def _fetch_polygon_chain(
        self,
        symbol: Symbol,
        expiration: datetime | None,
    ) -> list[OptionContract]:
        """Fetch chain from Polygon.io."""
        client = await self._get_client()
        contracts = []

        try:
            # Get snapshot of all options for underlying
            url = f"https://api.polygon.io/v3/snapshot/options/{symbol}"
            params = {"apiKey": self.polygon_key, "limit": 250}

            if expiration:
                params["expiration_date"] = expiration.strftime("%Y-%m-%d")

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for result in data.get("results", []):
                try:
                    details = result.get("details", {})
                    day = result.get("day", {})
                    greeks = result.get("greeks", {})

                    exp_str = details.get("expiration_date", "")
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d") if exp_str else datetime.now()

                    opt_type = OptionType.CALL if details.get("contract_type") == "call" else OptionType.PUT

                    contracts.append(OptionContract(
                        symbol=details.get("ticker", ""),
                        underlying=result.get("underlying_asset", {}).get("ticker", symbol),
                        option_type=opt_type,
                        strike=float(details.get("strike_price", 0)),
                        expiration=exp_date,
                        bid=float(result.get("last_quote", {}).get("bid", 0)),
                        ask=float(result.get("last_quote", {}).get("ask", 0)),
                        last_price=float(day.get("close", 0)),
                        volume=int(day.get("volume", 0)),
                        open_interest=int(result.get("open_interest", 0)),
                        implied_volatility=greeks.get("implied_volatility"),
                        delta=greeks.get("delta"),
                        gamma=greeks.get("gamma"),
                        theta=greeks.get("theta"),
                        vega=greeks.get("vega"),
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Polygon option: {e}")

        except Exception as e:
            logger.error(f"Polygon options fetch error: {e}")

        return contracts

    async def get_flow_summary(
        self,
        symbol: Symbol,
        underlying_price: float,
    ) -> OptionsFlowSummary:
        """
        Get options flow summary for a symbol.

        Args:
            symbol: Underlying symbol
            underlying_price: Current price of underlying

        Returns:
            OptionsFlowSummary with aggregated metrics
        """
        contracts = await self.fetch_options_chain(symbol)
        return self._analyzer.analyze_chain(contracts, underlying_price)

    async def get_unusual_activity(
        self,
        symbols: list[Symbol] | None = None,
        min_premium: float = 100_000,
    ) -> list[UnusualActivity]:
        """
        Get unusual options activity across symbols.

        Args:
            symbols: Symbols to check (None for market-wide)
            min_premium: Minimum premium threshold

        Returns:
            List of UnusualActivity alerts
        """
        all_unusual = []

        # Default to popular symbols if none specified
        if symbols is None:
            symbols = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD", "AMZN", "META", "GOOGL", "MSFT"]

        for symbol in symbols:
            try:
                contracts = await self.fetch_options_chain(symbol)
                # Get current price from options ATM strike
                underlying_price = self._estimate_underlying_price(contracts)

                for contract in contracts:
                    premium = contract.volume * contract.mid_price * 100

                    if premium < min_premium:
                        continue

                    vol_oi = (
                        contract.volume / contract.open_interest
                        if contract.open_interest > 0
                        else float('inf')
                    )

                    if vol_oi < 1.5:
                        continue

                    # Determine sentiment
                    if contract.option_type == OptionType.CALL:
                        sentiment = "bullish"
                    elif contract.strike < underlying_price * 0.95:
                        sentiment = "bearish"
                    else:
                        sentiment = "neutral"

                    all_unusual.append(UnusualActivity(
                        underlying=symbol,
                        option_type=contract.option_type,
                        strike=contract.strike,
                        expiration=contract.expiration,
                        activity_type=UnusualActivityType.BLOCK,
                        volume=contract.volume,
                        open_interest=contract.open_interest,
                        premium=premium,
                        spot_price=underlying_price,
                        timestamp=datetime.now(),
                        sentiment=sentiment,
                    ))

                await asyncio.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.warning(f"Error checking unusual activity for {symbol}: {e}")

        # Sort by premium
        all_unusual.sort(key=lambda x: x.premium, reverse=True)
        return all_unusual

    def _estimate_underlying_price(self, contracts: list[OptionContract]) -> float:
        """Estimate underlying price from ATM options."""
        if not contracts:
            return 0

        # Find where call and put prices are closest (ATM)
        strikes = sorted(set(c.strike for c in contracts))
        if not strikes:
            return 0

        # Return middle strike as approximation
        return strikes[len(strikes) // 2]

    def to_dataframe(
        self,
        contracts: list[OptionContract],
    ) -> pd.DataFrame:
        """Convert contracts to DataFrame."""
        if not contracts:
            return pd.DataFrame()

        records = [c.to_dict() for c in contracts]
        return pd.DataFrame(records)


class PutCallRatioSource:
    """
    Put/Call ratio data source.

    Fetches historical and current put/call ratios for market sentiment.
    """

    name = "put_call_ratio"

    # Historical average P/C ratio levels
    NEUTRAL_RATIO = 0.7
    BULLISH_THRESHOLD = 1.0  # High P/C = contrarian bullish
    BEARISH_THRESHOLD = 0.5  # Low P/C = contrarian bearish

    def __init__(self, cache_ttl_minutes: int = 30):
        """Initialize P/C ratio source."""
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_equity_pc_ratio(self) -> dict[str, float]:
        """
        Get equity-only put/call ratio.

        Returns:
            Dict with ratio and percentile
        """
        # This would typically come from CBOE or similar
        # Placeholder implementation
        return {
            "ratio": 0.65,
            "percentile": 45.0,
            "signal": "neutral",
        }

    async def get_index_pc_ratio(self) -> dict[str, float]:
        """
        Get index put/call ratio (SPX, etc).

        Returns:
            Dict with ratio and signal
        """
        return {
            "ratio": 1.1,
            "percentile": 70.0,
            "signal": "bullish",  # High P/C is contrarian bullish
        }

    async def get_total_pc_ratio(self) -> dict[str, float]:
        """
        Get total market put/call ratio.

        Returns:
            Combined ratio metrics
        """
        equity = await self.get_equity_pc_ratio()
        index = await self.get_index_pc_ratio()

        avg_ratio = (equity["ratio"] + index["ratio"]) / 2

        if avg_ratio > self.BULLISH_THRESHOLD:
            signal = "bullish"
        elif avg_ratio < self.BEARISH_THRESHOLD:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "equity_ratio": equity["ratio"],
            "index_ratio": index["ratio"],
            "total_ratio": avg_ratio,
            "signal": signal,
        }


async def fetch_options_flow(
    symbol: Symbol,
    underlying_price: float,
    tradier_token: str | None = None,
    polygon_key: str | None = None,
) -> OptionsFlowSummary:
    """
    Convenience function to fetch options flow.

    Args:
        symbol: Underlying symbol
        underlying_price: Current price
        tradier_token: Tradier API token
        polygon_key: Polygon API key

    Returns:
        OptionsFlowSummary
    """
    source = OptionsFlowSource(
        tradier_token=tradier_token,
        polygon_key=polygon_key,
    )

    try:
        return await source.get_flow_summary(symbol, underlying_price)
    finally:
        await source.close()


async def fetch_unusual_options(
    symbols: list[Symbol] | None = None,
    min_premium: float = 100_000,
    tradier_token: str | None = None,
    polygon_key: str | None = None,
) -> list[UnusualActivity]:
    """
    Convenience function to fetch unusual options activity.

    Args:
        symbols: Symbols to check
        min_premium: Minimum premium threshold
        tradier_token: Tradier API token
        polygon_key: Polygon API key

    Returns:
        List of UnusualActivity
    """
    source = OptionsFlowSource(
        tradier_token=tradier_token,
        polygon_key=polygon_key,
    )

    try:
        return await source.get_unusual_activity(symbols, min_premium)
    finally:
        await source.close()


async def get_put_call_ratio(symbol: str) -> dict[str, float]:
    """
    Get put/call ratio for a symbol from Yahoo Finance.

    Args:
        symbol: Stock symbol

    Returns:
        Dictionary with volume and OI ratios
    """
    source = OptionsFlowSource()

    try:
        contracts = await source.fetch_options_chain(symbol)

        if not contracts:
            return {"volume_ratio": 1.0, "oi_ratio": 1.0, "signal": "neutral"}

        calls = [c for c in contracts if c.option_type == OptionType.CALL]
        puts = [c for c in contracts if c.option_type == OptionType.PUT]

        call_volume = sum(c.volume for c in calls)
        put_volume = sum(c.volume for c in puts)
        call_oi = sum(c.open_interest for c in calls)
        put_oi = sum(c.open_interest for c in puts)

        volume_ratio = put_volume / call_volume if call_volume > 0 else 1.0
        oi_ratio = put_oi / call_oi if call_oi > 0 else 1.0

        # Determine signal (contrarian)
        if volume_ratio > 1.2:
            signal = "bullish"  # High put buying = contrarian bullish
        elif volume_ratio < 0.6:
            signal = "bearish"  # Low put buying = contrarian bearish
        else:
            signal = "neutral"

        return {
            "volume_ratio": round(volume_ratio, 3),
            "oi_ratio": round(oi_ratio, 3),
            "call_volume": call_volume,
            "put_volume": put_volume,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "signal": signal,
        }

    finally:
        await source.close()


async def calculate_max_pain(symbol: str, expiration: str | None = None) -> dict[str, Any]:
    """
    Calculate max pain price for a symbol.

    Max pain is the strike where option sellers (market makers) make the most money,
    often acting as a price magnet near expiration.

    Args:
        symbol: Stock symbol
        expiration: Specific expiration (YYYY-MM-DD) or None for nearest

    Returns:
        Dictionary with max pain strike and details
    """
    source = OptionsFlowSource()

    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d") if expiration else None
        contracts = await source.fetch_options_chain(symbol, exp_date)

        if not contracts:
            return {"max_pain": None, "error": "No options data"}

        # Get unique strikes
        strikes = sorted(set(c.strike for c in contracts))

        if not strikes:
            return {"max_pain": None, "error": "No strikes found"}

        # Calculate pain at each strike
        pain_by_strike = {}

        for test_strike in strikes:
            total_pain = 0

            for contract in contracts:
                oi = contract.open_interest

                if contract.option_type == OptionType.CALL:
                    # Call is ITM if strike < test_strike
                    if contract.strike < test_strike:
                        intrinsic = (test_strike - contract.strike) * oi * 100
                        total_pain += intrinsic
                else:
                    # Put is ITM if strike > test_strike
                    if contract.strike > test_strike:
                        intrinsic = (contract.strike - test_strike) * oi * 100
                        total_pain += intrinsic

            pain_by_strike[test_strike] = total_pain

        # Max pain is where pain is minimized
        max_pain_strike = min(pain_by_strike, key=pain_by_strike.get)

        # Get current price estimate
        underlying_price = source._estimate_underlying_price(contracts)

        return {
            "max_pain": max_pain_strike,
            "current_price": underlying_price,
            "distance_pct": round((max_pain_strike - underlying_price) / underlying_price * 100, 2) if underlying_price else 0,
            "pain_at_max_pain": pain_by_strike[max_pain_strike],
            "nearest_expirations": list(set(c.expiration.strftime("%Y-%m-%d") for c in contracts))[:4],
        }

    finally:
        await source.close()


def get_options_features(contracts: list[OptionContract], underlying_price: float) -> dict[str, float]:
    """
    Extract features from options chain for ML strategies.

    Args:
        contracts: List of option contracts
        underlying_price: Current underlying price

    Returns:
        Dictionary of features for ML models
    """
    if not contracts or underlying_price <= 0:
        return {
            "put_call_volume_ratio": 1.0,
            "put_call_oi_ratio": 1.0,
            "avg_iv_call": 0.0,
            "avg_iv_put": 0.0,
            "iv_skew": 0.0,
            "near_atm_volume": 0,
            "near_atm_oi": 0,
            "total_premium": 0,
        }

    calls = [c for c in contracts if c.option_type == OptionType.CALL]
    puts = [c for c in contracts if c.option_type == OptionType.PUT]

    # Volume and OI ratios
    call_vol = sum(c.volume for c in calls)
    put_vol = sum(c.volume for c in puts)
    call_oi = sum(c.open_interest for c in calls)
    put_oi = sum(c.open_interest for c in puts)

    pc_vol_ratio = put_vol / call_vol if call_vol > 0 else 1.0
    pc_oi_ratio = put_oi / call_oi if call_oi > 0 else 1.0

    # IV analysis
    call_ivs = [c.implied_volatility for c in calls if c.implied_volatility]
    put_ivs = [c.implied_volatility for c in puts if c.implied_volatility]

    avg_iv_call = np.mean(call_ivs) if call_ivs else 0.0
    avg_iv_put = np.mean(put_ivs) if put_ivs else 0.0

    # IV skew (put IV vs call IV at same moneyness)
    iv_skew = avg_iv_put - avg_iv_call

    # Near ATM activity (within 5% of current price)
    atm_range = underlying_price * 0.05
    near_atm = [
        c for c in contracts
        if abs(c.strike - underlying_price) <= atm_range
    ]
    near_atm_volume = sum(c.volume for c in near_atm)
    near_atm_oi = sum(c.open_interest for c in near_atm)

    # Total premium
    total_premium = sum(c.volume * c.mid_price * 100 for c in contracts)

    return {
        "put_call_volume_ratio": round(pc_vol_ratio, 4),
        "put_call_oi_ratio": round(pc_oi_ratio, 4),
        "avg_iv_call": round(avg_iv_call, 4),
        "avg_iv_put": round(avg_iv_put, 4),
        "iv_skew": round(iv_skew, 4),
        "near_atm_volume": near_atm_volume,
        "near_atm_oi": near_atm_oi,
        "total_premium": round(total_premium, 2),
    }
