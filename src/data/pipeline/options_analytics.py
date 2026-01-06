"""Options Analytics Engine for real-time position monitoring.

Provides:
- Greeks calculation and dollar Greeks
- IV analysis (rank, percentile, vs HV)
- Probability analysis (ITM, profit, expected move)
- Time decay projections
- Roll recommendations
- Portfolio-level options summary

Usage:
    from src.data.pipeline.options_analytics import OptionsAnalyzer

    analyzer = OptionsAnalyzer()

    # Single option analysis
    analytics = analyzer.analyze_option("SLB250206C00044000")

    # Portfolio analysis
    portfolio = analyzer.analyze_portfolio(["SLB250206C00044000", "HAL250221C00032000"])

    # Get IV rank for underlying
    iv_rank = analyzer.get_iv_rank("SLB")
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class OptionGreeks:
    """Option Greeks."""
    delta: float
    gamma: float
    theta: float  # Per day
    vega: float  # Per 1% IV change
    rho: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta": round(self.delta, 4),
            "gamma": round(self.gamma, 6),
            "theta": round(self.theta, 4),
            "vega": round(self.vega, 4),
            "rho": round(self.rho, 4),
        }


@dataclass
class OptionAnalytics:
    """Comprehensive analysis of a single option position."""

    symbol: str  # Full option symbol
    underlying: str
    underlying_price: float
    strike: float
    expiration: date
    option_type: str  # "call" or "put"
    days_to_expiry: int

    # Pricing
    bid: float
    ask: float
    mid: float
    last: float
    spread_pct: float  # (ask-bid)/mid

    # Greeks
    greeks: OptionGreeks

    # Dollar Greeks (per contract = 100 shares)
    dollar_delta: float
    dollar_theta: float  # Daily decay in $
    dollar_gamma: float
    dollar_vega: float

    # Implied Volatility
    iv: float
    iv_rank: float  # 0-100 percentile vs 52-week
    iv_percentile: float
    historical_vol_20d: float
    iv_vs_hv: float  # IV premium/discount

    # Probability Analysis
    prob_itm: float
    prob_profit: float
    expected_move: float  # 1 std dev move by expiry

    # Breakeven Analysis
    breakeven: float
    distance_to_breakeven: float
    distance_to_breakeven_pct: float

    # Time Decay Analysis
    theta_per_day: float  # $ lost per day per contract
    theta_acceleration: float  # Rate of theta increase
    optimal_exit_dte: int  # When theta accelerates (typically 21 DTE)

    # Volume & Open Interest
    volume: int
    open_interest: int
    volume_oi_ratio: float

    # Status
    moneyness: str  # "ITM", "ATM", "OTM"
    itm_amount: float  # How much ITM (positive) or OTM (negative)

    # Recommendation
    hold_score: float  # 0-100, higher = better to hold
    roll_recommendation: bool
    suggested_action: str  # "hold", "close", "roll", "add"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "underlying_price": self.underlying_price,
            "strike": self.strike,
            "expiration": self.expiration.isoformat(),
            "option_type": self.option_type,
            "days_to_expiry": self.days_to_expiry,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "last": self.last,
            "spread_pct": self.spread_pct,
            "greeks": self.greeks.to_dict(),
            "dollar_delta": self.dollar_delta,
            "dollar_theta": self.dollar_theta,
            "dollar_gamma": self.dollar_gamma,
            "dollar_vega": self.dollar_vega,
            "iv": self.iv,
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "historical_vol_20d": self.historical_vol_20d,
            "iv_vs_hv": self.iv_vs_hv,
            "prob_itm": self.prob_itm,
            "prob_profit": self.prob_profit,
            "expected_move": self.expected_move,
            "breakeven": self.breakeven,
            "distance_to_breakeven": self.distance_to_breakeven,
            "distance_to_breakeven_pct": self.distance_to_breakeven_pct,
            "theta_per_day": self.theta_per_day,
            "theta_acceleration": self.theta_acceleration,
            "optimal_exit_dte": self.optimal_exit_dte,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "volume_oi_ratio": self.volume_oi_ratio,
            "moneyness": self.moneyness,
            "itm_amount": self.itm_amount,
            "hold_score": self.hold_score,
            "roll_recommendation": self.roll_recommendation,
            "suggested_action": self.suggested_action,
            "notes": self.notes,
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"{self.underlying} {self.expiration.strftime('%b %d')} ${self.strike} {self.option_type.upper()} Analysis:",
            f"  Price: ${self.mid:.2f} (bid ${self.bid:.2f} / ask ${self.ask:.2f})",
            f"  Underlying: ${self.underlying_price:.2f} | Status: {self.moneyness} by ${abs(self.itm_amount):.2f}",
            "",
            "  Greeks:",
            f"    Delta: {self.greeks.delta:.2f} | Theta: -${abs(self.dollar_theta):.2f}/day | Vega: {self.greeks.vega:.2f}",
            f"    Dollar Delta: ${self.dollar_delta:.0f} | Dollar Theta: -${abs(self.dollar_theta):.2f}/day",
            "",
            "  IV Analysis:",
            f"    IV: {self.iv*100:.1f}% | IV Rank: {self.iv_rank:.0f} ({self._iv_label()})",
            f"    HV20: {self.historical_vol_20d*100:.1f}% | IV Premium: {self.iv_vs_hv*100:+.1f}%",
        ]

        if self.iv_rank > 70:
            lines.append(f"    Note: IV elevated - options expensive")
        elif self.iv_rank < 30:
            lines.append(f"    Note: IV low - options cheap")

        lines.extend([
            "",
            "  Probability:",
            f"    Prob ITM: {self.prob_itm*100:.0f}% | Breakeven: ${self.breakeven:.2f}",
            f"    Expected Move by Expiry: +/- ${self.expected_move:.2f}",
            "",
            "  Time Decay:",
            f"    {self.days_to_expiry} DTE | Theta accelerates in {max(0, self.days_to_expiry - 21)} days",
            f"    Daily Decay: -${abs(self.theta_per_day):.2f}/contract",
        ])

        # Recommendation
        lines.extend([
            "",
            f"  Recommendation: {self.suggested_action.upper()}",
        ])

        for note in self.notes[:3]:
            lines.append(f"    - {note}")

        return "\n".join(lines)

    def _iv_label(self) -> str:
        if self.iv_rank >= 70:
            return "elevated"
        elif self.iv_rank <= 30:
            return "low"
        else:
            return "normal"


@dataclass
class PositionOptionsAnalytics:
    """Portfolio-level options analysis."""

    timestamp: datetime
    total_delta: float  # Net delta exposure
    total_theta: float  # Daily theta decay (all positions)
    total_vega: float  # IV sensitivity
    total_gamma: float
    max_loss: float  # If all options expire worthless
    weighted_avg_iv: float
    total_premium_at_risk: float
    positions: list[OptionAnalytics] = field(default_factory=list)

    # Summary stats
    total_positions: int = 0
    calls_count: int = 0
    puts_count: int = 0
    avg_dte: float = 0.0
    positions_near_expiry: int = 0  # < 7 DTE
    high_theta_positions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_delta": round(self.total_delta, 2),
            "total_theta": round(self.total_theta, 2),
            "total_vega": round(self.total_vega, 2),
            "total_gamma": round(self.total_gamma, 4),
            "max_loss": round(self.max_loss, 2),
            "weighted_avg_iv": round(self.weighted_avg_iv, 4),
            "total_premium_at_risk": round(self.total_premium_at_risk, 2),
            "total_positions": self.total_positions,
            "calls_count": self.calls_count,
            "puts_count": self.puts_count,
            "avg_dte": round(self.avg_dte, 1),
            "positions_near_expiry": self.positions_near_expiry,
            "high_theta_positions": self.high_theta_positions,
            "positions": [p.to_dict() for p in self.positions],
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"OPTIONS PORTFOLIO SUMMARY - {self.timestamp.strftime('%H:%M ET')}",
            "=" * 50,
            "",
            f"Positions: {self.total_positions} ({self.calls_count} calls, {self.puts_count} puts)",
            f"Total Premium at Risk: ${self.total_premium_at_risk:,.2f}",
            f"Max Loss (all expire worthless): ${self.max_loss:,.2f}",
            "",
            "GREEKS EXPOSURE:",
            f"  Net Delta: ${self.total_delta:+,.0f} ({'bullish' if self.total_delta > 0 else 'bearish'} exposure)",
            f"  Daily Theta: -${abs(self.total_theta):.2f} (losing ${abs(self.total_theta):.2f}/day to decay)",
            f"  Total Vega: ${self.total_vega:+,.0f} ({'long' if self.total_vega > 0 else 'short'} volatility)",
            f"  Total Gamma: {self.total_gamma:+.4f}",
            "",
            f"IV: Weighted Avg {self.weighted_avg_iv*100:.1f}%",
            f"Time: Avg DTE {self.avg_dte:.0f} days",
        ]

        if self.positions_near_expiry > 0:
            lines.append(f"  WARNING: {self.positions_near_expiry} position(s) < 7 DTE")

        if self.high_theta_positions:
            lines.append(f"\nHIGH THETA DECAY:")
            for pos in self.high_theta_positions[:3]:
                lines.append(f"  - {pos}")

        # Position breakdown
        if self.positions:
            lines.extend(["", "POSITION DETAILS:"])
            for pos in self.positions[:5]:
                status = f"{pos.moneyness}"
                lines.append(
                    f"  {pos.underlying} {pos.expiration.strftime('%m/%d')} ${pos.strike}{pos.option_type[0].upper()}: "
                    f"${pos.mid:.2f} | {status} | theta -${abs(pos.dollar_theta):.2f}/day"
                )

        return "\n".join(lines)


class OptionsAnalyzer:
    """
    Options analytics engine for real-time position monitoring.

    Features:
    - Greeks calculation (delta, gamma, theta, vega, rho)
    - Dollar Greeks for position sizing
    - IV analysis (rank, percentile, vs historical)
    - Probability calculations
    - Time decay projections
    - Roll recommendations
    """

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize options analyzer.

        Args:
            risk_free_rate: Annual risk-free rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate
        self._price_cache: dict[str, tuple[datetime, float]] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._hv_cache: dict[str, tuple[datetime, float]] = {}

    def _get_underlying_price(self, symbol: str) -> float:
        """Get current price for underlying with caching."""
        if symbol in self._price_cache:
            cached_time, cached_price = self._price_cache[symbol]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_price

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if len(hist) > 0:
                price = float(hist["Close"].iloc[-1])
                self._price_cache[symbol] = (datetime.now(), price)
                return price
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")

        raise ValueError(f"Could not get price for {symbol}")

    def _get_historical_volatility(self, symbol: str, days: int = 20) -> float:
        """Calculate historical volatility (annualized)."""
        if symbol in self._hv_cache:
            cached_time, cached_hv = self._hv_cache[symbol]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_hv

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="60d")

            if len(hist) < days + 1:
                return 0.30  # Default 30%

            returns = hist["Close"].pct_change().dropna()
            hv = returns.tail(days).std() * np.sqrt(252)
            self._hv_cache[symbol] = (datetime.now(), hv)
            return float(hv)

        except Exception as e:
            logger.warning(f"Failed to calculate HV for {symbol}: {e}")
            return 0.30

    def _parse_option_symbol(self, symbol: str) -> dict:
        """
        Parse OCC option symbol format.

        Format: SYMBOL + YYMMDD + C/P + Strike (8 digits with 3 decimal places)
        Example: SLB250206C00044000 = SLB Feb 6 2025 $44 Call
        """
        # Try OCC format first
        match = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', symbol.upper())
        if match:
            underlying = match.group(1)
            date_str = match.group(2)
            option_type = "call" if match.group(3) == "C" else "put"
            strike = int(match.group(4)) / 1000

            # Parse date (YYMMDD)
            year = 2000 + int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            expiration = date(year, month, day)

            return {
                "underlying": underlying,
                "expiration": expiration,
                "option_type": option_type,
                "strike": strike,
            }

        # Try simpler format: SYMBOL_EXPIRY_STRIKE_TYPE
        # e.g., SLB_2025-02-06_44_C
        match2 = re.match(r'^([A-Z]+)_(\d{4}-\d{2}-\d{2})_(\d+\.?\d*)_([CP])$', symbol.upper())
        if match2:
            return {
                "underlying": match2.group(1),
                "expiration": datetime.strptime(match2.group(2), "%Y-%m-%d").date(),
                "option_type": "call" if match2.group(4) == "C" else "put",
                "strike": float(match2.group(3)),
            }

        raise ValueError(f"Could not parse option symbol: {symbol}")

    def _black_scholes_greeks(
        self,
        S: float,  # Spot price
        K: float,  # Strike
        T: float,  # Time to expiry (years)
        r: float,  # Risk-free rate
        sigma: float,  # Volatility
        option_type: str,  # "call" or "put"
    ) -> tuple[float, OptionGreeks]:
        """
        Calculate option price and Greeks using Black-Scholes.

        Returns:
            Tuple of (price, Greeks)
        """
        if T <= 0 or sigma <= 0:
            # At expiry
            if option_type == "call":
                intrinsic = max(0, S - K)
                delta = 1.0 if S > K else 0.0
            else:
                intrinsic = max(0, K - S)
                delta = -1.0 if K > S else 0.0

            return intrinsic, OptionGreeks(
                delta=delta,
                gamma=0,
                theta=0,
                vega=0,
                rho=0,
            )

        # Calculate d1 and d2
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        # Price
        if option_type == "call":
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = -norm.cdf(-d1)

        # Greeks
        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))

        if option_type == "call":
            theta = (
                -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                - r * K * math.exp(-r * T) * norm.cdf(d2)
            ) / 365
        else:
            theta = (
                -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                + r * K * math.exp(-r * T) * norm.cdf(-d2)
            ) / 365

        vega = S * norm.pdf(d1) * math.sqrt(T) / 100  # Per 1% IV change

        if option_type == "call":
            rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100
        else:
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100

        return price, OptionGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho,
        )

    def _calculate_prob_itm(
        self,
        S: float,
        K: float,
        T: float,
        sigma: float,
        option_type: str,
    ) -> float:
        """Calculate probability of finishing ITM."""
        if T <= 0:
            if option_type == "call":
                return 1.0 if S > K else 0.0
            else:
                return 1.0 if S < K else 0.0

        # Using log-normal distribution
        d2 = (math.log(S / K) + (self.risk_free_rate - 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))

        if option_type == "call":
            return float(norm.cdf(d2))
        else:
            return float(norm.cdf(-d2))

    def _calculate_expected_move(self, S: float, T: float, sigma: float) -> float:
        """Calculate 1 standard deviation expected move by expiry."""
        return S * sigma * math.sqrt(T)

    def _get_option_chain_data(self, underlying: str, expiration: date, strike: float, option_type: str) -> dict:
        """Get real option data from yfinance."""
        try:
            ticker = yf.Ticker(underlying)
            exp_str = expiration.strftime("%Y-%m-%d")

            chain = ticker.option_chain(exp_str)
            options_df = chain.calls if option_type == "call" else chain.puts

            # Find the specific strike
            row = options_df[options_df["strike"] == strike]

            if len(row) > 0:
                row = row.iloc[0]
                return {
                    "bid": float(row.get("bid", 0) or 0),
                    "ask": float(row.get("ask", 0) or 0),
                    "last": float(row.get("lastPrice", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "open_interest": int(row.get("openInterest", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0.30) or 0.30),
                }

        except Exception as e:
            logger.debug(f"Could not get option chain data: {e}")

        return None

    def get_iv_rank(self, underlying: str) -> float:
        """
        Get IV rank (0-100) for underlying.

        Uses historical volatility as proxy since real IV history requires paid data.
        """
        try:
            ticker = yf.Ticker(underlying)
            hist = ticker.history(period="1y")

            if len(hist) < 60:
                return 50.0  # Default to middle

            returns = hist["Close"].pct_change().dropna()

            # 20-day rolling volatility
            rolling_vol = returns.rolling(window=20).std() * np.sqrt(252)
            rolling_vol = rolling_vol.dropna()

            current_vol = rolling_vol.iloc[-1]
            vol_min = rolling_vol.min()
            vol_max = rolling_vol.max()

            if vol_max > vol_min:
                rank = (current_vol - vol_min) / (vol_max - vol_min)
                return float(rank * 100)

            return 50.0

        except Exception as e:
            logger.warning(f"Failed to calculate IV rank for {underlying}: {e}")
            return 50.0

    def analyze_option(self, symbol: str, quantity: int = 1) -> OptionAnalytics:
        """
        Perform full analysis of a single option position.

        Args:
            symbol: Option symbol (OCC format or SYMBOL_EXPIRY_STRIKE_TYPE)
            quantity: Number of contracts (positive = long, negative = short)

        Returns:
            OptionAnalytics with comprehensive analysis
        """
        # Parse option symbol
        parsed = self._parse_option_symbol(symbol)
        underlying = parsed["underlying"]
        expiration = parsed["expiration"]
        option_type = parsed["option_type"]
        strike = parsed["strike"]

        # Get underlying price
        spot = self._get_underlying_price(underlying)

        # Calculate days to expiry
        today = date.today()
        dte = (expiration - today).days

        # Get historical volatility
        hv_20d = self._get_historical_volatility(underlying)

        # Try to get real market data
        market_data = self._get_option_chain_data(underlying, expiration, strike, option_type)

        if market_data:
            bid = market_data["bid"]
            ask = market_data["ask"]
            last = market_data["last"]
            volume = market_data["volume"]
            open_interest = market_data["open_interest"]
            iv = market_data["iv"]
        else:
            # Use model prices
            iv = hv_20d * 1.15  # Assume 15% VRP
            T = max(dte, 1) / 365.0
            model_price, _ = self._black_scholes_greeks(spot, strike, T, self.risk_free_rate, iv, option_type)
            bid = model_price * 0.95
            ask = model_price * 1.05
            last = model_price
            volume = 0
            open_interest = 0

        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
        spread_pct = (ask - bid) / mid if mid > 0 else 0

        # Calculate Greeks
        T = max(dte, 1) / 365.0
        _, greeks = self._black_scholes_greeks(spot, strike, T, self.risk_free_rate, iv, option_type)

        # Dollar Greeks (per contract = 100 shares)
        dollar_delta = greeks.delta * 100 * spot
        dollar_theta = greeks.theta * 100
        dollar_gamma = greeks.gamma * 100 * spot
        dollar_vega = greeks.vega * 100

        # IV analysis
        iv_rank = self.get_iv_rank(underlying)
        iv_percentile = iv_rank  # Simplified
        iv_vs_hv = (iv - hv_20d) / hv_20d if hv_20d > 0 else 0

        # Probability analysis
        prob_itm = self._calculate_prob_itm(spot, strike, T, iv, option_type)
        expected_move = self._calculate_expected_move(spot, T, iv)

        # Breakeven
        if option_type == "call":
            breakeven = strike + mid
            prob_profit = self._calculate_prob_itm(spot, breakeven, T, iv, "call")
        else:
            breakeven = strike - mid
            prob_profit = self._calculate_prob_itm(spot, breakeven, T, iv, "put")

        distance_to_breakeven = breakeven - spot if option_type == "call" else spot - breakeven
        distance_to_breakeven_pct = distance_to_breakeven / spot if spot > 0 else 0

        # Time decay analysis
        theta_per_day = abs(dollar_theta)
        theta_acceleration = 1.0 / max(dte, 1)  # Simplified
        optimal_exit_dte = 21  # Theta accelerates around 21 DTE

        # Volume/OI analysis
        volume_oi_ratio = volume / open_interest if open_interest > 0 else 0

        # Moneyness
        if option_type == "call":
            itm_amount = spot - strike
        else:
            itm_amount = strike - spot

        if abs(itm_amount) < spot * 0.02:  # Within 2%
            moneyness = "ATM"
        elif itm_amount > 0:
            moneyness = "ITM"
        else:
            moneyness = "OTM"

        # Generate recommendation
        notes = []
        hold_score = 50.0  # Start neutral

        # Adjust for time decay
        if dte < 7:
            hold_score -= 30
            notes.append(f"Near expiry ({dte} DTE) - theta accelerating")
        elif dte < 21:
            hold_score -= 15
            notes.append(f"Approaching theta acceleration zone ({dte} DTE)")

        # Adjust for moneyness
        if moneyness == "OTM" and dte < 14:
            hold_score -= 20
            notes.append("OTM with limited time - low probability of profit")

        # Adjust for IV
        if iv_rank > 70:
            hold_score += 10 if quantity < 0 else -10  # Good for shorts, bad for longs
            notes.append("IV elevated - premium rich")
        elif iv_rank < 30:
            hold_score += 10 if quantity > 0 else -10  # Good for longs, bad for shorts
            notes.append("IV low - premium cheap")

        # Adjust for probability
        if prob_profit < 0.3:
            hold_score -= 20
            notes.append(f"Low probability of profit ({prob_profit*100:.0f}%)")
        elif prob_profit > 0.7:
            hold_score += 10
            notes.append(f"High probability of profit ({prob_profit*100:.0f}%)")

        # Roll recommendation
        roll_recommendation = (
            dte < 14 and moneyness != "ITM" and hold_score < 40
        )
        if roll_recommendation:
            notes.append("Consider rolling to later expiration")

        # Suggested action
        if hold_score >= 60:
            suggested_action = "hold"
        elif hold_score >= 40:
            if roll_recommendation:
                suggested_action = "roll"
            else:
                suggested_action = "hold"
        elif hold_score >= 20:
            suggested_action = "roll" if roll_recommendation else "close"
        else:
            suggested_action = "close"

        return OptionAnalytics(
            symbol=symbol,
            underlying=underlying,
            underlying_price=spot,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            days_to_expiry=dte,
            bid=bid,
            ask=ask,
            mid=mid,
            last=last,
            spread_pct=spread_pct,
            greeks=greeks,
            dollar_delta=dollar_delta,
            dollar_theta=dollar_theta,
            dollar_gamma=dollar_gamma,
            dollar_vega=dollar_vega,
            iv=iv,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            historical_vol_20d=hv_20d,
            iv_vs_hv=iv_vs_hv,
            prob_itm=prob_itm,
            prob_profit=prob_profit,
            expected_move=expected_move,
            breakeven=breakeven,
            distance_to_breakeven=distance_to_breakeven,
            distance_to_breakeven_pct=distance_to_breakeven_pct,
            theta_per_day=theta_per_day,
            theta_acceleration=theta_acceleration,
            optimal_exit_dte=optimal_exit_dte,
            volume=volume,
            open_interest=open_interest,
            volume_oi_ratio=volume_oi_ratio,
            moneyness=moneyness,
            itm_amount=itm_amount,
            hold_score=max(0, min(100, hold_score)),
            roll_recommendation=roll_recommendation,
            suggested_action=suggested_action,
            notes=notes,
        )

    def analyze_portfolio(self, positions: list[str], quantities: list[int] | None = None) -> PositionOptionsAnalytics:
        """
        Analyze all options positions in portfolio.

        Args:
            positions: List of option symbols
            quantities: List of quantities (defaults to 1 for each)

        Returns:
            PositionOptionsAnalytics with aggregate analysis
        """
        if quantities is None:
            quantities = [1] * len(positions)

        analyzed_positions = []
        total_delta = 0.0
        total_theta = 0.0
        total_vega = 0.0
        total_gamma = 0.0
        max_loss = 0.0
        total_premium = 0.0
        weighted_iv_sum = 0.0
        total_dte = 0
        high_theta = []

        for symbol, qty in zip(positions, quantities):
            try:
                analytics = self.analyze_option(symbol, qty)
                analyzed_positions.append(analytics)

                # Aggregate Greeks (adjust for quantity)
                total_delta += analytics.dollar_delta * qty
                total_theta += analytics.dollar_theta * qty
                total_vega += analytics.dollar_vega * qty
                total_gamma += analytics.greeks.gamma * qty

                # Premium at risk
                position_premium = analytics.mid * 100 * abs(qty)
                total_premium += position_premium
                if qty > 0:  # Long positions
                    max_loss += position_premium

                # Weighted IV
                weighted_iv_sum += analytics.iv * position_premium

                # DTE tracking
                total_dte += analytics.days_to_expiry

                # High theta positions
                if abs(analytics.dollar_theta) > 10:
                    high_theta.append(
                        f"{analytics.underlying}: -${abs(analytics.dollar_theta):.2f}/day"
                    )

            except Exception as e:
                logger.warning(f"Failed to analyze {symbol}: {e}")

        # Calculate averages
        n_positions = len(analyzed_positions)
        calls = [p for p in analyzed_positions if p.option_type == "call"]
        puts = [p for p in analyzed_positions if p.option_type == "put"]
        near_expiry = [p for p in analyzed_positions if p.days_to_expiry < 7]

        weighted_avg_iv = weighted_iv_sum / total_premium if total_premium > 0 else 0
        avg_dte = total_dte / n_positions if n_positions > 0 else 0

        return PositionOptionsAnalytics(
            timestamp=datetime.now(),
            total_delta=total_delta,
            total_theta=total_theta,
            total_vega=total_vega,
            total_gamma=total_gamma,
            max_loss=max_loss,
            weighted_avg_iv=weighted_avg_iv,
            total_premium_at_risk=total_premium,
            positions=analyzed_positions,
            total_positions=n_positions,
            calls_count=len(calls),
            puts_count=len(puts),
            avg_dte=avg_dte,
            positions_near_expiry=len(near_expiry),
            high_theta_positions=high_theta[:5],
        )

    def get_greeks(self, symbol: str) -> OptionGreeks:
        """Quick Greeks lookup for a single option."""
        analytics = self.analyze_option(symbol)
        return analytics.greeks

    def find_rolls(self, symbol: str) -> list[dict]:
        """
        Find optimal roll candidates for an option.

        Args:
            symbol: Current option symbol

        Returns:
            List of roll suggestions with expected improvement
        """
        parsed = self._parse_option_symbol(symbol)
        underlying = parsed["underlying"]
        option_type = parsed["option_type"]
        strike = parsed["strike"]
        expiration = parsed["expiration"]

        spot = self._get_underlying_price(underlying)
        suggestions = []

        try:
            ticker = yf.Ticker(underlying)
            expirations = ticker.options

            # Filter to expirations further out
            current_dte = (expiration - date.today()).days

            for exp_str in expirations[:8]:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                new_dte = (exp_date - date.today()).days

                if new_dte > current_dte + 7:  # At least 1 week further out
                    # Analyze current and new position
                    new_symbol = f"{underlying}_{exp_str}_{strike}_{option_type[0].upper()}"

                    try:
                        current_analytics = self.analyze_option(symbol)
                        new_analytics = self.analyze_option(new_symbol)

                        theta_improvement = new_analytics.theta_per_day - current_analytics.theta_per_day
                        time_value_gained = new_analytics.mid - current_analytics.mid

                        suggestions.append({
                            "new_expiration": exp_str,
                            "new_dte": new_dte,
                            "dte_extension": new_dte - current_dte,
                            "new_price": new_analytics.mid,
                            "cost_to_roll": time_value_gained,
                            "theta_improvement": theta_improvement,
                            "new_prob_profit": new_analytics.prob_profit,
                        })

                    except Exception:
                        continue

        except Exception as e:
            logger.warning(f"Failed to find rolls for {symbol}: {e}")

        # Sort by theta improvement
        suggestions.sort(key=lambda x: x.get("theta_improvement", 0), reverse=True)
        return suggestions[:3]

    def get_summary(self, symbol: str) -> str:
        """Get human-readable summary for a single option."""
        analytics = self.analyze_option(symbol)
        return analytics.get_summary()
