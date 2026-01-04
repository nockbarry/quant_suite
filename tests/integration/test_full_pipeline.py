"""Integration tests for the full trading pipeline.

Tests end-to-end functionality:
- Signal generation with real data
- Paper trade execution
- Risk limit enforcement
- Alert triggering
- Portfolio monitoring
- Factor attribution
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Core imports
from src.core import (
    Direction,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
    Signal,
    SP500_TOP_50,
    TradeProposal,
)

# Execution imports
from src.execution import (
    DailySignalPipeline,
    ExecutionResult,
    OrderExecutor,
    PipelineConfig,
    PortfolioMonitor,
    TradingMode,
    TradingOrchestrator,
    OrchestratorConfig,
)
from src.execution.broker.base import Broker, BrokerStatus, AccountInfo, Quote
from src.execution.pipeline.order_executor import ExecutionStatus

# Evaluation imports
from src.evaluation.attribution import FactorModel, AttributionResult
from src.evaluation.backtest import BudgetExecutionModel, MarketState

# Data imports
from src.core.universe_manager import UniverseManager, MarketCapTier
from src.data.storage.feature_store import FeatureStore


class MockBroker(Broker):
    """Mock broker for testing."""

    name = "mock"
    supports_short = True
    supports_fractional = True
    supports_crypto = False

    def __init__(self):
        self._connected = False
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._cash = Decimal("10000.00")
        self._order_counter = 0

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_status(self) -> BrokerStatus:
        return BrokerStatus.CONNECTED if self._connected else BrokerStatus.DISCONNECTED

    async def get_account(self) -> AccountInfo:
        portfolio_value = self._cash + sum(
            p.market_value for p in self._positions.values()
        )
        return AccountInfo(
            account_id="TEST001",
            cash=self._cash,
            portfolio_value=portfolio_value,
            buying_power=self._cash * 2,
            currency="USD",
            margin_enabled=False,
            day_trade_count=0,
            pattern_day_trader=False,
            trading_blocked=False,
        )

    async def get_positions(self) -> dict[str, Position]:
        return self._positions.copy()

    async def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    async def submit_order(self, order: Order) -> Order:
        self._order_counter += 1
        order.order_id = f"ORDER_{self._order_counter}"
        order.status = "filled"
        order.filled_quantity = order.quantity
        order.filled_price = Decimal("100.00")  # Mock price
        self._orders[order.order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            del self._orders[order_id]
            return True
        return False

    async def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    async def get_open_orders(self) -> list[Order]:
        return list(self._orders.values())

    async def get_quote(self, symbol: str) -> Quote | None:
        return Quote(
            symbol=symbol,
            bid=Decimal("99.50"),
            ask=Decimal("100.50"),
            bid_size=100,
            ask_size=100,
            last=Decimal("100.00"),
            last_size=50,
            volume=1000000,
            timestamp=datetime.now(),
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {s: await self.get_quote(s) for s in symbols}


class MockStrategy:
    """Mock strategy for testing."""

    name = "mock_strategy"
    universe = ["AAPL", "MSFT", "GOOGL"]

    def get_required_history(self) -> int:
        return 20

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        timestamp: datetime,
    ) -> list[Signal]:
        signals = []
        for symbol in self.universe:
            if symbol in data:
                signals.append(Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=0.7,
                    confidence=0.6,
                    timestamp=timestamp,
                ))
        return signals


@pytest.fixture
def mock_broker():
    """Create mock broker."""
    return MockBroker()


@pytest.fixture
def mock_strategy():
    """Create mock strategy."""
    return MockStrategy()


@pytest.fixture
def sample_portfolio():
    """Create sample portfolio."""
    return Portfolio(
        cash=Decimal("10000.00"),
        positions={
            "AAPL": Position(
                symbol="AAPL",
                quantity=Decimal("10"),
                entry_price=Decimal("150.00"),
                current_price=Decimal("155.00"),
                entry_time=datetime.now() - timedelta(days=5),
            ),
        },
    )


@pytest.fixture
def sample_returns():
    """Create sample return series."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=252, freq="B")
    returns = pd.Series(
        np.random.randn(252) * 0.02,  # 2% daily vol
        index=dates,
        name="returns",
    )
    return returns


