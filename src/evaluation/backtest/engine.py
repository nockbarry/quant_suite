"""Vectorized backtesting engine."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ...core import Direction, Portfolio, Signal, Symbol
from ...strategies.base import Strategy
from .costs import CostModel, PercentageCost


@dataclass
class BacktestConfig:
    """Configuration for backtest execution."""

    initial_capital: float = 100_000.0
    cost_model: CostModel = field(default_factory=PercentageCost)
    position_size: float = 0.1  # 10% per position
    max_positions: int = 10
    allow_short: bool = True
    rebalance_frequency: str = "daily"  # daily, weekly, monthly
    benchmark: str | None = "SPY"
    # Execution timing to prevent look-ahead bias
    signal_delay: int = 1  # Days to delay signal execution (1 = next day)
    use_open_price: bool = True  # Execute at open price (vs close)


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    returns: pd.Series
    positions: pd.DataFrame
    trades: pd.DataFrame
    signals: pd.DataFrame
    metrics: dict[str, float]
    config: BacktestConfig
    strategy_name: str
    start_date: datetime
    end_date: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert results to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "metrics": self.metrics,
            "num_trades": len(self.trades),
            "final_value": float(self.returns.iloc[-1]) if len(self.returns) > 0 else 0,
        }


class VectorizedBacktest:
    """
    Vectorized backtesting engine.

    Efficiently simulates strategy performance using vectorized operations
    on pandas DataFrames.
    """

    def __init__(self, config: BacktestConfig | None = None):
        """
        Initialize backtest engine.

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()

    def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> BacktestResult:
        """
        Run backtest for a strategy.

        Args:
            strategy: Strategy to backtest
            data: OHLCV data (single or multi-asset)
            start_date: Start date for backtest
            end_date: End date for backtest

        Returns:
            BacktestResult with performance metrics
        """
        # Convert to dict format if single DataFrame
        if isinstance(data, pd.DataFrame):
            if len(strategy.universe) > 0:
                data = {strategy.universe[0]: data}
            else:
                data = {"ASSET": data}

        # Filter by date range
        if start_date or end_date:
            data = self._filter_dates(data, start_date, end_date)

        # Get common date index
        common_dates = self._get_common_dates(data)
        if len(common_dates) == 0:
            raise ValueError("No common dates in data")

        # Generate signals for all dates
        all_signals = self._generate_all_signals(strategy, data, common_dates)

        # Simulate trading
        returns, positions, trades = self._simulate(
            data,
            all_signals,
            common_dates,
        )

        # Calculate metrics
        metrics = self._calculate_metrics(returns, trades)

        return BacktestResult(
            returns=returns,
            positions=positions,
            trades=trades,
            signals=all_signals,
            metrics=metrics,
            config=self.config,
            strategy_name=strategy.name,
            start_date=common_dates[0].to_pydatetime(),
            end_date=common_dates[-1].to_pydatetime(),
        )

    def _filter_dates(
        self,
        data: dict[Symbol, pd.DataFrame],
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> dict[Symbol, pd.DataFrame]:
        """Filter data by date range."""
        filtered = {}
        for symbol, df in data.items():
            df_filtered = df.copy()
            if start_date:
                df_filtered = df_filtered[df_filtered.index >= start_date]
            if end_date:
                df_filtered = df_filtered[df_filtered.index <= end_date]
            if len(df_filtered) > 0:
                filtered[symbol] = df_filtered
        return filtered

    def _get_common_dates(
        self,
        data: dict[Symbol, pd.DataFrame],
    ) -> pd.DatetimeIndex:
        """Get common dates across all assets."""
        if not data:
            return pd.DatetimeIndex([])

        indices = [df.index for df in data.values()]
        common = indices[0]
        for idx in indices[1:]:
            common = common.intersection(idx)
        return common.sort_values()

    def _generate_all_signals(
        self,
        strategy: Strategy,
        data: dict[Symbol, pd.DataFrame],
        dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """Generate signals for all dates with proper temporal constraints.

        IMPORTANT: To prevent look-ahead bias, signals are generated using
        data strictly BEFORE the signal date. The signal is then executed
        with a delay (default: next day's open).
        """
        required_history = strategy.get_required_history()
        signal_delay = self.config.signal_delay
        signals_list = []

        for i, date in enumerate(dates):
            if i < required_history:
                continue

            # CRITICAL: Use data strictly BEFORE the current date to avoid look-ahead
            # This simulates making a decision at end of previous day
            historical_data = {}
            for symbol, df in data.items():
                # Only include data BEFORE current date (not including today)
                mask = df.index < date
                df_hist = df[mask].tail(required_history + 1)
                if len(df_hist) >= required_history:
                    historical_data[symbol] = df_hist

            if not historical_data:
                continue

            # Generate signals based on prior data
            # The timestamp is when the signal would be EXECUTED (after delay)
            try:
                # Pass the prior day's date as the decision point
                prior_date = dates[i - 1] if i > 0 else date
                signals = strategy.generate_signals(historical_data, prior_date.to_pydatetime())

                for signal in signals:
                    # Apply signal delay - signal executes signal_delay days later
                    exec_idx = i + signal_delay - 1
                    if exec_idx < len(dates):
                        exec_date = dates[exec_idx]
                        signals_list.append({
                            "timestamp": exec_date,  # Execution date, not signal date
                            "signal_date": prior_date,  # When signal was generated
                            "symbol": signal.symbol,
                            "direction": signal.direction.value,
                            "strength": signal.strength,
                            "confidence": signal.confidence,
                        })
            except Exception as e:
                continue

        if not signals_list:
            return pd.DataFrame(columns=["timestamp", "signal_date", "symbol", "direction", "strength", "confidence"])

        return pd.DataFrame(signals_list)

    def _simulate(
        self,
        data: dict[Symbol, pd.DataFrame],
        signals: pd.DataFrame,
        dates: pd.DatetimeIndex,
    ) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
        """Simulate trading based on signals with proper execution timing."""
        # Initialize
        capital = self.config.initial_capital
        positions: dict[Symbol, float] = {}  # symbol -> quantity
        position_prices: dict[Symbol, float] = {}  # symbol -> entry price

        # Track results
        portfolio_values = []
        position_history = []
        trades = []

        # Create price panels - close for valuation, open for execution
        close_prices = pd.DataFrame({
            symbol: df["close"].reindex(dates)
            for symbol, df in data.items()
        })

        # Use open prices for trade execution to avoid look-ahead bias
        if self.config.use_open_price:
            exec_prices = pd.DataFrame({
                symbol: df["open"].reindex(dates) if "open" in df.columns else df["close"].reindex(dates)
                for symbol, df in data.items()
            })
        else:
            exec_prices = close_prices

        # For backwards compatibility
        prices = close_prices

        # Convert signals to lookup
        signal_lookup: dict[datetime, dict[Symbol, float]] = {}
        if len(signals) > 0:
            for _, row in signals.iterrows():
                ts = row["timestamp"]
                if ts not in signal_lookup:
                    signal_lookup[ts] = {}
                signal_lookup[ts][row["symbol"]] = row["strength"]

        for i, date in enumerate(dates):
            current_close = close_prices.loc[date]
            current_exec = exec_prices.loc[date]

            # Calculate current portfolio value using CLOSE prices (mark-to-market)
            portfolio_value = capital
            for symbol, qty in positions.items():
                if symbol in current_close and not pd.isna(current_close[symbol]):
                    portfolio_value += qty * current_close[symbol]

            portfolio_values.append({
                "date": date,
                "value": portfolio_value,
                "cash": capital,
            })

            # Record positions
            position_history.append({
                "date": date,
                "positions": positions.copy(),
                "portfolio_value": portfolio_value,
            })

            # Process signals for this date - use EXECUTION prices (open) for trades
            if date in signal_lookup:
                for symbol, strength in signal_lookup[date].items():
                    # Check execution price availability
                    if symbol not in current_exec or pd.isna(current_exec[symbol]):
                        continue

                    # Execute at open price to avoid look-ahead bias
                    price = current_exec[symbol]
                    target_position = self._calculate_target_position(
                        strength,
                        portfolio_value,
                        price,
                    )

                    current_position = positions.get(symbol, 0)
                    trade_qty = target_position - current_position

                    if abs(trade_qty) > 0.01:  # Minimum trade threshold
                        # Execute trade
                        cost = self.config.cost_model.calculate(
                            price,
                            abs(trade_qty),
                            "buy" if trade_qty > 0 else "sell",
                        )

                        trade_value = trade_qty * price
                        capital -= trade_value + cost

                        if target_position != 0:
                            positions[symbol] = target_position
                            position_prices[symbol] = price
                        elif symbol in positions:
                            del positions[symbol]
                            if symbol in position_prices:
                                del position_prices[symbol]

                        trades.append({
                            "date": date,
                            "symbol": symbol,
                            "quantity": trade_qty,
                            "price": price,
                            "cost": cost,
                            "side": "buy" if trade_qty > 0 else "sell",
                        })

        # Create result DataFrames
        value_df = pd.DataFrame(portfolio_values).set_index("date")
        returns = value_df["value"].pct_change().fillna(0)
        returns.name = "returns"

        positions_df = pd.DataFrame([
            {"date": h["date"], **h["positions"]}
            for h in position_history
        ])
        if len(positions_df) > 0:
            positions_df = positions_df.set_index("date")

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
            columns=["date", "symbol", "quantity", "price", "cost", "side"]
        )

        # Convert returns to cumulative for final output
        cumulative_returns = (1 + returns).cumprod() * self.config.initial_capital

        return cumulative_returns, positions_df, trades_df

    def _calculate_target_position(
        self,
        strength: float,
        portfolio_value: float,
        price: float,
    ) -> float:
        """Calculate target position size based on signal strength."""
        # Position value based on strength and configured size
        position_value = portfolio_value * self.config.position_size * abs(strength)

        # Calculate quantity
        quantity = position_value / price

        # Apply direction
        if strength < 0 and self.config.allow_short:
            quantity = -quantity
        elif strength < 0:
            quantity = 0

        return quantity

    def _calculate_metrics(
        self,
        returns: pd.Series,
        trades: pd.DataFrame,
    ) -> dict[str, float]:
        """Calculate performance metrics."""
        if len(returns) < 2:
            return {}

        # Convert cumulative to period returns
        period_returns = returns.pct_change().dropna()

        # Basic metrics
        total_return = (returns.iloc[-1] / self.config.initial_capital) - 1
        days = (returns.index[-1] - returns.index[0]).days
        years = days / 365.25

        cagr = (1 + total_return) ** (1 / max(years, 0.001)) - 1 if years > 0 else 0

        # Risk metrics
        volatility = period_returns.std() * np.sqrt(252)
        sharpe = (period_returns.mean() * 252) / max(volatility, 0.001) if volatility > 0 else 0

        # Drawdown
        cumulative = (1 + period_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Trade statistics
        num_trades = len(trades)
        if num_trades > 0:
            total_costs = trades["cost"].sum()
        else:
            total_costs = 0

        return {
            "total_return": float(total_return),
            "cagr": float(cagr),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "num_trades": num_trades,
            "total_costs": float(total_costs),
            "final_value": float(returns.iloc[-1]),
        }


def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame | dict[Symbol, pd.DataFrame],
    initial_capital: float = 100_000,
    **kwargs: Any,
) -> BacktestResult:
    """
    Convenience function to run a backtest.

    Args:
        strategy: Strategy to backtest
        data: OHLCV data
        initial_capital: Starting capital
        **kwargs: Additional BacktestConfig parameters

    Returns:
        BacktestResult
    """
    config = BacktestConfig(initial_capital=initial_capital, **kwargs)
    engine = VectorizedBacktest(config)
    return engine.run(strategy, data)
