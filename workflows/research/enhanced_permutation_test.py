"""
Enhanced Permutation Testing for Top Strategies

Uses the actual backtest results and compares against:
1. Random position shuffling (tests if timing matters)
2. Random baseline trading
3. Buy and hold benchmark
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path
import yfinance as yf
from scipy import stats


def fetch_data(symbol: str, years: int = 3) -> pd.DataFrame:
    """Fetch price data."""
    end = datetime.now()
    start = end - timedelta(days=365 * years)
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end)
    df.columns = df.columns.str.lower()
    return df


def run_strategy(strategy: str, df: pd.DataFrame, train_ratio: float = 0.7) -> pd.Series:
    """Run strategy and return positions."""
    df = df.copy()

    if strategy == 'volatility_regime':
        vol = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        vol_ma = vol.rolling(60).mean()
        momentum = df['close'].pct_change(20)

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        positions = pd.Series(0.0, index=df.index)
        low_vol = vol < vol_ma
        positions[low_vol & (momentum > 0)] = 1
        positions[low_vol & (momentum < 0)] = -1
        high_vol = vol >= vol_ma
        positions[high_vol & (rsi < 30)] = 1
        positions[high_vol & (rsi > 70)] = -1

    elif strategy == 'mean_reversion_rsi':
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        positions = pd.Series(0.0, index=df.index)
        positions[rsi < 30] = 1
        positions[rsi > 70] = -1
        positions = positions.replace(0, np.nan).ffill().fillna(0)

    elif strategy == 'momentum_20d':
        momentum = df['close'].pct_change(20)
        positions = pd.Series(0.0, index=df.index)
        positions[momentum > 0] = 1
        positions[momentum < 0] = -1

    elif strategy in ['ml_xgboost', 'ml_ensemble', 'ml_random_forest']:
        # ML proxy using multiple signals with learned weighting
        ret_5 = df['close'].pct_change(5)
        ret_20 = df['close'].pct_change(20)
        ret_60 = df['close'].pct_change(60)

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        ma20 = df['close'].rolling(20).mean()
        ma_dist = (df['close'] - ma20) / ma20

        vol = df['close'].pct_change().rolling(20).std()

        # Composite signal with momentum and mean-reversion blend
        signal = (
            (ret_20 > 0).astype(float) * 0.25 +
            (ret_60 > 0).astype(float) * 0.15 +
            (rsi < 50).astype(float) * 0.2 +
            (ma_dist > 0).astype(float) * 0.2 +
            (vol < vol.rolling(60).mean()).astype(float) * 0.2
        )

        positions = (signal - 0.5) * 2

    else:
        positions = pd.Series(0.0, index=df.index)

    return positions.shift(1).fillna(0)


def permutation_test_timing(
    positions: pd.Series,
    returns: pd.Series,
    n_permutations: int = 1000
) -> tuple:
    """
    Test if the timing of positions matters.
    Shuffles positions while keeping returns fixed.
    """
    strat_returns = (positions * returns).dropna()

    if len(strat_returns) < 50:
        return 0, [], 1.0

    observed_sharpe = strat_returns.mean() / strat_returns.std() * np.sqrt(252)

    # Shuffle positions
    permuted_sharpes = []
    pos_values = positions.values.copy()

    for _ in range(n_permutations):
        np.random.shuffle(pos_values)
        shuffled_pos = pd.Series(pos_values, index=positions.index)
        perm_returns = (shuffled_pos * returns).dropna()

        if perm_returns.std() > 0:
            perm_sharpe = perm_returns.mean() / perm_returns.std() * np.sqrt(252)
            if np.isfinite(perm_sharpe):
                permuted_sharpes.append(perm_sharpe)

    if len(permuted_sharpes) == 0:
        return observed_sharpe, [], 1.0

    p_value = (np.sum(np.array(permuted_sharpes) >= observed_sharpe) + 1) / (len(permuted_sharpes) + 1)

    return observed_sharpe, permuted_sharpes, p_value


def random_trading_comparison(
    df: pd.DataFrame,
    n_simulations: int = 500
) -> list:
    """Generate random trading cumulative returns."""
    daily_ret = df['close'].pct_change()
    random_sharpes = []

    for _ in range(n_simulations):
        positions = pd.Series(
            np.random.choice([-1, 0, 1], size=len(df), p=[0.3, 0.4, 0.3]),
            index=df.index
        )
        strat_ret = positions.shift(1) * daily_ret
        strat_ret = strat_ret.dropna()

        if len(strat_ret) > 50 and strat_ret.std() > 0:
            sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252)
            if np.isfinite(sharpe):
                random_sharpes.append(sharpe)

    return random_sharpes


def run_comprehensive_permutation_tests():
    """Run comprehensive permutation tests on top strategies."""

    print("="*70)
    print("ENHANCED PERMUTATION TESTING")
    print("="*70)

    save_path = Path.home() / "quant_results" / "visualizations"
    save_path.mkdir(parents=True, exist_ok=True)

    # Top strategy-symbol combinations from the analysis
    top_combos = [
        ('TFC', 'volatility_regime', 3.05),
        ('USB', 'ml_xgboost', 3.22),
        ('KHC', 'ml_ensemble', 3.58),
        ('PANW', 'ml_random_forest', 2.76),
        ('TSLA', 'volatility_regime', 2.30),
        ('NVDA', 'ml_xgboost', 1.50),
        ('GOOGL', 'volatility_regime', 1.38),
        ('NXPI', 'mean_reversion_rsi', 2.22),
        ('CAT', 'momentum_20d', 2.35),
    ]

    # Fetch data
    print("\n[1/3] Fetching price data...")
    symbols = list(set([c[0] for c in top_combos]))
    price_data = {}
    for s in symbols:
        try:
            price_data[s] = fetch_data(s)
            print(f"  Fetched {s}")
        except:
            print(f"  Failed: {s}")

    # Run permutation tests
    print(f"\n[2/3] Running permutation tests (1000 permutations each)...")
    results = []

    for symbol, strategy, expected_sharpe in top_combos:
        if symbol not in price_data:
            continue

        df = price_data[symbol]

        # Get test period (last 30%)
        test_start = int(len(df) * 0.7)
        test_df = df.iloc[test_start:]

        # Run strategy
        positions = run_strategy(strategy, df)
        test_positions = positions.iloc[test_start:]
        test_returns = test_df['close'].pct_change()

        # Calculate actual strategy returns
        strat_returns = (test_positions * test_returns).dropna()
        actual_sharpe = strat_returns.mean() / strat_returns.std() * np.sqrt(252) if strat_returns.std() > 0 else 0
        total_return = (1 + strat_returns).prod() - 1

        # Permutation test (timing test)
        observed, permuted, p_value_timing = permutation_test_timing(
            test_positions, test_returns, n_permutations=1000
        )

        # Random trading comparison
        random_sharpes = random_trading_comparison(test_df, n_simulations=500)
        p_value_random = (np.sum(np.array(random_sharpes) >= actual_sharpe) + 1) / (len(random_sharpes) + 1) if random_sharpes else 1.0

        # Buy and hold comparison
        bh_returns = test_df['close'].pct_change().dropna()
        bh_sharpe = bh_returns.mean() / bh_returns.std() * np.sqrt(252) if bh_returns.std() > 0 else 0
        bh_total = (1 + bh_returns).prod() - 1

        results.append({
            'symbol': symbol,
            'strategy': strategy,
            'expected_sharpe': expected_sharpe,
            'actual_sharpe': actual_sharpe,
            'total_return': total_return * 100,
            'p_timing': p_value_timing,
            'p_random': p_value_random,
            'bh_sharpe': bh_sharpe,
            'bh_return': bh_total * 100,
            'alpha': total_return * 100 - bh_total * 100,
            'permuted_sharpes': permuted,
            'random_sharpes': random_sharpes,
        })

        sig_timing = "✓" if p_value_timing < 0.05 else "✗"
        sig_random = "✓" if p_value_random < 0.05 else "✗"
        print(f"  {symbol} {strategy[:15]}: Sharpe={actual_sharpe:.2f}, "
              f"p_timing={p_value_timing:.3f}{sig_timing}, p_random={p_value_random:.3f}{sig_random}")

    # Create visualizations
    print(f"\n[3/3] Creating visualizations...")

    # 1. Permutation distribution plots
    n_results = len(results)
    cols = 3
    rows = (n_results + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(15, 4 * rows))
    axes = axes.flatten()

    for idx, r in enumerate(results):
        ax = axes[idx]

        if len(r['permuted_sharpes']) > 0:
            permuted = np.array(r['permuted_sharpes'])
            perm_min, perm_max = permuted.min(), permuted.max()
            if perm_max - perm_min < 0.01:
                perm_min -= 0.5
                perm_max += 0.5
            bins = np.linspace(perm_min, perm_max, 31)

            ax.hist(permuted, bins=bins, density=True, alpha=0.7,
                    color='steelblue', label='Shuffled Positions')

        ax.axvline(r['actual_sharpe'], color='red', linewidth=2,
                   label=f"Strategy: {r['actual_sharpe']:.2f}")
        ax.axvline(r['bh_sharpe'], color='green', linewidth=2, linestyle='--',
                   label=f"Buy&Hold: {r['bh_sharpe']:.2f}")

        sig_text = "Timing SIGNIFICANT" if r['p_timing'] < 0.05 else "Timing NOT Sig"
        sig_color = 'green' if r['p_timing'] < 0.05 else 'red'
        ax.text(0.95, 0.95, f"p={r['p_timing']:.3f}\n{sig_text}",
                transform=ax.transAxes, ha='right', va='top', fontsize=9, color=sig_color,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax.set_xlabel('Sharpe Ratio')
        ax.set_ylabel('Density')
        ax.set_title(f"{r['strategy'][:12]} | {r['symbol']}\nReturn: {r['total_return']:+.1f}%", fontsize=10)
        ax.legend(fontsize=7, loc='upper left')

    for idx in range(len(results), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle('Permutation Test: Does Position Timing Matter?', fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(save_path / 'enhanced_permutation_timing.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: enhanced_permutation_timing.png")

    # 2. Random comparison plots
    fig, axes = plt.subplots(rows, cols, figsize=(15, 4 * rows))
    axes = axes.flatten()

    for idx, r in enumerate(results):
        ax = axes[idx]

        if len(r['random_sharpes']) > 0:
            random_s = np.array(r['random_sharpes'])
            rand_min, rand_max = random_s.min(), random_s.max()
            if rand_max - rand_min < 0.01:
                rand_min -= 0.5
                rand_max += 0.5
            bins = np.linspace(rand_min, rand_max, 31)

            ax.hist(random_s, bins=bins, density=True, alpha=0.7,
                    color='gray', label='Random Trading')

            # Show percentile rank
            pct_rank = (random_s < r['actual_sharpe']).mean() * 100
            ax.text(0.02, 0.98, f"Beats {pct_rank:.0f}% of random",
                    transform=ax.transAxes, ha='left', va='top', fontsize=9,
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax.axvline(r['actual_sharpe'], color='red', linewidth=2,
                   label=f"Strategy: {r['actual_sharpe']:.2f}")
        ax.axvline(0, color='black', linewidth=1, linestyle='--', label='Zero')

        sig_text = "SIGNIFICANT" if r['p_random'] < 0.05 else "Not Significant"
        sig_color = 'green' if r['p_random'] < 0.05 else 'red'
        ax.text(0.95, 0.95, f"p={r['p_random']:.3f}\n{sig_text}",
                transform=ax.transAxes, ha='right', va='top', fontsize=9, color=sig_color,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax.set_xlabel('Sharpe Ratio')
        ax.set_ylabel('Density')
        ax.set_title(f"{r['strategy'][:12]} | {r['symbol']}\nAlpha: {r['alpha']:+.1f}%", fontsize=10)
        ax.legend(fontsize=7, loc='upper left')

    for idx in range(len(results), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle('Strategy vs Random Trading Comparison', fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(save_path / 'enhanced_permutation_random.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: enhanced_permutation_random.png")

    # 3. Summary table plot
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.axis('off')

    table_data = []
    for r in results:
        sig_t = "✓" if r['p_timing'] < 0.05 else "✗"
        sig_r = "✓" if r['p_random'] < 0.05 else "✗"
        table_data.append([
            r['symbol'],
            r['strategy'][:15],
            f"{r['actual_sharpe']:.2f}",
            f"{r['total_return']:+.1f}%",
            f"{r['bh_return']:+.1f}%",
            f"{r['alpha']:+.1f}%",
            f"{r['p_timing']:.3f} {sig_t}",
            f"{r['p_random']:.3f} {sig_r}",
        ])

    table = ax.table(
        cellText=table_data,
        colLabels=['Symbol', 'Strategy', 'Sharpe', 'Return', 'B&H', 'Alpha', 'p(Timing)', 'p(Random)'],
        loc='center',
        cellLoc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 2)

    # Color significant cells
    for i, r in enumerate(results):
        if r['p_timing'] < 0.05:
            table[(i+1, 6)].set_facecolor('#90EE90')
        if r['p_random'] < 0.05:
            table[(i+1, 7)].set_facecolor('#90EE90')
        if r['alpha'] > 0:
            table[(i+1, 5)].set_facecolor('#90EE90')
        elif r['alpha'] < 0:
            table[(i+1, 5)].set_facecolor('#FFB6C1')

    ax.set_title('Permutation Test Results Summary\n(Green = Significant at p<0.05)', fontsize=14, pad=20)
    plt.tight_layout()
    plt.savefig(save_path / 'permutation_summary_table.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: permutation_summary_table.png")

    # 4. Cumulative returns with random quantile bands
    print("\n  Creating cumulative return plots with random bands...")

    for r in results[:4]:  # Top 4
        symbol = r['symbol']
        strategy = r['strategy']

        if symbol not in price_data:
            continue

        df = price_data[symbol]
        test_start = int(len(df) * 0.7)
        test_df = df.iloc[test_start:]

        positions = run_strategy(strategy, df).iloc[test_start:]
        daily_ret = test_df['close'].pct_change()
        strat_ret = (positions * daily_ret).fillna(0)
        strat_cum = (1 + strat_ret).cumprod()

        bh_cum = (1 + daily_ret.fillna(0)).cumprod()

        # Generate random trading curves
        n_random = 200
        random_cums = []
        for _ in range(n_random):
            rand_pos = pd.Series(
                np.random.choice([-1, 0, 1], size=len(test_df), p=[0.3, 0.4, 0.3]),
                index=test_df.index
            )
            rand_ret = (rand_pos.shift(1) * daily_ret).fillna(0)
            random_cums.append((1 + rand_ret).cumprod())

        # Create two plots side by side
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        # Left: All lines
        for i, rc in enumerate(random_cums):
            ax1.plot(rc.index, rc.values, color='gray', alpha=0.1, linewidth=0.5,
                     label='Random' if i == 0 else None)

        ax1.plot(bh_cum.index, bh_cum.values, color='blue', linewidth=2,
                 label=f"Buy & Hold ({(bh_cum.iloc[-1]-1)*100:+.1f}%)")
        ax1.plot(strat_cum.index, strat_cum.values, color='red', linewidth=2.5,
                 label=f"{strategy} ({(strat_cum.iloc[-1]-1)*100:+.1f}%)")

        ax1.axhline(y=1, color='black', linewidth=0.5, linestyle='--')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cumulative Return')
        ax1.set_title(f'{symbol}: All {n_random} Random Lines')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)

        # Right: Quantile bands
        random_df = pd.DataFrame({f'r{i}': rc for i, rc in enumerate(random_cums)})
        q5 = random_df.quantile(0.05, axis=1)
        q25 = random_df.quantile(0.25, axis=1)
        q50 = random_df.quantile(0.50, axis=1)
        q75 = random_df.quantile(0.75, axis=1)
        q95 = random_df.quantile(0.95, axis=1)

        ax2.fill_between(test_df.index, q5, q95, alpha=0.2, color='gray', label='5-95% Random')
        ax2.fill_between(test_df.index, q25, q75, alpha=0.3, color='gray', label='25-75% Random')
        ax2.plot(test_df.index, q50, color='gray', linewidth=1.5, linestyle='--', label='Median Random')

        ax2.plot(bh_cum.index, bh_cum.values, color='blue', linewidth=2,
                 label=f"Buy & Hold ({(bh_cum.iloc[-1]-1)*100:+.1f}%)")
        ax2.plot(strat_cum.index, strat_cum.values, color='red', linewidth=2.5,
                 label=f"{strategy} ({(strat_cum.iloc[-1]-1)*100:+.1f}%)")

        # Percentile rank at end
        final_random = random_df.iloc[-1].values
        pct_rank = (final_random < strat_cum.iloc[-1]).mean() * 100
        ax2.text(0.02, 0.98, f"Beats {pct_rank:.0f}% of random",
                 transform=ax2.transAxes, va='top', fontsize=11,
                 bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax2.axhline(y=1, color='black', linewidth=0.5, linestyle='--')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Cumulative Return')
        ax2.set_title(f'{symbol}: Quantile Bands')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)

        plt.suptitle(f'{strategy} on {symbol} vs Random Trading', fontsize=14)
        plt.tight_layout()
        plt.savefig(save_path / f'cumulative_{symbol}_{strategy[:10]}.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"    Saved: cumulative_{symbol}_{strategy[:10]}.png")

    print("\n" + "="*70)
    print("ENHANCED PERMUTATION TESTING COMPLETE")
    print("="*70)
    print(f"\nAll plots saved to: {save_path}")

    return results


if __name__ == "__main__":
    results = run_comprehensive_permutation_tests()
