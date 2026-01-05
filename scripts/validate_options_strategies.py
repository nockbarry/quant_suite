#!/usr/bin/env python3
"""
Validate Options Strategies Historically

Tests Venezuela thesis options strategies across multiple historical periods
to validate expected performance.

Usage:
    PYTHONPATH=. python scripts/validate_options_strategies.py
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.backtest.options_backtest import (
    BacktestResult,
    OptionsBacktester,
    StrategyType,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/home/nock/quant_results/options_validation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_multi_period_validation(
    backtester: OptionsBacktester,
    symbol: str,
    strategy_func: callable,
    strategy_name: str,
    start_year: int = 2023,
    end_year: int = 2025,
    interval_days: int = 30,
) -> list[BacktestResult]:
    """Run strategy across multiple historical entry points."""
    results = []

    current_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)

    while current_date < end_date:
        try:
            result = strategy_func(symbol, current_date)
            results.append(result)
            logger.debug(f"{symbol} {strategy_name} {current_date.strftime('%Y-%m-%d')}: {result.total_return:.1%}")
        except Exception as e:
            logger.debug(f"Failed {current_date}: {e}")

        current_date += timedelta(days=interval_days)

    return results


def analyze_results(results: list[BacktestResult], strategy_name: str) -> dict:
    """Analyze backtest results and generate statistics."""
    if not results:
        return {"error": "No results"}

    returns = [r.total_return for r in results]
    wins = [r for r in results if r.total_return > 0]
    losses = [r for r in results if r.total_return <= 0]

    # Risk metrics
    returns_array = np.array(returns)
    sharpe = np.mean(returns_array) / np.std(returns_array) * np.sqrt(12) if np.std(returns_array) > 0 else 0

    stats = {
        "strategy": strategy_name,
        "total_trades": len(results),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(results) if results else 0,
        "avg_return": np.mean(returns),
        "median_return": np.median(returns),
        "std_return": np.std(returns),
        "max_return": np.max(returns),
        "min_return": np.min(returns),
        "avg_win": np.mean([r.total_return for r in wins]) if wins else 0,
        "avg_loss": np.mean([r.total_return for r in losses]) if losses else 0,
        "profit_factor": abs(sum(r.total_return for r in wins) / sum(r.total_return for r in losses)) if losses and sum(r.total_return for r in losses) != 0 else float('inf'),
        "sharpe_ratio": sharpe,
        "avg_days_held": np.mean([r.days_held for r in results]),
    }

    # Exit reason breakdown
    exit_reasons = {}
    for r in results:
        exit_reasons[r.exit_reason] = exit_reasons.get(r.exit_reason, 0) + 1
    stats["exit_reasons"] = exit_reasons

    return stats


def run_venezuela_thesis_validation():
    """
    Run comprehensive validation of Venezuela thesis options strategies.

    Tests:
    1. Multiple entry dates across 2023-2025
    2. Different IV scenarios (normal, event, earnings)
    3. All strategy types
    4. Multiple symbols
    """
    backtester = OptionsBacktester()

    # Venezuela thesis symbols
    symbols = ["SLB", "VLO", "HAL", "XLE"]

    # Strategy configurations
    strategies = {
        "diagonal_spread_normal": lambda s, d: backtester.backtest_diagonal_spread(s, d, iv_scenario="normal"),
        "diagonal_spread_event": lambda s, d: backtester.backtest_diagonal_spread(s, d, iv_scenario="event"),
        "calendar_spread": lambda s, d: backtester.backtest_calendar_spread(s, d),
        "iron_condor_event": lambda s, d: backtester.backtest_iron_condor(s, d, iv_scenario="event"),
    }

    all_results = {}
    all_stats = []

    print("\n" + "=" * 80)
    print("VENEZUELA THESIS OPTIONS STRATEGY VALIDATION")
    print(f"Testing: {', '.join(symbols)}")
    print(f"Period: 2023-2025")
    print("=" * 80)

    for symbol in symbols:
        print(f"\n### {symbol} ###")
        all_results[symbol] = {}

        for strategy_name, strategy_func in strategies.items():
            logger.info(f"Testing {symbol} {strategy_name}...")

            results = run_multi_period_validation(
                backtester,
                symbol,
                strategy_func,
                strategy_name,
                start_year=2023,
                end_year=2025,
                interval_days=30,
            )

            if results:
                stats = analyze_results(results, strategy_name)
                stats["symbol"] = symbol
                all_stats.append(stats)
                all_results[symbol][strategy_name] = results

                print(f"  {strategy_name}: {stats['win_rate']:.0%} win rate, "
                      f"{stats['avg_return']:+.1%} avg return, "
                      f"{stats['total_trades']} trades")

    # Summary table
    print("\n" + "=" * 80)
    print("STRATEGY PERFORMANCE SUMMARY")
    print("=" * 80)

    print(f"\n{'Symbol':<6} {'Strategy':<25} {'Win%':<8} {'Avg Ret':<10} {'Sharpe':<8} {'Trades':<8}")
    print("-" * 80)

    for stats in sorted(all_stats, key=lambda x: x['avg_return'], reverse=True):
        print(f"{stats['symbol']:<6} {stats['strategy']:<25} "
              f"{stats['win_rate']:.0%}     {stats['avg_return']:+.1%}      "
              f"{stats['sharpe_ratio']:.2f}     {stats['total_trades']}")

    # Best strategies
    print("\n" + "=" * 80)
    print("TOP PERFORMING STRATEGIES (by avg return)")
    print("=" * 80)

    top_strategies = sorted(all_stats, key=lambda x: x['avg_return'], reverse=True)[:5]
    for i, stats in enumerate(top_strategies, 1):
        print(f"\n{i}. {stats['symbol']} {stats['strategy']}")
        print(f"   Avg Return: {stats['avg_return']:+.1%}")
        print(f"   Win Rate: {stats['win_rate']:.0%}")
        print(f"   Sharpe Ratio: {stats['sharpe_ratio']:.2f}")
        print(f"   Profit Factor: {stats['profit_factor']:.2f}")
        print(f"   Avg Days Held: {stats['avg_days_held']:.0f}")

    # Most consistent strategies (highest win rate)
    print("\n" + "=" * 80)
    print("MOST CONSISTENT STRATEGIES (by win rate)")
    print("=" * 80)

    consistent_strategies = sorted(all_stats, key=lambda x: x['win_rate'], reverse=True)[:5]
    for i, stats in enumerate(consistent_strategies, 1):
        print(f"\n{i}. {stats['symbol']} {stats['strategy']}")
        print(f"   Win Rate: {stats['win_rate']:.0%}")
        print(f"   Avg Return: {stats['avg_return']:+.1%}")
        print(f"   Trades: {stats['total_trades']}")

    # Strategy type analysis
    print("\n" + "=" * 80)
    print("STRATEGY TYPE ANALYSIS (aggregated across symbols)")
    print("=" * 80)

    strategy_types = {}
    for stats in all_stats:
        stype = stats['strategy']
        if stype not in strategy_types:
            strategy_types[stype] = []
        strategy_types[stype].append(stats)

    for stype, type_stats in strategy_types.items():
        avg_return = np.mean([s['avg_return'] for s in type_stats])
        avg_win_rate = np.mean([s['win_rate'] for s in type_stats])
        total_trades = sum([s['total_trades'] for s in type_stats])

        print(f"\n{stype}:")
        print(f"  Avg Return: {avg_return:+.1%}")
        print(f"  Avg Win Rate: {avg_win_rate:.0%}")
        print(f"  Total Trades: {total_trades}")

    # Save results
    output_file = OUTPUT_DIR / "validation_results.json"
    with open(output_file, "w") as f:
        json.dump(all_stats, f, indent=2, default=str)
    logger.info(f"Saved results to {output_file}")

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR VENEZUELA THESIS")
    print("=" * 80)

    # Find best by symbol
    best_by_symbol = {}
    for stats in all_stats:
        symbol = stats['symbol']
        if symbol not in best_by_symbol or stats['avg_return'] > best_by_symbol[symbol]['avg_return']:
            best_by_symbol[symbol] = stats

    for symbol, stats in best_by_symbol.items():
        print(f"\n{symbol}: Use {stats['strategy']}")
        print(f"  Expected Return: {stats['avg_return']:+.1%}")
        print(f"  Win Rate: {stats['win_rate']:.0%}")

    return all_stats


def run_geopolitical_event_simulation():
    """
    Simulate options performance during a geopolitical event.

    Models the Venezuela/Maduro capture scenario:
    - Day 0: Event occurs, IV spikes 40%
    - Days 1-21: IV gradually normalizes
    - Stock moves based on thesis (SLB +20%, VLO +15%)
    """
    from src.evaluation.backtest.options_pricer import IVModel, Option, OptionType, OptionsPricer

    print("\n" + "=" * 80)
    print("GEOPOLITICAL EVENT SIMULATION: VENEZUELA SCENARIO")
    print("=" * 80)

    pricer = OptionsPricer()
    iv_model = IVModel(base_iv=0.30)

    # Simulation parameters
    initial_spot = 40.0  # SLB-like price
    base_iv = 0.30
    event_spike = 0.40  # 40% IV spike
    days_to_simulate = 60

    # Generate IV path (event on day 5)
    iv_path = iv_model.geopolitical_event_model(
        base_iv,
        days_before_event=5,
        days_after_event=55,
        spike_magnitude=event_spike,
    )

    # Generate stock path (gradual +20% over 60 days with noise)
    np.random.seed(42)
    daily_drift = (1.20 ** (1/60)) - 1  # 20% over 60 days
    stock_path = [initial_spot]
    for i in range(1, days_to_simulate):
        noise = np.random.normal(0, 0.02)  # 2% daily volatility
        stock_path.append(stock_path[-1] * (1 + daily_drift + noise))

    # Test strategies
    strategies = {
        "Long Call (90 DTE)": {
            "legs": [Option(OptionType.CALL, 42, datetime.now() + timedelta(days=90), 1)],
        },
        "Diagonal Spread": {
            "legs": [
                Option(OptionType.CALL, 38, datetime.now() + timedelta(days=90), 1),  # Long ITM
                Option(OptionType.CALL, 44, datetime.now() + timedelta(days=30), -1),  # Short OTM
            ],
        },
        "Iron Condor": {
            "legs": [
                Option(OptionType.PUT, 34, datetime.now() + timedelta(days=30), 1),
                Option(OptionType.PUT, 36, datetime.now() + timedelta(days=30), -1),
                Option(OptionType.CALL, 44, datetime.now() + timedelta(days=30), -1),
                Option(OptionType.CALL, 46, datetime.now() + timedelta(days=30), 1),
            ],
        },
        "Calendar Spread": {
            "legs": [
                Option(OptionType.CALL, 40, datetime.now() + timedelta(days=60), 1),
                Option(OptionType.CALL, 40, datetime.now() + timedelta(days=30), -1),
            ],
        },
    }

    print(f"\nSimulation: Event on Day 5, Stock +20% over 60 days")
    print(f"Initial Spot: ${initial_spot}, Base IV: {base_iv:.0%}")

    results = {}

    for strategy_name, config in strategies.items():
        # Entry on day 6 (day after event - optimal entry per research)
        entry_day = 6
        entry_spot = stock_path[entry_day]
        entry_iv = iv_path[entry_day]

        # Calculate entry value
        entry_value = 0
        for leg in config["legs"]:
            price = pricer.price_option(leg, entry_spot, datetime.now() + timedelta(days=entry_day), entry_iv)
            entry_value += price.theoretical_price * leg.quantity * 100

        # Calculate exit value (day 30 for short-dated strategies, day 60 for longer)
        if "90 DTE" in strategy_name or "Calendar" in strategy_name:
            exit_day = min(55, len(stock_path) - 1)
        else:
            exit_day = min(28, len(stock_path) - 1)

        exit_spot = stock_path[exit_day]
        exit_iv = iv_path[exit_day]

        exit_value = 0
        for leg in config["legs"]:
            # Adjust expiration for time passed
            new_exp = leg.expiration - timedelta(days=exit_day - entry_day)
            adjusted_leg = Option(leg.option_type, leg.strike, new_exp, leg.quantity)
            price = pricer.price_option(adjusted_leg, exit_spot, datetime.now() + timedelta(days=exit_day), exit_iv)
            exit_value += price.theoretical_price * leg.quantity * 100

        pnl = exit_value - entry_value
        ret = pnl / abs(entry_value) if entry_value != 0 else 0

        results[strategy_name] = {
            "entry_value": entry_value,
            "exit_value": exit_value,
            "pnl": pnl,
            "return": ret,
            "entry_spot": entry_spot,
            "exit_spot": exit_spot,
            "entry_iv": entry_iv,
            "exit_iv": exit_iv,
            "days_held": exit_day - entry_day,
        }

    # Print results
    print(f"\n{'Strategy':<25} {'Entry':<12} {'Exit':<12} {'P&L':<12} {'Return':<10}")
    print("-" * 80)

    for name, r in sorted(results.items(), key=lambda x: x[1]['return'], reverse=True):
        print(f"{name:<25} ${r['entry_value']:>8.0f}   ${r['exit_value']:>8.0f}   "
              f"${r['pnl']:>+8.0f}   {r['return']:>+.1%}")

    print(f"\nStock: ${stock_path[6]:.2f} -> ${stock_path[-1]:.2f} ({(stock_path[-1]/stock_path[6]-1):+.1%})")
    print(f"IV: {iv_path[6]:.1%} -> {iv_path[-1]:.1%}")

    # Best strategy
    best = max(results.items(), key=lambda x: x[1]['return'])
    print(f"\nBest Strategy: {best[0]} with {best[1]['return']:+.1%} return")

    return results


def main():
    """Run all validations."""
    print("=" * 80)
    print("OPTIONS STRATEGY VALIDATION SUITE")
    print("=" * 80)

    # Run historical validation
    print("\n[1/2] Running historical validation...")
    historical_stats = run_venezuela_thesis_validation()

    # Run geopolitical event simulation
    print("\n[2/2] Running geopolitical event simulation...")
    event_results = run_geopolitical_event_simulation()

    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)
    print(f"\nResults saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
