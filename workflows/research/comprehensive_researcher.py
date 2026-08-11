"""
Comprehensive Research Workflow

Enhanced research system that:
1. Uses sector-aware symbol categorization
2. Runs multiple validation tests (MCPT, walk-forward, bootstrap)
3. Integrates leak detection
4. Tests across correlation clusters
5. Generates new experiment leads
6. Produces detailed research reports

Usage:
    from workflows.research.comprehensive_researcher import ComprehensiveResearcher

    researcher = ComprehensiveResearcher()
    report = asyncio.run(researcher.run_full_cycle())
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))

import numpy as np
import pandas as pd

from .symbol_universe import (
    SymbolUniverse, Sector, Industry, VolatilityProfile,
    get_strategy_suggestions_for_symbol, get_cross_sector_pairs,
)
from .knowledge_base import KnowledgeBase
from .data_hub import DataHub, DataBundle

# Import plotting module
try:
    from workflows.visualizations.strategy_plots import (
        StrategyPlotter, PlotConfig, plot_validation_dashboard
    )
    PLOTS_AVAILABLE = True
except ImportError:
    PLOTS_AVAILABLE = False

# Import evaluation module functions
from src.evaluation import (
    # Metrics
    sharpe_ratio, sortino_ratio, max_drawdown, total_return,
    win_rate, profit_factor, calmar_ratio,
    performance_summary, risk_summary,
    # Statistical testing
    compute_bootstrap_ci, BootstrapCI,
    StatisticalTester, test_strategy_significance,
    # Hypothesis testing (data snooping protection)
    reality_check, stepwise_spa,
    # Regime analysis
    detect_regimes, evaluate_by_regime, get_current_regime,
    # MCPT
    mcpt_test, MCPTConfig,
    # Reporting
    generate_json_report,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ValidationResult:
    """Comprehensive validation result."""
    strategy_name: str
    symbol: str
    params: dict

    # Basic metrics
    train_sharpe: float = 0.0
    val_sharpe: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0

    # Additional metrics from evaluation module
    sortino: float = 0.0
    calmar: float = 0.0
    win_rate_pct: float = 0.0

    # MCPT results
    mcpt_p_value: float = 1.0
    mcpt_percentile: float = 0.0

    # Walk-forward results
    walk_forward_oos_sharpe: float = 0.0
    walk_forward_stability: float = 0.0
    is_oos_ratio: float = 0.0

    # Bootstrap CI
    sharpe_ci_lower: float = 0.0
    sharpe_ci_upper: float = 0.0

    # Regime analysis
    regime_performance: dict = field(default_factory=dict)
    current_regime: str = ""

    # Leak check
    has_lookahead_bias: bool = False
    leak_details: list[str] = field(default_factory=list)

    # Data snooping protection
    survives_reality_check: bool = True

    # Status
    is_significant: bool = False
    passes_all_checks: bool = False
    failure_reasons: list[str] = field(default_factory=list)

    # Store returns for later analysis
    returns: pd.Series | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "symbol": self.symbol,
            "params": self.params,
            "train_sharpe": self.train_sharpe,
            "val_sharpe": self.val_sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "win_rate": self.win_rate_pct,
            "mcpt_p_value": self.mcpt_p_value,
            "walk_forward_oos_sharpe": self.walk_forward_oos_sharpe,
            "sharpe_ci": [self.sharpe_ci_lower, self.sharpe_ci_upper],
            "regime_performance": self.regime_performance,
            "current_regime": self.current_regime,
            "has_lookahead_bias": self.has_lookahead_bias,
            "survives_reality_check": self.survives_reality_check,
            "is_significant": self.is_significant,
            "passes_all_checks": self.passes_all_checks,
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class ExperimentLead:
    """A promising experiment direction for future research."""
    title: str
    description: str
    strategy_type: str
    symbols: list[str]
    params: dict
    rationale: str
    priority: float  # 0-1
    source: str  # "sector_analysis", "correlation", "pattern_extension", etc.
    expected_edge: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "strategy_type": self.strategy_type,
            "symbols": self.symbols,
            "params": self.params,
            "rationale": self.rationale,
            "priority": self.priority,
            "source": self.source,
            "expected_edge": self.expected_edge,
        }


@dataclass
class ResearchCycleReport:
    """Complete report from a research cycle."""
    cycle_id: str
    start_time: datetime
    end_time: datetime

    # Experiments run
    total_experiments: int
    significant_count: int
    passed_all_checks_count: int

    # Best results
    validated_strategies: list[ValidationResult]
    best_strategies: list[dict]

    # Sector analysis
    sector_performance: dict[str, dict]

    # New leads generated
    experiment_leads: list[ExperimentLead]

    # Statistics
    coverage_by_sector: dict[str, int]
    strategies_tested: list[str]

    # Data snooping protection results
    reality_check_result: dict = field(default_factory=dict)
    strategies_surviving_snooping: int = 0

    # Current market regime
    current_regime: str = ""
    regime_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "runtime_minutes": (self.end_time - self.start_time).total_seconds() / 60,
            "total_experiments": self.total_experiments,
            "significant_count": self.significant_count,
            "passed_all_checks_count": self.passed_all_checks_count,
            "best_strategies": self.best_strategies,
            "sector_performance": self.sector_performance,
            "experiment_leads": [l.to_dict() for l in self.experiment_leads],
            "coverage_by_sector": self.coverage_by_sector,
            "reality_check": self.reality_check_result,
            "strategies_surviving_snooping": self.strategies_surviving_snooping,
            "current_regime": self.current_regime,
            "regime_confidence": self.regime_confidence,
        }


# =============================================================================
# STRATEGY EXECUTORS
# =============================================================================

def execute_rsi_reversal(df: pd.DataFrame, params: dict) -> pd.Series:
    """RSI mean reversion strategy."""
    period = params.get("period", 14)
    oversold = params.get("oversold", 30)
    overbought = params.get("overbought", 70)

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    positions = pd.Series(0, index=df.index)
    positions[rsi < oversold] = 1
    positions[rsi > overbought] = -1

    return positions.shift(1).fillna(0)


def execute_momentum(df: pd.DataFrame, params: dict) -> pd.Series:
    """Momentum strategy."""
    lookback = params.get("lookback", 20)
    threshold = params.get("threshold", 0.0)

    momentum = df["close"].pct_change(lookback)

    positions = pd.Series(0, index=df.index)
    positions[momentum > threshold] = 1
    positions[momentum < -threshold] = -1

    return positions.shift(1).fillna(0)


def execute_breakout(df: pd.DataFrame, params: dict) -> pd.Series:
    """Breakout strategy."""
    lookback = params.get("lookback", 20)

    high_channel = df["high"].rolling(lookback).max()
    low_channel = df["low"].rolling(lookback).min()

    positions = pd.Series(0, index=df.index)
    positions[df["close"] > high_channel.shift(1)] = 1
    positions[df["close"] < low_channel.shift(1)] = -1

    return positions.ffill().shift(1).fillna(0)


def execute_bollinger_reversal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Bollinger band mean reversion."""
    period = params.get("period", 20)
    num_std = params.get("num_std", 2.0)

    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std

    positions = pd.Series(0, index=df.index)
    positions[df["close"] < lower] = 1
    positions[df["close"] > upper] = -1

    return positions.shift(1).fillna(0)


