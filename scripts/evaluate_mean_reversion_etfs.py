#!/usr/bin/env python3
"""
Mean-Reversion Strategy Evaluation for Major ETFs

Evaluates RSI Reversal and Bollinger Band strategies on major ETFs
for paper trading readiness assessment.

Usage:
    PYTHONPATH=. python scripts/evaluate_mean_reversion_etfs.py
"""

import sys
sys.path.insert(0, '/home/nock/projects/quant_suite/src')

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np


def rsi(prices, period=14):
    """Calculate RSI."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def rsi_reversal(prices, oversold=30, overbought=70):
    """Buy when RSI < oversold, sell when RSI > overbought."""
    rsi_val = rsi(prices)
    signal = pd.Series(0, index=prices.index)
    signal[rsi_val < oversold] = 1
    signal[rsi_val > overbought] = 0
    return signal.shift(1).fillna(0)


def bollinger_reversal(prices, window=20, num_std=2):
    """Buy when price touches lower band."""
    sma = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    lower = sma - num_std * std
    signal = (prices <= lower).astype(int)
    return signal.shift(1).fillna(0)


def calculate_sharpe(returns, annual_factor=252):
    """Calculate annualized Sharpe ratio."""
    if len(returns) < 10 or returns.std() == 0:
        return 0.0
    return np.sqrt(annual_factor) * returns.mean() / returns.std()


def calculate_sortino(returns, annual_factor=252):
    """Calculate Sortino ratio (downside risk)."""
    if len(returns) < 10:
        return 0.0
    negative_returns = returns[returns < 0]
    if len(negative_returns) == 0 or negative_returns.std() == 0:
        return 0.0 if returns.mean() <= 0 else float('inf')
    return np.sqrt(annual_factor) * returns.mean() / negative_returns.std()


def calculate_max_drawdown(returns):
    """Calculate maximum drawdown."""
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return float(drawdown.min())


def calculate_win_rate(returns):
    """Calculate win rate."""
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def evaluate_strategy(symbol, strategy_fn, strategy_name, days=60):
    """Evaluate strategy on recent data."""
    try:
        end = datetime.now()
        start = end - timedelta(days=days + 50)

        data = yf.download(symbol, start=start, end=end, progress=False)
        if len(data) < 30:
            return None

        # Handle multi-index columns from yfinance
        if 'Close' in data.columns:
            prices = data['Close']
        else:
            prices = data['close']

        if hasattr(prices, 'columns'):
            prices = prices.iloc[:, 0] if len(prices.shape) > 1 else prices

        returns = prices.pct_change().dropna()

        signal = strategy_fn(prices)
        strategy_returns = signal * returns
        strategy_returns = strategy_returns.dropna().tail(days)

        # Calculate metrics
        sharpe = calculate_sharpe(strategy_returns)
        sortino = calculate_sortino(strategy_returns)
        total_return = (1 + strategy_returns).prod() - 1
        max_dd = calculate_max_drawdown(strategy_returns)
        win_rate = calculate_win_rate(strategy_returns[strategy_returns != 0])

        # Count signal days
        signal_days = int((signal.tail(days) > 0).sum())

        return {
            'symbol': symbol,
            'strategy': strategy_name,
            'sharpe_60d': round(sharpe, 2),
            'sortino_60d': round(sortino, 2),
            'total_return_60d': round(total_return * 100, 2),
            'max_drawdown': round(max_dd * 100, 2),
            'win_rate': round(win_rate * 100, 1),
            'signal_days': signal_days,
            'days': len(strategy_returns)
        }
    except Exception as e:
        return {'symbol': symbol, 'strategy': strategy_name, 'error': str(e)}


def paper_trading_readiness(results):
    """Assess paper trading readiness based on metrics."""
    readiness = []
    for r in results:
        if 'error' in r:
            continue

        score = 0
        reasons = []

        # Sharpe > 0.3 (good risk-adjusted return)
        if r.get('sharpe_60d', 0) > 0.3:
            score += 2
            reasons.append("Good Sharpe")
        elif r.get('sharpe_60d', 0) > 0:
            score += 1
            reasons.append("Positive Sharpe")

        # Positive returns
        if r.get('total_return_60d', 0) > 0:
            score += 1
            reasons.append("Positive returns")

        # Max drawdown < 10%
        if abs(r.get('max_drawdown', -100)) < 10:
            score += 1
            reasons.append("Low drawdown")

        # Win rate > 50%
        if r.get('win_rate', 0) > 50:
            score += 1
            reasons.append("High win rate")

        # Determine status
        if score >= 4:
            status = "READY"
        elif score >= 2:
            status = "PROMISING"
        else:
            status = "NEEDS_WORK"

        readiness.append({
            **r,
            'readiness_score': score,
            'readiness_status': status,
            'readiness_reasons': reasons
        })

    return readiness


def main():
    # Major ETFs covering different sectors
    symbols = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV']

    print("=" * 70)
    print("ETF MEAN-REVERSION STRATEGY EVALUATION")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Strategies: RSI Reversal, Bollinger Band Reversal")
    print(f"Evaluation Period: 60 days")
    print("=" * 70)
    print()

    results = []
    strategies = [
        (rsi_reversal, 'rsi_reversal'),
        (bollinger_reversal, 'bollinger_reversal')
    ]

    print("Fetching data and evaluating strategies...")
    print()

    for symbol in symbols:
        for strategy_fn, name in strategies:
            result = evaluate_strategy(symbol, strategy_fn, name, days=60)
            if result:
                results.append(result)

    # Sort by Sharpe ratio
    valid_results = [r for r in results if 'error' not in r]
    sorted_results = sorted(valid_results, key=lambda x: x.get('sharpe_60d', 0), reverse=True)

    print("=" * 70)
    print("RESULTS (Sorted by Sharpe Ratio)")
    print("=" * 70)
    print(f"{'Strategy/Symbol':<30} {'Sharpe':>8} {'Return':>10} {'MaxDD':>8} {'WinRate':>8}")
    print("-" * 70)

    for r in sorted_results:
        name = f"{r['strategy']}/{r['symbol']}"
        print(f"{name:<30} {r['sharpe_60d']:>8.2f} {r['total_return_60d']:>9.2f}% {r['max_drawdown']:>7.2f}% {r['win_rate']:>7.1f}%")

    # Paper trading readiness assessment
    readiness = paper_trading_readiness(results)
    ready_strategies = [r for r in readiness if r.get('readiness_status') == 'READY']
    promising_strategies = [r for r in readiness if r.get('readiness_status') == 'PROMISING']

    print()
    print("=" * 70)
    print("PAPER TRADING READINESS ASSESSMENT")
    print("=" * 70)

    if ready_strategies:
        print("\n[READY FOR PAPER TRADING] (Score >= 4/5)")
        for r in sorted(ready_strategies, key=lambda x: x['sharpe_60d'], reverse=True):
            print(f"  * {r['strategy']}/{r['symbol']}: Sharpe={r['sharpe_60d']}, Return={r['total_return_60d']}%")
            print(f"    Reasons: {', '.join(r['readiness_reasons'])}")
    else:
        print("\n[READY FOR PAPER TRADING]: None currently meet criteria")

    if promising_strategies:
        print("\n[PROMISING - MORE VALIDATION NEEDED] (Score 2-3/5)")
        for r in sorted(promising_strategies, key=lambda x: x['sharpe_60d'], reverse=True):
            print(f"  * {r['strategy']}/{r['symbol']}: Sharpe={r['sharpe_60d']}, Return={r['total_return_60d']}%")
            print(f"    Reasons: {', '.join(r['readiness_reasons'])}")

    # Top picks summary
    print()
    print("=" * 70)
    print("TOP PICKS (Sharpe > 0.3)")
    print("=" * 70)
    top = [r for r in sorted_results if r.get('sharpe_60d', 0) > 0.3]
    if top:
        for r in top:
            print(f"  {r['strategy']}/{r['symbol']}: Sharpe={r['sharpe_60d']}, Sortino={r['sortino_60d']}")
    else:
        print("  No strategies currently meet Sharpe > 0.3 threshold")

    # Recommendations
    print()
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    best_rsi = max([r for r in sorted_results if r['strategy'] == 'rsi_reversal'],
                   key=lambda x: x['sharpe_60d'], default=None)
    best_bb = max([r for r in sorted_results if r['strategy'] == 'bollinger_reversal'],
                  key=lambda x: x['sharpe_60d'], default=None)

    if best_rsi:
        print(f"\nBest RSI Reversal: {best_rsi['symbol']}")
        print(f"  - Sharpe: {best_rsi['sharpe_60d']}, Return: {best_rsi['total_return_60d']}%")

    if best_bb:
        print(f"\nBest Bollinger Band: {best_bb['symbol']}")
        print(f"  - Sharpe: {best_bb['sharpe_60d']}, Return: {best_bb['total_return_60d']}%")

    print("\nNext Steps:")
    print("  1. Run full MCPT validation on top picks (p < 0.05 required)")
    print("  2. Test with 2-day minimum hold for PDT compliance")
    print("  3. Use paper trading script: scripts/paper_trade.py")
    print(f"     Example: PYTHONPATH=. python scripts/paper_trade.py --strategy bb_reversion --symbols {best_bb['symbol'] if best_bb else 'SPY'}")

    return results


if __name__ == "__main__":
    main()
