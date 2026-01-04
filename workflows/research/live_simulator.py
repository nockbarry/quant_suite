"""
Live Trading Day Simulator

Simulates how strategies would work on an actual trading day with
realistic constraints and timing.

Timeline:
    - 9:30 AM: Market opens
    - 4:00 PM: Market closes
    - After close: Compute signals for TOMORROW
    - Next day 9:30 AM: Execute orders at open

This ensures no look-ahead bias in the simulation.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
import yfinance as yf


@dataclass
class TradingDayResult:
    """Result from simulating a single trading day."""
    date: datetime
    signal: float
    position: float
    entry_price: float
    features_date: datetime  # Date features were computed from
    pnl: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class LiveSimulationResult:
    """Complete result from live trading simulation."""
    daily_results: list[TradingDayResult]
    total_pnl: float
    total_costs: float
    sharpe_ratio: float
    max_drawdown: float
    n_trades: int
    avg_holding_days: float

    def summary(self) -> str:
        """Generate summary string."""
        return f"""
Live Trading Simulation Results
================================
Total P&L: {self.total_pnl:.2f}%
Total Costs: {self.total_costs:.2f}%
Net P&L: {self.total_pnl - self.total_costs:.2f}%
Sharpe Ratio: {self.sharpe_ratio:.2f}
Max Drawdown: {self.max_drawdown:.2f}%
Number of Trades: {self.n_trades}
Avg Holding Period: {self.avg_holding_days:.1f} days
"""


class LiveTradingSimulator:
    """
    Simulates how strategies would work on a live trading day.

    This class enforces realistic constraints:
    1. Features only use data available at signal time
    2. Signals generated after close, executed next open
    3. Transaction costs and slippage applied
    4. Discrete position sizing

    Usage:
        simulator = LiveTradingSimulator(slippage_bps=5.0, commission_bps=1.0)
        result = simulator.simulate_strategy(df, strategy_func)
    """

    def __init__(
        self,
        slippage_bps: float = 5.0,
        commission_bps: float = 1.0,
        initial_capital: float = 100_000.0,
        min_position_usd: float = 100.0,
    ):
        """
        Initialize simulator.

        Args:
            slippage_bps: Slippage in basis points per trade
            commission_bps: Commission in basis points per trade
            initial_capital: Starting capital
            min_position_usd: Minimum position size in dollars
        """
        self.slippage_bps = slippage_bps
        self.commission_bps = commission_bps
        self.initial_capital = initial_capital
        self.min_position_usd = min_position_usd

    def get_data_as_of(
        self,
        df: pd.DataFrame,
        as_of_date: datetime,
        price_type: str = "close",
    ) -> pd.DataFrame:
        """
        Get data available as of a specific date.

        Args:
            df: Full price DataFrame
            as_of_date: The date to get data as of
            price_type: "close" means data up to and including close[as_of_date]

        Returns:
            DataFrame with only data that would be available
        """
        if price_type == "close":
            return df.loc[:as_of_date].copy()
        elif price_type == "open":
            # For open, we don't have same-day close yet
            return df.loc[:as_of_date - timedelta(days=1)].copy()
        else:
            raise ValueError(f"Unknown price_type: {price_type}")

    def simulate_trading_day(
        self,
        date: datetime,
        df: pd.DataFrame,
        compute_features: Callable[[pd.DataFrame], pd.DataFrame],
        generate_signal: Callable[[pd.DataFrame], float],
        prev_position: float = 0.0,
    ) -> TradingDayResult:
        """
        Simulate one trading day with realistic constraints.

        Args:
            date: The trading day to simulate
            df: Full price DataFrame
            compute_features: Function to compute features from data
            generate_signal: Function to generate signal from features
            prev_position: Previous day's position

        Returns:
            TradingDayResult with all details
        """
        # 1. Get data available at market open (yesterday's close)
        yesterday = date - timedelta(days=1)
        available_data = self.get_data_as_of(df, yesterday, "close")

        if len(available_data) < 60:  # Need enough history for features
            return TradingDayResult(
                date=date,
                signal=0.0,
                position=0.0,
                entry_price=0.0,
                features_date=yesterday,
                pnl=0.0,
            )

        # 2. Compute features from yesterday's data only
        features = compute_features(available_data)

        # 3. Generate signal from yesterday's features
        try:
            signal = generate_signal(features)
        except Exception:
            signal = 0.0

        # 4. Get today's open price for execution
        if date not in df.index:
            return TradingDayResult(
                date=date,
                signal=signal,
                position=prev_position,
                entry_price=0.0,
                features_date=yesterday,
                pnl=0.0,
            )

        today_open = df.loc[date, 'open'] if 'open' in df.columns else df.loc[date, 'close']

        # 5. Apply slippage to execution price
        slippage_factor = 1 + (self.slippage_bps / 10000) * np.sign(signal - prev_position)
        execution_price = today_open * slippage_factor

        # 6. Compute commission
        position_change = abs(signal - prev_position)
        commission = position_change * (self.commission_bps / 10000)

        # 7. Calculate P&L if we had a previous position
        pnl = 0.0
        if prev_position != 0 and date in df.index:
            # Use today's close for marking
            today_close = df.loc[date, 'close']
            if today_open > 0:
                daily_return = (today_close - today_open) / today_open
                pnl = prev_position * daily_return * 100  # As percentage

        return TradingDayResult(
            date=date,
            signal=signal,
            position=signal,  # New position after today
            entry_price=execution_price,
            features_date=yesterday,
            pnl=pnl,
            commission=commission * 100,  # As percentage
            slippage=(self.slippage_bps / 100) * position_change if position_change > 0 else 0,
        )

    def simulate_strategy(
        self,
        df: pd.DataFrame,
        compute_features: Callable[[pd.DataFrame], pd.DataFrame],
        generate_signal: Callable[[pd.DataFrame], float],
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> LiveSimulationResult:
        """
        Simulate a strategy over a date range.

        Args:
            df: Price DataFrame with OHLCV
            compute_features: Function to compute features
            generate_signal: Function to generate trading signal (-1 to 1)
            start_date: Start of simulation (default: 60 days after data start)
            end_date: End of simulation (default: data end)

        Returns:
            LiveSimulationResult with full analysis
        """
        # Determine date range
        all_dates = df.index.tolist()

        if start_date is None:
            start_idx = 60  # Need 60 days of history
        else:
            start_idx = all_dates.index(start_date) if start_date in all_dates else 60

        if end_date is None:
            end_idx = len(all_dates)
        else:
            end_idx = all_dates.index(end_date) + 1 if end_date in all_dates else len(all_dates)

        # Run simulation
        results = []
        prev_position = 0.0

        for i in range(start_idx, end_idx):
            date = all_dates[i]
            result = self.simulate_trading_day(
                date=date,
                df=df,
                compute_features=compute_features,
                generate_signal=generate_signal,
                prev_position=prev_position,
            )
            results.append(result)
            prev_position = result.position

        # Calculate summary statistics
        if not results:
            return LiveSimulationResult(
                daily_results=[],
                total_pnl=0.0,
                total_costs=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                n_trades=0,
                avg_holding_days=0.0,
            )

        pnls = [r.pnl for r in results]
        costs = [r.commission + r.slippage for r in results]

        total_pnl = sum(pnls)
        total_costs = sum(costs)

        # Sharpe ratio
        pnl_std = np.std(pnls) if len(pnls) > 1 else 1
        sharpe = (np.mean(pnls) / pnl_std * np.sqrt(252)) if pnl_std > 0 else 0

        # Max drawdown
        cum_pnl = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum_pnl)
        drawdown = cum_pnl - peak
        max_dd = min(drawdown) if len(drawdown) > 0 else 0

        # Trade count
        positions = [r.position for r in results]
        pos_changes = np.diff([0] + positions)
        n_trades = int(np.sum(np.abs(pos_changes) > 0.1))

        # Average holding period
        in_position = np.array([abs(p) > 0.1 for p in positions])
        if n_trades > 0:
            avg_holding = in_position.sum() / n_trades
        else:
            avg_holding = 0

        return LiveSimulationResult(
            daily_results=results,
            total_pnl=total_pnl,
            total_costs=total_costs,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            n_trades=n_trades,
            avg_holding_days=avg_holding,
        )


def verify_feature_availability(feature_date: datetime, signal_date: datetime) -> bool:
    """
    Ensure features used for signal are actually available.

    Rule: feature_date must be < signal_date
    - Close price available after 4 PM
    - Signal generated after close
    - Execution next morning
    """
    return feature_date < signal_date


def create_simple_momentum_strategy():
    """Create a simple momentum strategy for testing."""

    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        """Compute features using only available data."""
        features = pd.DataFrame(index=df.index)
        features['momentum_20'] = df['close'].pct_change(20)
        features['rsi'] = compute_rsi(df['close'], 14)
        return features

    def generate_signal(features: pd.DataFrame) -> float:
        """Generate signal from latest features."""
        if len(features) < 20:
            return 0.0

        latest = features.iloc[-1]
        momentum = latest.get('momentum_20', 0)

        if pd.isna(momentum):
            return 0.0

        # Simple momentum signal
        if momentum > 0.02:
            return 1.0
        elif momentum < -0.02:
            return -1.0
        else:
            return 0.0

    return compute_features, generate_signal


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI indicator."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


if __name__ == "__main__":
    # Example usage
    print("Live Trading Simulator Example")
    print("=" * 50)

    # Get sample data
    df = yf.download("AAPL", period="2y", progress=False)
    df.columns = [c.lower() for c in df.columns]

    # Create simple strategy
    compute_features, generate_signal = create_simple_momentum_strategy()

    # Run simulation
    simulator = LiveTradingSimulator(
        slippage_bps=5.0,
        commission_bps=1.0,
    )

    result = simulator.simulate_strategy(
        df=df,
        compute_features=compute_features,
        generate_signal=generate_signal,
    )

    print(result.summary())
