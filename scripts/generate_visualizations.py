#!/usr/bin/env python3
"""
Generate Visualizations for Research System

Creates charts and figures for inspection:
1. Coverage heatmap
2. Learning curve
3. Strategy performance comparison
4. Sector flow analysis
5. Options sentiment dashboard
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings('ignore')

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Output directory
OUTPUT_DIR = Path.home() / "quant_results" / "visualizations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_figure(name: str, fig=None):
    """Save figure to output directory."""
    if fig is None:
        fig = plt.gcf()
    path = OUTPUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"Saved: {path}")
    return path


# =============================================================================
# FIGURE 1: Coverage Heatmap
# =============================================================================

def create_coverage_heatmap():
    """Create a heatmap showing strategy-symbol coverage."""
    print("\n1. Creating coverage heatmap...")

    from workflows.research.research_dashboard import ResearchDashboard

    dashboard = ResearchDashboard()
    matrix = dashboard.get_coverage_matrix()

    # Convert to numeric
    numeric = matrix.replace({
        "success": 2,
        "failure": 1,
        "untested": 0
    }).astype(int)

    fig, ax = plt.subplots(figsize=(16, 12))

    # Create custom colormap
    cmap = sns.color_palette(["#E8E8E8", "#FF6B6B", "#4ECDC4"])

    sns.heatmap(
        numeric,
        ax=ax,
        cmap=cmap,
        cbar_kws={"ticks": [0.33, 1, 1.67]},
        linewidths=0.5,
        linecolor='white',
    )

    # Fix colorbar
    cbar = ax.collections[0].colorbar
    cbar.set_ticklabels(["Untested", "Failed", "Success"])

    ax.set_title("Research Coverage Matrix\n(Strategy × Symbol)", fontsize=16, fontweight='bold')
    ax.set_xlabel("Symbol", fontsize=12)
    ax.set_ylabel("Strategy", fontsize=12)

    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.yticks(rotation=0, fontsize=9)

    # Add stats
    stats = dashboard.get_status()
    fig.text(0.02, 0.02,
             f"Coverage: {stats['coverage_pct']:.1f}% | "
             f"Success: {stats['total_successes']} | "
             f"Tested: {stats['total_experiments']}",
             fontsize=10, style='italic')

    save_figure("coverage_heatmap", fig)


# =============================================================================
# FIGURE 2: Learning Curve
# =============================================================================

def create_learning_curve():
    """Create learning curve showing discoveries over time."""
    print("\n2. Creating learning curve...")

    from workflows.research.research_dashboard import ResearchDashboard

    dashboard = ResearchDashboard()
    curve = dashboard.get_learning_curve()

    if curve.empty:
        print("  No learning curve data available")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(curve["date"], curve["cumulative_discoveries"],
            marker="o", linewidth=2, markersize=8, color="#4ECDC4")
    ax.fill_between(curve["date"], curve["cumulative_discoveries"],
                    alpha=0.3, color="#4ECDC4")

    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Cumulative Significant Discoveries", fontsize=12)
    ax.set_title("Research Learning Curve\n(Are we finding new patterns?)",
                 fontsize=16, fontweight='bold')

    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)

    save_figure("learning_curve", fig)


# =============================================================================
# FIGURE 3: Strategy Performance Comparison
# =============================================================================

def create_strategy_comparison():
    """Create bar chart comparing strategy performance."""
    print("\n3. Creating strategy performance comparison...")

    from workflows.research.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    successes = kb.get_successful_strategies(min_sharpe=0.5)

    if not successes:
        print("  No successful strategies to plot")
        return

    # Group by strategy
    strategy_sharpes = {}
    for s in successes:
        if s.strategy_name not in strategy_sharpes:
            strategy_sharpes[s.strategy_name] = []
        strategy_sharpes[s.strategy_name].append(s.val_sharpe)

    # Calculate stats
    data = []
    for strategy, sharpes in strategy_sharpes.items():
        data.append({
            "strategy": strategy,
            "avg_sharpe": np.mean(sharpes),
            "max_sharpe": max(sharpes),
            "count": len(sharpes),
        })

    df = pd.DataFrame(data).sort_values("avg_sharpe", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 8))

    colors = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(df)))

    bars = ax.barh(df["strategy"], df["avg_sharpe"], color=colors)

    # Add count labels
    for i, (bar, count) in enumerate(zip(bars, df["count"])):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                f"n={count}", va='center', fontsize=9)

    ax.set_xlabel("Average Validation Sharpe Ratio", fontsize=12)
    ax.set_ylabel("Strategy", fontsize=12)
    ax.set_title("Strategy Performance Comparison\n(Successful strategies only)",
                 fontsize=16, fontweight='bold')

    ax.axvline(x=1.0, color='red', linestyle='--', alpha=0.5, label='Sharpe=1.0')
    ax.legend()

    save_figure("strategy_comparison", fig)


# =============================================================================
# FIGURE 4: Sector Flow Analysis
# =============================================================================

def create_sector_flow_chart():
    """Create sector flow analysis chart."""
    print("\n4. Creating sector flow chart...")

    # Load sector snapshot
    snapshot_path = Path.home() / "quant_results" / "system_tests" / "sector_snapshot.json"

    if not snapshot_path.exists():
        print("  No sector snapshot data available")
        return

    with open(snapshot_path) as f:
        snapshot = json.load(f)

    sectors = snapshot.get("sectors", {})

    data = []
    for sector, info in sectors.items():
        if "net_flow_20d" in info:
            data.append({
                "sector": sector.replace("_", " ").title(),
                "flow": info["net_flow_20d"],
                "signal": info.get("signal", "neutral"),
            })

    if not data:
        print("  No sector data to plot")
        return

    df = pd.DataFrame(data).sort_values("flow", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 8))

    colors = ["#FF6B6B" if f < 0 else "#4ECDC4" for f in df["flow"]]

    bars = ax.barh(df["sector"], df["flow"] / 1e6, color=colors)

    ax.axvline(x=0, color='black', linewidth=0.5)

    ax.set_xlabel("Estimated Net Flow ($ Millions)", fontsize=12)
    ax.set_ylabel("Sector", fontsize=12)
    ax.set_title("Sector ETF Flow Estimates (20 Days)\n(Positive = Inflow, Negative = Outflow)",
                 fontsize=16, fontweight='bold')

    # Add value labels
    for bar in bars:
        width = bar.get_width()
        label_x = width + 0.1 if width >= 0 else width - 0.1
        ha = 'left' if width >= 0 else 'right'
        ax.text(label_x, bar.get_y() + bar.get_height()/2,
                f'{width:.1f}M', va='center', ha=ha, fontsize=9)

    save_figure("sector_flows", fig)


# =============================================================================
# FIGURE 5: Options Sentiment Dashboard
# =============================================================================

def create_options_dashboard():
    """Create options sentiment dashboard."""
    print("\n5. Creating options sentiment dashboard...")

    # Load options data
    options_path = Path.home() / "quant_results" / "system_tests" / "options_full_results.json"

    if not options_path.exists():
        print("  No options data available")
        return

    with open(options_path) as f:
        options_data = json.load(f)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Put/Call Ratios
    ax1 = axes[0, 0]
    symbols = []
    pc_ratios = []
    for symbol in ["AAPL", "MSFT", "SPY"]:
        if symbol in options_data and "features" in options_data[symbol]:
            symbols.append(symbol)
            pc_ratios.append(options_data[symbol]["features"]["put_call_volume_ratio"])

    if symbols:
        colors = ["#FF6B6B" if r > 1 else "#4ECDC4" if r < 0.7 else "#FFE66D" for r in pc_ratios]
        ax1.bar(symbols, pc_ratios, color=colors)
        ax1.axhline(y=1.0, color='red', linestyle='--', alpha=0.5, label='Neutral')
        ax1.axhline(y=0.7, color='green', linestyle='--', alpha=0.5, label='Bullish')
        ax1.set_ylabel("Put/Call Ratio")
        ax1.set_title("Put/Call Volume Ratios")
        ax1.legend()

    # 2. IV Skew
    ax2 = axes[0, 1]
    iv_skews = []
    for symbol in ["AAPL", "MSFT", "SPY"]:
        if symbol in options_data and "features" in options_data[symbol]:
            iv_skews.append(options_data[symbol]["features"]["iv_skew"])

    if iv_skews:
        colors = ["#FF6B6B" if s > 0 else "#4ECDC4" for s in iv_skews]
        ax2.bar(symbols, iv_skews, color=colors)
        ax2.axhline(y=0, color='black', linewidth=0.5)
        ax2.set_ylabel("IV Skew (Put - Call)")
        ax2.set_title("Implied Volatility Skew")

    # 3. Contract Counts
    ax3 = axes[1, 0]
    calls = []
    puts = []
    for symbol in ["AAPL", "MSFT", "SPY"]:
        if symbol in options_data:
            calls.append(options_data[symbol].get("calls", 0))
            puts.append(options_data[symbol].get("puts", 0))

    if calls:
        x = np.arange(len(symbols))
        width = 0.35
        ax3.bar(x - width/2, calls, width, label='Calls', color='#4ECDC4')
        ax3.bar(x + width/2, puts, width, label='Puts', color='#FF6B6B')
        ax3.set_xticks(x)
        ax3.set_xticklabels(symbols)
        ax3.set_ylabel("Contract Count")
        ax3.set_title("Options Chain Size")
        ax3.legend()

    # 4. Max Pain
    ax4 = axes[1, 1]
    if "AAPL_max_pain" in options_data:
        mp = options_data["AAPL_max_pain"]
        if mp.get("max_pain") and mp.get("current_price"):
            prices = [mp["current_price"], mp["max_pain"]]
            labels = ["Current", "Max Pain"]
            colors = ["#4ECDC4", "#FFE66D"]
            ax4.bar(labels, prices, color=colors)
            ax4.set_ylabel("Price ($)")
            ax4.set_title(f"AAPL Max Pain Analysis\n(Distance: {mp.get('distance_pct', 0):.1f}%)")

    fig.suptitle("Options Market Sentiment Dashboard", fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()

    save_figure("options_dashboard", fig)


# =============================================================================
# FIGURE 6: Cross-Asset Correlation Matrix
# =============================================================================

def create_correlation_matrix():
    """Create cross-asset correlation heatmap."""
    print("\n6. Creating correlation matrix...")

    corr_path = Path.home() / "quant_results" / "experiments" / "correlation_matrix.csv"

    if not corr_path.exists():
        print("  No correlation data available")
        return

    corr = pd.read_csv(corr_path, index_col=0)

    fig, ax = plt.subplots(figsize=(10, 8))

    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)

    sns.heatmap(
        corr,
        mask=mask,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.5,
        ax=ax,
        cbar_kws={"shrink": 0.8},
    )

    ax.set_title("Cross-Asset Return Correlations (3 Month)",
                 fontsize=16, fontweight='bold')

    save_figure("correlation_matrix", fig)


# =============================================================================
# FIGURE 7: Failure Analysis
# =============================================================================

def create_failure_analysis():
    """Create failure analysis visualization."""
    print("\n7. Creating failure analysis...")

    from workflows.research.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    summary = kb.summarize_failures()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Failures by strategy
    ax1 = axes[0]
    by_strategy = summary.get("by_strategy", {})
    if by_strategy:
        strategies = list(by_strategy.keys())[:10]
        counts = [by_strategy[s]["count"] for s in strategies]

        colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(strategies)))
        ax1.barh(strategies, counts, color=colors)
        ax1.set_xlabel("Failure Count")
        ax1.set_title("Failures by Strategy")

    # Failures by symbol
    ax2 = axes[1]
    by_symbol = summary.get("by_symbol", {})
    if by_symbol:
        symbols = list(by_symbol.keys())[:10]
        counts = [by_symbol[s]["count"] for s in symbols]

        colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(symbols)))
        ax2.barh(symbols, counts, color=colors)
        ax2.set_xlabel("Failure Count")
        ax2.set_title("Failures by Symbol")

    fig.suptitle("Failure Analysis\n(What to Avoid)", fontsize=16, fontweight='bold')
    plt.tight_layout()

    save_figure("failure_analysis", fig)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Generate all visualizations."""
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    create_coverage_heatmap()
    create_learning_curve()
    create_strategy_comparison()
    create_sector_flow_chart()
    create_options_dashboard()
    create_correlation_matrix()
    create_failure_analysis()

    print("\n" + "=" * 70)
    print(f"All visualizations saved to: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
