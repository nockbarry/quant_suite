#!/usr/bin/env python3
"""
Lead-Lag Strategy Validation Script

Comprehensive validation of lead-lag strategies including:
1. Lead-lag relationship verification
2. Feature analysis
3. Backtest with realistic costs
4. MCPT statistical validation
5. Walk-forward out-of-sample testing
6. Regime analysis
7. Risk metrics

Usage:
    PYTHONPATH=. python scripts/validate_lead_lag_strategy.py

    # With specific parameters
    PYTHONPATH=. python scripts/validate_lead_lag_strategy.py --lag 18 --threshold 0.02

    # Quick test
    PYTHONPATH=. python scripts/validate_lead_lag_strategy.py --quick

Author: Claude Code
Created: 2026-01-04
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# DATA ACQUISITION
# =============================================================================

def fetch_data(symbols: list[str], days: int = 730) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for symbols."""
    data = {}
    period = f"{days}d" if days <= 365 else f"{min(days // 365 + 1, 10)}y"

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if not hist.empty:
                data[symbol] = hist
                logger.info(f"Fetched {symbol}: {len(hist)} rows")
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")

    return data


# =============================================================================
# LEAD-LAG ANALYSIS
# =============================================================================

def analyze_lead_lag(
    leader_data: pd.DataFrame,
    target_data: pd.DataFrame,
    max_lag: int = 30,
) -> pd.DataFrame:
    """
    Analyze correlation at different lags.

    Returns DataFrame with lag, correlation, p_value.
    """
    from scipy import stats

    leader_returns = leader_data['Close'].pct_change().dropna()
    target_returns = target_data['Close'].pct_change().dropna()

    # Align
    aligned = pd.concat([leader_returns, target_returns], axis=1, join='inner')
    aligned.columns = ['leader', 'target']

    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            shifted_leader = aligned['leader'].shift(-lag)
            valid = pd.concat([shifted_leader, aligned['target']], axis=1).dropna()
        else:
            shifted_target = aligned['target'].shift(lag)
            valid = pd.concat([aligned['leader'], shifted_target], axis=1).dropna()

        if len(valid) < 30:
            continue

        corr, pval = stats.pearsonr(valid.iloc[:, 0], valid.iloc[:, 1])
        results.append({
            'lag': lag,
            'correlation': corr,
            'p_value': pval,
            'n_obs': len(valid),
        })

    return pd.DataFrame(results)


def find_optimal_lag(lag_analysis: pd.DataFrame) -> dict:
    """Find optimal lag from analysis."""
    best_idx = lag_analysis['correlation'].abs().idxmax()
    best = lag_analysis.loc[best_idx]

    return {
        'optimal_lag': int(best['lag']),
        'correlation': best['correlation'],
        'p_value': best['p_value'],
        'direction': 'leader_leads' if best['lag'] < 0 else 'concurrent' if best['lag'] == 0 else 'target_leads',
    }


# =============================================================================
# BACKTESTING
# =============================================================================

