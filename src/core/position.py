"""Position and Portfolio management."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pandas as pd

from .types import Direction, OrderSide, Symbol


@dataclass
class Position:
    """
    Represents an open position in an asset.

    Attributes:
        symbol: Asset symbol
        quantity: Number of units held (negative for short)
        entry_price: Average entry price
        current_price: Current market price
        entry_time: When position was opened
        position_id: Unique identifier
    """

    symbol: Symbol
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    entry_time: datetime
    position_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> Direction:
        """Get position direction."""
        if self.quantity > 0:
            return Direction.LONG
        elif self.quantity < 0:
            return Direction.SHORT
        return Direction.FLAT

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0

    @property
    def market_value(self) -> Decimal:
        """Current market value of position."""
        return abs(self.quantity) * self.current_price

    @property
    def cost_basis(self) -> Decimal:
        """Total cost basis of position."""
        return abs(self.quantity) * self.entry_price

    @property
    def unrealized_pnl(self) -> Decimal:
        """Unrealized profit/loss."""
        if self.is_long:
            return self.quantity * (self.current_price - self.entry_price)
        elif self.is_short:
            return abs(self.quantity) * (self.entry_price - self.current_price)
        return Decimal(0)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return float(self.unrealized_pnl / self.cost_basis)

    def update_price(self, price: Decimal) -> None:
        """Update current market price."""
        self.current_price = price

    def add(self, quantity: Decimal, price: Decimal) -> None:
        """
        Add to position (scaling in).

        Updates average entry price using weighted average.
        """
        if quantity == 0:
            return

        total_cost = self.cost_basis + abs(quantity) * price
        new_quantity = self.quantity + quantity

        if new_quantity != 0:
            self.entry_price = total_cost / abs(new_quantity)
        self.quantity = new_quantity

    def to_dict(self) -> dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "quantity": float(self.quantity),
            "entry_price": float(self.entry_price),
            "current_price": float(self.current_price),
            "entry_time": self.entry_time.isoformat(),
            "market_value": float(self.market_value),
            "unrealized_pnl": float(self.unrealized_pnl),
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "direction": self.direction.value,
        }


@dataclass
class Portfolio:
    """
    Portfolio of positions with cash management.

    Attributes:
        cash: Available cash balance
        positions: Dictionary of open positions by symbol
        initial_capital: Starting capital
    """

    initial_capital: Decimal
    cash: Decimal = field(default=Decimal(0))
    positions: dict[Symbol, Position] = field(default_factory=dict)
    realized_pnl: Decimal = field(default=Decimal(0))
    trade_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cash == 0:
            self.cash = self.initial_capital

    @property
    def market_value(self) -> Decimal:
        """Total market value of all positions."""
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_value(self) -> Decimal:
        """Total portfolio value (cash + positions)."""
        return self.cash + self.market_value

    @property
    def unrealized_pnl(self) -> Decimal:
        """Total unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> Decimal:
        """Total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def total_return(self) -> float:
        """Total return as percentage."""
        if self.initial_capital == 0:
            return 0.0
        return float((self.total_value - self.initial_capital) / self.initial_capital)

    @property
    def cash_weight(self) -> float:
        """Cash as percentage of total portfolio."""
        if self.total_value == 0:
            return 1.0
        return float(self.cash / self.total_value)

    def get_position(self, symbol: Symbol) -> Position | None:
        """Get position for a symbol."""
        return self.positions.get(symbol)

    def position_weight(self, symbol: Symbol) -> float:
        """Get position weight as percentage of portfolio."""
        if self.total_value == 0:
            return 0.0
        pos = self.positions.get(symbol)
        if pos is None:
            return 0.0
        return float(pos.market_value / self.total_value)

    def open_position(
        self,
        symbol: Symbol,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
    ) -> None:
        """Open or add to a position."""
        cost = abs(quantity) * price

        if symbol in self.positions:
            # Add to existing position
            self.positions[symbol].add(quantity, price)
        else:
            # Open new position
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                current_price=price,
                entry_time=timestamp,
            )

        # Update cash
        if quantity > 0:  # Buying
            self.cash -= cost
        else:  # Short selling
            self.cash += cost

        # Record trade
        self.trade_history.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "side": OrderSide.BUY.value if quantity > 0 else OrderSide.SELL.value,
            "quantity": float(abs(quantity)),
            "price": float(price),
            "cost": float(cost),
        })

    def close_position(
        self,
        symbol: Symbol,
        price: Decimal,
        timestamp: datetime,
        quantity: Decimal | None = None,
    ) -> Decimal:
        """
        Close (or partially close) a position.

        Returns the realized P&L.
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return Decimal(0)

        # Determine quantity to close
        close_qty = quantity if quantity is not None else abs(pos.quantity)
        close_qty = min(close_qty, abs(pos.quantity))

        # Calculate P&L
        if pos.is_long:
            pnl = close_qty * (price - pos.entry_price)
            self.cash += close_qty * price
        else:
            pnl = close_qty * (pos.entry_price - price)
            self.cash -= close_qty * price

        self.realized_pnl += pnl

        # Update or remove position
        remaining = abs(pos.quantity) - close_qty
        if remaining <= 0:
            del self.positions[symbol]
        else:
            if pos.is_long:
                pos.quantity = Decimal(remaining)
            else:
                pos.quantity = Decimal(-remaining)

        # Record trade
        self.trade_history.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "side": OrderSide.SELL.value if pos.is_long else OrderSide.BUY.value,
            "quantity": float(close_qty),
            "price": float(price),
            "pnl": float(pnl),
        })

        return pnl

    def update_prices(self, prices: dict[Symbol, Decimal]) -> None:
        """Update current prices for all positions."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert positions to DataFrame."""
        if not self.positions:
            return pd.DataFrame()

        data = [pos.to_dict() for pos in self.positions.values()]
        return pd.DataFrame(data)

    def summary(self) -> dict[str, Any]:
        """Get portfolio summary."""
        return {
            "total_value": float(self.total_value),
            "cash": float(self.cash),
            "market_value": float(self.market_value),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_pnl": float(self.total_pnl),
            "total_return": self.total_return,
            "num_positions": len(self.positions),
            "cash_weight": self.cash_weight,
        }
