"""
Research Dashboard - Unified View of Research Progress

Provides a single-pane view of:
- All experiments run and their outcomes
- Significant strategies found
- Coverage matrix (which symbol-strategy pairs tested)
- Gaps in research
- Learning curve over time
- Next priorities

Usage:
    dashboard = ResearchDashboard()
    print(dashboard.get_status())
    dashboard.show_coverage_heatmap()
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from workflows.research.knowledge_base import KnowledgeBase


# Known strategy names from the system
KNOWN_STRATEGIES = [
    # Traditional
    "sma_crossover", "ema_crossover", "macd", "rsi_momentum",
    "rsi_reversal", "bollinger_breakout", "bollinger_reversal",
    "momentum_20d", "momentum_60d", "trend_breakout", "trend_sma_cross",
    "mean_reversion_rsi", "volatility_regime",
    # ML
    "ml_xgboost", "ml_random_forest", "ml_ensemble", "ml_lstm", "ml_transformer",
    # Alternative
    "sentiment_momentum", "sentiment_reversal", "insider_momentum",
    "multi_signal", "regime_adaptive", "cointegration_pairs",
]

# Default symbols
DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "MRVL", "CRM", "ORCL",
    "JPM", "BAC", "GS", "MS", "WFC", "V", "MA",
]


class ResearchDashboard:
    """
    Unified view of all research progress and learnings.

    This dashboard aggregates data from:
    - Knowledge base (successes, failures, insights)
    - Session history
    - Backtest results
    """

    def __init__(
        self,
        knowledge_path: Path | None = None,
        results_path: Path | None = None,
    ):
        self.knowledge_path = knowledge_path or Path.home() / "quant_results" / "knowledge"
        self.results_path = results_path or Path.home() / "quant_results"
        self.kb = KnowledgeBase(self.knowledge_path)

    def get_status(self) -> dict[str, Any]:
        """
        Get current state of all research.

        Returns comprehensive dictionary with:
        - total_experiments: Number of experiments run
        - significant_strategies: List of strategies that showed significance
        - coverage: Percentage of symbol-strategy pairs tested
        - gaps: Untested combinations
        - recent_insights: Insights from last 7 days
        - next_priorities: Suggested next experiments
        """
        # Count experiments
        total_experiments = len(self.kb.tested_hypotheses)

        # Get significant strategies
        significant = self._get_significant_strategies()

        # Calculate coverage
        coverage = self._calculate_coverage()

        # Identify gaps
        gaps = self._identify_gaps()

        # Recent insights
        recent_insights = self._get_recent_insights(days=7)

        # Next priorities
        next_priorities = self._suggest_next_experiments()

        return {
            "total_experiments": total_experiments,
            "total_successes": len(self.kb.successes),
            "total_failures": len(self.kb.failures),
            "significant_strategies": significant,
            "coverage_pct": coverage["percentage"],
            "coverage_details": coverage,
            "gaps": gaps[:20],  # Top 20 gaps
            "total_gaps": len(gaps),
            "recent_insights": recent_insights,
            "next_priorities": next_priorities,
            "patterns_found": len(self.kb.patterns),
            "updated_at": datetime.now().isoformat(),
        }

    def _get_significant_strategies(self) -> list[dict]:
        """Get strategies that showed statistical significance."""
        results = []
        seen = set()

        for success in sorted(self.kb.successes, key=lambda x: x.val_sharpe, reverse=True):
            key = f"{success.strategy_name}_{success.symbol}"
            if key not in seen:
                seen.add(key)
                results.append({
                    "strategy": success.strategy_name,
                    "symbol": success.symbol,
                    "val_sharpe": round(success.val_sharpe, 2),
                    "p_value": round(success.p_value, 4),
                    "params": success.params,
                })

        return results

    def _calculate_coverage(self) -> dict:
        """Calculate coverage matrix - what's been tested."""
        # Get all tested pairs from successes and failures
        tested_pairs = set()

        for success in self.kb.successes:
            tested_pairs.add((success.strategy_name, success.symbol))

        for failure in self.kb.failures:
            tested_pairs.add((failure["strategy_name"], failure["symbol"]))

        # Calculate coverage
        total_possible = len(KNOWN_STRATEGIES) * len(DEFAULT_SYMBOLS)

        # Filter to known strategies
        valid_pairs = {
            (s, sym) for s, sym in tested_pairs
            if s in KNOWN_STRATEGIES and sym in DEFAULT_SYMBOLS
        }

        percentage = (len(valid_pairs) / total_possible * 100) if total_possible > 0 else 0

        # Build coverage by strategy
        coverage_by_strategy = defaultdict(list)
        for strategy, symbol in valid_pairs:
            coverage_by_strategy[strategy].append(symbol)

        return {
            "percentage": round(percentage, 1),
            "tested_pairs": len(valid_pairs),
            "total_possible": total_possible,
            "by_strategy": dict(coverage_by_strategy),
            "strategies_tested": list(set(s for s, _ in valid_pairs)),
            "symbols_covered": list(set(sym for _, sym in valid_pairs)),
        }

    def _identify_gaps(self) -> list[tuple[str, str]]:
        """Identify untested strategy-symbol combinations."""
        tested_pairs = set()

        for success in self.kb.successes:
            tested_pairs.add((success.strategy_name, success.symbol))

        for failure in self.kb.failures:
            tested_pairs.add((failure["strategy_name"], failure["symbol"]))

        gaps = []
        for strategy in KNOWN_STRATEGIES:
            for symbol in DEFAULT_SYMBOLS:
                if (strategy, symbol) not in tested_pairs:
                    gaps.append((strategy, symbol))

        return gaps

    def _get_recent_insights(self, days: int = 7) -> list[dict]:
        """Get insights from the last N days."""
        cutoff = datetime.now() - timedelta(days=days)

        recent = []
        for insight in self.kb.insights:
            try:
                insight_time = datetime.fromisoformat(insight.timestamp)
                if insight_time > cutoff:
                    recent.append({
                        "category": insight.category,
                        "content": insight.content,
                        "confidence": insight.confidence,
                        "timestamp": insight.timestamp,
                    })
            except (ValueError, AttributeError):
                continue

        return sorted(recent, key=lambda x: x["timestamp"], reverse=True)

    def _suggest_next_experiments(self, n: int = 5) -> list[dict]:
        """Suggest next experiments based on patterns and gaps."""
        suggestions = []

        # 1. Prioritize strategies that have worked on some symbols
        winning_strategies = defaultdict(list)
        for success in self.kb.successes:
            winning_strategies[success.strategy_name].append({
                "symbol": success.symbol,
                "sharpe": success.val_sharpe,
            })

        # Suggest trying winning strategies on untested symbols
        gaps = self._identify_gaps()
        gap_set = set(gaps)

        for strategy, wins in sorted(
            winning_strategies.items(),
            key=lambda x: len(x[1]),
            reverse=True
        ):
            avg_sharpe = np.mean([w["sharpe"] for w in wins])
            for symbol in DEFAULT_SYMBOLS:
                if (strategy, symbol) in gap_set:
                    suggestions.append({
                        "strategy": strategy,
                        "symbol": symbol,
                        "reason": f"Works on {len(wins)} symbols (avg Sharpe {avg_sharpe:.2f})",
                        "priority": "high" if avg_sharpe > 1.0 else "medium",
                    })
                    if len(suggestions) >= n * 2:
                        break
            if len(suggestions) >= n * 2:
                break

        # 2. Add some exploration suggestions (untested strategies)
        tested_strategies = set(self._calculate_coverage()["by_strategy"].keys())
        untested_strategies = [s for s in KNOWN_STRATEGIES if s not in tested_strategies]

        for strategy in untested_strategies[:2]:
            # Suggest on liquid symbols first
            for symbol in ["AAPL", "MSFT", "NVDA"]:
                if (strategy, symbol) in gap_set:
                    suggestions.append({
                        "strategy": strategy,
                        "symbol": symbol,
                        "reason": "Strategy not yet tested",
                        "priority": "low",
                    })
                    break

        return suggestions[:n]

    def get_coverage_matrix(self) -> pd.DataFrame:
        """
        Get full coverage matrix as a DataFrame.

        Returns DataFrame with strategies as rows, symbols as columns.
        Values: 'success', 'failure', 'untested'
        """
        matrix = pd.DataFrame(
            index=KNOWN_STRATEGIES,
            columns=DEFAULT_SYMBOLS,
            data="untested"
        )

        # Mark successes
        for success in self.kb.successes:
            if success.strategy_name in matrix.index and success.symbol in matrix.columns:
                matrix.loc[success.strategy_name, success.symbol] = "success"

        # Mark failures (don't overwrite successes)
        for failure in self.kb.failures:
            strat = failure["strategy_name"]
            sym = failure["symbol"]
            if strat in matrix.index and sym in matrix.columns:
                if matrix.loc[strat, sym] == "untested":
                    matrix.loc[strat, sym] = "failure"

        return matrix

    def get_learning_curve(self) -> pd.DataFrame:
        """
        Get learning curve - significant findings over time.

        Returns DataFrame with dates and cumulative discoveries.
        """
        discoveries = []

        for success in self.kb.successes:
            try:
                date = datetime.fromisoformat(success.timestamp).date()
                discoveries.append({
                    "date": date,
                    "strategy": success.strategy_name,
                    "symbol": success.symbol,
                    "sharpe": success.val_sharpe,
                })
            except (ValueError, AttributeError):
                continue

        if not discoveries:
            return pd.DataFrame(columns=["date", "cumulative_discoveries", "avg_sharpe"])

        df = pd.DataFrame(discoveries)
        df = df.sort_values("date")

        # Group by date
        daily = df.groupby("date").agg({
            "strategy": "count",
            "sharpe": "mean"
        }).rename(columns={"strategy": "new_discoveries"})

        daily["cumulative_discoveries"] = daily["new_discoveries"].cumsum()
        daily = daily.reset_index()

        return daily

    def show_coverage_heatmap(self, save_path: str | None = None) -> None:
        """
        Display coverage heatmap.

        Shows which strategy-symbol pairs have been tested and their outcomes.
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
        except ImportError:
            print("matplotlib and seaborn required for visualization")
            return

        matrix = self.get_coverage_matrix()

        # Convert to numeric
        numeric = matrix.replace({
            "success": 2,
            "failure": 1,
            "untested": 0
        }).astype(int)

        fig, ax = plt.subplots(figsize=(16, 10))

        cmap = sns.color_palette(["lightgray", "salmon", "limegreen"])
        sns.heatmap(
            numeric,
            ax=ax,
            cmap=cmap,
            cbar_kws={"ticks": [0, 1, 2], "label": "Status"},
            linewidths=0.5,
        )

        # Fix colorbar labels
        cbar = ax.collections[0].colorbar
        cbar.set_ticklabels(["Untested", "Failed", "Success"])

        ax.set_title("Research Coverage Matrix\n(Strategy × Symbol)", fontsize=14)
        ax.set_xlabel("Symbol")
        ax.set_ylabel("Strategy")

        plt.xticks(rotation=45, ha="right")
        plt.yticks(rotation=0)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Saved to {save_path}")
        else:
            plt.show()

    def show_learning_curve(self, save_path: str | None = None) -> None:
        """Display learning curve visualization."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib required for visualization")
            return

        curve = self.get_learning_curve()

        if curve.empty:
            print("No data for learning curve")
            return

        fig, ax = plt.subplots(figsize=(10, 6))

        ax.plot(curve["date"], curve["cumulative_discoveries"], marker="o", linewidth=2)
        ax.fill_between(curve["date"], curve["cumulative_discoveries"], alpha=0.3)

        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative Significant Discoveries")
        ax.set_title("Research Learning Curve\n(Are we finding new patterns?)")
        ax.grid(True, alpha=0.3)

        plt.xticks(rotation=45)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Saved to {save_path}")
        else:
            plt.show()

    def export_research_summary(self) -> str:
        """
        Export a markdown summary for Claude to read at session start.

        Returns comprehensive markdown string with all key information.
        """
        status = self.get_status()

        lines = [
            "# Research Session Briefing",
            f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Quick Stats",
            f"- Total experiments: {status['total_experiments']}",
            f"- Significant findings: {status['total_successes']}",
            f"- Failed hypotheses: {status['total_failures']}",
            f"- Patterns discovered: {status['patterns_found']}",
            f"- Coverage: {status['coverage_pct']:.1f}%",
            "",
            "## Top Performing Strategies",
        ]

        for i, strat in enumerate(status["significant_strategies"][:10], 1):
            lines.append(
                f"{i}. **{strat['strategy']}** on {strat['symbol']} "
                f"(Sharpe: {strat['val_sharpe']}, p={strat['p_value']})"
            )

        lines.extend([
            "",
            "## Suggested Next Experiments",
        ])

        for i, sugg in enumerate(status["next_priorities"], 1):
            lines.append(f"{i}. {sugg['strategy']} on {sugg['symbol']} - {sugg['reason']}")

        lines.extend([
            "",
            f"## Coverage Gaps ({status['total_gaps']} untested combinations)",
        ])

        gap_summary = defaultdict(list)
        for strategy, symbol in status["gaps"][:50]:
            gap_summary[strategy].append(symbol)

        for strategy, symbols in list(gap_summary.items())[:5]:
            lines.append(f"- {strategy}: {', '.join(symbols[:5])}...")

        if status["recent_insights"]:
            lines.extend([
                "",
                "## Recent Insights",
            ])
            for insight in status["recent_insights"][:5]:
                lines.append(f"- [{insight['category']}] {insight['content']}")

        if self.kb.patterns:
            lines.extend([
                "",
                "## Discovered Patterns",
            ])
            for pattern in self.kb.get_patterns(min_confidence=0.5)[:5]:
                lines.append(
                    f"- **{pattern.name}**: {pattern.description} "
                    f"(confidence: {pattern.confidence:.0%})"
                )

        return "\n".join(lines)

    def get_strategy_performance(self, strategy_name: str) -> dict:
        """Get detailed performance for a specific strategy."""
        successes = [s for s in self.kb.successes if s.strategy_name == strategy_name]
        failures = [f for f in self.kb.failures if f["strategy_name"] == strategy_name]

        if not successes and not failures:
            return {"error": f"No data for strategy: {strategy_name}"}

        win_rate = len(successes) / (len(successes) + len(failures)) if (successes or failures) else 0

        return {
            "strategy": strategy_name,
            "total_tests": len(successes) + len(failures),
            "successes": len(successes),
            "failures": len(failures),
            "win_rate": round(win_rate, 2),
            "avg_sharpe": round(np.mean([s.val_sharpe for s in successes]), 2) if successes else None,
            "best_sharpe": round(max(s.val_sharpe for s in successes), 2) if successes else None,
            "winning_symbols": [s.symbol for s in successes],
            "failing_symbols": [f["symbol"] for f in failures],
        }

    def get_symbol_performance(self, symbol: str) -> dict:
        """Get detailed performance for a specific symbol."""
        successes = [s for s in self.kb.successes if s.symbol == symbol]
        failures = [f for f in self.kb.failures if f["symbol"] == symbol]

        if not successes and not failures:
            return {"error": f"No data for symbol: {symbol}"}

        win_rate = len(successes) / (len(successes) + len(failures)) if (successes or failures) else 0

        return {
            "symbol": symbol,
            "total_tests": len(successes) + len(failures),
            "successes": len(successes),
            "failures": len(failures),
            "win_rate": round(win_rate, 2),
            "avg_sharpe": round(np.mean([s.val_sharpe for s in successes]), 2) if successes else None,
            "best_strategy": max(successes, key=lambda s: s.val_sharpe).strategy_name if successes else None,
            "working_strategies": list(set(s.strategy_name for s in successes)),
            "failed_strategies": list(set(f["strategy_name"] for f in failures)),
        }