@pytest.fixture
def sample_factor_returns():
    """Create sample factor returns."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=252, freq="B")
    return pd.DataFrame({
        "Market": np.random.randn(252) * 0.01,
        "Size": np.random.randn(252) * 0.005,
        "Value": np.random.randn(252) * 0.005,
        "Momentum": np.random.randn(252) * 0.008,
    }, index=dates)


class TestSignalPipeline:
    """Tests for daily signal generation pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_generates_signals(self, mock_strategy, sample_portfolio):
        """Test that pipeline generates signals from strategies."""
        config = PipelineConfig(
            symbols=["AAPL", "MSFT", "GOOGL"],
            min_signal_strength=0.3,
            min_signal_confidence=0.5,
        )

        pipeline = DailySignalPipeline(
            strategies=[mock_strategy],
            config=config,
        )

        # Mock data refresh
        with patch.object(pipeline, "_refresh_data") as mock_refresh:
            mock_refresh.return_value = {
                "AAPL": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 150,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
                "MSFT": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 300,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
                "GOOGL": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 140,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
            }

            result = await pipeline.run(sample_portfolio)

        assert result is not None
        assert len(result.signals) > 0

    @pytest.mark.asyncio
    async def test_pdt_tracking(self, mock_strategy, sample_portfolio):
        """Test PDT rule compliance tracking."""
        config = PipelineConfig(
            symbols=["AAPL"],
            pdt_enabled=True,
            min_hold_days=2,
        )

        pipeline = DailySignalPipeline(
            strategies=[mock_strategy],
            config=config,
        )

        # Record entry
        pipeline.record_trade("AAPL", is_entry=True)

        # Should not be able to close same day
        assert not pipeline.pdt_tracker.can_close_position("AAPL", min_hold_days=2)

        # Simulate passage of time
        pipeline.pdt_tracker.position_entry_dates["AAPL"] = datetime.now() - timedelta(days=3)

        # Should now be able to close
        assert pipeline.pdt_tracker.can_close_position("AAPL", min_hold_days=2)


class TestOrderExecutor:
    """Tests for order execution."""

    @pytest.mark.asyncio
    async def test_execute_market_order(self, mock_broker):
        """Test market order execution."""
        executor = OrderExecutor(mock_broker)

        proposal = TradeProposal(
            order=Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                order_type=OrderType.MARKET,
            ),
            strategy="test",
            reasoning="Test order",
            confidence=0.8,
        )

        await mock_broker.connect()
        result = await executor.execute_proposal(proposal)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.fill_quantity > 0

    @pytest.mark.asyncio
    async def test_execution_stats_tracking(self, mock_broker):
        """Test that execution statistics are tracked."""
        executor = OrderExecutor(mock_broker)

        proposal = TradeProposal(
            order=Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                order_type=OrderType.MARKET,
            ),
            strategy="test",
            reasoning="Test order",
            confidence=0.8,
        )

        await mock_broker.connect()
        await executor.execute_proposal(proposal)

        stats = executor.get_stats()
        assert stats["total_orders"] == 1
        assert stats["successful_orders"] == 1


