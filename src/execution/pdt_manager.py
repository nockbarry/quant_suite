"""Pattern Day Trader (PDT) Manager for accounts under $25,000.

Tracks day trades and enforces PDT rules to avoid account restrictions.

PDT Rule Summary:
- Day trade = Buy and sell same security same day
- 3 day trades allowed per 5 rolling business days for <$25k accounts
- 4+ day trades triggers PDT designation and restrictions
- Must maintain 2-day minimum hold for swing positions

This manager:
1. Tracks rolling 5-day day trade count
2. Warns before triggering PDT threshold
3. Enforces minimum hold periods
4. Calculates available day trade capacity
5. Suggests swing vs day trade based on capacity
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class TradeType(str, Enum):
    """Type of trade for PDT tracking."""
    DAY_TRADE = "day_trade"  # Same-day round trip
    SWING_ENTRY = "swing_entry"  # Position opened, held overnight
    SWING_EXIT = "swing_exit"  # Position closed after 2+ days
    UNKNOWN = "unknown"


class PDTStatus(str, Enum):
    """PDT status of the account."""
    SAFE = "safe"  # 0-2 day trades, have capacity
    WARNING = "warning"  # 2 day trades, only 1 left
    AT_LIMIT = "at_limit"  # 3 day trades, no capacity
    RESTRICTED = "restricted"  # Would be flagged if another day trade
    PDT_FLAGGED = "pdt_flagged"  # Account has PDT designation


@dataclass
class DayTrade:
    """Record of a single day trade."""
    date: date
    symbol: str
    buy_time: datetime
    sell_time: datetime
    buy_price: float
    sell_price: float
    quantity: int
    pnl: float
    was_intentional: bool = True  # vs forced exit (stop loss same day)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date.isoformat(),
            "symbol": self.symbol,
            "buy_time": self.buy_time.isoformat(),
            "sell_time": self.sell_time.isoformat(),
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "was_intentional": self.was_intentional,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DayTrade":
        """Create from dictionary."""
        return cls(
            date=date.fromisoformat(data["date"]),
            symbol=data["symbol"],
            buy_time=datetime.fromisoformat(data["buy_time"]),
            sell_time=datetime.fromisoformat(data["sell_time"]),
            buy_price=data["buy_price"],
            sell_price=data["sell_price"],
            quantity=data["quantity"],
            pnl=data["pnl"],
            was_intentional=data.get("was_intentional", True),
        )


@dataclass
class OpenPosition:
    """An open position being tracked for minimum hold."""
    symbol: str
    entry_date: date
    entry_time: datetime
    entry_price: float
    quantity: int
    can_sell_date: date  # Earliest date to sell without triggering day trade

    @property
    def hold_days(self) -> int:
        """Days held so far."""
        return (date.today() - self.entry_date).days

    @property
    def can_day_trade(self) -> bool:
        """Check if selling today would be a day trade."""
        return self.entry_date == date.today()

    @property
    def can_swing_exit(self) -> bool:
        """Check if can exit as swing trade (2+ day hold)."""
        return date.today() >= self.can_sell_date

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date.isoformat(),
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "can_sell_date": self.can_sell_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpenPosition":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            entry_date=date.fromisoformat(data["entry_date"]),
            entry_time=datetime.fromisoformat(data["entry_time"]),
            entry_price=data["entry_price"],
            quantity=data["quantity"],
            can_sell_date=date.fromisoformat(data["can_sell_date"]),
        )


def get_business_days_ago(n: int, from_date: date | None = None) -> date:
    """Get the date n business days ago."""
    from_date = from_date or date.today()
    count = 0
    current = from_date

    while count < n:
        current -= timedelta(days=1)
        # Skip weekends (0=Monday, 6=Sunday)
        if current.weekday() < 5:
            count += 1

    return current


def add_business_days(start: date, n: int) -> date:
    """Add n business days to a date."""
    current = start
    count = 0

    while count < n:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1

    return current


class PDTManager:
    """
    Pattern Day Trader compliance manager.

    Tracks day trades and enforces PDT rules for accounts under $25,000.
    """

    PDT_THRESHOLD = 25_000  # Account value threshold
    DAY_TRADE_LIMIT = 3  # Max day trades per rolling period
    ROLLING_PERIOD_DAYS = 5  # Rolling business days
    MIN_SWING_HOLD_DAYS = 2  # Minimum hold to avoid day trade

    def __init__(
        self,
        account_equity: float,
        persist_path: str | None = None,
        is_pdt_flagged: bool = False,
    ):
        """
        Initialize PDT manager.

        Args:
            account_equity: Current account equity
            persist_path: Path to persist state (optional)
            is_pdt_flagged: Whether account is already PDT flagged
        """
        self.account_equity = account_equity
        self.persist_path = Path(persist_path) if persist_path else None
        self.is_pdt_flagged = is_pdt_flagged

        # State
        self._day_trades: list[DayTrade] = []
        self._open_positions: dict[str, OpenPosition] = {}

        # Load persisted state
        if self.persist_path and self.persist_path.exists():
            self._load_state()

    @property
    def is_pdt_restricted(self) -> bool:
        """Check if account is PDT restricted (<$25k)."""
        return self.account_equity < self.PDT_THRESHOLD and not self.is_pdt_flagged

    @property
    def rolling_day_trades(self) -> list[DayTrade]:
        """Get day trades in the rolling 5-day period."""
        cutoff = get_business_days_ago(self.ROLLING_PERIOD_DAYS)
        return [dt for dt in self._day_trades if dt.date >= cutoff]

    @property
    def day_trade_count(self) -> int:
        """Current day trade count in rolling period."""
        return len(self.rolling_day_trades)

    @property
    def day_trades_remaining(self) -> int:
        """How many day trades can still be made."""
        if not self.is_pdt_restricted:
            return 999  # Unlimited for >$25k accounts
        return max(0, self.DAY_TRADE_LIMIT - self.day_trade_count)

    @property
    def status(self) -> PDTStatus:
        """Current PDT status."""
        if self.is_pdt_flagged:
            return PDTStatus.PDT_FLAGGED
        if not self.is_pdt_restricted:
            return PDTStatus.SAFE

        count = self.day_trade_count

        if count == 0:
            return PDTStatus.SAFE
        elif count == 1:
            return PDTStatus.SAFE
        elif count == 2:
            return PDTStatus.WARNING
        elif count == 3:
            return PDTStatus.AT_LIMIT
        else:
            return PDTStatus.RESTRICTED

    @property
    def next_day_trade_available(self) -> date | None:
        """When will the next day trade capacity free up?"""
        if self.day_trades_remaining > 0:
            return date.today()

        if not self.rolling_day_trades:
            return date.today()

        # Find oldest day trade that will expire
        oldest = min(dt.date for dt in self.rolling_day_trades)
        return add_business_days(oldest, self.ROLLING_PERIOD_DAYS)

    def can_day_trade(self, symbol: str | None = None) -> tuple[bool, str]:
        """
        Check if a day trade is allowed.

        Args:
            symbol: Symbol to check (optional)

        Returns:
            Tuple of (allowed, reason)
        """
        if not self.is_pdt_restricted:
            return True, "Account above PDT threshold"

        if self.is_pdt_flagged:
            return False, "Account is PDT flagged"

        if self.day_trade_count >= self.DAY_TRADE_LIMIT:
            next_available = self.next_day_trade_available
            return False, f"Day trade limit reached. Next available: {next_available}"

        if self.day_trade_count == self.DAY_TRADE_LIMIT - 1:
            return True, "WARNING: This would be your last day trade for 5 business days"

        return True, f"{self.day_trades_remaining} day trades remaining"

    def should_swing_trade(self, symbol: str) -> tuple[bool, str]:
        """
        Recommend whether to swing trade vs day trade.

        Args:
            symbol: Symbol to trade

        Returns:
            Tuple of (should_swing, reason)
        """
        can_dt, reason = self.can_day_trade(symbol)

        if not can_dt:
            return True, f"Must swing trade: {reason}"

        if self.day_trades_remaining <= 1:
            return True, "Recommend swing: only 1 day trade remaining, save for emergencies"

        if self.day_trades_remaining == 2:
            return False, "Day trade OK, but consider swing to preserve capacity"

        return False, "Day trade OK, sufficient capacity"

    def record_entry(
        self,
        symbol: str,
        price: float,
        quantity: int,
        entry_time: datetime | None = None,
    ) -> OpenPosition:
        """
        Record a new position entry.

        Args:
            symbol: Symbol
            price: Entry price
            quantity: Number of shares
            entry_time: Entry timestamp

        Returns:
            OpenPosition object
        """
        entry_time = entry_time or datetime.now()
        entry_date = entry_time.date()
        can_sell_date = add_business_days(entry_date, self.MIN_SWING_HOLD_DAYS)

        position = OpenPosition(
            symbol=symbol,
            entry_date=entry_date,
            entry_time=entry_time,
            entry_price=price,
            quantity=quantity,
            can_sell_date=can_sell_date,
        )

        self._open_positions[symbol] = position
        self._save_state()

        logger.info(
            f"Position entry recorded: {symbol} @ ${price:.2f} x {quantity}. "
            f"Can swing exit on {can_sell_date}"
        )

        return position

    def record_exit(
        self,
        symbol: str,
        price: float,
        quantity: int | None = None,
        exit_time: datetime | None = None,
        was_intentional: bool = True,
    ) -> tuple[TradeType, DayTrade | None]:
        """
        Record a position exit and determine if it was a day trade.

        Args:
            symbol: Symbol
            price: Exit price
            quantity: Shares sold (None = full position)
            exit_time: Exit timestamp
            was_intentional: Whether exit was intentional vs forced

        Returns:
            Tuple of (trade_type, day_trade_record if applicable)
        """
        exit_time = exit_time or datetime.now()
        position = self._open_positions.get(symbol)

        if position is None:
            logger.warning(f"No tracked position for {symbol}")
            return TradeType.UNKNOWN, None

        quantity = quantity or position.quantity
        exit_date = exit_time.date()

        # Check if this is a day trade
        if exit_date == position.entry_date:
            # This is a day trade
            pnl = (price - position.entry_price) * quantity

            day_trade = DayTrade(
                date=exit_date,
                symbol=symbol,
                buy_time=position.entry_time,
                sell_time=exit_time,
                buy_price=position.entry_price,
                sell_price=price,
                quantity=quantity,
                pnl=pnl,
                was_intentional=was_intentional,
            )

            self._day_trades.append(day_trade)

            # Remove or reduce position
            if quantity >= position.quantity:
                del self._open_positions[symbol]
            else:
                position.quantity -= quantity

            self._save_state()

            logger.warning(
                f"DAY TRADE recorded: {symbol}. "
                f"Day trade count: {self.day_trade_count}/{self.DAY_TRADE_LIMIT}"
            )

            return TradeType.DAY_TRADE, day_trade

        else:
            # Swing trade exit
            if quantity >= position.quantity:
                del self._open_positions[symbol]
            else:
                position.quantity -= quantity

            self._save_state()

            logger.info(f"Swing exit recorded: {symbol} after {position.hold_days} days")

            return TradeType.SWING_EXIT, None

    def get_position(self, symbol: str) -> OpenPosition | None:
        """Get tracked position for a symbol."""
        return self._open_positions.get(symbol)

    def get_all_positions(self) -> dict[str, OpenPosition]:
        """Get all tracked positions."""
        return self._open_positions.copy()

    def get_positions_can_exit(self) -> list[OpenPosition]:
        """Get positions that can be exited without day trade."""
        return [p for p in self._open_positions.values() if p.can_swing_exit]

    def get_positions_locked(self) -> list[OpenPosition]:
        """Get positions that must be held to avoid day trade."""
        return [p for p in self._open_positions.values() if not p.can_swing_exit]

    def update_equity(self, equity: float) -> None:
        """Update account equity (affects PDT restriction)."""
        was_restricted = self.is_pdt_restricted
        self.account_equity = equity

        if was_restricted and not self.is_pdt_restricted:
            logger.info("Account now above $25k PDT threshold - day trade restrictions lifted")
        elif not was_restricted and self.is_pdt_restricted:
            logger.warning("Account dropped below $25k - PDT restrictions now apply")

    def get_summary(self) -> dict[str, Any]:
        """Get PDT status summary."""
        return {
            "account_equity": self.account_equity,
            "is_pdt_restricted": self.is_pdt_restricted,
            "is_pdt_flagged": self.is_pdt_flagged,
            "status": self.status.value,
            "day_trade_count": self.day_trade_count,
            "day_trade_limit": self.DAY_TRADE_LIMIT,
            "day_trades_remaining": self.day_trades_remaining,
            "next_day_trade_available": self.next_day_trade_available.isoformat() if self.next_day_trade_available else None,
            "open_positions": len(self._open_positions),
            "positions_can_exit": len(self.get_positions_can_exit()),
            "positions_locked": len(self.get_positions_locked()),
            "rolling_day_trades": [dt.to_dict() for dt in self.rolling_day_trades],
        }

    def _save_state(self) -> None:
        """Persist state to file."""
        if not self.persist_path:
            return

        state = {
            "account_equity": self.account_equity,
            "is_pdt_flagged": self.is_pdt_flagged,
            "day_trades": [dt.to_dict() for dt in self._day_trades],
            "open_positions": {
                symbol: pos.to_dict()
                for symbol, pos in self._open_positions.items()
            },
            "updated_at": datetime.now().isoformat(),
        }

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> None:
        """Load state from file."""
        if not self.persist_path or not self.persist_path.exists():
            return

        try:
            with open(self.persist_path, "r") as f:
                state = json.load(f)

            self.account_equity = state.get("account_equity", self.account_equity)
            self.is_pdt_flagged = state.get("is_pdt_flagged", False)

            self._day_trades = [
                DayTrade.from_dict(dt) for dt in state.get("day_trades", [])
            ]

            self._open_positions = {
                symbol: OpenPosition.from_dict(pos)
                for symbol, pos in state.get("open_positions", {}).items()
            }

            # Clean up old day trades
            cutoff = get_business_days_ago(self.ROLLING_PERIOD_DAYS + 5)
            self._day_trades = [dt for dt in self._day_trades if dt.date >= cutoff]

            logger.info(f"Loaded PDT state: {self.day_trade_count} day trades, {len(self._open_positions)} positions")

        except Exception as e:
            logger.error(f"Error loading PDT state: {e}")

    def __repr__(self) -> str:
        return (
            f"PDTManager(equity=${self.account_equity:,.0f}, "
            f"status={self.status.value}, "
            f"day_trades={self.day_trade_count}/{self.DAY_TRADE_LIMIT})"
        )


# Convenience function
def create_pdt_manager(
    account_equity: float,
    persist_dir: str = "/home/nock/quant_results/pdt",
) -> PDTManager:
    """
    Create a PDT manager with persistence.

    Args:
        account_equity: Current account equity
        persist_dir: Directory for persistence

    Returns:
        PDTManager instance
    """
    persist_path = Path(persist_dir) / "pdt_state.json"
    return PDTManager(account_equity=account_equity, persist_path=str(persist_path))
