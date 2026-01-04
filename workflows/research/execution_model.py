"""
Realistic Execution Model for Backtesting

Simulates real-world trading constraints:
- Transaction costs (commission + slippage)
- Execution timing (signal at close -> execute at next open)
- Discrete position sizing (whole shares)
- Trade counting (including reversals)

Key Principle:
    Signal at close[t] -> Execute at open[t+1]

This ensures no look-ahead bias in execution.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ExecutionConfig:
    """Configuration for realistic execution simulation."""

    # Transaction costs (in basis points)
    commission_bps: float = 1.0       # 1 bp = 0.01% per trade
    slippage_bps: float = 5.0         # Conservative estimate for liquid stocks

    # Position constraints
    min_position_usd: float = 100.0   # Minimum position size
    initial_capital: float = 100_000.0

    # Execution timing
    execution_price: Literal["next_open", "close"] = "next_open"

    # Target horizon for walk-forward gap
    target_horizon: int = 5

    @property
    def total_cost_bps(self) -> float:
        """Total round-trip cost in basis points."""
        return (self.commission_bps + self.slippage_bps) * 2

    @property
    def cost_per_trade(self) -> float:
        """Cost per trade as a decimal (not basis points)."""
        return (self.commission_bps + self.slippage_bps) / 10000


class ExecutionSimulator:
    """
    Simulates realistic trade execution with costs and timing.

    Usage:
        config = ExecutionConfig(commission_bps=1.0, slippage_bps=5.0)
        exec_sim = ExecutionSimulator(config)

        # Apply to backtest
        net_returns = exec_sim.compute_net_returns(df, positions)
        trade_stats = exec_sim.count_trades(positions)
    """

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()

    def compute_realistic_returns(
        self,
        df: pd.DataFrame,
        positions: pd.Series,
        apply_costs: bool = True,
    ) -> pd.Series:
        """
        Compute strategy returns with realistic execution timing.

        Args:
            df: Price DataFrame with 'open' and 'close' columns
            positions: Signal-based positions (before lag)
            apply_costs: Whether to deduct transaction costs

        Returns:
            Net returns series after costs

        Timeline:
            - Signal generated after close on day t (using close[t] data)
            - Order submitted overnight
            - Execution at open[t+1] (with slippage)
            - Position held until next signal change
        """
        if self.config.execution_price == "next_open":
            # Use open-to-open returns for realistic execution
            if 'open' in df.columns:
                price_returns = df['open'].pct_change()
            else:
                # Fall back to close-to-close with warning
                price_returns = df['close'].pct_change()
        else:
            price_returns = df['close'].pct_change()

        # Position from yesterday's signal, executed at today's open
        # The positions should already be lagged by the strategy
        gross_returns = positions * price_returns

        if apply_costs:
            # Compute trade costs
            trade_costs = self._compute_trade_costs(positions, price_returns)
            net_returns = gross_returns - trade_costs
            return net_returns

        return gross_returns

    def _compute_trade_costs(
        self,
        positions: pd.Series,
        returns: pd.Series,
    ) -> pd.Series:
        """
        Compute transaction costs as a return drag.

        Each trade (buy or sell) incurs commission + slippage.
        Position reversals (long to short) count as 2 trades.
        """
        costs = pd.Series(0.0, index=positions.index)

        # Detect position changes
        pos_diff = positions.diff().abs()

        # Cost per unit of position change
        cost_per_unit = self.config.cost_per_trade

        # Total cost = cost_per_trade * |position_change|
        costs = pos_diff * cost_per_unit

        return costs.fillna(0)

    def count_trades(self, positions: pd.Series) -> dict:
        """
        Count actual trades accurately.

        Returns:
            Dictionary with trade statistics
        """
        pos_diff = positions.diff()

        # Count entries and exits
        buys = (pos_diff > 0).sum()
        sells = (pos_diff < 0).sum()
        total_trades = buys + sells

        # Position reversals (long to short or vice versa)
        # These are effectively 2 trades: close old + open new
        long_to_short = ((positions.shift(1) > 0) & (positions < 0)).sum()
        short_to_long = ((positions.shift(1) < 0) & (positions > 0)).sum()
        reversals = long_to_short + short_to_long

        # Average daily turnover
        daily_turnover = pos_diff.abs().mean()

        # Annualized turnover
        annualized_turnover = daily_turnover * 252

        return {
            'buys': int(buys),
            'sells': int(sells),
            'total_trades': int(total_trades),
            'reversals': int(reversals),
            'effective_trades': int(total_trades + reversals),  # Reversals count double
            'daily_turnover': float(daily_turnover),
            'annualized_turnover': float(annualized_turnover),
        }

    def discretize_positions(
        self,
        positions: pd.Series,
        prices: pd.Series,
        capital: float = None,
    ) -> pd.Series:
        """
        Convert fractional signal positions to discrete share counts.

        This ensures we're not assuming impossible fractional shares.

        Args:
            positions: Fractional positions (-1 to 1)
            prices: Current prices for position sizing
            capital: Available capital (uses config default if not specified)

        Returns:
            Discretized positions (whole shares * sign)
        """
        if capital is None:
            capital = self.config.initial_capital

        # Dollar allocation per position
        dollars_per_position = capital * positions.abs()

        # Convert to shares (rounded to whole numbers)
        shares = (dollars_per_position / prices).round()

        # Zero out positions below minimum
        shares[shares * prices < self.config.min_position_usd] = 0

        # Restore direction
        return shares * np.sign(positions)

    def estimate_total_costs(
        self,
        positions: pd.Series,
        holding_period_days: int = None,
    ) -> dict:
        """
        Estimate total trading costs for a strategy.

        Returns:
            Dictionary with cost breakdown
        """
        trade_stats = self.count_trades(positions)
        n_trading_days = len(positions)

        # If no holding period specified, estimate from turnover
        if holding_period_days is None:
            if trade_stats['daily_turnover'] > 0:
                holding_period_days = int(1 / trade_stats['daily_turnover'])
            else:
                holding_period_days = n_trading_days

        # Cost calculations
        cost_per_trade = self.config.cost_per_trade
        total_trades = trade_stats['effective_trades']

        # Annual cost as percentage of capital
        trades_per_year = total_trades * (252 / n_trading_days) if n_trading_days > 0 else 0
        annual_cost_pct = trades_per_year * cost_per_trade * 100

        return {
            'total_trades': total_trades,
            'trades_per_year': trades_per_year,
            'cost_per_trade_bps': (self.config.commission_bps + self.config.slippage_bps),
            'annual_cost_pct': annual_cost_pct,
            'estimated_holding_days': holding_period_days,
        }


class WalkForwardValidator:
    """
    Validates walk-forward methodology to prevent data leakage.

    Key requirement: Gap between train end and test start must be >= target_horizon
    """

    def __init__(self, target_horizon: int = 5):
        self.target_horizon = target_horizon

    def validate_split(
        self,
        train_end_idx: int,
        test_start_idx: int,
    ) -> dict:
        """
        Validate that walk-forward split has sufficient gap.

        Returns:
            Validation result with pass/fail and details
        """
        gap = test_start_idx - train_end_idx
        is_valid = gap >= self.target_horizon

        return {
            'is_valid': is_valid,
            'gap_days': gap,
            'required_gap': self.target_horizon,
            'message': (
                f"✓ Gap of {gap} days >= {self.target_horizon} required"
                if is_valid else
                f"✗ Gap of {gap} days < {self.target_horizon} required - DATA LEAKAGE!"
            )
        }

    def get_safe_train_end(
        self,
        test_start_idx: int,
    ) -> int:
        """
        Get the latest safe training end index given a test start.

        Training should end at least target_horizon days before test starts
        to prevent the target variable from leaking test period prices.
        """
        return test_start_idx - self.target_horizon


def apply_execution_model(
    df: pd.DataFrame,
    positions: pd.Series,
    config: ExecutionConfig = None,
) -> dict:
    """
    Convenience function to apply full execution model.

    Args:
        df: Price DataFrame
        positions: Strategy positions (after lag)
        config: Execution configuration

    Returns:
        Dictionary with returns, costs, and trade statistics
    """
    if config is None:
        config = ExecutionConfig()

    simulator = ExecutionSimulator(config)

    # Compute net returns
    net_returns = simulator.compute_realistic_returns(df, positions, apply_costs=True)
    gross_returns = simulator.compute_realistic_returns(df, positions, apply_costs=False)

    # Trade statistics
    trade_stats = simulator.count_trades(positions)
    cost_estimate = simulator.estimate_total_costs(positions)

    # Performance metrics
    total_return = (1 + net_returns.dropna()).prod() - 1
    total_return_gross = (1 + gross_returns.dropna()).prod() - 1

    sharpe = (
        net_returns.mean() / net_returns.std() * np.sqrt(252)
        if net_returns.std() > 0 else 0
    )
    sharpe_gross = (
        gross_returns.mean() / gross_returns.std() * np.sqrt(252)
        if gross_returns.std() > 0 else 0
    )

    return {
        'net_returns': net_returns,
        'gross_returns': gross_returns,
        'total_return_net': total_return * 100,
        'total_return_gross': total_return_gross * 100,
        'cost_drag': (total_return_gross - total_return) * 100,
        'sharpe_net': sharpe,
        'sharpe_gross': sharpe_gross,
        'trade_stats': trade_stats,
        'cost_estimate': cost_estimate,
    }


if __name__ == "__main__":
    # Example usage
    import yfinance as yf

    # Get sample data
    df = yf.download("AAPL", period="2y", progress=False)
    df.columns = [c.lower() for c in df.columns]

    # Simple momentum strategy
    momentum = df['close'].pct_change(20).shift(1)
    positions = pd.Series(0.0, index=df.index)
    positions[momentum > 0] = 1
    positions[momentum < 0] = -1
    positions = positions.shift(1).fillna(0)

    # Apply execution model
    config = ExecutionConfig(
        commission_bps=1.0,
        slippage_bps=5.0,
    )

    results = apply_execution_model(df, positions, config)

    print("Execution Model Results:")
    print(f"  Gross Return: {results['total_return_gross']:.2f}%")
    print(f"  Net Return: {results['total_return_net']:.2f}%")
    print(f"  Cost Drag: {results['cost_drag']:.2f}%")
    print(f"  Sharpe (Net): {results['sharpe_net']:.2f}")
    print(f"  Total Trades: {results['trade_stats']['total_trades']}")
    print(f"  Annual Turnover: {results['trade_stats']['annualized_turnover']:.2f}")