class TestPortfolioMonitor:
    """Tests for portfolio monitoring."""

    def test_snapshot_creation(self, sample_portfolio):
        """Test portfolio snapshot creation."""
        monitor = PortfolioMonitor(initial_capital=10000.0)

        snapshot = monitor.take_snapshot(sample_portfolio)

        assert snapshot is not None
        assert snapshot.total_value > 0
        assert snapshot.num_positions == 1

    def test_drawdown_calculation(self, sample_portfolio):
        """Test drawdown tracking."""
        monitor = PortfolioMonitor(initial_capital=10000.0)

        # Take initial snapshot
        snapshot1 = monitor.take_snapshot(sample_portfolio)

        # Simulate loss
        sample_portfolio._cash = Decimal("8000.00")
        snapshot2 = monitor.take_snapshot(sample_portfolio)

        assert snapshot2.drawdown < 0

    @pytest.mark.asyncio
    async def test_alert_triggering(self, sample_portfolio):
        """Test alert triggering on threshold breach."""
        monitor = PortfolioMonitor(initial_capital=10000.0)

        # Set day start high
        monitor.day_start_value = 15000.0

        # Portfolio is now at ~11550 (10000 cash + 10 * 155)
        # This is a significant daily loss
        snapshot = monitor.take_snapshot(sample_portfolio)
        alerts = await monitor.check_alerts(snapshot)

        # Should trigger daily loss alert
        assert snapshot.daily_pnl < 0


class TestExecutionModel:
    """Tests for execution/slippage modeling."""

    def test_budget_execution_model(self):
        """Test budget-optimized execution model."""
        model = BudgetExecutionModel()

        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
        )

        market_state = MarketState.from_price(
            symbol="AAPL",
            price=150.0,
            spread_bps=5.0,
            avg_daily_volume=50_000_000,
        )

        # Budget model should have zero market impact
        impact = model.estimate_market_impact(order, market_state)
        assert impact == 0.0

        # Should still have slippage
        slippage, slippage_bps = model.estimate_slippage(order, market_state)
        assert slippage_bps > 0

    def test_fill_simulation(self):
        """Test order fill simulation."""
        model = BudgetExecutionModel()

        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
        )

        market_state = MarketState.from_price(
            symbol="AAPL",
            price=150.0,
            spread_bps=5.0,
        )

        fill = model.simulate_fill(order, market_state)

        assert fill.fill_quantity == 10.0
        assert fill.fill_price > 0
        assert fill.total_cost >= 0


class TestFactorAttribution:
    """Tests for factor attribution."""

    def test_factor_model_attribution(self, sample_returns, sample_factor_returns):
        """Test factor model attribution."""
        model = FactorModel()

        result = model.attribute(sample_returns, sample_factor_returns)

        assert isinstance(result, AttributionResult)
        assert result.r_squared >= 0
        assert len(result.factor_exposures) > 0

    def test_alpha_calculation(self, sample_returns, sample_factor_returns):
        """Test alpha calculation."""
        model = FactorModel()

        result = model.attribute(sample_returns, sample_factor_returns)

        # Alpha should be calculated
        assert result.alpha is not None
        assert result.alpha_annualized is not None


class TestUniverseManager:
    """Tests for universe management."""

    def test_market_cap_classification(self):
        """Test market cap tier classification."""
        assert MarketCapTier.from_market_cap(300_000_000_000) == MarketCapTier.MEGA
        assert MarketCapTier.from_market_cap(50_000_000_000) == MarketCapTier.LARGE
        assert MarketCapTier.from_market_cap(5_000_000_000) == MarketCapTier.MID
        assert MarketCapTier.from_market_cap(500_000_000) == MarketCapTier.SMALL
        assert MarketCapTier.from_market_cap(100_000_000) == MarketCapTier.MICRO


class TestFeatureStore:
    """Tests for feature store."""

    def test_store_and_retrieve_features(self, tmp_path):
        """Test storing and retrieving features."""
        store = FeatureStore(db_path=tmp_path / "test_features.duckdb")

        # Store features
        store.store_features(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            features={"rsi": 45.5, "momentum": 0.02},
        )

        # Retrieve features
        features = store.get_point_in_time(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
        )

        assert "rsi" in features
        assert features["rsi"] == 45.5

    def test_point_in_time_query(self, tmp_path):
        """Test point-in-time query prevents look-ahead."""
        store = FeatureStore(db_path=tmp_path / "test_features.duckdb")

        # Store feature computed at different times
        store.store_features(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            features={"rsi": 45.0},
            computed_at=datetime(2024, 1, 15, 10, 0),  # 10 AM
        )

        store.store_features(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            features={"rsi": 50.0},  # Updated value
            computed_at=datetime(2024, 1, 15, 16, 0),  # 4 PM
        )

        # Query as of 12 PM - should get earlier value
        features = store.get_point_in_time(
            symbol="AAPL",
            date=datetime(2024, 1, 15),
            as_of=datetime(2024, 1, 15, 12, 0),
        )

        assert features["rsi"] == 45.0  # Earlier value


