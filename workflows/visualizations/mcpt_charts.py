"""
MCPT visualization generation for publication-quality plots.

Generates:
- Permutation distributions with original values marked
- Multi-metric summary grids
- Strategy comparison charts
"""

from pathlib import Path
from typing import Any

import numpy as np

# Matplotlib imports with fallback
HAS_MATPLOTLIB = False
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    Figure = Any
except Exception:
    # Handle other matplotlib initialization errors
    Figure = Any


class MCPTVisualizer:
    """
    Generate publication-quality MCPT visualizations.

    Creates charts showing:
    - Distribution of permuted metric values
    - Original strategy value vs random baseline
    - Statistical significance annotations
    """

    def __init__(self, style: str | None = None):
        """
        Initialize the visualizer.

        Args:
            style: Matplotlib style to use (default: clean custom style)

        Raises:
            ImportError: If matplotlib is not available
        """
        if not HAS_MATPLOTLIB:
            raise ImportError(
                "matplotlib is required for visualizations. "
                "Install with: pip install matplotlib"
            )

        if style:
            try:
                plt.style.use(style)
            except Exception:
                pass  # Fall back to default style

        # Color palette
        self.colors = {
            "distribution": "#3b82f6",  # Blue
            "original": "#ef4444",      # Red
            "significant": "#22c55e",   # Green
            "not_significant": "#f59e0b",  # Amber
            "grid": "#e5e7eb",          # Light gray
            "text": "#1f2937",          # Dark gray
        }

    def plot_permutation_distribution(
        self,
        permutation_values: list[float],
        original_value: float,
        p_value: float,
        metric_name: str = "Sharpe Ratio",
        strategy_name: str = "Strategy",
        figsize: tuple[int, int] = (10, 6),
    ) -> Figure:
        """
        Plot permutation distribution with original value marked.

        Creates a histogram of permuted values with:
        - Vertical line for original strategy value
        - Shaded significance region (95th percentile+)
        - P-value annotation with significance flag
        - Clean, publication-ready styling

        Args:
            permutation_values: List of metric values from permuted data
            original_value: Metric value from original strategy
            p_value: Calculated p-value
            metric_name: Name of the metric for labeling
            strategy_name: Strategy name for title
            figsize: Figure dimensions

        Returns:
            Matplotlib Figure object
        """
        fig, ax = plt.subplots(figsize=figsize)

        is_significant = p_value < 0.05
        perm_array = np.array(permutation_values)

        # Calculate percentiles
        p5 = np.percentile(perm_array, 5)
        p95 = np.percentile(perm_array, 95)

        # Histogram of permuted values
        n, bins, patches = ax.hist(
            perm_array,
            bins=50,
            density=True,
            alpha=0.7,
            color=self.colors["distribution"],
            edgecolor="white",
            linewidth=0.5,
            label=f"Permuted Distribution (n={len(perm_array)})",
        )

        # Original value vertical line
        ax.axvline(
            original_value,
            color=self.colors["original"],
            linewidth=2.5,
            linestyle="--",
            label=f"Original: {original_value:.4f}",
        )

        # Shade significance region (above 95th percentile)
        if p95 < max(perm_array) * 1.1:
            shade_color = self.colors["significant"] if is_significant else self.colors["not_significant"]
            ax.axvspan(
                p95,
                max(perm_array) * 1.05,
                alpha=0.15,
                color=shade_color,
            )
            ax.axvline(
                p95,
                color=shade_color,
                linewidth=1,
                linestyle=":",
                alpha=0.7,
                label=f"95th percentile: {p95:.4f}",
            )

        # P-value annotation box
        sig_text = "SIGNIFICANT" if is_significant else "Not Significant"
        sig_color = self.colors["significant"] if is_significant else self.colors["not_significant"]

        textbox = f"p-value: {p_value:.4f}\n{sig_text}"
        props = dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=sig_color, linewidth=2)
        ax.text(
            0.98, 0.95,
            textbox,
            transform=ax.transAxes,
            fontsize=11,
            fontweight="bold",
            color=sig_color,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=props,
        )

        # Labels and title
        ax.set_xlabel(metric_name, fontsize=12, color=self.colors["text"])
        ax.set_ylabel("Density", fontsize=12, color=self.colors["text"])
        ax.set_title(
            f"MCPT Distribution: {metric_name}\n{strategy_name}",
            fontsize=14,
            fontweight="bold",
            color=self.colors["text"],
        )

        # Legend
        ax.legend(loc="upper left", framealpha=0.9)

        # Clean up appearance
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(colors=self.colors["text"])

        plt.tight_layout()
        return fig

    def plot_multi_metric_summary(
        self,
        metrics_data: dict[str, dict[str, Any]],
        strategy_name: str = "Strategy",
        figsize: tuple[int, int] = (12, 10),
    ) -> Figure:
        """
        Plot summary grid of all tested metrics.

        Args:
            metrics_data: Dict mapping metric names to their data:
                {
                    "sharpe_ratio": {
                        "permutation_values": [...],
                        "original_value": 1.5,
                        "p_value": 0.02,
                        "is_significant": True
                    },
                    ...
                }
            strategy_name: Strategy name for title
            figsize: Figure dimensions

        Returns:
            Matplotlib Figure with grid of mini-histograms
        """
        metrics = list(metrics_data.keys())
        n_metrics = len(metrics)

        if n_metrics == 0:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(0.5, 0.5, "No metrics to display", ha="center", va="center")
            return fig

        # Determine grid size
        if n_metrics <= 2:
            nrows, ncols = 1, 2
        elif n_metrics <= 4:
            nrows, ncols = 2, 2
        elif n_metrics <= 6:
            nrows, ncols = 2, 3
        else:
            nrows, ncols = 3, 3

        fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
        axes = axes.flatten() if n_metrics > 1 else [axes]

        for i, metric in enumerate(metrics):
            if i >= len(axes):
                break

            ax = axes[i]
            data = metrics_data[metric]

            perm_values = data.get("permutation_values", [])
            original = data.get("original_value", 0)
            p_val = data.get("p_value", 1.0)
            is_sig = data.get("is_significant", False)

            if len(perm_values) > 0:
                # Mini histogram
                ax.hist(
                    perm_values,
                    bins=30,
                    alpha=0.7,
                    color=self.colors["distribution"],
                    edgecolor="white",
                )
                ax.axvline(
                    original,
                    color=self.colors["original"],
                    linewidth=2,
                    linestyle="--",
                )

                # Background color based on significance
                if is_sig:
                    ax.set_facecolor("#dcfce7")  # Light green
                else:
                    ax.set_facecolor("#fef9c3")  # Light yellow

            # Title with p-value
            metric_label = metric.replace("_", " ").title()
            ax.set_title(
                f"{metric_label}\np={p_val:.4f}",
                fontsize=10,
                fontweight="bold" if is_sig else "normal",
            )

            ax.tick_params(labelsize=8)

        # Hide unused axes
        for i in range(n_metrics, len(axes)):
            axes[i].set_visible(False)

        # Main title
        fig.suptitle(
            f"MCPT Summary: {strategy_name}",
            fontsize=14,
            fontweight="bold",
            y=1.02,
        )

        plt.tight_layout()
        return fig

    def plot_strategy_comparison(
        self,
        strategies_data: list[dict[str, Any]],
        metric: str = "sharpe_ratio",
        figsize: tuple[int, int] = (12, 6),
    ) -> Figure:
        """
        Compare multiple strategies' MCPT results.

        Creates a bar chart with error bars showing permutation range.

        Args:
            strategies_data: List of dicts with strategy results:
                [
                    {
                        "name": "SMA_10_30",
                        "original_value": 1.5,
                        "p_value": 0.02,
                        "is_significant": True,
                        "perm_5th": 0.1,
                        "perm_95th": 0.8,
                    },
                    ...
                ]
            metric: Metric name for labeling
            figsize: Figure dimensions

        Returns:
            Matplotlib Figure
        """
        fig, ax = plt.subplots(figsize=figsize)

        names = [s["name"] for s in strategies_data]
        originals = [s["original_value"] for s in strategies_data]
        p_values = [s["p_value"] for s in strategies_data]
        is_sig = [s["is_significant"] for s in strategies_data]

        # Error bars from permutation distribution
        lowers = [s.get("perm_5th", 0) for s in strategies_data]
        uppers = [s.get("perm_95th", 0) for s in strategies_data]

        x = np.arange(len(names))
        colors = [
            self.colors["significant"] if sig else self.colors["not_significant"]
            for sig in is_sig
        ]

        # Bar chart
        bars = ax.bar(
            x, originals,
            color=colors,
            alpha=0.8,
            edgecolor="white",
            linewidth=2,
        )

        # Error bars showing permutation range
        yerr_lower = [max(0, o - l) for o, l in zip(originals, lowers)]
        yerr_upper = [max(0, u - o) for o, u in zip(originals, uppers)]

        ax.errorbar(
            x, originals,
            yerr=[yerr_lower, yerr_upper],
            fmt="none",
            ecolor="gray",
            capsize=5,
            capthick=2,
            alpha=0.7,
        )

        # Zero line
        ax.axhline(0, color="black", linewidth=0.5, linestyle="-")

        # P-value annotations
        for i, (bar, p) in enumerate(zip(bars, p_values)):
            height = bar.get_height()
            offset = 0.05 * max(abs(h) for h in originals) if originals else 0.1
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + offset if height >= 0 else height - offset,
                f"p={p:.3f}",
                ha="center",
                va="bottom" if height >= 0 else "top",
                fontsize=9,
                color=self.colors["text"],
            )

        # Labels
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=45, ha="right")
        ax.set_ylabel(metric.replace("_", " ").title(), fontsize=12)
        ax.set_title(
            f"Strategy Comparison: {metric.replace('_', ' ').title()}",
            fontsize=14,
            fontweight="bold",
        )

        # Legend
        sig_patch = mpatches.Patch(
            color=self.colors["significant"],
            label="Significant (p < 0.05)"
        )
        ns_patch = mpatches.Patch(
            color=self.colors["not_significant"],
            label="Not Significant"
        )
        ax.legend(handles=[sig_patch, ns_patch], loc="upper right")

        # Clean up
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        plt.tight_layout()
        return fig


# Convenience functions

def plot_permutation_distribution(
    permutation_values: list[float],
    original_value: float,
    p_value: float,
    metric_name: str = "Sharpe Ratio",
    **kwargs,
) -> Figure:
    """
    Quick function to plot a permutation distribution.

    See MCPTVisualizer.plot_permutation_distribution for full docs.
    """
    viz = MCPTVisualizer()
    return viz.plot_permutation_distribution(
        permutation_values=permutation_values,
        original_value=original_value,
        p_value=p_value,
        metric_name=metric_name,
        **kwargs,
    )