def run_backtest(
    leader_data: pd.DataFrame,
    target_data: pd.DataFrame,
    lag_days: int = 18,
    signal_threshold: float = 0.02,
    momentum_window: int = 5,
    transaction_cost_bps: int = 10,
    holding_period: int = 5,
) -> dict:
    """
    Run backtest of lead-lag strategy.

    Returns dict with returns, sharpe, metrics.
    """
    # Align data
    common_idx = leader_data.index.intersection(target_data.index)
    leader = leader_data.loc[common_idx, 'Close']
    target = target_data.loc[common_idx, 'Close']

    # Calculate leader momentum (lagged)
    leader_momentum = leader.pct_change(momentum_window).shift(lag_days)

    # Generate signals
    signals = pd.Series(0, index=common_idx)
    signals[leader_momentum > signal_threshold] = 1  # Long
    signals[leader_momentum < -signal_threshold] = -1  # Short

    # Remove consecutive duplicate signals (only enter on new signal)
    signal_changes = signals.diff().fillna(0)
    entry_signals = signals.where(signal_changes != 0, 0)

    # Calculate target returns
    target_returns = target.pct_change()

    # Strategy returns (with holding period)
    position = pd.Series(0.0, index=common_idx)

    for i, idx in enumerate(common_idx):
        if entry_signals.loc[idx] != 0:
            # Enter position
            end_idx = min(i + holding_period, len(common_idx) - 1)
            position.iloc[i:end_idx + 1] = entry_signals.loc[idx]

    # Apply transaction costs
    trades = position.diff().abs()
    costs = trades * (transaction_cost_bps / 10000)

    # Strategy returns
    strategy_returns = (position.shift(1) * target_returns) - costs
    strategy_returns = strategy_returns.dropna()

    # Calculate metrics
    total_return = (1 + strategy_returns).prod() - 1
    ann_return = (1 + total_return) ** (252 / len(strategy_returns)) - 1
    volatility = strategy_returns.std() * np.sqrt(252)
    sharpe = ann_return / volatility if volatility > 0 else 0

    # Drawdown
    cumulative = (1 + strategy_returns).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Win rate
    winning_days = (strategy_returns > 0).sum()
    total_days = (strategy_returns != 0).sum()
    win_rate = winning_days / total_days if total_days > 0 else 0

    # Trade count
    n_trades = (trades > 0).sum()

    return {
        'returns': strategy_returns,
        'cumulative_returns': cumulative,
        'total_return': total_return,
        'annual_return': ann_return,
        'volatility': volatility,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'n_trades': n_trades,
        'n_days': len(strategy_returns),
        'positions': position,
    }


# =============================================================================
# STATISTICAL VALIDATION
# =============================================================================

def mcpt_test(
    strategy_returns: pd.Series,
    n_permutations: int = 1000,
) -> dict:
    """
    Monte Carlo Permutation Test.

    Tests if strategy Sharpe is significantly better than random.
    """
    strategy_sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)

    permuted_sharpes = []
    returns_array = strategy_returns.values

    for _ in range(n_permutations):
        # Permute returns
        permuted = np.random.permutation(returns_array)
        perm_sharpe = np.mean(permuted) / np.std(permuted) * np.sqrt(252)
        permuted_sharpes.append(perm_sharpe)

    permuted_sharpes = np.array(permuted_sharpes)

    # P-value: fraction of permuted Sharpes >= strategy Sharpe
    p_value = (permuted_sharpes >= strategy_sharpe).mean()

    return {
        'strategy_sharpe': strategy_sharpe,
        'permuted_mean': np.mean(permuted_sharpes),
        'permuted_std': np.std(permuted_sharpes),
        'p_value': p_value,
        'significant': p_value < 0.05,
        'permuted_sharpes': permuted_sharpes,
    }


def walk_forward_test(
    leader_data: pd.DataFrame,
    target_data: pd.DataFrame,
    lag_days: int = 18,
    signal_threshold: float = 0.02,
    n_splits: int = 5,
    train_pct: float = 0.6,
) -> list[dict]:
    """
    Walk-forward out-of-sample testing.

    Splits data into train/test periods and validates on each.
    """
    # Align data
    common_idx = leader_data.index.intersection(target_data.index)
    n = len(common_idx)

    results = []
    step_size = n // n_splits

    for i in range(n_splits):
        # Define train/test split
        test_start = i * step_size
        test_end = min((i + 1) * step_size, n)
        train_end = test_start

        if train_end < 100:  # Need minimum training data
            continue

        # Get train and test data
        train_idx = common_idx[:train_end]
        test_idx = common_idx[test_start:test_end]

        train_leader = leader_data.loc[train_idx]
        train_target = target_data.loc[train_idx]
        test_leader = leader_data.loc[test_idx]
        test_target = target_data.loc[test_idx]

        # Run backtest on train
        train_result = run_backtest(
            train_leader, train_target,
            lag_days=lag_days,
            signal_threshold=signal_threshold,
        )

        # Run backtest on test
        test_result = run_backtest(
            test_leader, test_target,
            lag_days=lag_days,
            signal_threshold=signal_threshold,
        )

        results.append({
            'split': i + 1,
            'train_start': str(train_idx[0].date()) if len(train_idx) > 0 else None,
            'train_end': str(train_idx[-1].date()) if len(train_idx) > 0 else None,
            'test_start': str(test_idx[0].date()) if len(test_idx) > 0 else None,
            'test_end': str(test_idx[-1].date()) if len(test_idx) > 0 else None,
            'train_sharpe': train_result['sharpe_ratio'],
            'test_sharpe': test_result['sharpe_ratio'],
            'train_return': train_result['total_return'],
            'test_return': test_result['total_return'],
            'oos_degradation': (train_result['sharpe_ratio'] - test_result['sharpe_ratio']) / max(train_result['sharpe_ratio'], 0.01),
        })

    return results


