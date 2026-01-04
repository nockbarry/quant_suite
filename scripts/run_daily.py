#!/usr/bin/env python3
"""
Daily Trading Pipeline Runner

Runs the complete daily signal generation and execution pipeline.
Designed for budget traders ($200-$2,000) with swing trading focus.

Usage:
    # Run signal generation (no execution)
    python scripts/run_daily.py --mode signals

    # Run paper trading
    python scripts/run_daily.py --mode paper

    # Run live trading (requires confirmation)
    python scripts/run_daily.py --mode live --confirm

    # Run with scheduler (APScheduler)
    python scripts/run_daily.py --mode paper --schedule

Schedule (ET):
    06:30 - Data refresh
    07:00 - Signal generation
    09:30 - Execute orders (market open)
    16:00 - End-of-day snapshot
    16:30 - Daily report

Environment Variables:
    ALPACA_API_KEY - Alpaca API key
    ALPACA_SECRET_KEY - Alpaca secret key
    ALPACA_PAPER - "true" for paper trading (default)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

# Rich for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from src.core import Direction, Portfolio, Position, Symbol
from src.core.strategy_config import load_strategy_config, StrategyConfigBundle
from src.execution.pipeline.daily_signals import (
    DailySignalPipeline,
    PipelineConfig,
    PipelineResult,
)
from src.execution.pipeline.order_executor import (
    OrderExecutor,
    ExecutorConfig,
    ExecutionResult,
)
from src.risk.position_sizing import FixedFractionalSizer
from src.data.feature_engineering.feature_registry import FeatureComputer

# Knowledge base for feedback loop
try:
    from workflows.research.knowledge_base import KnowledgeBase
    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

console = Console() if RICH_AVAILABLE else None


# =============================================================================
# FEATURE COMPUTATION
# =============================================================================

def compute_features_for_data(
    data: dict[str, pd.DataFrame],
    feature_names: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Compute required features for all symbols.

    Args:
        data: Dict of symbol -> OHLCV DataFrame
        feature_names: List of feature names to compute

    Returns:
        Dict of symbol -> DataFrame with original data + computed features
    """
    computer = FeatureComputer()
    enriched = {}

    for symbol, df in data.items():
        if df.empty or len(df) < 30:
            enriched[symbol] = df
            continue

        # Start with original data
        result = df.copy()

        # Compute each requested feature
        for feature_name in feature_names:
            try:
                features = computer.compute_feature(feature_name, df)
                # Merge with result
                for col in features.columns:
                    result[col] = features[col]
            except Exception as e:
                logger.debug(f"Could not compute {feature_name} for {symbol}: {e}")

        enriched[symbol] = result

    return enriched


# =============================================================================
# VALIDATED STRATEGIES
# =============================================================================

