"""PDT (Pattern Day Trader) aware backtesting framework.

Provides PDT-compliant backtesting with:
- Minimum holding period enforcement
- Day trade tracking over rolling 5-day window
- Holding period optimization
- Separate strategy universes for budget vs full accounts
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """Account type classification."""

    BUDGET = "budget"  # Under $25k, PDT restricted
    MARGIN = "margin"  # Over $25k, no PDT restrictions
    CASH = "cash"  # Cash account, no PDT but T+1 settlement


@dataclass
class PDTConfig:
    """PDT rule configuration."""

    # Core PDT rules
    max_day_trades_per_5_days: int = 3  # Pattern day trader limit
    min_holding_days_budget: int = 2  # Minimum hold for budget accounts
    pdt_threshold: float = 25000.0  # Account value threshold

    # Account-specific settings
    cash_settlement_days: int = 1  # T+1 for cash accounts

    # Position limits
    max_position_pct: float = 0.25  # Maximum single position as % of portfolio
    max_daily_loss_pct: float = 0.05  # Maximum daily loss


@dataclass
class DayTrade:
    """Record of a day trade."""

    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl: float

    def is_same_day(self) -> bool:
        """Check if entry and exit are same day."""
        return self.entry_date.date() == self.exit_date.date()


@dataclass
class Position:
    """Active position with entry tracking."""

    symbol: str
    shares: int
    entry_price: float
    entry_date: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class HoldingPeriodResult:
    """Result of testing a specific holding period."""

    holding_period_days: int
    sharpe_ratio: float
    total_return: float
    num_trades: int
    win_rate: float
    max_drawdown: float
    pdt_compliant: bool
    day_trades_count: int
    avg_holding_days: float
    p_value: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "holding_period_days": self.holding_period_days,
            "sharpe_ratio": self.sharpe_ratio,
            "total_return": self.total_return,
            "num_trades": self.num_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "pdt_compliant": self.pdt_compliant,
            "day_trades_count": self.day_trades_count,
            "avg_holding_days": self.avg_holding_days,
            "p_value": self.p_value,
            **self.metadata,
        }


class PDTTracker:
    """
    Tracks day trades and enforces PDT rules.

    Maintains rolling 5-day window of day trades and
    determines if new trades are allowed.
    """

    def __init__(self, config: PDTConfig | None = None):
        """
        Initialize PDT tracker.

        Args:
            config: PDT configuration
        """
        self.config = config or PDTConfig()
        self.day_trades: list[DayTrade] = []
        self.positions: dict[str, Position] = {}

    def reset(self) -> None:
        """Reset tracker state."""
        self.day_trades = []
        self.positions = {}

    def _get_day_trades_in_window(self, as_of_date: datetime) -> list[DayTrade]:
        """Get day trades in the rolling 5-day window."""
        window_start = as_of_date - timedelta(days=5)
        return [
            dt for dt in self.day_trades
            if dt.exit_date >= window_start and dt.exit_date <= as_of_date
        ]

    def get_remaining_day_trades(self, as_of_date: datetime) -> int:
        """Get remaining allowed day trades."""
        used = len(self._get_day_trades_in_window(as_of_date))
        return max(0, self.config.max_day_trades_per_5_days - used)

    def can_day_trade(self, as_of_date: datetime) -> bool:
        """Check if day trading is allowed."""
        return self.get_remaining_day_trades(as_of_date) > 0

    def can_close_position(
        self,
        symbol: str,
        close_date: datetime,
        account_type: AccountType = AccountType.BUDGET,
    ) -> tuple[bool, str]:
        """
        Check if a position can be closed.

        Args:
            symbol: Symbol to close
            close_date: Date of close
            account_type: Account type

        Returns:
            Tuple of (can_close, reason)
        """
        if symbol not in self.positions:
            return False, "No position to close"

        position = self.positions[symbol]
        days_held = (close_date - position.entry_date).days

        if account_type == AccountType.MARGIN:
            # No restrictions for margin accounts over $25k
            return True, "Margin account - no PDT restrictions"

        if account_type == AccountType.BUDGET:
            # Check minimum holding period
            if days_held < self.config.min_holding_days_budget:
                return False, f"Minimum hold {self.config.min_holding_days_budget} days, held {days_held}"

            # If same-day close, check day trade limit
            if days_held == 0:
                if not self.can_day_trade(close_date):
                    return False, "Day trade limit reached (3/5 days)"

            return True, "PDT compliant"

        if account_type == AccountType.CASH:
            # Cash accounts have settlement restrictions
            if days_held < self.config.cash_settlement_days:
                return False, f"Cash settlement requires T+{self.config.cash_settlement_days}"
            return True, "Cash account compliant"

        return True, "Unknown account type - allowing"

    def open_position(
        self,
        symbol: str,
        shares: int,
        price: float,
        date: datetime,
    ) -> None:
        """Open or add to a position."""
        if symbol in self.positions:
            # Average into existing position
            pos = self.positions[symbol]
            total_cost = pos.shares * pos.entry_price + shares * price
            total_shares = pos.shares + shares
            pos.shares = total_shares
            pos.entry_price = total_cost / total_shares
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                shares=shares,
                entry_price=price,
                entry_date=date,
                current_price=price,
            )

    def close_position(
        self,
        symbol: str,
        price: float,
        date: datetime,
    ) -> DayTrade | None:
        """Close a position and record if day trade."""
        if symbol not in self.positions:
            return None

        position = self.positions[symbol]
        pnl = (price - position.entry_price) * position.shares

        trade = DayTrade(
            symbol=symbol,
            entry_date=position.entry_date,
            exit_date=date,
            entry_price=position.entry_price,
            exit_price=price,
            shares=position.shares,
            pnl=pnl,
        )

        # Record if day trade
        if trade.is_same_day():
            self.day_trades.append(trade)

        del self.positions[symbol]
        return trade


class PDTAwareBacktest:
    """
    PDT-aware backtesting engine.

    Runs backtests with PDT rule enforcement:
    - Enforces minimum holding period
    - Tracks day trades over rolling window
    - Calculates PDT-compliant metrics
    """

    def __init__(
        self,
        config: PDTConfig | None = None,
        account_type: AccountType = AccountType.BUDGET,
        initial_capital: float = 10000.0,
        transaction_cost_bps: float = 10.0,
    ):
        """
        Initialize PDT-aware backtest.

        Args:
            config: PDT configuration
            account_type: Account type for PDT rules
            initial_capital: Starting capital
            transaction_cost_bps: Transaction cost in basis points
        """
        self.config = config or PDTConfig()
        self.account_type = account_type
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.tracker = PDTTracker(self.config)

    def run_with_holding_period(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        min_holding_days: int = 0,
    ) -> HoldingPeriodResult:
        """
        Run backtest with enforced minimum holding period.

        Args:
            signals: DataFrame with signal column (-1, 0, 1)
            prices: DataFrame with close prices
            min_holding_days: Minimum days to hold positions

        Returns:
            HoldingPeriodResult with metrics
        """
        self.tracker.reset()
        equity = [self.initial_capital]
        position = 0
        entry_date = None
        entry_price = 0
        trades = []
        day_trades = 0

        for i in range(1, len(signals)):
            date = signals.index[i]
            signal = signals.iloc[i]
            price = prices.iloc[i]
            prev_price = prices.iloc[i - 1]

            # Update equity
            if position != 0:
                pnl = position * (price - prev_price)
                equity.append(equity[-1] + pnl)
            else:
                equity.append(equity[-1])

            # Check for exit signals
            if position != 0 and signal == 0:
                # Check if we can close
                days_held = (date - entry_date).days if entry_date else 0

                if days_held >= min_holding_days:
                    # Close position
                    trade_pnl = position * (price - entry_price)
                    trade_pnl -= abs(position * price) * self.transaction_cost_bps / 10000
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "days_held": days_held,
                        "pnl": trade_pnl,
                    })

                    if days_held == 0:
                        day_trades += 1

                    position = 0
                    entry_date = None

            # Check for entry signals
            if position == 0 and signal != 0:
                # Enter position
                position = signal  # 1 for long, -1 for short
                entry_date = date
                entry_price = price
                # Transaction cost on entry
                equity[-1] -= abs(position * price) * self.transaction_cost_bps / 10000

        # Close any remaining position
        if position != 0 and entry_date:
            days_held = (signals.index[-1] - entry_date).days
            trade_pnl = position * (prices.iloc[-1] - entry_price)
            trades.append({
                "entry_date": entry_date,
                "exit_date": signals.index[-1],
                "days_held": days_held,
                "pnl": trade_pnl,
            })

        # Calculate metrics
        equity_series = pd.Series(equity, index=signals.index[:len(equity)])
        returns = equity_series.pct_change().dropna()

        sharpe = returns.mean() / (returns.std() + 1e-8) * np.sqrt(252) if len(returns) > 1 else 0
        total_return = (equity[-1] / self.initial_capital - 1)

        # Win rate
        winning_trades = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = winning_trades / len(trades) if trades else 0

        # Max drawdown
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min()

        # Average holding days
        avg_holding = np.mean([t["days_held"] for t in trades]) if trades else 0

        # PDT compliance
        pdt_compliant = (
            day_trades <= self.config.max_day_trades_per_5_days
            and min_holding_days >= self.config.min_holding_days_budget
        ) if self.account_type == AccountType.BUDGET else True

        return HoldingPeriodResult(
            holding_period_days=min_holding_days,
            sharpe_ratio=float(sharpe),
            total_return=float(total_return),
            num_trades=len(trades),
            win_rate=float(win_rate),
            max_drawdown=float(max_drawdown),
            pdt_compliant=pdt_compliant,
            day_trades_count=day_trades,
            avg_holding_days=float(avg_holding),
        )

    def compare_holding_periods(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        holding_periods: list[int] | None = None,
    ) -> list[HoldingPeriodResult]:
        """
        Compare performance across different holding periods.

        Args:
            signals: DataFrame with signal column
            prices: DataFrame with close prices
            holding_periods: List of holding periods to test

        Returns:
            List of HoldingPeriodResult for each period
        """
        if holding_periods is None:
            holding_periods = [0, 2, 5, 10, 20]

        results = []
        for period in holding_periods:
            result = self.run_with_holding_period(signals, prices, period)
            results.append(result)
            logger.info(
                f"Holding period {period} days: "
                f"Sharpe={result.sharpe_ratio:.2f}, "
                f"Return={result.total_return:.1%}, "
                f"PDT={result.pdt_compliant}"
            )

        return results


class HoldingPeriodOptimizer:
    """
    Finds optimal holding periods for strategies.

    Tests different holding periods and identifies:
    - Best period for budget accounts (PDT compliant)
    - Best period for full accounts (unrestricted)
    - Trade-offs between periods
    """

    def __init__(
        self,
        backtest: PDTAwareBacktest | None = None,
    ):
        """
        Initialize optimizer.

        Args:
            backtest: PDTAwareBacktest instance
        """
        self.backtest = backtest or PDTAwareBacktest()
        self.results: dict[str, list[HoldingPeriodResult]] = {}

    def run_full_optimization(
        self,
        strategy_signals: dict[str, pd.DataFrame],
        strategy_prices: dict[str, pd.DataFrame],
        holding_periods: list[int] | None = None,
    ) -> dict[str, list[HoldingPeriodResult]]:
        """
        Run holding period optimization for multiple strategies.

        Args:
            strategy_signals: Dict of strategy_name -> signals DataFrame
            strategy_prices: Dict of strategy_name -> prices DataFrame
            holding_periods: Periods to test

        Returns:
            Dict of strategy_name -> list of results
        """
        if holding_periods is None:
            holding_periods = [0, 2, 5, 10, 20]

        for name, signals in strategy_signals.items():
            prices = strategy_prices.get(name)
            if prices is None:
                logger.warning(f"No prices for strategy {name}")
                continue

            results = self.backtest.compare_holding_periods(
                signals, prices, holding_periods
            )
            self.results[name] = results

        return self.results

    def get_best_for_budget_account(
        self,
        metric: str = "sharpe_ratio",
    ) -> dict[str, HoldingPeriodResult]:
        """
        Get best holding period for each strategy (budget account).

        Args:
            metric: Metric to optimize

        Returns:
            Dict of strategy_name -> best result
        """
        best = {}
        for name, results in self.results.items():
            # Filter to PDT compliant only
            compliant = [r for r in results if r.pdt_compliant]
            if not compliant:
                logger.warning(f"No PDT-compliant results for {name}")
                continue

            # Find best by metric
            best_result = max(compliant, key=lambda r: getattr(r, metric))
            best[name] = best_result

        return best

    def get_best_for_full_account(
        self,
        metric: str = "sharpe_ratio",
    ) -> dict[str, HoldingPeriodResult]:
        """
        Get best holding period for full account (no PDT restrictions).

        Args:
            metric: Metric to optimize

        Returns:
            Dict of strategy_name -> best result
        """
        best = {}
        for name, results in self.results.items():
            if not results:
                continue

            best_result = max(results, key=lambda r: getattr(r, metric))
            best[name] = best_result

        return best

    def export_recommendations(self) -> pd.DataFrame:
        """
        Export holding period recommendations as DataFrame.

        Returns:
            DataFrame with recommendations
        """
        rows = []
        budget_best = self.get_best_for_budget_account()
        full_best = self.get_best_for_full_account()

        for name in self.results.keys():
            budget = budget_best.get(name)
            full = full_best.get(name)

            rows.append({
                "strategy": name,
                "budget_holding_days": budget.holding_period_days if budget else None,
                "budget_sharpe": budget.sharpe_ratio if budget else None,
                "budget_return": budget.total_return if budget else None,
                "full_holding_days": full.holding_period_days if full else None,
                "full_sharpe": full.sharpe_ratio if full else None,
                "full_return": full.total_return if full else None,
                "pdt_compliant": budget.pdt_compliant if budget else False,
            })

        return pd.DataFrame(rows)

    def find_optimal_holding_period(
        self,
        results: list[HoldingPeriodResult],
        metric: str = "sharpe_ratio",
        require_pdt_compliant: bool = True,
    ) -> HoldingPeriodResult | None:
        """
        Find optimal holding period from results.

        Args:
            results: List of holding period results
            metric: Metric to optimize
            require_pdt_compliant: Only consider PDT compliant periods

        Returns:
            Best result or None
        """
        filtered = results
        if require_pdt_compliant:
            filtered = [r for r in results if r.pdt_compliant]

        if not filtered:
            return None

        return max(filtered, key=lambda r: getattr(r, metric))


def get_pdt_holding_recommendation(
    account_value: float,
    config: PDTConfig | None = None,
) -> dict[str, Any]:
    """
    Get holding period recommendations based on account value.

    Args:
        account_value: Current account value
        config: PDT configuration

    Returns:
        Recommendation dict
    """
    config = config or PDTConfig()

    if account_value >= config.pdt_threshold:
        return {
            "account_type": AccountType.MARGIN.value,
            "min_holding_days": 0,
            "max_day_trades": "unlimited",
            "recommendation": "Full day trading allowed",
        }
    else:
        return {
            "account_type": AccountType.BUDGET.value,
            "min_holding_days": config.min_holding_days_budget,
            "max_day_trades": config.max_day_trades_per_5_days,
            "recommendation": (
                f"Minimum {config.min_holding_days_budget}-day hold, "
                f"max {config.max_day_trades_per_5_days} day trades per 5 days"
            ),
        }