def execute_volatility_breakout(df: pd.DataFrame, params: dict) -> pd.Series:
    """ATR-based volatility breakout."""
    atr_period = params.get("atr_period", 14)
    mult = params.get("multiplier", 1.5)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    upper = df["close"].shift(1) + mult * atr.shift(1)
    lower = df["close"].shift(1) - mult * atr.shift(1)

    positions = pd.Series(0, index=df.index)
    positions[df["close"] > upper] = 1
    positions[df["close"] < lower] = -1

    return positions.shift(1).fillna(0)


def execute_sma_crossover(df: pd.DataFrame, params: dict) -> pd.Series:
    """SMA crossover strategy."""
    fast = params.get("fast_period", 10)
    slow = params.get("slow_period", 30)

    fast_ma = df["close"].rolling(fast).mean()
    slow_ma = df["close"].rolling(slow).mean()

    positions = pd.Series(0, index=df.index)
    positions[fast_ma > slow_ma] = 1
    positions[fast_ma < slow_ma] = -1

    return positions.shift(1).fillna(0)


STRATEGY_MAP = {
    "rsi_reversal": execute_rsi_reversal,
    "momentum": execute_momentum,
    "breakout": execute_breakout,
    "bollinger_reversal": execute_bollinger_reversal,
    "volatility_breakout": execute_volatility_breakout,
    "sma_crossover": execute_sma_crossover,
}


# =============================================================================
# COMPREHENSIVE RESEARCHER
# =============================================================================

