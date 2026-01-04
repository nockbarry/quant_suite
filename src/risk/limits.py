"""Risk limits and constraints for portfolio management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from ..core import Order, OrderSide, Portfolio, Position, Symbol


class LimitViolation(str, Enum):
    """Types of limit violations."""

    POSITION_SIZE = "position_size"
    SECTOR_CONCENTRATION = "sector_concentration"
    DRAWDOWN = "drawdown"
    DAILY_LOSS = "daily_loss"
    TRADE_SIZE = "trade_size"
    CORRELATION = "correlation"
    LEVERAGE = "leverage"
    LIQUIDITY = "liquidity"


@dataclass
class LimitCheckResult:
    """Result of a limit check."""

    passed: bool
    violation: LimitViolation | None = None
    message: str = ""
    current_value: float = 0.0
    limit_value: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class RiskLimit(ABC):
    """Abstract base class for risk limits."""

    name: str = "base_limit"

    @abstractmethod
    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """
        Check if an order violates this limit.

        Args:
            order: Proposed order
            portfolio: Current portfolio state
            **kwargs: Additional context

        Returns:
            LimitCheckResult indicating pass/fail
        """
        ...


class MaxPositionSizeLimit(RiskLimit):
    """
    Maximum position size limit.

    Prevents any single position from exceeding a percentage of portfolio.
    """

    name = "max_position_size"

    def __init__(
        self,
        max_position_pct: float = 0.10,
        max_position_value: float | None = None,
    ):
        """
        Initialize position size limit.

        Args:
            max_position_pct: Maximum position as % of portfolio
            max_position_value: Maximum absolute position value
        """
        self.max_position_pct = max_position_pct
        self.max_position_value = max_position_value

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check position size limit."""
        if price is None:
            price = order.limit_price or Decimal("0")

        # Calculate position after trade
        current_position = portfolio.get_position(order.symbol)
        current_qty = current_position.quantity if current_position else Decimal("0")

        if order.side == OrderSide.BUY:
            new_qty = current_qty + order.quantity
        else:
            new_qty = current_qty - order.quantity

        new_value = abs(new_qty) * price
        portfolio_value = portfolio.total_value

        # Check percentage limit
        if portfolio_value > 0:
            position_pct = float(new_value / portfolio_value)
            if position_pct > self.max_position_pct:
                return LimitCheckResult(
                    passed=False,
                    violation=LimitViolation.POSITION_SIZE,
                    message=f"Position would be {position_pct:.1%}, max is {self.max_position_pct:.1%}",
                    current_value=position_pct,
                    limit_value=self.max_position_pct,
                )

        # Check absolute limit
        if self.max_position_value and float(new_value) > self.max_position_value:
            return LimitCheckResult(
                passed=False,
                violation=LimitViolation.POSITION_SIZE,
                message=f"Position value ${new_value:,.0f} exceeds max ${self.max_position_value:,.0f}",
                current_value=float(new_value),
                limit_value=self.max_position_value,
            )

        return LimitCheckResult(passed=True)


class MaxSectorConcentrationLimit(RiskLimit):
    """
    Maximum sector concentration limit.

    Prevents over-concentration in any single sector.
    """

    name = "max_sector_concentration"

    def __init__(
        self,
        max_sector_pct: float = 0.30,
        sector_mapping: dict[Symbol, str] | None = None,
    ):
        """
        Initialize sector concentration limit.

        Args:
            max_sector_pct: Maximum sector allocation
            sector_mapping: Dictionary mapping symbols to sectors
        """
        self.max_sector_pct = max_sector_pct
        self.sector_mapping = sector_mapping or {}

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check sector concentration limit."""
        if price is None:
            price = order.limit_price or Decimal("0")

        # Get sector for this symbol
        sector = self.sector_mapping.get(order.symbol, "Unknown")

        # Calculate current sector exposure
        sector_value = Decimal("0")
        for symbol, position in portfolio.positions.items():
            pos_sector = self.sector_mapping.get(symbol, "Unknown")
            if pos_sector == sector:
                sector_value += position.market_value

        # Add proposed trade
        if order.side == OrderSide.BUY:
            sector_value += order.quantity * price
        else:
            sector_value -= order.quantity * price

        portfolio_value = portfolio.total_value
        if portfolio_value > 0:
            sector_pct = float(sector_value / portfolio_value)
            if sector_pct > self.max_sector_pct:
                return LimitCheckResult(
                    passed=False,
                    violation=LimitViolation.SECTOR_CONCENTRATION,
                    message=f"Sector '{sector}' would be {sector_pct:.1%}, max is {self.max_sector_pct:.1%}",
                    current_value=sector_pct,
                    limit_value=self.max_sector_pct,
                    metadata={"sector": sector},
                )

        return LimitCheckResult(passed=True)


class MaxDrawdownLimit(RiskLimit):
    """
    Maximum drawdown limit.

    Halts trading when drawdown exceeds threshold.
    """

    name = "max_drawdown"

    def __init__(
        self,
        max_drawdown_pct: float = 0.20,
        halt_on_breach: bool = True,
    ):
        """
        Initialize drawdown limit.

        Args:
            max_drawdown_pct: Maximum allowed drawdown
            halt_on_breach: If True, halt all trading on breach
        """
        self.max_drawdown_pct = max_drawdown_pct
        self.halt_on_breach = halt_on_breach
        self._peak_value: Decimal | None = None

    def update_peak(self, portfolio_value: Decimal) -> None:
        """Update peak portfolio value."""
        if self._peak_value is None or portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check drawdown limit."""
        portfolio_value = portfolio.total_value

        # Update peak
        self.update_peak(portfolio_value)

        if self._peak_value and self._peak_value > 0:
            drawdown = float((self._peak_value - portfolio_value) / self._peak_value)

            if drawdown > self.max_drawdown_pct:
                return LimitCheckResult(
                    passed=False,
                    violation=LimitViolation.DRAWDOWN,
                    message=f"Drawdown is {drawdown:.1%}, max is {self.max_drawdown_pct:.1%}",
                    current_value=drawdown,
                    limit_value=self.max_drawdown_pct,
                    metadata={
                        "peak_value": float(self._peak_value),
                        "current_value": float(portfolio_value),
                        "halt_trading": self.halt_on_breach,
                    },
                )

        return LimitCheckResult(passed=True)


