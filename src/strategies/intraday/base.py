"""Base class for intraday trading strategies.

Intraday strategies:
- Operate on minute-level data (1m, 5m, 15m)
- Must close positions before market close
- Have stricter risk limits than swing strategies
- PDT-aware (integrate with PDTManager)
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any

import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe


class SessionPhase(str, Enum):
    """Phase of the trading session."""
    PRE_MARKET = "pre_market"  # 4:00-9:30 AM
    OPENING = "opening"  # 9:30-10:00 AM (high volatility)
    MID_DAY = "mid_day"  # 10:00-2:30 PM (lower volume)
    POWER_HOUR = "power_hour"  # 2:30-4:00 PM (volume picks up)
    CLOSE = "close"  # 3:55-4:00 PM (final minutes)
    AFTER_HOURS = "after_hours"  # 4:00-8:00 PM
    CLOSED = "closed"


# Session boundaries (ET)
SESSION_TIMES = {
    SessionPhase.PRE_MARKET: (time(4, 0), time(9, 30)),
    SessionPhase.OPENING: (time(9, 30), time(10, 0)),
    SessionPhase.MID_DAY: (time(10, 0), time(14, 30)),
    SessionPhase.POWER_HOUR: (time(14, 30), time(15, 55)),
    SessionPhase.CLOSE: (time(15, 55), time(16, 0)),
    SessionPhase.AFTER_HOURS: (time(16, 0), time(20, 0)),
}


def get_session_phase(t: time | datetime | None = None) -> SessionPhase:
    """Get current session phase."""
    if t is None:
        t = datetime.now().time()
    elif isinstance(t, datetime):
        t = t.time()

    for phase, (start, end) in SESSION_TIMES.items():
        if start <= t < end:
            return phase

    return SessionPhase.CLOSED


@dataclass
class IntradaySignal:
    """Enhanced signal for intraday trading."""

    # Core signal data
    symbol: str
    direction: Direction
    strength: float  # -1 to 1
    confidence: float  # 0 to 1
    timestamp: datetime
    strategy_name: str

    # Intraday-specific
    session_phase: SessionPhase
    entry_price: float
    stop_loss: float
    take_profit: float
    max_hold_minutes: int = 120  # Default 2 hours

    # Risk management
    position_size_pct: float = 5.0  # % of portfolio
    risk_reward_ratio: float = 2.0

    # Context
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stop_loss_pct(self) -> float:
        """Stop loss as percentage."""
        if self.entry_price == 0:
            return 0
        return abs(self.stop_loss - self.entry_price) / self.entry_price * 100

    @property
    def take_profit_pct(self) -> float:
        """Take profit as percentage."""
        if self.entry_price == 0:
            return 0
        return abs(self.take_profit - self.entry_price) / self.entry_price * 100

    @property
    def must_exit_by(self) -> datetime:
        """Time by which position must be closed."""
        # Always exit by 3:55 PM ET for day trades
        exit_time = self.timestamp.replace(hour=15, minute=55, second=0)
        hold_exit = self.timestamp + pd.Timedelta(minutes=self.max_hold_minutes)
        return min(exit_time, hold_exit)

    def to_core_signal(self) -> Signal:
        """Convert to core Signal object."""
        return Signal(
            timestamp=self.timestamp,
            symbol=self.symbol,
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            signal_type=SignalType.ENTRY_LONG if self.direction == Direction.LONG else SignalType.ENTRY_SHORT,
            strategy_name=self.strategy_name,
            metadata={
                **self.metadata,
                "intraday": True,
                "session_phase": self.session_phase.value,
                "entry_price": self.entry_price,
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "max_hold_minutes": self.max_hold_minutes,
                "must_exit_by": self.must_exit_by.isoformat(),
                "position_size_pct": self.position_size_pct,
                "reason": self.reason,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "session_phase": self.session_phase.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_hold_minutes": self.max_hold_minutes,
            "must_exit_by": self.must_exit_by.isoformat(),
            "position_size_pct": self.position_size_pct,
            "risk_reward_ratio": self.risk_reward_ratio,
            "reason": self.reason,
        }


@dataclass
class IntradayStrategyConfig:
    """Configuration for intraday strategies."""

    name: str
    universe: list[str]
    timeframe: Timeframe = Timeframe.MINUTE_5

    # Session preferences
    allowed_phases: list[SessionPhase] = field(default_factory=lambda: [
        SessionPhase.OPENING,
        SessionPhase.MID_DAY,
        SessionPhase.POWER_HOUR,
    ])
    avoid_first_minutes: int = 5  # Avoid first N minutes of opening
    close_before_minutes: int = 5  # Close positions N minutes before close

    # Risk limits (stricter than swing)
    max_position_pct: float = 10.0  # Max 10% of portfolio
    max_loss_per_trade_pct: float = 1.0  # Max 1% loss per trade
    max_daily_loss_pct: float = 3.0  # Stop trading if down 3% on day
    max_trades_per_day: int = 5  # Limit number of trades

    # Signal requirements
    min_confidence: float = 0.6
    min_strength: float = 0.3

    # Strategy-specific parameters
    parameters: dict[str, Any] = field(default_factory=dict)

    enabled: bool = True


class IntradayStrategy:
    """
    Base class for intraday trading strategies.

    Subclasses must implement:
    - generate_signals(): Generate intraday signals from minute data
    - get_required_bars(): Number of bars needed
    """

    name: str = "intraday_base"
    description: str = ""
    version: str = "1.0.0"

    def __init__(self, config: IntradayStrategyConfig):
        """
        Initialize intraday strategy.

        Args:
            config: Strategy configuration
        """
        self.config = config
        self._trade_count_today = 0
        self._daily_pnl = 0.0
        self._last_reset_date = None

    @abstractmethod
    def generate_signals(
        self,
        data: pd.DataFrame,
        timestamp: datetime | None = None,
    ) -> list[IntradaySignal]:
        """
        Generate intraday trading signals.

        Args:
            data: Minute OHLCV data
            timestamp: Current timestamp

        Returns:
            List of IntradaySignal objects
        """
        ...

    @abstractmethod
    def get_required_bars(self) -> int:
        """
        Get number of minute bars required.

        Returns:
            Number of bars needed
        """
        ...

    def should_trade(self, timestamp: datetime | None = None) -> tuple[bool, str]:
        """
        Check if conditions allow trading.

        Returns:
            Tuple of (should_trade, reason)
        """
        timestamp = timestamp or datetime.now()

        # Check session phase
        phase = get_session_phase(timestamp)
        if phase not in self.config.allowed_phases:
            return False, f"Session phase {phase.value} not in allowed phases"

        # Check daily trade limit
        self._check_daily_reset(timestamp)
        if self._trade_count_today >= self.config.max_trades_per_day:
            return False, f"Daily trade limit ({self.config.max_trades_per_day}) reached"

        # Check daily loss limit
        if self._daily_pnl <= -self.config.max_daily_loss_pct:
            return False, f"Daily loss limit ({self.config.max_daily_loss_pct}%) reached"

        # Check time relative to market open/close
        market_time = timestamp.time()

        # Avoid first N minutes
        if phase == SessionPhase.OPENING:
            open_time = time(9, 30)
            minutes_since_open = (
                (market_time.hour - open_time.hour) * 60 +
                (market_time.minute - open_time.minute)
            )
            if minutes_since_open < self.config.avoid_first_minutes:
                return False, f"Avoiding first {self.config.avoid_first_minutes} minutes"

        # Close positions before market close
        close_time = time(16, 0)
        minutes_to_close = (
            (close_time.hour - market_time.hour) * 60 -
            market_time.minute
        )
        if minutes_to_close < self.config.close_before_minutes:
            return False, f"Too close to market close ({minutes_to_close} min remaining)"

        return True, "Trading conditions OK"

    def record_trade(self, pnl_pct: float) -> None:
        """Record a completed trade."""
        self._trade_count_today += 1
        self._daily_pnl += pnl_pct

    def _check_daily_reset(self, timestamp: datetime) -> None:
        """Reset daily counters if new day."""
        current_date = timestamp.date()
        if self._last_reset_date != current_date:
            self._trade_count_today = 0
            self._daily_pnl = 0.0
            self._last_reset_date = current_date

    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss: float,
    ) -> int:
        """
        Calculate position size based on risk.

        Uses fixed fractional position sizing based on stop loss.

        Args:
            portfolio_value: Total portfolio value
            entry_price: Entry price
            stop_loss: Stop loss price

        Returns:
            Number of shares
        """
        # Risk per trade (1% of portfolio by default)
        risk_amount = portfolio_value * (self.config.max_loss_per_trade_pct / 100)

        # Risk per share
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0

        # Shares based on risk
        shares_by_risk = int(risk_amount / risk_per_share)

        # Shares based on max position size
        max_position = portfolio_value * (self.config.max_position_pct / 100)
        shares_by_size = int(max_position / entry_price)

        return min(shares_by_risk, shares_by_size)

    def create_signal(
        self,
        symbol: str,
        direction: Direction,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        strength: float,
        confidence: float,
        reason: str = "",
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> IntradaySignal:
        """
        Helper to create an intraday signal.

        Args:
            symbol: Symbol
            direction: Long or short
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            strength: Signal strength (-1 to 1)
            confidence: Confidence (0 to 1)
            reason: Reason for signal
            timestamp: Signal timestamp
            **kwargs: Additional metadata

        Returns:
            IntradaySignal object
        """
        timestamp = timestamp or datetime.now()

        # Calculate risk/reward
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        return IntradaySignal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            timestamp=timestamp,
            strategy_name=self.name,
            session_phase=get_session_phase(timestamp),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=rr_ratio,
            position_size_pct=self.config.max_position_pct,
            reason=reason,
            metadata=kwargs,
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get strategy statistics."""
        return {
            "name": self.name,
            "trade_count_today": self._trade_count_today,
            "daily_pnl_pct": self._daily_pnl,
            "max_trades_per_day": self.config.max_trades_per_day,
            "max_daily_loss_pct": self.config.max_daily_loss_pct,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