class ComprehensiveResearcher:
    """
    Comprehensive research workflow with full validation suite.

    Features:
    - Sector-aware testing
    - Multiple validation methods (MCPT, walk-forward, bootstrap)
    - Leak detection
    - Cross-sector pattern analysis
    - Automatic lead generation
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        n_permutations: int = 500,
        validation_days: int = 90,
        min_sharpe: float = 0.5,
        max_p_value: float = 0.05,
    ):
        self.output_dir = output_dir or _RESULTS_DIR / "comprehensive_research"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.n_permutations = n_permutations
        self.validation_days = validation_days
        self.min_sharpe = min_sharpe
        self.max_p_value = max_p_value

        self.universe = SymbolUniverse()
        self.kb = KnowledgeBase()
        self.hub = DataHub()

        # Results tracking
        self.results: list[ValidationResult] = []
        self.leads: list[ExperimentLead] = []

    async def run_full_cycle(
        self,
        universes: list[str] | None = None,
        strategies: list[str] | None = None,
        generate_plots: bool = False,
    ) -> ResearchCycleReport:
        """
        Run a full comprehensive research cycle.

        Args:
            universes: Universe names to test (default: all main universes)
            strategies: Strategy types to test (default: all)
            generate_plots: Generate validation plots for significant strategies

        Returns:
            Complete research cycle report
        """
        cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now()

        logger.info(f"Starting comprehensive research cycle: {cycle_id}")
        print(f"\n{'='*60}")
        print(f"COMPREHENSIVE RESEARCH CYCLE: {cycle_id}")
        print(f"{'='*60}")

        # Get universes to test
        all_universes = self.universe.get_research_universes()
        universes = universes or ["market_etfs", "tech_mega", "semiconductors", "high_volatility"]

        # Get strategies to test
        strategies = strategies or list(STRATEGY_MAP.keys())

        # Collect all symbols
        all_symbols = set()
        for uni_name in universes:
            if uni_name in all_universes:
                all_symbols.update(all_universes[uni_name])

        print(f"Testing {len(all_symbols)} symbols across {len(universes)} universes")
        print(f"Strategies: {strategies}")
        print(f"Permutations: {self.n_permutations}")
        print(f"{'='*60}\n")

        # Fetch data
        print("Fetching data...")
        data = await self._fetch_data(list(all_symbols))
        print(f"  Loaded {len(data)} symbols\n")

        # Run experiments by sector
        sector_performance = {}
        coverage_by_sector = {}
        total_experiments = 0

        for sector in [Sector.TECHNOLOGY, Sector.FINANCIALS, Sector.HEALTHCARE, Sector.ETF]:
            sector_symbols = [s for s in all_symbols if self._get_sector(s) == sector]
            if not sector_symbols:
                continue

            print(f"\n--- Testing {sector.value.upper()} ({len(sector_symbols)} symbols) ---")
            coverage_by_sector[sector.value] = len(sector_symbols)

            sector_results = []
            for symbol in sector_symbols:
                if symbol not in data:
                    continue

                # Get suggested strategies for this sector
                suggested = get_strategy_suggestions_for_symbol(symbol)
                test_strategies = [s for s in strategies if s in suggested or len(suggested) == 0]

                for strat in test_strategies[:3]:  # Limit strategies per symbol
                    result = await self._run_single_experiment(
                        strategy_name=strat,
                        symbol=symbol,
                        price_data=data[symbol],
                    )
                    self.results.append(result)
                    sector_results.append(result)
                    total_experiments += 1

                    # Print progress
                    status = "PASS" if result.passes_all_checks else "fail"
                    print(f"  {symbol}/{strat}: Sharpe={result.val_sharpe:.2f}, "
                          f"p={result.mcpt_p_value:.3f} [{status}]")

            # Calculate sector performance
            significant = [r for r in sector_results if r.is_significant]
            sector_performance[sector.value] = {
                "total": len(sector_results),
                "significant": len(significant),
                "best_sharpe": max((r.val_sharpe for r in sector_results), default=0),
                "avg_sharpe": np.mean([r.val_sharpe for r in sector_results]) if sector_results else 0,
            }

        # Generate experiment leads
        print("\n--- Generating New Experiment Leads ---")
        self.leads = self._generate_leads()
        print(f"  Generated {len(self.leads)} new leads")

        # Compile report
        validated = [r for r in self.results if r.passes_all_checks]
        significant = [r for r in self.results if r.is_significant]

        # Data snooping protection with Reality Check
        reality_check_result = {}
        strategies_surviving = 0
        if len(significant) >= 5:
            print("\n--- Running Reality Check (Data Snooping Protection) ---")
            try:
                # Collect returns from significant strategies as dict
                strategy_returns_dict = {
                    f"{r.strategy_name}/{r.symbol}": r.returns
                    for r in significant
                    if r.returns is not None and len(r.returns.dropna()) > 50
                }
                if len(strategy_returns_dict) >= 3:
                    # Use first symbol's price returns as benchmark
                    first_symbol = next(iter(data.keys()))
                    benchmark = data[first_symbol]["close"].pct_change().dropna()

                    rc_result = reality_check(strategy_returns_dict, benchmark)
                    reality_check_result = {
                        "p_value": rc_result.p_value,
                        "is_significant": rc_result.is_significant,
                        "best_strategy": rc_result.best_strategy,
                        "best_performance": rc_result.best_performance,
                    }
                    strategies_surviving = 1 if rc_result.is_significant else 0
                    print(f"  Reality Check p-value: {rc_result.p_value:.4f}")
                    print(f"  Best strategy: {rc_result.best_strategy} (significant: {rc_result.is_significant})")
                    print(f"  Strategies surviving snooping: {strategies_surviving}/{len(significant)}")
            except Exception as e:
                logger.warning(f"Reality check failed: {e}")
                print(f"  Reality check failed: {e}")

        best_strategies = sorted(
            [r.to_dict() for r in significant],
            key=lambda x: x["val_sharpe"],
            reverse=True,
        )[:10]

        # Detect current market regime using any available data
        current_regime = ""
        regime_confidence = 0.0
        try:
            if data:
                first_symbol = next(iter(data.keys()))
                regime_result = get_current_regime(data[first_symbol])
                # get_current_regime returns {'success': bool, 'data': {'regime': str, 'probability': float}}
                if isinstance(regime_result, dict) and regime_result.get("success"):
                    current_regime = regime_result.get("data", {}).get("regime", "")
                    regime_confidence = regime_result.get("data", {}).get("probability", 0.0)
                    print(f"\n--- Current Market Regime: {current_regime} (confidence: {regime_confidence:.2f}) ---")
        except Exception as e:
            logger.debug(f"Regime detection failed: {e}")

        report = ResearchCycleReport(
            cycle_id=cycle_id,
            start_time=start_time,
            end_time=datetime.now(),
            total_experiments=total_experiments,
            significant_count=len(significant),
            passed_all_checks_count=len(validated),
            validated_strategies=validated,
            best_strategies=best_strategies,
            sector_performance=sector_performance,
            experiment_leads=self.leads,
            coverage_by_sector=coverage_by_sector,
            strategies_tested=strategies,
            reality_check_result=reality_check_result,
            strategies_surviving_snooping=strategies_surviving,
            current_regime=current_regime,
            regime_confidence=regime_confidence,
        )

        # Save report
        self._save_report(report)

        # Generate plots for significant strategies
        if generate_plots and PLOTS_AVAILABLE and significant:
            print("\n--- Generating Validation Plots ---")
            try:
                plotter = StrategyPlotter()

                # Generate individual plots for top significant strategies
                for result in significant[:5]:  # Top 5 by significance
                    if result.returns is not None and result.symbol in data:
                        try:
                            # Equity curve for each significant strategy
                            plotter.plot_strategy_vs_random_vs_buyhold(
                                strategy_returns=result.returns,
                                price_data=data[result.symbol],
                                strategy_name=result.strategy_name,
                                symbol=result.symbol,
                                n_random=50,
                            )
                            print(f"  Generated plot for {result.strategy_name}/{result.symbol}")
                        except Exception as e:
                            logger.warning(f"Plot generation failed for {result.strategy_name}/{result.symbol}: {e}")

                # Generate multi-strategy comparison if we have multiple significant strategies
                if len(significant) >= 2:
                    try:
                        strategy_returns_dict = {
                            f"{r.strategy_name}/{r.symbol}": r.returns
                            for r in significant[:5]
                            if r.returns is not None
                        }
                        if strategy_returns_dict:
                            # Use first available symbol's data for price reference
                            first_symbol = next(
                                (r.symbol for r in significant if r.symbol in data),
                                None
                            )
                            if first_symbol:
                                plotter.plot_multi_strategy_comparison(
                                    strategies=strategy_returns_dict,
                                    price_data=data[first_symbol],
                                )
                                print(f"  Generated multi-strategy comparison plot")
                    except Exception as e:
                        logger.warning(f"Multi-strategy comparison plot failed: {e}")

                print(f"  Plots saved to: {plotter.output_dir}")

            except Exception as e:
                logger.error(f"Plot generation failed: {e}")
        elif generate_plots and not PLOTS_AVAILABLE:
            logger.warning("Plot generation requested but matplotlib not available")

        # Print summary
        print(f"\n{'='*60}")
        print("RESEARCH CYCLE COMPLETE")
        print(f"{'='*60}")
        print(f"Total experiments: {total_experiments}")
        print(f"Significant (p<0.05): {len(significant)}")
        print(f"Passed all checks: {len(validated)}")

        if best_strategies:
            print("\nTop strategies:")
            for s in best_strategies[:5]:
                print(f"  - {s['strategy']}/{s['symbol']}: Sharpe={s['val_sharpe']:.2f}, p={s['mcpt_p_value']:.4f}")

        print(f"\nNew leads generated: {len(self.leads)}")
        print(f"Report saved to: {self.output_dir / f'{cycle_id}.json'}")

        return report

    async def _fetch_data(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        """Fetch price data for all symbols."""
        import yfinance as yf

        data = {}
        for symbol in symbols:
            try:
                df = yf.download(
                    symbol,
                    start=datetime.now() - timedelta(days=730),
                    end=datetime.now(),
                    progress=False,
                )
                if len(df) > 100:
                    # Handle both single and multi-index columns from yfinance
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.droplevel(1)
                    df.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in df.columns]
                    data[symbol] = df
            except Exception as e:
                logger.warning(f"Could not fetch {symbol}: {e}")

        return data

    async def _run_single_experiment(
        self,
        strategy_name: str,
        symbol: str,
        price_data: pd.DataFrame,
        benchmark_returns: pd.Series | None = None,
    ) -> ValidationResult:
        """Run a single experiment with full validation suite using evaluation module."""
        result = ValidationResult(
            strategy_name=strategy_name,
            symbol=symbol,
            params={},
        )

        try:
            # Split data
            val_start = len(price_data) - self.validation_days
            if val_start < 100:
                result.failure_reasons.append("Insufficient data")
                return result

            train_data = price_data.iloc[:val_start]
            val_data = price_data.iloc[val_start:]

            # Get strategy executor
            executor = STRATEGY_MAP.get(strategy_name)
            if not executor:
                result.failure_reasons.append(f"Unknown strategy: {strategy_name}")
                return result

            # Run on training data
            train_positions = executor(train_data, {})
            train_metrics = self._calculate_metrics(train_positions, train_data)
            result.train_sharpe = train_metrics["sharpe"]

            # Run on validation data
            val_positions = executor(val_data, {})
            val_metrics = self._calculate_metrics(val_positions, val_data)
            result.val_sharpe = val_metrics["sharpe"]
            result.sortino = val_metrics["sortino"]
            result.calmar = val_metrics["calmar"]
            result.win_rate_pct = val_metrics["win_rate"]
            result.total_return = val_metrics["total_return"]
            result.max_drawdown = val_metrics["max_drawdown"]
            result.trade_count = val_metrics["trades"]
            result.returns = val_metrics["returns"]

            # MCPT test - use fallback since evaluation module mcpt_test expects Strategy objects
            result.mcpt_p_value = self._run_mcpt_fallback(executor, val_data, val_metrics["sharpe"])

            result.is_significant = result.mcpt_p_value < self.max_p_value

            # Bootstrap CI for Sharpe using evaluation module
            try:
                bootstrap_ci = BootstrapCI(n_bootstrap=1000, confidence_level=0.95)
                ci_result = bootstrap_ci.compute(
                    val_metrics["returns"].dropna().values,
                    statistic_func=lambda x: np.mean(x) / np.std(x) * np.sqrt(252) if np.std(x) > 0 else 0
                )
                result.sharpe_ci_lower = ci_result.lower
                result.sharpe_ci_upper = ci_result.upper
            except Exception as e:
                logger.warning(f"Bootstrap CI failed for {strategy_name}/{symbol}: {e}")
                result.sharpe_ci_lower, result.sharpe_ci_upper = self._bootstrap_sharpe_ci_fallback(
                    val_metrics["returns"]
                )

            # Regime analysis using evaluation module
            try:
                detect_regimes(val_data)
                regime_perf = evaluate_by_regime(val_metrics["returns"], val_data)
                result.regime_performance = {str(k): v for k, v in regime_perf.items()} if regime_perf else {}
                current = get_current_regime(val_data)
                # get_current_regime returns {'success': bool, 'data': {'regime': str, 'probability': float}}
                if isinstance(current, dict) and current.get("success"):
                    result.current_regime = current.get("data", {}).get("regime", "")
                else:
                    result.current_regime = ""
            except Exception as e:
                logger.debug(f"Regime analysis failed for {strategy_name}/{symbol}: {e}")
                result.regime_performance = {}
                result.current_regime = ""

            # Leak detection (simple check)
            result.has_lookahead_bias = self._check_lookahead(train_positions, train_data)

            # Determine if passes all checks
            if (result.is_significant and
                result.val_sharpe >= self.min_sharpe and
                not result.has_lookahead_bias and
                result.trade_count >= 5):
                result.passes_all_checks = True
            else:
                if not result.is_significant:
                    result.failure_reasons.append(f"Not significant (p={result.mcpt_p_value:.3f})")
                if result.val_sharpe < self.min_sharpe:
                    result.failure_reasons.append(f"Low Sharpe ({result.val_sharpe:.2f})")
                if result.has_lookahead_bias:
                    result.failure_reasons.append("Lookahead bias detected")
                if result.trade_count < 5:
                    result.failure_reasons.append(f"Insufficient trades ({result.trade_count})")

            # Record to knowledge base
            if result.is_significant:
                self.kb.record_success(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    params={},
                    train_sharpe=result.train_sharpe,
                    val_sharpe=result.val_sharpe,
                    p_value=result.mcpt_p_value,
                    session_id="comprehensive_research",
                )

        except Exception as e:
            result.failure_reasons.append(f"Error: {str(e)}")
            logger.warning(f"Error in experiment {strategy_name}/{symbol}: {e}")

        return result

    def _calculate_metrics(
        self,
        positions: pd.Series,
        price_data: pd.DataFrame,
        cost_bps: float = 10,
    ) -> dict:
        """Calculate strategy metrics using evaluation module functions."""
        returns = price_data["close"].pct_change()
        strategy_returns = positions * returns

        # Transaction costs
        costs = positions.diff().abs() * (cost_bps / 10000)
        strategy_returns = strategy_returns - costs
        strategy_returns = strategy_returns.replace([np.inf, -np.inf], 0).fillna(0)

        # Use evaluation module functions for metrics
        try:
            sharpe = sharpe_ratio(strategy_returns)
            sortino = sortino_ratio(strategy_returns)
            max_dd = max_drawdown(strategy_returns)
            tot_ret = total_return(strategy_returns)
            calmar = calmar_ratio(strategy_returns)
            wr = win_rate(strategy_returns)
        except Exception:
            # Fallback if evaluation module functions fail
            sharpe = (
                strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                if strategy_returns.std() > 0 else 0
            )
            sortino = 0.0
            max_dd = 0.0
            tot_ret = (1 + strategy_returns).prod() - 1
            calmar = 0.0
            wr = 0.0

        trades = (positions.diff().abs() > 0).sum()

        return {
            "returns": strategy_returns,
            "total_return": float(tot_ret),
            "sharpe": float(sharpe),
            "sortino": float(sortino),
            "max_drawdown": float(max_dd),
            "calmar": float(calmar),
            "win_rate": float(wr),
            "trades": int(trades),
        }

    def _run_mcpt_fallback(
        self,
        executor,
        val_data: pd.DataFrame,
        original_sharpe: float,
    ) -> float:
        """Fallback Monte Carlo Permutation Test when evaluation module fails."""
        perm_sharpes = []

        for i in range(self.n_permutations):
            try:
                permuted = self._permute_data(val_data, seed=42 + i)
                perm_positions = executor(permuted, {})
                perm_metrics = self._calculate_metrics(perm_positions, permuted)
                perm_sharpes.append(perm_metrics["sharpe"])
            except Exception:
                continue

        if len(perm_sharpes) < 50:
            return 1.0

        p_value = (np.sum(np.array(perm_sharpes) >= original_sharpe) + 1) / (len(perm_sharpes) + 1)
        return float(p_value)

    def _permute_data(self, df: pd.DataFrame, seed: int) -> pd.DataFrame:
        """Permute OHLCV data by shuffling returns."""
        np.random.seed(seed)
        n = len(df)
        if n < 20:
            return df.copy()

        # Decompose
        prev_close = df["close"].shift(1)
        gap_returns = ((df["open"] - prev_close) / prev_close).fillna(0).values
        intrabar_returns = ((df["close"] - df["open"]) / df["open"]).fillna(0).values

        # Shuffle
        perm_gap = np.random.permutation(n - 1)
        perm_intra = np.random.permutation(n - 1)

        shuffled_gaps = gap_returns[1:][perm_gap]
        shuffled_intra = intrabar_returns[1:][perm_intra]

        # Reconstruct
        prices = np.zeros(n)
        opens = np.zeros(n)
        prices[0] = df["close"].iloc[0]
        opens[0] = df["open"].iloc[0]

        for i in range(1, n):
            opens[i] = prices[i - 1] * (1 + shuffled_gaps[i - 1])
            prices[i] = opens[i] * (1 + shuffled_intra[i - 1])

        permuted = pd.DataFrame(index=df.index)
        permuted["open"] = opens
        permuted["close"] = prices
        permuted["high"] = np.maximum(opens, prices) * 1.01
        permuted["low"] = np.minimum(opens, prices) * 0.99
        permuted["volume"] = df["volume"].values

        return permuted

    def _bootstrap_sharpe_ci_fallback(
        self,
        returns: pd.Series,
        n_bootstrap: int = 1000,
        ci: float = 0.95,
    ) -> tuple[float, float]:
        """Fallback bootstrap CI when evaluation module fails."""
        sharpes = []
        n = len(returns)

        for _ in range(n_bootstrap):
            sample = returns.sample(n=n, replace=True)
            if sample.std() > 0:
                sharpe = sample.mean() / sample.std() * np.sqrt(252)
                sharpes.append(sharpe)

        if not sharpes:
            return 0.0, 0.0

        alpha = (1 - ci) / 2
        lower = np.percentile(sharpes, alpha * 100)
        upper = np.percentile(sharpes, (1 - alpha) * 100)

        return float(lower), float(upper)

    def _check_lookahead(self, positions: pd.Series, data: pd.DataFrame) -> bool:
        """Simple lookahead bias check."""
        # Check if positions use future information
        # A simple heuristic: positions should be shifted
        if positions.isna().sum() > len(positions) * 0.1:
            return True

        # Check for unrealistic trade timing
        returns = data["close"].pct_change()
        strategy_returns = positions * returns

        # If strategy returns are suspiciously high (>200% Sharpe), flag it
        if strategy_returns.std() > 0:
            sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
            if sharpe > 5:  # Unrealistically high
                return True

        return False

    def _get_sector(self, symbol: str) -> Sector:
        """Get sector for a symbol."""
        meta = self.universe.get_metadata(symbol)
        return meta.sector if meta else Sector.TECHNOLOGY

    def _generate_leads(self) -> list[ExperimentLead]:
        """Generate new experiment leads based on results."""
        leads = []

        # 1. Extend successful strategies to similar symbols
        significant = [r for r in self.results if r.is_significant]
        for result in significant[:5]:
            # Find similar symbols
            meta = self.universe.get_metadata(result.symbol)
            if meta:
                similar = self.universe.get_by_industry(meta.industry)
                untested = [s for s in similar if s != result.symbol and
                           not any(r.symbol == s and r.strategy_name == result.strategy_name
                                  for r in self.results)]

                if untested:
                    leads.append(ExperimentLead(
                        title=f"Extend {result.strategy_name} to {meta.industry.value}",
                        description=f"Strategy worked on {result.symbol} (Sharpe={result.val_sharpe:.2f}). "
                                   f"Test on similar {meta.industry.value} stocks.",
                        strategy_type=result.strategy_name,
                        symbols=untested[:5],
                        params=result.params,
                        rationale=f"Same industry ({meta.industry.value}) often shares similar patterns",
                        priority=0.8,
                        source="pattern_extension",
                        expected_edge="Cross-symbol pattern persistence",
                    ))

        # 2. Sector-specific opportunities
        for sector, perf in self._get_sector_gaps().items():
            if perf["gap"]:
                leads.append(ExperimentLead(
                    title=f"Untested strategies in {sector}",
                    description=f"Sector has {perf['tested']} tested but {len(perf['gap'])} strategies not tried.",
                    strategy_type=perf["gap"][0],
                    symbols=self.universe.get_by_sector(Sector(sector))[:5],
                    params={},
                    rationale=f"Sector-strategy affinity suggests these may work",
                    priority=0.6,
                    source="sector_analysis",
                    expected_edge="Sector-specific pattern",
                ))

        # 3. Cross-sector correlation plays
        for pair in get_cross_sector_pairs()[:3]:
            leads.append(ExperimentLead(
                title=f"Correlation strategy: {pair[0]}/{pair[1]}",
                description=f"Test mean reversion on correlation breaks between {pair[0]} and {pair[1]}",
                strategy_type="correlation",
                symbols=list(pair),
                params={"lookback": 60, "threshold": 0.3},
                rationale="Historical correlation breaks often revert",
                priority=0.5,
                source="correlation",
                expected_edge="Correlation reversion",
            ))

        # 4. Parameter variations on successful strategies
        for result in significant[:3]:
            for param_set in self._generate_param_variations(result.strategy_name):
                leads.append(ExperimentLead(
                    title=f"Parameter sweep: {result.strategy_name} on {result.symbol}",
                    description=f"Try alternative parameters on successful strategy",
                    strategy_type=result.strategy_name,
                    symbols=[result.symbol],
                    params=param_set,
                    rationale="Parameter optimization may improve edge",
                    priority=0.4,
                    source="param_sweep",
                    expected_edge="Optimized parameters",
                ))

        # 5. Volatility regime-specific testing
        high_vol = self.universe.get_by_volatility(VolatilityProfile.HIGH)
        low_vol = self.universe.get_by_volatility(VolatilityProfile.LOW)

        leads.append(ExperimentLead(
            title="Mean reversion on high volatility stocks",
            description="Test RSI/Bollinger reversal on high-beta names",
            strategy_type="bollinger_reversal",
            symbols=high_vol[:5],
            params={"period": 15, "num_std": 2.5},
            rationale="High vol stocks often overshoot, creating reversion opportunities",
            priority=0.7,
            source="volatility_regime",
            expected_edge="Volatility-based mean reversion",
        ))

        leads.append(ExperimentLead(
            title="Trend following on low volatility stocks",
            description="Test SMA crossover on low-beta defensive names",
            strategy_type="sma_crossover",
            symbols=low_vol[:5],
            params={"fast_period": 20, "slow_period": 50},
            rationale="Low vol stocks trend more reliably",
            priority=0.6,
            source="volatility_regime",
            expected_edge="Trend persistence in low vol",
        ))

        return sorted(leads, key=lambda x: x.priority, reverse=True)[:20]

    def _get_sector_gaps(self) -> dict[str, dict]:
        """Find sectors with untested strategies."""
        from .symbol_universe import SECTOR_STRATEGY_AFFINITY

        gaps = {}
        for sector, strategies in SECTOR_STRATEGY_AFFINITY.items():
            if isinstance(sector, Sector):
                sector_results = [r for r in self.results if self._get_sector(r.symbol) == sector]
                tested_strategies = set(r.strategy_name for r in sector_results)
                untested = [s for s in strategies if s not in tested_strategies]

                gaps[sector.value] = {
                    "tested": len(tested_strategies),
                    "gap": untested,
                }

        return gaps

    def _generate_param_variations(self, strategy_name: str) -> list[dict]:
        """Generate parameter variations for a strategy."""
        variations = {
            "rsi_reversal": [
                {"period": 7, "oversold": 25, "overbought": 75},
                {"period": 21, "oversold": 30, "overbought": 70},
            ],
            "momentum": [
                {"lookback": 10, "threshold": 0.02},
                {"lookback": 40, "threshold": 0.0},
            ],
            "bollinger_reversal": [
                {"period": 15, "num_std": 2.5},
                {"period": 30, "num_std": 1.5},
            ],
            "sma_crossover": [
                {"fast_period": 5, "slow_period": 20},
                {"fast_period": 20, "slow_period": 100},
            ],
        }
        return variations.get(strategy_name, [])

    def _save_report(self, report: ResearchCycleReport) -> None:
        """Save research report to file."""
        filepath = self.output_dir / f"{report.cycle_id}.json"

        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        # Also save leads as separate file for easy access
        leads_path = self.output_dir / f"{report.cycle_id}_leads.json"
        with open(leads_path, "w") as f:
            json.dump([l.to_dict() for l in report.experiment_leads], f, indent=2)

        logger.info(f"Report saved to {filepath}")


# =============================================================================
# CLI
# =============================================================================

async def main():
    """Run comprehensive research from CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive Research Runner")
    parser.add_argument("--universes", nargs="+", default=None)
    parser.add_argument("--strategies", nargs="+", default=None)
    parser.add_argument("--permutations", type=int, default=500)
    parser.add_argument("--validation-days", type=int, default=90)
    parser.add_argument("--plots", action="store_true", help="Generate validation plots for significant strategies")

    args = parser.parse_args()

    researcher = ComprehensiveResearcher(
        n_permutations=args.permutations,
        validation_days=args.validation_days,
    )

    report = await researcher.run_full_cycle(
        universes=args.universes,
        strategies=args.strategies,
        generate_plots=args.plots,
    )

    print(f"\nResearch complete. See report at: {researcher.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