class BaseStrategy:
    """Base class for strategies with feature computation."""

    name: str = "base"
    universe: list[str] = []
    required_features: list[str] = []

    def compute_features(self, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Compute required features for this strategy."""
        if not self.required_features:
            return data
        return compute_features_for_data(data, self.required_features)


class InsiderTechnicalStrategy(BaseStrategy):
    """
    Insider-Technical Confluence Strategy.

    Validated: Sharpe 1.23 on QQQ (p=0.00)

    Combines accumulation detection with technical indicators.
    """

    name = "insider_technical"
    universe = ["QQQ", "MSFT", "AAPL", "GOOGL", "XLK", "AMAT", "SPY"]
    required_features = ["rsi", "bollinger_bands", "volume_features"]

    def __init__(
        self,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        volume_lookback: int = 60,
    ):
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.volume_lookback = volume_lookback

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        as_of: datetime,
    ) -> list:
        """Generate signals for all symbols in universe."""
        from src.core import Signal, SignalType

        signals = []

        for symbol, df in data.items():
            if len(df) < max(self.volume_lookback, self.bb_period) + 20:
                continue

            try:
                signal = self._generate_signal(symbol, df)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.warning(f"Error generating signal for {symbol}: {e}")

        return signals

    def _generate_signal(self, symbol: str, df: pd.DataFrame) -> Any:
        """Generate signal for a single symbol."""
        from src.core import Signal, SignalType

        close = df["close"]
        volume = df.get("volume", pd.Series(1, index=df.index))

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / (loss + 1e-10)))
        current_rsi = rsi.iloc[-1]

        # Bollinger Bands
        ma = close.rolling(self.bb_period).mean()
        std = close.rolling(self.bb_period).std()
        bb_upper = ma + 2 * std
        bb_lower = ma - 2 * std
        bb_position = (close - ma) / (2 * std + 1e-10)
        current_bb = bb_position.iloc[-1]

        # Accumulation signal (volume/price divergence)
        returns = close.pct_change()
        avg_volume = volume.rolling(20).mean()
        volume_ratio = volume / (avg_volume + 1)
        abs_returns = returns.abs()
        accum_score = (volume_ratio - 1) / (abs_returns * 100 + 1)
        accum_ma = accum_score.rolling(self.volume_lookback).mean()
        current_accum = accum_ma.iloc[-1]

        # Signal logic
        # Long: RSI oversold + price near lower BB + accumulation
        long_rsi = current_rsi < self.rsi_oversold
        long_bb = current_bb < -0.8
        long_accum = current_accum > 0.1

        # Short: RSI overbought + price near upper BB
        short_rsi = current_rsi > self.rsi_overbought
        short_bb = current_bb > 0.8

        # Calculate confluence score
        long_score = (
            (1.0 if long_rsi else 0.0) * 0.4 +
            (1.0 if long_bb else 0.0) * 0.3 +
            (1.0 if long_accum else 0.0) * 0.3
        )

        short_score = (
            (1.0 if short_rsi else 0.0) * 0.5 +
            (1.0 if short_bb else 0.0) * 0.5
        )

        # Generate signal if score is high enough
        if long_score >= 0.5:
            return Signal(
                symbol=symbol,
                direction=Direction.LONG,
                strength=float(long_score),
                confidence=float(min(0.9, long_score + 0.2)),
                timestamp=datetime.now(),
                signal_type=SignalType.ENTRY,
                metadata={
                    "rsi": float(current_rsi),
                    "bb_position": float(current_bb),
                    "accum_score": float(current_accum),
                },
            )
        elif short_score >= 0.5:
            return Signal(
                symbol=symbol,
                direction=Direction.SHORT,
                strength=float(short_score),
                confidence=float(min(0.9, short_score + 0.2)),
                timestamp=datetime.now(),
                signal_type=SignalType.ENTRY,
                metadata={
                    "rsi": float(current_rsi),
                    "bb_position": float(current_bb),
                },
            )

        return None


class RSIReversalStrategy(BaseStrategy):
    """
    RSI Mean Reversion Strategy.

    Validated: Sharpe 0.61 on IWM (p=0.04)
    """

    name = "rsi_reversal"
    universe = ["IWM", "SPY", "QQQ", "DIA"]
    required_features = ["rsi", "returns", "mean_reversion"]

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 25.0,
        rsi_overbought: float = 75.0,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        as_of: datetime,
    ) -> list:
        from src.core import Signal, SignalType

        signals = []

        for symbol, df in data.items():
            if len(df) < self.rsi_period + 20:
                continue

            close = df["close"]
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period).mean()
            rsi = 100 - (100 / (1 + gain / (loss + 1e-10)))

            current_rsi = rsi.iloc[-1]
            prev_rsi = rsi.iloc[-2]

            # Entry on extreme RSI with reversal
            if current_rsi < self.rsi_oversold and current_rsi > prev_rsi:
                strength = (self.rsi_oversold - current_rsi) / self.rsi_oversold
                signals.append(Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=float(min(1.0, strength + 0.3)),
                    confidence=0.6,
                    timestamp=datetime.now(),
                    signal_type=SignalType.ENTRY,
                    metadata={"rsi": float(current_rsi)},
                ))
            elif current_rsi > self.rsi_overbought and current_rsi < prev_rsi:
                strength = (current_rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
                signals.append(Signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=float(min(1.0, strength + 0.3)),
                    confidence=0.6,
                    timestamp=datetime.now(),
                    signal_type=SignalType.ENTRY,
                    metadata={"rsi": float(current_rsi)},
                ))

        return signals


class VolatilityBreakoutStrategy(BaseStrategy):
    """
    Volatility Breakout Strategy.

    Validated: Sharpe 0.73 on AMD (p=0.02)
    """

    name = "volatility_breakout"
    universe = ["AMD", "NVDA", "MRVL", "MU"]
    required_features = ["atr", "volatility", "returns", "volume_features"]

    def __init__(
        self,
        atr_period: int = 14,
        breakout_mult: float = 1.5,
        vol_lookback: int = 20,
    ):
        self.atr_period = atr_period
        self.breakout_mult = breakout_mult
        self.vol_lookback = vol_lookback

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        as_of: datetime,
    ) -> list:
        from src.core import Signal, SignalType

        signals = []

        for symbol, df in data.items():
            if len(df) < max(self.atr_period, self.vol_lookback) + 20:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # ATR
            tr = pd.concat([
                high - low,
                abs(high - close.shift(1)),
                abs(low - close.shift(1))
            ], axis=1).max(axis=1)
            atr = tr.rolling(self.atr_period).mean()

            # Volatility regime
            returns = close.pct_change()
            vol = returns.rolling(self.vol_lookback).std() * np.sqrt(252)
            vol_ma = vol.rolling(60).mean()

            # High vol regime + breakout
            high_vol = vol.iloc[-1] > vol_ma.iloc[-1]
            breakout_level = close.iloc[-2] + atr.iloc[-2] * self.breakout_mult
            breakdown_level = close.iloc[-2] - atr.iloc[-2] * self.breakout_mult

            current_close = close.iloc[-1]

            if high_vol:
                if current_close > breakout_level:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=0.7,
                        confidence=0.65,
                        timestamp=datetime.now(),
                        signal_type=SignalType.ENTRY,
                        metadata={
                            "breakout_level": float(breakout_level),
                            "vol_ratio": float(vol.iloc[-1] / vol_ma.iloc[-1]),
                        },
                    ))
                elif current_close < breakdown_level:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=0.7,
                        confidence=0.65,
                        timestamp=datetime.now(),
                        signal_type=SignalType.ENTRY,
                        metadata={
                            "breakdown_level": float(breakdown_level),
                            "vol_ratio": float(vol.iloc[-1] / vol_ma.iloc[-1]),
                        },
                    ))

        return signals


# =============================================================================
# PIPELINE RUNNER
# =============================================================================

class DailyRunner:
    """
    Orchestrates the daily trading pipeline.

    Loads strategy configuration from config/strategies/validated_strategies.yaml
    and computes required features at runtime.
    """

    def __init__(
        self,
        mode: str = "signals",  # signals, paper, live
        capital: float = 1000.0,
        output_dir: Path = None,
        config_file: str = "validated_strategies.yaml",
    ):
        self.mode = mode
        self.capital = capital
        self.output_dir = output_dir or Path.home() / "quant_results" / "daily_runs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load strategy configuration
        try:
            self.config = load_strategy_config(config_file)
            logger.info(f"Loaded config from {config_file}")
            logger.info(f"  Enabled strategies: {len(self.config.get_enabled_strategies())}")
            logger.info(f"  Total symbols: {len(self.config.get_all_symbols())}")
            logger.info(f"  Required features: {len(self.config.get_all_features())}")
        except Exception as e:
            logger.warning(f"Could not load config: {e}, using defaults")
            self.config = None

        # Initialize strategies from config or use defaults
        self.strategies = self._init_strategies()

        # Pipeline config from config file or defaults
        if self.config:
            defaults = self.config.defaults
            pdt = self.config.pdt
            self.pipeline_config = PipelineConfig(
                symbols=list(self.config.get_all_symbols()),
                lookback_days=defaults.get("lookback_days", 60),
                min_signal_strength=defaults.get("min_signal_strength", 0.3),
                min_signal_confidence=defaults.get("min_signal_confidence", 0.5),
                pdt_enabled=pdt.enabled,
                min_hold_days=pdt.min_hold_days,
                max_day_trades=pdt.max_day_trades,
                max_position_pct=defaults.get("max_position_pct", 0.25),
                max_positions=8,
                min_trade_value=defaults.get("min_trade_value", 20.0),
                max_drawdown_pct=self.config.alerts.max_drawdown_critical,
                daily_loss_limit_pct=self.config.alerts.daily_loss_critical,
            )
        else:
            self.pipeline_config = PipelineConfig(
                symbols=self._get_universe(),
                lookback_days=60,
                min_signal_strength=0.3,
                min_signal_confidence=0.5,
                pdt_enabled=True,
                min_hold_days=2,
                max_day_trades=3,
                max_position_pct=0.25,
                max_positions=8,
                min_trade_value=20.0,
                max_drawdown_pct=0.15,
                daily_loss_limit_pct=0.05,
            )

        # Position sizer
        self.position_sizer = FixedFractionalSizer(
            fraction=0.10,
            max_fraction=0.25,
            scale_by_strength=True,
        )

        # Initialize pipeline
        self.pipeline = DailySignalPipeline(
            strategies=self.strategies,
            config=self.pipeline_config,
            position_sizer=self.position_sizer,
        )

        # Broker (lazy init)
        self._broker = None
        self._executor = None

        # Knowledge base for feedback loop
        self._knowledge_base = None
        if KNOWLEDGE_BASE_AVAILABLE:
            try:
                self._knowledge_base = KnowledgeBase()
                logger.info("Knowledge base initialized for feedback loop")
            except Exception as e:
                logger.warning(f"Could not initialize knowledge base: {e}")

    def _init_strategies(self) -> list:
        """Initialize strategies from config or use defaults."""
        import inspect

        # Map strategy names to classes
        strategy_classes = {
            "insider_technical": InsiderTechnicalStrategy,
            "rsi_reversal": RSIReversalStrategy,
            "volatility_breakout": VolatilityBreakoutStrategy,
        }

        strategies = []

        if self.config:
            # Load strategies from config
            for strat_def in self.config.get_enabled_strategies():
                if strat_def.name in strategy_classes:
                    # Get the class
                    cls = strategy_classes[strat_def.name]

                    # Filter parameters to only those accepted by __init__
                    sig = inspect.signature(cls.__init__)
                    valid_params = set(sig.parameters.keys()) - {'self'}
                    filtered_params = {
                        k: v for k, v in strat_def.parameters.items()
                        if k in valid_params
                    }

                    # Initialize with filtered parameters
                    try:
                        strategy = cls(**filtered_params)
                        # Override universe from config
                        strategy.universe = strat_def.universe
                        # Set required features from config
                        strategy.required_features = strat_def.features
                        strategies.append(strategy)
                        logger.info(f"  Loaded strategy: {strat_def.name} "
                                   f"(Sharpe: {strat_def.validation.sharpe}, "
                                   f"p={strat_def.validation.p_value})")
                    except Exception as e:
                        logger.warning(f"Could not initialize {strat_def.name}: {e}")
                        # Fall back to default initialization
                        try:
                            strategy = cls()
                            strategy.universe = strat_def.universe
                            strategy.required_features = strat_def.features
                            strategies.append(strategy)
                            logger.info(f"  Loaded {strat_def.name} with defaults")
                        except Exception as e2:
                            logger.error(f"Failed to load {strat_def.name}: {e2}")
                else:
                    logger.warning(f"Unknown strategy class: {strat_def.name}")
        else:
            # Use default strategies
            strategies = [
                InsiderTechnicalStrategy(),
                RSIReversalStrategy(),
                VolatilityBreakoutStrategy(),
            ]

        return strategies

    def _get_universe(self) -> list[str]:
        """Get combined universe from all strategies."""
        universe = set()
        for strategy in self.strategies:
            universe.update(strategy.universe)
        return sorted(list(universe))

    async def _get_broker(self):
        """Get or create broker connection."""
        if self._broker is None:
            api_key = os.environ.get("ALPACA_API_KEY")
            secret_key = os.environ.get("ALPACA_SECRET_KEY")
            paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

            # Try loading from credentials.yaml if not in environment
            if not api_key or not secret_key:
                creds_path = Path(__file__).parent.parent / "config" / "credentials.yaml"
                if creds_path.exists():
                    try:
                        import yaml
                        with open(creds_path) as f:
                            creds = yaml.safe_load(f)
                        alpaca = creds.get("alpaca", {})
                        api_key = alpaca.get("api_key")
                        secret_key = alpaca.get("secret_key")
                        paper = alpaca.get("paper", True)
                        logger.info("Loaded Alpaca credentials from config/credentials.yaml")
                    except Exception as e:
                        logger.warning(f"Could not load credentials.yaml: {e}")

            if not api_key or not secret_key:
                logger.warning("Alpaca credentials not found - running in signals-only mode")
                return None

            from src.execution.broker.alpaca import AlpacaBroker

            self._broker = AlpacaBroker(
                api_key=api_key,
                secret_key=secret_key,
                paper=paper if self.mode != "live" else False,
            )
            await self._broker.connect()

            self._executor = OrderExecutor(
                self._broker,
                ExecutorConfig(
                    max_retries=3,
                    use_limit_orders=False,
                    order_timeout_seconds=60,
                ),
            )

        return self._broker

    def _get_portfolio(self) -> Portfolio:
        """Get current portfolio state."""
        # For now, create a simple portfolio
        # In production, this would come from the broker
        return Portfolio(
            initial_capital=Decimal(str(self.capital)),
            cash=Decimal(str(self.capital)),
            positions={},
        )

    async def run_signals(self) -> PipelineResult:
        """Run signal generation only."""
        logger.info("=" * 60)
        logger.info("DAILY SIGNAL GENERATION")
        logger.info("=" * 60)

        portfolio = self._get_portfolio()
        result = await self.pipeline.run(portfolio, force_refresh=True)

        self._print_result(result)
        self._save_result(result)

        # Knowledge base feedback
        self._record_live_signals(result)
        self._record_daily_summary(result)

        return result

    async def run_paper(self) -> tuple[PipelineResult, list[ExecutionResult]]:
        """Run paper trading."""
        logger.info("=" * 60)
        logger.info("PAPER TRADING")
        logger.info("=" * 60)

        # Generate signals (this also records to knowledge base)
        portfolio = self._get_portfolio()
        result = await self.pipeline.run(portfolio, force_refresh=True)

        self._print_result(result)
        self._save_result(result)

        # Record signals to knowledge base
        self._record_live_signals(result)

        if not result.proposals:
            logger.info("No trade proposals generated")
            self._record_daily_summary(result)
            return result, []

        # Get broker
        broker = await self._get_broker()
        if broker is None:
            logger.warning("No broker connection - cannot execute")
            self._record_daily_summary(result)
            return result, []

        # Execute proposals
        logger.info(f"\nExecuting {len(result.proposals)} proposals...")
        exec_results = await self._executor.execute_proposals(result.proposals)

        self._print_execution_results(exec_results)
        self._save_execution_results(exec_results)

        # Knowledge base feedback with executions
        self._record_executions(exec_results)
        self._record_daily_summary(result, exec_results)

        return result, exec_results

    async def run_live(self, confirm: bool = False) -> tuple[PipelineResult, list[ExecutionResult]]:
        """Run live trading."""
        if not confirm:
            logger.error("Live trading requires --confirm flag")
            return None, []

        logger.info("=" * 60)
        logger.info("LIVE TRADING")
        logger.info("=" * 60)
        logger.warning(">>> LIVE TRADING MODE - REAL MONEY <<<")

        return await self.run_paper()

    def _print_result(self, result: PipelineResult) -> None:
        """Print pipeline result."""
        if RICH_AVAILABLE and console:
            self._print_result_rich(result)
        else:
            self._print_result_plain(result)

    def _print_result_rich(self, result: PipelineResult) -> None:
        """Print with Rich formatting."""
        # Summary panel
        summary = f"""
[bold]Signals Generated:[/bold] {len(result.signals)}
[bold]Trade Proposals:[/bold] {len(result.proposals)}
[bold]Rejected:[/bold] {len(result.rejected)}
[bold]Buy Signals:[/bold] {result.num_buy_signals}
[bold]Sell Signals:[/bold] {result.num_sell_signals}
[bold]PDT Status:[/bold] {result.metadata.get('pdt_status', {}).get('day_trades_count', 0)}/3 day trades
        """
        console.print(Panel(summary, title="Pipeline Summary", border_style="green"))

        # Signals table
        if result.signals:
            table = Table(title="Generated Signals")
            table.add_column("Symbol", style="cyan")
            table.add_column("Direction", style="green")
            table.add_column("Strength", justify="right")
            table.add_column("Confidence", justify="right")
            table.add_column("Strategy")

            for s in result.signals:
                direction_color = "green" if s.direction == Direction.LONG else "red"
                table.add_row(
                    s.symbol,
                    f"[{direction_color}]{s.direction.value}[/{direction_color}]",
                    f"{s.strength:.2f}",
                    f"{s.confidence:.2f}",
                    s.strategy,
                )

            console.print(table)

        # Proposals table
        if result.proposals:
            table = Table(title="Trade Proposals")
            table.add_column("Symbol", style="cyan")
            table.add_column("Side")
            table.add_column("Quantity", justify="right")
            table.add_column("Strategy")
            table.add_column("Reasoning")

            for p in result.proposals:
                side_color = "green" if p.order.side.value == "BUY" else "red"
                table.add_row(
                    p.order.symbol,
                    f"[{side_color}]{p.order.side.value}[/{side_color}]",
                    f"{p.order.quantity:.4f}",
                    p.strategy,
                    p.reasoning[:40] + "..." if len(p.reasoning) > 40 else p.reasoning,
                )

            console.print(table)

        # Rejected
        if result.rejected:
            console.print(f"\n[yellow]Rejected signals: {len(result.rejected)}[/yellow]")
            for signal, reason in result.rejected[:5]:
                console.print(f"  - {signal.symbol}: {reason}")

    def _print_result_plain(self, result: PipelineResult) -> None:
        """Print without Rich."""
        print("\n" + "=" * 60)
        print("PIPELINE SUMMARY")
        print("=" * 60)
        print(f"Signals Generated: {len(result.signals)}")
        print(f"Trade Proposals: {len(result.proposals)}")
        print(f"Rejected: {len(result.rejected)}")
        print(f"Buy/Sell: {result.num_buy_signals}/{result.num_sell_signals}")

        if result.signals:
            print("\nSIGNALS:")
            for s in result.signals:
                print(f"  {s.symbol}: {s.direction.value} "
                      f"(str={s.strength:.2f}, conf={s.confidence:.2f}) "
                      f"[{s.strategy}]")

        if result.proposals:
            print("\nPROPOSALS:")
            for p in result.proposals:
                print(f"  {p.order.symbol}: {p.order.side.value} "
                      f"qty={p.order.quantity:.4f}")

    def _print_execution_results(self, results: list[ExecutionResult]) -> None:
        """Print execution results."""
        if RICH_AVAILABLE and console:
            table = Table(title="Execution Results")
            table.add_column("Symbol", style="cyan")
            table.add_column("Status")
            table.add_column("Fill Price", justify="right")
            table.add_column("Quantity", justify="right")
            table.add_column("Slippage (bps)", justify="right")

            for r in results:
                status_color = "green" if r.is_success else "red"
                table.add_row(
                    r.proposal.order.symbol,
                    f"[{status_color}]{r.status.value}[/{status_color}]",
                    f"${r.fill_price:.2f}" if r.fill_price else "-",
                    f"{r.fill_quantity:.4f}" if r.fill_quantity else "-",
                    f"{r.slippage_bps:.1f}" if r.slippage_bps else "-",
                )

            console.print(table)
        else:
            print("\nEXECUTION RESULTS:")
            for r in results:
                print(f"  {r.proposal.order.symbol}: {r.status.value} "
                      f"@ ${r.fill_price:.2f}" if r.fill_price else "")

    def _save_result(self, result: PipelineResult) -> None:
        """Save pipeline result to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"signals_{timestamp}.json"

        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        logger.info(f"Results saved to: {filepath}")

    def _save_execution_results(self, results: list[ExecutionResult]) -> None:
        """Save execution results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"execution_{timestamp}.json"

        with open(filepath, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2, default=str)

        logger.info(f"Execution results saved to: {filepath}")

    # =========================================================================
    # KNOWLEDGE BASE FEEDBACK LOOP
    # =========================================================================

    def _record_live_signals(self, result: PipelineResult) -> None:
        """
        Record live signals to knowledge base for tracking.

        Enables comparison between backtest predictions and live behavior.
        """
        if not self._knowledge_base:
            return

        try:
            for signal in result.signals:
                self._knowledge_base.add_insight(
                    category="strategy",
                    content=f"Live signal: {signal.symbol} {signal.direction.value} "
                            f"(str={signal.strength:.2f}, conf={signal.confidence:.2f})",
                    evidence=[f"daily_run_{datetime.now().strftime('%Y%m%d')}"],
                    confidence=signal.confidence,
                    tags=[
                        "live_signal",
                        signal.strategy,
                        signal.symbol,
                        signal.direction.value,
                    ],
                )

            logger.info(f"Recorded {len(result.signals)} live signals to knowledge base")

        except Exception as e:
            logger.warning(f"Could not record signals to knowledge base: {e}")

    def _record_executions(self, results: list[ExecutionResult]) -> None:
        """
        Record execution results to knowledge base.

        Tracks fill prices and slippage for drift detection.
        """
        if not self._knowledge_base:
            return

        try:
            for exec_result in results:
                # Build insight content
                if exec_result.is_success:
                    content = (
                        f"Executed: {exec_result.proposal.order.symbol} "
                        f"{exec_result.proposal.order.side.value} "
                        f"qty={exec_result.fill_quantity:.4f} @ ${exec_result.fill_price:.2f}"
                    )
                    if exec_result.slippage_bps:
                        content += f" (slippage: {exec_result.slippage_bps:.1f}bps)"

                    self._knowledge_base.add_insight(
                        category="strategy",
                        content=content,
                        evidence=[f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"],
                        confidence=0.9,
                        tags=[
                            "execution",
                            exec_result.proposal.strategy,
                            exec_result.proposal.order.symbol,
                            "success",
                        ],
                    )
                else:
                    self._knowledge_base.add_insight(
                        category="warning",
                        content=f"Failed execution: {exec_result.proposal.order.symbol} - {exec_result.status.value}",
                        evidence=[f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"],
                        confidence=0.8,
                        tags=[
                            "execution",
                            exec_result.proposal.strategy,
                            exec_result.proposal.order.symbol,
                            "failed",
                        ],
                    )

            successful = sum(1 for r in results if r.is_success)
            logger.info(f"Recorded {successful}/{len(results)} executions to knowledge base")

        except Exception as e:
            logger.warning(f"Could not record executions to knowledge base: {e}")

    def _record_daily_summary(self, result: PipelineResult, exec_results: list[ExecutionResult] = None) -> None:
        """
        Record daily summary to knowledge base.

        Creates an overall insight for the day's trading activity.
        """
        if not self._knowledge_base:
            return

        try:
            # Build summary
            summary_parts = [
                f"Daily Summary {datetime.now().strftime('%Y-%m-%d')}:",
                f"  Signals: {len(result.signals)} ({result.num_buy_signals} buy, {result.num_sell_signals} sell)",
                f"  Proposals: {len(result.proposals)}",
                f"  Rejected: {len(result.rejected)}",
            ]

            if exec_results:
                successful = sum(1 for r in exec_results if r.is_success)
                avg_slippage = sum(
                    r.slippage_bps for r in exec_results if r.slippage_bps
                ) / max(1, sum(1 for r in exec_results if r.slippage_bps))
                summary_parts.extend([
                    f"  Executions: {successful}/{len(exec_results)} successful",
                    f"  Avg Slippage: {avg_slippage:.1f}bps",
                ])

            # Record strategies that generated signals
            strategies_active = set(s.strategy for s in result.signals)
            if strategies_active:
                summary_parts.append(f"  Active Strategies: {', '.join(strategies_active)}")

            self._knowledge_base.add_insight(
                category="pattern",
                content="\n".join(summary_parts),
                evidence=[f"daily_run_{datetime.now().strftime('%Y%m%d')}"],
                confidence=0.95,
                tags=["daily_summary", datetime.now().strftime("%Y-%m-%d")],
            )

            logger.info("Recorded daily summary to knowledge base")

        except Exception as e:
            logger.warning(f"Could not record daily summary: {e}")


# =============================================================================
# SCHEDULER
# =============================================================================

def setup_scheduler(runner: DailyRunner, config=None):
    """Setup APScheduler for automated runs using config."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return None

    # Load schedule config
    if config is None:
        try:
            from src.core.strategy_config import load_strategy_config
            config = load_strategy_config()
        except Exception as e:
            logger.warning(f"Could not load strategy config: {e}")
            config = None

    # Get schedule times from config or use defaults
    if config:
        sched = config.schedule
        timezone = sched.timezone
        signal_time = sched.signal_time
        execution_time = sched.execution_time
        eod_time = sched.eod_time
        signal_days = ",".join(sched.signal_days[:3])  # mon,tue,wed format
    else:
        timezone = "America/New_York"
        signal_time = "07:00"
        execution_time = "09:35"
        eod_time = "16:05"
        signal_days = "mon,tue,wed,thu,fri"

    # Parse times
    sig_hour, sig_min = map(int, signal_time.split(":"))
    exec_hour, exec_min = map(int, execution_time.split(":"))
    eod_hour, eod_min = map(int, eod_time.split(":"))

    scheduler = AsyncIOScheduler()

    # Pre-market signal generation
    scheduler.add_job(
        runner.run_signals,
        CronTrigger(
            hour=sig_hour,
            minute=sig_min,
            day_of_week="mon,tue,wed,thu,fri",
            timezone=timezone,
        ),
        id="morning_signals",
        name=f"Morning Signal Generation ({signal_time} ET)",
    )

    # Market open execution
    async def market_open_execution():
        if runner.mode in ("paper", "live"):
            await runner.run_paper()

    scheduler.add_job(
        market_open_execution,
        CronTrigger(
            hour=exec_hour,
            minute=exec_min,
            day_of_week="mon,tue,wed,thu,fri",
            timezone=timezone,
        ),
        id="market_open",
        name=f"Market Open Execution ({execution_time} ET)",
    )

    # End of day snapshot
    scheduler.add_job(
        runner.run_signals,
        CronTrigger(
            hour=eod_hour,
            minute=eod_min,
            day_of_week="mon,tue,wed,thu,fri",
            timezone=timezone,
        ),
        id="eod_snapshot",
        name=f"End of Day Snapshot ({eod_time} ET)",
    )

    # Log scheduled jobs
    logger.info(f"Scheduled jobs (timezone: {timezone}):")
    logger.info(f"  - Signal generation: {signal_time} ET (Mon-Fri)")
    logger.info(f"  - Execution: {execution_time} ET (Mon-Fri)")
    logger.info(f"  - EOD snapshot: {eod_time} ET (Mon-Fri)")

    return scheduler


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Daily Trading Pipeline Runner")
    parser.add_argument(
        "--mode",
        choices=["signals", "paper", "live"],
        default="signals",
        help="Running mode",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Account capital",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run with scheduler",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm live trading",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory",
    )

    args = parser.parse_args()

    runner = DailyRunner(
        mode=args.mode,
        capital=args.capital,
        output_dir=args.output_dir,
    )

    if args.schedule:
        scheduler = setup_scheduler(runner)
        if scheduler:
            scheduler.start()
            logger.info("Scheduler started. Press Ctrl+C to exit.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                scheduler.shutdown()
        return

    # Single run
    if args.mode == "signals":
        await runner.run_signals()
    elif args.mode == "paper":
        await runner.run_paper()
    elif args.mode == "live":
        await runner.run_live(confirm=args.confirm)


if __name__ == "__main__":
    asyncio.run(main())