class DailyLossLimit(RiskLimit):
    """
    Daily loss limit.

    Halts trading when daily P&L exceeds loss threshold.
    """

    name = "daily_loss"

    def __init__(
        self,
        max_daily_loss_pct: float = 0.05,
        max_daily_loss_value: float | None = None,
    ):
        """
        Initialize daily loss limit.

        Args:
            max_daily_loss_pct: Maximum daily loss as % of portfolio
            max_daily_loss_value: Maximum absolute daily loss
        """
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_daily_loss_value = max_daily_loss_value
        self._day_start_value: Decimal | None = None
        self._last_reset_date: datetime | None = None

    def reset_daily(self, portfolio_value: Decimal) -> None:
        """Reset daily tracking."""
        self._day_start_value = portfolio_value
        self._last_reset_date = datetime.now()

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check daily loss limit."""
        # Auto-reset on new day
        now = datetime.now()
        if self._last_reset_date is None or now.date() != self._last_reset_date.date():
            self.reset_daily(portfolio.total_value)

        if self._day_start_value is None:
            return LimitCheckResult(passed=True)

        portfolio_value = portfolio.total_value
        daily_pnl = portfolio_value - self._day_start_value
        daily_pnl_pct = float(daily_pnl / self._day_start_value) if self._day_start_value > 0 else 0

        # Check percentage limit
        if daily_pnl_pct < -self.max_daily_loss_pct:
            return LimitCheckResult(
                passed=False,
                violation=LimitViolation.DAILY_LOSS,
                message=f"Daily loss is {daily_pnl_pct:.1%}, max is {self.max_daily_loss_pct:.1%}",
                current_value=abs(daily_pnl_pct),
                limit_value=self.max_daily_loss_pct,
                metadata={"daily_pnl": float(daily_pnl)},
            )

        # Check absolute limit
        if self.max_daily_loss_value and float(-daily_pnl) > self.max_daily_loss_value:
            return LimitCheckResult(
                passed=False,
                violation=LimitViolation.DAILY_LOSS,
                message=f"Daily loss ${-daily_pnl:,.0f} exceeds max ${self.max_daily_loss_value:,.0f}",
                current_value=float(-daily_pnl),
                limit_value=self.max_daily_loss_value,
            )

        return LimitCheckResult(passed=True)


class MaxTradeSizeLimit(RiskLimit):
    """
    Maximum single trade size limit.

    Prevents excessively large individual trades.
    """

    name = "max_trade_size"

    def __init__(
        self,
        max_trade_pct: float = 0.05,
        max_trade_value: float | None = None,
    ):
        """
        Initialize trade size limit.

        Args:
            max_trade_pct: Maximum trade as % of portfolio
            max_trade_value: Maximum absolute trade value
        """
        self.max_trade_pct = max_trade_pct
        self.max_trade_value = max_trade_value

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check trade size limit."""
        if price is None:
            price = order.limit_price or Decimal("0")

        trade_value = order.quantity * price
        portfolio_value = portfolio.total_value

        # Check percentage limit
        if portfolio_value > 0:
            trade_pct = float(trade_value / portfolio_value)
            if trade_pct > self.max_trade_pct:
                return LimitCheckResult(
                    passed=False,
                    violation=LimitViolation.TRADE_SIZE,
                    message=f"Trade is {trade_pct:.1%} of portfolio, max is {self.max_trade_pct:.1%}",
                    current_value=trade_pct,
                    limit_value=self.max_trade_pct,
                )

        # Check absolute limit
        if self.max_trade_value and float(trade_value) > self.max_trade_value:
            return LimitCheckResult(
                passed=False,
                violation=LimitViolation.TRADE_SIZE,
                message=f"Trade value ${trade_value:,.0f} exceeds max ${self.max_trade_value:,.0f}",
                current_value=float(trade_value),
                limit_value=self.max_trade_value,
            )

        return LimitCheckResult(passed=True)


