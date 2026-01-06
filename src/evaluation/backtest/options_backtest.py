#!/usr/bin/env python3
"""
Options Strategy Backtester

Backtests multi-leg options strategies with IV dynamics modeling.
Supports all major strategy types from the Venezuela thesis research.

Usage:
    from src.evaluation.backtest.options_backtest import OptionsBacktester

    backtester = OptionsBacktester()
    results = backtester.backtest_diagonal_spread("SLB", start_date, end_date)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths
from src.evaluation.backtest.options_pricer import (
    Greeks,
    IVModel,
    Option,
    OptionPrice,
    OptionsPricer,
    OptionType,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = paths.options_backtest


class StrategyType(Enum):
    DIAGONAL_SPREAD = "diagonal_spread"
    CALENDAR_SPREAD = "calendar_spread"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    VERTICAL_SPREAD = "vertical_spread"
    PMCC = "pmcc"


@dataclass
class OptionsPosition:
    """A multi-leg options position."""
    strategy_type: StrategyType
    symbol: str
    legs: list[Option]
    entry_date: datetime
    entry_prices: list[float]  # Per leg
    entry_spot: float
    entry_iv: float
    quantity: int = 1

    def total_cost(self) -> float:
        """Calculate total entry cost (positive = debit)."""
        return sum(
            price * leg.quantity * 100
            for price, leg in zip(self.entry_prices, self.legs)
        )


@dataclass
class DailyPnL:
    """Daily P&L snapshot."""
    date: datetime
    spot_price: float
    iv: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    delta: float
    theta: float
    vega: float
    days_to_expiry: float


@dataclass
class BacktestResult:
    """Complete backtest results."""
    strategy_type: StrategyType
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_cost: float
    exit_value: float
    total_pnl: float
    total_return: float
    max_drawdown: float
    max_gain: float
    days_held: int
    daily_pnl: list[DailyPnL]
    exit_reason: str
    greeks_at_entry: Greeks
    greeks_at_exit: Greeks

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_type": self.strategy_type.value,
            "symbol": self.symbol,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "entry_cost": self.entry_cost,
            "exit_value": self.exit_value,
            "total_pnl": self.total_pnl,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "max_gain": self.max_gain,
            "days_held": self.days_held,
            "exit_reason": self.exit_reason,
        }


class OptionsBacktester:
    """Backtest options strategies with realistic IV dynamics."""

    def __init__(
        self,
        risk_free_rate: float = 0.05,
        transaction_cost: float = 0.65,  # Per contract
    ):
        self.pricer = OptionsPricer(risk_free_rate)
        self.iv_model = IVModel()
        self.transaction_cost = transaction_cost
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Fetch historical price data."""
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)
        return hist

    def _estimate_historical_iv(
        self,
        prices: pd.Series,
        window: int = 20,
    ) -> pd.Series:
        """Estimate historical IV from realized volatility."""
        returns = prices.pct_change().dropna()
        rv = returns.rolling(window).std() * np.sqrt(252)
        # IV typically trades at premium to RV
        iv = rv * 1.15
        return iv.fillna(0.30)

    def _value_position(
        self,
        position: OptionsPosition,
        spot: float,
        as_of: datetime,
        iv: float,
    ) -> tuple[float, Greeks]:
        """Value a multi-leg position."""
        total_value = 0
        total_delta = 0
        total_gamma = 0
        total_theta = 0
        total_vega = 0

        for leg in position.legs:
            price_result = self.pricer.price_option(leg, spot, as_of, iv)
            leg_value = price_result.theoretical_price * leg.quantity * 100

            total_value += leg_value
            total_delta += price_result.greeks.delta * leg.quantity
            total_gamma += price_result.greeks.gamma * leg.quantity
            total_theta += price_result.greeks.theta * leg.quantity * 100
            total_vega += price_result.greeks.vega * leg.quantity * 100

        greeks = Greeks(
            delta=total_delta,
            gamma=total_gamma,
            theta=total_theta,
            vega=total_vega,
            rho=0,
        )

        return total_value, greeks

    def backtest_position(
        self,
        position: OptionsPosition,
        price_data: pd.DataFrame,
        iv_path: np.ndarray | None = None,
        take_profit: float = 0.50,  # 50% of max profit
        stop_loss: float = -1.0,  # 100% of debit
        close_at_dte: int = 7,  # Close at 7 DTE
    ) -> BacktestResult:
        """
        Backtest an options position.

        Args:
            position: Options position to backtest
            price_data: Historical price DataFrame
            iv_path: Optional custom IV path (otherwise estimated)
            take_profit: Exit at this % gain
            stop_loss: Exit at this % loss (negative)
            close_at_dte: Close position at this many DTE

        Returns:
            BacktestResult with full P&L history
        """
        entry_cost = position.total_cost()
        daily_pnl_list = []

        # Get dates
        dates = price_data.index.tolist()
        start_idx = 0
        for i, d in enumerate(dates):
            if d.date() >= position.entry_date.date():
                start_idx = i
                break

        # Estimate IV if not provided
        if iv_path is None:
            iv_series = self._estimate_historical_iv(price_data["Close"])
            iv_path = iv_series.values[start_idx:]

        # Track position
        max_value = entry_cost
        min_value = entry_cost
        exit_date = None
        exit_value = 0
        exit_reason = "expiration"
        greeks_at_exit = None

        # Find earliest expiration
        earliest_exp = min(leg.expiration for leg in position.legs)

        for i, date in enumerate(dates[start_idx:]):
            if i >= len(iv_path):
                break

            spot = price_data["Close"].iloc[start_idx + i]
            iv = iv_path[i]
            as_of = datetime.combine(date.date(), datetime.min.time())

            # Check if expired
            dte = (earliest_exp - as_of).days
            if dte <= 0:
                exit_date = as_of
                exit_reason = "expiration"
                break

            # Value position
            value, greeks = self._value_position(position, spot, as_of, iv)

            # Calculate P&L
            unrealized_pnl = value - entry_cost
            unrealized_pnl_pct = unrealized_pnl / abs(entry_cost) if entry_cost != 0 else 0

            # Track extremes
            max_value = max(max_value, value)
            min_value = min(min_value, value)

            # Record daily P&L
            daily_pnl_list.append(DailyPnL(
                date=as_of,
                spot_price=spot,
                iv=iv,
                position_value=value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                delta=greeks.delta,
                theta=greeks.theta,
                vega=greeks.vega,
                days_to_expiry=dte,
            ))

            greeks_at_exit = greeks

            # Check exit conditions
            if unrealized_pnl_pct >= take_profit:
                exit_date = as_of
                exit_value = value
                exit_reason = f"take_profit ({take_profit:.0%})"
                break

            if unrealized_pnl_pct <= stop_loss:
                exit_date = as_of
                exit_value = value
                exit_reason = f"stop_loss ({stop_loss:.0%})"
                break

            if dte <= close_at_dte:
                exit_date = as_of
                exit_value = value
                exit_reason = f"close_at_{close_at_dte}_dte"
                break

        # Final values
        if exit_date is None:
            exit_date = dates[-1]
            if daily_pnl_list:
                exit_value = daily_pnl_list[-1].position_value
            else:
                exit_value = entry_cost

        total_pnl = exit_value - entry_cost
        total_return = total_pnl / abs(entry_cost) if entry_cost != 0 else 0

        # Calculate drawdown
        if daily_pnl_list:
            values = [d.position_value for d in daily_pnl_list]
            max_drawdown = min(0, min(v - entry_cost for v in values) / abs(entry_cost))
            max_gain = max(0, max(v - entry_cost for v in values) / abs(entry_cost))
        else:
            max_drawdown = 0
            max_gain = 0

        # Entry Greeks
        _, greeks_at_entry = self._value_position(
            position, position.entry_spot, position.entry_date, position.entry_iv
        )

        return BacktestResult(
            strategy_type=position.strategy_type,
            symbol=position.symbol,
            entry_date=position.entry_date,
            exit_date=exit_date,
            entry_cost=entry_cost,
            exit_value=exit_value,
            total_pnl=total_pnl,
            total_return=total_return,
            max_drawdown=max_drawdown,
            max_gain=max_gain,
            days_held=(exit_date - position.entry_date).days,
            daily_pnl=daily_pnl_list,
            exit_reason=exit_reason,
            greeks_at_entry=greeks_at_entry,
            greeks_at_exit=greeks_at_exit or greeks_at_entry,
        )

    def backtest_diagonal_spread(
        self,
        symbol: str,
        entry_date: datetime,
        long_dte: int = 90,
        short_dte: int = 30,
        long_delta: float = 0.70,  # ITM
        short_delta: float = 0.30,  # OTM
        iv_scenario: str = "normal",  # "normal", "event", "earnings"
    ) -> BacktestResult:
        """
        Backtest a diagonal call spread.

        This is the HIGHEST CONVICTION strategy from research.
        """
        # Fetch data
        end_date = entry_date + timedelta(days=long_dte + 30)
        price_data = self._get_historical_data(symbol, entry_date - timedelta(days=30), end_date)

        if price_data.empty:
            raise ValueError(f"No price data for {symbol}")

        # Get entry spot
        entry_idx = 0
        for i, d in enumerate(price_data.index):
            if d.date() >= entry_date.date():
                entry_idx = i
                break

        entry_spot = price_data["Close"].iloc[entry_idx]

        # Calculate strikes based on delta targets
        # Approximate: ITM strike = spot * (1 - (1-delta)*0.1)
        long_strike = round(entry_spot * (1 - (1 - long_delta) * 0.15), 0)  # ~5% ITM
        short_strike = round(entry_spot * (1 + short_delta * 0.20), 0)  # ~10% OTM

        # Create legs
        long_exp = entry_date + timedelta(days=long_dte)
        short_exp = entry_date + timedelta(days=short_dte)

        long_leg = Option(OptionType.CALL, long_strike, long_exp, quantity=1)
        short_leg = Option(OptionType.CALL, short_strike, short_exp, quantity=-1)

        # Estimate entry IV
        iv_series = self._estimate_historical_iv(price_data["Close"])
        entry_iv = iv_series.iloc[entry_idx] if entry_idx < len(iv_series) else 0.30

        # Price at entry
        long_price = self.pricer.price_option(long_leg, entry_spot, entry_date, entry_iv)
        short_price = self.pricer.price_option(short_leg, entry_spot, entry_date, entry_iv)

        position = OptionsPosition(
            strategy_type=StrategyType.DIAGONAL_SPREAD,
            symbol=symbol,
            legs=[long_leg, short_leg],
            entry_date=entry_date,
            entry_prices=[long_price.theoretical_price, short_price.theoretical_price],
            entry_spot=entry_spot,
            entry_iv=entry_iv,
        )

        # Generate IV path based on scenario
        days_to_backtest = (end_date - entry_date).days
        if iv_scenario == "event":
            iv_path = self.iv_model.geopolitical_event_model(
                entry_iv, days_before_event=5, days_after_event=days_to_backtest
            )
        elif iv_scenario == "earnings":
            iv_path = self.iv_model.earnings_iv_model(
                entry_iv, days_to_earnings=21, post_earnings_days=days_to_backtest - 21
            )
        else:
            iv_path = self.iv_model.simulate_iv_path(entry_iv, days_to_backtest, seed=42)

        return self.backtest_position(position, price_data, iv_path)

    def backtest_iron_condor(
        self,
        symbol: str,
        entry_date: datetime,
        dte: int = 30,
        wing_width: float = 0.10,  # 10% OTM for short strikes
        protection_width: float = 0.05,  # 5% further for long strikes
        iv_scenario: str = "event",
    ) -> BacktestResult:
        """
        Backtest an iron condor.

        Best for IV mean reversion post-event.
        """
        end_date = entry_date + timedelta(days=dte + 10)
        price_data = self._get_historical_data(symbol, entry_date - timedelta(days=30), end_date)

        if price_data.empty:
            raise ValueError(f"No price data for {symbol}")

        entry_idx = 0
        for i, d in enumerate(price_data.index):
            if d.date() >= entry_date.date():
                entry_idx = i
                break

        entry_spot = price_data["Close"].iloc[entry_idx]
        expiration = entry_date + timedelta(days=dte)

        # Calculate strikes
        put_short = round(entry_spot * (1 - wing_width), 0)
        put_long = round(entry_spot * (1 - wing_width - protection_width), 0)
        call_short = round(entry_spot * (1 + wing_width), 0)
        call_long = round(entry_spot * (1 + wing_width + protection_width), 0)

        # Create legs
        legs = [
            Option(OptionType.PUT, put_long, expiration, quantity=1),
            Option(OptionType.PUT, put_short, expiration, quantity=-1),
            Option(OptionType.CALL, call_short, expiration, quantity=-1),
            Option(OptionType.CALL, call_long, expiration, quantity=1),
        ]

        # Estimate entry IV
        iv_series = self._estimate_historical_iv(price_data["Close"])
        entry_iv = iv_series.iloc[entry_idx] if entry_idx < len(iv_series) else 0.30

        # Price at entry
        entry_prices = []
        for leg in legs:
            price = self.pricer.price_option(leg, entry_spot, entry_date, entry_iv)
            entry_prices.append(price.theoretical_price)

        position = OptionsPosition(
            strategy_type=StrategyType.IRON_CONDOR,
            symbol=symbol,
            legs=legs,
            entry_date=entry_date,
            entry_prices=entry_prices,
            entry_spot=entry_spot,
            entry_iv=entry_iv,
        )

        # IV path for event scenario
        days_to_backtest = (end_date - entry_date).days
        if iv_scenario == "event":
            # Simulate post-event IV crush
            iv_path = self.iv_model.geopolitical_event_model(
                entry_iv, days_before_event=0, days_after_event=days_to_backtest
            )
        else:
            iv_path = self.iv_model.simulate_iv_path(entry_iv, days_to_backtest, seed=42)

        return self.backtest_position(position, price_data, iv_path, take_profit=0.50)

    def backtest_calendar_spread(
        self,
        symbol: str,
        entry_date: datetime,
        short_dte: int = 30,
        long_dte: int = 60,
        iv_scenario: str = "normal",
    ) -> BacktestResult:
        """Backtest a calendar spread (same strike, different expirations)."""
        end_date = entry_date + timedelta(days=short_dte + 10)
        price_data = self._get_historical_data(symbol, entry_date - timedelta(days=30), end_date)

        if price_data.empty:
            raise ValueError(f"No price data for {symbol}")

        entry_idx = 0
        for i, d in enumerate(price_data.index):
            if d.date() >= entry_date.date():
                entry_idx = i
                break

        entry_spot = price_data["Close"].iloc[entry_idx]
        atm_strike = round(entry_spot, 0)

        short_exp = entry_date + timedelta(days=short_dte)
        long_exp = entry_date + timedelta(days=long_dte)

        legs = [
            Option(OptionType.CALL, atm_strike, long_exp, quantity=1),
            Option(OptionType.CALL, atm_strike, short_exp, quantity=-1),
        ]

        iv_series = self._estimate_historical_iv(price_data["Close"])
        entry_iv = iv_series.iloc[entry_idx] if entry_idx < len(iv_series) else 0.30

        entry_prices = []
        for leg in legs:
            price = self.pricer.price_option(leg, entry_spot, entry_date, entry_iv)
            entry_prices.append(price.theoretical_price)

        position = OptionsPosition(
            strategy_type=StrategyType.CALENDAR_SPREAD,
            symbol=symbol,
            legs=legs,
            entry_date=entry_date,
            entry_prices=entry_prices,
            entry_spot=entry_spot,
            entry_iv=entry_iv,
        )

        days_to_backtest = (end_date - entry_date).days
        iv_path = self.iv_model.simulate_iv_path(entry_iv, days_to_backtest, seed=42)

        return self.backtest_position(position, price_data, iv_path, close_at_dte=5)

    def run_strategy_suite(
        self,
        symbol: str,
        entry_date: datetime,
    ) -> dict[str, BacktestResult]:
        """Run all strategies for comparison."""
        results = {}

        strategies = [
            ("diagonal_spread", lambda: self.backtest_diagonal_spread(symbol, entry_date)),
            ("calendar_spread", lambda: self.backtest_calendar_spread(symbol, entry_date)),
            ("iron_condor", lambda: self.backtest_iron_condor(symbol, entry_date)),
        ]

        for name, backtest_func in strategies:
            try:
                results[name] = backtest_func()
                logger.info(f"{symbol} {name}: {results[name].total_return:.1%}")
            except Exception as e:
                logger.error(f"Failed to backtest {name} for {symbol}: {e}")

        return results

    def print_backtest_report(self, result: BacktestResult) -> None:
        """Print formatted backtest report."""
        print("\n" + "=" * 70)
        print(f"OPTIONS BACKTEST: {result.strategy_type.value.upper()} - {result.symbol}")
        print("=" * 70)

        print(f"\nEntry: {result.entry_date.strftime('%Y-%m-%d')}")
        print(f"Exit: {result.exit_date.strftime('%Y-%m-%d')} ({result.exit_reason})")
        print(f"Days Held: {result.days_held}")

        print(f"\nEntry Cost: ${result.entry_cost:,.2f}")
        print(f"Exit Value: ${result.exit_value:,.2f}")
        print(f"Total P&L: ${result.total_pnl:,.2f}")
        print(f"Total Return: {result.total_return:+.1%}")

        print(f"\nMax Drawdown: {result.max_drawdown:.1%}")
        print(f"Max Gain: {result.max_gain:.1%}")

        print(f"\nEntry Greeks:")
        print(f"  Delta: {result.greeks_at_entry.delta:.3f}")
        print(f"  Theta: ${result.greeks_at_entry.theta:.2f}/day")
        print(f"  Vega: ${result.greeks_at_entry.vega:.2f}/1% IV")

        # P&L curve summary
        if result.daily_pnl:
            print(f"\nP&L Curve (sampled):")
            sample_days = [0, len(result.daily_pnl) // 4, len(result.daily_pnl) // 2,
                          3 * len(result.daily_pnl) // 4, -1]
            for i in sample_days:
                if 0 <= i < len(result.daily_pnl):
                    d = result.daily_pnl[i]
                    print(f"  Day {i+1}: Spot ${d.spot_price:.2f}, IV {d.iv:.1%}, "
                          f"P&L {d.unrealized_pnl_pct:+.1%}")


def main():
    """Run backtest examples."""
    backtester = OptionsBacktester()

    # Test with SLB - diagonal spread
    entry_date = datetime(2025, 7, 1)  # Historical test

    print("Running Venezuela Thesis Options Backtest...")
    print("=" * 70)

    # Test diagonal spread
    try:
        result = backtester.backtest_diagonal_spread(
            "SLB",
            entry_date,
            iv_scenario="event"
        )
        backtester.print_backtest_report(result)
    except Exception as e:
        logger.error(f"Diagonal spread backtest failed: {e}")

    # Test iron condor
    try:
        result = backtester.backtest_iron_condor(
            "SLB",
            entry_date,
            iv_scenario="event"
        )
        backtester.print_backtest_report(result)
    except Exception as e:
        logger.error(f"Iron condor backtest failed: {e}")

    # Run full suite comparison
    print("\n" + "=" * 70)
    print("STRATEGY COMPARISON")
    print("=" * 70)

    for symbol in ["SLB", "VLO"]:
        try:
            results = backtester.run_strategy_suite(symbol, entry_date)
            print(f"\n{symbol}:")
            for name, r in results.items():
                print(f"  {name}: {r.total_return:+.1%} ({r.exit_reason})")
        except Exception as e:
            logger.error(f"Suite failed for {symbol}: {e}")


if __name__ == "__main__":
    main()
