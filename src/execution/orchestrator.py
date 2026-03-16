"""Trading orchestrator - Single entry point for daily trading operations.

Coordinates all trading components:
- Data refresh
- Signal generation
- Order execution
- Position monitoring
- Performance attribution
- Daily reporting

Supports three modes:
- research: Backtesting and strategy development
- paper: Paper trading with Alpaca
- live: Live trading (requires explicit confirmation)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from src.core.paths import paths

import pandas as pd

from ..core import Portfolio, Position, Symbol
from ..strategies.base import Strategy
from .broker.base import Broker
from .monitoring.dashboard import PortfolioMonitor, PortfolioSnapshot
from .order_manager import OrderManager, OrderManagerConfig
from .pipeline.daily_signals import DailySignalPipeline, PipelineConfig, PipelineResult
from .pipeline.order_executor import ExecutionResult, ExecutorConfig, OrderExecutor

logger = logging.getLogger(__name__)


class TradingMode(str, Enum):
    """Trading operation mode."""

    RESEARCH = "research"  # Backtesting only, no execution
    PAPER = "paper"  # Paper trading
    LIVE = "live"  # Live trading


class OrchestratorState(str, Enum):
    """Current state of the orchestrator."""

    IDLE = "idle"
    REFRESHING_DATA = "refreshing_data"
    GENERATING_SIGNALS = "generating_signals"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_ORDERS = "executing_orders"
    MONITORING = "monitoring"
    GENERATING_REPORT = "generating_report"
    ERROR = "error"


@dataclass
class ScheduleConfig:
    """Configuration for scheduled operations (all times in ET)."""

    data_refresh_time: time = time(6, 30)  # 6:30 AM ET
    signal_generation_time: time = time(7, 0)  # 7:00 AM ET
    market_open_time: time = time(9, 30)  # 9:30 AM ET
    execution_time: time = time(9, 35)  # 9:35 AM ET (5 min after open)
    eod_snapshot_time: time = time(16, 0)  # 4:00 PM ET
    attribution_time: time = time(16, 30)  # 4:30 PM ET
    daily_report_time: time = time(17, 0)  # 5:00 PM ET

    def get_schedule(self) -> list[tuple[time, str]]:
        """Get ordered schedule of operations."""
        return sorted([
            (self.data_refresh_time, "refresh_data"),
            (self.signal_generation_time, "generate_signals"),
            (self.execution_time, "execute_orders"),
            (self.eod_snapshot_time, "eod_snapshot"),
            (self.attribution_time, "run_attribution"),
            (self.daily_report_time, "generate_report"),
        ])


@dataclass
class OrchestratorConfig:
    """Configuration for trading orchestrator."""

    mode: TradingMode = TradingMode.PAPER
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    # Strategy settings
    symbols: list[str] = field(default_factory=list)
    max_positions: int = 10
    max_position_pct: float = 0.25  # 25% for budget accounts

    # Execution settings
    require_approval: bool = False  # Fully autonomous — no human approval
    auto_approve_paper: bool = True  # Auto-approve in paper mode
    max_daily_trades: int = 10

    # Risk settings
    max_drawdown_pct: float = 0.15
    daily_loss_limit_pct: float = 0.05
    emergency_stop_enabled: bool = True

    # Reporting
    results_dir: Path = field(default_factory=lambda: paths.base)
    save_signals: bool = True
    save_trades: bool = True

    # Timing
    operation_timeout_seconds: int = 300  # 5 min timeout per operation


@dataclass
class DailyReport:
    """Daily trading report."""

    date: datetime
    mode: TradingMode
    starting_value: float
    ending_value: float
    daily_pnl: float
    daily_pnl_pct: float
    signals_generated: int
    trades_executed: int
    trades_approved: int
    trades_rejected: int
    positions: list[dict[str, Any]]
    alerts_triggered: int
    errors: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "mode": self.mode.value,
            "starting_value": self.starting_value,
            "ending_value": self.ending_value,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct,
            "signals_generated": self.signals_generated,
            "trades_executed": self.trades_executed,
            "trades_approved": self.trades_approved,
            "trades_rejected": self.trades_rejected,
            "positions": self.positions,
            "alerts_triggered": self.alerts_triggered,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        """Generate text summary."""
        pnl_sign = "+" if self.daily_pnl >= 0 else ""
        lines = [
            "=" * 60,
            f"DAILY TRADING REPORT - {self.date.strftime('%Y-%m-%d')}",
            f"Mode: {self.mode.value.upper()}",
            "=" * 60,
            "",
            "PERFORMANCE",
            f"  Starting Value: ${self.starting_value:,.2f}",
            f"  Ending Value:   ${self.ending_value:,.2f}",
            f"  Daily P&L:      {pnl_sign}${self.daily_pnl:,.2f} ({pnl_sign}{self.daily_pnl_pct:.2%})",
            "",
            "ACTIVITY",
            f"  Signals Generated: {self.signals_generated}",
            f"  Trades Approved:   {self.trades_approved}",
            f"  Trades Executed:   {self.trades_executed}",
            f"  Trades Rejected:   {self.trades_rejected}",
            f"  Alerts Triggered:  {self.alerts_triggered}",
            "",
            f"POSITIONS ({len(self.positions)})",
        ]

        for pos in self.positions:
            pnl = pos.get("unrealized_pnl", 0)
            pnl_sign = "+" if pnl >= 0 else ""
            lines.append(
                f"  {pos['symbol']:6s} {pos['quantity']:8.2f} @ ${pos['current_price']:.2f} "
                f"({pnl_sign}${pnl:.2f})"
            )

        if self.errors:
            lines.extend(["", "ERRORS"])
            for error in self.errors:
                lines.append(f"  - {error}")

        lines.append("=" * 60)
        return "\n".join(lines)


class TradingOrchestrator:
    """
    Master orchestrator for daily trading operations.

    Coordinates all trading components in a unified workflow:

    Daily Schedule (ET):
    - 06:30 - Refresh market data
    - 07:00 - Generate signals from strategies
    - 09:30 - Market opens
    - 09:35 - Execute approved orders
    - 16:00 - End-of-day snapshot
    - 16:30 - Run performance attribution
    - 17:00 - Generate daily report

    Supports three modes:
    - research: Backtesting and analysis only
    - paper: Paper trading via Alpaca
    - live: Live trading (requires explicit enable)
    """

    def __init__(
        self,
        broker: Broker,
        strategies: list[Strategy],
        config: OrchestratorConfig | None = None,
        on_signal: Callable[[PipelineResult], None] | None = None,
        on_trade: Callable[[ExecutionResult], None] | None = None,
        on_alert: Callable[[Any], None] | None = None,
    ):
        """
        Initialize trading orchestrator.

        Args:
            broker: Broker for order execution
            strategies: List of trading strategies
            config: Orchestrator configuration
            on_signal: Callback when signals are generated
            on_trade: Callback when trades are executed
            on_alert: Callback when alerts are triggered
        """
        self.broker = broker
        self.strategies = strategies
        self.config = config or OrchestratorConfig()

        # Callbacks
        self.on_signal = on_signal
        self.on_trade = on_trade
        self.on_alert = on_alert

        # Initialize components
        self._init_components()

        # State
        self.state = OrchestratorState.IDLE
        self.portfolio: Portfolio | None = None
        self.today_signals: PipelineResult | None = None
        self.today_executions: list[ExecutionResult] = []
        self.today_errors: list[str] = []
        self.day_start_value: float = 0.0

        # Ensure results directory exists
        self.config.results_dir.mkdir(parents=True, exist_ok=True)

    def _init_components(self) -> None:
        """Initialize sub-components."""
        # Signal pipeline
        pipeline_config = PipelineConfig(
            symbols=self.config.symbols,
            max_position_pct=self.config.max_position_pct,
            max_positions=self.config.max_positions,
            pdt_enabled=True,
            min_hold_days=2,
        )
        self.signal_pipeline = DailySignalPipeline(
            strategies=self.strategies,
            config=pipeline_config,
        )

        # Order executor
        executor_config = ExecutorConfig(
            max_retries=3,
            use_limit_orders=False,  # Market orders for simplicity
        )
        self.order_executor = OrderExecutor(self.broker, executor_config)

        # Order manager with approval
        manager_config = OrderManagerConfig(
            require_approval=self.config.require_approval,
            auto_approve_threshold=0.0 if not self.config.auto_approve_paper else 1.0,
        )
        self.order_manager = OrderManager(self.broker, manager_config)

        # Portfolio monitor
        self.monitor = PortfolioMonitor(
            initial_capital=1000.0,  # Will be updated on connect
            snapshot_interval_seconds=60,
        )

    async def connect(self) -> bool:
        """Connect to broker and initialize portfolio."""
        try:
            connected = await self.broker.connect()
            if not connected:
                logger.error("Failed to connect to broker")
                return False

            # Get account info
            account = await self.broker.get_account()
            self.monitor.initial_capital = float(account.portfolio_value)
            self.day_start_value = float(account.portfolio_value)

            # Get current positions
            positions = await self.broker.get_positions()
            self.portfolio = Portfolio(
                cash=account.cash,
                positions=positions,
            )

            logger.info(
                f"Connected to broker. Account value: ${account.portfolio_value:,.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.state = OrchestratorState.ERROR
            return False

    async def disconnect(self) -> None:
        """Disconnect from broker."""
        await self.broker.disconnect()
        await self.monitor.stop()
        logger.info("Disconnected from broker")

    async def run_daily_cycle(self) -> DailyReport:
        """
        Run a complete daily trading cycle.

        This is the main entry point for daily operations.

        Returns:
            DailyReport summarizing the day's activity
        """
        logger.info(f"Starting daily cycle in {self.config.mode.value} mode")
        self.today_errors = []
        self.today_executions = []

        try:
            # Step 1: Refresh data
            await self._run_step("refresh_data", self._refresh_data)

            # Step 2: Generate signals
            await self._run_step("generate_signals", self._generate_signals)

            # Step 3: Execute orders (if not research mode)
            if self.config.mode != TradingMode.RESEARCH:
                await self._run_step("execute_orders", self._execute_orders)

            # Step 4: Start monitoring
            if self.config.mode != TradingMode.RESEARCH:
                await self.monitor.start(self.portfolio)

            # Step 5: EOD snapshot
            await self._run_step("eod_snapshot", self._eod_snapshot)

            # Step 6: Generate report
            report = await self._generate_report()

            return report

        except Exception as e:
            logger.error(f"Daily cycle failed: {e}")
            self.today_errors.append(str(e))
            self.state = OrchestratorState.ERROR
            return await self._generate_report()

        finally:
            await self.monitor.stop()
            self.state = OrchestratorState.IDLE

    async def _run_step(
        self,
        step_name: str,
        step_fn: Callable,
    ) -> Any:
        """Run a step with timeout and error handling."""
        logger.info(f"Running step: {step_name}")

        try:
            result = await asyncio.wait_for(
                step_fn(),
                timeout=self.config.operation_timeout_seconds,
            )
            return result

        except asyncio.TimeoutError:
            error = f"Step {step_name} timed out"
            logger.error(error)
            self.today_errors.append(error)

        except Exception as e:
            error = f"Step {step_name} failed: {e}"
            logger.error(error)
            self.today_errors.append(error)

    async def _refresh_data(self) -> None:
        """Refresh market data."""
        self.state = OrchestratorState.REFRESHING_DATA

        # Update portfolio from broker
        if self.config.mode != TradingMode.RESEARCH:
            account = await self.broker.get_account()
            positions = await self.broker.get_positions()
            self.portfolio = Portfolio(
                cash=account.cash,
                positions=positions,
            )

        logger.info(f"Data refreshed. Portfolio value: ${self.portfolio.total_value:,.2f}")

    async def _generate_signals(self) -> PipelineResult:
        """Generate trading signals."""
        self.state = OrchestratorState.GENERATING_SIGNALS

        result = await self.signal_pipeline.run(
            portfolio=self.portfolio,
            symbols=self.config.symbols,
        )

        self.today_signals = result

        if self.on_signal:
            self.on_signal(result)

        # Save signals if configured
        if self.config.save_signals:
            await self._save_signals(result)

        logger.info(
            f"Generated {len(result.signals)} signals, "
            f"{len(result.proposals)} proposals"
        )

        return result

    async def _execute_orders(self) -> list[ExecutionResult]:
        """Execute approved orders."""
        self.state = OrchestratorState.EXECUTING_ORDERS

        if not self.today_signals or not self.today_signals.proposals:
            logger.info("No proposals to execute")
            return []

        proposals = self.today_signals.proposals

        # In paper mode with auto-approve, execute directly
        if self.config.mode == TradingMode.PAPER and self.config.auto_approve_paper:
            results = await self.order_executor.execute_proposals(proposals)

        # Otherwise, queue for approval
        else:
            self.state = OrchestratorState.AWAITING_APPROVAL
            # Queue proposals and wait for approval
            for proposal in proposals:
                await self.order_manager.queue_proposal(proposal)

            # In live mode, require explicit approval
            if self.config.mode == TradingMode.LIVE:
                logger.warning("Live mode: Proposals queued for manual approval")
                return []

            # Get approved proposals
            approved = await self.order_manager.get_approved_proposals()
            results = await self.order_executor.execute_proposals(approved)

        self.today_executions = results

        # Track trades for PDT
        for result in results:
            if result.is_success:
                is_entry = result.proposal.order.side.value == "buy"
                self.signal_pipeline.record_trade(
                    result.proposal.order.symbol,
                    is_entry=is_entry,
                )

                if self.on_trade:
                    self.on_trade(result)

        # Save trades if configured
        if self.config.save_trades:
            await self._save_trades(results)

        logger.info(
            f"Executed {len([r for r in results if r.is_success])} trades, "
            f"{len([r for r in results if not r.is_success])} failed"
        )

        return results

    async def _eod_snapshot(self) -> PortfolioSnapshot:
        """Take end-of-day snapshot."""
        self.state = OrchestratorState.MONITORING

        # Refresh portfolio
        if self.config.mode != TradingMode.RESEARCH:
            account = await self.broker.get_account()
            positions = await self.broker.get_positions()
            self.portfolio = Portfolio(
                cash=account.cash,
                positions=positions,
            )

        snapshot = self.monitor.take_snapshot(self.portfolio)

        # Check alerts
        await self.monitor.check_alerts(snapshot)

        logger.info(
            f"EOD snapshot: ${snapshot.total_value:,.2f} "
            f"(P&L: ${snapshot.daily_pnl:+,.2f})"
        )

        return snapshot

    async def _generate_report(self) -> DailyReport:
        """Generate daily report."""
        self.state = OrchestratorState.GENERATING_REPORT

        snapshot = self.monitor.get_latest_snapshot()

        # Get position details
        positions = []
        if snapshot:
            positions = [
                {
                    "symbol": sym,
                    **pos,
                }
                for sym, pos in snapshot.positions.items()
            ]

        report = DailyReport(
            date=datetime.now(),
            mode=self.config.mode,
            starting_value=self.day_start_value,
            ending_value=snapshot.total_value if snapshot else self.day_start_value,
            daily_pnl=snapshot.daily_pnl if snapshot else 0.0,
            daily_pnl_pct=snapshot.daily_pnl_pct if snapshot else 0.0,
            signals_generated=len(self.today_signals.signals) if self.today_signals else 0,
            trades_executed=len([r for r in self.today_executions if r.is_success]),
            trades_approved=len(self.today_signals.proposals) if self.today_signals else 0,
            trades_rejected=len(self.today_signals.rejected) if self.today_signals else 0,
            positions=positions,
            alerts_triggered=len(self.monitor.alerts),
            errors=self.today_errors,
            metadata={
                "pdt_status": self.signal_pipeline.get_pdt_status(),
                "execution_stats": self.order_executor.get_stats(),
            },
        )

        # Save report
        await self._save_report(report)

        return report

    async def _save_signals(self, result: PipelineResult) -> None:
        """Save signals to file."""
        filepath = (
            self.config.results_dir
            / "signals"
            / f"signals_{datetime.now().strftime('%Y%m%d')}.json"
        )
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

    async def _save_trades(self, results: list[ExecutionResult]) -> None:
        """Save trades to file."""
        filepath = (
            self.config.results_dir
            / "trades"
            / f"trades_{datetime.now().strftime('%Y%m%d')}.json"
        )
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2, default=str)

    async def _save_report(self, report: DailyReport) -> None:
        """Save daily report to file."""
        filepath = (
            self.config.results_dir
            / "reports"
            / f"report_{datetime.now().strftime('%Y%m%d')}.json"
        )
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        # Also save text summary
        text_filepath = filepath.with_suffix(".txt")
        with open(text_filepath, "w") as f:
            f.write(report.summary())

        logger.info(f"Report saved to {filepath}")

    async def run_scheduled(self) -> None:
        """
        Run orchestrator on schedule.

        This runs continuously, executing operations at scheduled times.
        """
        logger.info("Starting scheduled orchestrator")

        while True:
            now = datetime.now()
            schedule = self.config.schedule.get_schedule()

            for scheduled_time, operation in schedule:
                # Check if we should run this operation
                scheduled_dt = datetime.combine(now.date(), scheduled_time)

                if now >= scheduled_dt and now < scheduled_dt + timedelta(minutes=5):
                    logger.info(f"Running scheduled operation: {operation}")

                    if operation == "refresh_data":
                        await self._refresh_data()
                    elif operation == "generate_signals":
                        await self._generate_signals()
                    elif operation == "execute_orders":
                        await self._execute_orders()
                    elif operation == "eod_snapshot":
                        await self._eod_snapshot()
                    elif operation == "generate_report":
                        await self._generate_report()

            # Sleep until next minute
            await asyncio.sleep(60)

    def emergency_stop(self) -> None:
        """Emergency stop - cancel all pending orders."""
        logger.warning("EMERGENCY STOP TRIGGERED")
        self.state = OrchestratorState.ERROR

        # Cancel pending orders
        asyncio.create_task(self.order_executor.cancel_all_pending())

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "state": self.state.value,
            "mode": self.config.mode.value,
            "portfolio_value": float(self.portfolio.total_value) if self.portfolio else 0,
            "today_signals": len(self.today_signals.signals) if self.today_signals else 0,
            "today_trades": len(self.today_executions),
            "today_errors": len(self.today_errors),
            "pdt_status": self.signal_pipeline.get_pdt_status(),
        }


async def run_paper_trading(
    broker: Broker,
    strategies: list[Strategy],
    symbols: list[str],
    days: int = 1,
) -> list[DailyReport]:
    """
    Convenience function to run paper trading.

    Args:
        broker: Alpaca paper broker
        strategies: Trading strategies
        symbols: Symbols to trade
        days: Number of days to run

    Returns:
        List of daily reports
    """
    config = OrchestratorConfig(
        mode=TradingMode.PAPER,
        symbols=symbols,
        auto_approve_paper=True,
    )

    orchestrator = TradingOrchestrator(broker, strategies, config)

    if not await orchestrator.connect():
        raise RuntimeError("Failed to connect to broker")

    reports = []
    try:
        for _ in range(days):
            report = await orchestrator.run_daily_cycle()
            reports.append(report)
            print(report.summary())

    finally:
        await orchestrator.disconnect()

    return reports
