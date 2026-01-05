#!/usr/bin/env python3
"""
Multi-Horizon Strategy Research

Evaluates strategies across multiple time horizons with focus on recent data
for paper trading readiness.

Usage:
    PYTHONPATH=. python scripts/multi_horizon_research.py --quick
    PYTHONPATH=. python scripts/multi_horizon_research.py --full --plots
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Time horizons to test
TIME_HORIZONS = {
    "30d": 30,
    "60d": 60,
    "90d": 90,
    "180d": 180,
    "1y": 365,
    "2y": 730,
}

# Strategies to test
STRATEGIES = [
    "bollinger_reversal",
    "momentum",
    "rsi_reversal",
    "breakout",
    "sma_crossover",
    "volatility_breakout",
]

# Symbols by category
SYMBOL_UNIVERSES = {
    "tech_mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"],
    "semiconductors": ["AMD", "QCOM", "MU", "MRVL", "AVGO", "INTC"],
    "etfs": ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF"],
    "high_volatility": ["TSLA", "COIN", "ARKK", "MSTR"],
}


@dataclass
class HorizonResult:
    """Result for a single time horizon."""
    horizon: str
    days: int
    sharpe: float
    total_return: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    p_value: float
    is_significant: bool


@dataclass
class StrategyEvaluation:
    """Complete evaluation across all horizons."""
    strategy: str
    symbol: str
    evaluated_at: str
    horizons: list[HorizonResult] = field(default_factory=list)

    # Recent performance focus
    recent_30d_sharpe: float = 0.0
    recent_60d_sharpe: float = 0.0
    recent_90d_sharpe: float = 0.0

    # Long-term validation
    full_period_sharpe: float = 0.0
    full_period_p_value: float = 1.0

    # PDT compliance
    pdt_best_holding: int = 2
    pdt_sharpe: float = 0.0

    # Recommendation
    paper_trading_ready: bool = False
    recommendation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "evaluated_at": self.evaluated_at,
            "horizons": [asdict(h) for h in self.horizons],
            "recent_30d_sharpe": self.recent_30d_sharpe,
            "recent_60d_sharpe": self.recent_60d_sharpe,
            "recent_90d_sharpe": self.recent_90d_sharpe,
            "full_period_sharpe": self.full_period_sharpe,
            "full_period_p_value": self.full_period_p_value,
            "pdt_best_holding": self.pdt_best_holding,
            "pdt_sharpe": self.pdt_sharpe,
            "paper_trading_ready": self.paper_trading_ready,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
        }


def get_strategy_signals(strategy_name: str, data: pd.DataFrame) -> pd.Series:
    """Generate signals for a strategy."""
    prices = data['Close'] if 'Close' in data.columns else data['close']

    if strategy_name == 'bollinger_reversal':
        sma = prices.rolling(20).mean()
        std = prices.rolling(20).std()
        lower = sma - 2 * std
        upper = sma + 2 * std
        signals = pd.Series(0, index=prices.index)
        signals[prices < lower] = 1
        signals[prices > upper] = -1

    elif strategy_name == 'momentum':
        mom = prices.pct_change(20)
        signals = pd.Series(0, index=prices.index)
        signals[mom > 0.05] = 1
        signals[mom < -0.05] = -1

    elif strategy_name == 'rsi_reversal':
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        signals = pd.Series(0, index=prices.index)
        signals[rsi < 30] = 1
        signals[rsi > 70] = -1

    elif strategy_name == 'breakout':
        high_20 = prices.rolling(20).max()
        low_20 = prices.rolling(20).min()
        signals = pd.Series(0, index=prices.index)
        signals[prices >= high_20.shift(1)] = 1
        signals[prices <= low_20.shift(1)] = -1

    elif strategy_name == 'sma_crossover':
        fast_ma = prices.rolling(10).mean()
        slow_ma = prices.rolling(30).mean()
        signals = pd.Series(0, index=prices.index)
        signals[fast_ma > slow_ma] = 1
        signals[fast_ma < slow_ma] = -1

    elif strategy_name == 'volatility_breakout':
        tr = pd.concat([
            prices.rolling(1).max() - prices.rolling(1).min(),
            (prices - prices.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        upper = prices.shift(1) + 1.5 * atr.shift(1)
        lower = prices.shift(1) - 1.5 * atr.shift(1)
        signals = pd.Series(0, index=prices.index)
        signals[prices > upper] = 1
        signals[prices < lower] = -1

    else:
        # Default momentum
        mom = prices.pct_change(10)
        signals = pd.Series(0, index=prices.index)
        signals[mom > 0.03] = 1
        signals[mom < -0.03] = -1

    return signals.shift(1).fillna(0)


def calculate_metrics(signals: pd.Series, prices: pd.Series, cost_bps: float = 10) -> dict:
    """Calculate strategy metrics."""
    returns = prices.pct_change()
    strategy_returns = signals * returns

    # Transaction costs
    costs = signals.diff().abs() * (cost_bps / 10000)
    strategy_returns = strategy_returns - costs
    strategy_returns = strategy_returns.replace([np.inf, -np.inf], 0).fillna(0)

    if len(strategy_returns) < 20 or strategy_returns.std() == 0:
        return {
            "sharpe": 0,
            "total_return": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "trade_count": 0,
            "returns": strategy_returns,
        }

    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
    total_return = (1 + strategy_returns).prod() - 1

    # Max drawdown
    cum_returns = (1 + strategy_returns).cumprod()
    rolling_max = cum_returns.cummax()
    drawdown = (cum_returns - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Win rate
    winning = (strategy_returns > 0).sum()
    total_trades = (strategy_returns != 0).sum()
    win_rate = winning / total_trades if total_trades > 0 else 0

    # Trade count
    trade_count = (signals.diff().abs() > 0).sum()

    return {
        "sharpe": float(sharpe),
        "total_return": float(total_return),
        "max_drawdown": float(max_drawdown),
        "win_rate": float(win_rate),
        "trade_count": int(trade_count),
        "returns": strategy_returns,
    }


def run_mcpt(strategy_returns: pd.Series, n_permutations: int = 100) -> tuple[float, float]:
    """Quick MCPT test."""
    if len(strategy_returns) < 30:
        return 1.0, 0.0

    original_sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0

    abs_returns = np.abs(strategy_returns.values)
    n = len(abs_returns)

    count_better = 0
    for _ in range(n_permutations):
        random_signs = np.random.choice([-1, 1], size=n)
        perm_returns = abs_returns * random_signs
        perm_sharpe = np.mean(perm_returns) / np.std(perm_returns) * np.sqrt(252) if np.std(perm_returns) > 0 else 0
        if perm_sharpe >= original_sharpe:
            count_better += 1

    p_value = (count_better + 1) / (n_permutations + 1)
    return p_value, original_sharpe


def test_pdt_holding(signals: pd.Series, prices: pd.Series, hold_days: int) -> float:
    """Test with specific holding period."""
    if hold_days == 0:
        held_signals = signals
    else:
        held_signals = signals.copy()
        position = 0
        hold_counter = 0

        for i in range(len(signals)):
            if hold_counter > 0:
                held_signals.iloc[i] = position
                hold_counter -= 1
            elif signals.iloc[i] != 0 and signals.iloc[i] != position:
                position = signals.iloc[i]
                hold_counter = hold_days
                held_signals.iloc[i] = position
            else:
                held_signals.iloc[i] = position

    returns = prices.pct_change()
    strat_returns = held_signals.shift(1).fillna(0) * returns
    strat_returns = strat_returns.dropna()

    if len(strat_returns) < 20 or strat_returns.std() == 0:
        return 0.0

    return strat_returns.mean() / strat_returns.std() * np.sqrt(252)


def evaluate_single_horizon(
    strategy: str,
    symbol: str,
    data: pd.DataFrame,
    horizon_name: str,
    horizon_days: int,
    n_permutations: int = 100,
) -> HorizonResult | None:
    """Evaluate strategy on a single time horizon."""
    try:
        # Get recent data for this horizon
        actual_days = min(len(data), horizon_days)
        if actual_days < 30:  # Need at least 30 days
            return None

        horizon_data = data.iloc[-actual_days:].copy()
        prices = horizon_data['Close'] if 'Close' in horizon_data.columns else horizon_data['close']

        if len(prices) < 30:
            return None

        # Generate signals on full horizon data
        signals = get_strategy_signals(strategy, horizon_data)

        # Calculate metrics
        metrics = calculate_metrics(signals, prices)

        # Quick MCPT
        p_value, _ = run_mcpt(metrics["returns"], n_permutations)

        return HorizonResult(
            horizon=horizon_name,
            days=actual_days,
            sharpe=metrics["sharpe"],
            total_return=metrics["total_return"],
            max_drawdown=metrics["max_drawdown"],
            win_rate=metrics["win_rate"],
            trade_count=metrics["trade_count"],
            p_value=p_value,
            is_significant=p_value < 0.10,  # Slightly relaxed for quick evaluation
        )

    except Exception as e:
        logger.warning(f"Error evaluating {strategy}/{symbol} on {horizon_name}: {e}")
        return None


def evaluate_strategy_symbol(
    strategy: str,
    symbol: str,
    data: pd.DataFrame,
    n_permutations: int = 100,
) -> StrategyEvaluation:
    """Full multi-horizon evaluation for a strategy/symbol pair."""
    evaluation = StrategyEvaluation(
        strategy=strategy,
        symbol=symbol,
        evaluated_at=datetime.now().isoformat(),
    )

    prices = data['Close'] if 'Close' in data.columns else data['close']

    # Evaluate each time horizon
    for horizon_name, horizon_days in TIME_HORIZONS.items():
        result = evaluate_single_horizon(
            strategy, symbol, data, horizon_name, horizon_days, n_permutations
        )
        if result:
            evaluation.horizons.append(result)

            # Store recent performance
            if horizon_name == "30d":
                evaluation.recent_30d_sharpe = result.sharpe
            elif horizon_name == "60d":
                evaluation.recent_60d_sharpe = result.sharpe
            elif horizon_name == "90d":
                evaluation.recent_90d_sharpe = result.sharpe
            elif horizon_name == "2y":
                evaluation.full_period_sharpe = result.sharpe
                evaluation.full_period_p_value = result.p_value

    # PDT holding period optimization on full data
    signals = get_strategy_signals(strategy, data)
    best_pdt_sharpe = 0
    best_pdt_hold = 2

    for hold_days in [2, 3, 5, 7, 10]:
        sharpe = test_pdt_holding(signals, prices, hold_days)
        if sharpe > best_pdt_sharpe:
            best_pdt_sharpe = sharpe
            best_pdt_hold = hold_days

    evaluation.pdt_best_holding = best_pdt_hold
    evaluation.pdt_sharpe = best_pdt_sharpe

    # Determine paper trading readiness
    # Criteria (relaxed for paper trading testing):
    # 1. Recent 60d Sharpe > 1.0 (strong recent performance)
    # 2. PDT-compliant Sharpe > 0.5
    # OR
    # 1. Recent 60d Sharpe > 0 AND PDT Sharpe > 0.8

    strong_recent = evaluation.recent_60d_sharpe > 1.0
    decent_recent = evaluation.recent_60d_sharpe > 0
    good_pdt = evaluation.pdt_sharpe > 0.5
    strong_pdt = evaluation.pdt_sharpe > 0.8

    if strong_recent and good_pdt:
        evaluation.paper_trading_ready = True
        evaluation.recommendation = "READY"
        evaluation.confidence = min(1.0, (
            0.4 * min(evaluation.recent_60d_sharpe / 3, 1) +
            0.3 * min(evaluation.pdt_sharpe / 2, 1) +
            0.3 * (1 if evaluation.recent_30d_sharpe > 0 else 0)
        ))
    elif decent_recent and strong_pdt:
        evaluation.paper_trading_ready = True
        evaluation.recommendation = "READY"
        evaluation.confidence = min(0.7, (
            0.3 * min(evaluation.recent_60d_sharpe / 2, 1) +
            0.5 * min(evaluation.pdt_sharpe / 2, 1) +
            0.2 * (1 if evaluation.recent_30d_sharpe > 0 else 0)
        ))
    elif decent_recent and good_pdt:
        evaluation.paper_trading_ready = False
        evaluation.recommendation = "MONITOR"
        evaluation.confidence = 0.4
    elif strong_pdt:
        evaluation.paper_trading_ready = False
        evaluation.recommendation = "MONITOR"
        evaluation.confidence = 0.3
    else:
        evaluation.paper_trading_ready = False
        evaluation.recommendation = "SKIP"
        evaluation.confidence = 0.0

    return evaluation


def fetch_data(symbols: list[str], days: int = 730) -> dict[str, pd.DataFrame]:
    """Fetch data for all symbols."""
    data = {}
    for symbol in symbols:
        try:
            df = yf.download(
                symbol,
                start=datetime.now() - timedelta(days=days),
                end=datetime.now(),
                progress=False,
            )
            if len(df) > 100:
                # Handle multi-index columns from yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                data[symbol] = df
        except Exception as e:
            logger.warning(f"Could not fetch {symbol}: {e}")
    return data


def run_multi_horizon_research(
    universes: list[str] | None = None,
    strategies: list[str] | None = None,
    quick: bool = False,
    generate_plots: bool = False,
) -> dict:
    """Run full multi-horizon research cycle."""

    print(f"\n{'='*70}")
    print("MULTI-HORIZON STRATEGY RESEARCH")
    print(f"Focus: Paper Trading Readiness for {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*70}\n")

    # Setup
    universes = universes or list(SYMBOL_UNIVERSES.keys())
    strategies = strategies or STRATEGIES
    n_permutations = 50 if quick else 200

    # Collect symbols
    all_symbols = set()
    for uni in universes:
        if uni in SYMBOL_UNIVERSES:
            all_symbols.update(SYMBOL_UNIVERSES[uni])

    print(f"Testing {len(strategies)} strategies on {len(all_symbols)} symbols")
    print(f"Time horizons: {list(TIME_HORIZONS.keys())}")
    print(f"Permutations: {n_permutations}")
    print()

    # Fetch data
    print("Fetching data...")
    data = fetch_data(list(all_symbols))
    print(f"  Loaded {len(data)} symbols\n")

    # Run evaluations in parallel
    evaluations: list[StrategyEvaluation] = []
    total_tests = len(strategies) * len(data)
    completed = 0

    print("Running multi-horizon evaluations...")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}

        for strategy in strategies:
            for symbol, df in data.items():
                future = executor.submit(
                    evaluate_strategy_symbol,
                    strategy, symbol, df, n_permutations
                )
                futures[future] = (strategy, symbol)

        for future in as_completed(futures):
            strategy, symbol = futures[future]
            completed += 1

            try:
                result = future.result()
                evaluations.append(result)

                # Print progress
                status = "READY" if result.paper_trading_ready else "skip"
                recent = result.recent_60d_sharpe
                full = result.full_period_sharpe
                print(f"  [{completed}/{total_tests}] {strategy}/{symbol}: "
                      f"60d={recent:.2f}, 2y={full:.2f}, pdt={result.pdt_sharpe:.2f} [{status}]")

            except Exception as e:
                logger.error(f"Error in {strategy}/{symbol}: {e}")

    # Compile results
    ready_strategies = [e for e in evaluations if e.paper_trading_ready]
    monitor_strategies = [e for e in evaluations if e.recommendation == "MONITOR"]

    # Sort by confidence
    ready_strategies.sort(key=lambda x: x.confidence, reverse=True)
    monitor_strategies.sort(key=lambda x: x.pdt_sharpe, reverse=True)

    # Generate plots for top strategies
    if generate_plots and ready_strategies:
        try:
            from workflows.visualizations.strategy_plots import StrategyPlotter

            print("\n--- Generating Plots ---")
            plotter = StrategyPlotter()

            for eval_result in ready_strategies[:5]:
                if eval_result.symbol in data:
                    df = data[eval_result.symbol]
                    prices = df['Close'] if 'Close' in df.columns else df['close']
                    signals = get_strategy_signals(eval_result.strategy, df)
                    returns = signals * prices.pct_change()

                    plotter.plot_strategy_vs_random_vs_buyhold(
                        strategy_returns=returns,
                        price_data=df,
                        strategy_name=eval_result.strategy,
                        symbol=eval_result.symbol,
                        n_random=50,
                    )
                    print(f"  Generated plot for {eval_result.strategy}/{eval_result.symbol}")

            print(f"  Plots saved to: {plotter.output_dir}")
        except Exception as e:
            logger.warning(f"Plot generation failed: {e}")

    # Print summary
    print(f"\n{'='*70}")
    print("RESEARCH RESULTS")
    print(f"{'='*70}")
    print(f"Total evaluations: {len(evaluations)}")
    print(f"Paper trading ready: {len(ready_strategies)}")
    print(f"Monitor (close): {len(monitor_strategies)}")

    if ready_strategies:
        print(f"\n--- READY FOR PAPER TRADING (Top 10) ---")
        print(f"{'Strategy':<20} {'Symbol':<8} {'30d':<8} {'60d':<8} {'90d':<8} {'2y':<8} {'PDT':<8} {'Conf':<6}")
        print("-" * 80)
        for e in ready_strategies[:10]:
            print(f"{e.strategy:<20} {e.symbol:<8} "
                  f"{e.recent_30d_sharpe:>7.2f} {e.recent_60d_sharpe:>7.2f} "
                  f"{e.recent_90d_sharpe:>7.2f} {e.full_period_sharpe:>7.2f} "
                  f"{e.pdt_sharpe:>7.2f} {e.confidence:>5.2f}")

    if monitor_strategies:
        print(f"\n--- MONITOR (May become ready) ---")
        for e in monitor_strategies[:5]:
            print(f"  {e.strategy}/{e.symbol}: 60d={e.recent_60d_sharpe:.2f}, pdt={e.pdt_sharpe:.2f}")

    # Horizon analysis
    print(f"\n--- PERFORMANCE BY TIME HORIZON ---")
    horizon_stats = {}
    for horizon in TIME_HORIZONS.keys():
        sharpes = []
        for e in evaluations:
            for h in e.horizons:
                if h.horizon == horizon:
                    sharpes.append(h.sharpe)
        if sharpes:
            horizon_stats[horizon] = {
                "mean": np.mean(sharpes),
                "median": np.median(sharpes),
                "std": np.std(sharpes),
                "positive_pct": sum(1 for s in sharpes if s > 0) / len(sharpes) * 100,
            }

    print(f"{'Horizon':<10} {'Mean':<10} {'Median':<10} {'Std':<10} {'%Positive':<10}")
    print("-" * 50)
    for horizon, stats in horizon_stats.items():
        print(f"{horizon:<10} {stats['mean']:>9.2f} {stats['median']:>9.2f} "
              f"{stats['std']:>9.2f} {stats['positive_pct']:>9.1f}%")

    # Paper trading recommendations
    print(f"\n{'='*70}")
    print("PAPER TRADING RECOMMENDATIONS FOR TOMORROW")
    print(f"{'='*70}")

    if ready_strategies:
        print("\nTop 5 strategies to deploy:")
        for i, e in enumerate(ready_strategies[:5], 1):
            print(f"\n{i}. {e.strategy} on {e.symbol}")
            print(f"   PDT Hold: {e.pdt_best_holding} days")
            print(f"   Recent Performance: 30d={e.recent_30d_sharpe:.2f}, 60d={e.recent_60d_sharpe:.2f}")
            print(f"   Full Period: Sharpe={e.full_period_sharpe:.2f}, p={e.full_period_p_value:.3f}")
            print(f"   Confidence: {e.confidence:.1%}")
    else:
        print("\nNo strategies currently meet all criteria for paper trading.")
        print("Consider the MONITOR strategies or adjust criteria.")

    # Save results
    output_dir = Path.home() / "quant_results" / "multi_horizon_research"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "universes": universes,
            "strategies": strategies,
            "n_permutations": n_permutations,
            "time_horizons": list(TIME_HORIZONS.keys()),
        },
        "summary": {
            "total_evaluations": len(evaluations),
            "ready_count": len(ready_strategies),
            "monitor_count": len(monitor_strategies),
        },
        "ready_strategies": [e.to_dict() for e in ready_strategies],
        "monitor_strategies": [e.to_dict() for e in monitor_strategies[:10]],
        "horizon_stats": horizon_stats,
        "all_evaluations": [e.to_dict() for e in evaluations],
    }

    filename = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_dir / filename, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_dir / filename}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Multi-Horizon Strategy Research")
    parser.add_argument("--universes", nargs="+", default=None, help="Symbol universes to test")
    parser.add_argument("--strategies", nargs="+", default=None, help="Strategies to test")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer permutations)")
    parser.add_argument("--full", action="store_true", help="Full mode (more permutations)")
    parser.add_argument("--plots", action="store_true", help="Generate plots for top strategies")

    args = parser.parse_args()

    quick = args.quick and not args.full

    run_multi_horizon_research(
        universes=args.universes,
        strategies=args.strategies,
        quick=quick,
        generate_plots=args.plots,
    )


if __name__ == "__main__":
    main()