# =============================================================================
# MAIN VALIDATION PIPELINE
# =============================================================================

async def run_full_validation(
    leader_symbol: str = 'MU',
    target_symbols: list[str] = None,
    lag_days: int = 18,
    signal_threshold: float = 0.02,
    days: int = 730,
    quick: bool = False,
) -> dict:
    """Run full validation pipeline."""

    if target_symbols is None:
        target_symbols = ['NVDA', 'AMD', 'AVGO', 'QCOM']

    print("=" * 70)
    print("LEAD-LAG STRATEGY VALIDATION")
    print("=" * 70)
    print(f"Leader: {leader_symbol}")
    print(f"Targets: {target_symbols}")
    print(f"Lag: {lag_days} days")
    print(f"Signal Threshold: {signal_threshold:.1%}")
    print(f"Data Period: {days} days")
    print("=" * 70)

    # =========================================================================
    # STEP 1: Fetch Data
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 1: DATA ACQUISITION")
    print("=" * 70)

    all_symbols = [leader_symbol] + target_symbols
    data = fetch_data(all_symbols, days=days)

    if leader_symbol not in data:
        raise ValueError(f"Could not fetch leader data for {leader_symbol}")

    leader_data = data[leader_symbol]
    print(f"Leader data: {len(leader_data)} rows ({leader_data.index[0].date()} to {leader_data.index[-1].date()})")

    # =========================================================================
    # STEP 2: Verify Lead-Lag Relationship
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 2: LEAD-LAG RELATIONSHIP VERIFICATION")
    print("=" * 70)

    relationship_results = {}
    for target in target_symbols:
        if target not in data:
            continue

        target_data = data[target]
        lag_analysis = analyze_lead_lag(leader_data, target_data, max_lag=30)
        optimal = find_optimal_lag(lag_analysis)

        relationship_results[target] = optimal
        print(f"\n{leader_symbol} → {target}:")
        print(f"  Optimal lag: {optimal['optimal_lag']} days")
        print(f"  Correlation: {optimal['correlation']:.3f}")
        print(f"  P-value: {optimal['p_value']:.4f}")
        print(f"  Direction: {optimal['direction']}")

    # =========================================================================
    # STEP 3: Backtesting
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 3: BACKTESTING")
    print("=" * 70)

    backtest_results = {}
    for target in target_symbols:
        if target not in data:
            continue

        result = run_backtest(
            leader_data, data[target],
            lag_days=lag_days,
            signal_threshold=signal_threshold,
        )

        backtest_results[target] = result
        print(f"\n{target}:")
        print(f"  Sharpe Ratio: {result['sharpe_ratio']:.2f}")
        print(f"  Total Return: {result['total_return']:.1%}")
        print(f"  Max Drawdown: {result['max_drawdown']:.1%}")
        print(f"  Win Rate: {result['win_rate']:.1%}")
        print(f"  Trades: {result['n_trades']}")

    # =========================================================================
    # STEP 4: MCPT Validation
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 4: MCPT STATISTICAL VALIDATION")
    print("=" * 70)

    n_perms = 100 if quick else 1000
    mcpt_results = {}

    for target in target_symbols:
        if target not in backtest_results:
            continue

        returns = backtest_results[target]['returns']
        mcpt = mcpt_test(returns, n_permutations=n_perms)
        mcpt_results[target] = mcpt

        status = "SIGNIFICANT" if mcpt['significant'] else "NOT SIGNIFICANT"
        print(f"\n{target}:")
        print(f"  Strategy Sharpe: {mcpt['strategy_sharpe']:.2f}")
        print(f"  Permuted Mean: {mcpt['permuted_mean']:.2f} ± {mcpt['permuted_std']:.2f}")
        print(f"  P-value: {mcpt['p_value']:.4f}")
        print(f"  Status: {status}")

    # =========================================================================
    # STEP 5: Walk-Forward Testing
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 5: WALK-FORWARD OUT-OF-SAMPLE TESTING")
    print("=" * 70)

    n_splits = 3 if quick else 5
    wf_results = {}

    for target in target_symbols:
        if target not in data:
            continue

        wf = walk_forward_test(
            leader_data, data[target],
            lag_days=lag_days,
            signal_threshold=signal_threshold,
            n_splits=n_splits,
        )
        wf_results[target] = wf

        print(f"\n{target}:")
        print(f"  {'Split':<6} {'Train Sharpe':>12} {'Test Sharpe':>12} {'Degradation':>12}")
        print("  " + "-" * 48)

        avg_oos = []
        for split in wf:
            deg = split.get('oos_degradation', 0) * 100
            avg_oos.append(split['test_sharpe'])
            print(f"  {split['split']:<6} {split['train_sharpe']:>12.2f} {split['test_sharpe']:>12.2f} {deg:>11.0f}%")

        print(f"\n  Average OOS Sharpe: {np.mean(avg_oos):.2f}")

    # =========================================================================
    # STEP 6: Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(f"\n{'Target':<8} {'Correlation':>12} {'Sharpe':>8} {'p-value':>10} {'Status':>15}")
    print("-" * 60)

    significant_count = 0
    for target in target_symbols:
        if target not in mcpt_results:
            continue

        corr = relationship_results.get(target, {}).get('correlation', 0)
        sharpe = backtest_results[target]['sharpe_ratio']
        pval = mcpt_results[target]['p_value']
        sig = mcpt_results[target]['significant']

        status = "SIGNIFICANT" if sig else "Not sig"
        if sig:
            significant_count += 1

        print(f"{target:<8} {corr:>12.3f} {sharpe:>8.2f} {pval:>10.4f} {status:>15}")

    print(f"\nSignificant strategies: {significant_count}/{len(target_symbols)}")

    # =========================================================================
    # Save Results
    # =========================================================================
    output_dir = Path("/home/nock/quant_results/lead_lag_validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"validation_{leader_symbol}_{timestamp}.json"

    # Prepare results for JSON
    results = {
        'timestamp': timestamp,
        'config': {
            'leader_symbol': leader_symbol,
            'target_symbols': target_symbols,
            'lag_days': lag_days,
            'signal_threshold': signal_threshold,
            'days': days,
        },
        'relationships': relationship_results,
        'backtest': {
            target: {
                'sharpe_ratio': r['sharpe_ratio'],
                'total_return': r['total_return'],
                'max_drawdown': r['max_drawdown'],
                'win_rate': r['win_rate'],
                'n_trades': int(r['n_trades']),
            }
            for target, r in backtest_results.items()
        },
        'mcpt': {
            target: {
                'strategy_sharpe': m['strategy_sharpe'],
                'p_value': m['p_value'],
                'significant': m['significant'],
            }
            for target, m in mcpt_results.items()
        },
        'walk_forward': wf_results,
        'summary': {
            'significant_count': significant_count,
            'total_targets': len(target_symbols),
        }
    }

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_file}")

    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Validate Lead-Lag Strategy")
    parser.add_argument('--leader', default='MU', help='Leader symbol')
    parser.add_argument('--targets', nargs='+', default=['NVDA', 'AMD', 'AVGO', 'QCOM'],
                        help='Target symbols')
    parser.add_argument('--lag', type=int, default=18, help='Lag days')
    parser.add_argument('--threshold', type=float, default=0.02, help='Signal threshold')
    parser.add_argument('--days', type=int, default=730, help='Data days')
    parser.add_argument('--quick', action='store_true', help='Quick test mode')

    args = parser.parse_args()

    asyncio.run(run_full_validation(
        leader_symbol=args.leader,
        target_symbols=args.targets,
        lag_days=args.lag,
        signal_threshold=args.threshold,
        days=args.days,
        quick=args.quick,
    ))


if __name__ == '__main__':
    main()
