"""
Strategy Comparison Plots

Comprehensive visualization for strategy validation:
1. Strategy vs Random vs Buy-and-Hold equity curves
2. PDT compliant vs non-PDT strategies comparison
3. MCPT permutation distributions
4. Bootstrap confidence interval visualization
5. Regime-conditional performance
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Matplotlib imports with fallback
HAS_MATPLOTLIB = False
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.figure import Figure
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    Figure = Any
except Exception:
    Figure = Any


@dataclass
class PlotConfig:
    """Configuration for plot generation."""
    figsize: tuple[int, int] = (12, 8)
    dpi: int = 150
    style: str = "default"
    save_format: str = "png"

    # Colors
    strategy_color: str = "#ef4444"  # Red
    benchmark_color: str = "#3b82f6"  # Blue
    random_color: str = "#9ca3af"  # Gray
    pdt_color: str = "#22c55e"  # Green
    non_pdt_color: str = "#f59e0b"  # Amber
    significant_color: str = "#22c55e"  # Green
    not_significant_color: str = "#ef4444"  # Red


class StrategyPlotter:
    """
    Generate comprehensive strategy comparison plots.

    Creates visualizations for:
    - Equity curves (strategy vs random vs buy-and-hold)
    - PDT compliant vs non-PDT performance
    - MCPT permutation distributions
    - Bootstrap confidence intervals
    """

    def __init__(self, config: PlotConfig | None = None, output_dir: Path | None = None):
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required. Install with: pip install matplotlib")

        self.config = config or PlotConfig()
        self.output_dir = output_dir or Path.home() / "quant_results" / "plots"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_strategy_vs_random_vs_buyhold(
        self,
        strategy_returns: pd.Series,
        price_data: pd.DataFrame,
        strategy_name: str = "Strategy",
        symbol: str = "Symbol",
        n_random: int = 100,
        save: bool = True,
    ) -> Figure:
        """
        Plot strategy equity curve vs random trades vs buy-and-hold.

        Shows:
        - Strategy cumulative returns (red line)
        - Buy-and-hold cumulative returns (blue line)
        - Random trading simulations (gray shaded area with quantiles)

        Args:
            strategy_returns: Strategy daily returns
            price_data: OHLCV DataFrame with 'close' column
            strategy_name: Name for plot title
            symbol: Symbol name for plot title
            n_random: Number of random simulations
            save: Whether to save the plot

        Returns:
            Matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)

        # Align data
        if 'close' in price_data.columns:
            close = price_data['close']
        elif 'Close' in price_data.columns:
            close = price_data['Close']
        else:
            raise ValueError("price_data must have 'close' or 'Close' column")

        # Buy and hold
        bh_returns = close.pct_change().dropna()
        bh_cum = (1 + bh_returns).cumprod()

        # Strategy
        strat_returns = strategy_returns.reindex(bh_returns.index).fillna(0)
        strat_cum = (1 + strat_returns).cumprod()

        # Random simulations
        random_cums = []
        for _ in range(n_random):
            random_positions = pd.Series(
                np.random.choice([-1, 0, 1], size=len(bh_returns), p=[0.3, 0.4, 0.3]),
                index=bh_returns.index
            )
            random_returns = random_positions.shift(1).fillna(0) * bh_returns
            random_cum = (1 + random_returns).cumprod()
            random_cums.append(random_cum)

        # Stack random results
        random_df = pd.DataFrame({f'r{i}': rc for i, rc in enumerate(random_cums)})
        random_5 = random_df.quantile(0.05, axis=1)
        random_25 = random_df.quantile(0.25, axis=1)
        random_50 = random_df.quantile(0.50, axis=1)
        random_75 = random_df.quantile(0.75, axis=1)
        random_95 = random_df.quantile(0.95, axis=1)

        # Plot random quantiles
        ax.fill_between(random_5.index, random_5, random_95,
                       alpha=0.15, color=self.config.random_color, label='5-95% Random')
        ax.fill_between(random_25.index, random_25, random_75,
                       alpha=0.25, color=self.config.random_color, label='25-75% Random')
        ax.plot(random_50.index, random_50, color=self.config.random_color,
               linestyle='--', linewidth=1, label='Median Random')

        # Plot buy and hold
        ax.plot(bh_cum.index, bh_cum, color=self.config.benchmark_color,
               linewidth=2, label=f'Buy & Hold ({(bh_cum.iloc[-1]-1)*100:.1f}%)')

        # Plot strategy
        ax.plot(strat_cum.index, strat_cum, color=self.config.strategy_color,
               linewidth=2.5, label=f'{strategy_name} ({(strat_cum.iloc[-1]-1)*100:.1f}%)')

        # Annotations
        final_strat = strat_cum.iloc[-1]
        final_randoms = random_df.iloc[-1].values
        pct_rank = (final_randoms < final_strat).mean() * 100

        ax.text(0.02, 0.98, f'Beats {pct_rank:.0f}% of random traders',
               transform=ax.transAxes, fontsize=11, va='top', fontweight='bold',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))

        ax.axhline(y=1, color='black', linewidth=0.5, linestyle=':')
        ax.set_xlabel('Date', fontsize=11)
        ax.set_ylabel('Cumulative Return', fontsize=11)
        ax.set_title(f'{strategy_name} on {symbol}\nvs Random Trading vs Buy-and-Hold',
                    fontsize=13, fontweight='bold')
        ax.legend(loc='upper left', framealpha=0.9)
        ax.grid(True, alpha=0.3)

        # Clean up
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save:
            filename = f"equity_curve_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig

    def plot_pdt_comparison(
        self,
        returns_by_holding: dict[int, pd.Series],
        strategy_name: str = "Strategy",
        symbol: str = "Symbol",
        pdt_min_days: int = 2,
        save: bool = True,
    ) -> Figure:
        """
        Compare PDT-compliant vs non-PDT holding periods.

        Args:
            returns_by_holding: Dict mapping holding days to returns series
            strategy_name: Strategy name for title
            symbol: Symbol for title
            pdt_min_days: Minimum days for PDT compliance
            save: Whether to save

        Returns:
            Matplotlib Figure
        """
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Left: Equity curves
        ax1 = axes[0]

        for hold_days, returns in sorted(returns_by_holding.items()):
            cum_ret = (1 + returns).cumprod()
            is_pdt = hold_days >= pdt_min_days
            color = self.config.pdt_color if is_pdt else self.config.non_pdt_color
            linestyle = '-' if is_pdt else '--'
            label = f'{hold_days}d hold ({"PDT" if is_pdt else "non-PDT"})'

            ax1.plot(cum_ret.index, cum_ret, color=color, linestyle=linestyle,
                    linewidth=2 if is_pdt else 1.5, alpha=0.9 if is_pdt else 0.6,
                    label=label)

        ax1.axhline(y=1, color='black', linewidth=0.5, linestyle=':')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cumulative Return')
        ax1.set_title('Equity Curves by Holding Period', fontweight='bold')
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # Right: Sharpe comparison bar chart
        ax2 = axes[1]

        hold_days_list = sorted(returns_by_holding.keys())
        sharpes = []
        colors = []

        for hold_days in hold_days_list:
            returns = returns_by_holding[hold_days]
            sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            sharpes.append(sharpe)
            is_pdt = hold_days >= pdt_min_days
            colors.append(self.config.pdt_color if is_pdt else self.config.non_pdt_color)

        bars = ax2.bar([f'{d}d' for d in hold_days_list], sharpes, color=colors, edgecolor='white')

        # Add value labels
        for bar, sharpe in zip(bars, sharpes):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2, height + 0.05,
                    f'{sharpe:.2f}', ha='center', fontsize=10)

        # Add PDT line
        ax2.axhline(y=0, color='black', linewidth=0.5)

        # Legend
        pdt_patch = mpatches.Patch(color=self.config.pdt_color, label=f'PDT Compliant (≥{pdt_min_days}d)')
        non_pdt_patch = mpatches.Patch(color=self.config.non_pdt_color, label=f'Non-PDT (<{pdt_min_days}d)')
        ax2.legend(handles=[pdt_patch, non_pdt_patch], loc='upper right')

        ax2.set_xlabel('Holding Period')
        ax2.set_ylabel('Sharpe Ratio')
        ax2.set_title('Sharpe Ratio by Holding Period', fontweight='bold')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        plt.suptitle(f'{strategy_name} on {symbol}: PDT Compliance Analysis',
                    fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()

        if save:
            filename = f"pdt_comparison_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig

    def plot_mcpt_distribution(
        self,
        original_sharpe: float,
        permuted_sharpes: list[float],
        p_value: float,
        strategy_name: str = "Strategy",
        symbol: str = "Symbol",
        save: bool = True,
    ) -> Figure:
        """
        Plot MCPT permutation distribution with strategy value marked.

        Args:
            original_sharpe: Observed strategy Sharpe ratio
            permuted_sharpes: List of Sharpe ratios from permuted data
            p_value: Calculated p-value
            strategy_name: Strategy name
            symbol: Symbol name
            save: Whether to save

        Returns:
            Matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=self.config.figsize)

        is_significant = p_value < 0.05
        perm_array = np.array(permuted_sharpes)

        # Histogram
        n, bins, patches = ax.hist(
            perm_array, bins=50, density=True, alpha=0.7,
            color='#3b82f6', edgecolor='white', linewidth=0.5,
            label=f'Permuted Distribution (n={len(perm_array)})'
        )

        # Percentiles
        p95 = np.percentile(perm_array, 95)
        p99 = np.percentile(perm_array, 99)

        # Original value line
        ax.axvline(original_sharpe, color=self.config.strategy_color,
                  linewidth=2.5, linestyle='--', label=f'Strategy: {original_sharpe:.3f}')

        # 95th percentile line
        ax.axvline(p95, color='orange', linewidth=1.5, linestyle=':',
                  label=f'95th percentile: {p95:.3f}')

        # Shade significance region
        if original_sharpe > p95:
            ax.axvspan(p95, max(perm_array.max() * 1.05, original_sharpe * 1.1),
                      alpha=0.15, color=self.config.significant_color)

        # Significance annotation
        sig_text = "SIGNIFICANT" if is_significant else "Not Significant"
        sig_color = self.config.significant_color if is_significant else self.config.not_significant_color

        props = dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor=sig_color, linewidth=2)
        ax.text(0.97, 0.95, f'p-value: {p_value:.4f}\n{sig_text}',
               transform=ax.transAxes, fontsize=12, fontweight='bold',
               color=sig_color, va='top', ha='right', bbox=props)

        ax.set_xlabel('Sharpe Ratio', fontsize=11)
        ax.set_ylabel('Density', fontsize=11)
        ax.set_title(f'MCPT Permutation Test: {strategy_name} on {symbol}',
                    fontsize=13, fontweight='bold')
        ax.legend(loc='upper left', framealpha=0.9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save:
            filename = f"mcpt_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig

    def plot_bootstrap_ci(
        self,
        returns: pd.Series,
        bootstrap_sharpes: list[float],
        ci_lower: float,
        ci_upper: float,
        strategy_name: str = "Strategy",
        symbol: str = "Symbol",
        save: bool = True,
    ) -> Figure:
        """
        Plot bootstrap Sharpe ratio distribution with confidence interval.

        Args:
            returns: Strategy returns
            bootstrap_sharpes: List of bootstrapped Sharpe ratios
            ci_lower: Lower CI bound
            ci_upper: Upper CI bound
            strategy_name: Strategy name
            symbol: Symbol name
            save: Whether to save

        Returns:
            Matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # Observed Sharpe
        observed_sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

        # Histogram
        ax.hist(bootstrap_sharpes, bins=50, density=True, alpha=0.7,
               color='#8b5cf6', edgecolor='white', linewidth=0.5,
               label=f'Bootstrap Distribution (n={len(bootstrap_sharpes)})')

        # Observed value
        ax.axvline(observed_sharpe, color=self.config.strategy_color,
                  linewidth=2.5, linestyle='--', label=f'Observed: {observed_sharpe:.3f}')

        # CI bounds
        ax.axvline(ci_lower, color='#22c55e', linewidth=2, linestyle='-',
                  label=f'95% CI: [{ci_lower:.3f}, {ci_upper:.3f}]')
        ax.axvline(ci_upper, color='#22c55e', linewidth=2, linestyle='-')

        # Shade CI region
        ax.axvspan(ci_lower, ci_upper, alpha=0.2, color='#22c55e')

        # Zero line
        ax.axvline(0, color='black', linewidth=1, linestyle=':')

        # Annotation
        ci_includes_zero = ci_lower <= 0 <= ci_upper
        annotation = "CI includes zero" if ci_includes_zero else "CI excludes zero"
        color = self.config.not_significant_color if ci_includes_zero else self.config.significant_color

        ax.text(0.97, 0.95, annotation, transform=ax.transAxes,
               fontsize=11, fontweight='bold', color=color, va='top', ha='right',
               bbox=dict(boxstyle='round', facecolor='white', edgecolor=color, linewidth=2))

        ax.set_xlabel('Sharpe Ratio', fontsize=11)
        ax.set_ylabel('Density', fontsize=11)
        ax.set_title(f'Bootstrap Sharpe Confidence Interval: {strategy_name} on {symbol}',
                    fontsize=13, fontweight='bold')
        ax.legend(loc='upper left', framealpha=0.9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save:
            filename = f"bootstrap_ci_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig

    def plot_comprehensive_validation(
        self,
        strategy_returns: pd.Series,
        price_data: pd.DataFrame,
        returns_by_holding: dict[int, pd.Series] | None,
        mcpt_sharpes: list[float] | None,
        mcpt_p_value: float | None,
        bootstrap_sharpes: list[float] | None,
        ci_lower: float | None,
        ci_upper: float | None,
        strategy_name: str = "Strategy",
        symbol: str = "Symbol",
        n_random: int = 50,
        save: bool = True,
    ) -> Figure:
        """
        Create comprehensive 2x2 validation dashboard.

        Args:
            strategy_returns: Strategy daily returns
            price_data: OHLCV data
            returns_by_holding: Dict of holding period -> returns (optional)
            mcpt_sharpes: List of permuted Sharpe ratios (optional)
            mcpt_p_value: MCPT p-value (optional)
            bootstrap_sharpes: List of bootstrapped Sharpe ratios (optional)
            ci_lower, ci_upper: Confidence interval bounds (optional)
            strategy_name: Strategy name
            symbol: Symbol name
            n_random: Number of random simulations
            save: Whether to save

        Returns:
            Matplotlib Figure
        """
        fig = plt.figure(figsize=(16, 12))
        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.25)

        # Get close price
        if 'close' in price_data.columns:
            close = price_data['close']
        elif 'Close' in price_data.columns:
            close = price_data['Close']
        else:
            close = price_data.iloc[:, 0]

        bh_returns = close.pct_change().dropna()

        # ========== Panel 1: Strategy vs Random vs Buy-and-Hold ==========
        ax1 = fig.add_subplot(gs[0, 0])

        strat_returns = strategy_returns.reindex(bh_returns.index).fillna(0)
        strat_cum = (1 + strat_returns).cumprod()
        bh_cum = (1 + bh_returns).cumprod()

        # Quick random simulations
        random_df = pd.DataFrame()
        for i in range(n_random):
            rp = pd.Series(np.random.choice([-1, 0, 1], len(bh_returns), p=[0.3, 0.4, 0.3]), index=bh_returns.index)
            random_df[f'r{i}'] = (1 + rp.shift(1).fillna(0) * bh_returns).cumprod()

        random_5, random_95 = random_df.quantile(0.05, axis=1), random_df.quantile(0.95, axis=1)
        random_50 = random_df.quantile(0.50, axis=1)

        ax1.fill_between(random_5.index, random_5, random_95, alpha=0.2, color='gray', label='5-95% Random')
        ax1.plot(random_50.index, random_50, color='gray', linestyle='--', linewidth=1, label='Median Random')
        ax1.plot(bh_cum.index, bh_cum, color=self.config.benchmark_color, linewidth=2,
                label=f'Buy & Hold ({(bh_cum.iloc[-1]-1)*100:.1f}%)')
        ax1.plot(strat_cum.index, strat_cum, color=self.config.strategy_color, linewidth=2.5,
                label=f'Strategy ({(strat_cum.iloc[-1]-1)*100:.1f}%)')

        ax1.axhline(y=1, color='black', linewidth=0.5, linestyle=':')
        ax1.set_title('Strategy vs Random vs Buy-and-Hold', fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # ========== Panel 2: PDT Comparison ==========
        ax2 = fig.add_subplot(gs[0, 1])

        if returns_by_holding:
            hold_days = sorted(returns_by_holding.keys())
            sharpes = []
            colors = []
            for hd in hold_days:
                ret = returns_by_holding[hd]
                s = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
                sharpes.append(s)
                colors.append(self.config.pdt_color if hd >= 2 else self.config.non_pdt_color)

            bars = ax2.bar([f'{d}d' for d in hold_days], sharpes, color=colors, edgecolor='white')
            for bar, s in zip(bars, sharpes):
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03, f'{s:.2f}', ha='center', fontsize=9)

            ax2.axhline(y=0, color='black', linewidth=0.5)
            pdt_patch = mpatches.Patch(color=self.config.pdt_color, label='PDT (≥2d)')
            non_pdt_patch = mpatches.Patch(color=self.config.non_pdt_color, label='Non-PDT')
            ax2.legend(handles=[pdt_patch, non_pdt_patch], loc='upper right', fontsize=8)
        else:
            ax2.text(0.5, 0.5, 'PDT data not available', ha='center', va='center', fontsize=12)

        ax2.set_title('PDT Holding Period Analysis', fontweight='bold')
        ax2.set_xlabel('Holding Period')
        ax2.set_ylabel('Sharpe Ratio')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        # ========== Panel 3: MCPT Distribution ==========
        ax3 = fig.add_subplot(gs[1, 0])

        if mcpt_sharpes and mcpt_p_value is not None:
            observed = strat_returns.mean() / strat_returns.std() * np.sqrt(252) if strat_returns.std() > 0 else 0
            perm_array = np.array(mcpt_sharpes)

            ax3.hist(perm_array, bins=40, density=True, alpha=0.7, color='#3b82f6', edgecolor='white')
            ax3.axvline(observed, color=self.config.strategy_color, linewidth=2.5, linestyle='--', label=f'Strategy: {observed:.2f}')
            ax3.axvline(np.percentile(perm_array, 95), color='orange', linewidth=1.5, linestyle=':', label='95th pct')

            is_sig = mcpt_p_value < 0.05
            sig_color = self.config.significant_color if is_sig else self.config.not_significant_color
            ax3.text(0.97, 0.95, f'p={mcpt_p_value:.4f}\n{"SIG" if is_sig else "Not Sig"}',
                    transform=ax3.transAxes, fontsize=10, fontweight='bold', color=sig_color,
                    va='top', ha='right', bbox=dict(boxstyle='round', facecolor='white', edgecolor=sig_color))
            ax3.legend(loc='upper left', fontsize=8)
        else:
            ax3.text(0.5, 0.5, 'MCPT data not available', ha='center', va='center', fontsize=12)

        ax3.set_title('MCPT Permutation Test', fontweight='bold')
        ax3.set_xlabel('Sharpe Ratio')
        ax3.set_ylabel('Density')
        ax3.spines['top'].set_visible(False)
        ax3.spines['right'].set_visible(False)

        # ========== Panel 4: Bootstrap CI ==========
        ax4 = fig.add_subplot(gs[1, 1])

        if bootstrap_sharpes and ci_lower is not None and ci_upper is not None:
            observed = strat_returns.mean() / strat_returns.std() * np.sqrt(252) if strat_returns.std() > 0 else 0

            ax4.hist(bootstrap_sharpes, bins=40, density=True, alpha=0.7, color='#8b5cf6', edgecolor='white')
            ax4.axvline(observed, color=self.config.strategy_color, linewidth=2.5, linestyle='--', label=f'Observed: {observed:.2f}')
            ax4.axvline(ci_lower, color='#22c55e', linewidth=2, label=f'95% CI: [{ci_lower:.2f}, {ci_upper:.2f}]')
            ax4.axvline(ci_upper, color='#22c55e', linewidth=2)
            ax4.axvspan(ci_lower, ci_upper, alpha=0.2, color='#22c55e')
            ax4.axvline(0, color='black', linewidth=1, linestyle=':')

            ci_includes_zero = ci_lower <= 0 <= ci_upper
            ax4.text(0.97, 0.95, "CI includes 0" if ci_includes_zero else "CI > 0",
                    transform=ax4.transAxes, fontsize=10, fontweight='bold',
                    color=self.config.not_significant_color if ci_includes_zero else self.config.significant_color,
                    va='top', ha='right', bbox=dict(boxstyle='round', facecolor='white'))
            ax4.legend(loc='upper left', fontsize=8)
        else:
            ax4.text(0.5, 0.5, 'Bootstrap data not available', ha='center', va='center', fontsize=12)

        ax4.set_title('Bootstrap Confidence Interval', fontweight='bold')
        ax4.set_xlabel('Sharpe Ratio')
        ax4.set_ylabel('Density')
        ax4.spines['top'].set_visible(False)
        ax4.spines['right'].set_visible(False)

        # Main title
        plt.suptitle(f'Comprehensive Validation: {strategy_name} on {symbol}',
                    fontsize=15, fontweight='bold', y=1.01)

        plt.tight_layout()

        if save:
            filename = f"validation_dashboard_{strategy_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig

    def plot_multi_strategy_comparison(
        self,
        strategies: dict[str, pd.Series],
        price_data: pd.DataFrame,
        save: bool = True,
    ) -> Figure:
        """
        Compare multiple strategies on the same chart.

        Args:
            strategies: Dict of strategy_name -> returns series
            price_data: OHLCV data
            save: Whether to save

        Returns:
            Matplotlib Figure
        """
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Get close
        if 'close' in price_data.columns:
            close = price_data['close']
        elif 'Close' in price_data.columns:
            close = price_data['Close']
        else:
            close = price_data.iloc[:, 0]

        bh_returns = close.pct_change().dropna()
        bh_cum = (1 + bh_returns).cumprod()

        # Color cycle
        colors = plt.cm.tab10(np.linspace(0, 1, len(strategies)))

        # Left: Equity curves
        ax1 = axes[0]
        ax1.plot(bh_cum.index, bh_cum, color='black', linewidth=2, linestyle='--', label='Buy & Hold')

        sharpes = {}
        for (name, returns), color in zip(strategies.items(), colors):
            ret = returns.reindex(bh_returns.index).fillna(0)
            cum = (1 + ret).cumprod()
            ax1.plot(cum.index, cum, color=color, linewidth=1.5, label=f'{name} ({(cum.iloc[-1]-1)*100:.1f}%)')
            sharpes[name] = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0

        ax1.axhline(y=1, color='gray', linewidth=0.5, linestyle=':')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cumulative Return')
        ax1.set_title('Strategy Equity Curves', fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # Right: Sharpe comparison
        ax2 = axes[1]
        sorted_sharpes = sorted(sharpes.items(), key=lambda x: x[1], reverse=True)
        names = [s[0] for s in sorted_sharpes]
        values = [s[1] for s in sorted_sharpes]
        bar_colors = [self.config.significant_color if v > 0.5 else self.config.not_significant_color for v in values]

        bars = ax2.barh(names, values, color=bar_colors, edgecolor='white')
        for bar, v in zip(bars, values):
            ax2.text(v + 0.02, bar.get_y() + bar.get_height()/2, f'{v:.2f}', va='center', fontsize=9)

        ax2.axvline(x=0, color='black', linewidth=0.5)
        ax2.axvline(x=0.5, color='orange', linewidth=1, linestyle='--', label='Min threshold (0.5)')
        ax2.set_xlabel('Sharpe Ratio')
        ax2.set_title('Sharpe Ratio Comparison', fontweight='bold')
        ax2.legend(loc='lower right', fontsize=8)
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        plt.tight_layout()

        if save:
            filename = f"multi_strategy_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.config.save_format}"
            fig.savefig(self.output_dir / filename, dpi=self.config.dpi, bbox_inches='tight')

        return fig


# Convenience functions
def plot_strategy_validation(
    strategy_returns: pd.Series,
    price_data: pd.DataFrame,
    strategy_name: str = "Strategy",
    symbol: str = "Symbol",
    n_random: int = 100,
    output_dir: Path | None = None,
) -> Figure:
    """Quick function to plot strategy vs random vs buy-and-hold."""
    plotter = StrategyPlotter(output_dir=output_dir)
    return plotter.plot_strategy_vs_random_vs_buyhold(
        strategy_returns, price_data, strategy_name, symbol, n_random
    )


def plot_validation_dashboard(
    strategy_returns: pd.Series,
    price_data: pd.DataFrame,
    returns_by_holding: dict[int, pd.Series] | None = None,
    mcpt_sharpes: list[float] | None = None,
    mcpt_p_value: float | None = None,
    bootstrap_sharpes: list[float] | None = None,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
    strategy_name: str = "Strategy",
    symbol: str = "Symbol",
    output_dir: Path | None = None,
) -> Figure:
    """Quick function to create comprehensive validation dashboard."""
    plotter = StrategyPlotter(output_dir=output_dir)
    return plotter.plot_comprehensive_validation(
        strategy_returns=strategy_returns,
        price_data=price_data,
        returns_by_holding=returns_by_holding,
        mcpt_sharpes=mcpt_sharpes,
        mcpt_p_value=mcpt_p_value,
        bootstrap_sharpes=bootstrap_sharpes,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        strategy_name=strategy_name,
        symbol=symbol,
    )
