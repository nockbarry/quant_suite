"""
Strategy Visualization & Permutation Testing

Creates comprehensive plots for:
1. Strategy performance comparisons
2. Category analysis heatmaps
3. Monte Carlo permutation tests
4. Random baseline comparisons (all lines + quantiles)
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime, timedelta
import os
from pathlib import Path
import yfinance as yf
from scipy import stats
import json

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))


# =============================================================================
# DATA LOADING
# =============================================================================

def load_analysis_results():
    """Load results from universe analysis."""
    results_dir = _RESULTS_DIR / "universe_analysis"

    results_df = pd.read_csv(results_dir / "all_results.csv")

    with open(results_dir / "category_analysis.json", 'r') as f:
        category_analysis = json.load(f)

    with open(results_dir / "asset_profiles.json", 'r') as f:
        profiles = json.load(f)

    return results_df, category_analysis, profiles


def fetch_price_data(symbols: list, years: int = 3) -> dict:
    """Fetch price data for symbols."""
    end = datetime.now()
    start = end - timedelta(days=365 * years)

    data = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end)
            if len(df) > 100:
                df.columns = df.columns.str.lower()
                data[symbol] = df
        except:
            pass
    return data


# =============================================================================
# STRATEGY IMPLEMENTATIONS (for backtesting plots)
# =============================================================================

def run_strategy(strategy_name: str, df: pd.DataFrame) -> pd.Series:
    """Run strategy and return daily returns."""
    df = df.copy()

    if strategy_name == 'momentum_20d':
        momentum = df['close'].pct_change(20)
        positions = pd.Series(0, index=df.index)
        positions[momentum > 0] = 1
        positions[momentum < 0] = -1
        positions = positions.shift(1).fillna(0)

    elif strategy_name == 'mean_reversion_rsi':
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        positions = pd.Series(0, index=df.index)
        positions[rsi < 30] = 1
        positions[rsi > 70] = -1
        positions = positions.replace(0, np.nan).ffill().fillna(0)
        positions = positions.shift(1).fillna(0)

    elif strategy_name == 'volatility_regime':
        vol = df['close'].pct_change().rolling(20).std() * np.sqrt(252)
        vol_ma = vol.rolling(60).mean()
        momentum = df['close'].pct_change(20)

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        positions = pd.Series(0, index=df.index)
        low_vol = vol < vol_ma
        positions[low_vol & (momentum > 0)] = 1
        positions[low_vol & (momentum < 0)] = -1
        high_vol = vol >= vol_ma
        positions[high_vol & (rsi < 30)] = 1
        positions[high_vol & (rsi > 70)] = -1
        positions = positions.shift(1).fillna(0)

    elif strategy_name == 'ml_xgboost' or strategy_name == 'ml_ensemble':
        # Simplified ML proxy using multiple signals
        ret_20 = df['close'].pct_change(20)

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))

        ma20 = df['close'].rolling(20).mean()
        ma_dist = (df['close'] - ma20) / ma20

        # Composite signal
        signal = (
            (ret_20 > 0).astype(float) * 0.4 +
            (rsi < 50).astype(float) * 0.3 +
            (ma_dist > 0).astype(float) * 0.3
        )

        positions = (signal - 0.5) * 2
        positions = positions.shift(1).fillna(0)

    else:
        positions = pd.Series(0, index=df.index)

    daily_ret = df['close'].pct_change()
    strat_ret = positions * daily_ret

    return strat_ret.fillna(0)


# =============================================================================
# PERMUTATION TESTING
# =============================================================================

def monte_carlo_permutation_test(
    strategy_returns: pd.Series,
    n_permutations: int = 500,
) -> tuple:
    """
    Run Monte Carlo permutation test.
    Returns: (observed_sharpe, permuted_sharpes, p_value)
    """
    returns = strategy_returns.dropna()
    returns = returns[np.isfinite(returns)]

    if len(returns) < 50:
        return 0, [], 1.0

    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0, [], 1.0

    # Observed Sharpe
    observed_sharpe = returns.mean() / std * np.sqrt(252)
    if np.isnan(observed_sharpe):
        return 0, [], 1.0

    # Permutation test - shuffle the returns
    permuted_sharpes = []
    for _ in range(n_permutations):
        shuffled = np.random.permutation(returns.values)
        perm_std = shuffled.std()
        if perm_std > 0:
            perm_sharpe = shuffled.mean() / perm_std * np.sqrt(252)
            if np.isfinite(perm_sharpe):
                permuted_sharpes.append(perm_sharpe)

    if len(permuted_sharpes) == 0:
        return observed_sharpe, [], 1.0

    # P-value: proportion of permuted >= observed
    p_value = (np.sum(np.array(permuted_sharpes) >= observed_sharpe) + 1) / (len(permuted_sharpes) + 1)

    return observed_sharpe, permuted_sharpes, p_value


def run_random_baseline(
    df: pd.DataFrame,
    n_simulations: int = 200,
) -> list:
    """Run random trading simulations, return cumulative returns for each."""
    daily_ret = df['close'].pct_change()
    random_cum_returns = []

    for _ in range(n_simulations):
        # Random positions: -1, 0, or 1
        positions = pd.Series(
            np.random.choice([-1, 0, 1], size=len(df), p=[0.3, 0.4, 0.3]),
            index=df.index
        )
        strat_ret = positions.shift(1) * daily_ret
        cum_ret = (1 + strat_ret.fillna(0)).cumprod()
        random_cum_returns.append(cum_ret)

    return random_cum_returns


# =============================================================================
# VISUALIZATION FUNCTIONS
# =============================================================================

def plot_strategy_overview(results_df: pd.DataFrame, save_path: Path):
    """Plot strategy performance overview."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 1. Strategy comparison bar chart
    ax1 = axes[0, 0]
    strat_summary = results_df.groupby('strategy').agg({
        'sharpe': 'mean',
        'total_return': 'mean',
        'vs_spy': 'mean',
    }).sort_values('sharpe', ascending=True)

    colors = ['#e74c3c' if x < 0 else '#2ecc71' for x in strat_summary['sharpe']]
    bars = ax1.barh(strat_summary.index, strat_summary['sharpe'], color=colors)
    ax1.axvline(x=0, color='black', linewidth=0.5)
    ax1.set_xlabel('Average Sharpe Ratio')
    ax1.set_title('Strategy Performance Comparison')

    for i, (idx, row) in enumerate(strat_summary.iterrows()):
        ax1.text(row['sharpe'] + 0.02, i, f"{row['sharpe']:.2f}", va='center', fontsize=9)

    # 2. Return distribution boxplot
    ax2 = axes[0, 1]
    strategies_ordered = strat_summary.index.tolist()
    data_for_box = [results_df[results_df['strategy'] == s]['total_return'].values
                    for s in strategies_ordered]
    bp = ax2.boxplot(data_for_box, vert=False, labels=strategies_ordered, patch_artist=True)
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax2.axvline(x=0, color='black', linewidth=0.5, linestyle='--')
    ax2.set_xlabel('Total Return (%)')
    ax2.set_title('Return Distribution by Strategy')

    # 3. Beat SPY percentage
    ax3 = axes[1, 0]
    beat_spy = results_df.groupby('strategy').apply(
        lambda x: (x['vs_spy'] > 0).mean() * 100
    ).reindex(strategies_ordered)

    colors3 = ['#e74c3c' if x < 50 else '#2ecc71' for x in beat_spy]
    ax3.barh(beat_spy.index, beat_spy.values, color=colors3)
    ax3.axvline(x=50, color='black', linewidth=1, linestyle='--', label='50% threshold')
    ax3.set_xlabel('% of Stocks Beating SPY')
    ax3.set_title('Strategy Alpha Generation')
    ax3.legend()

    # 4. Sharpe vs Return scatter
    ax4 = axes[1, 1]
    for strat in results_df['strategy'].unique():
        strat_data = results_df[results_df['strategy'] == strat]
        ax4.scatter(strat_data['sharpe'], strat_data['total_return'],
                   alpha=0.5, label=strat, s=30)
    ax4.axhline(y=0, color='gray', linewidth=0.5, linestyle='--')
    ax4.axvline(x=0, color='gray', linewidth=0.5, linestyle='--')
    ax4.set_xlabel('Sharpe Ratio')
    ax4.set_ylabel('Total Return (%)')
    ax4.set_title('Risk-Adjusted Returns')
    ax4.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)

    plt.tight_layout()
    plt.savefig(save_path / 'strategy_overview.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: strategy_overview.png")


def plot_category_heatmaps(results_df: pd.DataFrame, save_path: Path):
    """Plot heatmaps showing strategy performance by category."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))

    # 1. By Market Cap
    ax1 = axes[0, 0]
    pivot_cap = results_df.pivot_table(
        values='sharpe', index='strategy', columns='market_cap_cat', aggfunc='mean'
    )
    pivot_cap = pivot_cap[['mega', 'large', 'mid', 'small']].dropna(axis=1, how='all')
    im1 = ax1.imshow(pivot_cap.values, cmap='RdYlGn', aspect='auto', vmin=-0.5, vmax=1.5)
    ax1.set_xticks(range(len(pivot_cap.columns)))
    ax1.set_xticklabels(pivot_cap.columns)
    ax1.set_yticks(range(len(pivot_cap.index)))
    ax1.set_yticklabels(pivot_cap.index)
    ax1.set_title('Sharpe by Market Cap')
    plt.colorbar(im1, ax=ax1)

    for i in range(len(pivot_cap.index)):
        for j in range(len(pivot_cap.columns)):
            val = pivot_cap.iloc[i, j]
            if not np.isnan(val):
                ax1.text(j, i, f'{val:.2f}', ha='center', va='center', fontsize=8)

    # 2. By Volume
    ax2 = axes[0, 1]
    pivot_vol = results_df.pivot_table(
        values='sharpe', index='strategy', columns='volume_cat', aggfunc='mean'
    )
    pivot_vol = pivot_vol[['high', 'medium', 'low']].dropna(axis=1, how='all')
    im2 = ax2.imshow(pivot_vol.values, cmap='RdYlGn', aspect='auto', vmin=-0.5, vmax=1.5)
    ax2.set_xticks(range(len(pivot_vol.columns)))
    ax2.set_xticklabels(pivot_vol.columns)
    ax2.set_yticks(range(len(pivot_vol.index)))
    ax2.set_yticklabels(pivot_vol.index)
    ax2.set_title('Sharpe by Volume')
    plt.colorbar(im2, ax=ax2)

    for i in range(len(pivot_vol.index)):
        for j in range(len(pivot_vol.columns)):
            val = pivot_vol.iloc[i, j]
            if not np.isnan(val):
                ax2.text(j, i, f'{val:.2f}', ha='center', va='center', fontsize=8)

    # 3. By Volatility
    ax3 = axes[1, 0]
    pivot_volat = results_df.pivot_table(
        values='sharpe', index='strategy', columns='volatility_cat', aggfunc='mean'
    )
    pivot_volat = pivot_volat[['high', 'medium', 'low']].dropna(axis=1, how='all')
    im3 = ax3.imshow(pivot_volat.values, cmap='RdYlGn', aspect='auto', vmin=-0.5, vmax=1.5)
    ax3.set_xticks(range(len(pivot_volat.columns)))
    ax3.set_xticklabels(pivot_volat.columns)
    ax3.set_yticks(range(len(pivot_volat.index)))
    ax3.set_yticklabels(pivot_volat.index)
    ax3.set_title('Sharpe by Volatility')
    plt.colorbar(im3, ax=ax3)

    for i in range(len(pivot_volat.index)):
        for j in range(len(pivot_volat.columns)):
            val = pivot_volat.iloc[i, j]
            if not np.isnan(val):
                ax3.text(j, i, f'{val:.2f}', ha='center', va='center', fontsize=8)

    # 4. Top 10 sectors
    ax4 = axes[1, 1]
    sector_strat = results_df.groupby(['sector', 'strategy'])['sharpe'].mean().reset_index()
    top_combos = sector_strat.nlargest(15, 'sharpe')

    labels = [f"{row['strategy'][:12]}\n{row['sector'][:10]}" for _, row in top_combos.iterrows()]
    colors = plt.cm.RdYlGn((top_combos['sharpe'].values + 0.5) / 2)
    bars = ax4.barh(range(len(top_combos)), top_combos['sharpe'].values, color=colors)
    ax4.set_yticks(range(len(top_combos)))
    ax4.set_yticklabels(labels, fontsize=8)
    ax4.set_xlabel('Sharpe Ratio')
    ax4.set_title('Top 15 Strategy-Sector Combinations')
    ax4.invert_yaxis()

    plt.tight_layout()
    plt.savefig(save_path / 'category_heatmaps.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: category_heatmaps.png")


def plot_permutation_tests(
    top_results: list,
    price_data: dict,
    n_permutations: int,
    save_path: Path
):
    """Run and plot permutation tests for top strategies."""
    n_tests = len(top_results)
    cols = 3
    rows = (n_tests + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(15, 4 * rows))
    axes = axes.flatten() if n_tests > 1 else [axes]

    results_summary = []

    for idx, (symbol, strategy, expected_sharpe) in enumerate(top_results):
        ax = axes[idx]

        if symbol not in price_data:
            ax.text(0.5, 0.5, f'{symbol} data not available', ha='center', va='center')
            ax.set_title(f'{strategy} on {symbol}')
            continue

        df = price_data[symbol]

        # Run strategy
        strat_returns = run_strategy(strategy, df)

        # Get test period returns (last 30%)
        test_start = int(len(strat_returns) * 0.7)
        test_returns = strat_returns.iloc[test_start:]

        # Run permutation test
        observed, permuted, p_value = monte_carlo_permutation_test(test_returns, n_permutations)

        results_summary.append({
            'symbol': symbol,
            'strategy': strategy,
            'observed_sharpe': observed,
            'p_value': p_value,
            'significant': p_value < 0.05,
        })

        # Skip if no permuted data
        if len(permuted) == 0:
            ax.text(0.5, 0.5, 'Insufficient data', ha='center', va='center')
            ax.set_title(f'{strategy} on {symbol}')
            continue

        # Filter NaN values and plot histogram
        permuted = np.array([p for p in permuted if np.isfinite(p)])

        if len(permuted) < 10:
            ax.text(0.5, 0.5, 'Insufficient valid permutations', ha='center', va='center',
                    transform=ax.transAxes)
            ax.set_title(f'{strategy} on {symbol}')
            continue

        # Use linspace for bins to avoid issues
        perm_min, perm_max = permuted.min(), permuted.max()
        if perm_max - perm_min < 0.001:
            # All values nearly identical - expand range
            perm_min -= 0.5
            perm_max += 0.5

        bins = np.linspace(perm_min, perm_max, 31)  # 30 bins
        ax.hist(permuted, bins=bins, density=True, alpha=0.7, color='steelblue', label='Permuted')
        ax.axvline(observed, color='red', linewidth=2, label=f'Observed: {observed:.2f}')
        ax.axvline(np.percentile(permuted, 95), color='orange', linewidth=1.5,
                   linestyle='--', label='95th percentile')

        # Add significance annotation
        sig_text = "SIGNIFICANT" if p_value < 0.05 else "Not Significant"
        sig_color = 'green' if p_value < 0.05 else 'red'
        ax.text(0.95, 0.95, f'p={p_value:.3f}\n{sig_text}', transform=ax.transAxes,
                ha='right', va='top', fontsize=10, color=sig_color,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        ax.set_xlabel('Sharpe Ratio')
        ax.set_ylabel('Density')
        ax.set_title(f'{strategy} on {symbol}')
        ax.legend(loc='upper left', fontsize=8)

    # Hide empty subplots
    for idx in range(len(top_results), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle(f'Monte Carlo Permutation Tests ({n_permutations} permutations)', fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(save_path / 'permutation_tests.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: permutation_tests.png")

    return results_summary


def plot_random_comparison_all_lines(
    symbol: str,
    strategy: str,
    df: pd.DataFrame,
    n_random: int,
    save_path: Path,
):
    """Plot strategy vs ALL random trading lines."""
    # Run strategy
    strat_returns = run_strategy(strategy, df)
    test_start = int(len(df) * 0.7)
    test_df = df.iloc[test_start:]
    test_returns = strat_returns.iloc[test_start:]

    strat_cum = (1 + test_returns).cumprod()

    # Run random baselines
    random_cums = run_random_baseline(test_df, n_random)

    # Buy and hold
    bh_ret = test_df['close'].pct_change()
    bh_cum = (1 + bh_ret.fillna(0)).cumprod()

    # Plot
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot all random lines
    for i, rand_cum in enumerate(random_cums):
        rand_cum_aligned = rand_cum.reindex(test_df.index)
        ax.plot(rand_cum_aligned.index, rand_cum_aligned.values,
                color='gray', alpha=0.1, linewidth=0.5,
                label='Random' if i == 0 else None)

    # Plot buy and hold
    ax.plot(bh_cum.index, bh_cum.values, color='blue', linewidth=2,
            label=f'Buy & Hold ({(bh_cum.iloc[-1]-1)*100:.1f}%)')

    # Plot strategy
    ax.plot(strat_cum.index, strat_cum.values, color='red', linewidth=2.5,
            label=f'{strategy} ({(strat_cum.iloc[-1]-1)*100:.1f}%)')

    ax.axhline(y=1, color='black', linewidth=0.5, linestyle='--')
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Return')
    ax.set_title(f'{strategy} on {symbol} vs {n_random} Random Trading Strategies')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path / f'random_all_lines_{symbol}_{strategy}.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: random_all_lines_{symbol}_{strategy}.png")


def plot_random_comparison_quantiles(
    symbol: str,
    strategy: str,
    df: pd.DataFrame,
    n_random: int,
    save_path: Path,
):
    """Plot strategy vs random quantile bands."""
    # Run strategy
    strat_returns = run_strategy(strategy, df)
    test_start = int(len(df) * 0.7)
    test_df = df.iloc[test_start:]
    test_returns = strat_returns.iloc[test_start:]

    strat_cum = (1 + test_returns).cumprod()

    # Run random baselines
    random_cums = run_random_baseline(test_df, n_random)

    # Align all random cumulative returns
    random_matrix = pd.DataFrame(index=test_df.index)
    for i, rand_cum in enumerate(random_cums):
        random_matrix[f'rand_{i}'] = rand_cum.reindex(test_df.index)

    # Calculate quantiles
    quantiles = {
        'q5': random_matrix.quantile(0.05, axis=1),
        'q25': random_matrix.quantile(0.25, axis=1),
        'q50': random_matrix.quantile(0.50, axis=1),
        'q75': random_matrix.quantile(0.75, axis=1),
        'q95': random_matrix.quantile(0.95, axis=1),
    }

    # Buy and hold
    bh_ret = test_df['close'].pct_change()
    bh_cum = (1 + bh_ret.fillna(0)).cumprod()

    # Plot
    fig, ax = plt.subplots(figsize=(14, 8))

    # Fill between quantiles
    ax.fill_between(test_df.index, quantiles['q5'], quantiles['q95'],
                    alpha=0.2, color='gray', label='5-95% Random Range')
    ax.fill_between(test_df.index, quantiles['q25'], quantiles['q75'],
                    alpha=0.3, color='gray', label='25-75% Random Range')

    # Plot median random
    ax.plot(test_df.index, quantiles['q50'], color='gray', linewidth=1.5,
            linestyle='--', label='Median Random')

    # Plot buy and hold
    ax.plot(bh_cum.index, bh_cum.values, color='blue', linewidth=2,
            label=f'Buy & Hold ({(bh_cum.iloc[-1]-1)*100:.1f}%)')

    # Plot strategy
    ax.plot(strat_cum.index, strat_cum.values, color='red', linewidth=2.5,
            label=f'{strategy} ({(strat_cum.iloc[-1]-1)*100:.1f}%)')

    # Calculate percentile rank of strategy at end
    final_strat = strat_cum.iloc[-1]
    final_randoms = random_matrix.iloc[-1].values
    pct_rank = (final_randoms < final_strat).mean() * 100

    ax.text(0.02, 0.98, f'Strategy beats {pct_rank:.0f}% of random traders',
            transform=ax.transAxes, fontsize=12, va='top',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.axhline(y=1, color='black', linewidth=0.5, linestyle='--')
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Return')
    ax.set_title(f'{strategy} on {symbol} vs Random Trading Quantiles')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path / f'random_quantiles_{symbol}_{strategy}.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: random_quantiles_{symbol}_{strategy}.png")


def plot_top_performers(results_df: pd.DataFrame, price_data: dict, save_path: Path):
    """Plot equity curves for top performing strategy-symbol combinations."""
    top_20 = results_df.nlargest(12, 'sharpe')

    fig, axes = plt.subplots(4, 3, figsize=(16, 14))
    axes = axes.flatten()

    for idx, (_, row) in enumerate(top_20.iterrows()):
        ax = axes[idx]
        symbol = row['symbol']
        strategy = row['strategy']

        if symbol not in price_data:
            ax.text(0.5, 0.5, f'{symbol} not available', ha='center', va='center')
            ax.set_title(f'{strategy} on {symbol}')
            continue

        df = price_data[symbol]

        # Run strategy
        strat_returns = run_strategy(strategy, df)
        test_start = int(len(df) * 0.7)
        test_df = df.iloc[test_start:]
        test_returns = strat_returns.iloc[test_start:]

        strat_cum = (1 + test_returns).cumprod()
        bh_ret = test_df['close'].pct_change()
        bh_cum = (1 + bh_ret.fillna(0)).cumprod()

        ax.plot(strat_cum.index, strat_cum.values, color='red', linewidth=1.5,
                label=f'Strategy ({(strat_cum.iloc[-1]-1)*100:.0f}%)')
        ax.plot(bh_cum.index, bh_cum.values, color='blue', linewidth=1.5, alpha=0.7,
                label=f'B&H ({(bh_cum.iloc[-1]-1)*100:.0f}%)')

        ax.axhline(y=1, color='gray', linewidth=0.5, linestyle='--')
        ax.set_title(f'{strategy[:15]} | {symbol}\nSharpe: {row["sharpe"]:.2f}', fontsize=10)
        ax.legend(fontsize=8, loc='upper left')
        ax.tick_params(axis='x', labelsize=7)

    plt.suptitle('Top 12 Strategy-Symbol Combinations by Sharpe Ratio', fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(save_path / 'top_performers.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: top_performers.png")


def plot_comprehensive_summary(results_df: pd.DataFrame, perm_results: list, save_path: Path):
    """Create a comprehensive summary dashboard."""
    fig = plt.figure(figsize=(20, 12))
    gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.3, wspace=0.3)

    # 1. Strategy Rankings (top left, spans 2 cols)
    ax1 = fig.add_subplot(gs[0, :2])
    strat_summary = results_df.groupby('strategy').agg({
        'sharpe': 'mean',
        'total_return': 'mean',
    }).sort_values('sharpe', ascending=True)

    colors = ['#e74c3c' if x < 0 else '#2ecc71' for x in strat_summary['sharpe']]
    ax1.barh(strat_summary.index, strat_summary['sharpe'], color=colors)
    ax1.axvline(x=0, color='black', linewidth=0.5)
    ax1.set_xlabel('Average Sharpe Ratio')
    ax1.set_title('Strategy Performance Ranking', fontsize=12, fontweight='bold')

    # 2. Win rates (top right)
    ax2 = fig.add_subplot(gs[0, 2])
    beat_random = results_df.groupby('strategy').apply(
        lambda x: (x['vs_random'] > 0).mean() * 100
    ).sort_values(ascending=True)

    colors2 = ['#e74c3c' if x < 50 else '#2ecc71' for x in beat_random]
    ax2.barh(beat_random.index, beat_random.values, color=colors2)
    ax2.axvline(x=50, color='black', linewidth=1, linestyle='--')
    ax2.set_xlabel('% Beat Random')
    ax2.set_title('Beat Random Rate', fontsize=12, fontweight='bold')

    # 3. Permutation test results (top right corner)
    ax3 = fig.add_subplot(gs[0, 3])
    if perm_results:
        perm_df = pd.DataFrame(perm_results)
        sig_count = perm_df['significant'].sum()
        total = len(perm_df)

        ax3.pie([sig_count, total - sig_count],
                labels=[f'Significant\n({sig_count})', f'Not Sig\n({total-sig_count})'],
                colors=['#2ecc71', '#e74c3c'], autopct='%1.0f%%',
                startangle=90)
        ax3.set_title('MCPT Results\n(p < 0.05)', fontsize=12, fontweight='bold')
    else:
        ax3.text(0.5, 0.5, 'No permutation\nresults', ha='center', va='center')

    # 4. Market cap heatmap (middle left)
    ax4 = fig.add_subplot(gs[1, :2])
    pivot_cap = results_df.pivot_table(
        values='sharpe', index='strategy', columns='market_cap_cat', aggfunc='mean'
    )
    if 'mega' in pivot_cap.columns:
        pivot_cap = pivot_cap[['mega', 'large', 'mid', 'small']].dropna(axis=1, how='all')
    im = ax4.imshow(pivot_cap.values, cmap='RdYlGn', aspect='auto', vmin=-0.5, vmax=1.5)
    ax4.set_xticks(range(len(pivot_cap.columns)))
    ax4.set_xticklabels(pivot_cap.columns)
    ax4.set_yticks(range(len(pivot_cap.index)))
    ax4.set_yticklabels(pivot_cap.index, fontsize=9)
    ax4.set_title('Sharpe by Market Cap Category', fontsize=12, fontweight='bold')
    plt.colorbar(im, ax=ax4)

    # 5. Volatility heatmap (middle right)
    ax5 = fig.add_subplot(gs[1, 2:])
    pivot_vol = results_df.pivot_table(
        values='sharpe', index='strategy', columns='volatility_cat', aggfunc='mean'
    )
    if 'high' in pivot_vol.columns:
        pivot_vol = pivot_vol[['high', 'medium', 'low']].dropna(axis=1, how='all')
    im2 = ax5.imshow(pivot_vol.values, cmap='RdYlGn', aspect='auto', vmin=-0.5, vmax=1.5)
    ax5.set_xticks(range(len(pivot_vol.columns)))
    ax5.set_xticklabels(pivot_vol.columns)
    ax5.set_yticks(range(len(pivot_vol.index)))
    ax5.set_yticklabels(pivot_vol.index, fontsize=9)
    ax5.set_title('Sharpe by Volatility Category', fontsize=12, fontweight='bold')
    plt.colorbar(im2, ax=ax5)

    # 6. Top performers table (bottom)
    ax6 = fig.add_subplot(gs[2, :])
    ax6.axis('off')

    top_10 = results_df.nlargest(10, 'sharpe')[
        ['symbol', 'strategy', 'sharpe', 'total_return', 'vs_spy', 'sector', 'market_cap_cat']
    ]

    table_data = []
    for _, row in top_10.iterrows():
        table_data.append([
            row['symbol'],
            row['strategy'][:18],
            f"{row['sharpe']:.2f}",
            f"{row['total_return']:+.1f}%",
            f"{row['vs_spy']:+.1f}%",
            row['sector'][:12],
            row['market_cap_cat'],
        ])

    table = ax6.table(
        cellText=table_data,
        colLabels=['Symbol', 'Strategy', 'Sharpe', 'Return', 'vs SPY', 'Sector', 'Mkt Cap'],
        loc='center',
        cellLoc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)
    ax6.set_title('Top 10 Strategy-Symbol Combinations', fontsize=12, fontweight='bold', pad=20)

    plt.suptitle('Renaissance Lite - Universe Analysis Dashboard', fontsize=16, fontweight='bold', y=0.98)
    plt.savefig(save_path / 'comprehensive_dashboard.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: comprehensive_dashboard.png")


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def run_visualizations(n_permutations: int = 500, n_random: int = 200):
    """Run all visualizations."""
    print("="*70)
    print("STRATEGY VISUALIZATION & PERMUTATION TESTING")
    print("="*70)

    # Setup
    save_path = _RESULTS_DIR / "visualizations"
    save_path.mkdir(parents=True, exist_ok=True)

    # Load results
    print("\n[1/7] Loading analysis results...")
    results_df, category_analysis, profiles = load_analysis_results()
    print(f"  Loaded {len(results_df)} backtest results")

    # Get top strategies for detailed analysis
    top_results = results_df.nlargest(9, 'sharpe')[['symbol', 'strategy', 'sharpe']].values.tolist()

    # Fetch price data for top symbols
    print("\n[2/7] Fetching price data for top performers...")
    top_symbols = list(set([r[0] for r in top_results]))
    # Add a few more for diversity
    additional = ['NVDA', 'TSLA', 'GOOGL', 'JPM', 'XOM']
    all_symbols = list(set(top_symbols + additional))
    price_data = fetch_price_data(all_symbols)
    print(f"  Fetched {len(price_data)} symbols")

    # 1. Strategy overview
    print("\n[3/7] Creating strategy overview plots...")
    plot_strategy_overview(results_df, save_path)

    # 2. Category heatmaps
    print("\n[4/7] Creating category heatmaps...")
    plot_category_heatmaps(results_df, save_path)

    # 3. Permutation tests
    print(f"\n[5/7] Running permutation tests ({n_permutations} permutations)...")
    perm_results = plot_permutation_tests(top_results, price_data, n_permutations, save_path)

    # Print permutation summary
    print("\n  Permutation Test Results:")
    for r in perm_results:
        sig = "✓" if r['significant'] else "✗"
        print(f"    {sig} {r['strategy'][:15]} on {r['symbol']}: "
              f"Sharpe={r['observed_sharpe']:.2f}, p={r['p_value']:.3f}")

    # 4. Random comparison plots
    print(f"\n[6/7] Creating random comparison plots ({n_random} simulations)...")

    # Pick top 3 for detailed random comparison
    for symbol, strategy, _ in top_results[:3]:
        if symbol in price_data:
            plot_random_comparison_all_lines(symbol, strategy, price_data[symbol], n_random, save_path)
            plot_random_comparison_quantiles(symbol, strategy, price_data[symbol], n_random, save_path)

    # 5. Top performers
    print("\n[7/7] Creating top performers and dashboard...")
    plot_top_performers(results_df, price_data, save_path)
    plot_comprehensive_summary(results_df, perm_results, save_path)

    print("\n" + "="*70)
    print("VISUALIZATION COMPLETE")
    print("="*70)
    print(f"\nAll plots saved to: {save_path}")
    print("\nFiles generated:")
    for f in sorted(save_path.glob("*.png")):
        print(f"  - {f.name}")

    return perm_results


if __name__ == "__main__":
    results = run_visualizations(n_permutations=500, n_random=200)