class MaxLeverageLimit(RiskLimit):
    """
    Maximum leverage limit.

    Prevents portfolio from exceeding leverage threshold.
    """

    name = "max_leverage"

    def __init__(self, max_leverage: float = 1.0):
        """
        Initialize leverage limit.

        Args:
            max_leverage: Maximum leverage ratio (1.0 = no leverage)
        """
        self.max_leverage = max_leverage

    def check(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> LimitCheckResult:
        """Check leverage limit."""
        if price is None:
            price = order.limit_price or Decimal("0")

        # Calculate gross exposure after trade
        gross_exposure = sum(
            abs(p.market_value) for p in portfolio.positions.values()
        )

        # Add proposed trade
        gross_exposure += order.quantity * price

        portfolio_value = portfolio.total_value
        if portfolio_value > 0:
            leverage = float(gross_exposure / portfolio_value)
            if leverage > self.max_leverage:
                return LimitCheckResult(
                    passed=False,
                    violation=LimitViolation.LEVERAGE,
                    message=f"Leverage would be {leverage:.2f}x, max is {self.max_leverage:.2f}x",
                    current_value=leverage,
                    limit_value=self.max_leverage,
                )

        return LimitCheckResult(passed=True)


@dataclass
class RiskLimitsConfig:
    """Configuration for risk limits."""

    max_position_pct: float = 0.10
    max_sector_pct: float = 0.30
    max_drawdown_pct: float = 0.20
    max_daily_loss_pct: float = 0.05
    max_trade_pct: float = 0.05
    max_leverage: float = 1.0


class RiskManager:
    """
    Manages multiple risk limits.

    Checks orders against all configured limits.
    """

    def __init__(
        self,
        config: RiskLimitsConfig | None = None,
        sector_mapping: dict[Symbol, str] | None = None,
    ):
        """
        Initialize risk manager.

        Args:
            config: Risk limits configuration
            sector_mapping: Symbol to sector mapping
        """
        self.config = config or RiskLimitsConfig()
        self.sector_mapping = sector_mapping or {}

        # Initialize limits
        self.limits: list[RiskLimit] = [
            MaxPositionSizeLimit(max_position_pct=self.config.max_position_pct),
            MaxSectorConcentrationLimit(
                max_sector_pct=self.config.max_sector_pct,
                sector_mapping=self.sector_mapping,
            ),
            MaxDrawdownLimit(max_drawdown_pct=self.config.max_drawdown_pct),
            DailyLossLimit(max_daily_loss_pct=self.config.max_daily_loss_pct),
            MaxTradeSizeLimit(max_trade_pct=self.config.max_trade_pct),
            MaxLeverageLimit(max_leverage=self.config.max_leverage),
        ]

    def check_order(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> list[LimitCheckResult]:
        """
        Check an order against all limits.

        Args:
            order: Proposed order
            portfolio: Current portfolio
            price: Current price
            **kwargs: Additional context

        Returns:
            List of check results (failed checks only)
        """
        violations = []

        for limit in self.limits:
            result = limit.check(order, portfolio, price=price, **kwargs)
            if not result.passed:
                violations.append(result)

        return violations

    def is_order_allowed(
        self,
        order: Order,
        portfolio: Portfolio,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> tuple[bool, list[LimitCheckResult]]:
        """
        Check if an order is allowed.

        Args:
            order: Proposed order
            portfolio: Current portfolio
            price: Current price

        Returns:
            Tuple of (is_allowed, violations)
        """
        violations = self.check_order(order, portfolio, price, **kwargs)
        return len(violations) == 0, violations

    def add_limit(self, limit: RiskLimit) -> None:
        """Add a custom risk limit."""
        self.limits.append(limit)

    def remove_limit(self, limit_name: str) -> None:
        """Remove a limit by name."""
        self.limits = [l for l in self.limits if l.name != limit_name]
