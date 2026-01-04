"""Daily signal generation pipeline.

Scheduled daily signal generation with:
- Data refresh from yfinance
- Feature computation
- Multi-strategy signal generation
- Risk limit application
- PDT rule compliance
- TradeProposal output
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf

from ...core import (
    Direction,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
    Signal,
    Symbol,
    TradeProposal,
)
from ...risk.limits import LimitCheckResult, RiskLimit
from ...risk.position_sizing import PositionSizer
from ...strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class SignalSummary:
    """Summary of a generated signal."""

    symbol: str
    direction: Direction
    strength: float
    confidence: float
    strategy: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PipelineResult:
    """Result of running the daily signal pipeline."""

    timestamp: datetime
    signals: list[SignalSummary]
    proposals: list[TradeProposal]
    rejected: list[tuple[SignalSummary, str]]  # Signal and rejection reason
    data_errors: list[str]
    risk_violations: list[LimitCheckResult]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def num_buy_signals(self) -> int:
        return sum(1 for s in self.signals if s.direction == Direction.LONG)

    @property
    def num_sell_signals(self) -> int:
        return sum(1 for s in self.signals if s.direction == Direction.SHORT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "num_signals": len(self.signals),
            "num_proposals": len(self.proposals),
            "num_rejected": len(self.rejected),
            "num_buy": self.num_buy_signals,
            "num_sell": self.num_sell_signals,
            "signals": [s.to_dict() for s in self.signals],
            "proposals": [p.to_dict() for p in self.proposals],
            "data_errors": self.data_errors,
        }


@dataclass
class PipelineConfig:
    """Configuration for daily signal pipeline."""

    # Universe
    symbols: list[str] = field(default_factory=list)

    # Data settings
    lookback_days: int = 60
    refresh_timeout_seconds: int = 30

    # Signal generation
    min_signal_strength: float = 0.3
    min_signal_confidence: float = 0.5

    # PDT compliance
    pdt_enabled: bool = True
    min_hold_days: int = 2  # Minimum hold period for PDT compliance
    max_day_trades: int = 3  # Max day trades in 5 rolling days
    account_value_threshold: float = 25000.0  # Above this, PDT doesn't apply

    # Position sizing
    max_position_pct: float = 0.25  # 25% max for budget accounts
    max_positions: int = 10
    min_trade_value: float = 20.0  # Minimum trade value

    # Risk limits
    max_drawdown_pct: float = 0.15  # 15% max drawdown
    daily_loss_limit_pct: float = 0.05  # 5% daily loss limit

    # Timing
    signal_delay_minutes: int = 0  # Delay before acting on signals


@dataclass
class PDTTracker:
    """Tracks Pattern Day Trade status."""

    day_trades: list[datetime] = field(default_factory=list)  # Last 5 rolling days
    position_entry_dates: dict[str, datetime] = field(default_factory=dict)
    account_value: float = 0.0

    def add_day_trade(self, timestamp: datetime) -> None:
        """Record a day trade."""
        self.day_trades.append(timestamp)
        # Keep only last 5 rolling days
        cutoff = datetime.now() - timedelta(days=5)
        self.day_trades = [dt for dt in self.day_trades if dt > cutoff]

    def record_entry(self, symbol: str, timestamp: datetime) -> None:
        """Record position entry date."""
        self.position_entry_dates[symbol] = timestamp

    def clear_position(self, symbol: str) -> None:
        """Clear position tracking."""
        if symbol in self.position_entry_dates:
            del self.position_entry_dates[symbol]

    def get_day_trade_count(self) -> int:
        """Get number of day trades in last 5 days."""
        cutoff = datetime.now() - timedelta(days=5)
        return len([dt for dt in self.day_trades if dt > cutoff])

    def is_pdt_restricted(self, max_trades: int = 3) -> bool:
        """Check if PDT restricted."""
        return self.get_day_trade_count() >= max_trades

    def can_close_position(
        self,
        symbol: str,
        min_hold_days: int = 2,
        account_value: float | None = None,
    ) -> bool:
        """Check if position can be closed without triggering day trade."""
        # Check if account is above PDT threshold
        av = account_value or self.account_value
        if av >= 25000:
            return True

        if symbol not in self.position_entry_dates:
            return True

        entry_date = self.position_entry_dates[symbol]
        hold_days = (datetime.now() - entry_date).days

        return hold_days >= min_hold_days

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_trades_count": self.get_day_trade_count(),
            "is_restricted": self.is_pdt_restricted(),
            "positions_tracked": len(self.position_entry_dates),
            "account_value": self.account_value,
        }


class DailySignalPipeline:
    """
    Daily signal generation pipeline.

    Designed for budget traders with PDT compliance:
    - Pre-market signal generation (7:00 AM ET)
    - Swing trading focus (2-10 day holds)
    - Risk limit enforcement
    - TradeProposal output for approval queue

    Schedule:
    1. Refresh data (yfinance last close)
    2. Compute today's features
    3. Generate signals from strategies
    4. Apply risk limits
    5. PDT compliance check
    6. Output TradeProposals
    """

    def __init__(
        self,
        strategies: list[Strategy],
        config: PipelineConfig | None = None,
        position_sizer: PositionSizer | None = None,
        risk_limits: list[RiskLimit] | None = None,
    ):
        """
        Initialize daily signal pipeline.

        Args:
            strategies: List of strategies to generate signals from
            config: Pipeline configuration
            position_sizer: Position sizing algorithm
            risk_limits: Risk limits to apply
        """
        self.strategies = strategies
        self.config = config or PipelineConfig()
        self.position_sizer = position_sizer
        self.risk_limits = risk_limits or []

        self.pdt_tracker = PDTTracker()
        self._data_cache: dict[str, pd.DataFrame] = {}
        self._last_refresh: datetime | None = None

    async def run(
        self,
        portfolio: Portfolio,
        symbols: list[str] | None = None,
        force_refresh: bool = False,
    ) -> PipelineResult:
        """
        Run the daily signal pipeline.

        Args:
            portfolio: Current portfolio state
            symbols: Symbols to process (overrides config)
            force_refresh: Force data refresh

        Returns:
            PipelineResult with signals and proposals
        """
        start_time = datetime.now()
        symbols = symbols or self.config.symbols
        data_errors = []

        # Update PDT tracker
        self.pdt_tracker.account_value = float(portfolio.total_value)

        # Step 1: Refresh data
        logger.info(f"Refreshing data for {len(symbols)} symbols")
        data = await self._refresh_data(symbols, force_refresh)
        for symbol in symbols:
            if symbol not in data:
                data_errors.append(f"No data for {symbol}")

        # Step 2: Generate signals from all strategies
        all_signals = []
        for strategy in self.strategies:
            try:
                strategy_signals = self._generate_strategy_signals(strategy, data)
                all_signals.extend(strategy_signals)
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed: {e}")
                data_errors.append(f"Strategy {strategy.name}: {e}")

        logger.info(f"Generated {len(all_signals)} raw signals")

        # Step 3: Filter signals by strength/confidence
        filtered_signals = self._filter_signals(all_signals)
        logger.info(f"{len(filtered_signals)} signals pass thresholds")

        # Step 4: Apply risk limits and create proposals
        proposals = []
        rejected = []
        risk_violations = []

        for signal in filtered_signals:
            # Check PDT compliance for exits
            if signal.direction == Direction.FLAT:
                if not self.pdt_tracker.can_close_position(
                    signal.symbol,
                    self.config.min_hold_days,
                    float(portfolio.total_value),
                ):
                    rejected.append((signal, "PDT: Position held less than min days"))
                    continue

            # Create trade proposal
            proposal = self._create_proposal(signal, portfolio, data)
            if proposal is None:
                rejected.append((signal, "Could not create valid proposal"))
                continue

            # Check risk limits
            passed_limits = True
            for limit in self.risk_limits:
                result = limit.check(proposal.order, portfolio)
                if not result.passed:
                    passed_limits = False
                    risk_violations.append(result)
                    rejected.append((signal, f"Risk limit: {result.message}"))
                    break

            if passed_limits:
                proposals.append(proposal)

        # Step 5: Check overall PDT status
        if self.config.pdt_enabled:
            if self.pdt_tracker.is_pdt_restricted(self.config.max_day_trades):
                logger.warning("PDT restricted - limiting to swing trades only")

        logger.info(
            f"Pipeline complete: {len(proposals)} proposals, "
            f"{len(rejected)} rejected"
        )

        return PipelineResult(
            timestamp=start_time,
            signals=filtered_signals,
            proposals=proposals,
            rejected=rejected,
            data_errors=data_errors,
            risk_violations=risk_violations,
            metadata={
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
                "num_strategies": len(self.strategies),
                "pdt_status": self.pdt_tracker.to_dict(),
            },
        )

    async def _refresh_data(
        self,
        symbols: list[str],
        force: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Refresh market data for symbols."""
        # Check cache validity
        if not force and self._last_refresh:
            cache_age = (datetime.now() - self._last_refresh).total_seconds()
            if cache_age < 300:  # 5 minute cache
                return self._data_cache

        data = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.config.lookback_days)

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty:
                    # Normalize column names
                    hist.columns = [c.lower() for c in hist.columns]
                    data[symbol] = hist
                else:
                    logger.warning(f"No data returned for {symbol}")

            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")

        self._data_cache = data
        self._last_refresh = datetime.now()

        return data

    def _generate_strategy_signals(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
    ) -> list[SignalSummary]:
        """Generate signals from a single strategy."""
        summaries = []

        try:
            # Filter data to strategy's universe
            strategy_data = {
                sym: df for sym, df in data.items()
                if sym in strategy.universe
            }

            if not strategy_data:
                return summaries

            # Generate signals
            signals = strategy.generate_signals(strategy_data, datetime.now())

            for signal in signals:
                summary = SignalSummary(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    strength=signal.strength,
                    confidence=signal.confidence,
                    strategy=strategy.name,
                    timestamp=datetime.now(),
                    metadata={
                        "signal_type": signal.signal_type.value if signal.signal_type else None,
                    },
                )
                summaries.append(summary)

        except Exception as e:
            logger.error(f"Error generating signals from {strategy.name}: {e}")

        return summaries

    def _filter_signals(self, signals: list[SignalSummary]) -> list[SignalSummary]:
        """Filter signals by strength and confidence thresholds."""
        return [
            s for s in signals
            if abs(s.strength) >= self.config.min_signal_strength
            and s.confidence >= self.config.min_signal_confidence
        ]

    def _create_proposal(
        self,
        signal: SignalSummary,
        portfolio: Portfolio,
        data: dict[str, pd.DataFrame],
    ) -> TradeProposal | None:
        """Create a trade proposal from a signal."""
        try:
            # Get current price
            if signal.symbol not in data or data[signal.symbol].empty:
                return None

            current_price = float(data[signal.symbol]["close"].iloc[-1])

            # Determine order side
            if signal.direction == Direction.LONG:
                side = OrderSide.BUY
            elif signal.direction == Direction.SHORT:
                side = OrderSide.SELL
            else:
                # FLAT means exit position
                position = portfolio.get_position(signal.symbol)
                if position is None:
                    return None
                side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY

            # Calculate position size
            if self.position_sizer:
                quantity = self.position_sizer.calculate(
                    signal=Signal(
                        symbol=signal.symbol,
                        direction=signal.direction,
                        strength=signal.strength,
                        confidence=signal.confidence,
                        timestamp=signal.timestamp,
                    ),
                    portfolio=portfolio,
                    price=current_price,
                )
            else:
                # Simple fixed percentage sizing
                position_value = float(portfolio.total_value) * self.config.max_position_pct
                quantity = Decimal(str(position_value / current_price))

            # Check minimum trade value
            trade_value = float(quantity) * current_price
            if trade_value < self.config.min_trade_value:
                return None

            # Create order
            order = Order(
                symbol=signal.symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
            )

            # Calculate risk metrics
            risk_metrics = {
                "position_pct": trade_value / float(portfolio.total_value),
                "signal_strength": signal.strength,
                "signal_confidence": signal.confidence,
            }

            return TradeProposal(
                order=order,
                strategy=signal.strategy,
                reasoning=f"{signal.direction.value} signal from {signal.strategy} "
                          f"(strength={signal.strength:.2f}, conf={signal.confidence:.2f})",
                confidence=signal.confidence,
                risk_metrics=risk_metrics,
            )

        except Exception as e:
            logger.error(f"Error creating proposal for {signal.symbol}: {e}")
            return None

    def add_strategy(self, strategy: Strategy) -> None:
        """Add a strategy to the pipeline."""
        self.strategies.append(strategy)

    def remove_strategy(self, strategy_name: str) -> bool:
        """Remove a strategy by name."""
        for i, s in enumerate(self.strategies):
            if s.name == strategy_name:
                self.strategies.pop(i)
                return True
        return False

    def get_strategy_names(self) -> list[str]:
        """Get list of active strategy names."""
        return [s.name for s in self.strategies]

    def update_pdt_tracker(
        self,
        account_value: float,
        day_trades: list[datetime] | None = None,
    ) -> None:
        """Update PDT tracker with account info."""
        self.pdt_tracker.account_value = account_value
        if day_trades:
            self.pdt_tracker.day_trades = day_trades

    def record_trade(
        self,
        symbol: str,
        is_entry: bool,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a trade for PDT tracking."""
        timestamp = timestamp or datetime.now()
        if is_entry:
            self.pdt_tracker.record_entry(symbol, timestamp)
        else:
            # Check if this is a day trade
            if symbol in self.pdt_tracker.position_entry_dates:
                entry_date = self.pdt_tracker.position_entry_dates[symbol]
                if (timestamp - entry_date).days == 0:
                    self.pdt_tracker.add_day_trade(timestamp)
            self.pdt_tracker.clear_position(symbol)

    def get_pdt_status(self) -> dict[str, Any]:
        """Get current PDT status."""
        return self.pdt_tracker.to_dict()
