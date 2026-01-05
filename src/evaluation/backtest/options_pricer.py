#!/usr/bin/env python3
"""
Options Pricing Engine

Black-Scholes pricing with IV modeling for backtesting.
Supports multi-leg strategies and IV dynamics simulation.

Usage:
    from src.evaluation.backtest.options_pricer import OptionsPricer, Option

    pricer = OptionsPricer()
    price = pricer.price_option(option, spot=100, days_to_expiry=30, iv=0.30)
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

import numpy as np
from scipy.stats import norm


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class Option:
    """Single option contract."""
    option_type: OptionType
    strike: float
    expiration: datetime
    quantity: int = 1  # Positive = long, negative = short

    def days_to_expiry(self, as_of: datetime) -> float:
        """Calculate days to expiration."""
        delta = self.expiration - as_of
        return max(0, delta.days + delta.seconds / 86400)


@dataclass
class Greeks:
    """Option Greeks."""
    delta: float
    gamma: float
    theta: float  # Per day
    vega: float  # Per 1% IV change
    rho: float


@dataclass
class OptionPrice:
    """Complete option pricing result."""
    theoretical_price: float
    intrinsic_value: float
    time_value: float
    greeks: Greeks


class OptionsPricer:
    """Black-Scholes options pricing engine."""

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize pricer.

        Args:
            risk_free_rate: Annual risk-free rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate

    def _d1(self, S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d1 for Black-Scholes."""
        if T <= 0 or sigma <= 0:
            return 0
        return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))

    def _d2(self, S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d2 for Black-Scholes."""
        if T <= 0 or sigma <= 0:
            return 0
        return self._d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

    def price_option(
        self,
        option: Option,
        spot: float,
        as_of: datetime,
        iv: float,
        dividend_yield: float = 0.0,
    ) -> OptionPrice:
        """
        Price an option using Black-Scholes.

        Args:
            option: Option contract to price
            spot: Current underlying price
            as_of: Pricing date
            iv: Implied volatility (annualized, e.g., 0.30 = 30%)
            dividend_yield: Annual dividend yield

        Returns:
            OptionPrice with theoretical price and Greeks
        """
        T = option.days_to_expiry(as_of) / 365.0
        K = option.strike
        r = self.risk_free_rate
        q = dividend_yield
        S = spot

        # Handle expiration
        if T <= 0:
            if option.option_type == OptionType.CALL:
                intrinsic = max(0, S - K)
            else:
                intrinsic = max(0, K - S)
            return OptionPrice(
                theoretical_price=intrinsic,
                intrinsic_value=intrinsic,
                time_value=0,
                greeks=Greeks(
                    delta=1.0 if intrinsic > 0 else 0.0,
                    gamma=0,
                    theta=0,
                    vega=0,
                    rho=0,
                ),
            )

        # Black-Scholes
        d1 = self._d1(S, K, T, r - q, iv)
        d2 = self._d2(S, K, T, r - q, iv)

        if option.option_type == OptionType.CALL:
            price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            intrinsic = max(0, S - K)
            delta = math.exp(-q * T) * norm.cdf(d1)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
            intrinsic = max(0, K - S)
            delta = -math.exp(-q * T) * norm.cdf(-d1)

        # Greeks
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * iv * math.sqrt(T))
        theta = (
            -S * math.exp(-q * T) * norm.pdf(d1) * iv / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * norm.cdf(d2 if option.option_type == OptionType.CALL else -d2)
            + q * S * math.exp(-q * T) * norm.cdf(d1 if option.option_type == OptionType.CALL else -d1)
        ) / 365  # Per day

        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T) / 100  # Per 1% IV

        rho = (
            K * T * math.exp(-r * T) * norm.cdf(d2 if option.option_type == OptionType.CALL else -d2)
        ) / 100

        if option.option_type == OptionType.PUT:
            rho = -rho

        return OptionPrice(
            theoretical_price=price,
            intrinsic_value=intrinsic,
            time_value=price - intrinsic,
            greeks=Greeks(
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                rho=rho,
            ),
        )

    def implied_volatility(
        self,
        option: Option,
        spot: float,
        as_of: datetime,
        market_price: float,
        max_iterations: int = 100,
        tolerance: float = 0.0001,
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson.

        Args:
            option: Option contract
            spot: Current underlying price
            as_of: Pricing date
            market_price: Observed market price
            max_iterations: Max Newton-Raphson iterations
            tolerance: Convergence tolerance

        Returns:
            Implied volatility
        """
        iv = 0.30  # Initial guess

        for _ in range(max_iterations):
            price_result = self.price_option(option, spot, as_of, iv)
            diff = price_result.theoretical_price - market_price

            if abs(diff) < tolerance:
                return iv

            vega = price_result.greeks.vega * 100  # Convert back
            if vega < 0.001:
                break

            iv = iv - diff / vega
            iv = max(0.01, min(5.0, iv))  # Bound IV

        return iv


class IVModel:
    """
    Implied Volatility dynamics model.

    Models IV behavior including:
    - Mean reversion
    - Term structure
    - Event-driven spikes
    - Earnings IV crush
    """

    def __init__(
        self,
        base_iv: float = 0.30,
        mean_reversion_speed: float = 0.1,
        vol_of_vol: float = 0.5,
    ):
        """
        Initialize IV model.

        Args:
            base_iv: Long-term mean IV
            mean_reversion_speed: Speed of mean reversion (daily)
            vol_of_vol: Volatility of volatility
        """
        self.base_iv = base_iv
        self.mean_reversion_speed = mean_reversion_speed
        self.vol_of_vol = vol_of_vol

    def simulate_iv_path(
        self,
        start_iv: float,
        num_days: int,
        events: list[tuple[int, float]] | None = None,
        seed: int | None = None,
    ) -> np.ndarray:
        """
        Simulate IV path with mean reversion and events.

        Args:
            start_iv: Starting IV level
            num_days: Number of days to simulate
            events: List of (day, iv_shock) tuples
            seed: Random seed for reproducibility

        Returns:
            Array of daily IV values
        """
        if seed is not None:
            np.random.seed(seed)

        iv_path = np.zeros(num_days)
        iv_path[0] = start_iv

        # Convert events to dict for lookup
        event_shocks = {}
        if events:
            for day, shock in events:
                event_shocks[day] = shock

        for t in range(1, num_days):
            # Mean reversion
            drift = self.mean_reversion_speed * (self.base_iv - iv_path[t - 1])

            # Random shock
            random_shock = self.vol_of_vol * iv_path[t - 1] * np.random.normal() / np.sqrt(252)

            # Event shock
            event_shock = event_shocks.get(t, 0)

            iv_path[t] = max(0.05, iv_path[t - 1] + drift + random_shock + event_shock)

        return iv_path

    def earnings_iv_model(
        self,
        base_iv: float,
        days_to_earnings: int,
        post_earnings_days: int = 5,
    ) -> np.ndarray:
        """
        Model IV behavior around earnings.

        Research-based:
        - IV inflates 20-50% in week before earnings
        - IV crushes 30-40% immediately after earnings

        Args:
            base_iv: Normal IV level
            days_to_earnings: Days until earnings
            post_earnings_days: Days to simulate after earnings

        Returns:
            Array of IV values
        """
        total_days = days_to_earnings + post_earnings_days
        iv_path = np.zeros(total_days)

        for t in range(total_days):
            if t < days_to_earnings:
                # IV inflation approaching earnings
                days_until = days_to_earnings - t
                if days_until <= 7:
                    # Rapid inflation in final week
                    inflation = 0.30 * (1 - days_until / 7)
                elif days_until <= 14:
                    # Gradual inflation
                    inflation = 0.10 * (1 - (days_until - 7) / 7)
                else:
                    inflation = 0

                iv_path[t] = base_iv * (1 + inflation)
            else:
                # Post-earnings IV crush
                days_after = t - days_to_earnings
                if days_after == 0:
                    # Immediate crush of 35%
                    iv_path[t] = base_iv * 1.30 * 0.65
                else:
                    # Gradual normalization
                    crush_remaining = max(0, 1 - days_after / 5)
                    iv_path[t] = base_iv * (1 + 0.05 * crush_remaining)

        return iv_path

    def geopolitical_event_model(
        self,
        base_iv: float,
        days_before_event: int = 5,
        days_after_event: int = 30,
        spike_magnitude: float = 0.40,
        reversion_days: int = 21,
    ) -> np.ndarray:
        """
        Model IV behavior around geopolitical events.

        Research-based (Iraq 2003, Libya 2011, Ukraine 2022):
        - IV spikes 25-40% on event
        - IV normalizes over 3-4 weeks (faster than fundamentals)

        Args:
            base_iv: Normal IV level
            days_before_event: Days to simulate before event
            days_after_event: Days to simulate after event
            spike_magnitude: Size of IV spike (e.g., 0.40 = 40% increase)
            reversion_days: Days for IV to normalize

        Returns:
            Array of IV values
        """
        total_days = days_before_event + days_after_event
        iv_path = np.zeros(total_days)

        event_day = days_before_event

        for t in range(total_days):
            if t < event_day:
                # Pre-event: slight elevation as uncertainty builds
                days_to_event = event_day - t
                if days_to_event <= 3:
                    elevation = 0.10 * (1 - days_to_event / 3)
                else:
                    elevation = 0
                iv_path[t] = base_iv * (1 + elevation)
            elif t == event_day:
                # Event day: spike
                iv_path[t] = base_iv * (1 + spike_magnitude)
            else:
                # Post-event: exponential decay back to base
                days_after = t - event_day
                decay = np.exp(-days_after / (reversion_days / 3))
                iv_path[t] = base_iv * (1 + spike_magnitude * decay)

        return iv_path


def main():
    """Test options pricing."""
    pricer = OptionsPricer()

    # Create a call option
    expiration = datetime.now() + timedelta(days=30)
    call = Option(OptionType.CALL, strike=100, expiration=expiration)

    # Price it
    result = pricer.price_option(call, spot=100, as_of=datetime.now(), iv=0.30)

    print("Option Pricing Test")
    print("=" * 40)
    print(f"Spot: $100, Strike: $100, IV: 30%, DTE: 30")
    print(f"Theoretical Price: ${result.theoretical_price:.2f}")
    print(f"Intrinsic Value: ${result.intrinsic_value:.2f}")
    print(f"Time Value: ${result.time_value:.2f}")
    print(f"\nGreeks:")
    print(f"  Delta: {result.greeks.delta:.4f}")
    print(f"  Gamma: {result.greeks.gamma:.4f}")
    print(f"  Theta: ${result.greeks.theta:.4f}/day")
    print(f"  Vega: ${result.greeks.vega:.4f}/1% IV")

    # Test IV models
    print("\n" + "=" * 40)
    print("IV Model Test - Geopolitical Event")
    print("=" * 40)

    iv_model = IVModel(base_iv=0.30)
    geo_iv = iv_model.geopolitical_event_model(0.30, days_before_event=5, days_after_event=30)

    print(f"Day -5 (pre-event): {geo_iv[0]:.1%}")
    print(f"Day 0 (event): {geo_iv[5]:.1%}")
    print(f"Day +1: {geo_iv[6]:.1%}")
    print(f"Day +7: {geo_iv[12]:.1%}")
    print(f"Day +14: {geo_iv[19]:.1%}")
    print(f"Day +21: {geo_iv[26]:.1%}")
    print(f"Day +30: {geo_iv[34]:.1%}")


if __name__ == "__main__":
    main()