def get_dashboard_status() -> dict:
    """Quick function to get dashboard status."""
    dashboard = ResearchDashboard()
    return dashboard.get_status()


def print_research_briefing():
    """Print research briefing to console."""
    dashboard = ResearchDashboard()
    print(dashboard.export_research_summary())


if __name__ == "__main__":
    dashboard = ResearchDashboard()

    print("=" * 60)
    print("RESEARCH DASHBOARD")
    print("=" * 60)

    status = dashboard.get_status()

    print(f"\nTotal Experiments: {status['total_experiments']}")
    print(f"Significant Findings: {status['total_successes']}")
    print(f"Failed Hypotheses: {status['total_failures']}")
    print(f"Coverage: {status['coverage_pct']:.1f}%")
    print(f"Gaps Remaining: {status['total_gaps']}")

    print("\n--- Top Strategies ---")
    for strat in status["significant_strategies"][:5]:
        print(f"  {strat['strategy']} on {strat['symbol']}: Sharpe={strat['val_sharpe']}")

    print("\n--- Next Priorities ---")
    for sugg in status["next_priorities"]:
        print(f"  [{sugg['priority']}] {sugg['strategy']} on {sugg['symbol']}")

    print("\n--- Full Briefing ---")
    print(dashboard.export_research_summary())