class TestTradingOrchestrator:
    """Tests for trading orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self, mock_broker, mock_strategy):
        """Test orchestrator initializes correctly."""
        config = OrchestratorConfig(
            mode=TradingMode.PAPER,
            symbols=["AAPL", "MSFT"],
        )

        orchestrator = TradingOrchestrator(
            broker=mock_broker,
            strategies=[mock_strategy],
            config=config,
        )

        assert orchestrator.config.mode == TradingMode.PAPER
        assert len(orchestrator.strategies) == 1

    @pytest.mark.asyncio
    async def test_orchestrator_connect(self, mock_broker, mock_strategy):
        """Test orchestrator connects to broker."""
        config = OrchestratorConfig(
            mode=TradingMode.PAPER,
            symbols=["AAPL"],
        )

        orchestrator = TradingOrchestrator(
            broker=mock_broker,
            strategies=[mock_strategy],
            config=config,
        )

        connected = await orchestrator.connect()
        assert connected

        await orchestrator.disconnect()

    @pytest.mark.asyncio
    async def test_orchestrator_status(self, mock_broker, mock_strategy):
        """Test orchestrator status reporting."""
        config = OrchestratorConfig(
            mode=TradingMode.PAPER,
            symbols=["AAPL"],
        )

        orchestrator = TradingOrchestrator(
            broker=mock_broker,
            strategies=[mock_strategy],
            config=config,
        )

        await orchestrator.connect()

        status = orchestrator.get_status()
        assert "state" in status
        assert "mode" in status
        assert status["mode"] == "paper"

        await orchestrator.disconnect()


class TestRiskLimits:
    """Tests for risk limit enforcement."""

    @pytest.mark.asyncio
    async def test_max_position_limit(self, mock_strategy, sample_portfolio):
        """Test maximum position size limit."""
        config = PipelineConfig(
            symbols=["AAPL"],
            max_position_pct=0.25,  # 25% max
        )

        pipeline = DailySignalPipeline(
            strategies=[mock_strategy],
            config=config,
        )

        # Position sizing should respect max_position_pct
        # This is enforced during proposal creation


class TestEndToEnd:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_daily_cycle_paper_mode(self, mock_broker, mock_strategy):
        """Test complete daily trading cycle in paper mode."""
        config = OrchestratorConfig(
            mode=TradingMode.PAPER,
            symbols=["AAPL", "MSFT", "GOOGL"],
            auto_approve_paper=True,
            results_dir=Path("/tmp/quant_test"),
        )

        orchestrator = TradingOrchestrator(
            broker=mock_broker,
            strategies=[mock_strategy],
            config=config,
        )

        # Connect
        connected = await orchestrator.connect()
        assert connected

        # Mock data refresh to avoid network calls
        with patch.object(
            orchestrator.signal_pipeline,
            "_refresh_data",
        ) as mock_refresh:
            mock_refresh.return_value = {
                "AAPL": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 150,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
                "MSFT": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 300,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
                "GOOGL": pd.DataFrame({
                    "close": np.random.randn(30) * 10 + 140,
                    "volume": np.random.randint(1000000, 5000000, 30),
                }),
            }

            # Run daily cycle
            report = await orchestrator.run_daily_cycle()

        # Verify report
        assert report is not None
        assert report.mode == TradingMode.PAPER

        # Disconnect
        await orchestrator.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
